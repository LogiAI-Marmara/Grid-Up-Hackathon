"""Smoke-test checks — the integration phase's "does data flow end to end".

Track C owns the runner (it starts the simulator, the collector, the detector
and this API, then calls this). Track B owns the CHECKS: given a live API and a
statement of which module carries which scenario, decide whether what came out
the far end is what the simulator put in. One entry point, exit 0 on success,
non-zero on failure:

    python -m analiz.duman --api http://127.0.0.1:8080 --senaryolar duman.json

INPUT FORMAT (`--senaryolar`, JSON, UTF-8). Which module carries which scenario
is the runner's knowledge, not ours, so it is an input:

    {
      "surum": 1,
      "bas": "2026-09-16T06:00:00Z",
      "moduller": {
        "TR041-P01-M2": "temiz",
        "TR041-P01-M1": ["gevsek_klemens", "seviye_gecisi"],
        "TR063-P02-M3": "besleme_kaybi"
      }
    }

  surum     format version, currently 1.
  bas       optional. Only episodes first seen at or after this instant count,
            so a database that has seen earlier runs does not pollute the
            result. Omit for a fresh database.
  moduller  modul_id -> one scenario name, or a list of them. A module may
            carry several checks (a loose terminal that also escalates).

SCENARIO VOCABULARY and what each check asserts, all read through contract ⑤:

  temiz              NO episode of any type on the module (since `bas`).
  gevsek_klemens     an episode whose `tip` is one the label format accepts
  asiri_yuk          for that scenario (`etiket.SENARYO_TIPLERI`); when its
  faz_dengesizligi   `kanit.kare_id` is present, `GET /termal/kare/{id}`
  nem_yukselmesi     returns 768 °C values (the frame decodes end to end).
  ark_olayi
  sensor_arizasi
  modul_saglik       a `modul_saglik` episode, any cause.
  besleme_kaybi      a `modul_saglik` episode whose `kanit.neden` is `besleme`,
                     or the module's detail reporting `besleme = yedek`.
  sinyal_zayif       a `modul_saglik` episode with `kanit.neden = sinyal`.
  saat_kaymasi       a `modul_saglik` episode with `kanit.neden = saat_kaymasi`.
  sessiz             a `modul_saglik` episode with `kanit.neden = sessizlik`.
  seviye_gecisi      an episode of the module has a `seviye` transition from
                     one non-normal severity to another (e.g. izle -> uyari),
                     visible both in its own journal and in `GET /gecisler`.

Global checks, always run: `/saglik` answers, the scan cursor is no further
behind than `--azami-imlec-gecikme-sn`, and the data-delay metric is present.

Nothing here touches the database: the point is that track C's consumer path
— the HTTP API — is what is being proven.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .etiket import SENARYO_ADLARI, SENARYO_TIPLERI
from .sozlesme import TERMAL_PIKSEL, Seviye, Tip

__all__ = [
    "SURUM",
    "DUMAN_SENARYOLARI",
    "Kontrol",
    "DumanRaporu",
    "DumanHatasi",
    "senaryolari_oku",
    "kontrol_et",
    "UrlIstemci",
    "main",
]

SURUM = 1

#: Scenario names this module understands. The seven of the label format, the
#: clean module, the module-health causes by name, and the severity transition.
DUMAN_SENARYOLARI: tuple[str, ...] = (
    "temiz",
    *SENARYO_ADLARI,
    "besleme_kaybi",
    "sinyal_zayif",
    "saat_kaymasi",
    "sessiz",
    "seviye_gecisi",
)

_NEDENLI = {
    "besleme_kaybi": "besleme",
    "sinyal_zayif": "sinyal",
    "saat_kaymasi": "saat_kaymasi",
    "sessiz": "sessizlik",
}

#: What `getir` returns: (HTTP status, decoded JSON body or None).
Getir = Callable[[str, dict[str, Any] | None], tuple[int, Any]]


class DumanHatasi(ValueError):
    """A scenario file that cannot be trusted, or an API that cannot be reached."""


@dataclass(frozen=True, slots=True)
class Kontrol:
    """One check's outcome."""

    ad: str
    basarili: bool
    ayrinti: str = ""
    modul_id: str | None = None
    senaryo: str | None = None

    @property
    def satir(self) -> str:
        etiket = "OK  " if self.basarili else "HATA"
        hedef = f" {self.modul_id}" if self.modul_id else ""
        return f"[{etiket}] {self.ad}{hedef}: {self.ayrinti}".rstrip(": ")


