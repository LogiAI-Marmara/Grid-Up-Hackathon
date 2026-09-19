-- 04_analiz_ve_anomali.sql
-- Grid Up Hackathon - İZ B Analiz, Tarama ve Anomali Takip Tabloları
-- Sıcak nokta, aşırı yük, faz dengesizliği, nem, klemens ve modül sessizlik olayları

SET search_path TO gridup, public;

-- ---------------------------------------------------------------------------
-- 1. Tarama İmleci (Scan Cursor) - Tarayıcının nerede kaldığını izler
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gridup.tarama_imleci (
    ad              TEXT        PRIMARY KEY,
    son_islenen     TIMESTAMPTZ NOT NULL,
    tur_sayisi      BIGINT      NOT NULL DEFAULT 0,
    guncellendi     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 2. Anomali Olayları Tablosu
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gridup.anomali (
    anomali_id      TEXT        PRIMARY KEY,
    modul_id        TEXT        NOT NULL REFERENCES gridup.modul (modul_id) ON DELETE CASCADE,
    tip             TEXT        NOT NULL,
    seviye          TEXT        NOT NULL,
    durum           TEXT        NOT NULL DEFAULT 'acik',
    baslangic       TIMESTAMPTZ NOT NULL,
    son_gorulme     TIMESTAMPTZ NOT NULL,
    gerekce         TEXT        NOT NULL,
    kanit           JSONB       NOT NULL DEFAULT '{}'::jsonb,
    kare_id         TEXT        REFERENCES gridup.termal_kare (kare_id) ON DELETE SET NULL,
    olusturuldu     TIMESTAMPTZ NOT NULL DEFAULT now(),
    guncellendi     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT anomali_seviye CHECK (seviye IN ('normal', 'izle', 'uyari', 'kritik')),
    CONSTRAINT anomali_durum CHECK (durum IN ('acik', 'onaylandi', 'kapandi')),
    CONSTRAINT anomali_tip CHECK (
        tip IN (
            'sicak_nokta', 'akim_sicaklik_sapmasi', 'faz_dengesizligi',
            'nem_yuksek', 'ortam_sicaklik_yuksek', 'ark', 'sensor_arizasi',
            'modul_saglik', 'asiri_yuk', 'gevsek_klemens'
        )
    )
);

CREATE INDEX IF NOT EXISTS anomali_modul_durum_idx ON gridup.anomali (modul_id, durum);
CREATE INDEX IF NOT EXISTS anomali_seviye_idx ON gridup.anomali (seviye) WHERE durum = 'acik';
CREATE INDEX IF NOT EXISTS anomali_son_gorulme_idx ON gridup.anomali (son_gorulme DESC);

-- ---------------------------------------------------------------------------
-- 3. Anomali Seviye Geçişleri (State Transitions & Histerezis Takibi)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gridup.anomali_gecis (
    gecis_id        BIGSERIAL   PRIMARY KEY,
    anomali_id      TEXT        NOT NULL REFERENCES gridup.anomali (anomali_id) ON DELETE CASCADE,
    onceki_seviye   TEXT        NOT NULL,
    yeni_seviye     TEXT        NOT NULL,
    zaman           TIMESTAMPTZ NOT NULL DEFAULT now(),
    tetikleyen_deger DOUBLE PRECISION,
    aciklama        TEXT
);

CREATE INDEX IF NOT EXISTS anomali_gecis_anomali_idx ON gridup.anomali_gecis (anomali_id, zaman DESC);
