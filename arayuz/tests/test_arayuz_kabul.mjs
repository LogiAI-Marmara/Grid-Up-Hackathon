/**
 * Grid Up — İZ C: Monitoring Arayüzü EK KABUL TESTLERİ
 * Koşturma: node --test "arayuz/tests/test_*.mjs"
 *
 * test_arayuz_sozlesme.mjs UI-01..UI-08'i iç fonksiyonlar üzerinden doğrular.
 * Bu dosya, aynı kabul ölçütlerini OPERATÖRÜN GERÇEKTEN İZLEDİĞİ YOL üzerinden
 * (modulSec, apiFetch, rozet hesabı) sınar ve sözleşme testlerinin atladığı
 * regresyonları kilitler. Gerçek operasyon veritabanına bağlanmaz.
 */

import test from 'node:test';
import assert from 'node:assert/strict';
import { setupMockEnvironment, loadApp } from './harness.mjs';

const ZAMAN = '2026-09-19T10:00:00Z';

function modulDetayi(modulId, ekle = {}) {
    return {
        modul_id: modulId,
        aktif: true,
        son_gorulme: ZAMAN,
        besleme: 'sebeke',
        sinyal: -58,
        durum_zaman: ZAMAN,
        son_olcumler: [
            { olcum_tipi: 'ortam_sicaklik', zaman: ZAMAN, deger: 25.0, birim: 'C', kalite: 'iyi' }
        ],
        acik_anomaliler: [],
        ...ekle
    };
}

function yanit(govde, { ok = true, status = 200 } = {}) {
    return { ok, status, json: async () => govde };
}

// --------------------------------------------------------------------------
test('UI-02: modulSec() ile modül değişince önceki modülün değerleri BİR AN BİLE kalmaz', async () => {
    const doc = setupMockEnvironment();
    const app = await loadApp();

    let aGecikmesi = null;
    global.fetch = async (url) => {
        if (url.includes('/termal/son')) return yanit({}, { ok: false, status: 404 });
        if (url.includes('/seri')) return yanit({ noktalar: [] });
        const m = url.match(/\/moduller\/(MODUL-[AB])$/);
        if (m) {
            if (m[1] === 'MODUL-A' && aGecikmesi) await aGecikmesi;
            const deger = m[1] === 'MODUL-A' ? 41.7 : 22.2;
            return yanit(modulDetayi(m[1], {
                son_olcumler: [{ olcum_tipi: 'ortam_sicaklik', zaman: ZAMAN, deger, birim: 'C', kalite: 'iyi' }]
            }));
        }
        return yanit({}, { ok: false, status: 404 });
    };

    // A seçilir ve ekrana yerleşir
    app.modulSec('MODUL-A', 'MODUL-A');
    await new Promise(r => setTimeout(r, 30));
    assert.equal(doc.getElementById('val-temp').textContent, '41.7', 'A ekrana gelmeli');
    assert.equal(doc.getElementById('active-module-name').textContent, 'MODUL-A', 'Başlık A olmalı');

    // A'nın bir sonraki yanıtı askıya alınır, B seçilir.
    // Seçimin HEMEN ardından — B yanıtı daha gelmeden — ekranda A'dan hiçbir şey kalmamalı.
    let cozucu;
    aGecikmesi = new Promise(r => { cozucu = r; });
    app.modulSec('MODUL-B', 'MODUL-B');

    assert.equal(doc.getElementById('val-temp').textContent, '--',
        "Seçim değişir değişmez önceki modülün ölçümü temizlenmeli (UI-02 kural 1)");
    assert.equal(doc.getElementById('active-module-name').textContent, 'MODUL-B',
        'Başlık anında yeni modüle geçmeli');
    assert.equal(doc.getElementById('active-module-badge').textContent, 'MODUL-B',
        'Modül kimliği rozeti anında yeni modüle geçmeli');
    assert.equal(app.state.termalMatris, null, 'Önceki modülün termal karesi anında düşmeli');

    cozucu();
    await new Promise(r => setTimeout(r, 40));
    assert.equal(doc.getElementById('val-temp').textContent, '22.2',
        "A'nın geciken yanıtı B ekranını ezmemeli (UI-02 kural 2)");
});

// --------------------------------------------------------------------------
test('UI-02/UI-07: API erişilemezse gösterge "BAĞLANTI KESİLDİ" olur, erişilebilirse geri döner', async () => {
    const doc = setupMockEnvironment();
    const app = await loadApp();

    // Bağlantı hatası: API'ye hiç ulaşılamıyor
    global.fetch = async () => { throw new Error('ECONNREFUSED'); };
    await app.hiyerarsiyiYukle();
    assert.equal(app.state.isOnline, false, 'Ağ hatasında API çevrimdışı sayılmalı');
    assert.equal(doc.getElementById('api-status-text').textContent, 'BAĞLANTI KESİLDİ');

    // HTTP 500: API ERİŞİLEBİLİR ama istek başarısız. Gösterge "çevrimiçi" kalır,
    // hatayı ilgili bölüm kendi gösterir (UI-02 kural 4, UI-07 kural 4).
    global.fetch = async () => yanit({ hata: { mesaj: 'patladı' } }, { ok: false, status: 500 });
    await app.hiyerarsiyiYukle();
    assert.equal(app.state.isOnline, true,
        'HTTP 500 yanıtı da erişilebilir bir API demektir; LED erişilebilirliği gösterir');
    assert.equal(doc.getElementById('api-status-text').textContent, 'API ÇEVRİMİÇİ');
    assert.match(doc.getElementById('hierarchy-container').innerHTML, /alınamadı/,
        'Başarısız bölüm kendi hata durumunu göstermeli');
});