@dataclass
class DumanRaporu:
    kontroller: list[Kontrol] = field(default_factory=list)

    @property
    def basarili(self) -> bool:
        return all(k.basarili for k in self.kontroller)

    @property
    def basarisizlar(self) -> list[Kontrol]:
        return [k for k in self.kontroller if not k.basarili]

    def ekle(self, kontrol: Kontrol) -> None:
        self.kontroller.append(kontrol)

    def sozluk(self) -> dict[str, Any]:
        return {
            "basarili": self.basarili,
            "kontrol_sayisi": len(self.kontroller),
            "basarisiz_sayisi": len(self.basarisizlar),
            "kontroller": [
                {
                    "ad": k.ad,
                    "basarili": k.basarili,
                    "modul_id": k.modul_id,
                    "senaryo": k.senaryo,
                    "ayrinti": k.ayrinti,
                }
                for k in self.kontroller
            ],
        }


# --------------------------------------------------------------------------
# Input
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DumanSenaryolari:
    moduller: dict[str, tuple[str, ...]]
    bas: datetime | None = None


def senaryolari_oku(kaynak: "Path | str | dict") -> DumanSenaryolari:
    """Parse the scenario file strictly. An unknown name is an error, not a skip."""
    if isinstance(kaynak, dict):
        veri = kaynak
    else:
        try:
            veri = json.loads(Path(kaynak).read_text(encoding="utf-8"))
        except (OSError, ValueError) as hata:
            raise DumanHatasi(f"senaryo dosyası okunamadı: {kaynak}: {hata}") from hata

    if not isinstance(veri, dict):
        raise DumanHatasi("senaryo dosyası bir JSON nesnesi olmalı")
    if veri.get("surum") != SURUM:
        raise DumanHatasi(f"surum {SURUM} bekleniyordu, {veri.get('surum')!r} geldi")
    moduller = veri.get("moduller")
    if not isinstance(moduller, dict) or not moduller:
        raise DumanHatasi("`moduller` boş olmayan bir nesne olmalı: modul_id -> senaryo")

    sonuc: dict[str, tuple[str, ...]] = {}
    for modul_id, senaryolar in moduller.items():
        if isinstance(senaryolar, str):
            senaryolar = [senaryolar]
        if not isinstance(senaryolar, list) or not senaryolar:
            raise DumanHatasi(f"{modul_id}: senaryo bir ad veya ad listesi olmalı")
        for ad in senaryolar:
            if ad not in DUMAN_SENARYOLARI:
                raise DumanHatasi(
                    f"{modul_id}: bilinmeyen senaryo {ad!r}; kabul edilenler: "
                    f"{', '.join(DUMAN_SENARYOLARI)}"
                )
        if "temiz" in senaryolar and len(senaryolar) > 1:
            raise DumanHatasi(f"{modul_id}: `temiz` başka bir senaryoyla birlikte olamaz")
        sonuc[str(modul_id)] = tuple(senaryolar)

    bas = None
    if veri.get("bas") is not None:
        try:
            bas = datetime.fromisoformat(str(veri["bas"]).replace("Z", "+00:00"))
        except ValueError as hata:
            raise DumanHatasi(f"`bas` ISO 8601 değil: {veri['bas']!r}") from hata
        if bas.tzinfo is None:
            raise DumanHatasi("`bas` saat dilimi taşımalı (UTC, sonunda Z)")
    return DumanSenaryolari(moduller=sonuc, bas=bas)


# --------------------------------------------------------------------------
# The checks
# --------------------------------------------------------------------------


def kontrol_et(
    getir: Getir,
    senaryolar: DumanSenaryolari,
    *,
    azami_imlec_gecikme_sn: float = 600.0,
) -> DumanRaporu:
    """Run every check against the API behind `getir`. Never raises on a failed
    check — failures are rows in the report; only an unreachable API raises."""
    rapor = DumanRaporu()
    _genel(getir, rapor, azami_imlec_gecikme_sn)

    for modul_id, adlar in senaryolar.moduller.items():
        olaylar = _modul_olaylari(getir, modul_id, senaryolar.bas, rapor)
        if olaylar is None:
            continue
        for ad in adlar:
            _senaryo(getir, rapor, modul_id, ad, olaylar)
    return rapor


