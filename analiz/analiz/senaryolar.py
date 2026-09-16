"""The labelled development set: the seven fault scenarios, and the hard cases.

Section 7.6 of the parent decision record fixes the seven scenarios, and no
single track may add to the list. They are reproduced here as data the detector
can be run against:

    1  gevsek klemens       slow single-point heating, current steady
    2  asiri yuk isinmasi   high current, general temperature rise
    3  faz dengesizligi     difference between phases, neutral current up
    4  nem yukselmesi       humidity threshold, condensation risk
    5  ark olayi            TVOC-2 trip record
    6  sensor arizasi       the measurement freezes or talks nonsense
    7  modul sagligi        silence, clock drift, power loss, weak signal

Scenarios 6 and 7 are not grid faults — they are the system's own health, and
section 7.6 is explicit that they are there so we can claim the system does not
die quietly.

WHAT THE SET IS FOR, AND WHAT IT IS NOT. This is the labelled set of section
2.7: the answer key is right here in the file, so it is a development and
regression set, not evidence. Evidence is the blind set of section 4.4, which
track A generates from a seed it does not share, and which only counts once. The
danger of a labelled set is exactly that it gets tuned against — "I missed
scenario 3, let me lower a threshold" — until the detector fits this file
instead of fitting reality.

Two properties keep it honest even so, and they are the two traps section 4.4
asks track A to avoid:

  - CLEAN MODULES. Five of them, faulty in no way. Without them a detector that
    alarms on everything scores a perfect detection rate, and the false-alarm
    rate — the metric that decides whether a monitoring system survives its first
    month in the field — cannot be computed at all.
  - HARD NEGATIVES. Modules that are noisy but healthy, and a whole site warming
    up together on a hot afternoon. These are the cases a threshold detector gets
    wrong, and they are here to be got right.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .etiket import EtiketDosyasi, EtiketSenaryosu, SURUM
from .fikstur import Fikstur
from .sozlesme import Besleme, Kalite, OlcumTipi, Tip

__all__ = [
    "Senaryo",
    "SENARYOLAR",
    "kur",
    "beklenen_tipler",
    "temiz_moduller",
    "etiket_uret",
    "SESSIZ_DAKIKA",
    "TESPIT_SAAT",
]


@dataclass(frozen=True, slots=True)
class Senaryo:
    """One labelled module: what was injected, and what should come out.

    `beklenen` is the answer key. A scenario whose `beklenen` is empty is a clean
    or hard-negative module and the correct output is *no episode at all* — those
    entries are the ones that make the set worth running.
    """

    modul_id: str
    ad: str
    aciklama: str
    beklenen: frozenset[Tip] = frozenset()
    #: Types that must NOT be produced. A sensor failure reported as a
    #: temperature anomaly is the specific mistake section 5 puts layer 0 there
    #: to prevent, so it is asserted directly rather than hoped for.
    yasak: frozenset[Tip] = frozenset()

    # -- ground truth, for the label file -----------------------------------
    #
    # These three describe the injection in the vocabulary of `etiket.py`, so
    # this set can emit a label file in exactly the format track A's blind sets
    # will use. They describe *when* the injection happened; they do not change
    # what is injected, so the signals the detector sees are untouched.

    #: Which of the seven scenarios of section 7.6 this is. Empty for a clean or
    #: hard-negative module.
    senaryo: str = ""

    #: Where in the injection ramp the fault begins, as a fraction. 0.0 is the
    #: start of the detection stretch. 1.0 for a fault that is instantaneous at
    #: the end of it, such as a module going dark.
    baslangic_oran: float = 0.0

    #: Where in the ramp the fault reaches its critical state, as a fraction.
    #:
    #: `None` for a fault that does not escalate: a frozen sensor is exactly as
    #: broken on the first sample as on the last, and inventing a critical moment
    #: for it would invent a lead time too. A scenario with no critical moment
    #: contributes to the detection rate and not to lead time, which is correct —
    #: there was no deadline to beat.
    kritik_oran: float | None = None


# --------------------------------------------------------------------------
# Signal generation
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Profil:
    """A healthy module's normal behaviour. Everything else is a deviation from it."""

    ortam_taban: float = 30.0
    ortam_genlik: float = 3.0
    nem_taban: float = 45.0
    nem_genlik: float = 6.0
    akim_taban: float = 300.0
    akim_genlik: float = 45.0
    termal_fark: float = 18.0
    gurultu: float = 0.35
    #: Rows this dense in the detection window, and this sparse in the baseline.
    sik_sn: float = 60.0
    seyrek_sn: float = 600.0


