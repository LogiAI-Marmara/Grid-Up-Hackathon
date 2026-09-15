-- 000 — the contract-shaped tables track B reads from.
--
-- WHY THIS FILE EXISTS
--
-- These tables are track A's: `modul`, `olcum`, `termal_ozet`, `termal_kare`
-- are contracts 1 and 2, and track A owns their definition. Track B does not
-- own them and must not change them.
--
-- But track B has to be runnable, testable and demonstrable on its own, against
-- a database it can create from nothing — track A's branch is not merged, and a
-- detector that can only be tested when another track's service is running is a
-- detector that does not get tested. So this migration restates the contract
-- DDL, column for column and constraint for constraint, and every statement is
-- `IF NOT EXISTS`.
--
-- The consequence of the IF NOT EXISTS is the point: run track A's migrations
-- first and this file is a no-op; run this one first and track A's are. Neither
-- clobbers the other, because they describe the same tables.
--
-- If the two ever disagree, `tests/test_sozlesme.py` is what catches it: it
-- asserts this schema's column names and types against the contract as track B
-- understands it, so a drift shows up as a failing test and not as quietly
-- wrong numbers six weeks later.
--
-- Requires PostgreSQL 14+ (declarative partitioning with foreign keys).

CREATE SCHEMA IF NOT EXISTS gridup;

SET search_path TO gridup, public;

CREATE TABLE IF NOT EXISTS gridup.sema_surum (
    surum       INTEGER     PRIMARY KEY,
    ad          TEXT        NOT NULL,
    uygulanma   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Reference tree: saha -> pano -> modul. The hierarchy lives inside modul_id.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS gridup.saha (
    saha_kodu   TEXT        PRIMARY KEY,
    ad          TEXT        NOT NULL,
    il          TEXT,
    ilce        TEXT,
    enlem       DOUBLE PRECISION,
    boylam      DOUBLE PRECISION,
    olusturma   TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT saha_kodu_bicim CHECK (saha_kodu ~ '^[A-Za-z0-9]{2,16}$'),
    CONSTRAINT saha_enlem_araligi CHECK (enlem IS NULL OR enlem BETWEEN -90 AND 90),
    CONSTRAINT saha_boylam_araligi CHECK (boylam IS NULL OR boylam BETWEEN -180 AND 180)
);

CREATE TABLE IF NOT EXISTS gridup.pano (
    saha_kodu   TEXT        NOT NULL REFERENCES gridup.saha (saha_kodu) ON DELETE CASCADE,
    pano_kodu   TEXT        NOT NULL,
    ad          TEXT,
    pano_tipi   TEXT        NOT NULL DEFAULT 'ag',
    guc_kva     NUMERIC(8, 1),
    olusturma   TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (saha_kodu, pano_kodu),
    CONSTRAINT pano_kodu_bicim CHECK (pano_kodu ~ '^[A-Za-z0-9]{2,16}$'),
    CONSTRAINT pano_tipi_gecerli CHECK (pano_tipi IN ('ag', 'og')),
    CONSTRAINT pano_guc_pozitif CHECK (guc_kva IS NULL OR guc_kva > 0)
);

CREATE TABLE IF NOT EXISTS gridup.modul (
    modul_id        TEXT        PRIMARY KEY,
    saha_kodu       TEXT        NOT NULL,
    pano_kodu       TEXT        NOT NULL,
    modul_kodu      TEXT        NOT NULL,
    aktif           BOOLEAN     NOT NULL DEFAULT TRUE,
    kurulum_zaman   TIMESTAMPTZ,
    yazilim_surumu  TEXT,
    son_gorulme     TIMESTAMPTZ,
    konum_notu      TEXT,
    olusturma       TIMESTAMPTZ NOT NULL DEFAULT now(),

    FOREIGN KEY (saha_kodu, pano_kodu)
        REFERENCES gridup.pano (saha_kodu, pano_kodu) ON DELETE CASCADE,

    CONSTRAINT modul_kodu_bicim CHECK (modul_kodu ~ '^[A-Za-z0-9]{2,16}$'),
    CONSTRAINT modul_id_bicim
        CHECK (modul_id = saha_kodu || '-' || pano_kodu || '-' || modul_kodu),
    CONSTRAINT modul_surum_bicim
        CHECK (yazilim_surumu IS NULL OR yazilim_surumu ~ '^\d+\.\d+\.\d+$')
);

CREATE INDEX IF NOT EXISTS modul_pano_idx
    ON gridup.modul (saha_kodu, pano_kodu);

CREATE INDEX IF NOT EXISTS modul_son_gorulme_idx
    ON gridup.modul (son_gorulme DESC NULLS LAST)
    WHERE aktif;

-- ---------------------------------------------------------------------------
-- olcum — contract 1, long/narrow, range-partitioned by month.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS gridup.olcum (
    modul_id     TEXT             NOT NULL REFERENCES gridup.modul (modul_id) ON DELETE CASCADE,
    olcum_tipi   TEXT             NOT NULL,
    zaman        TIMESTAMPTZ      NOT NULL,
    deger        DOUBLE PRECISION,
    birim        TEXT             NOT NULL,
    kalite       TEXT             NOT NULL DEFAULT 'iyi',
    alindi_zaman TIMESTAMPTZ      NOT NULL DEFAULT now(),

    PRIMARY KEY (modul_id, olcum_tipi, zaman),

    CONSTRAINT olcum_tipi_gecerli CHECK (olcum_tipi IN (
        'ortam_sicaklik', 'nem',
        'akim_l1', 'akim_l2', 'akim_l3', 'akim_notr',
        'termal_maks', 'termal_ort',
        'ark_olay'
    )),

    CONSTRAINT olcum_kalite_gecerli CHECK (kalite IN ('iyi', 'supheli', 'yok')),

    CONSTRAINT olcum_deger_var CHECK (deger IS NOT NULL OR kalite = 'yok'),

    CONSTRAINT olcum_birim_uyumlu CHECK (
        (olcum_tipi IN ('ortam_sicaklik', 'termal_maks', 'termal_ort') AND birim = 'C')
     OR (olcum_tipi = 'nem' AND birim = '%')
     OR (olcum_tipi IN ('akim_l1', 'akim_l2', 'akim_l3', 'akim_notr') AND birim = 'A')
     OR (olcum_tipi = 'ark_olay' AND birim = 'olay')
    ),

    -- Sanity bounds, not alarm thresholds. Alarm thresholds are track B's and
    -- live in ayar.py; a value outside these is a broken sensor or encoder.
    CONSTRAINT olcum_deger_araligi CHECK (
        deger IS NULL
     OR (olcum_tipi IN ('ortam_sicaklik') AND deger BETWEEN -40 AND 150)
     OR (olcum_tipi IN ('termal_maks', 'termal_ort') AND deger BETWEEN -40 AND 300)
     OR (olcum_tipi = 'nem' AND deger BETWEEN 0 AND 100)
     OR (olcum_tipi IN ('akim_l1', 'akim_l2', 'akim_l3', 'akim_notr') AND deger BETWEEN 0 AND 10000)
     OR (olcum_tipi = 'ark_olay' AND deger BETWEEN 0 AND 1000)
    )
) PARTITION BY RANGE (zaman);

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

CREATE TABLE IF NOT EXISTS gridup.olcum_varsayilan PARTITION OF gridup.olcum DEFAULT;

CREATE INDEX IF NOT EXISTS olcum_zaman_idx
    ON gridup.olcum (zaman DESC);

CREATE INDEX IF NOT EXISTS olcum_kalite_idx
    ON gridup.olcum (modul_id, zaman DESC)
    WHERE kalite <> 'iyi';

-- The scan loop's range query is `alindi_zaman > cursor ORDER BY alindi_zaman`.
-- Track A has no index for that because track A never asks the question; without
-- one, every turn is a sequential scan of the partition. This index is track B's
-- and is additive — it changes no column and no constraint.
CREATE INDEX IF NOT EXISTS olcum_alindi_zaman_idx
    ON gridup.olcum (alindi_zaman);

-- ---------------------------------------------------------------------------
-- termal_ozet / termal_kare — contract 2's thermal halves.
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
    -- Coordinates are [sutun, satir] — x first. 32 columns, 24 rows.
    CONSTRAINT termal_ozet_sutun_araligi CHECK (maks_sutun BETWEEN 0 AND 31),
    CONSTRAINT termal_ozet_satir_araligi CHECK (maks_satir BETWEEN 0 AND 23),
    CONSTRAINT termal_ozet_bolge_sayisi CHECK (cardinality(bolge_ort) = 4),
    CONSTRAINT termal_ozet_bolge_araligi CHECK (
        array_position(bolge_ort, NULL) IS NULL
        AND bolge_ort[1] BETWEEN -40 AND 300
        AND bolge_ort[2] BETWEEN -40 AND 300
        AND bolge_ort[3] BETWEEN -40 AND 300
        AND bolge_ort[4] BETWEEN -40 AND 300
    )
);

