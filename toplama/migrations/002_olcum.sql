-- 002 — the measurement table. Contract ① in long/narrow form.
--
-- Volume, from the decision record: 100 modules x ~6 measurement types every
-- 10 s is roughly 60 rows/s, ~5 million rows/day. A few days of synthetic data
-- is 15-20 million rows. That is ordinary for PostgreSQL, but it is enough that
-- the table is range-partitioned by month from the start — a load test is
-- allowed to fill one month and be dropped in one statement afterwards.
--
-- Full thermal frames deliberately do not live here; 768 values as 768 rows is
-- meaningless. See migration 003.

SET search_path TO gridup, public;

CREATE TABLE IF NOT EXISTS gridup.olcum (
    modul_id     TEXT             NOT NULL REFERENCES gridup.modul (modul_id) ON DELETE CASCADE,
    olcum_tipi   TEXT             NOT NULL,
    zaman        TIMESTAMPTZ      NOT NULL,
    deger        DOUBLE PRECISION,
    birim        TEXT             NOT NULL,
    kalite       TEXT             NOT NULL DEFAULT 'iyi',
    alindi_zaman TIMESTAMPTZ      NOT NULL DEFAULT now(),

    -- Natural key. Doubles as the dedup key: the collector can replay a packet
    -- with ON CONFLICT DO NOTHING and get exactly-once semantics for free,
    -- which matters because a module that loses its uplink retransmits.
    --
    -- Column order is deliberately (modul_id, olcum_tipi, zaman): the primary
    -- key index then also serves the read API's main query,
    -- "series of one type for one module between two timestamps", so no
    -- second index is needed for it. The partition key must be part of the PK,
    -- and zaman is, at the end where it is still usable as a range.
    PRIMARY KEY (modul_id, olcum_tipi, zaman),

    CONSTRAINT olcum_tipi_gecerli CHECK (olcum_tipi IN (
        'ortam_sicaklik', 'nem',
        'akim_l1', 'akim_l2', 'akim_l3', 'akim_notr',
        'termal_maks', 'termal_ort',
        'ark_olay'
    )),

    CONSTRAINT olcum_kalite_gecerli CHECK (kalite IN ('iyi', 'supheli', 'yok')),

    -- A value may only be missing when the quality field says there was no
    -- reading. Writing 0.0 for a dead sensor is exactly the confusion `kalite`
    -- exists to prevent.
    CONSTRAINT olcum_deger_var CHECK (deger IS NOT NULL OR kalite = 'yok'),

    -- The unit is determined by the measurement type; this pairing is the same
    -- one enums.OLCUM_BIRIM declares. Without it, a producer that mislabels
    -- amperes as Celsius writes silently wrong data that still looks valid.
    CONSTRAINT olcum_birim_uyumlu CHECK (
        (olcum_tipi IN ('ortam_sicaklik', 'termal_maks', 'termal_ort') AND birim = 'C')
     OR (olcum_tipi = 'nem' AND birim = '%')
     OR (olcum_tipi IN ('akim_l1', 'akim_l2', 'akim_l3', 'akim_notr') AND birim = 'A')
     OR (olcum_tipi = 'ark_olay' AND birim = 'olay')
    ),

    -- Sanity bounds, not alarm thresholds: a value outside these is a broken
    -- sensor or a broken encoder, and the detector should never see it. The
    -- alarm thresholds are track B's and live in the detector, not here.
    CONSTRAINT olcum_deger_araligi CHECK (
        deger IS NULL
     OR (olcum_tipi IN ('ortam_sicaklik') AND deger BETWEEN -40 AND 150)
     OR (olcum_tipi IN ('termal_maks', 'termal_ort') AND deger BETWEEN -40 AND 300)
     OR (olcum_tipi = 'nem' AND deger BETWEEN 0 AND 100)
     OR (olcum_tipi IN ('akim_l1', 'akim_l2', 'akim_l3', 'akim_notr') AND deger BETWEEN 0 AND 10000)
     OR (olcum_tipi = 'ark_olay' AND deger BETWEEN 0 AND 1000)
    )
) PARTITION BY RANGE (zaman);