def _gunun_saati(an: datetime) -> float:
    return an.hour + an.minute / 60.0 + an.second / 3600.0


def _ortam(an: datetime, p: Profil, rng: random.Random) -> float:
    """Daily ambient swing, peaking mid-afternoon."""
    faz = 2 * math.pi * (_gunun_saati(an) - 15.0) / 24.0
    return p.ortam_taban + p.ortam_genlik * math.cos(faz) + rng.gauss(0, p.gurultu)


def _nem(an: datetime, p: Profil, rng: random.Random) -> float:
    """Humidity runs opposite the temperature — warm air holds more water."""
    faz = 2 * math.pi * (_gunun_saati(an) - 15.0) / 24.0
    return max(5.0, p.nem_taban - p.nem_genlik * math.cos(faz) + rng.gauss(0, p.gurultu))


def _akim(an: datetime, p: Profil, rng: random.Random) -> float:
    """Daily load profile, peaking early evening."""
    faz = 2 * math.pi * (_gunun_saati(an) - 19.0) / 24.0
    return max(1.0, p.akim_taban + p.akim_genlik * math.cos(faz) + rng.gauss(0, p.gurultu * 3))


def _termal(ortam: float, akim: float, p: Profil, rng: random.Random) -> float:
    """Hot spot: ambient, plus the joint's own rise, plus a little from the load."""
    return ortam + p.termal_fark + 0.01 * (akim - p.akim_taban) + rng.gauss(0, p.gurultu)