// --------------------------------------------------------------------------
test('UI-03: tanınmayan/eksik seviye sessizce "normal" yapılmaz', async () => {
    const doc = setupMockEnvironment();
    const app = await loadApp();

    app.state.apiModulSeviyeleri = {};
    app.state.alarmModulSeviyeleri = {};

    // Hiç kaydı olmayan modül
    assert.equal(app.modulSeviyesiniGetir('YOK'), 'bilinmiyor',
        'Seviyesi hiç bilinmeyen modül "normal" sayılmaz');

    // API bozuk/tanınmayan bir seviye gönderdi
    app.state.apiModulSeviyeleri['MX'] = app.seviyeNormalize('kirmizi_alarm');
    assert.equal(app.modulSeviyesiniGetir('MX'), 'bilinmiyor',
        'Tanınmayan seviye değeri "normal" yapılmaz (UI-03 kural 8)');

    // Geçerli seviye gelince normale döner
    app.state.apiModulSeviyeleri['MX'] = app.seviyeNormalize('normal');
    assert.equal(app.modulSeviyesiniGetir('MX'), 'normal');

    // Açık anomali varsa en kötü seviye kazanır
    app.state.alarmModulSeviyeleri['MX'] = 'kritik';
    assert.equal(app.modulSeviyesiniGetir('MX'), 'kritik');

    // Kapanmamış olay kalmayınca ve API normal deyince rozet normale döner
    delete app.state.alarmModulSeviyeleri['MX'];
    assert.equal(app.modulSeviyesiniGetir('MX'), 'normal',
        'Geçmişteki yüksek seviye bellekte süresiz tutulmaz');
});

// --------------------------------------------------------------------------
test('UI-03: durum_zaman yoksa besleme/RSSI güncelliği iddia edilmez', async () => {
    const doc = setupMockEnvironment();
    const app = await loadApp();

    global.fetch = async (url) => {
        if (url.includes('/termal/son')) return yanit({}, { ok: false, status: 404 });
        if (url.includes('/seri')) return yanit({ noktalar: [] });
        return yanit(modulDetayi('M1', { besleme: null, sinyal: null, durum_zaman: null }));
    };
    await app.modulDetayYukle('M1');

    assert.equal(doc.getElementById('val-feed').textContent, 'BİLİNMİYOR',
        'besleme=null şebeke sayılmaz');
    assert.equal(doc.getElementById('val-rssi').textContent, 'Bilinmiyor',
        'sinyal=null "0 dBm" sayılmaz');
    assert.match(doc.getElementById('val-durum-zaman').textContent, /Bilinmiyor/,
        'durum_zaman yoksa açıkça bilinmiyor denir (UI-03 kural 3)');

    // durum_zaman gelince gösterilir
    global.fetch = async (url) => {
        if (url.includes('/termal/son')) return yanit({}, { ok: false, status: 404 });
        if (url.includes('/seri')) return yanit({ noktalar: [] });
        return yanit(modulDetayi('M1'));
    };
    await app.modulDetayYukle('M1', true);
    assert.match(doc.getElementById('val-durum-zaman').textContent, /2026/,
        'durum_zaman varsa TSİ olarak gösterilir');
});

