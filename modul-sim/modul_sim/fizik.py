"""Normal operation: weather, load, cabinet temperature, humidity.

This module is the reason the generated data is worth anything. A detector
trained against clean sinusoids proves nothing, so every quantity here carries
three layers:

1. a deterministic shape (season, day, week),
2. a slow random walk (weather fronts, demand shifting between feeders),
3. fast per-sample noise (the sensor itself).

Layer 2 is the important one. Without it every module's "normal" is identical
day to day, and any threshold works. With it, yesterday's normal is not exactly
today's normal — which is the actual problem an anomaly detector has to solve.

All state is driven by an explicitly seeded `random.Random`, so a run is
reproducible: same seed and same wall-clock window give byte-identical output.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime

from .ayar import HavaAyar, KabinAyar, YukAyar

GUN_S = 86400.0
YIL_GUN = 365.25


class YavasKayma:
    """Ornstein-Uhlenbeck random walk: drift that wanders but does not run away.

    A plain random walk would leave a 24 h run with a cabinet 15 °C off where it
    started. This one is mean-reverting, so it produces the thing we actually
    want — "today is a bit warmer than yesterday for no reason you can name" —
    without breaking the physical plausibility ranges the contract enforces.
    """

    def __init__(self, rng: random.Random, genlik: float, tau_s: float) -> None:
        self._rng = rng
        self._genlik = genlik
        self._tau = max(tau_s, 1.0)
        self.deger = rng.gauss(0.0, genlik * 0.5)

    def ilerle(self, dt_s: float) -> float:
        """Advance by `dt_s` seconds and return the new offset."""
        if dt_s <= 0:
            return self.deger
        bozunma = math.exp(-dt_s / self._tau)
        # Stationary variance is preserved, so the walk keeps the same spread
        # whatever step size the caller uses.
        sigma = self._genlik * math.sqrt(max(1.0 - bozunma * bozunma, 1e-9))
        self.deger = self.deger * bozunma + self._rng.gauss(0.0, sigma)
        return self.deger


def _gun_ici_saat(an: datetime) -> float:
    """Hour of day as a float, 0..24."""
    return an.hour + an.minute / 60.0 + an.second / 3600.0


def _yil_gunu(an: datetime) -> float:
    """Day of year as a float."""
    return an.timetuple().tm_yday + _gun_ici_saat(an) / 24.0


def doyma_basinci(sicaklik_c: float) -> float:
    """Saturation vapour pressure in hPa (Magnus form, valid -45..+60 °C)."""
    return 6.112 * math.exp(17.62 * sicaklik_c / (243.12 + sicaklik_c))


def ciy_noktasi(sicaklik_c: float, bagil_nem: float) -> float:
    """Dew point in °C from temperature and relative humidity.

    Scenario 4 is "condensation risk", and condensation is not a humidity
    number — it is the cabinet surface reaching the dew point. Computing it
    properly means the humidity scenario has a physical claim behind it instead
    of a bare threshold.
    """
    nem = min(max(bagil_nem, 0.5), 100.0)
    alfa = math.log(nem / 100.0) + 17.62 * sicaklik_c / (243.12 + sicaklik_c)
    return 243.12 * alfa / (17.62 - alfa)


def ic_bagil_nem(dis_sicaklik_c: float, dis_nem: float, ic_sicaklik_c: float) -> float:
    """Relative humidity inside the cabinet, from outside air warmed up.

    A cabinet is not sealed; the air in it is outside air at a higher
    temperature. Absolute moisture is conserved, so relative humidity falls as
    the box warms — which is why a cabinet that is *both* warm and damp is
    already interesting, and why a cold cabinet on a damp night is not.
    """
    oran = doyma_basinci(dis_sicaklik_c) / doyma_basinci(ic_sicaklik_c)
    return min(max(dis_nem * oran, 1.0), 100.0)


@dataclass
class HavaDurumu:
    """One weather sample at one site."""

    sicaklik_c: float
    bagil_nem: float


class Hava:
    """Outdoor weather for one site: seasonal + diurnal shape, drift, noise."""

    def __init__(self, ayar: HavaAyar, rng: random.Random) -> None:
        self.ayar = ayar
        self._rng = rng
        self._sicaklik_kayma = YavasKayma(rng, ayar.kayma_c, ayar.kayma_tau_s)
        self._nem_kayma = YavasKayma(rng, 6.0, ayar.kayma_tau_s * 1.3)

    def taban_sicaklik(self, an: datetime) -> float:
        """Deterministic part only — the shape without drift or noise."""
        a = self.ayar
        mevsim = a.yillik_genlik_c * math.cos(2 * math.pi * (_yil_gunu(an) - a.en_sicak_gun) / YIL_GUN)
        gunluk = a.gunluk_genlik_c * math.cos(2 * math.pi * (_gun_ici_saat(an) - a.en_sicak_saat) / 24.0)
        return a.yillik_ort_c + mevsim + gunluk

    def ilerle(self, an: datetime, dt_s: float) -> HavaDurumu:
        a = self.ayar
        sicaklik = self.taban_sicaklik(an) + self._sicaklik_kayma.ilerle(dt_s)
        sicaklik += self._rng.gauss(0.0, a.gurultu_c)
        # Humidity is anti-correlated with temperature over the day: the air
        # holds the same water, the warm hours just make it look drier.
        nem = a.taban_nem - a.nem_egim * (sicaklik - a.yillik_ort_c)
        nem += self._nem_kayma.ilerle(dt_s) + self._rng.gauss(0.0, 0.8)
        return HavaDurumu(sicaklik_c=sicaklik, bagil_nem=min(max(nem, 8.0), 99.0))


@dataclass
class YukDurumu:
    """One load sample for one module."""

    katsayi: float  # load as a fraction of the feeder rating
    akimlar: tuple[float, float, float]  # L1, L2, L3 in amperes
    notr: float  # neutral current in amperes


class Yuk:
    """Daily/weekly load profile and the three phase currents it produces."""

    def __init__(self, ayar: YukAyar, rng: random.Random) -> None:
        self.ayar = ayar
        self._rng = rng
        self._kayma = YavasKayma(rng, ayar.kayma_oran, ayar.kayma_tau_s)
        # Standing imbalance wanders slowly too — loads get switched between
        # phases during the day, which is exactly what scenario 3 must be told
        # apart from.
        self._faz_kayma = tuple(YavasKayma(rng, 0.012, 7200.0) for _ in range(3))

    def taban_katsayi(self, an: datetime) -> float:
        """Deterministic load factor: base + morning peak + evening peak."""
        a = self.ayar
        saniye = _gun_ici_saat(an) * 3600.0
        deger = a.taban_oran
        for merkez_saat, genlik, sigma in (
            (a.sabah_saat, a.sabah_genlik, a.sabah_sigma_s),
            (a.aksam_saat, a.aksam_genlik, a.aksam_sigma_s),
        ):
            fark = saniye - merkez_saat * 3600.0
            # Wrap around midnight so the evening peak does not get cut in half.
            fark = (fark + GUN_S / 2) % GUN_S - GUN_S / 2
            deger += genlik * math.exp(-0.5 * (fark / sigma) ** 2)
        if an.weekday() >= 5:
            deger *= a.haftasonu_kat
        return deger

    def ilerle(self, an: datetime, dt_s: float, olcek: float = 1.0) -> YukDurumu:
        """Advance the load. `olcek` is the scenario multiplier (overload)."""
        a = self.ayar
        katsayi = self.taban_katsayi(an) * (1.0 + self._kayma.ilerle(dt_s)) * olcek
        katsayi = max(katsayi, 0.02)

        akimlar = []
        for sapma, kayma in zip(a.faz_sapma, self._faz_kayma):
            faz = a.nominal_akim_a * katsayi * (sapma + kayma.ilerle(dt_s))
            faz *= 1.0 + self._rng.gauss(0.0, a.gurultu_oran)
            akimlar.append(max(faz, 0.0))
        l1, l2, l3 = akimlar
        return YukDurumu(katsayi=katsayi, akimlar=(l1, l2, l3), notr=self.notr_akimi(l1, l2, l3))

    def notr_akimi(self, l1: float, l2: float, l3: float) -> float:
        """Neutral current: phasor sum of the three phases plus zero sequence.

        The phasor sum alone would give a neutral near zero on a balanced
        board. Real LV boards carry 8-14 % of load current in the neutral even
        when balanced, because non-linear loads inject a third harmonic that
        adds arithmetically rather than cancelling. Leaving that out would make
        scenario 3 trivially detectable — any neutral current at all would mean
        imbalance.
        """
        a = self.ayar
        gercek = l1 - 0.5 * (l2 + l3)
        sanal = (math.sqrt(3) / 2.0) * (l3 - l2)
        temel = math.hypot(gercek, sanal)
        h3 = a.h3_oran * (l1 + l2 + l3) / 3.0
        return max(temel + h3 * (1.0 + self._rng.gauss(0.0, 0.05)), 0.0)


class Kabin:
    """Cabinet air temperature: outdoor air plus load heating, through a lag.

    The lag is the whole point. Copper losses follow I² instantly, but the air
    in a steel box takes ten to twenty minutes to catch up, so cabinet
    temperature lags the evening peak. A correlation detector that assumes
    instantaneous coupling will mis-fire on that lag — which is exactly the
    thing the generated data should make it prove it handles.
    """

    def __init__(self, ayar: KabinAyar, rng: random.Random, baslangic_c: float) -> None:
        self.ayar = ayar
        self._rng = rng
        self.sicaklik_c = baslangic_c

    def ilerle(self, dis_sicaklik_c: float, yuk_katsayisi: float, dt_s: float, ek_c: float = 0.0) -> float:
        a = self.ayar
        hedef = dis_sicaklik_c + a.tam_yuk_artis_c * (yuk_katsayisi**2) + ek_c
        agirlik = 1.0 - math.exp(-max(dt_s, 0.0) / a.tau_s)
        self.sicaklik_c += (hedef - self.sicaklik_c) * agirlik
        return self.sicaklik_c + self._rng.gauss(0.0, a.gurultu_c)
