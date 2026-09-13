"""The fleet loop: N modules, one clock, one scenario timeline.

`Modul` knows how to produce one packet for one instant. This module is what
turns that into a run: it builds the topology, gives every site its weather,
decides *when* the fault starts, and walks the clock forward in packet-period
steps, emitting every module's packet for each tick.

Three decisions are worth stating, because they are the difference between data
that proves something and data that only looks busy.

**Weather is shared per site, not per module.** Section 7.7's neighbour
comparison ("this module diverged from the other one in the same building") is
only meaningful if the two modules genuinely saw the same outdoor air. `Hava`
carries mutable drift state and `Modul` advances it itself, so handing the same
instance to several modules would advance the drift once per module per tick —
the drift would run N times too fast. `PaylasilanHava` fixes that by computing
one sample per instant and handing the same value to everyone in the site.

**The fault starts in the middle of the run, not at the beginning.** A detector
needs to see the module's normal behaviour before the fault to have anything to
compare against, and a demo needs the operator to watch the alarm appear rather
than find it already there. The scenario therefore gets a delay and a ramp
length, both derived from the run length by default.

**Time is emitted in module order inside each tick.** That is the order the
collector would see packets arrive in, so a run piped straight into the ingest
service is a realistic traffic pattern rather than one module's whole history
followed by the next one's.
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .ayar import EsikAyar, OrneklemeAyar, SahaAyar, topoloji
from .fizik import Hava, HavaDurumu
from .modul import Modul, UretilenPaket
from .senaryo import Senaryo, senaryo_olustur

#: Default root seed. Same seed plus same start time reproduces a run exactly.
VARSAYILAN_TOHUM = 20260914


class PaylasilanHava:
    """One weather realisation for a site, shared by every module in it.

    Wraps `Hava` and memoises the sample for the current instant: the first
    module in the site advances the drift, the rest read the same value back.
    The interface is the subset of `Hava` that `Modul` uses, so it is a drop-in
    replacement and `modul.py` needs to know nothing about sharing.
    """

    def __init__(self, hava: Hava) -> None:
        self._hava = hava
        self._an: datetime | None = None
        self._durum: HavaDurumu | None = None

    def taban_sicaklik(self, an: datetime) -> float:
        """Deterministic part of the weather — no state, safe to call any time."""
        return self._hava.taban_sicaklik(an)

    def ilerle(self, an: datetime, dt_s: float) -> HavaDurumu:
        if self._an != an or self._durum is None:
            self._durum = self._hava.ilerle(an, dt_s)
            self._an = an
        return self._durum


@dataclass(frozen=True)
class KosuAyar:
    """Everything that defines one run of the generator.

    `senaryo_bas_orani` / `senaryo_sure_orani` are fractions of the run length:
    with the defaults a 120-minute run is 42 minutes of healthy operation, then
    a fault that takes 66 minutes to reach full strength and stays there for the
    remaining 12. Both can be overridden in seconds when a test needs an exact
    timeline.
    """

    modul_sayisi: int = 9
    sure_dk: float = 60.0
    tohum: int = VARSAYILAN_TOHUM
    senaryo_ad: str | None = None
    #: Run start, UTC-aware. None means "so that the run ends about now", which
    #: keeps the daily load curve and the season realistic without producing
    #: timestamps in the future.
    baslangic: datetime | None = None
    senaryo_bas_orani: float = 0.35
    senaryo_sure_orani: float = 0.55
    senaryo_bas_s: float | None = None
    senaryo_sure_s: float | None = None
    ornekleme: OrneklemeAyar = field(default_factory=OrneklemeAyar)
    esik: EsikAyar = field(default_factory=EsikAyar)

    def __post_init__(self) -> None:
        if self.modul_sayisi < 1:
            raise ValueError("modul_sayisi must be at least 1")
        if self.sure_dk <= 0:
            raise ValueError("sure_dk must be positive")
        if self.baslangic is not None and self.baslangic.tzinfo is None:
            raise ValueError("baslangic must be timezone-aware (UTC)")

    @property
    def sure_s(self) -> float:
        return self.sure_dk * 60.0


@dataclass
class KosuOzeti:
    """Run statistics — what the CLI prints to stderr when the run is over."""

    modul_sayisi: int = 0
    paket: int = 0
    olcum: int = 0
    termal_ozet: int = 0
    termal_kare: int = 0
    kalite_supheli: int = 0
    kalite_yok: int = 0
    yedek_besleme: int = 0
    ark_olay: int = 0
    ilk_zaman: str | None = None
    son_zaman: str | None = None
    kare_sebepleri: dict[str, int] = field(default_factory=dict)

    def ekle(self, uretilen: UretilenPaket) -> None:
        paket = uretilen.paket
        self.paket += 1
        self.olcum += len(paket["olcumler"])
        if paket.get("termal_ozet") is not None:
            self.termal_ozet += 1
        if paket.get("termal_kare") is not None:
            self.termal_kare += 1
        if paket["modul_durum"]["besleme"] == "yedek":
            self.yedek_besleme += 1
        for olcum in paket["olcumler"]:
            if olcum["kalite"] == "supheli":
                self.kalite_supheli += 1
            elif olcum["kalite"] == "yok":
                self.kalite_yok += 1
            if olcum["olcum_tipi"] == "ark_olay":
                self.ark_olay += 1
        if self.ilk_zaman is None:
            self.ilk_zaman = paket["zaman"]
        self.son_zaman = paket["zaman"]
        if uretilen.kare_sebebi:
            # Group by the first trigger only: the full string carries the
            # measured values and would never repeat.
            anahtar = uretilen.kare_sebebi.split(",")[0].split(" ")[0]
            self.kare_sebepleri[anahtar] = self.kare_sebepleri.get(anahtar, 0) + 1


def varsayilan_baslangic(sure_s: float, paket_s: int) -> datetime:
    """Start time such that the run finishes at the current whole packet period.

    Aligning to the packet period keeps timestamps tidy (…:00, …:10, …:20) and
    makes two runs started within the same period produce identical output.
    """
    simdi = datetime.now(timezone.utc).replace(microsecond=0)
    hizala = simdi.second % max(paket_s, 1)
    return simdi - timedelta(seconds=hizala + sure_s)


class Filo:
    """A fleet of simulated modules driven by one clock."""

    def __init__(self, ayar: KosuAyar) -> None:
        self.ayar = ayar
        self.sahalar: tuple[SahaAyar, ...] = topoloji(
            ayar.modul_sayisi,
            ayar.tohum,
            esik=ayar.esik,
            ornekleme=ayar.ornekleme,
        )
        self.baslangic = ayar.baslangic or varsayilan_baslangic(ayar.sure_s, ayar.ornekleme.paket_s)
        self.bitis = self.baslangic + timedelta(seconds=ayar.sure_s)

        # Scenario timeline. Everything healthy up to `senaryo_baslangic`, then a
        # ramp of `senaryo_sure_s` to full strength.
        self.senaryo_baslangic = self.baslangic + timedelta(
            seconds=(
                ayar.senaryo_bas_s
                if ayar.senaryo_bas_s is not None
                else ayar.sure_s * ayar.senaryo_bas_orani
            )
        )
        self.senaryo_sure_s = (
            ayar.senaryo_sure_s
            if ayar.senaryo_sure_s is not None
            else max(ayar.sure_s * ayar.senaryo_sure_orani, float(ayar.ornekleme.paket_s))
        )

        self.moduller: list[Modul] = []
        self.senaryolar: list[Senaryo | None] = []
        for saha in self.sahalar:
            hava = PaylasilanHava(Hava(saha.hava, random.Random(saha.tohum ^ 0xC0FFEE)))
            for m_ayar in saha.modul_ayarlari:
                # One scenario instance per module: ArkOlay and friends keep
                # per-module state (which trips have fired, when), so sharing one
                # object across the fleet would let one module's arc suppress
                # another's.
                senaryo = senaryo_olustur(ayar.senaryo_ad) if ayar.senaryo_ad else None
                self.senaryolar.append(senaryo)
                self.moduller.append(
                    Modul(
                        m_ayar,
                        hava,  # type: ignore[arg-type]  # PaylasilanHava is the Hava interface Modul uses
                        baslangic=self.baslangic,
                        senaryo=senaryo,
                        senaryo_baslangic=self.senaryo_baslangic,
                        senaryo_sure_s=self.senaryo_sure_s,
                    )
                )

    # -- inspection -------------------------------------------------------

    @property
    def modul_idler(self) -> tuple[str, ...]:
        return tuple(m.modul_id for m in self.moduller)

    @property
    def tick_sayisi(self) -> int:
        """Number of clock steps, endpoints included."""
        return int(self.ayar.sure_s // self.ayar.ornekleme.paket_s) + 1

    # -- the run ----------------------------------------------------------

    def kosu(self, ozet: KosuOzeti | None = None) -> Iterator[UretilenPaket]:
        """Walk the clock and yield every packet, module order inside each tick.

        A generator on purpose: a 100-module, multi-day run is millions of
        packets, and the consumer (stdout, the ingest service, a test) should
        never need all of them in memory at once. Pass a `KosuOzeti` to have run
        statistics accumulated as a side effect.
        """
        if ozet is not None:
            ozet.modul_sayisi = len(self.moduller)
        adim = timedelta(seconds=self.ayar.ornekleme.paket_s)
        for i in range(self.tick_sayisi):
            an = self.baslangic + i * adim
            for modul in self.moduller:
                uretilen = modul.ilerle(an)
                if ozet is not None:
                    ozet.ekle(uretilen)
                yield uretilen

    def paketler(self, ozet: KosuOzeti | None = None) -> Iterator[dict]:
        """Same run, but only the wire packets — what stdout and ingest want."""
        for uretilen in self.kosu(ozet):
            yield uretilen.paket


def kosu_yap(ayar: KosuAyar, ozet: KosuOzeti | None = None) -> Iterator[dict]:
    """Convenience: build the fleet and stream its packets in one call."""
    return Filo(ayar).paketler(ozet)