// --------------------------------------------------------------------------
test('UI-04: özetten üretilmiş görselde uyarı şeridi görüntünün üzerinde sürekli durur', async () => {
    const doc = setupMockEnvironment();
    const app = await loadApp();
    const overlay = doc.getElementById('thermal-synthetic-overlay');

    // kare_id=null → tam kare yok → sentetik görsel + kaldırılamaz uyarı
    global.fetch = async (url) => {
        if (url.includes('/termal/son')) {
            return yanit({
                modul_id: 'M1', zaman: ZAMAN, maks: 48.2,
                maks_konum: [14, 9], bolge_ort: [25, 26, 27, 28], kare_id: null
            });
        }
        if (url.includes('/seri')) return yanit({ noktalar: [] });
        return yanit(modulDetayi('M1'));
    };
    await app.modulDetayYukle('M1');

    assert.equal(app.state.termalMatrisOlculdu, false, 'Sentetik görsel ölçülmüş sayılmaz');
    assert.equal(overlay.style.display, 'block', 'Uyarı şeridi görünür olmalı (UI-04 kural 2)');
    assert.match(overlay.textContent, /ölçülmüş piksel değildir/i);
    assert.doesNotMatch(doc.getElementById('thermal-source-badge').textContent, /Ölçülmüş Tam Kare/,
        '"Ölçülmüş Tam Kare" etiketi sentetik görselde kullanılmaz');

    // Gerçek 768 piksellik kare gelince şerit kalkar
    const pikseller = new Array(768).fill(30);
    pikseller[9 * 32 + 14] = 62.3;
    global.fetch = async (url) => {
        if (url.includes('/termal/kare/KARE-1')) {
            return yanit({
                kare_id: 'KARE-1', modul_id: 'M1', zaman: ZAMAN,
                satir_sayisi: 24, sutun_sayisi: 32, duzen: 'satir_oncelikli',
                piksel_verisi: pikseller
            });
        }
        if (url.includes('/termal/son')) {
            return yanit({
                modul_id: 'M1', zaman: ZAMAN, maks: 62.3,
                maks_konum: [14, 9], bolge_ort: [25, 26, 27, 28], kare_id: 'KARE-1'
            });
        }
        if (url.includes('/seri')) return yanit({ noktalar: [] });
        return yanit(modulDetayi('M1'));
    };
    await app.modulDetayYukle('M1', true);

    assert.equal(app.state.termalMatrisOlculdu, true, 'Doğrulanmış kare ölçülmüş sayılır');
    assert.equal(overlay.style.display, 'none', 'Gerçek karede uyarı şeridi kalkar');
    assert.equal(app.state.termalMatris[9 * 32 + 14], 62.3,
        '(x=14,y=9) pikseli y*32+x indeksinden okunur (UI-04 kural 3)');
});

// --------------------------------------------------------------------------
test('UI-04: kanıt sıcaklığı skor*100 değil, gerçek pikselden gelir', async () => {
    const doc = setupMockEnvironment();
    const app = await loadApp();

    const pikseller = new Array(768).fill(28);
    pikseller[9 * 32 + 14] = 62.3;

    const anomali = {
        id: 'AN-1', sira: 1, modul_id: 'M1', tip: 'sicak_nokta',
        seviye: 'kritik', durum: 'acik', skor: 0.85,
        gerekce: 'Sıcak nokta', ilk_gorulme: ZAMAN, son_gorulme: ZAMAN,
        kanit: { kare_id: 'KARE-1', piksel: [14, 9] }
    };
    app.state.cozulmemisAnomaliler = [anomali];

    global.fetch = async (url) => {
        if (url.includes('/termal/kare/KARE-1')) {
            return yanit({
                kare_id: 'KARE-1', modul_id: 'M1', zaman: ZAMAN,
                satir_sayisi: 24, sutun_sayisi: 32, duzen: 'satir_oncelikli',
                piksel_verisi: pikseller
            });
        }
        return yanit({}, { ok: false, status: 404 });
    };

    await app.anomaliSec('AN-1');
    assert.equal(doc.getElementById('val-tmax').textContent, '62.3',
        'skor=0.85 → 85 °C ASLA; sıcaklık gerçek pikselden gelir');
    assert.equal(app.state.termalMatrisOlculdu, true);
});

// --------------------------------------------------------------------------
test('UI-04: yanlış boyutlu / yanlış modüllü / NaN içeren kare reddedilir', async () => {
    setupMockEnvironment();
    const app = await loadApp();

    const gecerli = {
        kare_id: 'K', modul_id: 'M1', zaman: ZAMAN,
        satir_sayisi: 24, sutun_sayisi: 32,
        piksel_verisi: new Array(768).fill(30)
    };
    assert.equal(app.tamKareyiDogrula(gecerli, 'M1', ZAMAN), true);

    assert.equal(app.tamKareyiDogrula({ ...gecerli, piksel_verisi: new Array(767).fill(30) }, 'M1', ZAMAN),
        false, '767 piksel reddedilir');
    assert.equal(app.tamKareyiDogrula(gecerli, 'M2', ZAMAN), false, 'Yanlış modül reddedilir');
    assert.equal(app.tamKareyiDogrula(gecerli, 'M1', '2026-01-01T00:00:00Z'), false,
        'Yanlış zaman reddedilir (eski özetin işareti yeni karenin üstüne konmaz)');

    const nanli = { ...gecerli, piksel_verisi: new Array(768).fill(30) };
    nanli.piksel_verisi[5] = NaN;
    assert.equal(app.tamKareyiDogrula(nanli, 'M1', ZAMAN), false, 'NaN içeren kare reddedilir');

    const yaziLi = { ...gecerli, piksel_verisi: new Array(768).fill(30) };
    yaziLi.piksel_verisi[7] = '30';
    assert.equal(app.tamKareyiDogrula(yaziLi, 'M1', ZAMAN), false, 'Sayı olmayan piksel reddedilir');
});

