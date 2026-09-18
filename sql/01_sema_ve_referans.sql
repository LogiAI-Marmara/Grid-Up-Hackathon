-- 01_sema_ve_referans.sql
-- Grid Up Hackathon - Veritabanı Şeması ve Referans Ağacı
-- Saha -> Pano -> Modül hiyerarşisi ve şema sürüm takibi

CREATE SCHEMA IF NOT EXISTS gridup;

SET search_path TO gridup, public;

-- ---------------------------------------------------------------------------
-- 1. Şema Sürüm Takip Tablosu
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gridup.sema_surum (
    surum       INTEGER     PRIMARY KEY,
    ad          TEXT        NOT NULL,
    uygulanma   TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE gridup.sema_surum IS
    'Uygulanan veritabanı migrasyonlarının sürüm geçmişi.';

-- ---------------------------------------------------------------------------
-- 2. Saha (Trafo Merkezi / İstasyon) - modul_id 1. segmenti (Örn: TR041)
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

COMMENT ON TABLE gridup.saha IS 'Trafo merkezi / saha referans tablosu.';

-- ---------------------------------------------------------------------------
-- 3. Pano (AG / OG Dağıtım Panosu) - modul_id 2. segmenti (Örn: P01)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gridup.pano (
    saha_kodu   TEXT        NOT NULL REFERENCES gridup.saha (saha_kodu) ON DELETE CASCADE,
    pano_kodu   TEXT        NOT NULL,
    ad          TEXT,
    pano_tipi   TEXT        NOT NULL DEFAULT 'ag',
    olusturma   TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (saha_kodu, pano_kodu),
    CONSTRAINT pano_kodu_bicim CHECK (pano_kodu ~ '^[A-Za-z0-9]{2,16}$'),
    CONSTRAINT pano_tipi_kural CHECK (pano_tipi IN ('ag', 'og', 'kompanzasyon', 'ozel'))
);

COMMENT ON TABLE gridup.pano IS 'Saha içindeki elektrik panoları.';

-- ---------------------------------------------------------------------------
-- 4. Modül (Uç Cihaz / Sensör Modülü) - modul_id formatı: TR041-P01-M1
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gridup.modul (
    modul_id        TEXT        PRIMARY KEY,
    saha_kodu       TEXT        NOT NULL,
    pano_kodu       TEXT        NOT NULL,
    ad              TEXT,
    aktif           BOOLEAN     NOT NULL DEFAULT true,
    donanim_revizyon TEXT,
    yazilim_surumu  TEXT,
    olusturuldu     TIMESTAMPTZ NOT NULL DEFAULT now(),
    guncellendi     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT modul_pano_fk FOREIGN KEY (saha_kodu, pano_kodu)
        REFERENCES gridup.pano (saha_kodu, pano_kodu) ON DELETE CASCADE,
    CONSTRAINT modul_id_bicim CHECK (
        modul_id ~ '^[A-Za-z0-9]{2,16}-[A-Za-z0-9]{2,16}-[A-Za-z0-9]{1,16}$'
    )
);

CREATE INDEX IF NOT EXISTS modul_saha_pano_idx ON gridup.modul (saha_kodu, pano_kodu);

-- ---------------------------------------------------------------------------
-- 5. Modül Durum Bilgisi (Besleme, Sinyal, Canlılık)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gridup.modul_durum (
    modul_id        TEXT        NOT NULL REFERENCES gridup.modul (modul_id) ON DELETE CASCADE,
    zaman           TIMESTAMPTZ NOT NULL,
    besleme         TEXT        NOT NULL DEFAULT 'sebeke',
    sinyal          INTEGER,
    yazilim_surumu  TEXT,
    alindi_zaman    TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT modul_durum_tekil UNIQUE (modul_id, zaman),
    CONSTRAINT modul_durum_besleme CHECK (besleme IN ('sebeke', 'yedek', 'bilinmiyor'))
);

CREATE INDEX IF NOT EXISTS modul_durum_zaman_idx ON gridup.modul_durum (zaman DESC);
CREATE INDEX IF NOT EXISTS modul_durum_alindi_idx ON gridup.modul_durum (alindi_zaman DESC);
