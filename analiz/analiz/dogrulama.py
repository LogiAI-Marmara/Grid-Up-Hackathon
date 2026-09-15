"""Run the whole fixture set through the real scan loop, into a real database.

This is the labelled-set harness of section 2.7: fixtures in, scan turns run,
episodes out, answer key checked. It is not the blind-test evaluation tool —
that is section 4.4's, it belongs to a later delivery, and the seam it will plug
into is `rapor()` below, which already computes per-scenario detection and the
false-alarm count. What it does not compute is lead time, which needs the
injection's true onset time, and that is exactly the thing a blind set withholds.

    python -m analiz.dogrulama --dsn postgresql:///gridup_dogrulama

Leaves the database populated on purpose, so the episode and journal tables can
be inspected with SQL afterwards rather than through a test runner's output.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import psycopg

from .ayar import Ayar
from .db import baglan, sema_kur
from .fikstur import Fikstur
from .senaryolar import SENARYOLAR, Senaryo, kur
from .sozlesme import Tip
from .tarama import Tarayici

__all__ = ["dogrulama_ayari", "kos", "oynat", "rapor", "Rapor", "SenaryoSonucu"]


def dogrulama_ayari(dsn: str) -> Ayar:
    """Configuration for a fixture run.

    Two deliberate differences from production, and no others — the detector under
    test is otherwise exactly the one that would ship:

    `emniyet_payi_sn = 0`: the margin exists to tolerate a collector transaction
    committing after a turn started. Fixtures set `alindi_zaman` explicitly and
    commit before any turn runs, so there is nothing in flight to tolerate, and a
    non-zero margin would just make the run non-deterministic.

    `azami_aralik_sn = 0`: the per-turn range cap is a catch-up safety valve. The
    fixture set is written all at once and has to be consumed in the turns the
    test asks for, not spread over as many turns as a cap implies.
    """
    return Ayar().ile(
        veritabani={"dsn": dsn},
        tarama={
            "emniyet_payi_sn": 0.0,
            "azami_aralik_sn": 0.0,
            "ilk_imlec_geri_sn": 30 * 24 * 3600.0,
        },
    )


@dataclass(frozen=True, slots=True)
class SenaryoSonucu:
    """One scenario's verdict against the answer key."""

    senaryo: Senaryo
    uretilen: frozenset[Tip]

    @property
    def tespit(self) -> bool:
        """Did every expected type come out? Empty expectation means "stay silent"."""
        if not self.senaryo.beklenen:
            return not self.uretilen
        return self.senaryo.beklenen <= self.uretilen

    @property
    def ihlal(self) -> frozenset[Tip]:
        """Forbidden types that were produced anyway — e.g. a sensor fault
        reported as a temperature anomaly."""
        return self.senaryo.yasak & self.uretilen

    @property
    def fazla(self) -> frozenset[Tip]:
        """Types produced beyond what was expected. On a clean module these are
        false alarms; on a faulty one they are usually a second true symptom."""
        return self.uretilen - self.senaryo.beklenen


@dataclass(frozen=True, slots=True)
class Rapor:
    """The whole run. Three of section 4.4's four metrics; lead time needs onsets."""

    sonuclar: tuple[SenaryoSonucu, ...] = ()
    tur_sayisi: int = 0
    satir: int = 0
    olay: int = 0
    gecis: int = 0

    @property
    def tespit_orani(self) -> float:
        hedefler = [s for s in self.sonuclar if s.senaryo.beklenen]
        if not hedefler:
            return 0.0
        return sum(1 for s in hedefler if s.tespit) / len(hedefler)

    @property
    def yanlis_alarm(self) -> int:
        """Episodes on modules that should have produced none."""
        return sum(
            len(s.uretilen) for s in self.sonuclar if not s.senaryo.beklenen
        )

    @property
    def sensor_ayrimi(self) -> bool:
        """Was any sensor failure mistaken for a grid fault?"""
        return all(not s.ihlal for s in self.sonuclar)

    @property
    def basarili(self) -> bool:
        return (
            all(s.tespit for s in self.sonuclar)
            and self.sensor_ayrimi
            and self.yanlis_alarm == 0
        )


def kos(
    baglanti: psycopg.Connection,
    ayar: Ayar,
    simdi: datetime | None = None,
    tur_sayisi: int = 2,
    gecmis_gun: float = 15.0,
) -> Rapor:
    """Load the fixtures, run the scan loop, and score the result.

    More than one turn by default, because a single turn cannot show the episode
    model working: the second turn is what proves a repeated finding updates the
    open episode rather than opening a second one.
    """
    simdi = simdi or datetime.now(timezone.utc)
    sema_kur(baglanti)

    fikstur = Fikstur(baglanti)
    satir, _ = kur(fikstur, simdi, gecmis_gun=gecmis_gun)

    tarayici = Tarayici(baglanti, ayar)
    for i in range(tur_sayisi):
        # Advance the clock a little each turn so successive turns are distinct
        # passes rather than the same instant evaluated repeatedly.
        tarayici.tur(simdi=simdi + timedelta(seconds=i * ayar.tarama.periyot_sn))

    return rapor(baglanti, tur_sayisi=tur_sayisi, satir=satir)