// --------------------------------------------------------------------------
test('UI-05: boş operatör kimliğiyle POST yapılmaz; 500 yanıtında kart kaldırılmaz', async () => {
    const doc = setupMockEnvironment();
    const app = await loadApp();

    doc.getElementById('operator-id-input').value = '   ';
    global.alert = () => {};

    let postSayisi = 0;
    global.fetch = async (url, opts) => {
        if (opts && opts.method === 'POST') postSayisi++;
        return yanit({}, { ok: false, status: 500 });
    };

    await app.alarmOnayla('AN-1', 'M1');
    assert.equal(postSayisi, 0, 'Boş operatör kimliğiyle onay gönderilmez (UI-05 kural 7)');

    // Geçerli kimlik + HTTP 500 → tek POST, kart kaldırılmaz
    doc.getElementById('operator-id-input').value = 'nobetci_muh';
    app.state.cozulmemisAnomaliler = [{
        id: 'AN-1', sira: 1, modul_id: 'M1', tip: 'sicak_nokta', seviye: 'uyari',
        durum: 'acik', gerekce: 'test', ilk_gorulme: ZAMAN, son_gorulme: ZAMAN
    }];
    const oncekiSayi = app.state.cozulmemisAnomaliler.length;

    await app.alarmOnayla('AN-1', 'M1');
    assert.equal(postSayisi, 1, 'Hata durumunda POST tekrarlanmaz (UI-02 kural 5)');
    assert.equal(app.state.cozulmemisAnomaliler.length, oncekiSayi,
        '5xx yanıtında olay listeden düşürülmez (UI-05 kural 5)');
});

// --------------------------------------------------------------------------
test('UI-05: listede olmayan olay yok sayılmaz, /anomaliler/{id} ile okunur', async () => {
    const doc = setupMockEnvironment();
    const app = await loadApp();

    app.state.cozulmemisAnomaliler = [];
    let detayIstendi = false;

    global.fetch = async (url) => {
        if (url.includes('/anomaliler/AN-GIZLI')) {
            detayIstendi = true;
            return yanit({
                id: 'AN-GIZLI', sira: 9, modul_id: 'M9', tip: 'ark',
                seviye: 'kritik', durum: 'acik', skor: 0.9,
                gerekce: 'Ark olayı', ilk_gorulme: ZAMAN, son_gorulme: ZAMAN,
                kanit: { kare_id: null }
            });
        }
        return yanit({}, { ok: false, status: 404 });
    };

    await app.anomaliSec('AN-GIZLI');
    assert.equal(detayIstendi, true, 'Listede yoksa olay ayrıntısı API\'den okunur');
    assert.match(doc.getElementById('banner-desc').textContent, /Ark olayı/,
        'Okunan olayın gerekçesi gösterilir');
});

// --------------------------------------------------------------------------
test('UI-05: sayfalama imleci ilerlemezse tarama sonsuz dönmez', async () => {
    setupMockEnvironment();
    const app = await loadApp();

    let cagriSayisi = 0;
    global.fetch = async () => {
        cagriSayisi++;
        if (cagriSayisi > 20) throw new Error('SONSUZ DONGU');
        // Bozuk/vekil yanıt: `sonraki` hep aynı kalıyor
        return yanit({ veriler: [{ id: 'A', sira: 5 }], sonraki: 5, limit: 50 });
    };

    const sonuc = await app.sayfaliAnomalileriGetir('acik');
    assert.ok(cagriSayisi <= 3, `İlerlemeyen imleçte tarama durmalı (çağrı: ${cagriSayisi})`);
    assert.ok(sonuc.length >= 1);
});

// --------------------------------------------------------------------------
test('UI-06: zaman aralığı seçiliyken /seri isteğine hem bas hem bit gönderilir', async () => {
    const doc = setupMockEnvironment();
    const app = await loadApp();

    doc.getElementById('timeseries-metric').value = 'ortam_sicaklik';
    doc.getElementById('timeseries-interval').value = '';
    doc.getElementById('timeseries-range').value = '24h';

    app.state.aktifModulId = 'M1';
    app.state.sonGorulmeZamani = ZAMAN;

    const istenenUrller = [];
    global.fetch = async (url) => {
        istenenUrller.push(url);
        return yanit({
            modul_id: 'M1', olcum_tipi: 'ortam_sicaklik', aralik: null,
            noktalar: [{ zaman: ZAMAN, deger: 25.5, birim: 'C', kalite: 'iyi' }]
        });
    };

    await app.zamanSerisiYukle();
    const seriUrl = istenenUrller.find(u => u.includes('/seri'));
    assert.ok(seriUrl, '/seri isteği yapılmalı');
    assert.match(seriUrl, /tip=ortam_sicaklik/);
    assert.match(seriUrl, /[?&]bas=/, 'bas gönderilmeli');
    assert.match(seriUrl, /[?&]bit=/, 'bit gönderilmeli (UI-06 kural 2)');
});