COMMENT ON TABLE gridup.olcum IS
    'Contract 1, long/narrow. A new measurement type is a new row, never a schema change — that is what lets the extra-sensor decision stay deferred.';
COMMENT ON COLUMN gridup.olcum.zaman IS
    'Measurement time, stamped by the module itself. Stored as TIMESTAMPTZ; the collector parses the ISO 8601 Z string into it.';
COMMENT ON COLUMN gridup.olcum.alindi_zaman IS
    'Arrival time, stamped by the collector. Kept separate from zaman on purpose: if the network is slow the measurement time must stay the moment it was measured, and the difference between the two is what exposes module clock drift (scenario 7).';
COMMENT ON COLUMN gridup.olcum.deger IS
    'Real value in the real unit, decimal (C, A, %). Modbus integer scaling happens at the Modbus boundary only. NULL is legal only when kalite = ''yok''.';
COMMENT ON COLUMN gridup.olcum.kalite IS
    'iyi | supheli | yok. The only thing that separates a broken sensor reading 0 from a real 0 — scenario 6 rests entirely on this column.';

-- ---------------------------------------------------------------------------
-- Partitions
-- ---------------------------------------------------------------------------

-- Creates the monthly partition containing `ay`. Safe to call repeatedly; the
-- collector can call it on startup or a cron can run it a month ahead.
CREATE OR REPLACE FUNCTION gridup.olcum_bolum_olustur(ay DATE)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    bas DATE := date_trunc('month', ay)::DATE;
    bit DATE := (date_trunc('month', ay) + INTERVAL '1 month')::DATE;
    ad  TEXT := 'olcum_' || to_char(bas, 'YYYY_MM');
BEGIN
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS gridup.%I PARTITION OF gridup.olcum '
        'FOR VALUES FROM (%L) TO (%L)', ad, bas, bit);
    RETURN ad;
END;
$$;

COMMENT ON FUNCTION gridup.olcum_bolum_olustur(DATE) IS
    'Create the monthly olcum partition containing the given date. Idempotent.';

-- Demo and load-test window: the whole of 2026 plus a month either side, so
-- nobody has to think about partitions during the hackathon.
DO $$
DECLARE
    ay DATE;
BEGIN
    FOR ay IN
        SELECT generate_series(DATE '2025-12-01', DATE '2027-01-01', INTERVAL '1 month')::DATE
    LOOP
        PERFORM gridup.olcum_bolum_olustur(ay);
    END LOOP;
END;
$$;

-- Catch-all so an insert with an unexpected timestamp is never rejected. A
-- measurement that arrives with a wildly wrong clock is data about a fault
-- (scenario 7), not something to throw away at the door.
--
-- Caveat: once the default partition holds rows for month M, creating the real
-- partition for M fails until those rows are moved out. See README, "Partitions".
CREATE TABLE IF NOT EXISTS gridup.olcum_varsayilan PARTITION OF gridup.olcum DEFAULT;

-- ---------------------------------------------------------------------------
-- Secondary indexes
-- ---------------------------------------------------------------------------

-- "What happened across the whole fleet in this window" — the dashboard's live
-- view and every cross-module correlation the detector runs.
CREATE INDEX IF NOT EXISTS olcum_zaman_idx
    ON gridup.olcum (zaman DESC);

-- Suspect and missing readings are rare, and scenario 6 asks for exactly them.
-- A partial index keeps this nearly free on 5M rows/day.
CREATE INDEX IF NOT EXISTS olcum_kalite_idx
    ON gridup.olcum (modul_id, zaman DESC)
    WHERE kalite <> 'iyi';

INSERT INTO gridup.sema_surum (surum, ad)
VALUES (2, '002_olcum')
ON CONFLICT (surum) DO NOTHING;
