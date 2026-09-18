-- tam_kurulum.sql
-- Grid Up Hackathon - Tek Dosyada Tam Veritabanı Kurulumu ve Başlangıç Verileri
-- Tüm şemayı, tabloları, bölümleri ve başlangıç referans ağacını kurar.

CREATE SCHEMA IF NOT EXISTS gridup;
SET search_path TO gridup, public;

-- 1. Şema Sürümü
CREATE TABLE IF NOT EXISTS gridup.sema_surum (
    surum       INTEGER PRIMARY KEY,
    ad          TEXT NOT NULL,
    uygulanma   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. Saha
CREATE TABLE IF NOT EXISTS gridup.saha (
    saha_kodu   TEXT PRIMARY KEY,
    ad          TEXT NOT NULL,
    il          TEXT,
    ilce        TEXT,
    enlem       DOUBLE PRECISION,
    boylam      DOUBLE PRECISION,
    olusturma   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT saha_kodu_bicim CHECK (saha_kodu ~ '^[A-Za-z0-9]{2,16}$')
);

-- 3. Pano
CREATE TABLE IF NOT EXISTS gridup.pano (
    saha_kodu   TEXT NOT NULL REFERENCES gridup.saha (saha_kodu) ON DELETE CASCADE,
    pano_kodu   TEXT NOT NULL,
    ad          TEXT,
    pano_tipi   TEXT NOT NULL DEFAULT 'ag',
    olusturma   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (saha_kodu, pano_kodu),
    CONSTRAINT pano_kodu_bicim CHECK (pano_kodu ~ '^[A-Za-z0-9]{2,16}$')
);

-- 4. Modül
CREATE TABLE IF NOT EXISTS gridup.modul (
    modul_id        TEXT PRIMARY KEY,
    saha_kodu       TEXT NOT NULL,
    pano_kodu       TEXT NOT NULL,
    ad              TEXT,
    aktif           BOOLEAN NOT NULL DEFAULT true,
    donanim_revizyon TEXT,
    yazilim_surumu  TEXT,
    olusturuldu     TIMESTAMPTZ NOT NULL DEFAULT now(),
    guncellendi     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT modul_pano_fk FOREIGN KEY (saha_kodu, pano_kodu)
        REFERENCES gridup.pano (saha_kodu, pano_kodu) ON DELETE CASCADE
);

-- 5. Modül Durum
CREATE TABLE IF NOT EXISTS gridup.modul_durum (
    modul_id        TEXT NOT NULL REFERENCES gridup.modul (modul_id) ON DELETE CASCADE,
    zaman           TIMESTAMPTZ NOT NULL,
    besleme         TEXT NOT NULL DEFAULT 'sebeke',
    sinyal          INTEGER,
    yazilim_surumu  TEXT,
    alindi_zaman    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT modul_durum_tekil UNIQUE (modul_id, zaman)
);

-- 6. Bölümlü Ölçüm Tablosu
CREATE TABLE IF NOT EXISTS gridup.olcum (
    modul_id        TEXT NOT NULL REFERENCES gridup.modul (modul_id) ON DELETE CASCADE,
    olcum_tipi      TEXT NOT NULL,
    zaman           TIMESTAMPTZ NOT NULL,
    deger           DOUBLE PRECISION NOT NULL,
    birim           TEXT NOT NULL,
    kalite          TEXT NOT NULL DEFAULT 'iyi',
    alindi_zaman    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT olcum_pk PRIMARY KEY (modul_id, olcum_tipi, zaman)
) PARTITION BY RANGE (zaman);

CREATE TABLE IF NOT EXISTS gridup.olcum_varsayilan PARTITION OF gridup.olcum DEFAULT;
CREATE TABLE IF NOT EXISTS gridup.olcum_2026_09 PARTITION OF gridup.olcum
    FOR VALUES FROM ('2026-09-01 00:00:00+00') TO ('2026-10-01 00:00:00+00');
CREATE TABLE IF NOT EXISTS gridup.olcum_2026_10 PARTITION OF gridup.olcum
    FOR VALUES FROM ('2026-10-01 00:00:00+00') TO ('2026-11-01 00:00:00+00');

-- 7. Termal
CREATE SEQUENCE IF NOT EXISTS gridup.termal_kare_sira START WITH 1;

CREATE TABLE IF NOT EXISTS gridup.termal_kare (
    kare_id         TEXT PRIMARY KEY DEFAULT ('kr_' || lpad(nextval('gridup.termal_kare_sira')::TEXT, 6, '0')),
    modul_id        TEXT NOT NULL REFERENCES gridup.modul (modul_id) ON DELETE CASCADE,
    zaman           TIMESTAMPTZ NOT NULL,
    piksel_verisi   BYTEA NOT NULL,
    satir_sayisi    SMALLINT NOT NULL DEFAULT 24,
    sutun_sayisi    SMALLINT NOT NULL DEFAULT 32,
    alindi_zaman    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT termal_kare_tekil UNIQUE (modul_id, zaman)
);

CREATE TABLE IF NOT EXISTS gridup.termal_ozet (
    modul_id        TEXT NOT NULL REFERENCES gridup.modul (modul_id) ON DELETE CASCADE,
    zaman           TIMESTAMPTZ NOT NULL,
    maks            DOUBLE PRECISION NOT NULL,
    maks_sutun      SMALLINT NOT NULL,
    maks_satir      SMALLINT NOT NULL,
    bolge_ort       DOUBLE PRECISION[] NOT NULL,
    alindi_zaman    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT termal_ozet_pk PRIMARY KEY (modul_id, zaman)
);

-- 8. Analiz & Anomali
CREATE TABLE IF NOT EXISTS gridup.tarama_imleci (
    ad              TEXT PRIMARY KEY,
    son_islenen     TIMESTAMPTZ NOT NULL,
    tur_sayisi      BIGINT NOT NULL DEFAULT 0,
    guncellendi     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS gridup.anomali (
    anomali_id      TEXT PRIMARY KEY,
    modul_id        TEXT NOT NULL REFERENCES gridup.modul (modul_id) ON DELETE CASCADE,
    tip             TEXT NOT NULL,
    seviye          TEXT NOT NULL,
    durum           TEXT NOT NULL DEFAULT 'acik',
    baslangic       TIMESTAMPTZ NOT NULL,
    son_gorulme     TIMESTAMPTZ NOT NULL,
    gerekce         TEXT NOT NULL,
    kanit           JSONB NOT NULL DEFAULT '{}'::jsonb,
    kare_id         TEXT REFERENCES gridup.termal_kare (kare_id) ON DELETE SET NULL,
    olusturuldu     TIMESTAMPTZ NOT NULL DEFAULT now(),
    guncellendi     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS gridup.anomali_gecis (
    gecis_id        BIGSERIAL PRIMARY KEY,
    anomali_id      TEXT NOT NULL REFERENCES gridup.anomali (anomali_id) ON DELETE CASCADE,
    onceki_seviye   TEXT NOT NULL,
    yeni_seviye     TEXT NOT NULL,
    zaman           TIMESTAMPTZ NOT NULL DEFAULT now(),
    tetikleyen_deger DOUBLE PRECISION,
    aciklama        TEXT
);

-- 9. Başlangıç Tohum Verileri (Örnek Saha, Pano ve Modüller)
INSERT INTO gridup.saha (saha_kodu, ad, il, ilce) VALUES
    ('TR041', 'Kadıköy Trafo Merkezi', 'İstanbul', 'Kadıköy'),
    ('TR042', 'Üsküdar Trafo Merkezi', 'İstanbul', 'Üsküdar'),
    ('TR052', 'Ordu Merkez Dağıtım', 'Ordu', 'Altınordu'),
    ('TR063', 'Şanlıurfa Trafo İstasyonu', 'Şanlıurfa', 'Haliliye')
ON CONFLICT (saha_kodu) DO NOTHING;

INSERT INTO gridup.pano (saha_kodu, pano_kodu, ad, pano_tipi) VALUES
    ('TR041', 'P01', 'Giriş Ana AG Panosu', 'ag'),
    ('TR041', 'P02', 'Çıkış Fider Panosu', 'ag'),
    ('TR042', 'P01', 'Ana Kompanzasyon Panosu', 'kompanzasyon'),
    ('TR052', 'P01', 'Fider Panosu 1', 'ag'),
    ('TR063', 'P01', 'Ana Dağıtım Panosu', 'ag'),
    ('TR063', 'P02', 'Yedek Jeneratör Panosu', 'ag')
ON CONFLICT (saha_kodu, pano_kodu) DO NOTHING;

INSERT INTO gridup.modul (modul_id, saha_kodu, pano_kodu, ad, yazilim_surumu) VALUES
    ('TR041-P01-M1', 'TR041', 'P01', 'Giriş Fideri Modülü', '1.0.3'),
    ('TR041-P01-M2', 'TR041', 'P01', 'Bara Bağlantı Modülü', '1.0.3'),
    ('TR041-P02-M1', 'TR041', 'P02', 'Çıkış Fideri Modülü 1', '1.0.3'),
    ('TR052-P01-M1', 'TR052', 'P01', 'Ana Dağıtım Modülü', '1.0.3'),
    ('TR063-P01-M1', 'TR063', 'P01', 'Şebeke Giriş Modülü', '1.0.3'),
    ('TR063-P02-M1', 'TR063', 'P02', 'Jeneratör Giriş Modülü', '1.0.3')
ON CONFLICT (modul_id) DO NOTHING;
