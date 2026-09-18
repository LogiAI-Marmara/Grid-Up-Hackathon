"""Configuration objects and the fleet topology builder.

Every number the simulator uses is here, with the reason it has that value. Two
kinds of setting live side by side and should not be confused:

* **Physical parameters** (rated feeder current, thermal time constant, weather)
  describe the world. Changing them changes what "normal" looks like.
* **Module settings** (`EsikAyar`, `OrneklemeAyar`) describe the firmware.
  They are the counterpart of "send a setting from the centre to the module"
  in section 7.4 of the decision record: cadence and policy are things the
  operator owns, not constants.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from .sozlesme import TERMAL_SATIR, TERMAL_SUTUN

# ---------------------------------------------------------------------------
# Module firmware settings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EsikAyar:
    """On-board threshold policy — **not evaluated since the integration decision.**

    Section 7.4 of the decision record gated the 768-value frame behind this
    logic: summary only in normal traffic, frame when a trigger fired. The
    integration decision of 17 Sep (item 2) made the frame unconditional on
    every 30 s cycle, so `Modul.ilerle` no longer consults these values. The
    dataclass is kept as the configuration slot and the documented policy, so
    that re-enabling the gate is a change in one place. The original design:
    three independent triggers, because a hot spot is not always hot in
    absolute terms:

    * `maks_c` — absolute hot-pixel temperature.
    * `delta_c` — hot pixel minus frame mean. A 55 °C spot in a 25 °C cabinet is
      a fault; a 55 °C spot in a 50 °C cabinet on a hot August afternoon is the
      whole board being warm, and only the delta separates the two.
    * `kabin_delta_c` — hot pixel minus cabinet ambient, the cheap on-board
      stand-in for the current/temperature correlation the centre computes.

    `min_aralik_s` rate-limits frames so a module in a sustained fault does not
    spend its uplink retransmitting 768 values every cycle.
    """

    maks_c: float = 65.0
    delta_c: float = 14.0
    kabin_delta_c: float = 22.0
    min_aralik_s: int = 60
    #: Always attach a frame on an arc trip, whatever the temperatures say —
    #: that is the one packet the operator will certainly want to look at.
    ark_kare: bool = True


@dataclass(frozen=True)
class OrneklemeAyar:
    """Sampling periods, seconds. Section 7.2 of the decision record, as
    amended by the integration decision of 17 Sep (item 2): packet cadence and
    thermal frame generation are aligned at 30 seconds, and the frame goes in
    every packet. The sensor reads faster (termal_okuma_s) and averages
    sub-samples into one frame to lower temporal noise. Track A document 7
    section 7.2 is the table form of these values.
    """

    paket_s: int = 30  # packet period; also the current-averaging window
    akim_okuma_s: int = 2  # sub-samples averaged into one recorded value
    termal_okuma_s: int = 6  # sensor reads faster (5 sub-samples) and averages to reduce noise
    termal_s: int = 30  # thermal summary and frame: 30 s
    cevre_s: int = 60  # ambient temperature and humidity: 30-60 s
    # Arc is event-driven; there is no period for it.


# ---------------------------------------------------------------------------
# The physical world
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HavaAyar:
    """Outdoor weather at one site. Shared by every module in that site.

    Weather being per-site and not per-module is what makes track B's
    "compare a module against its neighbours" test meaningful: two modules in
    the same building see the same outdoor temperature, so a divergence between
    them is the cabinet, not the day.
    """

    yillik_ort_c: float = 16.5  # annual mean, inland Aegean
    yillik_genlik_c: float = 11.0  # seasonal swing, peak-to-mean
    en_sicak_gun: int = 205  # day of year of the seasonal peak (late July)
    gunluk_genlik_c: float = 6.5  # diurnal swing, peak-to-mean
    en_sicak_saat: float = 15.0  # hour of the daily peak, UTC-based sim clock
    taban_nem: float = 58.0  # relative humidity at the annual mean temperature
    nem_egim: float = 1.7  # %RH lost per °C above that mean
    gurultu_c: float = 0.25  # per-sample measurement noise
    kayma_c: float = 1.8  # amplitude of the slow weather random walk
    kayma_tau_s: float = 5400.0  # its time constant


@dataclass(frozen=True)
class YukAyar:
    """Daily and weekly load shape for one feeder.

    Two Gaussian peaks on a base load: a smaller morning one and the real
    evening peak. This is a distribution feeder, not an industrial one, which
    is why the evening peak dominates.
    """

    nominal_akim_a: float = 400.0  # feeder rating; per-module, see `pano_akim`
    taban_oran: float = 0.34  # night floor as a fraction of nominal
    sabah_saat: float = 8.5
    sabah_genlik: float = 0.26
    sabah_sigma_s: float = 1.9 * 3600
    aksam_saat: float = 19.5
    aksam_genlik: float = 0.45
    aksam_sigma_s: float = 2.4 * 3600
    haftasonu_kat: float = 0.86
    gurultu_oran: float = 0.015  # fast noise on every reading
    kayma_oran: float = 0.05  # slow random walk in demand
    kayma_tau_s: float = 3600.0
    #: Standing phase imbalance. No real board is balanced; a detector tuned on
    #: perfectly balanced synthetic data would fire on every real one.
    faz_sapma: tuple[float, float, float] = (1.025, 0.992, 0.983)
    #: Third-harmonic zero-sequence share. Non-linear loads put current in the
    #: neutral even when the phases are balanced — roughly 8-14 % in an LV board.
    h3_oran: float = 0.10


@dataclass(frozen=True)
class KabinAyar:
    """Cabinet thermal behaviour: how the box follows the weather and the load."""

    tam_yuk_artis_c: float = 21.0  # cabinet-over-outdoor rise at rated current
    tau_s: float = 900.0  # first-order lag; heat in a cabinet moves slowly
    gurultu_c: float = 0.18


@dataclass(frozen=True)
class TermalAyar:
    """32x24 array model: what the sensor sees when nothing is wrong.

    The frame is built as background + terminal blobs, which is also how a real
    one looks: a warm busbar band, a convection gradient, and a row of
    connection points that run hotter than the metal around them.
    """

    sutun: int = TERMAL_SUTUN
    satir: int = TERMAL_SATIR
    #: Terminal row and columns. The contract's example hot pixel is [14, 9],
    #: so the terminal row sits at 9 and the columns straddle 14.
    klemens_satir: int = 9
    klemens_sutunlar: tuple[int, ...] = (3, 8, 14, 19, 24, 29)
    klemens_sigma: float = 1.7  # blob width in pixels
    klemens_tam_yuk_c: float = 7.5  # terminal rise over ambient at rated load
    klemens_dagilim: float = 0.18  # +/- spread between terminals, per module
    bara_bant_c: float = 3.2  # busbar band warmth at rated load
    bara_sigma: float = 4.5  # its vertical extent in pixels
    egim_c: float = 2.4  # top-of-frame convection gradient
    fpn_c: float = 0.35  # fixed pattern noise, per pixel, constant per sensor
    gurultu_c: float = 0.22  # per-frame temporal noise, per pixel
    havuz_boyu: int = 4096  # pre-drawn noise pool, see termal.py


@dataclass(frozen=True)
class SaglikAyar:
    """Module health baseline: what `modul_durum` looks like when all is well."""

    yazilim_surumu: str = "1.0.3"
    sinyal_dbm: int = -72
    sinyal_salinim: float = 3.0  # dBm, slow wander
    #: Free-running module clock. Even a healthy module drifts a little; the
    #: collector sees it as the gap between `zaman` and `alindi_zaman`.
    saat_kayma_ppm: float = 12.0


# ---------------------------------------------------------------------------
# Fleet
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModulAyar:
    """Everything one simulated module needs, including its identity."""

    modul_id: str
    saha_kodu: str
    pano_kodu: str
    modul_kodu: str
    tohum: int
    yuk: YukAyar = field(default_factory=YukAyar)
    kabin: KabinAyar = field(default_factory=KabinAyar)
    termal: TermalAyar = field(default_factory=TermalAyar)
    saglik: SaglikAyar = field(default_factory=SaglikAyar)
    esik: EsikAyar = field(default_factory=EsikAyar)
    ornekleme: OrneklemeAyar = field(default_factory=OrneklemeAyar)


@dataclass(frozen=True)
class SahaAyar:
    """A site: shared weather plus the modules installed in it."""

    saha_kodu: str
    tohum: int
    hava: HavaAyar
    modul_ayarlari: tuple[ModulAyar, ...]


#: Site codes for generated topologies. TR041 is the decision record's example.
SAHA_KODLARI = tuple(f"TR{41 + i:03d}" for i in range(64))

#: Feeder ratings cycled over the panels. A 1600 kVA board feeds outgoing ways
#: of different sizes; giving every module the same rating would make the
#: fleet-wide "normal" suspiciously uniform.
PANO_AKIM_A = (250.0, 400.0, 630.0, 400.0, 315.0)


def _tohum(kok: int, metin: str) -> int:
    """Stable per-module seed: same id and same root seed give the same module.

    `hash()` is salted per process in Python 3, so it cannot be used here — a
    run would stop being reproducible across invocations.
    """
    deger = kok & 0xFFFFFFFF
    for harf in metin:
        deger = (deger * 1_000_003 + ord(harf)) & 0xFFFFFFFF
    return deger


def topoloji(
    modul_sayisi: int,
    tohum: int = 20260914,
    *,
    esik: EsikAyar | None = None,
    ornekleme: OrneklemeAyar | None = None,
    modul_basina_pano: int = 2,
) -> tuple[SahaAyar, ...]:
    """Build `modul_sayisi` modules laid out as sites -> panels -> modules.

    The shape follows section 7.7: the demo fleet is about three sites with two
    panels each and one or two modules per panel, and the load test is 100
    modules spread over several sites rather than 100 modules in one building.
    Panels per site therefore grows with the fleet while sites stay countable:

        9 modules   -> 3 sites x up to 2 panels x up to 2 modules
        100 modules -> 10 sites x 5 panels x 2 modules

    Deterministic: same arguments, same fleet, every time.
    """
    if modul_sayisi < 1:
        raise ValueError("modul_sayisi must be at least 1")

    pano_sayisi = math.ceil(modul_sayisi / modul_basina_pano)
    # Keep sites <= 10 for big fleets, and 2 panels per site for small ones.
    pano_basina_saha = 2 if pano_sayisi <= 6 else math.ceil(pano_sayisi / 10)
    saha_sayisi = math.ceil(pano_sayisi / pano_basina_saha)
    if saha_sayisi > len(SAHA_KODLARI):
        raise ValueError(f"fleet too large: needs {saha_sayisi} sites, {len(SAHA_KODLARI)} codes defined")

    kalan = modul_sayisi
    sahalar: list[SahaAyar] = []
    for saha_no in range(saha_sayisi):
        if kalan <= 0:
            break
        saha_kodu = SAHA_KODLARI[saha_no]
        saha_tohum = _tohum(tohum, saha_kodu)
        # Sites differ: a coastal site is damper, an inland one swings harder.
        hava = replace(
            HavaAyar(),
            yillik_ort_c=HavaAyar().yillik_ort_c + ((saha_tohum % 7) - 3) * 0.8,
            taban_nem=HavaAyar().taban_nem + ((saha_tohum // 7) % 9) - 4,
            gunluk_genlik_c=HavaAyar().gunluk_genlik_c + ((saha_tohum // 63) % 5) * 0.4,
        )
        modul_ayarlari: list[ModulAyar] = []
        for pano_no in range(pano_basina_saha):
            if kalan <= 0:
                break
            pano_kodu = f"P{pano_no + 1:02d}"
            nominal = PANO_AKIM_A[(saha_no + pano_no) % len(PANO_AKIM_A)]
            for modul_no in range(modul_basina_pano):
                if kalan <= 0:
                    break
                modul_kodu = f"M{modul_no + 1}"
                modul_id = f"{saha_kodu}-{pano_kodu}-{modul_kodu}"
                m_tohum = _tohum(tohum, modul_id)
                modul_ayarlari.append(
                    ModulAyar(
                        modul_id=modul_id,
                        saha_kodu=saha_kodu,
                        pano_kodu=pano_kodu,
                        modul_kodu=modul_kodu,
                        tohum=m_tohum,
                        yuk=replace(
                            YukAyar(),
                            nominal_akim_a=nominal,
                            # A second module on the same panel watches a
                            # different section, so it sees a different mix.
                            taban_oran=YukAyar().taban_oran + ((m_tohum % 11) - 5) * 0.012,
                            aksam_genlik=YukAyar().aksam_genlik + ((m_tohum // 11) % 9 - 4) * 0.015,
                            h3_oran=YukAyar().h3_oran + ((m_tohum // 99) % 7 - 3) * 0.012,
                        ),
                        saglik=replace(
                            SaglikAyar(),
                            sinyal_dbm=SaglikAyar().sinyal_dbm - (m_tohum % 17),
                            saat_kayma_ppm=SaglikAyar().saat_kayma_ppm * (0.4 + (m_tohum % 23) / 23.0),
                        ),
                        esik=esik or EsikAyar(),
                        ornekleme=ornekleme or OrneklemeAyar(),
                    )
                )
                kalan -= 1
        sahalar.append(
            SahaAyar(
                saha_kodu=saha_kodu,
                tohum=saha_tohum,
                hava=hava,
                modul_ayarlari=tuple(modul_ayarlari),
            )
        )
    return tuple(sahalar)


def modul_ayarlari(sahalar: tuple[SahaAyar, ...]) -> tuple[ModulAyar, ...]:
    """Flatten a topology into module order, which is also packet order."""
    return tuple(m for saha in sahalar for m in saha.modul_ayarlari)