def oynat(
    baglanti: psycopg.Connection,
    ayar: Ayar,
    simdi: datetime,
    bas: datetime,
    adim_dk: float = 15.0,
) -> int:
    """Replay the scan loop forward across the data, turn by turn.

    WHY THIS EXISTS, AND WHY LEAD TIME IS MEANINGLESS WITHOUT IT. `kos` runs a
    couple of turns at the end of the window, which is enough to prove the
    detector finds each scenario but says nothing about *when* it would have.
    Every episode opens at the last measurement, so the gap between the first
    detection and the critical moment comes out at roughly zero for everything —
    and that gap is the project's headline claim (section 2.5).

    Replaying steps the clock through the data the way it would pass in the
    field: a turn every `adim_dk` minutes, each one seeing only what had arrived
    by then. An episode therefore opens on the turn where the evidence first
    crossed a threshold, which is exactly the moment a real deployment would have
    told somebody — so the subtraction against the label's `kritik_esik` measures
    the thing it claims to measure.

    Returns the number of turns run.
    """
    tarayici = Tarayici(baglanti, ayar)
    tarayici.imlecler.geri_al(ayar.tarama.imlec_adi, bas)

    adim = timedelta(minutes=adim_dk)
    an = bas + adim
    sayac = 0
    while an <= simdi:
        tarayici.tur(simdi=an)
        sayac += 1
        an += adim
    if sayac == 0 or (an - adim) < simdi:
        tarayici.tur(simdi=simdi)
        sayac += 1
    return sayac


def rapor(baglanti: psycopg.Connection, tur_sayisi: int = 0, satir: int = 0) -> Rapor:
    """Score whatever is in the episode table against the answer key."""
    with baglanti.cursor() as imlec:
        imlec.execute("SELECT modul_id, tip FROM gridup.anomali")
        uretilen: dict[str, set[Tip]] = {}
        for row in imlec.fetchall():
            uretilen.setdefault(row["modul_id"], set()).add(Tip(row["tip"]))

        imlec.execute("SELECT count(*) AS n FROM gridup.anomali")
        olay = int(imlec.fetchone()["n"])  # type: ignore[index]
        imlec.execute("SELECT count(*) AS n FROM gridup.anomali_gecis")
        gecis = int(imlec.fetchone()["n"])  # type: ignore[index]

    return Rapor(
        sonuclar=tuple(
            SenaryoSonucu(senaryo=s, uretilen=frozenset(uretilen.get(s.modul_id, ())))
            for s in SENARYOLAR
        ),
        tur_sayisi=tur_sayisi,
        satir=satir,
        olay=olay,
        gecis=gecis,
    )


def _yazdir(r: Rapor) -> None:
    print(f"{'senaryo':<32} {'modul':<14} {'bekleniyor':<24} {'uretilen':<34} sonuc")
    print("-" * 118)
    for s in sorted(r.sonuclar, key=lambda x: x.senaryo.ad):
        bekleniyor = ",".join(sorted(t.value for t in s.senaryo.beklenen)) or "-"
        cikan = ",".join(sorted(t.value for t in s.uretilen)) or "-"
        if s.ihlal:
            sonuc = "IHLAL " + ",".join(sorted(t.value for t in s.ihlal))
        elif s.tespit:
            sonuc = "gecti"
        else:
            sonuc = "KACIRDI"
        print(f"{s.senaryo.ad:<32} {s.senaryo.modul_id:<14} {bekleniyor:<24} {cikan:<34} {sonuc}")
    print("-" * 118)
    print(
        f"tespit orani {r.tespit_orani:.0%} | yanlis alarm {r.yanlis_alarm} | "
        f"sensor ayrimi {'tamam' if r.sensor_ayrimi else 'BOZUK'} | "
        f"olay {r.olay} | gecis {r.gecis} | tur {r.tur_sayisi} | satir {r.satir}"
    )


def main(argv: list[str] | None = None) -> int:
    ayristirici = argparse.ArgumentParser(prog="analiz.dogrulama", description=__doc__)
    ayristirici.add_argument("--dsn", default="postgresql:///gridup_dogrulama")
    ayristirici.add_argument("--tur", type=int, default=2, help="scan turns to run")
    ayristirici.add_argument("--gun", type=float, default=15.0, help="days of history")
    ayristirici.add_argument("--ayrinti", action="store_true")
    args = ayristirici.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.ayrinti else logging.WARNING,
        format="%(levelname)-7s %(name)s: %(message)s",
    )
    ayar = dogrulama_ayari(args.dsn)
    with baglan(ayar) as baglanti:
        r = kos(baglanti, ayar, tur_sayisi=args.tur, gecmis_gun=args.gun)
    _yazdir(r)
    return 0 if r.basarili else 1


if __name__ == "__main__":
    sys.exit(main())