// --------------------------------------------------------------------------
test('UI-06: boş seri sıfır çizgisi değildir, API hatası ayrı mesajdır', async () => {
    const doc = setupMockEnvironment();
    const app = await loadApp();

    doc.getElementById('timeseries-metric').value = 'ortam_sicaklik';
    doc.getElementById('timeseries-interval').value = '';
    doc.getElementById('timeseries-range').value = '';
    app.state.aktifModulId = 'M1';

    global.fetch = async () => yanit({ modul_id: 'M1', olcum_tipi: 'ortam_sicaklik', aralik: null, noktalar: [] });
    await app.zamanSerisiYukle();
    assert.equal(doc.getElementById('timeseries-message').textContent, 'Bu aralıkta ölçüm yok');
    assert.deepEqual(app.state.seriNoktalar, [], 'Boş yanıt sıfır değerli noktaya dönüşmez');

    global.fetch = async () => yanit({ hata: { kod: 'ic_hata' } }, { ok: false, status: 500 });
    await app.zamanSerisiYukle();
    assert.equal(doc.getElementById('timeseries-message').textContent, 'Grafik yüklenemedi.',
        'API hatası "ölçüm yok" ile karıştırılmaz (UI-06 kural 4)');
});

// --------------------------------------------------------------------------
test('UI-01: pano başlığı hangi modülü seçeceğini söyler, boş pano boş görünür', async () => {
    const doc = setupMockEnvironment();
    const app = await loadApp();

    global.fetch = async (url) => {
        if (url.includes('/moduller?')) {
            return yanit({
                veriler: [{ modul_id: 'M-AKTIF', durum: 'aktif', seviye: 'normal', son_gorulme: ZAMAN }],
                toplam: 1, ofset: 0, limit: 50
            });
        }
        if (url.includes('/sahalar')) {
            return yanit({
                sahalar: [{
                    saha_kodu: 'SAHA-1', ad: 'Ana Saha',
                    panolar: [
                        { pano_kodu: 'PANO-1', ad: 'Dolu', moduller: [{ modul_id: 'M-AKTIF', aktif: true, seviye: 'normal' }] },
                        { pano_kodu: 'PANO-2', ad: 'Boş', moduller: [] }
                    ]
                }]
            });
        }
        return yanit({}, { ok: false, status: 404 });
    };

    await app.hiyerarsiyiYukle();
    const agac = doc.getElementById('hierarchy-container').textContent;
    assert.match(agac, /ilk modül: M-AKTIF/, 'Pano başlığı seçeceği modülü adlandırmalı (UI-01 kural 4)');
    assert.match(agac, /Bu panoda modül bulunmuyor/, 'Boş pano sessizce yok edilmez');
    assert.match(agac, /PANO-2/, 'Boş pano listede görünür');
});

// --------------------------------------------------------------------------
test('Statik şablon: index.html arayüzün vaat ettiği ibareleri taşır', async () => {
    const { readFileSync } = await import('node:fs');
    const { fileURLToPath } = await import('node:url');
    const kok = fileURLToPath(new URL('..', import.meta.url));
    const html = readFileSync(kok + 'index.html', 'utf-8');
    const app = await loadApp();

    assert.ok(html.includes('id="thermal-synthetic-overlay"'),
        'Tahmini görsel uyarı şeridi şablonda tanımlı olmalı');
    assert.ok(html.includes(app.SENTETIK_GORSEL_UYARISI),
        'Şablondaki ibare ile koddaki ibare aynı olmalı');
    assert.ok(html.includes('id="val-durum-zaman"'),
        'durum_zaman alanı şablonda bulunmalı');

    // UI-04 kural 5: renk skalası alarm eşiği değildir
    assert.match(html, /Isı Ölçeği[^<]*—[^<]*alarm eşiği değildir/,
        'Lejant açıkça "alarm eşiği değildir" demeli');

    // UI-05 kural 7: sabit operatör kimliği ön-doldurulmaz
    assert.doesNotMatch(html, /id="operator-id-input"[^>]*value="operator_1"/,
        'Operatör kimliği sabit operator_1 ile doldurulmaz');
});

// --------------------------------------------------------------------------
test('UI-02 kural 5: apiFetch tek adrese gider, 4xx/5xx sonrası isteği tekrarlamaz', async () => {
    setupMockEnvironment();
    const app = await loadApp();

    const cagrilanUrller = [];
    global.fetch = async (url) => {
        cagrilanUrller.push(url);
        return { ok: false, status: 502, json: async () => ({}) };
    };

    const res = await app.apiFetch('/anomaliler/AN-1/onayla?aktor=x', { method: 'POST' });
    assert.equal(res.status, 502, 'Hata yanıtı çağırana olduğu gibi aktarılır');
    assert.equal(cagrilanUrller.length, 1,
        'Vekil hatası sonrası ikinci bir adrese sessizce POST tekrarlanmaz');
});

