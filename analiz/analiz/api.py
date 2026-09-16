"""Contract ⑤ — the read API. Track B serves it, track C consumes it.

Every endpoint in section 7.3 of the parent record, plus the per-episode
`/anomaliler/{id}/gecisler` the İZ B record adds and the global `/gecisler`
feed the integration phase adds. Paths, query parameter names and field names come from the
contract and are not this module's to improve: track C builds against them, and
a helpful rename here is a silent breakage there.

SEPARATE PROCESS, by decision K1. The database is the only contact surface
between components, and that holds inside track B as well as between tracks: a
crashed or slow API must not be able to stop the detector, and a long scan turn
must not be able to stall the dashboard. `python -m analiz.api` runs this;
`python -m analiz tara` runs the loop; neither imports the other's runtime state.

READ-ONLY, with one exception. `POST /anomaliler/{id}/onayla` is the operator
acknowledgement, and it goes through `OlayDeposu.onayla` rather than issuing its
own UPDATE — so the episode tables still have exactly one writer, and the
acknowledgement lands in the journal with who and when, which section 6.4 makes
an audit requirement rather than a nicety.

Where the contract is silent — pagination, error shapes, status codes — the
choices are documented in `analiz/README.md` under "API kararları", because
track C needs to know them.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .ayar import Ayar
from .olay import OlayDeposu
from .sozlesme import Durum, OlcumTipi, Seviye, Tip
from .termal import KareHatasi, kare_coz

__all__ = ["olustur", "zaman_yaz"]

_gunluk = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------


def zaman_yaz(an: datetime | None) -> str | None:
    """Contract timestamp: UTC, ISO 8601, literal Z.

    Every timestamp leaving this API goes through here. Offsets such as +03:00
    are never emitted — one timezone everywhere means nobody consuming this has
    to ask "was that local?", which matters more than usual in a system that
    claims to detect clock drift.
    """
    if an is None:
        return None
    return an.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ApiHatasi(HTTPException):
    """An error in the documented shape.

    `kod` is a stable machine-readable slug track C can branch on; `mesaj` is
    Turkish because it is what ends up in front of an operator when the
    dashboard has nothing better to show.
    """

    def __init__(self, durum_kodu: int, kod: str, mesaj: str, **ayrinti: Any) -> None:
        super().__init__(status_code=durum_kodu, detail={"kod": kod, "mesaj": mesaj, **ayrinti})


def _bulunamadi(ne: str, kimlik: str) -> ApiHatasi:
    return ApiHatasi(404, "bulunamadi", f"{ne} bulunamadı: {kimlik}", kimlik=kimlik)


def _zaman_oku(metin: str | None, alan: str) -> datetime | None:
    """Parse a query-string timestamp, or reject it clearly."""
    if metin is None:
        return None
    try:
        an = datetime.fromisoformat(metin.strip().replace("Z", "+00:00"))
    except ValueError:
        raise ApiHatasi(
            400,
            "gecersiz_zaman",
            f"{alan} geçerli bir ISO 8601 zaman damgası değil: {metin!r}",
            alan=alan,
        ) from None
    return an if an.tzinfo else an.replace(tzinfo=timezone.utc)


#: Downsampling buckets the series endpoint accepts for `aralik`.
#:
#: A fixed vocabulary rather than free-form input: these become a date_trunc
#: argument, and an enumerated set is both safe and self-documenting for track C.
ARALIKLAR: dict[str, str] = {
    "10s": "10 seconds",
    "1m": "1 minute",
    "5m": "5 minutes",
    "15m": "15 minutes",
    "1h": "1 hour",
    "1d": "1 day",
}


# --------------------------------------------------------------------------
# Application
# --------------------------------------------------------------------------


def olustur(ayar: Ayar | None = None) -> FastAPI:
    """Build the app. A factory rather than a module-level singleton so tests
    can run it against their own database without touching the environment."""
    ayar = ayar or Ayar.ortamdan()

    @asynccontextmanager
    async def omur(uygulama: FastAPI):
        havuz = ConnectionPool(
            ayar.veritabani.dsn,
            min_size=ayar.api.havuz_asgari,
            max_size=ayar.api.havuz_azami,
            kwargs={"row_factory": dict_row, "autocommit": True},
            configure=lambda b: b.execute(f"SET search_path TO {ayar.veritabani.sema}, public"),
            open=False,
        )
        havuz.open()
        uygulama.state.havuz = havuz
        uygulama.state.ayar = ayar
        try:
            yield
        finally:
            havuz.close()

    uygulama = FastAPI(
        title="Grid Up — İZ B okuma API'si",
        version="1.0.0",
        description=(
            "Sözleşme ⑤. Anomali kayıtlarını, ölçüm serilerini ve termal kareleri "
            "okumak için. Yazma yalnızca operatör onayı ile."
        ),
        lifespan=omur,
    )

    if ayar.api.cors_kaynaklari:
        uygulama.add_middleware(
            CORSMiddleware,
            allow_origins=list(ayar.api.cors_kaynaklari),
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )

    @uygulama.exception_handler(HTTPException)
    async def _hata_bicimi(istek: Request, hata: HTTPException):
        """One error shape for every failure, so track C writes one handler."""
        govde = (
            hata.detail
            if isinstance(hata.detail, dict)
            else {"kod": "hata", "mesaj": str(hata.detail)}
        )
        return JSONResponse(status_code=hata.status_code, content={"hata": govde})

    def havuzdan():
        with uygulama.state.havuz.connection() as baglanti:
            yield baglanti

    _uclari_bagla(uygulama, ayar, havuzdan)
    return uygulama


def _uclari_bagla(uygulama: FastAPI, ayar: Ayar, havuzdan) -> None:
    api = ayar.api

    # ----------------------------------------------------------------------
    # GET /saglik
    # ----------------------------------------------------------------------

    @uygulama.get("/saglik", tags=["sistem"], summary="Servis durumu")
    def saglik():
        """Service health.

        Reports the database, the schema version and how far behind the scan
        loop is. `imlec_gecikme_sn` is the number that matters operationally: it
        is how stale the anomaly table is, and section 8 names a detector
        falling behind its scan period as the real scaling limit. A dashboard
        showing green while the detector is an hour behind is lying.

        `veri_gecikmesi` is the DATA-DELAY metric of the integration-phase
        clock-drift rule: over rows that arrived in the last
        `veri_gecikme_pencere_sn`, how late (arrival − measurement) they were.
        Late data is not an anomaly — a module that lost its uplink and then
        sent the backlog has a correct clock — so it is reported here, per
        module, instead of as `modul_saglik` episodes.
        """
        pencere_sn = api.veri_gecikme_pencere_sn
        esik_sn = ayar.katman0.saat_kaymasi_sn
        try:
            with uygulama.state.havuz.connection() as baglanti:
                with baglanti.cursor() as imlec:
                    imlec.execute("SELECT coalesce(max(surum), 0) AS s FROM gridup.sema_surum")
                    surum = int(imlec.fetchone()["s"])
                    imlec.execute(
                        "SELECT ad, son_islenen, tur_sayisi FROM gridup.tarama_imleci "
                        "ORDER BY ad"
                    )
                    imlecler = imlec.fetchall()
                    imlec.execute(
                        "SELECT count(*) AS n FROM gridup.anomali WHERE durum <> 'kapandi'"
                    )
                    acik = int(imlec.fetchone()["n"])
                    imlec.execute(
                        """
                        WITH son AS (
                            SELECT modul_id,
                                   extract(epoch FROM (alindi_zaman - zaman)) AS gecikme
                            FROM gridup.olcum
                            WHERE alindi_zaman > now() - make_interval(secs => %(p)s)
                        )
                        SELECT count(*) AS satir,
                               coalesce(max(gecikme), 0) AS azami,
                               coalesce(percentile_cont(0.5) WITHIN GROUP (ORDER BY gecikme), 0)
                                   AS p50,
                               coalesce(percentile_cont(0.95) WITHIN GROUP (ORDER BY gecikme), 0)
                                   AS p95,
                               count(*) FILTER (WHERE gecikme > %(e)s) AS geciken
                        FROM son
                        """,
                        {"p": pencere_sn, "e": esik_sn},
                    )
                    gecikme = imlec.fetchone()
                    imlec.execute(
                        """
                        SELECT modul_id,
                               max(extract(epoch FROM (alindi_zaman - zaman))) AS azami,
                               count(*) AS satir
                        FROM gridup.olcum
                        WHERE alindi_zaman > now() - make_interval(secs => %(p)s)
                        GROUP BY modul_id
                        HAVING max(extract(epoch FROM (alindi_zaman - zaman))) > %(e)s
                        ORDER BY azami DESC
                        LIMIT 50
                        """,
                        {"p": pencere_sn, "e": esik_sn},
                    )
                    geciken_moduller = imlec.fetchall()
        except Exception as hata:  # noqa: BLE001 - health must report, not raise
            _gunluk.exception("health check failed")
            raise ApiHatasi(
                503, "veritabani_erisilemez", f"Veritabanına erişilemiyor: {hata}"
            ) from hata

        simdi = datetime.now(timezone.utc)
        return {
            "durum": "calisiyor",
            "sema_surumu": surum,
            "acik_anomali": acik,
            "imlecler": [
                {
                    "ad": i["ad"],
                    "son_islenen": zaman_yaz(i["son_islenen"]),
                    "tur_sayisi": i["tur_sayisi"],
                    "gecikme_sn": round((simdi - i["son_islenen"]).total_seconds(), 1),
                }
                for i in imlecler
            ],
            "veri_gecikmesi": {
                "pencere_sn": pencere_sn,
                "esik_sn": esik_sn,
                "satir": int(gecikme["satir"]),
                "azami_sn": round(float(gecikme["azami"]), 1),
                "p50_sn": round(float(gecikme["p50"]), 1),
                "p95_sn": round(float(gecikme["p95"]), 1),
                "geciken_satir": int(gecikme["geciken"]),
                "geciken_moduller": [
                    {
                        "modul_id": m["modul_id"],
                        "azami_sn": round(float(m["azami"]), 1),
                        "satir": int(m["satir"]),
                    }
                    for m in geciken_moduller
                ],
            },
            "zaman": zaman_yaz(simdi),
        }

    # ----------------------------------------------------------------------
    # GET /sahalar
    # ----------------------------------------------------------------------

    @uygulama.get("/sahalar", tags=["hiyerarsi"], summary="Saha → pano → modül ağacı")
    def sahalar(baglanti=Depends(havuzdan)):
        """The site tree, with each module's worst open severity folded in.

        Built in one query rather than one per level: the tree is the dashboard's
        opening screen, and N+1 queries against a hundred modules is the kind of
        slowness that gets blamed on the database.
        """
        with baglanti.cursor() as imlec:
            imlec.execute(
                """
                SELECT s.saha_kodu, s.ad AS saha_adi, s.il, s.ilce, s.enlem, s.boylam,
                       p.pano_kodu, p.ad AS pano_adi, p.pano_tipi,
                       m.modul_id, m.aktif, m.son_gorulme,
                       a.seviye AS anomali_seviyesi
                FROM gridup.saha s
                LEFT JOIN gridup.pano p ON p.saha_kodu = s.saha_kodu
                LEFT JOIN gridup.modul m
                       ON m.saha_kodu = p.saha_kodu AND m.pano_kodu = p.pano_kodu
                LEFT JOIN LATERAL (
                    SELECT seviye FROM gridup.anomali x
                    WHERE x.modul_id = m.modul_id AND x.durum <> 'kapandi'
                    ORDER BY CASE seviye WHEN 'kritik' THEN 3 WHEN 'uyari' THEN 2
                                         WHEN 'izle' THEN 1 ELSE 0 END DESC
                    LIMIT 1
                ) a ON TRUE
                ORDER BY s.saha_kodu, p.pano_kodu, m.modul_id
                """
            )
            satirlar = imlec.fetchall()

        agac: dict[str, dict] = {}
        for r in satirlar:
            saha = agac.setdefault(
                r["saha_kodu"],
                {
                    "saha_kodu": r["saha_kodu"],
                    "ad": r["saha_adi"],
                    "il": r["il"],
                    "ilce": r["ilce"],
                    "enlem": r["enlem"],
                    "boylam": r["boylam"],
                    "panolar": {},
                },
            )
            if r["pano_kodu"] is None:
                continue
            pano = saha["panolar"].setdefault(
                r["pano_kodu"],
                {
                    "pano_kodu": r["pano_kodu"],
                    "ad": r["pano_adi"],
                    "pano_tipi": r["pano_tipi"],
                    "moduller": [],
                },
            )
            if r["modul_id"] is None:
                continue
            pano["moduller"].append(
                {
                    "modul_id": r["modul_id"],
                    "aktif": r["aktif"],
                    "son_gorulme": zaman_yaz(r["son_gorulme"]),
                    "seviye": r["anomali_seviyesi"] or Seviye.NORMAL.value,
                }
            )

        return {
            "sahalar": [
                {**s, "panolar": list(s["panolar"].values())} for s in agac.values()
            ]
        }

    # ----------------------------------------------------------------------
    # GET /moduller
    # ----------------------------------------------------------------------

    @uygulama.get("/moduller", tags=["modul"], summary="Modül listesi")
    def moduller(
        baglanti=Depends(havuzdan),
        saha: str | None = Query(None, description="saha_kodu ile filtrele"),
        pano: str | None = Query(None, description="pano_kodu ile filtrele"),
        seviye: Seviye | None = Query(None, description="en az bu seviyede açık anomalisi olanlar"),
        limit: int = Query(None, ge=1),
        ofset: int = Query(0, ge=0),
    ):
        """List modules with last-seen, module state and worst open severity.

        `durum` here is the MODULE's state and its vocabulary is
        `aktif | sessiz | pasif` — deliberately not the anomaly lifecycle's
        `acik | onaylandi | kapandi`, which is a different field on a different
        object. The contract lists the column as `durum`; this note is in the
        README too, because the collision is the single easiest thing to get
        wrong when consuming this endpoint.
        """
        boyut = min(limit or api.sayfa_boyutu, api.azami_sayfa_boyutu)
        sessizlik = ayar.katman0.sessizlik_sn

        kosullar = ["TRUE"]
        parametreler: list[Any] = [sessizlik]
        if saha:
            kosullar.append("m.saha_kodu = %s")
            parametreler.append(saha)
        if pano:
            kosullar.append("m.pano_kodu = %s")
            parametreler.append(pano)
        if seviye:
            kosullar.append(
                "CASE coalesce(a.seviye, 'normal') WHEN 'kritik' THEN 3 WHEN 'uyari' THEN 2 "
                "WHEN 'izle' THEN 1 ELSE 0 END >= "
                "CASE %s WHEN 'kritik' THEN 3 WHEN 'uyari' THEN 2 WHEN 'izle' THEN 1 ELSE 0 END"
            )
            parametreler.append(seviye.value)

        with baglanti.cursor() as imlec:
            imlec.execute(
                f"""
                SELECT m.modul_id, m.saha_kodu, m.pano_kodu, m.aktif, m.son_gorulme,
                       m.yazilim_surumu,
                       greatest(o.son_olcum, m.son_gorulme) AS goruldu,
                       coalesce(a.seviye, 'normal') AS seviye,
                       a.acik_sayisi,
                       CASE
                           WHEN NOT m.aktif THEN 'pasif'
                           WHEN greatest(o.son_olcum, m.son_gorulme) IS NULL THEN 'sessiz'
                           WHEN greatest(o.son_olcum, m.son_gorulme)
                                < now() - make_interval(secs => %s) THEN 'sessiz'
                           ELSE 'aktif'
                       END AS durum,
                       count(*) OVER () AS toplam
                FROM gridup.modul m
                LEFT JOIN LATERAL (
                    SELECT max(zaman) AS son_olcum FROM gridup.olcum x
                    WHERE x.modul_id = m.modul_id
                ) o ON TRUE
                LEFT JOIN LATERAL (
                    SELECT seviye, count(*) OVER () AS acik_sayisi
                    FROM gridup.anomali x
                    WHERE x.modul_id = m.modul_id AND x.durum <> 'kapandi'
                    ORDER BY CASE seviye WHEN 'kritik' THEN 3 WHEN 'uyari' THEN 2
                                         WHEN 'izle' THEN 1 ELSE 0 END DESC
                    LIMIT 1
                ) a ON TRUE
                WHERE {' AND '.join(kosullar)}
                ORDER BY m.modul_id
                LIMIT %s OFFSET %s
                """,
                (*parametreler, boyut, ofset),
            )
            satirlar = imlec.fetchall()

        toplam = int(satirlar[0]["toplam"]) if satirlar else 0
        return {
            "veriler": [
                {
                    "modul_id": r["modul_id"],
                    "saha_kodu": r["saha_kodu"],
                    "pano_kodu": r["pano_kodu"],
                    "son_gorulme": zaman_yaz(r["goruldu"]),
                    "durum": r["durum"],
                    "seviye": r["seviye"],
                    "acik_anomali": int(r["acik_sayisi"] or 0),
                    "yazilim_surumu": r["yazilim_surumu"],
                }
                for r in satirlar
            ],
            "toplam": toplam,
            "ofset": ofset,
            "limit": boyut,
        }

    # ----------------------------------------------------------------------
    # GET /moduller/{id}
    # ----------------------------------------------------------------------

    @uygulama.get("/moduller/{modul_id}", tags=["modul"], summary="Modül detayı")
    def modul(modul_id: str, baglanti=Depends(havuzdan)):
        """Module detail with the latest value of every measurement type.

        `DISTINCT ON` rather than a max/join: the primary key is
        (modul_id, olcum_tipi, zaman), so this walks the index backwards once per
        channel instead of scanning the module's history.

        `besleme` and `sinyal` are the newest `modul_durum` row's values
        (integration decision); both `null` for a module that has never sent a
        status packet. `durum_zaman` says when they were reported.
        """
        with baglanti.cursor() as imlec:
            imlec.execute(
                "SELECT modul_id, saha_kodu, pano_kodu, modul_kodu, aktif, "
                "kurulum_zaman, yazilim_surumu, son_gorulme, konum_notu "
                "FROM gridup.modul WHERE modul_id = %s",
                (modul_id,),
            )
            satir = imlec.fetchone()
            if satir is None:
                raise _bulunamadi("Modül", modul_id)

            imlec.execute(
                """
                SELECT DISTINCT ON (olcum_tipi)
                       olcum_tipi, zaman, deger, birim, kalite
                FROM gridup.olcum
                WHERE modul_id = %s
                ORDER BY olcum_tipi, zaman DESC
                """,
                (modul_id,),
            )
            son_olcumler = imlec.fetchall()

            imlec.execute(
                "SELECT id, tip, seviye, skor, durum, ilk_gorulme, son_gorulme, gerekce "
                "FROM gridup.anomali WHERE modul_id = %s AND durum <> 'kapandi' "
                "ORDER BY sira",
                (modul_id,),
            )
            anomaliler = imlec.fetchall()

            imlec.execute(
                "SELECT zaman, besleme, sinyal, yazilim_surumu FROM gridup.modul_durum "
                "WHERE modul_id = %s ORDER BY zaman DESC LIMIT 1",
                (modul_id,),
            )
            durum = imlec.fetchone()

        return {
            "modul_id": satir["modul_id"],
            "saha_kodu": satir["saha_kodu"],
            "pano_kodu": satir["pano_kodu"],
            "modul_kodu": satir["modul_kodu"],
            "aktif": satir["aktif"],
            "kurulum_zaman": zaman_yaz(satir["kurulum_zaman"]),
            "yazilim_surumu": (
                durum["yazilim_surumu"] if durum and durum["yazilim_surumu"]
                else satir["yazilim_surumu"]
            ),
            "son_gorulme": zaman_yaz(satir["son_gorulme"]),
            "konum_notu": satir["konum_notu"],
            "besleme": durum["besleme"] if durum else None,
            "sinyal": int(durum["sinyal"]) if durum else None,
            "durum_zaman": zaman_yaz(durum["zaman"]) if durum else None,
            "son_olcumler": [
                {
                    "olcum_tipi": o["olcum_tipi"],
                    "zaman": zaman_yaz(o["zaman"]),
                    "deger": o["deger"],
                    "birim": o["birim"],
                    "kalite": o["kalite"],
                }
                for o in son_olcumler
            ],
            "acik_anomaliler": [
                {
                    "id": a["id"],
                    "tip": a["tip"],
                    "seviye": a["seviye"],
                    "skor": a["skor"],
                    "durum": a["durum"],
                    "ilk_gorulme": zaman_yaz(a["ilk_gorulme"]),
                    "son_gorulme": zaman_yaz(a["son_gorulme"]),
                    "gerekce": a["gerekce"],
                }
                for a in anomaliler
            ],
        }

    # ----------------------------------------------------------------------
    # GET /moduller/{id}/seri
    # ----------------------------------------------------------------------

    @uygulama.get("/moduller/{modul_id}/seri", tags=["modul"], summary="Zaman serisi")
    def seri(
        modul_id: str,
        baglanti=Depends(havuzdan),
        tip: OlcumTipi = Query(..., description="olcum_tipi"),
        bas: str | None = Query(None, description="ISO 8601, dahil"),
        bit: str | None = Query(None, description="ISO 8601, dahil"),
        aralik: str | None = Query(
            None, description=f"kova boyutu: {', '.join(ARALIKLAR)}"
        ),
    ):
        """A measurement series, optionally bucketed.

        With `aralik` the response carries `ort`/`asgari`/`azami` per bucket
        rather than raw points. Min and max are returned alongside the mean
        because a mean alone hides exactly the spikes an operator is looking for
        — the bucket that averaged 46 °C may have touched 130.

        Without `aralik`, raw rows up to `azami_seri_noktasi`. Past that the
        request is REFUSED rather than truncated: a chart silently missing its
        last three days looks fine and is wrong, and the caller cannot tell.
        """
        bas_an = _zaman_oku(bas, "bas")
        bit_an = _zaman_oku(bit, "bit")
        if bas_an and bit_an and bit_an < bas_an:
            raise ApiHatasi(400, "gecersiz_aralik", "bit, bas'tan önce olamaz")
        if aralik is not None and aralik not in ARALIKLAR:
            raise ApiHatasi(
                400,
                "gecersiz_aralik_adi",
                f"aralik şunlardan biri olmalı: {', '.join(ARALIKLAR)}",
                kabul_edilenler=list(ARALIKLAR),
            )

        with baglanti.cursor() as imlec:
            imlec.execute("SELECT 1 FROM gridup.modul WHERE modul_id = %s", (modul_id,))
            if imlec.fetchone() is None:
                raise _bulunamadi("Modül", modul_id)

            kosul = ["modul_id = %s", "olcum_tipi = %s"]
            parametreler: list[Any] = [modul_id, tip.value]
            if bas_an:
                kosul.append("zaman >= %s")
                parametreler.append(bas_an)
            if bit_an:
                kosul.append("zaman <= %s")
                parametreler.append(bit_an)
            nerede = " AND ".join(kosul)

            if aralik:
                imlec.execute(
                    f"""
                    SELECT date_bin(%s::interval, zaman, TIMESTAMPTZ 'epoch') AS kova,
                           avg(deger) AS ort, min(deger) AS asgari, max(deger) AS azami,
                           count(*) AS sayi,
                           count(*) FILTER (WHERE kalite <> 'iyi') AS supheli
                    FROM gridup.olcum
                    WHERE {nerede}
                    GROUP BY kova
                    ORDER BY kova
                    LIMIT %s
                    """,
                    (ARALIKLAR[aralik], *parametreler, api.azami_seri_noktasi + 1),
                )
                satirlar = imlec.fetchall()
                if len(satirlar) > api.azami_seri_noktasi:
                    raise _cok_nokta(api, aralik)
                return {
                    "modul_id": modul_id,
                    "olcum_tipi": tip.value,
                    "aralik": aralik,
                    "noktalar": [
                        {
                            "zaman": zaman_yaz(r["kova"]),
                            "ort": float(r["ort"]) if r["ort"] is not None else None,
                            "asgari": r["asgari"],
                            "azami": r["azami"],
                            "sayi": int(r["sayi"]),
                            "supheli": int(r["supheli"]),
                        }
                        for r in satirlar
                    ],
                }

            imlec.execute(
                f"""
                SELECT zaman, deger, birim, kalite FROM gridup.olcum
                WHERE {nerede} ORDER BY zaman LIMIT %s
                """,
                (*parametreler, api.azami_seri_noktasi + 1),
            )
            satirlar = imlec.fetchall()
            if len(satirlar) > api.azami_seri_noktasi:
                raise _cok_nokta(api, None)

        return {
            "modul_id": modul_id,
            "olcum_tipi": tip.value,
            "aralik": None,
            "noktalar": [
                {
                    "zaman": zaman_yaz(r["zaman"]),
                    "deger": r["deger"],
                    "birim": r["birim"],
                    "kalite": r["kalite"],
                }
                for r in satirlar
            ],
        }

    # ----------------------------------------------------------------------
    # GET /moduller/{id}/termal/son
    # ----------------------------------------------------------------------

    @uygulama.get(
        "/moduller/{modul_id}/termal/son", tags=["termal"], summary="Son termal özet"
    )
    def termal_son(modul_id: str, baglanti=Depends(havuzdan)):
        """The newest thermal summary, with the id of the frame at the same instant.

        Since the integration phase a full frame arrives at every measurement
        instant (30 s period, same as the summary), so `kare_id` is normally
        present; `null` means the frame for that instant has not been stored.
        """
        with baglanti.cursor() as imlec:
            imlec.execute("SELECT 1 FROM gridup.modul WHERE modul_id = %s", (modul_id,))
            if imlec.fetchone() is None:
                raise _bulunamadi("Modül", modul_id)

            imlec.execute(
                "SELECT zaman, maks, maks_sutun, maks_satir, bolge_ort, alindi_zaman "
                "FROM gridup.termal_ozet WHERE modul_id = %s ORDER BY zaman DESC LIMIT 1",
                (modul_id,),
            )
            ozet = imlec.fetchone()
            if ozet is None:
                raise _bulunamadi("Termal özet", modul_id)

            imlec.execute(
                "SELECT kare_id FROM gridup.termal_kare WHERE modul_id = %s AND zaman = %s",
                (modul_id, ozet["zaman"]),
            )
            kare = imlec.fetchone()

        return {
            "modul_id": modul_id,
            "zaman": zaman_yaz(ozet["zaman"]),
            "maks": ozet["maks"],
            # [sutun, satir] — x first, as everywhere else in the contract.
            "maks_konum": [ozet["maks_sutun"], ozet["maks_satir"]],
            "bolge_ort": list(ozet["bolge_ort"]),
            "kare_id": kare["kare_id"] if kare else None,
            "alindi_zaman": zaman_yaz(ozet["alindi_zaman"]),
        }

    # ----------------------------------------------------------------------
    # GET /termal/kare/{kare_id}
    # ----------------------------------------------------------------------

    @uygulama.get("/termal/kare/{kare_id}", tags=["termal"], summary="Tam termal kare")
    def termal_kare(kare_id: str, baglanti=Depends(havuzdan)):
        """The full 768-value frame, in °C.

        Stored as `bytea` (int16 LE, 0.1 °C, 1536 bytes — integration decision)
        and decoded here, so the consumer's format is unchanged: an array of
        768 numbers. Row-major: the index of pixel (sutun, satir) is
        `satir * 32 + sutun`. Geometry is returned alongside the data rather
        than assumed, so a future sensor with a different resolution is a data
        change and not a silent reinterpretation of the array.
        """
        with baglanti.cursor() as imlec:
            imlec.execute(
                "SELECT kare_id, modul_id, zaman, piksel_verisi, satir_sayisi, "
                "sutun_sayisi, alindi_zaman FROM gridup.termal_kare WHERE kare_id = %s",
                (kare_id,),
            )
            satir = imlec.fetchone()
            if satir is None:
                raise _bulunamadi("Termal kare", kare_id)

        try:
            pikseller = kare_coz(satir["piksel_verisi"])
        except KareHatasi as hata:
            # The database CHECK makes this unreachable for rows track A wrote;
            # a 500 with a stable code beats a stack trace if it ever is not.
            raise ApiHatasi(
                500, "kare_cozulemedi", f"Termal kare çözülemedi: {hata}", kimlik=kare_id
            ) from hata

        return {
            "kare_id": satir["kare_id"],
            "modul_id": satir["modul_id"],
            "zaman": zaman_yaz(satir["zaman"]),
            "satir_sayisi": satir["satir_sayisi"],
            "sutun_sayisi": satir["sutun_sayisi"],
            "duzen": "satir_oncelikli",
            "birim": "C",
            "piksel_verisi": pikseller,
            "alindi_zaman": zaman_yaz(satir["alindi_zaman"]),
        }

    # ----------------------------------------------------------------------
    # GET /anomaliler
    # ----------------------------------------------------------------------

    @uygulama.get("/anomaliler", tags=["anomali"], summary="Anomali listesi")
    def anomaliler(
        baglanti=Depends(havuzdan),
        modul: str | None = Query(None, description="modul_id"),
        seviye: Seviye | None = Query(None, description="en az bu seviye"),
        bas: str | None = Query(None, description="son_gorulme >= bas"),
        bit: str | None = Query(None, description="ilk_gorulme <= bit"),
        durum: Durum | None = Query(None),
        tip: Tip | None = Query(None),
        sonra: int | None = Query(
            None, description="bu sira'dan sonrasını getir — alarm servisi için"
        ),
        limit: int = Query(None, ge=1),
    ):
        """The anomaly list, filtered and paginated.

        PAGINATION IS KEYSET, on `sira`, not offset. Section 7.2 puts a monotonic
        sequence on this table precisely so the alarm service can ask for
        "everything after the last one I handled" and be certain it missed
        nothing. Offset paging cannot promise that: an episode opening between
        two requests shifts every later row by one and the caller silently skips
        an alarm. `sonraki` in the response is the cursor for the next page, or
        null at the end.

        `seviye` filters at or above the given level, since "show me anything at
        least as bad as uyari" is the question an operator actually asks.
        """
        boyut = min(limit or api.sayfa_boyutu, api.azami_sayfa_boyutu)
        bas_an = _zaman_oku(bas, "bas")
        bit_an = _zaman_oku(bit, "bit")

        kosul = ["TRUE"]
        parametreler: list[Any] = []
        if modul:
            kosul.append("modul_id = %s")
            parametreler.append(modul)
        if durum:
            kosul.append("durum = %s")
            parametreler.append(durum.value)
        if tip:
            kosul.append("tip = %s")
            parametreler.append(tip.value)
        if seviye:
            kosul.append(
                "CASE seviye WHEN 'kritik' THEN 3 WHEN 'uyari' THEN 2 WHEN 'izle' THEN 1 "
                "ELSE 0 END >= CASE %s WHEN 'kritik' THEN 3 WHEN 'uyari' THEN 2 "
                "WHEN 'izle' THEN 1 ELSE 0 END"
            )
            parametreler.append(seviye.value)
        if bas_an:
            # Overlap semantics: an episode that is still running counts as being
            # in the window, which is what "what was happening on Tuesday" means.
            kosul.append("son_gorulme >= %s")
            parametreler.append(bas_an)
        if bit_an:
            kosul.append("ilk_gorulme <= %s")
            parametreler.append(bit_an)
        if sonra is not None:
            kosul.append("sira > %s")
            parametreler.append(sonra)

        with baglanti.cursor() as imlec:
            imlec.execute(
                f"""
                SELECT sira, id, modul_id, tip, seviye, maks_seviye, skor,
                       ilk_gorulme, son_gorulme, durum, gerekce, kanit, katman,
                       kapanma_zaman
                FROM gridup.anomali
                WHERE {' AND '.join(kosul)}
                ORDER BY sira
                LIMIT %s
                """,
                (*parametreler, boyut + 1),
            )
            satirlar = imlec.fetchall()

        devam = len(satirlar) > boyut
        satirlar = satirlar[:boyut]
        return {
            "veriler": [_anomali_govdesi(r) for r in satirlar],
            "sonraki": int(satirlar[-1]["sira"]) if devam and satirlar else None,
            "limit": boyut,
        }

    # ----------------------------------------------------------------------
    # GET /anomaliler/{id}
    # ----------------------------------------------------------------------

    @uygulama.get("/anomaliler/{anomali_id}", tags=["anomali"], summary="Anomali detayı")
    def anomali(anomali_id: str, baglanti=Depends(havuzdan)):
        """One episode: justification, evidence, frame reference."""
        with baglanti.cursor() as imlec:
            imlec.execute(
                "SELECT sira, id, modul_id, tip, seviye, maks_seviye, skor, "
                "ilk_gorulme, son_gorulme, durum, gerekce, kanit, katman, kapanma_zaman "
                "FROM gridup.anomali WHERE id = %s",
                (anomali_id,),
            )
            satir = imlec.fetchone()
            if satir is None:
                raise _bulunamadi("Anomali", anomali_id)
        return _anomali_govdesi(satir)

    # ----------------------------------------------------------------------
    # GET /anomaliler/{id}/gecisler   — section 7.3's addition
    # ----------------------------------------------------------------------

    @uygulama.get(
        "/anomaliler/{anomali_id}/gecisler",
        tags=["anomali"],
        summary="Olayın durum geçişleri (journal)",
    )
    def gecisler(anomali_id: str, baglanti=Depends(havuzdan)):
        """The episode's journal: every state and severity transition, in order.

        Section 6.4's audit trail — "when did this alarm arrive, who saw it, when
        did it clear" is a regulatory question in electricity distribution, so
        `aktor` carries who and `zaman` carries when for each transition, and the
        list is append-only.
        """
        with baglanti.cursor() as imlec:
            imlec.execute("SELECT 1 FROM gridup.anomali WHERE id = %s", (anomali_id,))
            if imlec.fetchone() is None:
                raise _bulunamadi("Anomali", anomali_id)
            imlec.execute(
                "SELECT id, zaman, alan, onceki, yeni, aktor, aciklama "
                "FROM gridup.anomali_gecis WHERE anomali_id = %s ORDER BY id",
                (anomali_id,),
            )
            satirlar = imlec.fetchall()

        return {
            "anomali_id": anomali_id,
            "gecisler": [
                {
                    "sira": int(r["id"]),
                    "zaman": zaman_yaz(r["zaman"]),
                    "alan": r["alan"],
                    "onceki": r["onceki"],
                    "yeni": r["yeni"],
                    "aktor": r["aktor"],
                    "aciklama": r["aciklama"],
                }
                for r in satirlar
            ],
        }

    # ----------------------------------------------------------------------
    # GET /gecisler   — the global transition feed (integration phase, ⑤)
    # ----------------------------------------------------------------------

    @uygulama.get("/gecisler", tags=["anomali"], summary="Tüm geçişler (küresel akış)")
    def gecis_akisi(
        baglanti=Depends(havuzdan),
        sonra: int | None = Query(None, description="bu id'den sonrasını getir"),
        limit: int = Query(None, ge=1),
    ):
        """Every `durum` and `seviye` transition across all episodes, in order.

        The alarm service's feed. Keyset on the journal's own id, as
        `/anomaliler` is on `sira`: the caller passes the last id it handled as
        `sonra` and can be certain nothing between two polls was skipped. Each
        row names its episode, so a consumer never has to join.

        `sonraki` is the id of the last row returned, or null when the page is
        empty — a resume cursor rather than `/anomaliler`'s "null on the last
        page", because a feed has no last page: the next poll resumes from it.
        """
        boyut = min(limit or api.sayfa_boyutu, api.azami_sayfa_boyutu)
        kosul = ["alan IN ('durum', 'seviye')"]
        parametreler: list[Any] = []
        if sonra is not None:
            kosul.append("id > %s")
            parametreler.append(sonra)

        with baglanti.cursor() as imlec:
            imlec.execute(
                f"""
                SELECT id, anomali_id, zaman, alan, onceki, yeni, aktor
                FROM gridup.anomali_gecis
                WHERE {' AND '.join(kosul)}
                ORDER BY id
                LIMIT %s
                """,
                (*parametreler, boyut),
            )
            satirlar = imlec.fetchall()

        return {
            "veriler": [
                {
                    "id": int(r["id"]),
                    "anomali_id": r["anomali_id"],
                    "zaman": zaman_yaz(r["zaman"]),
                    "alan": r["alan"],
                    "onceki": r["onceki"],
                    "yeni": r["yeni"],
                    "aktor": r["aktor"],
                }
                for r in satirlar
            ],
            "sonraki": int(satirlar[-1]["id"]) if satirlar else None,
            "limit": boyut,
        }

    # ----------------------------------------------------------------------
    # POST /anomaliler/{id}/onayla
    # ----------------------------------------------------------------------

    @uygulama.post(
        "/anomaliler/{anomali_id}/onayla", tags=["anomali"], summary="Operatör onayı"
    )
    def onayla(
        anomali_id: str,
        baglanti=Depends(havuzdan),
        aktor: str = Query(..., min_length=1, description="operatör kimliği"),
    ):
        """Acknowledge an episode.

        The API's only write, and it does not issue its own UPDATE: it calls
        `OlayDeposu.onayla`, so the episode tables keep exactly one writer and the
        acknowledgement lands in the journal with who and when. A second place
        that mutated episode state would eventually disagree with the first.

        `aktor` is required and has no default. An audit trail whose actor can be
        omitted answers "who saw it" with a shrug.
        """
        ayar_ = uygulama.state.ayar
        with baglanti.cursor() as imlec:
            imlec.execute("SELECT durum FROM gridup.anomali WHERE id = %s", (anomali_id,))
            satir = imlec.fetchone()
        if satir is None:
            raise _bulunamadi("Anomali", anomali_id)

        # The pool runs autocommit; OlayDeposu opens its own transactions.
        onceki = baglanti.autocommit
        baglanti.set_autocommit(False)
        try:
            depo = OlayDeposu(baglanti, ayar_)
            oldu = depo.onayla(anomali_id, aktor, datetime.now(timezone.utc))
            baglanti.commit()
        finally:
            baglanti.set_autocommit(onceki)

        if not oldu:
            raise ApiHatasi(
                409,
                "onaylanamaz",
                f"Anomali '{anomali_id}' 'acik' durumunda değil; şu an "
                f"'{satir['durum']}'. Yalnızca açık bir olay onaylanabilir.",
                kimlik=anomali_id,
                durum=satir["durum"],
            )

        with baglanti.cursor() as imlec:
            imlec.execute(
                "SELECT sira, id, modul_id, tip, seviye, maks_seviye, skor, "
                "ilk_gorulme, son_gorulme, durum, gerekce, kanit, katman, kapanma_zaman "
                "FROM gridup.anomali WHERE id = %s",
                (anomali_id,),
            )
            return _anomali_govdesi(imlec.fetchone())


def _cok_nokta(api, aralik: str | None) -> ApiHatasi:
    oneri = (
        "Daha dar bir bas/bit aralığı verin veya `aralik` parametresiyle kova boyutu seçin."
        if aralik is None
        else "Daha dar bir bas/bit aralığı verin veya daha büyük bir `aralik` seçin."
    )
    return ApiHatasi(
        400,
        "cok_fazla_nokta",
        f"Sonuç {api.azami_seri_noktasi} noktayı aşıyor. {oneri}",
        azami=api.azami_seri_noktasi,
        kabul_edilen_araliklar=list(ARALIKLAR),
    )


def _anomali_govdesi(satir: dict) -> dict:
    """Contract ③ — the episode model, exactly the integration decision's fields.

    `id, sira, modul_id, tip, seviye, maks_seviye, skor, ilk_gorulme,
    son_gorulme, durum, gerekce, kanit`. The single-`zaman` shape is invalid
    and the compatibility alias this body used to carry is gone with it. The
    detector-internal `katman` and the closing time travel inside `kanit`
    (`kanit.katman`, `kanit.kapanma_zaman`), where the contract leaves room
    for detector-specific evidence.
    """
    kanit = dict(satir["kanit"] or {})
    kanit["katman"] = satir["katman"]
    kanit["kapanma_zaman"] = zaman_yaz(satir["kapanma_zaman"])
    return {
        "id": satir["id"],
        "sira": int(satir["sira"]),
        "modul_id": satir["modul_id"],
        "tip": satir["tip"],
        "seviye": satir["seviye"],
        "maks_seviye": satir["maks_seviye"],
        "skor": satir["skor"],
        "ilk_gorulme": zaman_yaz(satir["ilk_gorulme"]),
        "son_gorulme": zaman_yaz(satir["son_gorulme"]),
        "durum": satir["durum"],
        "gerekce": satir["gerekce"],
        "kanit": kanit,
    }


def main(argv: "list[str] | None" = None) -> int:
    """Run the API as its own process: `python -m analiz.api`.

    Separate from the scan loop on purpose — decision K1. Two processes against
    one database, neither importing the other's runtime state, so a crash on
    either side cannot take the other down.
    """
    import argparse

    import uvicorn

    ayristirici = argparse.ArgumentParser(prog="analiz.api", description="Sözleşme ⑤ okuma API'si")
    ayristirici.add_argument("--dsn", help="PostgreSQL DSN")
    ayristirici.add_argument("--adres", help="bind address")
    ayristirici.add_argument("--port", type=int, help="bind port")
    ayristirici.add_argument("--ayrinti", action="store_true", help="debug logging")
    args = ayristirici.parse_args(argv)

    ayar = Ayar.ortamdan()
    if args.dsn:
        ayar = ayar.ile(veritabani={"dsn": args.dsn})
    degisiklik: dict[str, Any] = {}
    if args.adres:
        degisiklik["adres"] = args.adres
    if args.port:
        degisiklik["port"] = args.port
    if degisiklik:
        ayar = ayar.ile(api=degisiklik)

    logging.basicConfig(
        level=logging.DEBUG if args.ayrinti else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    uvicorn.run(
        olustur(ayar),
        host=ayar.api.adres,
        port=ayar.api.port,
        log_level="debug" if args.ayrinti else "info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
