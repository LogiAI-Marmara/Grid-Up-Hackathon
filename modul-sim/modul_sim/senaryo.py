"""The seven fault scenarios of section 7.6.

A scenario is a *perturbation*, not a data source: it receives the context the
module was about to report and pushes on it. Everything else — noise, drift,
the daily load shape, the thermal lag — keeps running underneath. That is
deliberate. A scenario implemented as "emit these values" would be detectable
by construction; a scenario implemented as "add resistance to terminal 2" has
to fight the same noise floor the detector does.

Each scenario declares `belirti` (the discriminating signal it produces) and
`beklenen_tip` (the `tip` value track B should end up raising for it). Those two
lines are the contract between track A and track B: if a detector fires on a
different `tip`, one of us is wrong, and it is visible without reading the code.

Scenarios ramp. A fault that appears at full strength in one sample is a step
change, and step changes are the easy case; a loose terminal takes hours.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime

from .sozlesme import Besleme, Kalite, OlcumTipi, Tip


@dataclass
class Baglam:
    """Mutable per-tick context. Scenarios modify it; the module then reports it.

    The module fills in the world as it would be with nothing wrong, calls
    `Senaryo.uygula`, and builds the packet from whatever comes back.
    """

    an: datetime  # true simulation time (not the module's own clock)
    dt_s: float  # seconds since the previous tick
    gecen_s: float  # seconds since the scenario started; negative before it does
    oran: float  # scenario progress, 0.0 before the start, ramping to 1.0

    dis_sicaklik_c: float
    dis_nem: float

    #: Load multiplier applied before the currents are computed (scenario 2).
    yuk_olcek: float = 1.0
    #: Per-phase multipliers applied on top of the standing imbalance (scenario 3).
    faz_olcek: tuple[float, float, float] = (1.0, 1.0, 1.0)
    #: Extra heat pushed into the cabinet air target, °C.
    kabin_ek_c: float = 0.0
    #: Extra relative humidity points inside the cabinet (scenario 4).
    nem_ek: float = 0.0

    #: Extra °C on individual terminals (scenario 1). Sized by the module.
    klemens_ek_c: list[float] = field(default_factory=list)
    #: Extra °C across the whole frame (scenario 5's flash).
    termal_genel_ek_c: float = 0.0

    #: Arc trips that fired on this tick. The module adds them to its counter.
    ark_tetik: int = 0

    besleme: Besleme = Besleme.SEBEKE
    sinyal_ek_dbm: float = 0.0
    saat_ek_s: float = 0.0
    #: True once the module is running on the supercapacitor and shedding load:
    #: heartbeat packets only, no measurements. `olcumler` may legally be empty.
    dusuk_guc: bool = False

    #: Quality overrides and sensor misbehaviour, keyed by measurement type.
    kalite_zorla: dict[OlcumTipi, Kalite] = field(default_factory=dict)
    dondur: set[OlcumTipi] = field(default_factory=set)  # repeat the last value
    sapit: set[OlcumTipi] = field(default_factory=set)  # emit nonsense
    dusur: set[OlcumTipi] = field(default_factory=set)  # no reading at all


class Senaryo:
    """Base class. `ad` is the CLI name and must match the decision record."""

    ad: str = ""
    baslik: str = ""
    belirti: str = ""
    beklenen_tip: tuple[Tip, ...] = ()

    def uygula(self, b: Baglam, rng: random.Random) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Senaryo {self.ad}>"


# ---------------------------------------------------------------------------
# 1 — loose terminal
# ---------------------------------------------------------------------------


class GevsekKlemens(Senaryo):
    """Contact resistance grows at one terminal. Current does not change.

    The heat is I²R, and I is on its normal daily curve, so the rise is not
    monotonic in wall-clock time — it breathes with the load. What does change
    monotonically is the ratio: degrees per ampere at that one pixel. That is
    the signal, and it is why this scenario is the project's central claim.
    """

    ad = "gevsek_klemens"
    baslik = "Loose terminal"
    belirti = (
        "termal_maks rises while akim_l* stay on their normal profile; maks_konum "
        "stays pinned to one pixel; the other terminals do not move"
    )
    beklenen_tip = (Tip.SICAK_NOKTA, Tip.AKIM_SICAKLIK_SAPMASI)

    def __init__(self, hedef_klemens: int = 2, son_artis_c: float = 46.0) -> None:
        self.hedef_klemens = hedef_klemens
        self.son_artis_c = son_artis_c

    def uygula(self, b: Baglam, rng: random.Random) -> None:
        if b.oran <= 0 or not b.klemens_ek_c:
            return
        sira = self.hedef_klemens % len(b.klemens_ek_c)
        # Resistance degradation accelerates: the hotter the joint, the faster
        # it oxidises. An exponent above 1 is the difference between "a ramp"
        # and "a runaway you should have caught early".
        artis = self.son_artis_c * (b.oran**1.7)
        b.klemens_ek_c[sira] += artis * (1.0 + rng.gauss(0.0, 0.02))
        # A hot joint warms the air around it a little, but only a little —
        # if the cabinet followed it one-for-one there would be nothing to
        # distinguish this from an overload.
        b.kabin_ek_c += 0.05 * artis


# ---------------------------------------------------------------------------
# 2 — overload heating
# ---------------------------------------------------------------------------


class AsiriYuk(Senaryo):
    """Demand climbs past the feeder rating; everything warms together."""

    ad = "asiri_yuk"
    baslik = "Overload heating"
    belirti = (
        "all three phase currents rise past nominal together, the cabinet and the "
        "whole thermal field follow with the cabinet's thermal lag; the terminal "
        "spread is unchanged"
    )
    beklenen_tip = (Tip.ASIRI_YUK, Tip.ORTAM_SICAKLIK_YUKSEK)

    def __init__(self, son_olcek: float = 1.9) -> None:
        self.son_olcek = son_olcek

    def uygula(self, b: Baglam, rng: random.Random) -> None:
        if b.oran <= 0:
            return
        b.yuk_olcek *= 1.0 + (self.son_olcek - 1.0) * b.oran
        # Ventilation cannot keep up once the board is over its rating: the
        # cabinet runs hotter than I² alone would predict.
        b.kabin_ek_c += 5.0 * b.oran


# ---------------------------------------------------------------------------
# 3 — phase imbalance
# ---------------------------------------------------------------------------


class FazDengesizlik(Senaryo):
    """Load migrates onto L1 and off L3; the neutral carries the difference."""

    ad = "faz_dengesizlik"
    baslik = "Phase imbalance"
    belirti = (
        "the L1/L3 spread grows well past the standing few percent and akim_notr "
        "rises far above its third-harmonic baseline; total load barely changes"
    )
    beklenen_tip = (Tip.FAZ_DENGESIZLIGI,)

    def __init__(self, son_sapma: float = 0.34) -> None:
        self.son_sapma = son_sapma

    def uygula(self, b: Baglam, rng: random.Random) -> None:
        if b.oran <= 0:
            return
        sapma = self.son_sapma * b.oran
        b.faz_olcek = (
            b.faz_olcek[0] * (1.0 + sapma),
            b.faz_olcek[1] * (1.0 - 0.05 * sapma),
            b.faz_olcek[2] * (1.0 - sapma),
        )
        # The overloaded phase heats its own terminals; imbalance is a thermal
        # problem too, not only a current one.
        if b.klemens_ek_c:
            b.klemens_ek_c[0] += 6.0 * sapma
            b.klemens_ek_c[1 % len(b.klemens_ek_c)] += 4.0 * sapma


# ---------------------------------------------------------------------------
# 4 — humidity rise
# ---------------------------------------------------------------------------


class NemYuksek(Senaryo):
    """Water gets in and the cabinet heater does not answer.

    The cabinet cooling toward the dew point matters as much as the humidity
    number: condensation is a surface reaching the dew point, not a percentage.
    """

    ad = "nem_yuksek"
    baslik = "Humidity rise / condensation risk"
    belirti = (
        "nem climbs to 90 %+ and stays there while the cabinet cools toward the "
        "dew point; kalite stays 'iyi', which is what separates this from a "
        "failed humidity sensor"
    )
    beklenen_tip = (Tip.NEM_YUKSEK,)

    def __init__(self, son_nem_ek: float = 34.0) -> None:
        self.son_nem_ek = son_nem_ek

    def uygula(self, b: Baglam, rng: random.Random) -> None:
        if b.oran <= 0:
            return
        b.nem_ek += self.son_nem_ek * b.oran * (1.0 + rng.gauss(0.0, 0.03))
        # A wet cabinet is also a cold one: the seal is open to the night air.
        b.kabin_ek_c -= 4.5 * b.oran


# ---------------------------------------------------------------------------
# 5 — arc event
# ---------------------------------------------------------------------------


class ArkOlay(Senaryo):
    """TVOC-2 trips. We record the event; detecting the arc is the device's job.

    The aftermath is as characteristic as the event: the breaker opens, so the
    current collapses to near zero, and the flash leaves the frame hot for a
    minute or so.
    """

    ad = "ark_olay"
    baslik = "Arc event (TVOC-2 trip)"
    belirti = (
        "an ark_olay row appears with the trip counter incremented, the thermal "
        "frame spikes tens of degrees for about a minute, and the phase currents "
        "collapse as the breaker opens"
    )
    beklenen_tip = (Tip.ARK,)

    #: Trip points as a fraction of the scenario ramp.
    TETIKLER = (0.45, 0.78)

    def __init__(self, parlama_c: float = 58.0, bozunma_tau_s: float = 35.0) -> None:
        self.parlama_c = parlama_c
        self.bozunma_tau_s = bozunma_tau_s
        self._atilan: set[float] = set()
        self._son_trip_s: float | None = None

    def uygula(self, b: Baglam, rng: random.Random) -> None:
        if b.oran <= 0:
            return
        for tetik in self.TETIKLER:
            if b.oran >= tetik and tetik not in self._atilan:
                self._atilan.add(tetik)
                b.ark_tetik += 1
                self._son_trip_s = b.gecen_s
        if self._son_trip_s is None:
            return
        gecen = max(b.gecen_s - self._son_trip_s, 0.0)
        b.termal_genel_ek_c += self.parlama_c * math.exp(-gecen / self.bozunma_tau_s)
        if b.klemens_ek_c:
            b.klemens_ek_c[0] += 0.5 * self.parlama_c * math.exp(-gecen / self.bozunma_tau_s)
        # Breaker open: load gone. It comes back only if someone re-closes it,
        # which nobody does inside a simulation run.
        b.yuk_olcek *= 0.04 + 0.96 * math.exp(-gecen / 4.0)


# ---------------------------------------------------------------------------
# 6 — sensor failure
# ---------------------------------------------------------------------------


class SensorAriza(Senaryo):
    """The combined temperature/humidity sensor dies in three stages.

    Freeze, then nonsense, then nothing. Both channels go together because on
    the real module they are one chip on one I²C bus — a failure that takes out
    only humidity and leaves temperature perfect is not a failure mode, it is a
    convenience.

    `kalite` is the whole point of this scenario: without it a frozen 24.3 °C
    is indistinguishable from a cabinet that happens to be stable.
    """

    ad = "sensor_ariza"
    baslik = "Sensor failure"
    belirti = (
        "ortam_sicaklik and nem first freeze at one value (kalite 'supheli'), then "
        "jump implausibly, then stop being reported at all (deger null, kalite "
        "'yok') — while the thermal array and the currents stay healthy"
    )
    beklenen_tip = (Tip.SENSOR_ARIZASI,)

    KANALLAR = (OlcumTipi.ORTAM_SICAKLIK, OlcumTipi.NEM)

    def uygula(self, b: Baglam, rng: random.Random) -> None:
        if b.oran <= 0:
            return
        if b.oran < 0.35:
            for kanal in self.KANALLAR:
                b.dondur.add(kanal)
                b.kalite_zorla[kanal] = Kalite.SUPHELI
        elif b.oran < 0.72:
            for kanal in self.KANALLAR:
                b.sapit.add(kanal)
                b.kalite_zorla[kanal] = Kalite.SUPHELI
        else:
            for kanal in self.KANALLAR:
                b.dusur.add(kanal)
                b.kalite_zorla[kanal] = Kalite.YOK


# ---------------------------------------------------------------------------
# 7 — module health
# ---------------------------------------------------------------------------


class ModulSaglik(Senaryo):
    """The module itself is in trouble: mains lost, radio fading, clock drifting.

    This is the "we do not die silently" claim. The backup store exists so that
    the packet saying *why* the module is about to go quiet gets out.
    """

    ad = "modul_saglik"
    baslik = "Module health degradation"
    belirti = (
        "modul_durum.besleme flips to 'yedek', sinyal fades by ~30 dBm, and the "
        "module clock runs away from real time so alindi_zaman - zaman grows to "
        "around a minute; near the end only heartbeat packets are sent"
    )
    beklenen_tip = (Tip.MODUL_SAGLIK,)

    def __init__(
        self,
        besleme_kaybi_orani: float = 0.45,
        sinyal_kaybi_dbm: float = 30.0,
        son_saat_kaymasi_s: float = 58.0,
    ) -> None:
        self.besleme_kaybi_orani = besleme_kaybi_orani
        self.sinyal_kaybi_dbm = sinyal_kaybi_dbm
        self.son_saat_kaymasi_s = son_saat_kaymasi_s

    def uygula(self, b: Baglam, rng: random.Random) -> None:
        if b.oran <= 0:
            return
        # The radio starts fading before anything else: an antenna connection
        # working loose is the early warning, the power loss is the event.
        b.sinyal_ek_dbm -= self.sinyal_kaybi_dbm * b.oran
        # A drifting RTC usually means a failing oscillator or a browning-out
        # supply, so the drift accelerates rather than staying linear.
        b.saat_ek_s += self.son_saat_kaymasi_s * (b.oran**1.4)
        if b.oran >= self.besleme_kaybi_orani:
            b.besleme = Besleme.YEDEK
            # On the supercapacitor the thermal array and the radio cannot both
            # be afforded, so the module sheds everything except the heartbeat
            # that says it is dying.
            if b.oran >= 0.85:
                b.dusuk_guc = True


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

#: CLI name -> factory. The keys are the seven scenarios of section 7.6; a track
#: owner may not add an eighth without the lead's approval.
SENARYOLAR: dict[str, type[Senaryo]] = {
    s.ad: s
    for s in (
        GevsekKlemens,
        AsiriYuk,
        FazDengesizlik,
        NemYuksek,
        ArkOlay,
        SensorAriza,
        ModulSaglik,
    )
}


def senaryo_olustur(ad: str) -> Senaryo:
    """Instantiate a scenario by its CLI name."""
    try:
        sinif = SENARYOLAR[ad]
    except KeyError:
        raise ValueError(f"unknown scenario {ad!r}; known: {', '.join(sorted(SENARYOLAR))}") from None
    return sinif()
