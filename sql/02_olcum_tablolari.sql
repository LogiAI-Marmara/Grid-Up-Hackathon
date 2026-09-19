-- 02_olcum_tablolari.sql
-- Grid Up Hackathon - Bölümlendirilmiş (Partitioned) Ölçüm Tablosu
-- Sensörlerden gelen skaler ölçümler (Akımlar, Sıcaklıklar, Nem, Ark)

SET search_path TO gridup, public;

-- ---------------------------------------------------------------------------
-- 1. Ana Bölümlü Ölçüm Tablosu (Zaman Aralıklı Bölümleme)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gridup.olcum (
    modul_id        TEXT        NOT NULL REFERENCES gridup.modul (modul_id) ON DELETE CASCADE,
    olcum_tipi      TEXT        NOT NULL,
    zaman           TIMESTAMPTZ NOT NULL,
    deger           DOUBLE PRECISION NOT NULL,
    birim           TEXT        NOT NULL,
    kalite          TEXT        NOT NULL DEFAULT 'iyi',
    alindi_zaman    TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT olcum_pk PRIMARY KEY (modul_id, olcum_tipi, zaman),
    CONSTRAINT olcum_kalite_kural CHECK (kalite IN ('iyi', 'supheli', 'yok')),
    CONSTRAINT olcum_tipi_kural CHECK (
        olcum_tipi IN (
            'ortam_sicaklik', 'nem',
            'akim_l1', 'akim_l2', 'akim_l3', 'akim_notr',
            'termal_maks', 'termal_ort',
            'ark_olay'
        )
    )
) PARTITION BY RANGE (zaman);

COMMENT ON TABLE gridup.olcum IS
    'Zaman aralığına göre bölümlenmiş skaler sensör ölçüm tablosu.';

-- ---------------------------------------------------------------------------
-- 2. Varsayılan (Default) Bölüm
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gridup.olcum_varsayilan
    PARTITION OF gridup.olcum DEFAULT;

-- ---------------------------------------------------------------------------
-- 3. 2026 Yılı Aylık Bölümleri (Hackathon ve Canlı Çalışma Dönemi)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gridup.olcum_2026_09
    PARTITION OF gridup.olcum
    FOR VALUES FROM ('2026-09-01 00:00:00+00') TO ('2026-10-01 00:00:00+00');

CREATE TABLE IF NOT EXISTS gridup.olcum_2026_10
    PARTITION OF gridup.olcum
    FOR VALUES FROM ('2026-10-01 00:00:00+00') TO ('2026-11-01 00:00:00+00');

-- ---------------------------------------------------------------------------
-- 4. Sorgu Hızlandırma İndeksleri
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS olcum_modul_zaman_idx
    ON gridup.olcum (modul_id, zaman DESC);

CREATE INDEX IF NOT EXISTS olcum_zaman_idx
    ON gridup.olcum (zaman DESC);

CREATE INDEX IF NOT EXISTS olcum_alindi_zaman_idx
    ON gridup.olcum (alindi_zaman DESC);

CREATE INDEX IF NOT EXISTS olcum_tip_zaman_idx
    ON gridup.olcum (olcum_tipi, zaman DESC);