def _genel(getir: Getir, rapor: DumanRaporu, azami_gecikme: float) -> None:
    durum, govde = getir("/saglik", None)
    if durum != 200 or not isinstance(govde, dict):
        rapor.ekle(Kontrol("saglik", False, f"HTTP {durum}"))
        return
    rapor.ekle(Kontrol("saglik", govde.get("durum") == "calisiyor", f"durum={govde.get('durum')}"))

    imlecler = govde.get("imlecler") or []
    if not imlecler:
        rapor.ekle(Kontrol("tarama_imleci", False, "hiç imleç yok — dedektör hiç tur atmamış"))
    else:
        en_az = min(float(i.get("gecikme_sn", 1e12)) for i in imlecler)
        rapor.ekle(
            Kontrol(
                "tarama_imleci",
                en_az <= azami_gecikme,
                f"en güncel imleç {en_az:.0f} sn geride (sınır {azami_gecikme:.0f} sn)",
            )
        )

    metrik = govde.get("veri_gecikmesi")
    rapor.ekle(
        Kontrol(
            "veri_gecikmesi",
            isinstance(metrik, dict) and "azami_sn" in metrik,
            f"azami {metrik.get('azami_sn')} sn, geciken satır {metrik.get('geciken_satir')}"
            if isinstance(metrik, dict)
            else "metrik yok",
        )
    )

    durum, govde = getir("/gecisler", {"limit": 1})
    rapor.ekle(
        Kontrol(
            "gecisler_akisi",
            durum == 200 and isinstance(govde, dict) and "veriler" in govde,
            f"HTTP {durum}",
        )
    )


def _modul_olaylari(
    getir: Getir, modul_id: str, bas: datetime | None, rapor: DumanRaporu
) -> list[dict] | None:
    """Every episode of the module (all states), paged by keyset, since `bas`."""
    durum, _ = getir(f"/moduller/{modul_id}", None)
    if durum != 200:
        rapor.ekle(Kontrol("modul", False, f"HTTP {durum} — modül API'de yok", modul_id))
        return None

    olaylar: list[dict] = []
    sonra: int | None = None
    while True:
        params: dict[str, Any] = {"modul": modul_id, "limit": 500}
        if sonra is not None:
            params["sonra"] = sonra
        durum, govde = getir("/anomaliler", params)
        if durum != 200 or not isinstance(govde, dict):
            rapor.ekle(Kontrol("anomaliler", False, f"HTTP {durum}", modul_id))
            return None
        olaylar.extend(govde.get("veriler") or [])
        sonra = govde.get("sonraki")
        if sonra is None:
            break

    if bas is not None:
        olaylar = [o for o in olaylar if _zaman(o.get("ilk_gorulme")) >= bas]
    return olaylar


def _senaryo(getir: Getir, rapor: DumanRaporu, modul_id: str, ad: str, olaylar: list[dict]) -> None:
    ozet = ", ".join(f"{o['tip']}/{o['seviye']}/{o['durum']}" for o in olaylar) or "olay yok"

    if ad == "temiz":
        rapor.ekle(Kontrol("temiz", not olaylar, ozet, modul_id, ad))
        return

    if ad in SENARYO_TIPLERI:
        kabul = {t.value for t in SENARYO_TIPLERI[ad]}
        eslesen = [o for o in olaylar if o["tip"] in kabul]
        rapor.ekle(
            Kontrol(
                ad,
                bool(eslesen),
                f"kabul edilen tipler {sorted(kabul)}; {ozet}",
                modul_id,
                ad,
            )
        )
        for olay in eslesen:
            kare_id = (olay.get("kanit") or {}).get("kare_id")
            if kare_id:
                _kare(getir, rapor, modul_id, ad, olay["id"], kare_id)
        return

    if ad in _NEDENLI:
        neden = _NEDENLI[ad]
        saglik = [o for o in olaylar if o["tip"] == Tip.MODUL_SAGLIK.value]
        nedenli = [o for o in saglik if (o.get("kanit") or {}).get("neden") == neden]
        basarili = bool(nedenli)
        ayrinti = f"neden={neden}; {ozet}"
        if ad == "besleme_kaybi" and not basarili and saglik:
            # Several health causes merge into one episode; the module's own
            # status settles it.
            durum, detay = getir(f"/moduller/{modul_id}", None)
            if durum == 200 and isinstance(detay, dict) and detay.get("besleme") == "yedek":
                basarili = True
                ayrinti += "; modül detayı besleme=yedek"
        rapor.ekle(Kontrol(ad, basarili, ayrinti, modul_id, ad))
        return

    if ad == "seviye_gecisi":
        _seviye_gecisi(getir, rapor, modul_id, olaylar)
        return

    rapor.ekle(Kontrol(ad, False, "bilinmeyen senaryo", modul_id, ad))  # pragma: no cover


def _kare(getir: Getir, rapor: DumanRaporu, modul_id: str, ad: str, olay_id: str, kare_id: str) -> None:
    durum, govde = getir(f"/termal/kare/{kare_id}", None)
    pikseller = govde.get("piksel_verisi") if isinstance(govde, dict) else None
    iyi = (
        durum == 200
        and isinstance(pikseller, list)
        and len(pikseller) == TERMAL_PIKSEL
        and all(isinstance(p, (int, float)) for p in pikseller)
    )
    rapor.ekle(
        Kontrol(
            "kanit_karesi",
            iyi,
            f"{olay_id} -> {kare_id}: HTTP {durum}, "
            f"{len(pikseller) if isinstance(pikseller, list) else 0} değer",
            modul_id,
            ad,
        )
    )