@dataclass
class Uretec:
    """Writes one module's history, with an optional fault laid over the end.

    `bozucu` is called for every sample in the detection window and may modify
    the measurement dictionary in place. Keeping the fault separate from the
    healthy signal means the same normal behaviour underlies every scenario, so
    a detector that fires is reacting to the injection and not to a scenario
    having been generated differently.
    """

    fikstur: Fikstur
    simdi: datetime
    profil: Profil = field(default_factory=Profil)
    tohum: int = 0

    def uret(
        self,
        modul_id: str,
        *,
        gecmis_gun: float = 15.0,
        tespit_saat: float = 7.0,
        bozucu=None,
        sessiz_dakika: float = 0.0,
        gecikme_sn: float = 2.0,
        termal_kare: bool = False,
    ) -> None:
        """Write a full history for one module.

        Two cadences: sparse over the fortnight the baseline is computed from,
        dense over the last few hours the detection window covers. Real modules
        do report at one rate, but a fortnight of 10-second samples is ~120k rows
        per channel per module and the fixture would take longer to write than
        the detector takes to run — the statistics come out the same either way.
        """
        rng = random.Random(f"{modul_id}:{self.tohum}")
        p = self.profil
        self.fikstur.modul(modul_id)

        son = self.simdi - timedelta(minutes=sessiz_dakika)
        tespit_bas = son - timedelta(hours=tespit_saat)
        gecmis_bas = self.simdi - timedelta(days=gecmis_gun)

        # --- baseline stretch: sparse, and only the channels that get a baseline
        an = gecmis_bas
        while an < tespit_bas:
            ortam = _ortam(an, p, rng)
            akim = _akim(an, p, rng)
            termal = _termal(ortam, akim, p, rng)
            self._yaz(modul_id, an, OlcumTipi.ORTAM_SICAKLIK, ortam, gecikme_sn)
            self._yaz(modul_id, an, OlcumTipi.NEM, _nem(an, p, rng), gecikme_sn)
            self._yaz(modul_id, an, OlcumTipi.TERMAL_MAKS, termal, gecikme_sn)
            self._yaz(modul_id, an, OlcumTipi.TERMAL_ORT, termal - 9.0, gecikme_sn)
            an += timedelta(seconds=p.seyrek_sn)

        # --- detection stretch: dense, every channel -------------------------
        an = tespit_bas
        while an <= son:
            ilerleme = (an - tespit_bas).total_seconds() / max(
                (son - tespit_bas).total_seconds(), 1.0
            )
            ortam = _ortam(an, p, rng)
            akim = _akim(an, p, rng)
            olcumler: dict[OlcumTipi, float | None] = {
                OlcumTipi.ORTAM_SICAKLIK: ortam,
                OlcumTipi.NEM: _nem(an, p, rng),
                OlcumTipi.AKIM_L1: akim,
                OlcumTipi.AKIM_L2: akim * rng.uniform(0.99, 1.01),
                OlcumTipi.AKIM_L3: akim * rng.uniform(0.99, 1.01),
                OlcumTipi.AKIM_NOTR: abs(rng.gauss(4.0, 1.5)),
            }
            saglikli_termal = _termal(ortam, akim, p, rng)
            olcumler[OlcumTipi.TERMAL_MAKS] = saglikli_termal
            olcumler[OlcumTipi.TERMAL_ORT] = saglikli_termal - 9.0

            kaliteler: dict[OlcumTipi, Kalite] = {}
            # `bolge_taban` is the level of the frame's four quadrant means, and
            # it is seeded from the *healthy* hot-spot value rather than from the
            # one a fault may be about to inflate. That is what makes the
            # neighbouring-pixel comparison meaningful: a fault that heats one
            # joint leaves this where it was and the pixel pulls away, while a
            # fault that heats the whole panel raises it too and the comparison
            # correctly stays quiet.
            #
            # The offset is small on purpose. NETA (section 9.2) treats 4-15 C
            # against a similar component as already a Priority 3 finding, so a
            # healthy frame whose hot pixel sat 9 C above its own quadrants would
            # be a panel with a problem, not a baseline.
            ek: dict = {
                "gecikme_sn": gecikme_sn,
                "piksel": (18, 11),
                "bolge_taban": saglikli_termal - 3.0,
                # Contract 2's status half, one row per packet. A healthy module
                # is on mains with a comfortable link; a bozucu changes either.
                "besleme": Besleme.SEBEKE,
                "sinyal": int(rng.gauss(-72.0, 3.0)),
            }
            if bozucu is not None:
                bozucu(an, ilerleme, olcumler, kaliteler, ek, rng)

            self.fikstur.durum(
                modul_id,
                an,
                besleme=ek["besleme"],
                sinyal=ek["sinyal"],
                alindi_zaman=an + timedelta(seconds=ek["gecikme_sn"]),
            )

            for olcum_tipi, deger in olcumler.items():
                self._yaz(
                    modul_id,
                    an,
                    olcum_tipi,
                    deger,
                    ek["gecikme_sn"],
                    kaliteler.get(olcum_tipi, Kalite.IYI),
                )

            maks = olcumler.get(OlcumTipi.TERMAL_MAKS)
            if maks is not None and kaliteler.get(OlcumTipi.TERMAL_MAKS, Kalite.IYI) is Kalite.IYI:
                taban = ek["bolge_taban"]
                sutun, satir = ek["piksel"]
                self.fikstur.termal(
                    modul_id,
                    an,
                    maks=maks,
                    maks_sutun=sutun,
                    maks_satir=satir,
                    bolge_ort=(taban - 1.2, taban + 0.8, taban - 0.6, taban + 1.0),
                    # A full frame at every instant (integration decision), for
                    # the modules that carry frames in this set.
                    kare=termal_kare,
                    alindi_zaman=an + timedelta(seconds=ek["gecikme_sn"]),
                )
            an += timedelta(seconds=p.sik_sn)

    def _yaz(
        self,
        modul_id: str,
        an: datetime,
        olcum_tipi: OlcumTipi,
        deger: float | None,
        gecikme_sn: float,
        kalite: Kalite = Kalite.IYI,
    ) -> None:
        self.fikstur.olcum(
            modul_id,
            olcum_tipi,
            an,
            None if deger is None else round(deger, 3),
            kalite,
            an + timedelta(seconds=gecikme_sn),
        )


