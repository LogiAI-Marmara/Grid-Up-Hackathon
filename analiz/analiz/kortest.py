"""Blind-test evaluation: the four metrics of section 4.4.

The protocol, verbatim from the record:

    1. track A runs the generator: N days, M modules, scenarios injected into
       randomly chosen modules, some left untouched.
    2. track B is given only the data. The label file stays with the producer.
    3. the detector runs. Its output is FROZEN.
    4. the key is opened and four metrics are computed.

This module is steps 3 and 4:

    python -m analiz.kortest dondur --dsn ... --cikti cikti.json
    python -m analiz.kortest degerlendir --etiket etiket.json --cikti cikti.json

Freezing is a separate command on purpose, and it is the step that makes the
test blind rather than merely labelled. Section 4.4's second trap: once a result
has been seen, fixing the detector and re-running against the same set destroys
its blindness — the set has leaked into the tuning. A frozen output file is the
artefact that makes "this is what the detector said before anyone looked at the
answers" a checkable claim instead of a promise.

WHY ALL FOUR TOGETHER. Detection rate alone is worthless: a detector that
alarms on everything scores 100%. False-alarm rate alone is worthless: one that
never fires scores perfectly. Lead time is the project's actual product —
section 2.5, "not 'we detected an anomaly' but 'we gave fourteen hours'
warning'". And sensor separation is what stops a broken thermocouple being
reported as a fire. Reporting any one of them on its own would be misleading,
so `rapor()` computes all four and the printer prints all four.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .etiket import (
    SISTEM_TIPLERI,
    EtiketDosyasi,
    EtiketHatasi,
    EtiketSenaryosu,
    oku as etiket_oku,
)
from .sozlesme import Tip

__all__ = ["Olay", "SenaryoSonucu", "KorTestRaporu", "dondur", "yukle", "rapor", "yazdir"]


@dataclass(frozen=True, slots=True)
class Olay:
    """One anomaly episode, as frozen detector output."""

    id: str
    modul_id: str
    tip: Tip
    seviye: str
    skor: float
    ilk_gorulme: datetime
    son_gorulme: datetime
    durum: str
    gerekce: str = ""

    @classmethod
    def sozlukten(cls, ham: dict[str, Any]) -> "Olay":
        return cls(
            id=str(ham["id"]),
            modul_id=str(ham["modul_id"]),
            tip=Tip(ham["tip"]),
            seviye=str(ham["seviye"]),
            skor=float(ham["skor"]),
            ilk_gorulme=_zaman(ham["ilk_gorulme"]),
            son_gorulme=_zaman(ham["son_gorulme"]),
            durum=str(ham["durum"]),
            gerekce=str(ham.get("gerekce") or ""),
        )


def _zaman(deger: Any) -> datetime:
    if isinstance(deger, datetime):
        return deger.astimezone(timezone.utc)
    an = datetime.fromisoformat(str(deger).replace("Z", "+00:00"))
    return an.astimezone(timezone.utc) if an.tzinfo else an.replace(tzinfo=timezone.utc)


def _zaman_yaz(an: datetime) -> str:
    return an.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------
# Step 3 — freeze
# --------------------------------------------------------------------------


def dondur(baglanti, yol: "str | Path | None" = None, kaynak: str = "") -> dict[str, Any]:
    """Freeze the detector's output: every episode, as it stands right now.

    Written before the label file is opened. Nothing here reads the labels, and
    that is the point — this is the artefact that proves what the detector said
    while it still had no access to the answers.
    """
    with baglanti.cursor() as imlec:
        imlec.execute(
            "SELECT sira, id, modul_id, tip, seviye, maks_seviye, skor, "
            "ilk_gorulme, son_gorulme, durum, gerekce, katman "
            "FROM gridup.anomali ORDER BY sira"
        )
        satirlar = imlec.fetchall()

    govde = {
        "dondurma_zamani": _zaman_yaz(datetime.now(timezone.utc)),
        "kaynak": kaynak,
        "olay_sayisi": len(satirlar),
        "olaylar": [
            {
                "sira": int(r["sira"]),
                "id": r["id"],
                "modul_id": r["modul_id"],
                "tip": r["tip"],
                "seviye": r["seviye"],
                "maks_seviye": r["maks_seviye"],
                "skor": float(r["skor"]),
                "ilk_gorulme": _zaman_yaz(r["ilk_gorulme"]),
                "son_gorulme": _zaman_yaz(r["son_gorulme"]),
                "durum": r["durum"],
                "gerekce": r["gerekce"],
                "katman": r["katman"],
            }
            for r in satirlar
        ],
    }
    if yol is not None:
        Path(yol).write_text(
            json.dumps(govde, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return govde


def yukle(yol: "str | Path") -> tuple[tuple[Olay, ...], dict[str, Any]]:
    """Read a frozen output file. Returns the episodes and the file's metadata."""
    yol = Path(yol)
    try:
        ham = json.loads(yol.read_text(encoding="utf-8"))
    except FileNotFoundError as hata:
        raise EtiketHatasi(f"frozen output not found: {yol}") from hata
    except json.JSONDecodeError as hata:
        raise EtiketHatasi(f"{yol}: not valid JSON — {hata}") from hata
    if not isinstance(ham, dict) or "olaylar" not in ham:
        raise EtiketHatasi(f"{yol}: expected an object with an 'olaylar' list")
    olaylar = tuple(Olay.sozlukten(o) for o in ham["olaylar"])
    return olaylar, {k: v for k, v in ham.items() if k != "olaylar"}