// --------------------------------------------------------------------------
test('UI-03: kalite=yok kartı "Veri yok" der, sabit altyazı bunu örtmez', async () => {
    const doc = setupMockEnvironment();
    const app = await loadApp();

    global.fetch = async (url) => {
        if (url.includes('/termal/son')) return yanit({}, { ok: false, status: 404 });
        if (url.includes('/seri')) return yanit({ noktalar: [] });
        return yanit(modulDetayi('M1', {
            son_olcumler: [
                // Gerçek 0 + kalite iyi → 0 olarak KALIR
                { olcum_tipi: 'akim_notr', zaman: ZAMAN, deger: 0, birim: 'A', kalite: 'iyi' },
                // Sayı var ama kalite yok → güvenilir ölçüm sayılmaz
                { olcum_tipi: 'nem', zaman: ZAMAN, deger: 55, birim: '%', kalite: 'yok' },
                // Şüpheli → değer gösterilir ama kartta uyarı çıkar
                { olcum_tipi: 'ortam_sicaklik', zaman: ZAMAN, deger: 31.4, birim: 'C', kalite: 'supheli' }
                // ark_olay hiç yok → 0 UYDURULMAZ
            ]
        }));
    };
    await app.modulDetayYukle('M1');

    assert.equal(doc.getElementById('val-notr').textContent, '0.0',
        'Gerçek deger=0 + kalite=iyi sıfır olarak kalır');
    assert.equal(doc.getElementById('val-arc').textContent, '--',
        'Eksik ark_olay kaydı 0 yapılmaz');
    assert.equal(doc.getElementById('val-hum').textContent, '--',
        'kalite=yok değeri gösterilmez');
    assert.match(doc.getElementById('hum-status').textContent, /Veri yok/,
        'kalite=yok kartı "Veri yok" demeli; sabit altyazı bunu örtmemeli (UI-03 kural 2)');
    assert.equal(doc.getElementById('val-temp').textContent, '31.4',
        'Şüpheli ölçümün değeri gösterilebilir');
    assert.ok(doc.getElementById('card-temp').querySelector('.card-quality-warning'),
        'Şüpheli ölçüm aynı kartta açıkça işaretlenir');
    assert.equal(doc.getElementById('current-diff').textContent, 'Faz Dengesizliği: Hesaplanamadı',
        'L1/L2/L3 yokken faz dengesizliği hesaplanmaz');
});

// --------------------------------------------------------------------------
test('UI-03: termal özet 404 iken son_olcumler.termal_maks (şüpheli) "Veri yok"a çökmez', async () => {
    // Gerçek yığında görüldü (TR063-P01-M1, sensor_arizasi senaryosu): /termal/son 404,
    // ama son_olcumler'de termal_maks=153.9 kalite=supheli var. Eski davranış kartı
    // "--" + "Termal Veri Yok" yapıyordu; operatör şüpheli ölçümü hiç görmüyordu.
    const doc = setupMockEnvironment();
    const app = await loadApp();
    // Önceki kanıt testi kanıt kipinde bırakmış olabilir; operatör "canlıya dön"e basar.
    app.canliGoruntuyeDon();

    global.fetch = async (url) => {
        if (url.includes('/termal/son')) return yanit({}, { ok: false, status: 404 });
        if (url.includes('/seri')) return yanit({ noktalar: [] });
        return yanit(modulDetayi('M1', {
            son_olcumler: [
                { olcum_tipi: 'ortam_sicaklik', zaman: ZAMAN, deger: 32.6, birim: 'C', kalite: 'iyi' },
                { olcum_tipi: 'termal_maks', zaman: ZAMAN, deger: 153.923, birim: 'C', kalite: 'supheli' }
            ]
        }));
    };
    await app.modulDetayYukle('M1');

    assert.equal(doc.getElementById('val-tmax').textContent, '153.9',
        'Şüpheli termal_maks değeri gösterilir, "--" yapılmaz');
    assert.ok(doc.getElementById('card-tmax').querySelector('.card-quality-warning'),
        'Şüpheli termal ölçüm aynı kartta işaretlenir');
    assert.match(doc.getElementById('hotspot-coord').textContent, /Kalite: supheli/,
        'Kart altyazısı kaliteyi söyler');
    assert.match(doc.getElementById('thermal-source-badge').textContent, /özet yok/i,
        'Rozet "özet yok" der, "Termal Veri Yok" demez');
    assert.match(doc.getElementById('banner-desc').textContent, /153\.9/,
        'Şerit son termal_maks ölçümünü ve kalitesini yazar');

    // Özet gerçekten yoksa (termal_maks kaydı da yok) eski davranış korunur.
    global.fetch = async (url) => {
        if (url.includes('/termal/son')) return yanit({}, { ok: false, status: 404 });
        if (url.includes('/seri')) return yanit({ noktalar: [] });
        return yanit(modulDetayi('M2'));
    };
    await app.modulDetayYukle('M2');
    assert.equal(doc.getElementById('val-tmax').textContent, '--');
    assert.equal(doc.getElementById('thermal-source-badge').textContent, 'Termal Veri Yok');
    assert.equal(doc.getElementById('card-tmax').querySelector('.card-quality-warning'), null,
        'Modül değişince önceki şüpheli uyarısı kalmaz');
});