CREATE INDEX IF NOT EXISTS termal_ozet_zaman_idx
    ON gridup.termal_ozet (zaman DESC);

CREATE INDEX IF NOT EXISTS termal_ozet_konum_idx
    ON gridup.termal_ozet (modul_id, maks_sutun, maks_satir, zaman DESC);

CREATE INDEX IF NOT EXISTS termal_ozet_alindi_zaman_idx
    ON gridup.termal_ozet (alindi_zaman);

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

    CONSTRAINT termal_kare_tekil UNIQUE (modul_id, zaman),
    CONSTRAINT termal_kare_id_bicim CHECK (kare_id ~ '^[A-Za-z0-9_-]{1,64}$'),
    CONSTRAINT termal_kare_boyut CHECK (satir_sayisi = 24 AND sutun_sayisi = 32),
    -- 32 x 24 = 768 values, row-major flat array. Index of (sutun, satir) is
    -- satir * 32 + sutun.
    CONSTRAINT termal_kare_uzunluk CHECK (
        jsonb_typeof(piksel_verisi) = 'array'
        AND jsonb_array_length(piksel_verisi) = 768
    )
);

CREATE INDEX IF NOT EXISTS termal_kare_modul_zaman_idx
    ON gridup.termal_kare (modul_id, zaman DESC);

CREATE INDEX IF NOT EXISTS termal_kare_zaman_idx
    ON gridup.termal_kare (zaman DESC);

INSERT INTO gridup.sema_surum (surum, ad) VALUES (1, '001_sema_ve_referans') ON CONFLICT (surum) DO NOTHING;
INSERT INTO gridup.sema_surum (surum, ad) VALUES (2, '002_olcum')            ON CONFLICT (surum) DO NOTHING;
INSERT INTO gridup.sema_surum (surum, ad) VALUES (3, '003_termal')           ON CONFLICT (surum) DO NOTHING;