def _seviye_gecisi(getir: Getir, rapor: DumanRaporu, modul_id: str, olaylar: list[dict]) -> None:
    gecerli = {s.value for s in Seviye} - {Seviye.NORMAL.value}
    bulunan: tuple[str, int, str] | None = None
    for olay in olaylar:
        durum, govde = getir(f"/anomaliler/{olay['id']}/gecisler", None)
        if durum != 200 or not isinstance(govde, dict):
            continue
        for g in govde.get("gecisler") or []:
            if g["alan"] == "seviye" and g["onceki"] in gecerli and g["yeni"] in gecerli:
                bulunan = (olay["id"], int(g["sira"]), f"{g['onceki']} -> {g['yeni']}")
                break
        if bulunan:
            break

    if bulunan is None:
        rapor.ekle(
            Kontrol(
                "seviye_gecisi", False, "hiçbir olayda seviye geçişi yok", modul_id, "seviye_gecisi"
            )
        )
        return

    olay_id, gecis_id, metin = bulunan
    # The same transition must be reachable through the global feed.
    durum, govde = getir("/gecisler", {"sonra": gecis_id - 1, "limit": 1})
    veriler = govde.get("veriler") if isinstance(govde, dict) else None
    kuresel = bool(veriler) and veriler[0]["id"] == gecis_id and veriler[0]["anomali_id"] == olay_id
    rapor.ekle(
        Kontrol(
            "seviye_gecisi",
            kuresel,
            f"{olay_id}: {metin} (geçiş {gecis_id}); /gecisler {'doğruladı' if kuresel else 'bulamadı'}",
            modul_id,
            "seviye_gecisi",
        )
    )


def _zaman(metin: str | None) -> datetime:
    if not metin:
        return datetime.min.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(metin.replace("Z", "+00:00"))


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------


class UrlIstemci:
    """`getir` over a live API with the standard library — no extra dependency
    for track C to install just to run the checks."""

    def __init__(self, taban: str, zaman_asimi_sn: float = 30.0) -> None:
        self._taban = taban.rstrip("/")
        self._zaman_asimi = zaman_asimi_sn

    def __call__(self, yol: str, params: dict[str, Any] | None) -> tuple[int, Any]:
        url = self._taban + yol
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        try:
            with urllib.request.urlopen(url, timeout=self._zaman_asimi) as cevap:  # noqa: S310
                return cevap.status, json.loads(cevap.read().decode("utf-8"))
        except urllib.error.HTTPError as hata:
            try:
                govde = json.loads(hata.read().decode("utf-8"))
            except ValueError:
                govde = None
            return hata.code, govde
        except (urllib.error.URLError, OSError, TimeoutError) as hata:
            raise DumanHatasi(f"API'ye ulaşılamıyor: {url}: {hata}") from hata


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def main(argv: "list[str] | None" = None) -> int:
    """Exit 0: every check passed. 1: at least one failed. 2: usage or unreachable API."""
    ayristirici = argparse.ArgumentParser(
        prog="analiz.duman",
        description="İZ B duman testi doğrulamaları — canlı API'ye karşı, çıkış kodu 0/1/2.",
    )
    ayristirici.add_argument("--api", required=True, help="API kökü, örn. http://127.0.0.1:8080")
    ayristirici.add_argument(
        "--senaryolar", required=True, help="modül -> senaryo eşlemesi (JSON, format için modül docstring'i)"
    )
    ayristirici.add_argument(
        "--azami-imlec-gecikme-sn",
        type=float,
        default=600.0,
        help="tarama imleci bundan daha geride ise başarısız (varsayılan 600)",
    )
    ayristirici.add_argument("--json", help="raporu bu dosyaya da yaz")
    ayristirici.add_argument("--zaman-asimi-sn", type=float, default=30.0)
    args = ayristirici.parse_args(argv)

    try:
        senaryolar = senaryolari_oku(args.senaryolar)
        rapor = kontrol_et(
            UrlIstemci(args.api, args.zaman_asimi_sn),
            senaryolar,
            azami_imlec_gecikme_sn=args.azami_imlec_gecikme_sn,
        )
    except DumanHatasi as hata:
        print(f"duman: {hata}", file=sys.stderr)
        return 2

    for kontrol in rapor.kontroller:
        print(kontrol.satir)
    print(
        f"{len(rapor.kontroller)} kontrol, {len(rapor.basarisizlar)} başarısız — "
        f"{'BAŞARILI' if rapor.basarili else 'BAŞARISIZ'}"
    )
    if args.json:
        Path(args.json).write_text(
            json.dumps(rapor.sozluk(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return 0 if rapor.basarili else 1


if __name__ == "__main__":
    raise SystemExit(main())
