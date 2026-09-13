-- 003 — thermal summary and full frames.
--
-- The data policy from the decision record has two halves, and so does this
-- migration:
--
--   normally      -> the module sends a summary        -> gridup.termal_ozet
--   on anomaly    -> it attaches the full 768 values   -> gridup.termal_kare
--
-- Why termal_ozet exists at all, given that termal_maks and termal_ort are
-- already measurement types in gridup.olcum: the long/narrow format stores one
-- scalar per row and has nowhere to put the *spatial* part of the summary —
-- maks_konum and the four quadrant means. Dropping those would throw away the
-- module's on-board work, so the summary keeps its own table and the two
-- scalars are additionally projected into olcum, which is the generic
-- time-series path the read API and the detector use. The duplication is
-- deliberate and one-directional: termal_ozet is the source, olcum is the
-- queryable projection, and the collector writes both in one transaction.

SET search_path TO gridup, public;

-- ---------------------------------------------------------------------------
-- termal_ozet — one row per thermal sampling cycle
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS gridup.termal_ozet (
    modul_id      TEXT             NOT NULL REFERENCES gridup.modul (modul_id) ON DELETE CASCADE,
    zaman         TIMESTAMPTZ      NOT NULL,
    maks          DOUBLE PRECISION NOT NULL,
    maks_sutun    SMALLINT         NOT NULL,
    maks_satir    SMALLINT         NOT NULL,
    bolge_ort     DOUBLE PRECISION[] NOT NULL,
    alindi_zaman  TIMESTAMPTZ      NOT NULL DEFAULT now(),

    PRIMARY KEY (modul_id, zaman),

    CONSTRAINT termal_ozet_maks_araligi CHECK (maks BETWEEN -40 AND 300),

    -- Coordinates are [sutun, satir] — x first, matching the contract's [14, 9]
    -- example. 32 columns, 24 rows.
    CONSTRAINT termal_ozet_sutun_araligi CHECK (maks_sutun BETWEEN 0 AND 31),
    CONSTRAINT termal_ozet_satir_araligi CHECK (maks_satir BETWEEN 0 AND 23),

    -- Four 16x12 quadrants: top-left, top-right, bottom-left, bottom-right.
    CONSTRAINT termal_ozet_bolge_sayisi CHECK (array_length(bolge_ort, 1) = 4),
    CONSTRAINT termal_ozet_bolge_araligi CHECK (
        NOT EXISTS (
            SELECT 1 FROM unnest(bolge_ort) AS o(deger)
            WHERE o.deger IS NULL OR o.deger < -40 OR o.deger > 300
        )
    )
);

COMMENT ON TABLE gridup.termal_ozet IS
    'What the module derives on-board from the 32x24 array so the full frame does not have to be transmitted. The scalars are also projected into gridup.olcum as termal_maks / termal_ort.';
COMMENT ON COLUMN gridup.termal_ozet.maks_sutun IS 'Hot-pixel column, 0..31 (x).';
COMMENT ON COLUMN gridup.termal_ozet.maks_satir IS 'Hot-pixel row, 0..23 (y).';
COMMENT ON COLUMN gridup.termal_ozet.bolge_ort IS
    'Mean of each 16x12 quadrant: [top-left, top-right, bottom-left, bottom-right]. Coarse spatial context without the full frame.';

CREATE INDEX IF NOT EXISTS termal_ozet_zaman_idx
    ON gridup.termal_ozet (zaman DESC);

-- "Has the hot spot been sitting on the same pixel for an hour?" is the loose
-- terminal signature (scenario 1); this makes that query an index scan.
CREATE INDEX IF NOT EXISTS termal_ozet_konum_idx
    ON gridup.termal_ozet (modul_id, maks_sutun, maks_satir, zaman DESC);

-- ---------------------------------------------------------------------------
-- termal_kare — the evidence image, written only when something fired
-- ---------------------------------------------------------------------------

CREATE SEQUENCE IF NOT EXISTS gridup.termal_kare_sira;

CREATE TABLE IF NOT EXISTS gridup.termal_kare (
    kare_id       TEXT        PRIMARY KEY
                  DEFAULT 'kr_' || lpad(nextval('gridup.termal_kare_sira')::TEXT, 6, '0'),
    modul_id      TEXT        NOT NULL REFERENCES gridup.modul (modul_id) ON DELETE CASCADE,
    zaman         TIMESTAMPTZ NOT NULL,
    piksel_verisi JSONB       NOT NULL,
    satir_sayisi  SMALLINT    NOT NULL DEFAULT 24,
    sutun_sayisi  SMALLINT    NOT NULL DEFAULT 32,
    alindi_zaman  TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- A module produces at most one frame per instant; this makes frame writes
    -- idempotent under retransmission, same as the measurement table.
    CONSTRAINT termal_kare_tekil UNIQUE (modul_id, zaman),

    CONSTRAINT termal_kare_id_bicim CHECK (kare_id ~ '^[A-Za-z0-9_-]{1,64}$'),
    CONSTRAINT termal_kare_boyut CHECK (satir_sayisi = 24 AND sutun_sayisi = 32),

    -- 32 x 24 = 768 values, row-major flat array, decimal Celsius. Checking the
    -- length here rather than trusting the producer is cheap and catches a
    -- truncated radio frame at the door instead of in the dashboard.
    CONSTRAINT termal_kare_uzunluk CHECK (
        jsonb_typeof(piksel_verisi) = 'array'
        AND jsonb_array_length(piksel_verisi) = 768
    )
);

COMMENT ON TABLE gridup.termal_kare IS
    'Full 32x24 thermal frame, stored as one JSONB array rather than 768 measurement rows. Written only when the module''s threshold logic fires, as the evidence image behind an anomaly.';
COMMENT ON COLUMN gridup.termal_kare.kare_id IS
    'Referenced by anomali.kanit.kare_id. Auto-generated as kr_000001 if the producer does not supply one.';
COMMENT ON COLUMN gridup.termal_kare.piksel_verisi IS
    'JSONB array of 768 numbers, row-major: index of pixel (sutun, satir) is satir * 32 + sutun. Element order is the contract; do not reorder.';
COMMENT ON COLUMN gridup.termal_kare.satir_sayisi IS
    'Frame geometry, stored explicitly so a future sensor with a different resolution is a data change and not a silent reinterpretation of the array.';

CREATE INDEX IF NOT EXISTS termal_kare_modul_zaman_idx
    ON gridup.termal_kare (modul_id, zaman DESC);

-- Frames are rare (anomaly-only), so a plain btree on zaman is enough for
-- retention sweeps and for the "recent evidence" panel.
CREATE INDEX IF NOT EXISTS termal_kare_zaman_idx
    ON gridup.termal_kare (zaman DESC);

INSERT INTO gridup.sema_surum (surum, ad)
VALUES (3, '003_termal')
ON CONFLICT (surum) DO NOTHING;