# --------------------------------------------------------------------------
# Step 4 — evaluate
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SenaryoSonucu:
    """One injected scenario, scored against what the detector produced."""

    senaryo: EtiketSenaryosu
    olaylar: tuple[Olay, ...]

    @property
    def eslesenler(self) -> tuple[Olay, ...]:
        """Episodes whose `tip` counts as detecting this scenario."""
        kabul = self.senaryo.kabul_edilen_tipler
        return tuple(o for o in self.olaylar if o.tip in kabul)

    @property
    def tespit(self) -> bool:
        return bool(self.eslesenler)

    @property
    def ilk_eslesen(self) -> Olay | None:
        """Earliest matching episode, by the measurement time that opened it.

        By `ilk_gorulme`, not by episode id: the id is the order the detector
        happened to write them in, and lead time is a claim about when we could
        first have told someone, which is a measurement time.
        """
        eslesen = self.eslesenler
        return min(eslesen, key=lambda o: o.ilk_gorulme) if eslesen else None

    @property
    def kazanilan_sure_sn(self) -> float | None:
        """Seconds between the first matching detection and the critical moment.

        Positive means we warned that far ahead — the project's actual product.
        Negative means the fault was already critical when we spoke, which is
        still a detection but not an early warning, and the sign carries that
        distinction rather than hiding it behind an absolute value.

        `None` when the scenario has no critical moment (a frozen sensor does
        not escalate) or was not detected at all. Both are excluded from the
        aggregate rather than counted as zero: a missed scenario has no lead
        time, and averaging in a zero would flatter the number.
        """
        ilk = self.ilk_eslesen
        if ilk is None or self.senaryo.kritik_esik is None:
            return None
        return (self.senaryo.kritik_esik - ilk.ilk_gorulme).total_seconds()

    @property
    def yabanci_tipler(self) -> frozenset[Tip]:
        """Episodes on this module outside the accepted set.

        Not counted as false alarms — the module really is faulty, and a second
        true symptom is not a false alarm. Reported separately as a diagnostic.
        """
        return frozenset(o.tip for o in self.olaylar) - self.senaryo.kabul_edilen_tipler

    @property
    def sebeke_kirlenmesi(self) -> frozenset[Tip]:
        """Grid-fault types produced on a system-health scenario.

        This is the specific mistake layer 0 exists to prevent: a broken sensor
        reported as a hot spot. On a `sensor_arizasi` module, any grid-fault
        episode is a miscount.
        """
        if not self.senaryo.sistem_sagligi:
            return frozenset()
        return frozenset(o.tip for o in self.olaylar if o.tip not in SISTEM_TIPLERI)


