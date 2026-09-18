-- 03_termal_tablolari.sql
-- Grid Up Hackathon - Termal Kamera Veri Tabloları
-- 32x24 (768 piksel) tam termal matris ve termal özet kayıtları

SET search_path TO gridup, public;

CREATE SEQUENCE IF NOT EXISTS gridup.termal_kare_sira START WITH 1;

-- ---------------------------------------------------------------------------
-- 1. Tam Termal Kare Tablosu (Bytea formatında int16 LE, 1536 bayt)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gridup.termal_kare (
    kare_id         TEXT        PRIMARY KEY DEFAULT ('kr_' || lpad(nextval('gridup.termal_kare_sira')::TEXT, 6, '0')),
    modul_id        TEXT        NOT NULL REFERENCES gridup.modul (modul_id) ON DELETE CASCADE,
    zaman           TIMESTAMPTZ NOT NULL,
    piksel_verisi   BYTEA       NOT NULL,
    satir_sayisi    SMALLINT    NOT NULL DEFAULT 24,
    sutun_sayisi    SMALLINT    NOT NULL DEFAULT 32,
    alindi_zaman    TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT termal_kare_tekil UNIQUE (modul_id, zaman),
    CONSTRAINT termal_kare_boyut CHECK (satir_sayisi = 24 AND sutun_sayisi = 32),
    CONSTRAINT termal_kare_uzunluk CHECK (octet_length(piksel_verisi) = 1536)
);

CREATE INDEX IF NOT EXISTS termal_kare_modul_zaman_idx
    ON gridup.termal_kare (modul_id, zaman DESC);

CREATE INDEX IF NOT EXISTS termal_kare_alindi_idx
    ON gridup.termal_kare (alindi_zaman DESC);

COMMENT ON TABLE gridup.termal_kare IS
    '768 piksel (24x32) ham termal görüntü kareleri. 16-bit küçük-endian signed integer (0.1 °C).';

-- ---------------------------------------------------------------------------
-- 2. Termal Özet Tablosu (Hafif Paket: Maksimum, Konum ve 4 Bölge Ortalaması)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gridup.termal_ozet (
    modul_id        TEXT        NOT NULL REFERENCES gridup.modul (modul_id) ON DELETE CASCADE,
    zaman           TIMESTAMPTZ NOT NULL,
    maks            DOUBLE PRECISION NOT NULL,
    maks_sutun      SMALLINT    NOT NULL,
    maks_satir      SMALLINT    NOT NULL,
    bolge_ort       DOUBLE PRECISION[] NOT NULL,
    alindi_zaman    TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT termal_ozet_pk PRIMARY KEY (modul_id, zaman),
    CONSTRAINT termal_ozet_sutun CHECK (maks_sutun BETWEEN 0 AND 31),
    CONSTRAINT termal_ozet_satir CHECK (maks_satir BETWEEN 0 AND 23)
);

CREATE INDEX IF NOT EXISTS termal_ozet_modul_zaman_idx
    ON gridup.termal_ozet (modul_id, zaman DESC);