# --------------------------------------------------------------------------
# The injections
# --------------------------------------------------------------------------


def _bozucu_gevsek_klemens(an, ilerleme, olcumler, kaliteler, ek, rng):
    """Scenario 1. A joint's contact resistance rising; the load does not change.

    The signature is a *negative*: the temperature climbs and nothing that could
    explain it does. Current steady, ambient steady, and the heat confined to one
    pixel while the rest of the frame stays where it was.
    """
    artis = 30.0 * ilerleme**1.4
    olcumler[OlcumTipi.TERMAL_MAKS] += artis
    # The frame does not follow: this is one joint, not the room. `bolge_taban`
    # is left where it was, so the hot pixel pulls away from its own quadrants.
    ek["piksel"] = (14, 9)


def _bozucu_asiri_yuk(an, ilerleme, olcumler, kaliteler, ek, rng):
    """Scenario 2. Overload: the current really did go up, and so did everything."""
    carpan = 1.0 + 1.3 * ilerleme
    for faz in (OlcumTipi.AKIM_L1, OlcumTipi.AKIM_L2, OlcumTipi.AKIM_L3):
        olcumler[faz] *= carpan
    olcumler[OlcumTipi.TERMAL_MAKS] += 45.0 * ilerleme
    olcumler[OlcumTipi.TERMAL_ORT] += 40.0 * ilerleme
    olcumler[OlcumTipi.ORTAM_SICAKLIK] += 8.0 * ilerleme
    # Whole-frame heating, so the neighbouring-pixel test correctly stays quiet:
    # this is not a joint, it is the busbar and the air around it.
    ek["bolge_taban"] += 45.0 * ilerleme


def _bozucu_faz_dengesizligi(an, ilerleme, olcumler, kaliteler, ek, rng):
    """Scenario 3. One phase sheds load; the difference returns via the neutral."""
    olcumler[OlcumTipi.AKIM_L3] *= 1.0 - 0.35 * ilerleme
    fark = olcumler[OlcumTipi.AKIM_L1] - olcumler[OlcumTipi.AKIM_L3]
    olcumler[OlcumTipi.AKIM_NOTR] = max(olcumler[OlcumTipi.AKIM_NOTR], fark * 0.9)


def _bozucu_nem(an, ilerleme, olcumler, kaliteler, ek, rng):
    """Scenario 4. Water getting in: humidity climbs towards condensation."""
    olcumler[OlcumTipi.NEM] = min(99.0, olcumler[OlcumTipi.NEM] + 48.0 * ilerleme)


def _bozucu_ark(an, ilerleme, olcumler, kaliteler, ek, rng):
    """Scenario 5. An arc: a single event row from the protection device.

    Written only at the instant it happened. The contract samples `ark_olay` on
    event, never periodically, so a fixture that wrote zeroes all day would be
    describing a sensor the system does not have.
    """
    if 0.90 < ilerleme <= 0.92:
        olcumler[OlcumTipi.ARK_OLAY] = 1.0


def _bozucu_sensor_kalite(an, ilerleme, olcumler, kaliteler, ek, rng):
    """Scenario 6a. A thermal sensor talking nonsense — and saying so.

    The values are deliberately alarming: ~150 C, far above every absolute limit
    in layer 1 and far outside the module's own baseline. If layer 0 did not veto
    the channel this module would produce a critical hot-spot alarm, which is the
    exact failure the layer exists to prevent. `kalite` is the only thing
    separating this from a real fire.
    """
    olcumler[OlcumTipi.TERMAL_MAKS] = 150.0 + rng.gauss(0, 4)
    kaliteler[OlcumTipi.TERMAL_MAKS] = Kalite.SUPHELI if rng.random() < 0.7 else Kalite.YOK
    if kaliteler[OlcumTipi.TERMAL_MAKS] is Kalite.YOK:
        olcumler[OlcumTipi.TERMAL_MAKS] = None


