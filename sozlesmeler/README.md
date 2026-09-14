# /sozlesmeler — shared contracts

The boundary between the three tracks. Everything here is **shared property**:
track A produces against it, track B consumes and produces against it, track C
consumes it. A mismatch between two tracks does not crash — it produces wrong
numbers quietly, which is worse. That is why the vocabularies live in exactly
one place and a script checks that they still agree.

Source of truth for the decisions behind these files: `gridup-proje-karar-kaydi.md`,
sections 9–11.

> **Changing anything in this folder requires the lead's approval and an
> announcement to all three tracks.** Adding a value to an enum is a contract
> change. Adding a measurement *type* is not a schema change — that is the whole
> point of the long/narrow format.

## Files

| File | What it is | Owner / consumer |
|---|---|---|
| `enums.py` | Single source of truth for every shared vocabulary, plus id/time/geometry rules | all tracks |
| `olcum_kaydi.schema.json` | Contract ① — one measurement row | A → B |
| `modul_paketi.schema.json` | Contract ② — what a module puts on the wire | A → A (ingest) |
| `anomali.schema.json` | Contract ③ — anomaly engine output | B → C |
| `dogrula.py` | Consistency check between the schemas and `enums.py` | CI / pre-commit |

Contracts ④ (Modbus register map) and ⑤ (read API) are track C's and track B's
to land here; this delivery covers ①②③.

## Vocabularies

Verbatim from section 10 of the decision record. Values are Turkish because they
are on the wire; code and comments are English.

```
olcum_tipi:  ortam_sicaklik | nem | akim_l1 | akim_l2 | akim_l3 |
             akim_notr | termal_maks | termal_ort | ark_olay
seviye:      normal | izle | uyari | kritik
tip:         sicak_nokta | akim_sicaklik_sapmasi | faz_dengesizligi |
             nem_yuksek | ortam_sicaklik_yuksek | ark | sensor_arizasi |
             modul_saglik
kalite:      iyi | supheli | yok
durum:       acik | onaylandi | kapandi
besleme:     sebeke | yedek
```

## Usage

Python — import, never retype:

```python
from sozlesmeler.enums import OlcumTipi, Kalite, OLCUM_BIRIM, zaman_yaz

kayit = {
    "modul_id": "TR041-P01-M1",
    "zaman": zaman_yaz(),
    "olcum_tipi": OlcumTipi.ORTAM_SICAKLIK.value,
    "deger": 34.7,
    "birim": OLCUM_BIRIM[OlcumTipi.ORTAM_SICAKLIK].value,
    "kalite": Kalite.IYI.value,
}
```

Anything that is not Python — dashboard, Modbus server — reads the same values
as JSON instead of hardcoding them:

```bash
python enums.py > sozlukler.json
```

Validating a packet (`pip install jsonschema`). `modul_paketi` `$ref`s
`olcum_kaydi` by relative filename, so both documents must be in the registry:

```python
import json, jsonschema
from pathlib import Path
from referencing import Registry, Resource

adlar = ["olcum_kaydi.schema.json", "modul_paketi.schema.json", "anomali.schema.json"]
semalar = {a: json.loads(Path(a).read_text()) for a in adlar}
kayit = Registry().with_resources(
    [(a, Resource.from_contents(s)) for a, s in semalar.items()]
)

dogrulayici = jsonschema.Draft202012Validator(semalar["modul_paketi.schema.json"], registry=kayit)
dogrulayici.validate(paket)
```

Checking that the contracts are still self-consistent:

```bash
python dogrula.py    # exit 0 = schemas and enums.py agree
```

It walks every schema and fails if an `enum` list drifts from `enums.py`, if a
`modul_id`/`zaman` pattern differs from the canonical regex, if the frame length
stops being 768, or if any embedded example no longer validates.

## Rules that the schemas encode

**Identity.** `modul_id` is `{saha}-{pano}-{modul}`, e.g. `TR041-P01-M1`. The
hierarchy is inside the id, so the dashboard tree and the load-test grouping come
for free. `enums.modul_id_ayristir()` splits it.

**Time.** UTC, ISO 8601, literal `Z`. Offsets such as `+03:00` are **rejected**:
one timezone everywhere means nobody has to ask "was this local?" during the
demo. The module stamps `zaman`; the collector adds `alindi_zaman`. The gap
between them is how module clock drift becomes visible (scenario 7) — so the two
must never be conflated.

**Units.** Real units, decimal, in the database: `C`, `%`, `A`. Integer scaling
happens at the Modbus boundary only, and the multiplier lives in the register map.

**Thermal frame.** 32 columns × 24 rows = 768 values, **row-major** flat array,
decimal °C. Index of pixel *(sutun, satir)* is `satir * 32 + sutun` —
`enums.piksel_indeks()` / `enums.indeks_piksel()`.

**Pixel coordinate order is `[sutun, satir]` — x first.** The decision record's
example `[14, 9]` is ambiguous on its own and both tracks B and C draw from it;
this is the reading we fixed. It applies to `termal_ozet.maks_konum` and
`anomali.kanit.piksel` alike.

**Quadrants.** `bolge_ort` is four 16×12 zone means in the order top-left,
top-right, bottom-left, bottom-right. It gives the detector coarse spatial
context without transmitting the frame.

**Data policy.** `termal_kare` is `null` in normal operation and carries the full
768 values only when the module's own threshold logic fires. This is what the
"we process at the edge" claim reduces to in practice, and it is why the module
has to recognise an anomaly on its own — otherwise it could not know when to send
the frame.

## Interpretations we fixed

The decision record leaves these underspecified. They are refinements, not enum
changes; listed here so track B and C can object before the code hardens.

1. **`deger` may be `null` only when `kalite` is `yok`.** A dead sensor has no
   value; forcing it to emit `0.0` is exactly the confusion `kalite` exists to
   prevent. Every other quality level requires a number.
2. **`birim` is an enumerated set** — `C`, `%`, `A`, `olay` — and is determined
   by `olcum_tipi` (`enums.OLCUM_BIRIM`). The record fixes the units but not their
   spelling; without this, three tracks invent `degC` / `Celsius` / `°C`
   independently. `olay` is the unit for `ark_olay`, which is a count read from
   the TVOC-2, not a physical quantity.
3. **Sanity ranges per measurement type** (`enums.OLCUM_ARALIK`). These are *not*
   alarm thresholds — those are track B's. A value outside these bounds is a
   broken sensor or a broken encoder and the detector should never see it.
4. **`sinyal` is dBm**, integer, −120…0. **`yazilim_surumu` is semantic
   versioning.**
5. **`anomali.kanit` stays open-ended** (no `additionalProperties: false`) because
   different detector types point at different evidence, but the keys `kare_id`,
   `piksel`, `olcum_tipi`, `pencere`, `esik`, `olculen` are reserved and must keep
   the shapes declared in the schema. The dashboard may rely on those.
6. **`olcumler` may be empty** — a heartbeat packet with only `modul_durum` is
   valid, and is how a module on backup power reports that it is dying.

Two constraints are *not* expressible in JSON Schema and are enforced by the
collector instead: every `olcumler[].modul_id` must equal the packet's
`modul_id`, and `maks_konum` must point at the hottest pixel when `termal_kare`
is present.
