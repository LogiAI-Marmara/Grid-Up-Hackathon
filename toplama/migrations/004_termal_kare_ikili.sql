-- 004_termal_kare_ikili.sql — the evidence frame moves from JSONB to BYTEA.
--
-- Why: integration item 2 changes the policy to a full frame on every sampling
-- instant (30 s), which turns the frame from a rare anomaly attachment into a
-- constant stream. At 100 modules x 30 s, a JSONB array of 768 decimal numbers
-- costs roughly 430 MB/day — the same order as the measurement table itself, for
-- data whose own author (the module) already holds it as 1536 bytes of int16.
-- Storing the producer's exact bytes is both smaller (measured: 5137 -> 1536
-- bytes for a realistic frame, a ~70% reduction) and lossless: the decimal JSON
-- was a re-encoding of these bytes, and re-encoding is where a 0.05 degC
-- rounding difference comes from.
--
-- The byte form is correct independently of item 2: it is the module's own
-- representation either way, and it removes the re-encoding. Item 2 makes it
-- matter for volume.
--
-- The wire contract does not change: `POST /paket` still carries the 768-number
-- JSON array, and the API still returns it. Only the storage form changes.

BEGIN;

-- PostgreSQL forbids a subquery in both a CHECK expression and an ALTER ... USING
-- transform, so the per-element work lives in a function. IMMUTABLE because it
-- depends on nothing but its argument, which is also what lets it be used in the
-- USING clause.
CREATE OR REPLACE FUNCTION gridup.kare_kodla(kare JSONB) RETURNS BYTEA
LANGUAGE sql IMMUTABLE AS $fn$
  -- Each element becomes int16 little-endian at 0.1 degC: value 452 -> 45.2 degC.
  -- The low/high bytes are taken with `x & 255` and `(x >> 8) & 255`, which give
  -- the two's-complement pair PostgreSQL already uses for a negative smallint
  -- (-100 -> 0x9C 0xFF -> bytes 9c ff). int2send would be the obvious choice but
  -- it emits big-endian, which is not the contract.
  SELECT decode(
           string_agg(
             encode(set_byte(set_byte('\x0000'::bytea, 0, (t.deger & 255)),
                                             1, ((t.deger >> 8) & 255)), 'hex'),
             '' ORDER BY t.ord),
           'hex')
  FROM (
    SELECT round(v::numeric * 10)::int AS deger, ord
    FROM jsonb_array_elements_text(kare) WITH ORDINALITY AS e(v, ord)
  ) AS t
$fn$;

COMMENT ON FUNCTION gridup.kare_kodla(JSONB) IS
    'Contract ① frame encoder: 768 decimal Celsius values (JSON array) -> 1536 bytes of '
    'int16 little-endian, 0.1 degC per unit, row-major. Immutable so the migration can use '
    'it in ALTER ... USING; the collector uses it for every write.';

-- The old CHECK asserted jsonb_typeof / jsonb_array_length, which cannot apply
-- to a bytea column. Drop it before the type change, add the byte-length check
-- after — the column is never unconstrained, only re-constrained.
ALTER TABLE gridup.termal_kare
    DROP CONSTRAINT IF EXISTS termal_kare_uzunluk;

-- The type change is guarded so re-running this file is a no-op rather than an
-- error (migration 001 states the rule: every migration is idempotent). After the
-- first run the column is already BYTEA, and an unguarded `USING kare_kodla(...)`
-- would then be asked to encode bytes as if they were JSON.
--
-- USING converts existing rows when the migration runs on a populated database.
-- The conversion reproduces exactly the bytes the module would have sent for that
-- frame, so a pre-existing frame survives unchanged (verified on a real 768-value
-- frame: 5137 bytes of JSON -> 1536 bytes, first pixel decoded back to the same value).
DO $goc$
BEGIN
    IF (
        SELECT data_type FROM information_schema.columns
        WHERE table_schema = 'gridup' AND table_name = 'termal_kare' AND column_name = 'piksel_verisi'
    ) = 'jsonb' THEN
        ALTER TABLE gridup.termal_kare
            ALTER COLUMN piksel_verisi TYPE BYTEA USING gridup.kare_kodla(piksel_verisi);
    END IF;
END
$goc$;

-- 768 values x 2 bytes. Checking the length here rather than trusting the
-- producer is cheap and catches a truncated radio frame at the door instead of
-- in the dashboard — the same job the old array-length check did. Guarded for the
-- same idempotency reason: the constraint already exists on a second run.
DO $goc$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'gridup.termal_kare'::regclass AND conname = 'termal_kare_uzunluk'
    ) THEN
        ALTER TABLE gridup.termal_kare
            ADD CONSTRAINT termal_kare_uzunluk CHECK (octet_length(piksel_verisi) = 1536);
    END IF;
END
$goc$;

COMMENT ON COLUMN gridup.termal_kare.piksel_verisi IS
    'Full 32x24 thermal frame as raw int16 little-endian bytes, 0.1 degC per unit '
    '(value 452 -> 45.2 degC), row-major: index of pixel (sutun, satir) is satir * 32 + sutun. '
    '1536 bytes. Element order is the contract; do not reorder.';

COMMENT ON TABLE gridup.termal_kare IS
    'Full 32x24 thermal frame, stored as the module''s own int16 bytes rather than 768 JSON '
    'numbers. Written whenever the module sends a frame; the evidence image behind an anomaly '
    'always exists for the moment the anomaly is tied to.';

-- The index on zaman already exists from migration 003; frames are now frequent
-- rather than rare, so it stops being a convenience and becomes the retention
-- sweep's main index. Nothing to rebuild — the shape is the same either way.

INSERT INTO gridup.sema_surum (surum, ad)
VALUES (4, '004_termal_kare_ikili')
ON CONFLICT (surum) DO NOTHING;

COMMIT;