def _bozucu_sensor_donuk(an, ilerleme, olcumler, kaliteler, ek, rng):
    """Scenario 6b. A frozen sensor: same value for hours, and `kalite` says 'iyi'.

    The harder half of scenario 6. Nothing in the data admits a fault — the module
    believes the reading. Only the physics gives it away: a hot spot does not hold
    78.00 C to the hundredth for six hours. And 78 C is above layer 1's `izle`
    limit and far outside this module's baseline, so without the frozen-value test
    it becomes a temperature anomaly.
    """
    olcumler[OlcumTipi.TERMAL_MAKS] = 78.0


def _bozucu_saat_kaymasi(an, ilerleme, olcumler, kaliteler, ek, rng):
    """Scenario 7b. The module's clock is behind: EVERY row arrives 15 min after
    its own timestamp, so the minimum gap in the window is 15 min — the
    integration-phase rule's "no reading is fresh" case. (A backlog would have a
    minimum near zero; see `_bozucu_gec_veri`.)"""
    ek["gecikme_sn"] = 900.0


def _bozucu_besleme_kaybi(an, ilerleme, olcumler, kaliteler, ek, rng):
    """Scenario 7c. Mains lost at 80% of the stretch; the supercapacitor carries
    the module and every packet since says so. Measurements stay healthy — the
    finding must come from the status rows alone."""
    if ilerleme >= 0.8:
        ek["besleme"] = Besleme.YEDEK


def _bozucu_sinyal_zayif(an, ilerleme, olcumler, kaliteler, ek, rng):
    """Scenario 7d. The link fades over the stretch, from -72 to about -112 dBm."""
    ek["sinyal"] = int(-72.0 - 40.0 * ilerleme + rng.gauss(0, 2.0))


def _bozucu_gec_veri(an, ilerleme, olcumler, kaliteler, ek, rng):
    """HARD NEGATIVE. Late data: the uplink was down for the first 60% of the
    stretch and the backlog arrived all at once when it came back. Measurement
    times are right, arrival times are late — the *maximum* gap is hours, the
    *minimum* is the usual two seconds. Not a clock fault; the old rule alarmed
    on it, the integration-phase rule must not."""
    if ilerleme < 0.6:
        # Everything measured before 60% arrives at the 60% mark.
        ek["gecikme_sn"] = 2.0 + (0.6 - ilerleme) * TESPIT_SAAT * 3600.0


def _bozucu_gurultulu(an, ilerleme, olcumler, kaliteler, ek, rng):
    """HARD NEGATIVE. A noisy but entirely healthy module.

    Real panels are electrically noisy places and real sensors are not laboratory
    instruments. Brief spikes happen — a reflection, a door opening, a technician
    walking past the lens. The correct output is nothing at all, and a detector
    that judges the newest sample instead of the window fails here.
    """
    olcumler[OlcumTipi.TERMAL_MAKS] += rng.gauss(0, 1.8)
    olcumler[OlcumTipi.ORTAM_SICAKLIK] += rng.gauss(0, 1.2)
    if rng.random() < 0.02:
        olcumler[OlcumTipi.TERMAL_MAKS] += rng.uniform(9.0, 14.0)


def _bozucu_ortak_isinma(an, ilerleme, olcumler, kaliteler, ek, rng):
    """HARD NEGATIVE. A hot afternoon: the whole site warms together.

    Section 5's summer-afternoon case, and the reason layer 3 is described as the
    layer that *reduces* false alarms. Every module here leaves its own baseline
    band at the same time, so layer 2 alone would raise one alarm per module — a
    downpour on the one afternoon an operator can least afford it. The correct
    output is silence, and the only thing that can produce it is the comparison
    between modules.
    """
    artis = 12.0 * ilerleme
    olcumler[OlcumTipi.ORTAM_SICAKLIK] += artis
    olcumler[OlcumTipi.TERMAL_MAKS] += artis
    olcumler[OlcumTipi.TERMAL_ORT] += artis
    # The whole frame warms with the air, so the hot pixel does not pull away.
    ek["bolge_taban"] += artis


# --------------------------------------------------------------------------
# The set
# --------------------------------------------------------------------------

