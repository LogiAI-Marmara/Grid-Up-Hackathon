-- 001 — schema, migration bookkeeping, and the saha -> pano -> modul reference tree.
--
-- Requires PostgreSQL 14 or newer (declarative partitioning with foreign keys,
-- used in migration 002).
--
-- Everything lives in the `gridup` schema rather than `public`, so a shared
-- on-prem PostgreSQL instance can host this next to something else without a
-- name collision, and a `DROP SCHEMA gridup CASCADE` is a complete uninstall.
--
-- All migrations are idempotent: re-running them is a no-op, not an error.

CREATE SCHEMA IF NOT EXISTS gridup;

SET search_path TO gridup, public;

-- ---------------------------------------------------------------------------
-- Migration bookkeeping
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS gridup.sema_surum (
    surum       INTEGER     PRIMARY KEY,
    ad          TEXT        NOT NULL,
    uygulanma   TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE gridup.sema_surum IS
    'Which migrations have been applied. Lets any service check that the DB it is talking to is the one it was built against.';

-- ---------------------------------------------------------------------------
-- saha — substation / site. The first segment of modul_id.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS gridup.saha (
    saha_kodu   TEXT        PRIMARY KEY,
    ad          TEXT        NOT NULL,
    il          TEXT,
    ilce        TEXT,
    enlem       DOUBLE PRECISION,
    boylam      DOUBLE PRECISION,
    olusturma   TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Must be a legal first segment of a modul_id: no dashes, or the id could
    -- not be split back into its three parts.
    CONSTRAINT saha_kodu_bicim CHECK (saha_kodu ~ '^[A-Za-z0-9]{2,16}$'),
    CONSTRAINT saha_enlem_araligi CHECK (enlem IS NULL OR enlem BETWEEN -90 AND 90),
    CONSTRAINT saha_boylam_araligi CHECK (boylam IS NULL OR boylam BETWEEN -180 AND 180)
);

COMMENT ON TABLE gridup.saha IS 'Transformer substation. First segment of modul_id, e.g. TR041.';
COMMENT ON COLUMN gridup.saha.enlem IS 'Latitude, optional. The dashboard map uses it; nothing depends on it.';

-- ---------------------------------------------------------------------------
-- pano — switchboard inside a site. The second segment of modul_id.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS gridup.pano (
    saha_kodu   TEXT        NOT NULL REFERENCES gridup.saha (saha_kodu) ON DELETE CASCADE,
    pano_kodu   TEXT        NOT NULL,
    ad          TEXT,
    pano_tipi   TEXT        NOT NULL DEFAULT 'ag',
    guc_kva     NUMERIC(8, 1),
    olusturma   TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (saha_kodu, pano_kodu),
    CONSTRAINT pano_kodu_bicim CHECK (pano_kodu ~ '^[A-Za-z0-9]{2,16}$'),
    -- 'ag' = low voltage board (the 1600 kVA target), 'og' = medium voltage cell.
    CONSTRAINT pano_tipi_gecerli CHECK (pano_tipi IN ('ag', 'og')),
    CONSTRAINT pano_guc_pozitif CHECK (guc_kva IS NULL OR guc_kva > 0)
);

COMMENT ON TABLE gridup.pano IS 'Switchboard. Second segment of modul_id, e.g. P01.';

-- ---------------------------------------------------------------------------
-- modul — the measuring device. Third segment, and the id every other table
-- points at.
-- ---------------------------------------------------------------------------

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

    -- The contract says the hierarchy lives inside the id. This constraint is
    -- what makes that true instead of merely intended: a module cannot be
    -- registered under a panel its own id does not name.
    CONSTRAINT modul_id_bicim
        CHECK (modul_id = saha_kodu || '-' || pano_kodu || '-' || modul_kodu),

    CONSTRAINT modul_surum_bicim
        CHECK (yazilim_surumu IS NULL OR yazilim_surumu ~ '^\d+\.\d+\.\d+$')
);

COMMENT ON TABLE gridup.modul IS
    'Measuring module. modul_id is {saha}-{pano}-{modul}, e.g. TR041-P01-M1, and the CHECK guarantees it matches the FK columns.';
COMMENT ON COLUMN gridup.modul.son_gorulme IS
    'Denormalised cache of the last packet time, maintained by the collector. Answers "which modules went quiet?" without scanning the measurement table.';
COMMENT ON COLUMN gridup.modul.aktif IS
    'FALSE for a decommissioned module. History is kept; it just stops being expected to report.';

CREATE INDEX IF NOT EXISTS modul_pano_idx
    ON gridup.modul (saha_kodu, pano_kodu);

-- Finding modules that stopped reporting is a hot path for the health view and
-- for scenario 7; only active modules are ever asked about.
CREATE INDEX IF NOT EXISTS modul_son_gorulme_idx
    ON gridup.modul (son_gorulme DESC NULLS LAST)
    WHERE aktif;

INSERT INTO gridup.sema_surum (surum, ad)
VALUES (1, '001_sema_ve_referans')
ON CONFLICT (surum) DO NOTHING;