// --------------------------------------------------------------------------
test('UI-07: vekil 502/503/504 döndürünce API çevrimdışı sayılır; 500 çevrimiçi kalır', async () => {
    // Gerçek yığında görüldü: analiz_api konteyneri durdurulunca Nginx /api için
    // 502/504 döndürdü, gösterge "API ÇEVRİMİÇİ" kaldı. Tarayıcı API'ye hiç değmez;
    // vekilin ağ geçidi hatası, API'ye ulaşılamadığının tek belirtisidir.
    const doc = setupMockEnvironment();
    const app = await loadApp();

    for (const kod of [502, 503, 504]) {
        global.fetch = async () => yanit({}, { ok: false, status: kod });
        await app.hiyerarsiyiYukle();
        assert.equal(app.state.isOnline, false, `HTTP ${kod} = API'ye ulaşılamıyor`);
        assert.equal(doc.getElementById('api-status-text').textContent, 'BAĞLANTI KESİLDİ');
    }

    global.fetch = async () => yanit({ hata: { mesaj: 'patladı' } }, { ok: false, status: 500 });
    await app.hiyerarsiyiYukle();
    assert.equal(app.state.isOnline, true, 'HTTP 500 API\'nin kendisinden gelir; erişilebilir');
});

// --------------------------------------------------------------------------
test('UI-02: yavaş başarısız olan modül isteği, üstüne binen taramalar yüzünden hatayı gizlemez', async () => {
    // Gerçek yığında görüldü: vekil 502'yi ~17 sn'de döndürüyor, tarama 3 sn'de bir
    // yeni istek açıyordu. Her başarısızlık kendinden yenisi tarafından "eski"
    // sayılıp düşüyor, hata şeridi hiç boyanmıyor, kartlar bayat değerle "sağlıklı"
    // görünüyordu.
    const doc = setupMockEnvironment();
    const app = await loadApp();
    app.canliGoruntuyeDon();

    // 1) Önce sağlıklı bir boyama.
    global.fetch = async (url) => {
        if (url.includes('/termal/son')) return yanit({}, { ok: false, status: 404 });
        if (url.includes('/seri')) return yanit({ noktalar: [] });
        return yanit(modulDetayi('M1'));
    };
    app.modulSec('M1', 'M1');
    await new Promise(r => setTimeout(r, 0));
    await new Promise(r => setTimeout(r, 0));
    assert.equal(doc.getElementById('val-temp').textContent, '25.0');

    // 2) API düşer: istekler yavaş (bekletilen) 502 ile biter.
    const bekleyenler = [];
    global.fetch = (url) => new Promise((resolve) => {
        bekleyenler.push(() => resolve(yanit({}, { ok: false, status: 502 })));
    });

    const t1 = app.modulDetayYukle('M1', true);   // tarama #1 (yavaş)
    const t2 = app.modulDetayYukle('M1', true);   // tarama #2: süren istek varken atlanır
    const t3 = app.modulDetayYukle('M1', true);   // tarama #3: atlanır
    assert.equal(bekleyenler.length, 1, 'Süren istek varken tarama yeni istek açmaz');

    bekleyenler[0]();
    await Promise.all([t1, t2, t3]);

    assert.equal(doc.getElementById('module-error-banner').style.display, 'flex',
        'Geç gelen hata boyanır: hata şeridi görünür');
    assert.match(doc.getElementById('module-error-banner').textContent, /HTTP 502/);
    assert.equal(doc.getElementById('active-module-status-badge').textContent, 'HATA');
    assert.equal(app.state.isOnline, false, '502 = çevrimdışı');
    assert.equal(doc.getElementById('val-temp').textContent, '--',
        'Hata anında bayat 25.0 ekranda kalmaz');

    // 2b) API geri gelir, aynı modülde tarama sürer: hata şeridi kalkar, değerler döner.
    global.fetch = async (url) => {
        if (url.includes('/termal/son')) return yanit({}, { ok: false, status: 404 });
        if (url.includes('/seri')) return yanit({ noktalar: [] });
        return yanit(modulDetayi('M1'));
    };
    await app.modulDetayYukle('M1', true);
    assert.equal(doc.getElementById('module-error-banner').style.display, 'none',
        'Bağlantı dönünce kesinti şeridi kalkar');
    assert.equal(doc.getElementById('val-temp').textContent, '25.0');
    assert.equal(app.state.isOnline, true);

    // 3) Operatör bu arada başka modüle geçtiyse eski modülün hatası boyanmaz.
    global.fetch = (url) => new Promise((resolve) => {
        bekleyenler.push(() => resolve(yanit({}, { ok: false, status: 502 })));
    });
    const t4 = app.modulDetayYukle('M1');
    app.state.aktifModulId = 'M2';
    doc.getElementById('module-error-banner').style.display = 'none';
    doc.getElementById('module-error-banner').textContent = '';
    bekleyenler[bekleyenler.length - 1]();
    await t4;
    assert.equal(doc.getElementById('module-error-banner').textContent, '',
        'Seçili olmayan modülün geç hatası ekrana yazılmaz');
});