SENARYOLAR: tuple[Senaryo, ...] = (
    Senaryo(
        "TR041-P01-M1",
        "senaryo_01_gevsek_klemens",
        "Tek noktada yavaş ısınma, akım ve ortam sabit.",
        beklenen=frozenset({Tip.AKIM_SICAKLIK_SAPMASI}),
        senaryo="gevsek_klemens",
        kritik_oran=1.0,
    ),
    Senaryo(
        "TR041-P02-M1",
        "senaryo_02_asiri_yuk",
        "Akım yükseliyor, pano geneli ısınıyor.",
        beklenen=frozenset({Tip.SICAK_NOKTA}),
        senaryo="asiri_yuk",
        kritik_oran=1.0,
    ),
    Senaryo(
        "TR052-P01-M1",
        "senaryo_03_faz_dengesizligi",
        "L3 yük atıyor, nötr akımı yükseliyor.",
        beklenen=frozenset({Tip.FAZ_DENGESIZLIGI}),
        senaryo="faz_dengesizligi",
        kritik_oran=1.0,
    ),
    Senaryo(
        "TR052-P01-M2",
        "senaryo_04_nem_yukselmesi",
        "Nem yoğuşma sınırına tırmanıyor.",
        beklenen=frozenset({Tip.NEM_YUKSEK}),
        senaryo="nem_yukselmesi",
        kritik_oran=1.0,
    ),
    Senaryo(
        "TR052-P02-M1",
        "senaryo_05_ark_olayi",
        "Ark koruma cihazı trip kaydı bıraktı.",
        beklenen=frozenset({Tip.ARK}),
        senaryo="ark_olayi",
        # The arc IS the critical moment; it does not ramp up to one.
        baslangic_oran=0.91,
        kritik_oran=0.91,
    ),
    Senaryo(
        "TR063-P01-M1",
        "senaryo_06a_sensor_kalitesiz",
        "Termal sensör 150 °C saçmalıyor, kalite alanı bunu söylüyor.",
        beklenen=frozenset({Tip.SENSOR_ARIZASI}),
        senaryo="sensor_arizasi",
        # No kritik_oran: a broken sensor does not get worse.
        yasak=frozenset({Tip.SICAK_NOKTA, Tip.AKIM_SICAKLIK_SAPMASI}),
    ),
    Senaryo(
        "TR063-P01-M2",
        "senaryo_06b_sensor_donuk",
        "Termal sensör 78.00 °C'de donmuş, kalite 'iyi' diyor.",
        beklenen=frozenset({Tip.SENSOR_ARIZASI}),
        senaryo="sensor_arizasi",
        yasak=frozenset({Tip.SICAK_NOKTA, Tip.AKIM_SICAKLIK_SAPMASI}),
    ),
    Senaryo(
        "TR063-P02-M1",
        "senaryo_07a_modul_sessiz",
        "Modül 40 dakikadır ölçüm göndermiyor.",
        beklenen=frozenset({Tip.MODUL_SAGLIK}),
        senaryo="modul_saglik",
        # The module goes dark at the end of its own stretch, and that instant is
        # both the onset and the critical state: there is no warning to be had
        # ahead of a module simply stopping.
        baslangic_oran=1.0,
        kritik_oran=1.0,
    ),
    Senaryo(
        "TR063-P02-M2",
        "senaryo_07b_saat_kaymasi",
        "Ölçüm zamanı ile varış zamanı 15 dakika ayrışmış.",
        beklenen=frozenset({Tip.MODUL_SAGLIK}),
        senaryo="modul_saglik",
        # Drift is present from the first sample and does not escalate.
    ),
    Senaryo(
        "TR063-P02-M3",
        "senaryo_07c_besleme_kaybi",
        "Şebeke beslemesi kesildi; modül yedek (süperkapasitör) beslemede.",
        beklenen=frozenset({Tip.MODUL_SAGLIK}),
        senaryo="modul_saglik",
        # Instantaneous at the moment mains went: onset and critical coincide.
        baslangic_oran=0.8,
        kritik_oran=0.8,
    ),
    Senaryo(
        "TR063-P02-M4",
        "senaryo_07d_sinyal_zayif",
        "Alınan sinyal gücü -72'den -112 dBm'e düşüyor.",
        beklenen=frozenset({Tip.MODUL_SAGLIK}),
        senaryo="modul_saglik",
        # A fading link has no critical moment of its own; it ends in silence.
    ),
    # --- clean modules: the set is worthless without them -------------------
    Senaryo("TR041-P01-M2", "temiz_01", "Hiçbir şey enjekte edilmedi."),
    Senaryo("TR041-P01-M3", "temiz_02", "Hiçbir şey enjekte edilmedi."),
    Senaryo("TR041-P02-M2", "temiz_03", "Hiçbir şey enjekte edilmedi."),
    Senaryo("TR052-P01-M3", "temiz_04", "Hiçbir şey enjekte edilmedi."),
    Senaryo("TR063-P01-M3", "temiz_05", "Hiçbir şey enjekte edilmedi."),
    # --- hard negatives -----------------------------------------------------
    Senaryo("TR074-P01-M1", "gurultulu_01", "Gürültülü ama sağlıklı.", yasak=frozenset()),
    Senaryo("TR074-P01-M2", "gurultulu_02", "Gürültülü ama sağlıklı."),
    Senaryo("TR074-P01-M3", "gurultulu_03", "Gürültülü ama sağlıklı."),
    Senaryo("TR074-P02-M1", "gurultulu_04", "Gürültülü ama sağlıklı."),
    Senaryo("TR085-P01-M1", "ortak_isinma_01", "Sıcak öğleden sonra; tüm saha birlikte ısınıyor."),
    Senaryo("TR085-P01-M2", "ortak_isinma_02", "Sıcak öğleden sonra; tüm saha birlikte ısınıyor."),
    Senaryo("TR085-P01-M3", "ortak_isinma_03", "Sıcak öğleden sonra; tüm saha birlikte ısınıyor."),
    Senaryo("TR085-P02-M1", "ortak_isinma_04", "Sıcak öğleden sonra; tüm saha birlikte ısınıyor."),
    Senaryo("TR096-P01-M1", "gec_veri_01", "Bağlantı kesildi, birikmiş veri sonradan geldi. Saat doğru."),
)

