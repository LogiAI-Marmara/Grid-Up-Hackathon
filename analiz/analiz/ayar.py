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

from .sozlesme import OlcumTipi, Seviye, Tip

__all__ = [
    "VeritabaniAyari",
    "TaramaAyari",
    "PencereAyari",
    "Katman0Ayari",
    "Katman1Ayari",
    "Katman2Ayari",
    "Katman2YavasAyari",
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

    #: How often the detector visits the database.
    #:
    #: Section 3.7 names 10 s and marks it adjustable. This default is 30 s, and
    #: the change is deliberate: the T5 load test measured a turn at 100 modules
    #: taking ~19 s, so a 10 s period leaves the detector permanently behind at
    #: the fleet size section 7.7 targets, while the same work fits inside 30 s
    #: with room to spare. See `analiz/README.md` § T5 for the measurements.
    #:
    #: Nothing is lost by the change. Section 3.5 fixes the timescale of every
    #: event this system detects at minutes to hours — a loose terminal takes
    #: days, overload hours — so 20 s of additional latency is invisible against
    #: them. The one event needing an instant response is the arc, and that is
    #: the TVOC-2's job (SIL-2, sub-millisecond); we only relay its record, and
    #: relaying it 20 s later changes nothing, because the protection device has
    #: already tripped.
    #:
    #: The scan period is unrelated to the evaluation window (section 3.6): the
    #: detector still looks back hours, it just looks back less often.
    periyot_sn: float = 30.0

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
    #:
    #: D1 (post-review): this is the FAST path only. Six hours is right for
    #: catching a sudden rise but structurally cannot see a fault that grows
    #: slower than it can accumulate `Katman2Ayari.asgari_delta` worth of rise
    #: inside a six-hour window — a terminal going 45 -> 60 C over ten days
    #: moves about 0.06 C inside any given six hours, which never clears the
    #: total-rise gate no matter how far the fault has actually come. That is
    #: exactly section 2.3's day-10 example, and it is why `Katman2YavasAyari`
    #: exists: a second, days-to-weeks window computed on daily SQL aggregates
    #: rather than by widening this one (a 21-day 30 s-cadence window would be
    #: 60k rows per channel per module pulled into Python every turn).
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

    #: Clock drift, integration-phase rule. Over the detection window the gap
    #: `alindi_zaman - zaman` is taken per sample, and:
    #:
    #:   - any sample measured AFTER it was received (gap below
    #:     `-ileri_tarih_tolerans_sn`) is certain drift — a module cannot
    #:     measure in the collector's future;
    #:   - the MINIMUM gap above `saat_kaymasi_sn` is drift: not one reading in
    #:     the window was fresh, so the offset is in the module's clock;
    #:   - minimum near zero with a large maximum is late (backfilled) data. Not
    #:     an anomaly — that is the uplink, not the clock — and it is exposed as
    #:     the data-delay metric under `/saglik` instead.
    #:
    #: The old rule judged the maximum gap and so called every backlog a broken
    #: clock; section 3.6 promises that a backlog is caught for free, not
    #: alarmed on.
    saat_kaymasi_sn: float = 120.0

    #: How far into the future a measurement may be stamped before it counts as
    #: future-dated. Not zero: `alindi_zaman` is the collector's transaction
    #: start and a module a second ahead of it is ordinary NTP scatter.
    ileri_tarih_tolerans_sn: float = 5.0

    # --- module status (contract 2's `modul_durum`, scenario 7) -------------
    #: The module reports `besleme = yedek` when the supercapacitor is carrying
    #: it. This many newest status rows on backup power is a power-loss finding;
    #: 2 rather than 1 for the same reason no layer judges a single sample.
    besleme_yedek_ardisik: int = 2

    #: Median received signal strength over the newest `sinyal_ornek` status
    #: rows below this, dBm, is a weak-signal finding. -100 dBm is where LoRa /
    #: NB-IoT links start dropping packets; tune per site.
    sinyal_zayif_dbm: float = -100.0
    sinyal_ornek: int = 5

    #: Status rows needed before either status test is applied at all.
    asgari_durum_ornek: int = 2

    #: Severity for each layer-0 finding. Sensor faults are never `kritik`: a
    #: broken sensor is a maintenance ticket, not a grid emergency, and letting
    #: it shout as loudly as a fire is how operators learn to ignore the system.
    kalite_seviye: Seviye = Seviye.UYARI
    donuk_seviye: Seviye = Seviye.UYARI
    aralik_disi_seviye: Seviye = Seviye.UYARI
    sessizlik_seviye: Seviye = Seviye.UYARI
    saat_kaymasi_seviye: Seviye = Seviye.IZLE
    besleme_seviye: Seviye = Seviye.UYARI
    sinyal_seviye: Seviye = Seviye.IZLE


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
    #:
    #: D2 (post-review): deviation from a module's OWN normal, alone, is capped
    #: at `izle`. Severity is meant to read off the PRESENT, load-normalized
    #: physical condition (section D2's excess-heating and difference-vs-peer
    #: criteria, both mapped to the FIST 4-13 bands), and a robust z-score is
    #: neither of those — it is "unusual for this module", which says nothing
    #: about whether the value is a routine maintenance note or a today problem.
    #: A previously-cold module having a routine 20 A load applied for the first
    #: time could show a huge z on a channel that never moved before, with
    #: nothing physically wrong. `z_uyari`/`z_kritik` are KEPT — not deleted —
    #: because they still shape the SCORE curve inside the capped `izle` band
    #: (see `katman2_taban._sapma`); they can no longer promote the resulting
    #: Bulgu's severity past `izle`. See `skor.esikle_tavanli`.
    z_izle: float = 3.5
    z_uyari: float = 6.0
    z_kritik: float = 10.0

    #: Floor on MAD. A channel that sat perfectly still all fortnight has MAD 0,
    #: and every later reading would divide to infinity. The floor is roughly one
    #: sensor quantisation step.
    asgari_mad: float = 0.3

    #: Trend, in units per hour over the detection window.
    #:
    #: D2 (post-review): these no longer set a Bulgu's severity. Severity means
    #: an action, and a slope is a forecast, not a present condition — "it is
    #: climbing" says nothing about whether to watch, schedule, or act right
    #: now, only about when it might. `egilim_izle` is kept as the minimum rate
    #: worth mentioning in `gerekce` at all (below it the slope disappears into
    #: measurement noise and saying anything is false precision); `egilim_uyari`
    #: / `egilim_kritik` are kept only to word the informational sentence's own
    #: "how fast is fast" framing — see `katman2_taban._egilim_bilgisi` — and
    #: play no further part in the severity `esikle` produces.
    egilim_izle: float = 0.5
    egilim_uyari: float = 1.5
    egilim_kritik: float = 4.0

    #: A trend is only mentioned if the window's total rise also clears this, so
    #: a steep slope fitted through ten minutes of noise stays quiet.
    asgari_delta: float = 5.0

    #: Minimum samples in the detection window before a slope is fitted.
    asgari_egilim_ornek: int = 8


@dataclass(frozen=True)
class Katman2YavasAyari:
    """Layer 2's SLOW path — decision D1.

    Days-to-weeks degradation the fast 6-hour window (`PencereAyari.tespit_sn`)
    structurally cannot see: see that field's docstring for why. Computed on
    SQL daily aggregates (`PencereGetirici._yavas_ozetler`), never on raw
    30 s-cadence rows — the whole point is a multi-week window, and pulling
    weeks of raw samples per channel per module into Python is the mistake
    `_tabanlar`'s own docstring already explains for the fast baseline.

    THE REFERENCE PROBLEM, AND WHY THIS DOES NOT USE A SLIDING BASELINE. D1's
    hardest requirement: the slow path must not judge a slow fault against a
    baseline the fault itself can drift. Verified failure mode of the naive
    approach (see tests/test_zaman_olcekleri.py
    ::test_yavas_isinma_taban_cizgisi_yutulur — kept as a regression so nobody
    "fixes" this back in later): feed `Katman2Ayari`'s existing 14-day sliding
    median/MAD a 10-day linear drift from 45 to 60 C, and the baseline ends up
    close to the drifting value's own recent median with a MAD wide enough to
    swallow it — no finding, from a detector whose entire selling point is
    catching exactly this.

    So the slow path's severity does NOT compare against a SLIDING statistic
    of its own recent history. It compares the module's CURRENT
    normalized-heating level — (hot spot - ambient) / current^n, robustly
    smoothed over the newest few daily buckets — against that SAME module's
    OWN normalized-heating level from the EARLIEST few qualifying buckets in
    the current (up to `pencere_sn`-long) window: an early-anchored reference
    rather than a sliding one, per D1's own list of acceptable alternatives.
    That excess is then mapped onto the same fixed, physical/engineering bands
    D2 assigns to the fast path's unexplained-heat check
    (`Katman3Ayari.aciklanamayan_*`, itself FIST 4-13's "excess heating over
    ambient" table) — see `dedektor.katman2_taban._yavas_isinma`'s "THE
    REFERENCE" comment for the full reasoning, including why raw (unreferenced)
    normalized heating cannot be used directly (a healthy bolted connection
    legitimately runs hot above ambient at rated current, and D2 is explicit
    that this "load-expected heating" is not itself a fault). The early
    reference is recomputed fresh on every evaluation from that evaluation's
    own window and never carried or updated turn to turn, so nothing here
    slides forward to re-absorb a fault that develops WITHIN the window —
    which is exactly the poisoning failure mode a sliding baseline has.
    """

    #: How far back the slow path looks. D1 asks for "at least 14 days"; 21 is
    #: used so a fault already weeks old, or a slow path started mid-fault,
    #: still leaves the Theil-Sen fit (see `dedektor.istatistik.theil_sen`)
    #: enough daily points on both sides of "now" to be a fit rather than a
    #: two-point line. Engineering default, unverified.
    pencere_sn: float = 21 * 24 * 3600.0

    #: SQL aggregation bucket width. Daily, not hourly: a switchgear joint's own
    #: thermal lag is itself hours long, so an hourly bucket mostly re-measures
    #: that lag with extra sampling noise, while a daily bucket averages it out
    #: and keeps the point count the trend fit considers small. Configurable for
    #: a site that wants tighter buckets once it has the data to justify it.
    kova_sn: float = 24 * 3600.0

    #: Minimum current, amperes, before a bucket contributes to the normalized
    #: series. Mirrors `Katman3Ayari.akim_asgari` — near no load, I^n is small
    #: and noisy and the ratio it feeds can mean anything.
    asgari_akim: float = 5.0

    #: Load-normalization exponent in (deger - ortam) / akim^n. 2 is the I^2 R
    #: model layer 3 also uses, and it is the physics-derived default here.
    #: NOTE, for the README's threshold table and honesty about sourcing: ABB
    #: publishes a vendor thermal model using n=1.6 for some busbar/connector
    #: geometries. That is a vendor example, not a standard, and this default
    #: is not it — it is recorded as an alternative in the README, not adopted.
    yuk_ustel: float = 2.0

    #: Daily buckets needed (after the current-floor filter) before the slow
    #: path evaluates a module at all. Below this there is not yet a "trend"
    #: to distinguish from bucket-to-bucket noise; cold start declines to fire,
    #: same policy as the fast baseline's `PencereAyari.asgari_taban_ornek`.
    asgari_kova: int = 10

    #: How many of the newest qualifying buckets the module's CURRENT
    #: normalized-heating level is a median of. Mirrors
    #: `PencereAyari.temsil_ornek` for the daily series.
    temsil_kova: int = 3

    #: D2's excess-heating-over-ambient bands, FIST 4-13 (Bureau of Reclamation
    #: FIST 4-13, delta-T over ambient): 1-10 K not reported, 11-20 -> izle,
    #: 21-40 -> uyari, >40 -> kritik. Identical criterion and identical bands to
    #: `Katman3Ayari.aciklanamayan_*` — same physical question, two time scales.
    asiri_isinma_izle: float = 11.0
    asiri_isinma_uyari: float = 21.0
    asiri_isinma_kritik: float = 40.0

    #: How often, at most, `PencereGetirici` re-runs the slow path's daily
    #: aggregate query for a given module, seconds. Measured against T5's own
    #: methodology (see `analiz/README.md`'s T5 section): re-running an
    #: unbounded 21-day aggregate over every channel for every module on
    #: EVERY 30 s scan turn nearly doubled the measured 100-module turn cost
    #: and pushed it back over the scan period (p95 ~49.6 s against a 30 s
    #: budget — see the README's "after" T5 row). A days-to-weeks trend cannot
    #: meaningfully change inside 30 s, so recomputing it every turn buys
    #: nothing: `PencereGetirici` caches the last result per module and only
    #: re-queries once `yenileme_sn` has passed since that module's last
    #: refresh, in its own process memory (same pattern, and the same
    #: restart-loses-it limitation, as `OlayDeposu._bekleyen`). 1 hour is an
    #: engineering default, unverified: comfortably below the days-scale
    #: resolution the slow path is built around, comfortably above the 30 s
    #: scan period.
    yenileme_sn: float = 3600.0


@dataclass(frozen=True)
class Katman3Ayari:
    """Layer 3 — relationships. The project's own technical claim, and the layer
    that removes false alarms rather than adding them."""

    # --- current vs temperature ---------------------------------------------
    #: Minimum temperature rise over the detection window before the comparison
    #: is worth making at all, Celsius. Below this there is nothing to explain.
    #: Aligned to FIST 4-13's own floor for `aciklanamayan_*` below: under 10 K
    #: excess is "not reported" there regardless, so there is no point running
    #: the accounting for less rise than that.
    sicaklik_artis_esigi: float = 10.0

    #: Unexplained temperature rise, in Celsius, after the load and the ambient
    #: have each been given credit for the share they account for.
    #:
    #: A joint dissipates I^2 * R. If the current is known at both ends of the
    #: window, the rise the load explains is computable rather than guessable,
    #: and what is left over is the part R must account for — which is the
    #: definition of a connection going bad. See `_akim_sicaklik`.
    #:
    #: D2 (post-review): these ARE the FIST 4-13 "excess heating over ambient"
    #: bands (U.S. Bureau of Reclamation FIST 4-13, delta-T over ambient rise):
    #: 1-10 K not reported, 11-20 K -> izle, 21-40 K -> uyari, >40 K -> kritik.
    #: The previous values (8 / 15 / 30) were an earlier, unsourced choice;
    #: these replace them and are the same bands `Katman2YavasAyari` uses for
    #: the slow path's identical criterion at a longer time scale.
    aciklanamayan_izle: float = 11.0
    aciklanamayan_uyari: float = 21.0
    aciklanamayan_kritik: float = 40.0

    #: Current below which the I^2 ratio is not trustworthy, amperes. Near zero
    #: load the ratio of two small noisy numbers explains anything at all.
    akim_asgari: float = 5.0

    # --- phase vs phase ------------------------------------------------------
    #: One phase's deviation from the median of the three, as a fraction. More
    #: sensitive than layer 1's absolute imbalance percentage, and it names the
    #: phase. A common-mode load change moves all three and cancels here.
    #:
    #: D2/D4 SOURCING NOTE: this is "difference vs a similar component" in
    #: spirit — the category FIST 4-13 gives bands of 1-3 K / 4-15 K / >15 K
    #: for — but the quantity here is a CURRENT fraction, not a Kelvin
    #: difference, and there is no physically honest way to convert one to the
    #: other without assuming a resistance and a load that this comparison does
    #: not have. Converting anyway would launder an engineering default as a
    #: standard citation, which is worse than admitting it is one. These three
    #: values are therefore left as an engineering default, unverified — not
    #: FIST-sourced — and documented as such in the README threshold table.
    faz_sapma_izle: float = 0.08
    faz_sapma_uyari: float = 0.15
    faz_sapma_kritik: float = 0.25
    #: Neutral current above this fraction of mean phase current corroborates.
    notr_orani: float = 0.20

    # --- neighbouring pixel --------------------------------------------------
    #: Hot pixel minus the mean of the four quadrant means, Celsius. A whole
    #: frame that rose together is ambient; one pixel pulling away is a terminal.
    #:
    #: D2 (post-review): this quantity IS a Kelvin difference against a similar
    #: reference (the pixel's own frame), so FIST 4-13's "difference vs a
    #: similar component" bands are the right SHAPE for it: 1-3 K not reported,
    #: 4-15 K -> uyari, >15 K -> kritik, with no separate izle tier in the
    #: source table at all.
    #:
    #: `piksel_ayrisma_izle` below is NOT set to FIST's literal 4 K, though —
    #: and that is a deliberate, documented deviation, not an oversight. A
    #: real (and this project's synthetic) thermal comparison carries its own
    #: measurement noise: quantisation, a few tenths of a degree of frame-to-
    #: frame jitter, and a small structural gap between a hot spot and its own
    #: quadrant means even on a module with nothing wrong. Section 2.6's own
    #: argument against a system that cries wolf applies here as directly as
    #: anywhere else in this file: pinning izle to literal-FIST's 4 K, with no
    #: buffer at all above the noise floor, reclassifies ordinary sensor noise
    #: as "uyari" on a schedule (verified against this project's own noisy-
    #: healthy fixture, `senaryolar._bozucu_gurultulu`, during validation —
    #: see the README's threshold table). 6 K keeps FIST's uyari onset (still
    #: well under it) while giving genuine noise room to not cross the line;
    #: kritik stays at FIST's literal 15 K, where the margin above realistic
    #: noise is already comfortable. The previous values here (8 / 15 / 25)
    #: predate this sourcing entirely; corrected toward FIST, not fully onto
    #: it, for the reason above.
    piksel_ayrisma_izle: float = 6.0
    piksel_ayrisma_uyari: float = 8.0
    piksel_ayrisma_kritik: float = 15.0
    #: How long the hot spot must stay on the same pixel to count as localised.
    piksel_kararlilik_orani: float = 0.6

    # --- module vs module ----------------------------------------------------
    #: This module's rise minus the median rise of its peers, Celsius. Same
    #: "difference vs a similar component" category, same FIST 4-13 bands, and
    #: the same noise-floor caveat as `piksel_ayrisma_*` above — a peer module
    #: is the similar component here instead of a peer pixel, and cross-module
    #: comparison over a live window carries its own noise for the same
    #: reason. Corrected from the previous unsourced 6 / 12 / 20 toward, but
    #: not onto, FIST's literal 4 K izle-equivalent boundary.
    modul_ayrisma_izle: float = 6.0
    modul_ayrisma_uyari: float = 8.0
    modul_ayrisma_kritik: float = 15.0
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

    #: `/saglik`'s data-delay metric is computed over rows that ARRIVED in this
    #: many seconds before now. Late (backfilled) data is not an anomaly — the
    #: clock-drift rule in `Katman0Ayari` says why — so this is where it shows.
    veri_gecikme_pencere_sn: float = 15 * 60.0

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

    #: Delay-on (D2, post-review): how long a qualifying condition must persist,
    #: continuously, before a NEW episode is allowed to open. Severity is meant
    #: to be an action taken on the present condition, not a forecast — but
    #: opening an episode itself from a single turn's single qualifying window
    #: is the same "one data point, one work order" failure just moved from
    #: severity into existence. A condition still present `bekleme_sn` later
    #: opens immediately at that point, with no further delay — this gates the
    #: opening moment only, never how long an already-open episode takes to
    #: reflect a new reading. Unrelated to `histerezis_sn`, which gates CLOSING
    #: and is unchanged.
    #:
    #: Engineering default, unverified: chosen to be comfortably shorter than
    #: the timescale of every fault this system targets (hours to weeks) and
    #: comfortably longer than the scan period, so it filters single-turn
    #: noise without meaningfully delaying a real detection.
    #:
    #: IMPLEMENTATION NOTE: tracked in `OlayDeposu`'s own process memory
    #: (`_bekleyen`), not in the database — see its docstring. A detector
    #: restart mid-persistence starts that condition's clock over, same as a
    #: cold start losing a baseline; this is judged an acceptable, documented
    #: limitation rather than a reason to add a persistent-pending table to a
    #: schema the review asked not be touched without strict need.
    bekleme_sn: float = 15 * 60.0

    #: Finding types exempt from the opening delay — they open on the very turn
    #: that finds them, as every finding did before this decision. The arc is
    #: the canonical, and so far only, case: the TVOC-2 is SIL-2 certified and
    #: has already decided by the time its row exists (section 3.5); delaying
    #: its own episode by `bekleme_sn` on top of that would add pure latency
    #: for a device this system is explicitly not re-deciding.
    bekleme_muaf: tuple[Tip, ...] = (Tip.ARK,)


@dataclass(frozen=True)
class Ayar:
    """The whole configuration tree."""

    veritabani: VeritabaniAyari = field(default_factory=VeritabaniAyari)
    tarama: TaramaAyari = field(default_factory=TaramaAyari)
    pencere: PencereAyari = field(default_factory=PencereAyari)
    katman0: Katman0Ayari = field(default_factory=Katman0Ayari)
    katman1: Katman1Ayari = field(default_factory=Katman1Ayari)
    katman2: Katman2Ayari = field(default_factory=Katman2Ayari)
    katman2_yavas: Katman2YavasAyari = field(default_factory=Katman2YavasAyari)
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
