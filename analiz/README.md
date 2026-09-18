# /analiz — İZ B, the analysis layer

Owns one question: **how does an anomaly come out of the data?**

Reads the measurement and thermal tables track A writes. Produces anomaly
episodes that track C reads. Touches no other track's code — decision K1's whole
point is that the only contact surface between A and B is a set of database
tables.

Authoritative specification: [`../docs/izb-karar-kaydi.md`](../docs/izb-karar-kaydi.md).
Every design decision below is from it; section numbers in the code refer to it.
The **integration-phase decisions** (episode model for contract ③, `modul_durum`,
binary thermal frames at every instant, the clock-drift table, the global
`/gecisler` feed) supersede the older documents where they differ; see
[Entegrasyon aşaması](#entegrasyon-aşaması--neler-değişti) below.

---

## What is here, and what is not

| Delivered |
|---|
| Package skeleton, config, entry point |
| Database layer, track B's own tables |
| Scan loop, cursor, manual rewind (K1) |
| Evaluation-window fetcher |
| All four detector layers (K2) |
| Score, severity, `gerekce` production |
| Episode lifecycle and journal (K3) |
| Fixtures: 7 scenarios + clean + hard negatives |
| **Read API — contract ⑤, including `/anomaliler/{id}/gecisler` and the global `/gecisler` feed** |
| **Label file format** (a contract track A must satisfy) |
| **Blind-test evaluation tool — four metrics** |
| **Load test and resource report (T5)** |
| **Smoke-test checks** (`analiz.duman`) — the entry point track C's runner calls |

Track B is complete; the integration-phase adaptation (items 6–14 of the
integration task) is on this branch.

---

## Quick start

```bash
cd analiz
pip install -e '.[api,test]'

createdb gridup
export GRIDUP_ANALIZ_VERITABANI_DSN=postgresql:///gridup

python -m analiz sema          # track A's migrations, then track B's
python -m analiz tara          # run the scan loop
python -m analiz durum         # cursor and episode state
python -m analiz geri-al -24h  # rewind, re-scan the last day
```

**Where the shared schema and vocabularies come from.** Track B defines none of
the shared tables and none of the shared enums. `python -m analiz sema` applies
`toplama/migrations/*.sql` (track A's, in file-name order) and then
`analiz/migrations/100_analiz.sql` (track B's own tables and indexes);
`analiz.sozlesme` imports `sozlesmeler/enums.py`. Both are found relative to
the repository root by default, and can be pointed elsewhere:

| Variable | Meaning | Default |
|---|---|---|
| `GRIDUP_TOPLAMA_MIGRASYON_DIZINI` | directory holding track A's `*.sql` | `<repo>/toplama/migrations` |
| `GRIDUP_SOZLESMELER_KOK` | directory that *contains* `sozlesmeler/` | `<repo>` |

On a checkout without `toplama/` and `sozlesmeler/` (this branch, before track
A's PR is on main), export them once — outside the repo — and point at the copy:

```bash
git archive origin/feature/track-a toplama/migrations sozlesmeler | tar -x -C /tmp/track-a
export GRIDUP_TOPLAMA_MIGRASYON_DIZINI=/tmp/track-a/toplama/migrations
export GRIDUP_SOZLESMELER_KOK=/tmp/track-a
```

The read API, as its own process:

```bash
python -m analiz.api --dsn postgresql:///gridup --port 8080
# or: python -m analiz sunucu --port 8080
# OpenAPI schema at /openapi.json, browsable docs at /docs
```

Everything end to end against the scenario set, leaving the database to inspect:

```bash
createdb gridup_dogrulama
python -m analiz.dogrulama --dsn postgresql:///gridup_dogrulama
```

Blind test (see [the protocol](#kör-test-protokolü)):

```bash
python -m analiz.kortest dondur      --dsn postgresql:///gridup --cikti cikti.json
python -m analiz.kortest degerlendir --etiket etiket.json --cikti cikti.json
```

Load test (T5):

```bash
python -m analiz.yuk --dsn postgresql:///gridup_yuk --moduller 10,50,100
```

Smoke-test checks against a live API (see [Duman testi](#duman-testi--iz-cnin-çağıracağı-giriş-noktası)):

```bash
python -m analiz.duman --api http://127.0.0.1:8080 --senaryolar duman.json
```

Tests (needs a PostgreSQL 14+ the current user can `createdb` on; the two
variables above if `toplama/` is not in the checkout):

```bash
python -m pytest -q
```

---

## Layout

```
analiz/
  sozlesme.py       re-exports sozlesmeler/enums.py; only B-specific helpers
  termal.py         the binary frame: int16 LE, 0.1 °C, 1536 bytes <-> 768 °C
  ayar.py           every threshold and window — configuration, not constants
  db.py             connection; applies toplama/migrations/*.sql then 100
  migrations/
    100_analiz.sql    anomali, anomali_gecis, tarama_imleci, B's indexes
  depo.py           the scan cursor                                     K1
  tarama.py         the scan loop                                       K1
  pencere.py        evaluation-window fetcher
  dedektor/
    istatistik.py     median, MAD, robust z, slope
    katman0_sensor.py sensor health — runs first, can veto a channel
    katman1_mutlak.py absolute limits, baseline-free
    katman2_taban.py  baseline deviation: magnitude and trend
    katman3_iliski.py relationships, and false-alarm suppression
    motor.py          runs the layers in order, merges findings
  skor.py           magnitude -> (severity, score)
  gerekce.py        the sentence the operator reads
  olay.py           episode lifecycle and the journal                   K3
  api.py            contract ⑤, served as its own process
  etiket.py         the label file format — the blind test's answer key
  kortest.py        blind-test evaluation: freeze, then four metrics
  yuk.py            load test and resource report                        T5
  fikstur.py        contract-shaped row writer
  senaryolar.py     the labelled set: 7 scenarios + clean + hard negatives
  dogrulama.py      end-to-end harness, and the turn-by-turn replay
  duman.py          smoke-test checks against a live API (track C calls it)
```

---

## The three decisions, as implemented

### K1 — periodic scan, cursor, rewindable

A background job. Every `tarama.periyot_sn` (default 30 s — see [T5](#t5--ölçeklenebilirlik-raporu)
for why it is not section 3.7's 10 s) it asks what has
arrived since its cursor, works out which modules those rows belong to,
evaluates **each of those modules once**, writes findings, advances the cursor.

Two implementation choices worth knowing about, both in `ayar.TaramaAyari`:

**The cursor tracks `alindi_zaman`, not `zaman`.** This is what makes section
3.6's "late data is caught for free" actually true. A module that loses its
uplink for five minutes and then sends 300 rows stamps them with *old*
measurement times; a cursor on `zaman` would already have moved past them and the
batch would be lost silently. Arrival time is monotonic per row, so a cursor on
it cannot skip. Tested in `test_tarama.py::test_tek_turda_gelen_hicbir_satir_dusmez`.

**The evaluation instant is per module, not per turn.** Derived from the newest
measurement that arrived for that module. Without this, a backlog and a
historical re-scan would both anchor their windows on the present and evaluate
empty windows — which would make the rewind feature silently useless, and rewind
is section 3.4's first argument for polling over push.

A module that has gone *silent* produces no rows and so can never appear in a
row-driven set. A separate sweep adds those modules, judged at the turn's own
instant. That is scenario 7.

### K2 — four layers, no machine learning

Run in order; the order is not cosmetic.

| | Looks at | Fires on |
|---|---|---|
| **0** sensor health | `kalite`, frozen values, impossible values, silence, clock drift, backup power, weak signal | `sensor_arizasi`, `modul_saglik` |
| **1** absolute limits | the value alone | `sicak_nokta`, `ortam_sicaklik_yuksek`, `nem_yuksek`, `faz_dengesizligi`, `ark` |
| **2** baseline deviation (fast, hours) | median + MAD magnitude, capped at `izle` (D2); trend is informational text only | `sicak_nokta`, `ortam_sicaklik_yuksek` |
| **2** normalized heating (slow, days–weeks, D1) | (hot spot − ambient) / current^n vs its own early-window level, mapped to FIST 4-13 bands | `akim_sicaklik_sapmasi` |
| **3** relationships | current↔temperature, phase↔phase, pixel↔frame, module↔module | `akim_sicaklik_sapmasi`, `faz_dengesizligi`, `sicak_nokta` |

**Post-review correction (decisions D1–D3, this PR):** layer 2's trend half
(the old `egilim_izle/uyari/kritik`-driven finding) no longer sets a severity
on its own — see [D2](#d2--severity-is-an-action-not-a-forecast) below — and a
second, slower evaluation now runs alongside the original 6-hour window for
exactly the multi-day fault the fast window structurally cannot see. Layer 3's
current-vs-temperature check no longer substitutes 0 °C for a missing ambient
channel (D3). Layer 0's physical-range check now runs before, not after, the
minimum-sample gate (D3).

Layer 0 runs first because everything after it assumes the numbers are real, and
its veto is **per channel** — a dead humidity sensor must not blind the thermal
detector on the same module. Layer 3 runs last because it is the only layer
allowed to take something back.

**The detector never judges a single sample.** Section 3.6 says it never looks at
"the current value", and `Seri.temsil()` is where that holds: layers judge the
median of the newest `pencere.temsil_ornek` samples. Judging the latest reading
would turn every noise spike into a work order — see the `gurultulu_*` modules in
the scenario set, which exist to catch exactly that regression.

**Baseline poisoning** (section 5's design note) is the failure mode that would
make layer 2 quietly useless: a sliding baseline absorbs a slow fault as fast as
it grows, learns it as the new normal, and goes silent exactly when it should
not. Three defences, all in `PencereGetirici._tabanlar` where the samples are
selected:

1. the baseline window is far longer than the detection window (14 d vs 6 h);
2. it stops `taban_bosluk_sn` short of the present, so a value is never judged
   against itself;
3. it is **frozen at onset** while an episode is open, and stretches inside past
   episodes are excluded.

**Layer 3 reduces false alarms rather than adding them.** On a hot afternoon
every panel on a site warms, layer 2 sees every module leave its band at once,
and alone it would raise one alarm per module. The module-to-module comparison
returns a suppression instead. The `ortak_isinma_*` modules test this.

Two departures from a literal reading of the record, both because the literal
version does not survive contact with real data:

- **Current-vs-temperature is posed as an I²R residual, not as "is the current
  flat?"** Over a six-hour window the current is never flat — a panel's load
  follows a daily profile, so a flatness test fires reliably at 4 a.m. and never
  in the afternoon. A joint dissipates I²R, so the rise the load explains is
  *computable*; what is left over needs R to have changed, which is the fault.
  It also gets the overload case right in the other direction: when the current
  really did double, I² explains more than the observed rise and the test stays
  correctly silent. `katman3_iliski._akim_sicaklik` has the full argument.
- **A specific diagnosis absorbs the generic finding it explains.** One loose
  terminal legitimately trips several tests; as separate episodes they are
  separate work orders for one repair. The survivor takes the *worse* of the two
  severities, so an absolute safety limit can never be quietly downgraded by a
  diagnosis. `motor._ozgulluk`.

No machine learning anywhere, for section 4.3's reasons — the decisive one being
that `gerekce` cannot be produced from a model score, and `gerekce` is mandatory.

### K3 — episode model plus journal

Section 6.2's arithmetic: a three-day fault at a 10 s period is 25,920 turns. A
row per turn would be 25,920 anomaly rows for one loose screw, and `durum` would
mean nothing because there would be no single row to acknowledge.

So the same `modul_id` + the same `tip`, not yet closed, is the **same episode** —
enforced by a partial unique index, not by convention, so two concurrent turns
cannot both open it. Repeated findings update it.

`gridup.anomali_gecis` is the journal: one permanent row per state or severity
transition, following ISA-18.2's split between an alarm status table and an alarm
journal. Not for display — for the audit trail. A severity change is a
transition; a score moving 0.81 → 0.83 inside `uyari` is not.

Episodes close after `olay.histerezis_sn` (default 30 min) without the condition.
Without hysteresis a value sitting on a threshold opens and closes an episode all
afternoon, and every open is an alarm.

---

## API kararları (sözleşmenin sessiz kaldığı yerler)

Contract ⑤ fixes the paths, the query parameter names and the field names. It
says nothing about pagination, error shapes or status codes. These are the
choices this implementation made; **track C needs all of them.**

### Sayfalama

`GET /anomaliler` pages by **keyset on `sira`**, not by offset:

```
GET /anomaliler?limit=50            -> {"veriler": [...], "sonraki": 1234, "limit": 50}
GET /anomaliler?limit=50&sonra=1234 -> the next page
```

`sonraki` is `null` on the last page. Section 7.2 puts a monotonic sequence on
the anomaly table precisely so the alarm service can ask for "everything after
the last id I handled" and be certain it missed nothing — offset paging cannot
make that promise, because an episode opening between two requests shifts every
later row by one and the caller silently skips an alarm.

`GET /moduller` uses `limit`/`ofset` and returns `toplam`. The module list is
bounded by the size of the fleet and does not change under the reader.

### Hata biçimi

One shape for every failure, so track C writes one handler:

```json
{"hata": {"kod": "bulunamadi", "mesaj": "Anomali bulunamadı: an_00412", "kimlik": "an_00412"}}
```

`kod` is a stable slug to branch on. `mesaj` is Turkish, because it can end up
in front of an operator. Extra keys are error-specific and additive.

| Kod | Durum | Ne zaman |
|---|---|---|
| `bulunamadi` | 404 | unknown module, anomaly or frame id |
| `gecersiz_zaman` | 400 | `bas` / `bit` is not ISO 8601 |
| `gecersiz_aralik` | 400 | `bit` precedes `bas` |
| `gecersiz_aralik_adi` | 400 | `aralik` outside the accepted set |
| `cok_fazla_nokta` | 400 | the series would exceed `azami_seri_noktasi` |
| `onaylanamaz` | 409 | acknowledging an episode that is not `acik` |
| `veritabani_erisilemez` | 503 | `/saglik` cannot reach the database |
| — | 422 | FastAPI enum/validation failure (e.g. an unknown `olcum_tipi`) |

### Diğer kararlar

**`durum` on `/moduller` is the MODULE's state**, with the vocabulary
`aktif | sessiz | pasif` — *not* the anomaly lifecycle's
`acik | onaylandi | kapandi`. The contract lists the column under that name and
the collision is the easiest thing to get wrong here. `sessiz` means no
measurement for longer than `katman0.sessizlik_sn`.

**The series endpoint refuses rather than truncates.** Over
`azami_seri_noktasi` (default 5000) it returns `cok_fazla_nokta` naming the
remedy. A chart quietly missing its last three days looks fine and is wrong, and
the caller cannot tell.

**A bucketed series carries `asgari` and `azami` beside `ort`.** `aralik` accepts
`10s | 1m | 5m | 15m | 1h | 1d`. A mean alone hides exactly the spike an operator
is looking for — a bucket averaging 46 °C may have touched 130.

**`/saglik` reports the scan cursor's lag**, not just liveness. Section 8 names a
detector falling behind its scan period as the real scaling limit, so a green
light over a stale anomaly table would be a lie. Watch `imlecler[].gecikme_sn`.

**`/saglik` also reports the data-delay metric, `veri_gecikmesi`.** Late
(backfilled) data is not an anomaly — see the clock-drift table below — so it is
exposed here instead: over rows that arrived in the last
`api.veri_gecikme_pencere_sn` (15 min), `azami_sn` / `p50_sn` / `p95_sn` of
`alindi_zaman − zaman`, `geciken_satir` above `katman0.saat_kaymasi_sn`, and the
modules responsible in `geciken_moduller[]`.

**`GET /moduller/{id}` carries `besleme` and `sinyal`** — the newest
`modul_durum` row's values (`sebeke | yedek`, dBm) and `durum_zaman`, when it
was reported. All three `null` for a module that has never sent a status packet.

**`GET /termal/kare/{id}` returns 768 °C numbers, as before.** Storage is
binary now (`bytea`, int16 LE, 0.1 °C, 1536 bytes); the API decodes. `birim`
is `"C"`.

**`GET /gecisler?sonra=<id>&limit=<n>` is the global transition feed:**

```json
{
  "veriler": [
    {"id": 1841, "anomali_id": "an_00412", "zaman": "2026-09-09T06:40:00Z",
     "alan": "seviye", "onceki": "izle", "yeni": "uyari", "aktor": "sistem"}
  ],
  "sonraki": 1841,
  "limit": 100
}
```

Keyset on the journal's own `id`, ascending, same pattern as `/anomaliler`:
pass the last `id` you handled as `sonra` and nothing between two polls can be
skipped. `alan` is only `durum` or `seviye`; `onceki` is `null` on an episode's
first transition; `aktor` is `sistem` for the detector and the operator identity
for an acknowledgement. One difference from `/anomaliler`, deliberate: `sonraki`
is the `id` of the last row returned (or `null` only when the page is empty), so
a poller stores it blindly and resumes from it — a feed has no last page.

**Timestamps are always UTC ISO 8601 with a literal `Z`.** Offsets are never
emitted.

**The anomaly body is exactly contract ③'s episode shape:** `id, sira,
modul_id, tip, seviye, maks_seviye, skor, ilk_gorulme, son_gorulme, durum,
gerekce, kanit`. The single-`zaman` shape is invalid since the integration
phase and the `zaman` alias this API used to emit is gone. Detector-internal
extras (`katman`, `kapanma_zaman`) travel inside `kanit`.

**Writes.** The API is read-only except `POST /anomaliler/{id}/onayla`, which
requires `aktor` and goes through `OlayDeposu` rather than issuing its own
UPDATE — so the episode tables keep exactly one writer and the acknowledgement
lands in the journal with who and when.

---

## Etiket dosyası formatı

> **İZ A için.** The blind-test tool cannot compute lead time without this file,
> and lead time is the project's headline claim. This section is the spec.

A blind set is data plus a label file. The data goes into the database; the label
file **stays with the producer** until the detector's output has been frozen
(section 4.4). It is JSON, UTF-8, and `analiz.etiket` parses it strictly.

```json
{
  "surum": 1,
  "tohum": 20260915,
  "uretim_zamani": "2026-09-15T09:40:00Z",
  "kapsam": { "bas": "2026-08-31T09:40:00Z", "bit": "2026-09-15T09:40:00Z" },
  "senaryolar": [
    {
      "senaryo_id": "senaryo_01",
      "modul_id": "TR041-P01-M1",
      "senaryo": "gevsek_klemens",
      "baslangic": "2026-09-08T14:00:00Z",
      "kritik_esik": "2026-09-10T03:00:00Z",
      "aciklama": "L2 çıkış klemensi gevşetildi"
    }
  ],
  "temiz_moduller": ["TR041-P01-M2", "TR052-P01-M1"]
}
```

| Alan | Zorunlu | Anlamı |
|---|---|---|
| `surum` | evet | Format version. Currently `1`. A reader refuses a version it was not built for rather than guessing. |
| `senaryolar[].modul_id` | evet | Which module the scenario was injected into. |
| `senaryolar[].senaryo` | evet | Which of the seven. Fixed vocabulary, below. |
| `senaryolar[].baslangic` | evet | When the injection began — the first moment anything was wrong. |
| `senaryolar[].kritik_esik` | hayır | When the fault reached its critical state. **Lead time is computed from this.** Omit only for a fault that does not escalate. |
| `senaryolar[].senaryo_id` | hayır | A label for the report. Defaults to `senaryo_01`, `senaryo_02`, … |
| `senaryolar[].beklenen_tip` | hayır | Pins the accepted anomaly `tip`(s). Normally omitted — see below. |
| `temiz_moduller` | evet | Modules deliberately left untouched. May be empty only if the set genuinely has none, and then the false-alarm rate cannot be measured at all. |
| `kapsam` | hayır | Observation window. The denominator of the per-module-day false-alarm rate. |
| `tohum`, `uretim_zamani`, `aciklama` | hayır | Provenance. |

**`senaryo` vocabulary** — section 7.6's seven, and no others:

```
gevsek_klemens | asiri_yuk | faz_dengesizligi | nem_yukselmesi |
ark_olayi | sensor_arizasi | modul_saglik
```

### İki nokta İZ A'nın dikkatine

**1. `kritik_esik` olmadan kazanılan süre hesaplanamaz.** Lead time is the
subtraction between the moment the detector first opened an episode and the
moment the fault became critical. The first number is in our database; the
second is known **only to the generator**. If it is not written down the metric
cannot exist, however good the detector is — and section 2.5 makes that metric
the project's actual product. For a ramp injection the end of the ramp is a
perfectly good answer; for an instantaneous event it is the event itself.

**2. `beklenen_tip` yazmayın — gerek yok.** Track A knows it injected a loose
terminal. Whether that surfaces as `akim_sicaklik_sapmasi` (the diagnosis) or
`sicak_nokta` (the observation) is track B's business, and both are correct
detections of the same screw. The mapping from scenario to acceptable `tip`
lives in `etiket.SENARYO_TIPLERI`, on this side. If track A pinned a single
expected `tip`, the evaluation would be measuring whether track B's naming
matched track A's guess about track B's naming, which is not a property of the
detector. `beklenen_tip` exists only for a set deliberately testing one specific
classification.

### Ayrıca

- Parsing is strict. An unknown scenario name, a missing field, a naive
  timestamp, a `kritik_esik` before its `baslangic`, or a module listed both
  clean and injected are all **errors**, never skipped rows. A half-parsed label
  file yields a detection rate computed over whatever survived parsing — which
  looks like a result, is not one, and is wrong in the flattering direction.
- Timestamps are UTC ISO 8601. A naive timestamp is rejected rather than assumed
  to be UTC: an unstated timezone shifts every lead time by the offset, silently
  and by hours.
- The fixture set emits this exact format (`senaryolar.etiket_uret`), so a real
  blind set drops straight into the tool with nothing to adapt.

---

## Kör test protokolü

Section 4.4, as commands:

```bash
# 1-2. track A generates the data and keeps the label file.
#      track B loads only the data.

# 3. the detector runs, and its output is FROZEN.
python -m analiz tara --tur 500
python -m analiz.kortest dondur --dsn postgresql:///gridup --cikti cikti.json

# 4. the key is opened and the four metrics are computed.
python -m analiz.kortest degerlendir --etiket etiket.json --cikti cikti.json
```

Freezing is a separate command on purpose. Section 4.4's second trap is that a
set stops being blind the moment a result is seen and the detector is re-tuned
against it. A frozen output file makes "this is what the detector said before
anyone looked at the answers" a checkable artefact rather than a promise.
Nothing in the freeze path reads the labels.

**The four metrics are reported together, always.** Any one alone is misleading:
a detector that alarms on everything scores a perfect detection rate, and one
that never fires a perfect false-alarm rate.

| Metrik | Nasıl hesaplanır |
|---|---|
| Tespit oranı | Per scenario, whether an episode of an accepted `tip` appeared on that module. |
| **Kazanılan süre** | `kritik_esik` − the earliest matching episode's `ilk_gorulme`. Positive means we warned that far ahead. |
| Yanlış alarm | Episodes on `temiz_moduller` ÷ (clean modules × observation days). |
| Sensör ayrımı | Share of `sensor_arizasi` / `modul_saglik` scenarios classified as such **and** producing no grid-fault episode. |

Judgement calls, each covered by a test:

- An extra episode on a genuinely faulty module is a **second true symptom, not
  a false alarm** — overload heats the cabinet as well as the busbar. False
  alarms are counted on the clean modules, where section 4.4 puts them.
- A scenario with no `kritik_esik` contributes to detection but is **excluded
  from the lead-time median** rather than counted as zero.
- With no clean modules the false-alarm rate is **undefined, not perfect**.
- Lead time uses the earliest matching episode **by measurement time**, not by
  episode id: the id is the order rows were written; the claim is about when we
  could first have told someone.
- A late detection yields a **negative** lead time rather than an absolute
  value, so a detector that is consistently late cannot look like one that is
  early.

### Kazanılan süre neden tur tur oynatmayı gerektirir

`dogrulama.kos` runs a couple of turns at the end of the fixture window. That is
enough to prove each scenario is found and **useless for saying when**: every
episode opens at the last measurement, so lead time reads ≈0 for everything.

`dogrulama.oynat` replays the loop turn by turn across the data the way the clock
passes in the field, so an episode opens on the turn where the evidence first
crossed a threshold — which is when a real deployment would have spoken. Any
lead-time number produced without it is meaningless.


---

## Entegrasyon aşaması — neler değişti

Integration task items 6–14, in the order they touch the code. The question the
phase answers is "does data flow end to end"; detector thresholds and trend
logic were not changed.

**No second copy of the contract (6, 6a, 7).** `migrations/000_sozlesme.sql` is
gone; `sema_kur` applies track A's `toplama/migrations/*.sql` and then
`100_analiz.sql`, which now also carries the three indexes track B needs on
track A's tables (`olcum_alindi_zaman_idx`, `termal_ozet_alindi_zaman_idx`,
`modul_durum_alindi_zaman_idx`). `sozlesme.py` imports `sozlesmeler/enums.py`
and defines only `AKIM_FAZLARI`, `SICAKLIK_KANALLARI`, `en_yuksek_seviye`. It
refuses to import if the shared `Tip` lacks `asiri_yuk`, naming the follow-up
(the `ASIRI_YUK = "asiri_yuk"` line in `sozlesmeler/enums.py`, to be applied
once main contains track A's PR). `asiri_yuk` is in the `anomali.tip` CHECK and
in `etiket.SENARYO_TIPLERI["asiri_yuk"]`; the detector does not yet emit it.

**Module status (8).** `gridup.modul_durum` (one row per packet: `besleme`,
`sinyal`, `yazilim_surumu`, `alindi_zaman`) is read into the window as
`Pencere.durumlar`. Layer 0 produces `modul_saglik` for:

| Cause | Rule | Configuration (`katman0`) |
|---|---|---|
| `besleme` | newest `besleme_yedek_ardisik` rows say `yedek` | `besleme_yedek_ardisik=2`, `besleme_seviye=uyari` |
| `sinyal` | median of newest `sinyal_ornek` rows below the floor | `sinyal_zayif_dbm=-100`, `sinyal_ornek=5`, `sinyal_seviye=izle` |

`kanit.neden` names the cause (`sessizlik | saat_kaymasi | besleme | sinyal`);
the engine keeps one episode per `tip`, so when several fire the worst wins and
`neden` says which. A `modul_durum` arrival is a "re-evaluate this module"
signal in the scan loop's range query, so a module sending only status is
still evaluated (`test_8_yalnizca_durum_gonderen_modul_yeniden_degerlendirilir`).

**Clock drift vs late data (9).** Per sample, gap = `alindi_zaman − zaman`:

| Observed in the window | Meaning | Output |
|---|---|---|
| a gap below `−ileri_tarih_tolerans_sn` (5 s) — measured after it was received | certain drift, clock ahead | `modul_saglik`, `kanit.yon = ileri` |
| **minimum** gap above `saat_kaymasi_sn` (120 s) — no reading is fresh | drift, clock behind | `modul_saglik`, `kanit.yon = geri` |
| minimum near zero, maximum high | late (backfilled) data | nothing; `/saglik` → `veri_gecikmesi` |

The previous rule judged the *maximum* gap and so called every backlog a broken
clock, contradicting section 3.6's "late data is caught for free". The fixture
set now has a backfilled hard negative (`gec_veri_01`) beside the drift scenario.

**Evidence frame at the event's time (10).** `kanit.kare_id` is the newest
frame at or before the module's evaluation instant, inside the detection
window — never a frame later than the instant, including on a historical
re-scan (`test_10_gecmis_yeniden_taramada_olayin_kendi_karesi_baglanir`). A
module with no frame in its window gets no `kare_id` rather than a stale one.

**Binary frame (11).** `termal_kare.piksel_verisi` is `bytea`: int16 signed,
little-endian, 0.1 °C, row-major, 768 values, exactly 1536 bytes. `termal.py`
is the codec; `GET /termal/kare/{id}` decodes; the fixtures encode. A full
frame now arrives at every measurement instant (30 s), same period as
`termal_ozet`; `/moduller/{id}/termal/son` reports the frame at the summary's
instant.

**Module detail (12), global feed (13).** See "API kararları" above.

**Smoke-test checks (14).** Next section.

---

## Duman testi — İZ C'nin çağıracağı giriş noktası

> **İZ C için.** The runner is yours: start the simulator, the collector, the
> detector and this API, then call this. The checks are ours. Exit 0 means every
> check passed; 1 means at least one failed (each failure is one line on
> stdout); 2 means the input was bad or the API could not be reached.

```bash
pip install -e 'analiz'                       # no extra dependency: stdlib HTTP
python -m analiz.duman --api http://127.0.0.1:8080 --senaryolar duman.json
# options: --azami-imlec-gecikme-sn 600   fail if the scan cursor is further behind
#          --json rapor.json              also write the report as JSON
#          --zaman-asimi-sn 30            per-request timeout
```

**Input — which module carries which scenario.** JSON, UTF-8. This is the
runner's knowledge (it told the simulator what to inject), so it is an input
to the checks, not something they infer:

```json
{
  "surum": 1,
  "bas": "2026-09-16T06:00:00Z",
  "moduller": {
    "TR041-P01-M2": "temiz",
    "TR041-P01-M1": ["gevsek_klemens", "seviye_gecisi"],
    "TR063-P02-M3": "besleme_kaybi"
  }
}
```

| Field | Required | Meaning |
|---|---|---|
| `surum` | yes | Format version, `1`. |
| `bas` | no | Only episodes with `ilk_gorulme ≥ bas` count. Set it to the run's start so a database that has seen earlier runs cannot pollute the result; omit for a fresh database. UTC, literal `Z`. |
| `moduller` | yes | `modul_id` → one scenario name or a list. `temiz` cannot be combined with another. |

**Scenario vocabulary and what each asserts** (everything through contract ⑤):

| Name | Passes when |
|---|---|
| `temiz` | the module has **no** episode of any type (since `bas`) |
| `gevsek_klemens`, `asiri_yuk`, `faz_dengesizligi`, `nem_yukselmesi`, `ark_olayi`, `sensor_arizasi`, `modul_saglik` | an episode whose `tip` is one the label format accepts for that scenario (`etiket.SENARYO_TIPLERI`). When it carries `kanit.kare_id`, `GET /termal/kare/{id}` must return 768 numbers — the frame decodes end to end |
| `besleme_kaybi` | a `modul_saglik` episode with `kanit.neden = besleme`, or the module detail reporting `besleme = yedek` |
| `sinyal_zayif` / `saat_kaymasi` / `sessiz` | a `modul_saglik` episode with `kanit.neden` = `sinyal` / `saat_kaymasi` / `sessizlik` |
| `seviye_gecisi` | one of the module's episodes has a `seviye` transition between two non-normal severities (e.g. `izle → uyari`), in its own journal **and** reachable through `GET /gecisler?sonra=<id-1>` |

Always run, regardless of input: `/saglik` answers with `durum = calisiyor`,
at least one scan cursor exists and is no further behind than
`--azami-imlec-gecikme-sn`, `veri_gecikmesi` is present, and `/gecisler`
answers. Required coverage for the phase — one clean module, one loose
terminal, one power loss, one severity transition, and the clean module having
opened nothing — is the first four rows of the table plus the global checks.

Scenario data comes from track A's simulator. The same checks pass on this
package's own fixture set (`tests/test_duman.py::FIKSTUR_SENARYOLARI` is a
complete example input), which is how they are tested here.

---

## Contract mismatches found on `feature/track-a`

Read-only inspection of PR #1, as found before the integration phase. Kept for
the record; the status of each is noted.

**1. `anomali.schema.json` has not caught up with the amendment in section 7.2 of
the İZ B record.** The schema still lists `zaman` as required and sets
`additionalProperties: false`. Section 7.2 replaces `zaman` with the pair
`ilk_gorulme` / `son_gorulme` and adds `maks_seviye`, and records that the lead
approved it. As things stand, a correctly-formed track B anomaly record **fails
validation** against the track A schema on two counts: a missing required
property, and three additional ones. Track B implements the amended shape,
because the decision record is authoritative for this track. The schema needs the
corresponding edit before the contract check can pass on both sides.

**2. (Resolved by the integration decisions: `gridup.modul_durum`, one row per
packet. Track B reads it — item 8.) `modul_durum.besleme` and `modul_durum.sinyal` are accepted and then
discarded.** Contract ② declares both, `modul_paketi.schema.json` requires them,
and `toplama/toplama/kayit.py` persists only `yazilim_surumu` and `son_gorulme`
into `gridup.modul`. There is no table holding either field, current or
historical. Consequence for this layer: scenario 7 is "besleme kaybı, sinyal
zayıflığı, saat kayması", and only the third is detectable. `modul_saglik` is
therefore implemented on silence and clock drift alone. Loss of supply — which
section 7.3 describes as the entire reason the module carries a backup store — is
not visible to the detector. Wiring it up is a few lines in
`katman0_sensor._modul_sagligi` once somewhere to read it from exists.

**3. (Still true on track A's side; the index now lives in `100_analiz.sql`.) No index supports the scan loop's main query.** `gridup.olcum` is indexed on
`(modul_id, olcum_tipi, zaman)` and on `zaman DESC`; the scan loop's range query
is on `alindi_zaman`, which track A never queries by. Without an index every turn
is a sequential scan of the partition. Track B's migration adds
`olcum_alindi_zaman_idx` — additive, changing no column and no constraint, so it
is safe on a shared schema.

**4. Item 3 of section 11.1 is now implemented, on track B's side.** The
monotonic sequence and time index the alarm service needs in order not to miss an
episode are `gridup.anomali.sira` (drawn from the same sequence as `id`, so their
orderings cannot disagree) and `anomali_son_gorulme_idx`.

**5. (Found during this review's local setup, not on track A's branch text
itself — recorded here because it fits this section, not because a code
change was made anywhere shared.) The exported `toplama/migrations/003_termal.sql`
this checkout's own setup instructions point at (`git archive
origin/feature/track-a toplama/migrations sozlesmeler`) still declares
`termal_kare.piksel_verisi JSONB`, while this file's own §11 ("Binary frame
(11)") and `fikstur.py`/`api.py` have always treated it as `bytea` (int16 LE).
A local, uncommitted patch to the exported copy (never to the shared
migration itself) was needed to run this delivery's test suite end to end
against a real database. Whether track A's actual current schema already
has the bytea column and this export is simply stale, or whether the
migration genuinely still says jsonb, was not otherwise determined — flagged
for track A to confirm, not fixed here.**

Nothing else diverged. Column names, types, enum values, the `[sutun, satir]`
pixel order, the 768-value row-major frame layout and the `kalite`/`deger`
relationship all match what this layer was built against.

**Since the integration phase** the schema and vocabularies are no longer
restated here at all, so this list cannot grow the same way: a divergence now
shows up as `tests/test_sozlesme.py` failing against track A's own files.

---

## Post-review corrections (D1–D5)

A technical review of PR #3 after it merged found real bugs and a design gap
in severity handling. This section records what changed, why, and — for D4 —
every threshold this package uses, its numeric value, where it comes from,
and where it is read. It does not touch `docs/izb-karar-kaydi.md`; these are
implementation corrections downstream of that record, not amendments to it.

### D1 — multi-time-scale detection

The original detection window (`PencereAyari.tespit_sn`, 6 hours) is right for
a sudden rise and structurally cannot see a fault that grows too slowly to
accumulate `Katman2Ayari.asgari_delta` worth of rise inside any given 6-hour
slice — a terminal drifting 45 → 60 °C over 10 days moves about 0.06 °C in any
six hours of that, which never clears the gate no matter how far the fault has
actually come by day 10.

A second, independent evaluation now runs alongside the fast one:
`Katman2YavasAyari` / `dedektor.katman2_taban._yavas_isinma`. It reads
`Katman2YavasAyari.pencere_sn` (21 days by default) of **daily SQL
aggregates** (`PencereGetirici._yavas_ozetler`, `date_trunc('day', ...)` +
`avg`/`max` — never raw samples pulled into Python), computes normalized
heating `(hot spot − ambient) / current^n` per day, fits a **Theil-Sen**
(median-of-pairwise-slopes) trend across those daily points — robust to a
single corrupted day-bucket, unlike an ordinary least-squares fit — and
compares the module's CURRENT normalized-heating level against ITS OWN level
from the EARLIEST few qualifying daily buckets in that same window.

**Why not a sliding baseline, and why an early-anchored one instead — the
crux of D1.** The existing 14-day sliding median/MAD
(`PencereAyari.taban_sn`/`taban_bosluk_sn`) is exactly the trap the slow path
exists to avoid: fed a 10-day linear drift, it absorbs the drift as the new
normal (verified as a regression test,
`tests/test_zaman_olcekleri.py::test_yavas_isinma_taban_cizgisi_yutulur` —
median ends up dragged toward the drifted value, robust z stays under the
fast path's own `izle` threshold). The slow path's reference is instead the
median of the OLDEST few qualifying buckets inside the SAME window being
evaluated, recomputed fresh every time rather than carried and updated turn
to turn. It cannot be poisoned by a fault developing WITHIN the window because
it never slides forward to re-absorb one. A fault already fully established
before the window even opens is a real, acknowledged limitation of any
window-based reference — not unique to this one — which is why the window
defaults to 21 days rather than the 14-day floor D1 asked for: more runway for
the early reference to predate a real fault's onset.

Missing ambient, missing/insufficient current data, or layer 0 having vetoed
either channel: the slow path is skipped for that module that turn, silently
— no default substituted (see D3 for why that specific failure mode matters).

**Performance.** An unbounded per-turn re-run of this query measurably broke
the T5 budget (see T5 below) — recomputing a days-scale trend every 30 s buys
nothing, so `PencereGetirici` now caches each module's slow-path result in
process memory and only re-queries after `Katman2YavasAyari.yenileme_sn` (1
hour default) has passed for that module.

### D2 — severity is an action, not a forecast

`izle` = keep watching, `uyari` = plan maintenance, `kritik` = act now.
Severity must read off the PRESENT, load-normalized condition; a forecast may
only appear as *text* inside `gerekce`, never as the reason a `Bulgu` carries
the severity it does.

- **Layer 2's own-history deviation** (`_sapma`, robust z) is capped at
  `izle` (`skor.esikle_tavanli`) — being unusual for ITS OWN history is not,
  alone, grounds for more. `Katman2Ayari.z_uyari`/`z_kritik` are kept to
  shape the score curve within the capped band, not removed.
- **Layer 2's trend** (`_egilim`, the OLS slope) no longer produces its own
  finding or severity at all. It survives as `_egilim_bilgisi`: text folded
  into an already-firing magnitude finding's `gerekce`, gated by the same
  `asgari_delta`/`asgari_egilim_ornek` as before. `egilim_izle` is now purely
  the "worth mentioning" floor; `egilim_uyari`/`egilim_kritik` only word the
  sentence and play no part in `esikle`.
- **Excess heating over ambient, load-normalized** (layer 3's
  `_akim_sicaklik`, and the slow path above) is mapped onto FIST 4-13's own
  bands: 1–10 K not reported, 11–20 → `izle`, 21–40 → `uyari`, >40 → `kritik`.
- **Difference vs a similar component** (phase-to-phase, pixel-vs-frame,
  module-vs-peers) is the same FIST 4-13 category, bands 1–3 K not reported,
  4–15 K → `uyari`, >15 K → `kritik`. Applied where the units allow it
  (Kelvin comparisons); phase-to-phase stays a current fraction and is NOT
  force-converted — see the threshold table below for the honest sourcing on
  each.
- **A configurable persistence delay** (`OlayAyari.bekleme_sn`, `olay.py`)
  now gates OPENING a new episode: a qualifying condition must recur across
  MEASUREMENT-time-advancing turns for `bekleme_sn` (15 minutes default,
  measured against detector/turn time — see `OlayDeposu._acilmaya_hazir`'s
  docstring for why turn time and not measurement time) before a fresh
  episode opens; an already-open episode is unaffected. The arc
  (`OlayAyari.bekleme_muaf`) is exempt and opens immediately, unchanged —
  the TVOC-2 is SIL-2 and has already decided.

### D3 — two fixes

1. **Layer 3's current-vs-temperature check** (`_akim_sicaklik`) used to
   credit a missing ambient channel with 0 °C, which (combined with an
   extreme current ratio) could report a critical `akim_sicaklik_sapmasi` for
   a module carrying nothing but a pure overload with no ambient sensor.
   It now returns no finding at all when the ambient channel is absent or
   layer-0-vetoed. Acceptance test A6
   (`tests/test_zaman_olcekleri.py::test_a6_...`) reproduces the scenario.
2. **Layer 0's physical-range check** used to run after the minimum-sample
   early return, so a channel with fewer than `Katman0Ayari.asgari_ornek`
   samples — one of them physically impossible — was waved through as merely
   "unjudged". The range check now runs first, unconditionally.
   `tests/test_katmanlar.py::test_kanal_sagligi_aralik_disi_az_ornekle`.

### D5 — new labelled scenarios

`senaryolar.py` gained one slow-developing loose-terminal scenario
(`senaryo_08_gevsek_klemens_yavas`, days-scale, current and ambient steady —
the same fault as scenario 1, driven by `Uretec.uret`'s new `yavas_bozucu`
hook rather than the fast `bozucu` one) and two hard negatives: ambient
rising over days with the surface following it (load-normalized heating
stays flat), and a sustained ~40% load increase over days with the
temperature rise consistent with I² (`asiri_yuk`'s own fault, not a loose
terminal — must never surface as `akim_sicaklik_sapmasi`). These are the
labelled/regression set (section 2.7); metrics from it are reported as
"labelled set", never "blind test" — see the [Kör test protokolü](#kör-test-protokolü)
section for the difference.

### D4 — threshold traceability

Every threshold, window and exponent in `ayar.py`, its default, its basis,
and where it is used. Basis is one of: **FIST 4-13** (U.S. Bureau of
Reclamation, infrared inspection of electrical equipment), **vendor
example** (a manufacturer's published model, not a standard), or
**engineering default, unverified** (a deliberate, documented choice with no
external citation — never invented as one).

**`VeritabaniAyari`**

| Field | Value | Basis | Used in |
|---|---|---|---|
| `sorgu_zaman_asimi_ms` | 30000 | engineering default, unverified | every DB cursor |

**`TaramaAyari` (K1, the scan loop)**

| Field | Value | Basis | Used in |
|---|---|---|---|
| `periyot_sn` | 30 s | engineering default — set from T5's own measurement, not a spec value | `tarama.py` |
| `emniyet_payi_sn` | 1 s | engineering default, unverified | `tarama.py._aralik_sonu` |
| `ilk_imlec_geri_sn` | 3600 s | engineering default, unverified | cold-start cursor |
| `azami_aralik_sn` | 6 h | engineering default, unverified | catch-up cap |

**`PencereAyari` (evaluation windows)**

| Field | Value | Basis | Used in |
|---|---|---|---|
| `tespit_sn` (fast detection window) | 6 h | decision record's worked example (section 5) | all four layers |
| `taban_sn` (fast baseline window) | 14 days | engineering default — "far longer than the detection window" per the poisoning defence, section 5 | `katman2_taban._sapma` |
| `taban_bosluk_sn` | 6 h | engineering default, unverified | poisoning defence part 2 |
| `asgari_taban_ornek` | 20 | engineering default, unverified | layer 2 cold-start gate |
| `komsu_sn` | 6 h | engineering default, unverified | layer 3 module-vs-module |
| `temsil_ornek` | 5 | engineering default, unverified | "representative value" median everywhere |

**`Katman0Ayari` (sensor health)**

| Field | Value | Basis | Used in |
|---|---|---|---|
| `kalite_orani` | 0.5 | engineering default, unverified | quality-flag test |
| `asgari_ornek` | 6 | engineering default, unverified | minimum-sample gate |
| `donuk_ardisik` | 12 | engineering default — "two minutes at the contract's 10 s cadence" | frozen-sensor test |
| `donuk_tolerans` | 1e-6 | sensor quantisation floor, unverified | frozen-sensor test |
| `sessizlik_sn` | 900 s | engineering default, unverified | silence finding |
| `saat_kaymasi_sn` | 120 s | engineering default, unverified | clock-drift finding |
| `ileri_tarih_tolerans_sn` | 5 s | NTP-scatter allowance, unverified | future-dated test |
| `besleme_yedek_ardisik` | 2 | engineering default, unverified | backup-power finding |
| `sinyal_zayif_dbm` | −100 dBm | LoRa/NB-IoT link-budget rule of thumb, unverified as a citation | weak-signal finding |
| severities (`kalite`/`donuk`/`aralik_disi`/`sessizlik`/`besleme` = `uyari`; `saat_kaymasi`/`sinyal` = `izle`) | — | engineering default — "a sensor fault is a maintenance ticket, not a grid emergency" | layer 0 |

**`Katman1Ayari` (absolute limits) — audited, not changed by D2**

| Field | Value | Basis | Used in |
|---|---|---|---|
| `termal_izle`/`uyari`/`kritik` | 70 / 90 / 130 °C | decision record cites TEDAS spec + material limits; 130 °C is the record's own worked-scenario insulation limit — **not independently verified against the TEDAS document by this review** | layer 1 hot-spot |
| `ortam_izle`/`uyari`/`kritik` | 45 / 55 / 65 °C | engineering default, unverified | layer 1 ambient |
| `nem_izle`/`uyari`/`kritik` | 75 / 85 / 95 % | engineering default (condensation risk), unverified | layer 1 humidity |
| `faz_izle`/`uyari`/`kritik` | 10 / 20 / 30 % | NEMA-style imbalance percentage, unverified as a specific citation | layer 1 phase |
| `faz_asgari_akim` | 20 A | engineering default, unverified | phase-imbalance noise floor |
| `ark_esik` | 0.5 | pass-through of the TVOC-2's own certified decision, not this system's threshold | arc finding |

**`Katman2Ayari` (fast baseline deviation)**

| Field | Value | Basis | Used in |
|---|---|---|---|
| `z_izle`/`z_uyari`/`z_kritik` | 3.5 / 6.0 / 10.0 | robust-z convention (comparable to a standard-deviation count); **D2: capped at `izle`, `uyari`/`kritik` now only shape the score curve** | `_sapma` |
| `asgari_mad` | 0.3 | ~1 sensor quantisation step, unverified | MAD floor |
| `egilim_izle`/`uyari`/`kritik` | 0.5 / 1.5 / 4.0 °C/h | engineering default, unverified; **D2: no longer set severity — `izle` is a "worth mentioning" floor, `uyari`/`kritik` only word the sentence** | `_egilim_bilgisi` |
| `asgari_delta` | 5.0 | engineering default, unverified | trend total-rise gate |
| `asgari_egilim_ornek` | 8 | engineering default, unverified | trend sample-count gate |

**`Katman2YavasAyari` (slow path, new in D1)**

| Field | Value | Basis | Used in |
|---|---|---|---|
| `pencere_sn` | 21 days | D1 asked for "at least 14 days"; 21 chosen for early-reference runway, engineering default | slow window |
| `kova_sn` | 24 h | engineering default — thermal lag itself is hours long, an hourly bucket mostly re-measures it | SQL bucket width |
| `asgari_akim` | 5 A | mirrors `Katman3Ayari.akim_asgari` | normalized-heating noise floor |
| `yuk_ustel` (n) | 2 | I²R, physics-derived | normalization exponent |
| `asgari_kova` | 10 | engineering default, unverified | slow-path cold-start gate |
| `temsil_kova` | 3 | mirrors `PencereAyari.temsil_ornek` | robust current/reference level |
| `asiri_isinma_izle`/`uyari`/`kritik` | 11 / 21 / 40 °C | **FIST 4-13**, same bands as `Katman3Ayari.aciklanamayan_*` | slow-path severity |
| `yenileme_sn` | 3600 s | engineering default — see T5 below for the measurement that set it | `PencereGetirici`'s slow-path cache |

Note on `yuk_ustel`: ABB publishes a vendor thermal model using **n = 1.6**
for some busbar/connector geometries — a vendor example, not a standard, and
not adopted here. 2 (the I²R physics model, also used by layer 3) is the
default.

**`Katman3Ayari` (relationships)**

| Field | Value | Basis | Used in |
|---|---|---|---|
| `sicaklik_artis_esigi` | 10 °C | aligned to FIST 4-13's own "not reported" floor below | worth-checking gate |
| `aciklanamayan_izle`/`uyari`/`kritik` | 11 / 21 / 40 °C | **FIST 4-13** ("excess heating over ambient") — corrected in D2 from the previous unsourced 8/15/30 | `_akim_sicaklik` |
| `akim_asgari` | 5 A | engineering default, unverified | I² ratio noise floor |
| `faz_sapma_izle`/`uyari`/`kritik` | 0.08 / 0.15 / 0.25 (fraction) | **engineering default, unverified — deliberately NOT converted to FIST's Kelvin bands**: this is a current-imbalance fraction, not a temperature difference, and forcing a Kelvin citation onto it would misrepresent the source | `_faz_faz` |
| `notr_orani` | 0.20 | engineering default, unverified | neutral-current corroboration |
| `piksel_ayrisma_izle`/`uyari`/`kritik` | 6 / 8 / 15 °C | **FIST 4-13 shape** (1–3 not reported / 4–15 uyari / >15 kritik), `izle`/`uyari` raised above FIST's literal 4 K specifically for noise-floor robustness — verified against this project's own noisy-healthy fixture during validation; `kritik` at FIST's literal 15 K. Corrected from the previous unsourced 8/15/25 | `_komsu_piksel` |
| `piksel_kararlilik_orani` | 0.6 | engineering default, unverified | hot-pixel stability gate |
| `modul_ayrisma_izle`/`uyari`/`kritik` | 6 / 8 / 15 °C | same as `piksel_ayrisma_*` above, same reasoning | `_modul_modul` |
| `asgari_komsu` | 2 | engineering default, unverified | peer-count gate |
| `komsu_kapsami` | "saha" | operational choice, not a threshold | peer scope |
| `ortak_hareket_delta` | 3.0 °C | engineering default, unverified | common-movement suppression |
| `ortak_hareket_orani` | 0.6 | engineering default, unverified | common-movement suppression |

**`OlayAyari` (episode lifecycle)**

| Field | Value | Basis | Used in |
|---|---|---|---|
| `histerezis_sn` | 30 min | decision record, section 6.5 ("about 30 minutes") | closing hysteresis |
| `bekleme_sn` (new in D2) | 15 min | engineering default — comfortably above the 30 s scan period, comfortably below the hours-to-weeks fault timescales this system targets | opening delay-on |
| `bekleme_muaf` | `{ark}` | section 3.5 — the TVOC-2 is SIL-2 and has already decided | delay-on exemption |

**`ApiAyari`** — no detection thresholds; page sizes and pool bounds are
operational, not physical, and not included above.

---

## T5 — ölçeklenebilirlik raporu

```
python -m analiz.yuk --moduller 10,50,100 --tur 10
```

**Donanım:** 4 fiziksel / 4 mantıksal çekirdek, 16.5 GB RAM,
Intel(R) Xeon(R) Processor @ 2.10GHz, cgroup CPU sınırı yok.
PostgreSQL 16 aynı makinede.

Scan period **30 s** (the default), 15 days of baseline history per module,
detection window sampled at the contract's 10 s cadence, 15% of each fleet
carrying an injected fault.

```
 modül  veri satırı   tur ort      p95  satır/tur  çekirdek-sn  ms/modül    bellek  doluluk  mod/çekirdek  yetişiyor
    10      311,610    2.029s   2.705s        270         2.08       208    164.0M       9%           144       evet
    50    1,558,050   11.177s  14.541s       1350        11.45       229    464.5M      48%           131       evet
   100    3,116,100   19.449s  22.687s       2700        19.89       199    758.6M      76%           151       evet
```

`çekirdek-sn` is CPU core-seconds per turn, **detector process plus PostgreSQL
backends**. The queries run in separate server processes and their cost never
appears in the detector's own `cpu_times()`, so a CPU figure that counted only
the Python side would be roughly half the real bill.

### Sonuç: 100 modül 30 saniyelik periyotta yetişiyor

p95 turn duration 22.7 s against a 30 s period — **76% duty, with headroom but
not a lot of it.** Section 7.7's 100-module target is met on default settings.

At the previous 10 s default the same fleet did not keep up: 19.9 core-seconds
of work per turn against a 10 s budget is ~199% duty, and the detector falls
permanently behind. That is why the default moved (see `ayar.TaramaAyari`).

### Kapasite: çekirdek başına ~151 modül

Stated per core rather than as a duration, because a turn duration is only true
of the machine it was measured on:

| | |
|---|---|
| modül başına çekirdek zamanı | **199 ms** (10/50/100 modülde 208 / 229 / 199 ms) |
| 30 sn periyotta çekirdek başına kapasite | **~151 modül** |
| 10 sn periyotta çekirdek başına kapasite | ~50 modül |

Per-module cost is flat across a tenfold range in fleet size (208 → 229 → 199
ms), which is what the design predicts: the work is a per-module window fetch
and a per-module baseline, and neither depends on how many other modules exist.
That flatness is what makes the capacity figure usable — it extrapolates because
the underlying cost does not change with scale.

Carrying it to other hardware is one ratio: a core 1.5× faster carries ~1.5×
as many modules.

### Tek çekirdek — varsayım değil, ölçüm

The previous run showed process CPU close to wall time, which *suggests* serial
work but does not establish it: the detector's process CPU excludes the
PostgreSQL backends it waits on, so a turn that was half Python and half SQL on
two different cores would show the same ratio. So the harness measures
system-wide CPU across the window instead.

```
Ortalama meşgul çekirdek: 1.16 / 4   (sistem geneli CPU ÷ duvar saati)
Tur içi paralellik:       1.02×      (19.89 çekirdek-sn ÷ 19.45 sn duvar saati)
```

**1.02× means essentially nothing overlaps.** The detector is one process, one
thread, evaluating modules in a loop; while a query runs, Python waits. Three of
the four cores on this box are idle during a turn.

The consequence for scaling advice is the point: **adding cores does not shorten
a turn.** A 16-core machine runs this at the same speed as a 4-core one. What
buys capacity is a longer period, or more detector processes.

### Nerede gidiyor

At 100 modules, ~6.7 s of the 19.4 s is SQL and the remaining ~12.7 s is Python:

| | ms/tur |
|---|---|
| pencere: ölçüm serileri | 2417 |
| taban çizgisi (medyan + MAD) | 2309 |
| pencere: son ölçüm | 1613 |
| pencere: termal özet | 353 |
| olay yazımı (33 çağrı) | 27 |
| tur aralık sorgusu | 4.8 |

The Python side is dominated by materialising the evaluation window: 6 hours at
10 s across 9 channels is ~19,000 samples per module, and each becomes a `Nokta`.
The detector layers themselves are cheap by comparison.

**İndeks etkisi.** The range query that opens every turn — a sequential scan over
3.1 million rows without it — costs **4.8 ms** at 100 modules. That is
`olcum_alindi_zaman_idx` doing its job; it is the index track A's migrations do
not have, because track A never queries by `alindi_zaman` (mismatch 3 above).

### Sınırı ötelemenin yolları

Not implemented — this delivery measures, it does not tune. In rough order of
return:

1. **Shard modules across processes.** The measured 1.02× says this is the only
   lever that uses the hardware already present. The cursor is per named cursor
   and the layers are pure functions of a window, so two detectors on disjoint
   module sets share nothing but the tables. Four processes on this box would
   carry ~600 modules at 30 s.
2. **Raise the period further.** Configuration (`tarama.periyot_sn`), and
   section 3.5 already argues the events we detect run on scales of minutes to
   hours. 60 s doubles capacity to ~300 modules per core.
3. **Stop building `Nokta` objects for the whole window.** The layers consume
   medians, slopes and endpoints; most of that could be computed in SQL, as the
   baseline already is. This is the largest single cost.
4. **Drop the `son ölçüm` query** (1.6 s/turn) in favour of `modul.son_gorulme`,
   which the contract maintains for exactly this question. Track B reads from
   `olcum` instead because `son_gorulme` only exists if track A's collector wrote
   it, and track B has to run standalone — so this one is a trade, not a free win.

---

## Düzeltme — P1'in kazanılan süre notu yanlıştı

The first delivery's README said, under "Extension points", that lead time could
not be computed because it "needs the injection's true onset — precisely what a
blind set withholds".

**That was wrong.** A blind set withholds the labels *while the detector runs*,
not while the evaluation runs. Section 4.4's protocol is explicit: the output is
frozen at step 3, the key is opened at step 4, and every metric is computed then
with the labels in hand. Lead time is computable and is now computed —
`kortest.SenaryoSonucu.kazanilan_sure_sn`.

What the earlier note got right, buried under the wrong conclusion, is that the
onset and critical times have to **come from the generator**, because nothing in
our database knows when an injected fault became critical. That is why
`kritik_esik` is a required part of the label format rather than something the
tool infers.

Measured on the labelled fixture set, with the loop replayed turn by turn: median
lead time **+4.0 hours**, from +5.8 h (overload) down to −0.1 h for the arc. The
negative one is correct and worth keeping visible — an arc is instantaneous, and
no monitoring system can warn ahead of it. The TVOC-2 trips in under a
millisecond and we relay the record.

---

## Conventions

Turkish for identifiers that mirror the contract (`olcum_tipi`, `seviye`, `tip`,
`kalite`, `durum`) because those values are on the wire, and for module names to
match the rest of the repository. English for comments. Turkish for `gerekce`,
because an operator reads it.
