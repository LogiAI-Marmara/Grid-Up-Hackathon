-- 05_ornek_sorgular.sql
-- Grid Up Hackathon - Operasyonel ve Analitik Hazır SQL Sorguları
-- Operatörler, veri bilimciler ve izleme ekranları için pratik sorgular

SET search_path TO gridup, public;

-- ===========================================================================
-- 1. Bir Modüle Ait En Son Ölçüm Değerleri
-- ===========================================================================
SELECT DISTINCT ON (olcum_tipi)
    modul_id,
    olcum_tipi,
    deger,
    birim,
    kalite,
    zaman AS olcum_zamani,
    alindi_zaman AS sisteme_giris
FROM gridup.olcum
WHERE modul_id = 'TR041-P01-M1'
ORDER BY olcum_tipi, zaman DESC;


-- ===========================================================================
-- 2. Açık ve Çözülmemiş Anomaliler (Kritik ve Uyarı Seviyeleri)
-- ===========================================================================
SELECT
    a.anomali_id,
    a.modul_id,
    m.saha_kodu,
    m.pano_kodu,
    a.seviye,
    a.tip,
    a.gerekce,
    a.son_gorulme,
    a.kare_id
FROM gridup.anomali a
JOIN gridup.modul m ON a.modul_id = m.modul_id
WHERE a.durum = 'acik'
ORDER BY 
    CASE a.seviye
        WHEN 'kritik' THEN 1
        WHEN 'uyari'  THEN 2
        WHEN 'izle'   THEN 3
        ELSE 4
    END,
    a.son_gorulme DESC;


-- ===========================================================================
-- 3. Üç Faz Akım Dengesi ve Dengesizlik Oranı (%)
-- ===========================================================================
WITH son_akimlar AS (
    SELECT
        modul_id,
        MAX(CASE WHEN olcum_tipi = 'akim_l1' THEN deger END) AS l1,
        MAX(CASE WHEN olcum_tipi = 'akim_l2' THEN deger END) AS l2,
        MAX(CASE WHEN olcum_tipi = 'akim_l3' THEN deger END) AS l3,
        MAX(CASE WHEN olcum_tipi = 'akim_notr' THEN deger END) AS notr,
        MAX(zaman) AS son_zaman
    FROM (
        SELECT DISTINCT ON (modul_id, olcum_tipi) modul_id, olcum_tipi, deger, zaman
        FROM gridup.olcum
        WHERE olcum_tipi IN ('akim_l1', 'akim_l2', 'akim_l3', 'akim_notr')
        ORDER BY modul_id, olcum_tipi, zaman DESC
    ) s
    GROUP BY modul_id
)
SELECT
    modul_id,
    ROUND(l1::numeric, 2) AS akim_l1,
    ROUND(l2::numeric, 2) AS akim_l2,
    ROUND(l3::numeric, 2) AS akim_l3,
    ROUND(notr::numeric, 2) AS akim_notr,
    ROUND(((l1 + l2 + l3) / 3.0)::numeric, 2) AS akim_ortalama,
    ROUND((GREATEST(ABS(l1 - (l1+l2+l3)/3.0), ABS(l2 - (l1+l2+l3)/3.0), ABS(l3 - (l1+l2+l3)/3.0)) 
           / NULLIF((l1+l2+l3)/3.0, 0) * 100.0)::numeric, 1) AS faz_dengesizlik_yuzde,
    son_zaman
FROM son_akimlar
WHERE l1 IS NOT NULL AND l2 IS NOT NULL AND l3 IS NOT NULL;


-- ===========================================================================
-- 4. Termal Sıcak Nokta ve Ortam Sıcaklığı Fark Analizi
-- ===========================================================================
SELECT
    t.modul_id,
    t.zaman,
    t.maks AS termal_maks_derece,
    t.maks_sutun,
    t.maks_satir,
    t.bolge_ort,
    ROUND((t.maks - (t.bolge_ort[1] + t.bolge_ort[2] + t.bolge_ort[3] + t.bolge_ort[4]) / 4.0)::numeric, 2) AS sicak_nokta_farki
FROM gridup.termal_ozet t
ORDER BY t.maks DESC
LIMIT 20;


-- ===========================================================================
-- 5. Sessiz Modüllerin Tespiti (Ölçüm Gelmeyen Modüller)
-- ===========================================================================
SELECT
    m.modul_id,
    m.saha_kodu,
    m.pano_kodu,
    MAX(o.zaman) AS en_son_olcum_zamani,
    ROUND(EXTRACT(EPOCH FROM (now() - MAX(o.zaman))) / 60.0, 1) AS sessiz_kaldigi_dakika
FROM gridup.modul m
LEFT JOIN gridup.olcum o ON m.modul_id = o.modul_id
WHERE m.aktif = true
GROUP BY m.modul_id, m.saha_kodu, m.pano_kodu
HAVING MAX(o.zaman) IS NULL OR MAX(o.zaman) < now() - INTERVAL '15 minutes'
ORDER BY en_son_olcum_zamani ASC NULLS FIRST;


-- ===========================================================================
-- 6. Veri Gecikmesi ve Saat Kayması (Clock Drift) Kontrolü
-- ===========================================================================
SELECT
    modul_id,
    COUNT(*) AS olcum_sayisi,
    ROUND(AVG(EXTRACT(EPOCH FROM (alindi_zaman - zaman)))::numeric, 2) AS ortalama_gecikme_sn,
    ROUND(MAX(EXTRACT(EPOCH FROM (alindi_zaman - zaman)))::numeric, 2) AS azami_gecikme_sn
FROM gridup.olcum
WHERE alindi_zaman > now() - INTERVAL '1 hour'
GROUP BY modul_id
ORDER BY azami_gecikme_sn DESC;