// --------------------------------------------------------------------------
test('UI-07: sayfa API kesintisinde açıldıysa ağaç bağlantı gelince kendiliğinden dolar', async () => {
    // Gerçek yığında görüldü: analiz_api kapalıyken açılan sayfa "Hiyerarşi taranıyor..."
    // yazısında kalıyor, API dönünce de operatör "Yenile"ye basmadıkça dolmuyordu.
    const doc = setupMockEnvironment();
    const app = await loadApp();
    app.state.hiyerarsiYuklendi = false;
    app.state.aktifModulId = null;

    global.fetch = async () => yanit({}, { ok: false, status: 502 });
    await app.hiyerarsiyiYukle();
    assert.equal(app.state.hiyerarsiYuklendi, false);
    assert.match(doc.getElementById('hierarchy-container').innerHTML, /alınamadı/,
        'Yer tutucu ("taranıyor") hata mesajını örtmemeli');

    // API geri gelir; periyodik tarama ağacı yeniden dener.
    global.fetch = async (url) => {
        if (url.includes('/moduller?')) return yanit({ veriler: [], sonraki: null });
        if (url.includes('/sahalar')) {
            return yanit({ sahalar: [{ saha_kodu: 'TR1', ad: 'TR1', panolar: [
                { pano_kodu: 'P1', ad: 'P1', moduller: [{ modul_id: 'TR1-P1-M1', aktif: true, seviye: 'normal' }] }
            ] }] });
        }
        if (url.includes('/termal/son')) return yanit({}, { ok: false, status: 404 });
        if (url.includes('/seri')) return yanit({ noktalar: [] });
        if (url.includes('/anomaliler')) return yanit({ veriler: [], sonraki: null });
        if (url.includes('/gecisler')) return yanit({ veriler: [], sonraki: null });
        return yanit(modulDetayi('TR1-P1-M1'));
    };
    app.state.pollIntervalMs = 5;
    app.startPolling();
    await new Promise(r => setTimeout(r, 60));
    clearInterval(app.state.pollTimer);
    app.state.pollTimer = null;
    // Tetiklenmiş asenkron geri çağrılar bitsin; sonraki testlere sızmasın.
    await new Promise(r => setTimeout(r, 30));
    assert.equal(app.state.hiyerarsiYuklendi, true, 'Tarama ağacı yeniden yükledi');
    assert.equal(app.state.aktifModulId, 'TR1-P1-M1', 'İlk modül kendiliğinden seçildi');
});

// --------------------------------------------------------------------------
test('UI-02: yavaş tarama sürerken modül değişince tarama kilidi takılı kalmaz', async () => {
    // Bot iddiası (PR #26, 1. tur): eski taramanın finally'si jetonu eskidiği için
    // detailInFlight'ı temizlemez ve tarama sonsuza kadar kilitlenir. Kilidi en yeni
    // istek temizler; o istek her zaman biter. Üretilerek çürütüldü, burada kilitli.
    const doc = setupMockEnvironment();
    const app = await loadApp();
    app.canliGoruntuyeDon();

    const bekleyen = [];
    global.fetch = (url) => new Promise((resolve) => {
        if (url.includes('/termal/son')) return resolve(yanit({}, { ok: false, status: 404 }));
        if (url.includes('/seri')) return resolve(yanit({ noktalar: [] }));
        bekleyen.push((id) => resolve(yanit(modulDetayi(id))));
    });

    // Önceki testlerden askıda kalmış istek olabilir; kullanıcı yolu (tarama değil)
    // ile temiz bir başlangıç: M1 seçilir ve yanıtı gelir.
    app.modulSec('M1', 'M1');
    await new Promise(r => setTimeout(r, 0));
    bekleyen.shift()('M1');
    await new Promise(r => setTimeout(r, 5));
    assert.equal(bekleyen.length, 0);

    const yavasTarama = app.modulDetayYukle('M1', true);   // tarama isteği askıda
    app.modulSec('M2', 'M2');                               // kullanıcı tıklar (tarama değil)
    await new Promise(r => setTimeout(r, 0));
    assert.equal(bekleyen.length, 2, 'Kullanıcı tıklaması tarama kilidine takılmaz');

    bekleyen[1]('M2');                                      // yeni modül yanıtı önce
    await new Promise(r => setTimeout(r, 5));
    bekleyen[0]('M1');                                      // eski tarama sonra
    await yavasTarama;
    await new Promise(r => setTimeout(r, 5));

    const onceki = bekleyen.length;
    app.modulDetayYukle('M2', true);
    await new Promise(r => setTimeout(r, 0));
    assert.equal(bekleyen.length, onceki + 1, 'Sonraki tarama yeni istek açabiliyor: kilit takılı değil');
    assert.equal(doc.getElementById('active-module-name').textContent, 'M2');
    assert.equal(doc.getElementById('module-error-banner').style.display || 'none', 'none',
        'Eski taramanın geç yanıtı M2 ekranına hata basmaz');
});
