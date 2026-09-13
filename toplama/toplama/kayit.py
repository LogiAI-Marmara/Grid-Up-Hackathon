"""Storage backends: where a validated packet actually lands.

The endpoint does not know how rows are stored. That is the point of this file,
and it buys two things the hackathon needs:

* **`postgres`** is the real target — the schema in `../migrations`, on-premise,
  no cloud anywhere in the path.
* **`dosya`** appends the same rows as JSONL. It exists so the collector can be
  started, demonstrated and tested with no database at all: the test suite runs
  against it, and track B can take the files as a fixture. It is a development
  backend, and the docstrings say where it stops being enough.

Both backends receive the *same rows*, produced once by `satirlar()`. A second
row-shaping implementation per backend is how the file output and the database
would drift apart, so there is only one.

One packet is one transaction. Migration 003 explains why: `termal_ozet` is the
source and the `termal_maks` / `termal_ort` rows in `olcum` are its queryable
projection, so a reader must never be able to see one without the other.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .modeller import ModulPaketi, YazimSonucu
from .sozlesme import TERMAL_SATIR, TERMAL_SUTUN, zaman_yaz

#: Backend names accepted in TOPLAMA_KAYIT.
KAYIT_ADLARI = ("postgres", "dosya")

VARSAYILAN_KAYIT = "dosya"
VARSAYILAN_DIZIN = "veri"


# ---------------------------------------------------------------------------
# Row shaping — one implementation, both backends
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Satirlar:
    """One packet expressed as database rows, with the table column names.

    `modul` is the reference-tree upsert. The collector registers modules it has
    not seen before instead of rejecting them: a module is commissioned in the
    field by someone who is not going to run an INSERT first, and the id already
    carries its whole hierarchy (section 11), so there is nothing left to ask.
    """

    modul: dict[str, Any]
    olcum: list[dict[str, Any]]
    termal_ozet: dict[str, Any] | None
    termal_kare: dict[str, Any] | None


def satirlar(paket: ModulPaketi, alindi_zaman: datetime) -> Satirlar:
    """Turn a validated packet into the rows the tables expect.

    `alindi_zaman` is stamped by the collector, never by the module: if the
    network is slow the measurement time must stay the moment it was measured,
    and the gap between the two is what exposes module clock drift (scenario 7).
    """
    kimlik = paket.kimlik

    modul = {
        "modul_id": paket.modul_id,
        "saha_kodu": kimlik.saha,
        "pano_kodu": kimlik.pano,
        "modul_kodu": kimlik.modul,
        "yazilim_surumu": paket.modul_durum.yazilim_surumu,
        "son_gorulme": paket.zaman,
    }

    olcum = [
        {
            "modul_id": kayit.modul_id,
            "olcum_tipi": kayit.olcum_tipi.value,
            "zaman": kayit.zaman,
            "deger": kayit.deger,
            "birim": kayit.birim.value,
            "kalite": kayit.kalite.value,
            "alindi_zaman": alindi_zaman,
        }
        for kayit in paket.olcumler
    ]

    ozet = None
    if paket.termal_ozet is not None:
        ozet = {
            "modul_id": paket.modul_id,
            "zaman": paket.zaman,
            "maks": paket.termal_ozet.maks,
            # [sutun, satir] split into two columns once, here.
            "maks_sutun": paket.termal_ozet.maks_sutun,
            "maks_satir": paket.termal_ozet.maks_satir,
            "bolge_ort": list(paket.termal_ozet.bolge_ort),
            "alindi_zaman": alindi_zaman,
        }

    kare = None
    if paket.termal_kare is not None:
        kare = {
            "modul_id": paket.modul_id,
            "zaman": paket.zaman,
            # 768 values as one array, not 768 measurement rows.
            "piksel_verisi": list(paket.termal_kare),
            "satir_sayisi": TERMAL_SATIR,
            "sutun_sayisi": TERMAL_SUTUN,
            "alindi_zaman": alindi_zaman,
        }

    return Satirlar(modul=modul, olcum=olcum, termal_ozet=ozet, termal_kare=kare)


# ---------------------------------------------------------------------------
# Backend interface
# ---------------------------------------------------------------------------


@dataclass
class Sayac:
    """Rows written since start-up. Reported by `/saglik`, asserted by the tests."""

    paket: int = 0
    olcum: int = 0
    termal_ozet: int = 0
    termal_kare: int = 0
    yinelenen: int = 0

    def sozluk(self) -> dict[str, int]:
        return {
            "paket": self.paket,
            "olcum": self.olcum,
            "termal_ozet": self.termal_ozet,
            "termal_kare": self.termal_kare,
            "yinelenen": self.yinelenen,
        }


class Kayit:
    """A storage backend. Implementations must be safe to call from threads.

    The endpoint is a plain `def`, so FastAPI runs it in a worker thread and
    blocking I/O here is fine — but two requests can land at once, which is why
    both implementations hold a lock around a write.
    """

    ad: str = "?"

    def __init__(self) -> None:
        self.sayac = Sayac()
        self._kilit = threading.Lock()

    def baslat(self) -> None:
        """Open resources / check reachability. Called once on start-up."""

    def yaz(self, paket: ModulPaketi, alindi_zaman: datetime) -> YazimSonucu:  # pragma: no cover - interface
        raise NotImplementedError

    def saglik(self) -> dict[str, Any]:  # pragma: no cover - interface
        raise NotImplementedError

    def kapat(self) -> None:
        """Release resources. Called on shutdown."""

    def _sonuc(
        self,
        paket: ModulPaketi,
        alindi_zaman: datetime,
        olcum: int,
        ozet: int,
        kare: int,
        kare_id: str | None,
        beklenen_olcum: int,
    ) -> YazimSonucu:
        """Update the counters and build the response body."""
        self.sayac.paket += 1
        self.sayac.olcum += olcum
        self.sayac.termal_ozet += ozet
        self.sayac.termal_kare += kare
        yinelenen = olcum == 0 and ozet == 0 and kare == 0 and (beklenen_olcum > 0 or paket.termal_ozet is not None)
        if yinelenen:
            self.sayac.yinelenen += 1
        return YazimSonucu(
            modul_id=paket.modul_id,
            zaman=paket.zaman_metni,
            alindi_zaman=zaman_yaz(alindi_zaman),
            olcum=olcum,
            termal_ozet=ozet,
            termal_kare=kare,
            kare_id=kare_id,
            yinelenen=yinelenen,
        )


# ---------------------------------------------------------------------------
# dosya — JSONL append, no database
# ---------------------------------------------------------------------------


class DosyaKayit(Kayit):
    """Append rows to one JSONL file per table.

    File names match the tables (`olcum.jsonl`, `termal_ozet.jsonl`,
    `termal_kare.jsonl`, `modul.jsonl`) and so do the keys, so a later
    `\\copy`-style import needs no translation and a test can assert on rows
    rather than on log lines.

    Deliberate limits, because this backend is for development and tests:

    * Deduplication is an in-memory set of primary keys, so it is per-process.
      The real dedup guarantee is the table's PK plus `ON CONFLICT DO NOTHING`.
    * "One packet, one transaction" is approximated by holding the lock while all
      four files are appended. An append-mode write of a short line is atomic
      enough for a demo; it is not a transaction, and that is the main reason
      this backend is not the production one.
    """

    ad = "dosya"

    DOSYALAR = {
        "modul": "modul.jsonl",
        "olcum": "olcum.jsonl",
        "termal_ozet": "termal_ozet.jsonl",
        "termal_kare": "termal_kare.jsonl",
    }

    def __init__(self, dizin: str | Path = VARSAYILAN_DIZIN) -> None:
        super().__init__()
        self.dizin = Path(dizin)
        self._gorulen_olcum: set[tuple[str, str, str]] = set()
        self._gorulen_ozet: set[tuple[str, str]] = set()
        self._gorulen_kare: set[tuple[str, str]] = set()
        self._gorulen_modul: dict[str, str] = {}
        self._kare_sira = 0

    # -- helpers ----------------------------------------------------------

    def yol(self, tablo: str) -> Path:
        return self.dizin / self.DOSYALAR[tablo]

    @staticmethod
    def _jsonlanabilir(satir: dict[str, Any]) -> dict[str, Any]:
        """Datetimes become contract timestamps; everything else is already JSON."""
        return {
            anahtar: (zaman_yaz(deger) if isinstance(deger, datetime) else deger)
            for anahtar, deger in satir.items()
        }

    def _ekle(self, tablo: str, satirlar_: list[dict[str, Any]]) -> None:
        if not satirlar_:
            return
        with self.yol(tablo).open("a", encoding="utf-8") as dosya:
            for satir in satirlar_:
                dosya.write(json.dumps(self._jsonlanabilir(satir), ensure_ascii=False, separators=(",", ":")) + "\n")

    def oku(self, tablo: str) -> list[dict[str, Any]]:
        """Read a table back. For tests and for handing a fixture to track B."""
        yol = self.yol(tablo)
        if not yol.exists():
            return []
        return [json.loads(satir) for satir in yol.read_text(encoding="utf-8").splitlines() if satir.strip()]

    # -- interface --------------------------------------------------------

    def baslat(self) -> None:
        self.dizin.mkdir(parents=True, exist_ok=True)

    def yaz(self, paket: ModulPaketi, alindi_zaman: datetime) -> YazimSonucu:
        satir_kumesi = satirlar(paket, alindi_zaman)
        with self._kilit:
            self.dizin.mkdir(parents=True, exist_ok=True)

            # Reference tree: written once per module, and again if its firmware
            # version changed — that is the only field worth re-recording here.
            modul = satir_kumesi.modul
            surum = modul["yazilim_surumu"]
            if self._gorulen_modul.get(modul["modul_id"]) != surum:
                self._gorulen_modul[modul["modul_id"]] = surum
                self._ekle("modul", [modul])

            yeni_olcum = []
            for satir in satir_kumesi.olcum:
                anahtar = (satir["modul_id"], satir["olcum_tipi"], zaman_yaz(satir["zaman"]))
                if anahtar in self._gorulen_olcum:
                    continue
                self._gorulen_olcum.add(anahtar)
                yeni_olcum.append(satir)
            self._ekle("olcum", yeni_olcum)

            ozet_sayisi = 0
            if satir_kumesi.termal_ozet is not None:
                anahtar = (paket.modul_id, paket.zaman_metni)
                if anahtar not in self._gorulen_ozet:
                    self._gorulen_ozet.add(anahtar)
                    self._ekle("termal_ozet", [satir_kumesi.termal_ozet])
                    ozet_sayisi = 1

            kare_sayisi = 0
            kare_id = None
            if satir_kumesi.termal_kare is not None:
                anahtar = (paket.modul_id, paket.zaman_metni)
                if anahtar not in self._gorulen_kare:
                    self._gorulen_kare.add(anahtar)
                    self._kare_sira += 1
                    # Same shape as the table's default, so a frame id looks the
                    # same whichever backend produced it.
                    kare_id = f"kr_{self._kare_sira:06d}"
                    self._ekle("termal_kare", [{"kare_id": kare_id, **satir_kumesi.termal_kare}])
                    kare_sayisi = 1

        return self._sonuc(
            paket,
            alindi_zaman,
            olcum=len(yeni_olcum),
            ozet=ozet_sayisi,
            kare=kare_sayisi,
            kare_id=kare_id,
            beklenen_olcum=len(satir_kumesi.olcum),
        )

    def saglik(self) -> dict[str, Any]:
        return {
            "kayit": self.ad,
            "durum": "hazir" if self.dizin.exists() else "dizin_yok",
            "dizin": str(self.dizin.resolve() if self.dizin.exists() else self.dizin),
            "modul_sayisi": len(self._gorulen_modul),
            "not": "development backend — no transactions, per-process dedup",
        }


# ---------------------------------------------------------------------------
# postgres — the real target
# ---------------------------------------------------------------------------

#: Reference tree upserts. A module is registered on first sight; `son_gorulme`
#: is the denormalised cache migration 001 documents, and GREATEST ignores NULLs
#: in PostgreSQL, so an out-of-order packet cannot move it backwards.
SAHA_SQL = """
INSERT INTO gridup.saha (saha_kodu, ad) VALUES (%s, %s)
ON CONFLICT (saha_kodu) DO NOTHING
"""

PANO_SQL = """
INSERT INTO gridup.pano (saha_kodu, pano_kodu) VALUES (%s, %s)
ON CONFLICT (saha_kodu, pano_kodu) DO NOTHING
"""

MODUL_SQL = """
INSERT INTO gridup.modul (modul_id, saha_kodu, pano_kodu, modul_kodu, yazilim_surumu, son_gorulme)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (modul_id) DO UPDATE SET
    yazilim_surumu = EXCLUDED.yazilim_surumu,
    son_gorulme    = GREATEST(gridup.modul.son_gorulme, EXCLUDED.son_gorulme)