@dataclass(frozen=True, slots=True)
class KorTestRaporu:
    """The four metrics, plus the detail behind them."""

    sonuclar: tuple[SenaryoSonucu, ...]
    temiz_moduller: tuple[str, ...]
    temiz_olaylar: tuple[Olay, ...]
    gozlem_gunu: float
    etiket_bilgisi: dict[str, Any] = field(default_factory=dict)
    cikti_bilgisi: dict[str, Any] = field(default_factory=dict)

    # -- metric 1: detection ------------------------------------------------

    @property
    def tespit_edilen(self) -> int:
        return sum(1 for s in self.sonuclar if s.tespit)

    @property
    def tespit_orani(self) -> float:
        return self.tespit_edilen / len(self.sonuclar) if self.sonuclar else 0.0

    # -- metric 2: lead time ------------------------------------------------

    @property
    def kazanilan_sureler(self) -> tuple[float, ...]:
        return tuple(
            s.kazanilan_sure_sn
            for s in self.sonuclar
            if s.kazanilan_sure_sn is not None
        )

    @property
    def medyan_kazanilan_saat(self) -> float | None:
        sureler = self.kazanilan_sureler
        return statistics.median(sureler) / 3600.0 if sureler else None

    @property
    def asgari_kazanilan_saat(self) -> float | None:
        sureler = self.kazanilan_sureler
        return min(sureler) / 3600.0 if sureler else None

    # -- metric 3: false alarms --------------------------------------------

    @property
    def modul_gun(self) -> float:
        """Denominator: clean modules times days observed.

        Zero when the set has no clean modules — and then the rate is not
        "perfect", it is undefined. Section 4.4's first trap is exactly a set
        with no clean modules, against which an alarm-at-everything detector
        scores flawlessly.
        """
        return len(self.temiz_moduller) * self.gozlem_gunu

    @property
    def yanlis_alarm_orani(self) -> float | None:
        if self.modul_gun <= 0:
            return None
        return len(self.temiz_olaylar) / self.modul_gun

    # -- metric 4: sensor separation ---------------------------------------

    @property
    def sistem_senaryolari(self) -> tuple[SenaryoSonucu, ...]:
        return tuple(s for s in self.sonuclar if s.senaryo.sistem_sagligi)

    @property
    def kirlenen_senaryolar(self) -> tuple[SenaryoSonucu, ...]:
        return tuple(s for s in self.sistem_senaryolari if s.sebeke_kirlenmesi)

    @property
    def ayrim_orani(self) -> float | None:
        """Share of system-health scenarios classified as such and not as grid faults."""
        hedefler = self.sistem_senaryolari
        if not hedefler:
            return None
        dogru = sum(1 for s in hedefler if s.tespit and not s.sebeke_kirlenmesi)
        return dogru / len(hedefler)

    # -- overall ------------------------------------------------------------

    @property
    def basarili(self) -> bool:
        return (
            self.tespit_orani == 1.0
            and not self.temiz_olaylar
            and (self.ayrim_orani in (None, 1.0))
        )


def rapor(
    etiket: EtiketDosyasi,
    olaylar: "tuple[Olay, ...] | list[Olay]",
    cikti_bilgisi: dict[str, Any] | None = None,
) -> KorTestRaporu:
    """Score frozen detector output against an opened label file."""
    modul_olaylari: dict[str, list[Olay]] = {}
    for olay in olaylar:
        modul_olaylari.setdefault(olay.modul_id, []).append(olay)

    sonuclar = tuple(
        SenaryoSonucu(senaryo=s, olaylar=tuple(modul_olaylari.get(s.modul_id, ())))
        for s in etiket.senaryolar
    )
    temiz_olaylar = tuple(
        o for o in olaylar if o.modul_id in set(etiket.temiz_moduller)
    )

    return KorTestRaporu(
        sonuclar=sonuclar,
        temiz_moduller=etiket.temiz_moduller,
        temiz_olaylar=temiz_olaylar,
        gozlem_gunu=etiket.gozlem_gunu,
        etiket_bilgisi={
            "senaryo": len(etiket.senaryolar),
            "temiz_modul": len(etiket.temiz_moduller),
            "gun": round(etiket.gozlem_gunu, 1),
            "tohum": etiket.tohum,
        },
        cikti_bilgisi=cikti_bilgisi or {},
    )


# --------------------------------------------------------------------------
# Printing
# --------------------------------------------------------------------------


def _saat(sn: float | None) -> str:
    if sn is None:
        return "—"
    return f"{sn / 3600.0:+.1f} sa"