#: How long the detection stretch is, and which module goes dark for how long.
#: Both the row generator and the label emitter read these, so the timeline in
#: the label file cannot drift from the timeline in the data — which would be an
#: invisible, systematic error in every lead time.
TESPIT_SAAT = 7.0
SESSIZ_DAKIKA: dict[str, float] = {"TR063-P02-M1": 40.0}


#: modul_id -> the injection to apply. Absent means a healthy module.
_BOZUCULAR = {
    "TR041-P01-M1": _bozucu_gevsek_klemens,
    "TR041-P02-M1": _bozucu_asiri_yuk,
    "TR052-P01-M1": _bozucu_faz_dengesizligi,
    "TR052-P01-M2": _bozucu_nem,
    "TR052-P02-M1": _bozucu_ark,
    "TR063-P01-M1": _bozucu_sensor_kalite,
    "TR063-P01-M2": _bozucu_sensor_donuk,
    "TR063-P02-M2": _bozucu_saat_kaymasi,
    "TR063-P02-M3": _bozucu_besleme_kaybi,
    "TR063-P02-M4": _bozucu_sinyal_zayif,
    "TR096-P01-M1": _bozucu_gec_veri,
    "TR074-P01-M1": _bozucu_gurultulu,
    "TR074-P01-M2": _bozucu_gurultulu,
    "TR074-P01-M3": _bozucu_gurultulu,
    "TR074-P02-M1": _bozucu_gurultulu,
    "TR085-P01-M1": _bozucu_ortak_isinma,
    "TR085-P01-M2": _bozucu_ortak_isinma,
    "TR085-P01-M3": _bozucu_ortak_isinma,
    "TR085-P02-M1": _bozucu_ortak_isinma,
}

#: Modules that carry a full frame at every instant, so `kanit.kare_id` has
#: something to point at. Every real module does (integration decision); the
#: fixture set limits it to the thermal scenarios to keep the suite's write
#: volume down — a frame per instant per module is 1.5 KB × 420 × 29 modules.
_KARELI = {"TR041-P01-M1", "TR041-P02-M1"}