"""

#: DO NOTHING on the primary key is the whole dedup story: a module with a backup
#: store retransmits after an outage, and replaying a packet must be a no-op
#: rather than a duplicate-key error.
OLCUM_SQL = """
INSERT INTO gridup.olcum (modul_id, olcum_tipi, zaman, deger, birim, kalite, alindi_zaman)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (modul_id, olcum_tipi, zaman) DO NOTHING
RETURNING 1
"""

OZET_SQL = """
INSERT INTO gridup.termal_ozet (modul_id, zaman, maks, maks_sutun, maks_satir, bolge_ort, alindi_zaman)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (modul_id, zaman) DO NOTHING
"""

KARE_SQL = """
INSERT INTO gridup.termal_kare (modul_id, zaman, piksel_verisi, satir_sayisi, sutun_sayisi, alindi_zaman)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (modul_id, zaman) DO NOTHING
RETURNING kare_id
"""

KARE_ARA_SQL = "SELECT kare_id FROM gridup.termal_kare WHERE modul_id = %s AND zaman = %s"

SURUM_SQL = "SELECT max(surum) FROM gridup.sema_surum"


class PostgresKayit(Kayit):
    """Writes to the on-premise PostgreSQL schema in `../migrations`.

    One long-lived connection, serialised by the backend lock. At the documented
    load — 100 modules x ~6 types every 10 s, about 60 rows/s — a single
    connection is far from the limit, and one connection makes "one packet, one
    transaction" trivially true. A connection pool is the upgrade path if the
    fleet grows, not something to add before it is needed.

    `psycopg` is imported lazily so that installing the service without a
    database (the `dosya` backend, the test suite) needs no driver at all.
    """

    ad = "postgres"

    def __init__(self, dsn: str) -> None:
        super().__init__()
        if not dsn:
            raise ValueError("postgres backend needs DATABASE_URL")
        self.dsn = dsn
        self._baglanti_nesnesi: Any = None

    # -- connection -------------------------------------------------------

    def _psycopg(self):
        try:
            import psycopg
        except ImportError as hata:  # pragma: no cover - depends on the environment
            raise RuntimeError("the postgres backend needs psycopg: pip install 'psycopg[binary]'") from hata
        return psycopg

    def _baglanti(self):
        psycopg = self._psycopg()
        if self._baglanti_nesnesi is None or self._baglanti_nesnesi.closed:
            self._baglanti_nesnesi = psycopg.connect(self.dsn, autocommit=True)
        return self._baglanti_nesnesi

    def baslat(self) -> None:
        with self._kilit, self._baglanti().cursor() as imlec:
            imlec.execute(SURUM_SQL)
            satir = imlec.fetchone()
        if not satir or satir[0] is None:
            raise RuntimeError("gridup.sema_surum is empty — run the migrations in toplama/migrations first")

    def kapat(self) -> None:
        with self._kilit:
            self._kapat_sessiz()

    def _kapat_sessiz(self) -> None:
        if self._baglanti_nesnesi is not None:
            try:
                self._baglanti_nesnesi.close()
            except Exception:  # pragma: no cover - closing must not raise
                pass
            self._baglanti_nesnesi = None

    # -- interface --------------------------------------------------------

    def yaz(self, paket: ModulPaketi, alindi_zaman: datetime) -> YazimSonucu:
        psycopg = self._psycopg()
        satir_kumesi = satirlar(paket, alindi_zaman)
        with self._kilit:
            for deneme in (1, 2):
                try:
                    return self._yaz(satir_kumesi, paket, alindi_zaman)
                except (psycopg.OperationalError, psycopg.InterfaceError):
                    # A dropped or broken connection (server restart, idle
                    # timeout, transactional state out of sync) is not a bad
                    # packet: reconnect once and retry before failing the
                    # request, because the module would otherwise have to buffer.
                    self._kapat_sessiz()
                    if deneme == 2:
                        raise
        raise AssertionError("unreachable")

    def _yaz(self, satir_kumesi: Satirlar, paket: ModulPaketi, alindi_zaman: datetime) -> YazimSonucu:
        from psycopg.types.json import Jsonb

        baglanti = self._baglanti()
        modul = satir_kumesi.modul
        with baglanti.transaction(), baglanti.cursor() as imlec:
            imlec.execute(SAHA_SQL, (modul["saha_kodu"], modul["saha_kodu"]))
            imlec.execute(PANO_SQL, (modul["saha_kodu"], modul["pano_kodu"]))
            imlec.execute(
                MODUL_SQL,
                (
                    modul["modul_id"],
                    modul["saha_kodu"],
                    modul["pano_kodu"],
                    modul["modul_kodu"],
                    modul["yazilim_surumu"],
                    modul["son_gorulme"],
                ),
            )

            olcum_sayisi = 0
            if satir_kumesi.olcum:
                imlec.executemany(
                    OLCUM_SQL,
                    [
                        (s["modul_id"], s["olcum_tipi"], s["zaman"], s["deger"], s["birim"], s["kalite"], s["alindi_zaman"])
                        for s in satir_kumesi.olcum
                    ],
                )
                # psycopg3's rowcount after executemany reflects only the last
                # statement, so the count of actually-inserted rows comes from the
                # RETURNING rows instead. ON CONFLICT DO NOTHING yields no row for
                # a retransmitted packet, which correctly reports 0 written.
                olcum_sayisi = len(imlec.fetchall())

            ozet_sayisi = 0
            if satir_kumesi.termal_ozet is not None:
                o = satir_kumesi.termal_ozet
                imlec.execute(
                    OZET_SQL,
                    (o["modul_id"], o["zaman"], o["maks"], o["maks_sutun"], o["maks_satir"], o["bolge_ort"], o["alindi_zaman"]),
                )
                ozet_sayisi = max(imlec.rowcount, 0)

            kare_sayisi = 0
            kare_id: str | None = None
            if satir_kumesi.termal_kare is not None:
                k = satir_kumesi.termal_kare
                imlec.execute(
                    KARE_SQL,
                    (
                        k["modul_id"],
                        k["zaman"],
                        Jsonb(k["piksel_verisi"]),
                        k["satir_sayisi"],
                        k["sutun_sayisi"],
                        k["alindi_zaman"],
                    ),
                )
                satir = imlec.fetchone()
                if satir is not None:
                    kare_id, kare_sayisi = satir[0], 1
                else:
                    # Already stored: return the existing id so the caller (and
                    # anomali.kanit.kare_id) still has something to point at.
                    imlec.execute(KARE_ARA_SQL, (k["modul_id"], k["zaman"]))
                    mevcut = imlec.fetchone()
                    kare_id = mevcut[0] if mevcut else None

        return self._sonuc(
            paket,
            alindi_zaman,
            olcum=olcum_sayisi,
            ozet=ozet_sayisi,
            kare=kare_sayisi,
            kare_id=kare_id,
            beklenen_olcum=len(satir_kumesi.olcum),
        )

    def saglik(self) -> dict[str, Any]:
        try:
            with self._kilit, self._baglanti().cursor() as imlec:
                imlec.execute(SURUM_SQL)
                satir = imlec.fetchone()
            return {"kayit": self.ad, "durum": "hazir", "sema_surumu": satir[0] if satir else None}
        except Exception as hata:
            # Health must report, not raise: a monitoring endpoint that 500s is
            # indistinguishable from a service that is down.
            return {"kayit": self.ad, "durum": "erisilemez", "hata": f"{type(hata).__name__}: {hata}"}


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KayitAyar:
    """Backend selection, read from the environment.

    Environment rather than a config file because this service is deployed as a
    container by track C, and `TOPLAMA_KAYIT` / `DATABASE_URL` are the two knobs
    a compose file can set without rebuilding the image.
    """

    kayit: str = VARSAYILAN_KAYIT
    dsn: str = ""
    dizin: str = VARSAYILAN_DIZIN
    cevre: dict[str, str] = field(default_factory=dict)

    @classmethod
    def cevreden(cls, cevre: dict[str, str] | None = None) -> KayitAyar:
        cevre = dict(os.environ if cevre is None else cevre)
        ad = (cevre.get("TOPLAMA_KAYIT") or VARSAYILAN_KAYIT).strip().lower()
        if ad not in KAYIT_ADLARI:
            raise ValueError(f"TOPLAMA_KAYIT must be one of {', '.join(KAYIT_ADLARI)}; got {ad!r}")
        return cls(
            kayit=ad,
            dsn=cevre.get("DATABASE_URL", ""),
            dizin=cevre.get("TOPLAMA_DOSYA_DIZIN") or VARSAYILAN_DIZIN,
            cevre=cevre,
        )


def kayit_olustur(ayar: KayitAyar | None = None) -> Kayit:
    """Build the configured backend. Does not connect; `baslat()` does that."""
    ayar = ayar or KayitAyar.cevreden()
    if ayar.kayit == "postgres":
        return PostgresKayit(ayar.dsn)
    return DosyaKayit(ayar.dizin)