def yazdir(r: KorTestRaporu, akis=None) -> None:
    """Print the detail table, then the four metrics."""
    yaz = (akis or sys.stdout).write

    yaz("\nSENARYO BAŞINA SONUÇ\n")
    yaz("-" * 108 + "\n")
    yaz(
        f"{'senaryo_id':<28} {'modul':<14} {'senaryo':<17} "
        f"{'üretilen tip':<24} {'tespit':<7} {'kazanılan':>10}\n"
    )
    yaz("-" * 108 + "\n")
    for s in sorted(r.sonuclar, key=lambda x: x.senaryo.senaryo_id):
        uretilen = ",".join(sorted(o.tip.value for o in s.olaylar)) or "—"
        if len(uretilen) > 23:
            uretilen = uretilen[:22] + "…"
        durum = "VAR" if s.tespit else "KAÇTI"
        if s.sebeke_kirlenmesi:
            durum = "KİRLİ"
        yaz(
            f"{s.senaryo.senaryo_id:<28} {s.senaryo.modul_id:<14} "
            f"{s.senaryo.senaryo:<17} {uretilen:<24} {durum:<7} "
            f"{_saat(s.kazanilan_sure_sn):>10}\n"
        )
    yaz("-" * 108 + "\n")

    if r.temiz_olaylar:
        yaz("\nTEMİZ MODÜLLERDE ÜRETİLEN OLAYLAR (yanlış alarm)\n")
        for o in r.temiz_olaylar:
            yaz(f"  {o.modul_id:<14} {o.tip.value:<24} {o.seviye:<7} {o.gerekce[:60]}\n")

    yanlis = r.yanlis_alarm_orani
    ayrim = r.ayrim_orani
    medyan = r.medyan_kazanilan_saat
    asgari = r.asgari_kazanilan_saat

    yaz("\nDÖRT METRİK\n")
    yaz("=" * 108 + "\n")
    yaz(f"{'metrik':<34} {'değer':<22} {'dayanak':<48}\n")
    yaz("-" * 108 + "\n")
    yaz(
        f"{'1. tespit oranı':<34} "
        f"{f'%{r.tespit_orani * 100:.0f}':<22} "
        f"{f'{r.tespit_edilen}/{len(r.sonuclar)} senaryo yakalandı':<48}\n"
    )
    yaz(
        f"{'2. kazanılan süre (medyan)':<34} "
        f"{(f'{medyan:+.1f} saat' if medyan is not None else '—'):<22} "
        f"{(f'en düşük {asgari:+.1f} sa, {len(r.kazanilan_sureler)} senaryoda ölçüldü' if asgari is not None else 'kritik eşiği olan senaryo yok'):<48}\n"
    )
    yaz(
        f"{'3. yanlış alarm (modül-gün)':<34} "
        f"{(f'{yanlis:.3f}' if yanlis is not None else 'ölçülemez'):<22} "
        f"{f'{len(r.temiz_olaylar)} olay / {len(r.temiz_moduller)} temiz modül × {r.gozlem_gunu:.1f} gün':<48}\n"
    )
    yaz(
        f"{'4. sensör arızası ayrımı':<34} "
        f"{(f'%{ayrim * 100:.0f}' if ayrim is not None else '—'):<22} "
        f"{f'{len(r.sistem_senaryolari)} sistem senaryosu, {len(r.kirlenen_senaryolar)} tanesi şebeke arızası sanıldı':<48}\n"
    )
    yaz("=" * 108 + "\n")
    yaz(f"sonuç: {'GEÇTİ' if r.basarili else 'KALDI'}\n")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: "list[str] | None" = None) -> int:
    ayristirici = argparse.ArgumentParser(prog="analiz.kortest", description=__doc__)
    alt = ayristirici.add_subparsers(dest="komut", required=True)

    p_dondur = alt.add_parser("dondur", help="freeze the detector's output (step 3)")
    p_dondur.add_argument("--dsn", required=True)
    p_dondur.add_argument("--cikti", required=True, help="output JSON path")

    p_deger = alt.add_parser("degerlendir", help="open the key and score (step 4)")
    p_deger.add_argument("--etiket", required=True, help="label file")
    p_deger.add_argument("--cikti", required=True, help="frozen output file")
    p_deger.add_argument("--json", action="store_true", help="emit JSON instead of a table")

    args = ayristirici.parse_args(argv)

    if args.komut == "dondur":
        from .db import baglan
        from .ayar import Ayar

        ayar = Ayar.ortamdan().ile(veritabani={"dsn": args.dsn})
        with baglan(ayar) as baglanti:
            govde = dondur(baglanti, args.cikti, kaynak=args.dsn)
        print(f"{govde['olay_sayisi']} olay donduruldu → {args.cikti}")
        return 0

    try:
        etiket = etiket_oku(args.etiket)
        olaylar, bilgi = yukle(args.cikti)
    except EtiketHatasi as hata:
        print(f"hata: {hata}", file=sys.stderr)
        return 2

    r = rapor(etiket, olaylar, bilgi)
    if args.json:
        print(
            json.dumps(
                {
                    "tespit_orani": r.tespit_orani,
                    "kazanilan_sure_medyan_saat": r.medyan_kazanilan_saat,
                    "yanlis_alarm_modul_gun": r.yanlis_alarm_orani,
                    "sensor_ayrim_orani": r.ayrim_orani,
                    "senaryolar": [
                        {
                            "senaryo_id": s.senaryo.senaryo_id,
                            "modul_id": s.senaryo.modul_id,
                            "senaryo": s.senaryo.senaryo,
                            "tespit": s.tespit,
                            "kazanilan_sure_sn": s.kazanilan_sure_sn,
                            "uretilen": sorted(o.tip.value for o in s.olaylar),
                        }
                        for s in r.sonuclar
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(
            f"\nKÖR TEST DEĞERLENDİRMESİ\n"
            f"etiket : {args.etiket}  "
            f"({r.etiket_bilgisi['senaryo']} senaryo, "
            f"{r.etiket_bilgisi['temiz_modul']} temiz modül, "
            f"{r.etiket_bilgisi['gun']} gün)\n"
            f"çıktı  : {args.cikti}  "
            f"({len(olaylar)} olay, donduruldu {bilgi.get('dondurma_zamani', '?')})"
        )
        yazdir(r)
    return 0 if r.basarili else 1


if __name__ == "__main__":
    raise SystemExit(main())
