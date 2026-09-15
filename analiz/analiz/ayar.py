"""Configuration for the analysis layer.

Everything the detector could plausibly want tuned lives here and nowhere else:
the scan period, every window length, and every threshold. Section 11.3 of the
decision record makes window lengths a track-internal decision, but it does not
make them constants buried in an `if` — a threshold that cannot be changed
without editing detector logic cannot be defended to a jury, re-tuned after a
blind test, or varied in a load test.

Three ways to build an `Ayar`, in increasing precedence:

    Ayar()                          # documented defaults
    Ayar.ortamdan()                 # defaults, then GRIDUP_ANALIZ_* env vars
    Ayar().ile(tarama={"periyot_sn": 2.0})   # explicit override, for tests

Every dataclass here is frozen: configuration is read at startup and does not
change under a running scan turn.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields, replace
from typing import Any

from .sozlesme import OlcumTipi, Seviye

__all__ = [
    "VeritabaniAyari",
    "TaramaAyari",
    "PencereAyari",
    "Katman0Ayari",
    "Katman1Ayari",
    "Katman2Ayari",
    "Katman3Ayari",
    "OlayAyari",
    "ApiAyari",
    "Ayar",
]

_ONEK = "GRIDUP_ANALIZ_"


@dataclass(frozen=True)
class VeritabaniAyari:
    """Where the measurements are and where the anomalies go.

    One database, two schemas' worth of tables in one schema: track A owns
    `olcum`/`termal_*`/`modul`, track B owns `anomali*`/`tarama_imleci`. Sharing
    a schema is what lets the detector read measurements without a network hop.
    """

    dsn: str = "postgresql:///gridup"
    sema: str = "gridup"
    #: Statement timeout for a single scan turn's queries, milliseconds. A turn
    #: that cannot finish inside this is a scale problem (section 8), and it
    #: should surface as an error rather than as a silently lengthening turn.
    sorgu_zaman_asimi_ms: int = 30_000


@dataclass(frozen=True)
class TaramaAyari:
    """Decision K1 — the scan loop."""

    #: How often the detector visits the database. Section 3.7: 10 s.
    periyot_sn: float = 10.0

    #: Name of the cursor row. A second named cursor is how a historical
    #: re-scan runs alongside the live one without either one moving the other.
    imlec_adi: str = "varsayilan"

    #: The cursor tracks `alindi_zaman` (arrival), not `zaman` (measurement time).
    #:
    #: This is the detail that makes section 3.6's "late data is caught for free"
    #: actually true. A module that loses its uplink for five minutes and then
    #: sends 300 rows stamps those rows with *old* measurement times; a cursor on
    #: `zaman` would have already moved past them and the batch would be lost
    #: silently. Arrival time is monotonic per row, so a cursor on it cannot skip.
    #:
    #: The cost is that a turn ends its range slightly in the past — see
    #: `emniyet_payi_sn`.
    imlec_alani: str = "alindi_zaman"

    #: How far back the range query stops short of "now", in seconds.
    #:
    #: `alindi_zaman` defaults to `now()`, which in PostgreSQL is transaction
    #: start time. A collector transaction that started before this turn but
    #: commits after it would otherwise land rows *behind* an already-advanced
    #: cursor and never be seen. Ending the range a second in the past is the
    #: cheap fix. Tests that control `alindi_zaman` explicitly set this to 0.
    emniyet_payi_sn: float = 1.0

    #: Cold start: with no cursor row, begin this far back rather than at the
    #: beginning of time, so a fresh detector against a full history does not
    #: spend its first turn scanning five million rows.
    ilk_imlec_geri_sn: float = 3600.0

    #: Safety valve for a very long catch-up: cap how much wall-clock time a
    #: single turn's range may span. 0 disables the cap. With a cap, a detector
    #: restarted after a day advances in bounded steps instead of one huge query.
    azami_aralik_sn: float = 6 * 3600.0


@dataclass(frozen=True)
class PencereAyari:
    """Evaluation windows. Section 3.6: these are unrelated to the scan period."""

    #: Detection window — how far back a layer looks to decide "what is happening
    #: now". The worked example in section 5 uses six hours.
    tespit_sn: float = 6 * 3600.0

    #: Baseline window — what "normal for this module-channel" is computed from.
    #:
    #: Deliberately much longer than the detection window. Section 5's design
    #: note on baseline poisoning: a slowly developing fault gets learned as the
    #: new normal if the baseline can absorb it as fast as it grows.
    taban_sn: float = 14 * 24 * 3600.0

    #: Gap between the end of the baseline window and the start of the detection
    #: window. The second half of the poisoning defence: the value being judged
    #: is never one of the values it is judged against.
    taban_bosluk_sn: float = 6 * 3600.0

    #: Below this many baseline samples the module is in cold start and layer 2
    #: declines to fire rather than judging against three readings.
    asgari_taban_ornek: int = 20

    #: Window used for the module-vs-module comparison in layer 3.
    komsu_sn: float = 6 * 3600.0

    #: Hard cap on rows pulled per channel per evaluation, newest first. A module
    #: sampling far faster than the contract says cannot blow up a turn.
    azami_satir: int = 5000

    #: How many samples a "representative value" is taken over.
    #:
    #: The layers judge the median of the newest `temsil_ornek` samples, never the
    #: single newest one — section 3.6, "the detector never looks at the current
    #: value". Raise it for a noisier site at the cost of reacting a few samples
    #: later; 1 restores single-sample behaviour and is not recommended.
    temsil_ornek: int = 5


@dataclass(frozen=True)
class Katman0Ayari:
    """Layer 0 — sensor health. Runs before everything and can veto a channel."""

    #: Fraction of the detection window's samples that must be non-`iyi` before
    #: the channel is called broken. A single suspect reading is noise; half the
    #: window is a fault.
    kalite_orani: float = 0.5

    #: A channel needs at least this many samples before layer 0 judges it.
    asgari_ornek: int = 6

    #: Consecutive identical readings that count as a frozen sensor. At the
    #: contract's 10 s thermal cadence, 12 samples is two minutes of a value that
    #: physically cannot hold that still.
    donuk_ardisik: int = 12

    #: Values closer together than this count as identical for the frozen test.
    #: Not zero: a sensor quantised to 0.1 C legitimately repeats a value.
    donuk_tolerans: float = 1e-6

    #: Channels exempt from the frozen-value test, because holding still is their
    #: normal behaviour. An arc counter reads 0 for months and is not broken.
    donuk_muaf: tuple[OlcumTipi, ...] = (OlcumTipi.ARK_OLAY,)

    #: Silence longer than this makes the module itself the finding (`modul_saglik`).
    sessizlik_sn: float = 900.0

    #: |zaman - alindi_zaman| above this is module clock drift — scenario 7.
    #: The two fields exist precisely so this is visible; conflating them hides it.
    saat_kaymasi_sn: float = 120.0

    #: Severity for each layer-0 finding. Sensor faults are never `kritik`: a
    #: broken sensor is a maintenance ticket, not a grid emergency, and letting
    #: it shout as loudly as a fire is how operators learn to ignore the system.
    kalite_seviye: Seviye = Seviye.UYARI
    donuk_seviye: Seviye = Seviye.UYARI
    aralik_disi_seviye: Seviye = Seviye.UYARI
    sessizlik_seviye: Seviye = Seviye.UYARI
    saat_kaymasi_seviye: Seviye = Seviye.IZLE


@dataclass(frozen=True)
class Katman1Ayari:
    """Layer 1 — absolute limits, independent of any baseline.

    Sources, per section 9: TEDAS specification, material temperature limits, and
    the NETA / Infraspection delta-T priority classes. A threshold here should be
    traceable to one of those, not to taste.
    """

    #: Surface / hot-spot temperature, Celsius. 130 C is the insulation limit the
    #: decision record's worked scenario ends at.
    termal_izle: float = 70.0
    termal_uyari: float = 90.0
    termal_kritik: float = 130.0

    #: Ambient inside the enclosure, Celsius.
    ortam_izle: float = 45.0
    ortam_uyari: float = 55.0
    ortam_kritik: float = 65.0

    #: Relative humidity, percent. Condensation risk, not comfort.
    nem_izle: float = 75.0
    nem_uyari: float = 85.0
    nem_kritik: float = 95.0

    #: Phase imbalance as a percentage of the mean line current.
    faz_izle: float = 10.0
    faz_uyari: float = 20.0
    faz_kritik: float = 30.0

    #: Below this mean current, imbalance percentage is arithmetic noise: 2 A
    #: against 1 A is 66% imbalance and means nothing. Guard rather than report.
    faz_asgari_akim: float = 20.0

    #: Any arc event at all is critical — the TVOC-2 is SIL-2 rated and we only
    #: relay what it already decided. Section 3.5.
    ark_esik: float = 0.5


@dataclass(frozen=True)
class Katman2Ayari:
    """Layer 2 — deviation from a robust baseline. Carries the early-warning claim."""

    #: Channels that get a baseline. Currents deliberately do not: a load change
    #: is not a fault, and current is judged in layer 3 by its relationship to
    #: temperature instead.
    kanallar: tuple[OlcumTipi, ...] = (
        OlcumTipi.TERMAL_MAKS,
        OlcumTipi.TERMAL_ORT,
        OlcumTipi.ORTAM_SICAKLIK,
    )

    #: Robust z thresholds. z = 0.6745 * (x - median) / MAD, so z is comparable to
    #: a standard-deviation count for normally distributed data but does not move
    #: when one reading is absurd.
    z_izle: float = 3.5
    z_uyari: float = 6.0
    z_kritik: float = 10.0

    #: Floor on MAD. A channel that sat perfectly still all fortnight has MAD 0,
    #: and every later reading would divide to infinity. The floor is roughly one
    #: sensor quantisation step.
    asgari_mad: float = 0.3

    #: Trend, in units per hour over the detection window. This is the half of
    #: layer 2 that produces a warning while the value is still harmless: +1.5
    #: C/h on a terminal is nothing now and 130 C in three days.
    egilim_izle: float = 0.5
    egilim_uyari: float = 1.5
    egilim_kritik: float = 4.0

    #: A trend is only reported if the window's total rise also clears this, so a
    #: steep slope fitted through ten minutes of noise stays quiet.
    asgari_delta: float = 5.0

    #: Minimum samples in the detection window before a slope is fitted.
    asgari_egilim_ornek: int = 8


@dataclass(frozen=True)
class Katman3Ayari:
    """Layer 3 — relationships. The project's own technical claim, and the layer
    that removes false alarms rather than adding them."""

    # --- current vs temperature ---------------------------------------------
    #: Minimum temperature rise over the detection window before the comparison
    #: is worth making at all, Celsius. Below this there is nothing to explain.
    sicaklik_artis_esigi: float = 8.0

    #: Unexplained temperature rise, in Celsius, after the load and the ambient
    #: have each been given credit for the share they account for.
    #:
    #: A joint dissipates I^2 * R. If the current is known at both ends of the
    #: window, the rise the load explains is computable rather than guessable,
    #: and what is left over is the part R must account for — which is the
    #: definition of a connection going bad. See `_akim_sicaklik`.
    aciklanamayan_izle: float = 8.0
    aciklanamayan_uyari: float = 15.0
    aciklanamayan_kritik: float = 30.0

    #: Current below which the I^2 ratio is not trustworthy, amperes. Near zero
    #: load the ratio of two small noisy numbers explains anything at all.
    akim_asgari: float = 5.0

    # --- phase vs phase ------------------------------------------------------
    #: One phase's deviation from the median of the three, as a fraction. More
    #: sensitive than layer 1's absolute imbalance percentage, and it names the
    #: phase. A common-mode load change moves all three and cancels here.
    faz_sapma_izle: float = 0.08
    faz_sapma_uyari: float = 0.15
    faz_sapma_kritik: float = 0.25
    #: Neutral current above this fraction of mean phase current corroborates.
    notr_orani: float = 0.20

    # --- neighbouring pixel --------------------------------------------------
    #: Hot pixel minus the mean of the four quadrant means, Celsius. A whole
    #: frame that rose together is ambient; one pixel pulling away is a terminal.
    piksel_ayrisma_izle: float = 8.0
    piksel_ayrisma_uyari: float = 15.0
    piksel_ayrisma_kritik: float = 25.0
    #: How long the hot spot must stay on the same pixel to count as localised.
    piksel_kararlilik_orani: float = 0.6

    # --- module vs module ----------------------------------------------------
    #: This module's rise minus the median rise of its peers, Celsius.
    modul_ayrisma_izle: float = 6.0
    modul_ayrisma_uyari: float = 12.0
    modul_ayrisma_kritik: float = 20.0
    #: Peers needed before a cross-module comparison means anything.
    asgari_komsu: int = 2
    #: Compare against modules in the same `saha`, or only the same `pano`.
    #: Panel-level is a tighter comparison; site-level finds more peers.
    komsu_kapsami: str = "saha"

    #: Peer rise within this much of ours means the fleet moved together — the
    #: summer-afternoon case. Layer 2's thermal finding is suppressed rather than
    #: reported, which is the false-alarm reduction section 5 claims.
    ortak_hareket_delta: float = 3.0
    #: Only suppress if this fraction of peers moved with us.
    ortak_hareket_orani: float = 0.6


@dataclass(frozen=True)
class ApiAyari:
    """Contract 5 — the read API track C consumes.

    Served as its own process, separate from the scan loop. Decision K1 makes the
    database the only contact surface between components, and that applies inside
    track B too: a slow or crashed API must not be able to stop the detector, and
    a long scan turn must not be able to stall the dashboard.
    """

    adres: str = "127.0.0.1"
    port: int = 8080

    #: Default and maximum page size for list endpoints. The maximum exists so a
    #: caller cannot ask for the whole anomaly table in one response.
    sayfa_boyutu: int = 50
    azami_sayfa_boyutu: int = 500

    #: Hard cap on points returned by the series endpoint. Beyond this the
    #: request is refused with an explanation rather than silently truncated —
    #: a chart drawn from quietly-dropped points is worse than an error, because
    #: nobody can see that it is wrong.
    azami_seri_noktasi: int = 5000

    #: Connection pool bounds for the API process.
    havuz_asgari: int = 1
    havuz_azami: int = 8

    #: Allowed CORS origins for the dashboard. Empty disables CORS entirely,
    #: which is the right default for an on-prem deployment serving the UI from
    #: the same host.
    cors_kaynaklari: tuple[str, ...] = ()


@dataclass(frozen=True)
class OlayAyari:
    """Decision K3 — the event lifecycle."""

    #: How long the condition must be absent before the event closes. Section
    #: 6.5: about 30 minutes. This is the hysteresis that stops one flickering
    #: reading from opening and closing an event all afternoon.
    histerezis_sn: float = 30 * 60.0

    #: Identity prefix. `an_00412` in the contract's example.
    kimlik_oneki: str = "an_"
    kimlik_basamak: int = 5

    #: Who the journal records as the actor for transitions the detector makes.
    sistem_aktoru: str = "sistem"


@dataclass(frozen=True)
class Ayar:
    """The whole configuration tree."""

    veritabani: VeritabaniAyari = field(default_factory=VeritabaniAyari)
    tarama: TaramaAyari = field(default_factory=TaramaAyari)
    pencere: PencereAyari = field(default_factory=PencereAyari)
    katman0: Katman0Ayari = field(default_factory=Katman0Ayari)
    katman1: Katman1Ayari = field(default_factory=Katman1Ayari)
    katman2: Katman2Ayari = field(default_factory=Katman2Ayari)
    katman3: Katman3Ayari = field(default_factory=Katman3Ayari)
    olay: OlayAyari = field(default_factory=OlayAyari)
    api: ApiAyari = field(default_factory=ApiAyari)

    # -- construction ------------------------------------------------------

    def ile(self, **bolumler: dict[str, Any]) -> "Ayar":
        """Return a copy with some fields of some sections replaced.

        `ayar.ile(tarama={"periyot_sn": 2.0})` changes one field and leaves the
        rest of `TaramaAyari` alone. Used by tests and by the load test, which is
        the point of having configuration at all.
        """
        yeni: dict[str, Any] = {}
        for ad, degerler in bolumler.items():
            mevcut = getattr(self, ad, None)
            if mevcut is None:
                raise KeyError(f"unknown configuration section: {ad!r}")
            yeni[ad] = replace(mevcut, **degerler)
        return replace(self, **yeni)

    @classmethod
    def ortamdan(cls, ortam: "dict[str, str] | None" = None) -> "Ayar":
        """Build from defaults overlaid with `GRIDUP_ANALIZ_<SECTION>_<FIELD>` vars.

        `GRIDUP_ANALIZ_TARAMA_PERIYOT_SN=2.5` sets `tarama.periyot_sn`. Only
        scalar fields (str/int/float/bool) are settable this way; tuple-valued
        fields such as the layer 2 channel list are structural and change in code.
        """
        ortam = os.environ if ortam is None else ortam
        temel = cls()
        bolumler: dict[str, dict[str, Any]] = {}
        for bolum in fields(temel):
            mevcut = getattr(temel, bolum.name)
            for alan in fields(mevcut):
                anahtar = f"{_ONEK}{bolum.name.upper()}_{alan.name.upper()}"
                if anahtar not in ortam:
                    continue
                ham = ortam[anahtar]
                simdiki = getattr(mevcut, alan.name)
                bolumler.setdefault(bolum.name, {})[alan.name] = _cevir(ham, simdiki, anahtar)
        return temel.ile(**bolumler) if bolumler else temel


def _cevir(ham: str, ornek: Any, anahtar: str) -> Any:
    """Coerce an environment string to the type of the default it replaces."""
    if isinstance(ornek, bool):
        dusuk = ham.strip().lower()
        if dusuk in {"1", "true", "yes", "evet"}:
            return True
        if dusuk in {"0", "false", "no", "hayir"}:
            return False
        raise ValueError(f"{anahtar}: expected a boolean, got {ham!r}")
    if isinstance(ornek, Seviye):
        return Seviye(ham.strip())
    if isinstance(ornek, bool | int) and not isinstance(ornek, bool):
        return int(ham)
    if isinstance(ornek, int):
        return int(ham)
    if isinstance(ornek, float):
        return float(ham)
    if isinstance(ornek, str):
        return ham
    raise TypeError(f"{anahtar}: {type(ornek).__name__} is not settable from the environment")