def kur(
    fikstur: Fikstur,
    simdi: datetime,
    tohum: int = 20260915,
    gecmis_gun: float = 15.0,
    secim: "tuple[str, ...] | None" = None,
) -> tuple[int, int]:
    """Write the whole set. Returns (measurement rows, thermal rows).

    `secim` narrows it to specific modules for a focused test — but note that a
    module evaluated without its site-mates loses layer 3's cross-module
    comparison, which for the hard negatives is the whole point.
    """
    uretec = Uretec(fikstur=fikstur, simdi=simdi, tohum=tohum)
    for senaryo in SENARYOLAR:
        if secim is not None and senaryo.modul_id not in secim:
            continue
        uretec.uret(
            senaryo.modul_id,
            gecmis_gun=gecmis_gun,
            bozucu=_BOZUCULAR.get(senaryo.modul_id),
            tespit_saat=TESPIT_SAAT,
            sessiz_dakika=SESSIZ_DAKIKA.get(senaryo.modul_id, 0.0),
            termal_kare=senaryo.modul_id in _KARELI,
        )
    return fikstur.yaz()


def beklenen_tipler() -> dict[str, frozenset[Tip]]:
    """The answer key, as a mapping. Only modules that should produce something."""
    return {s.modul_id: s.beklenen for s in SENARYOLAR if s.beklenen}


def temiz_moduller() -> tuple[str, ...]:
    """Modules that must produce no episode at all — clean and hard negatives alike."""
    return tuple(s.modul_id for s in SENARYOLAR if not s.beklenen)


def etiket_uret(
    simdi: datetime,
    tohum: int = 20260915,
    gecmis_gun: float = 15.0,
    secim: "tuple[str, ...] | None" = None,
) -> EtiketDosyasi:
    """Emit this set's answer key in `etiket.py`'s format.

    The fixture set and a real blind set differ in who holds this file and when,
    not in what it contains — so the evaluation tool is exercised against exactly
    the shape track A will hand over, and a real blind set drops straight in.

    The timeline is recomputed from the same constants the row generator used
    (`TESPIT_SAAT`, `SESSIZ_DAKIKA`), not copied, so the two cannot drift apart.

    ON `kritik_esik`. This is the generator's declaration of when the injected
    fault reached the state it was injected to reach — for a ramp, the end of the
    ramp; for the arc, the instant it fired; for a module going dark, the moment
    it stopped. Only the generator can know it, which is the whole reason the
    label file has to carry it: lead time is a subtraction between that instant
    and the moment the detector first opened an episode, and one of those two
    numbers is not in our database.
    """
    senaryolar: list[EtiketSenaryosu] = []
    temiz: list[str] = []

    for s in SENARYOLAR:
        if secim is not None and s.modul_id not in secim:
            continue
        if not s.senaryo:
            temiz.append(s.modul_id)
            continue

        son = simdi - timedelta(minutes=SESSIZ_DAKIKA.get(s.modul_id, 0.0))
        tespit_bas = son - timedelta(hours=TESPIT_SAAT)
        uzunluk = (son - tespit_bas).total_seconds()

        senaryolar.append(
            EtiketSenaryosu(
                senaryo_id=s.ad,
                modul_id=s.modul_id,
                senaryo=s.senaryo,
                baslangic=tespit_bas + timedelta(seconds=uzunluk * s.baslangic_oran),
                kritik_esik=(
                    tespit_bas + timedelta(seconds=uzunluk * s.kritik_oran)
                    if s.kritik_oran is not None
                    else None
                ),
                aciklama=s.aciklama,
            )
        )

    return EtiketDosyasi(
        surum=SURUM,
        senaryolar=tuple(senaryolar),
        temiz_moduller=tuple(temiz),
        tohum=tohum,
        uretim_zamani=simdi,
        kapsam_bas=simdi - timedelta(days=gecmis_gun),
        kapsam_bit=simdi,
        aciklama="İZ B etiketli geliştirme seti — kör test değil, regresyon setidir.",
    )
