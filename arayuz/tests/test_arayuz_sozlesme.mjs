/**
 * Grid Up — İZ C: Monitoring Arayüzü Kabul ve Sözleşme Testleri
 * Koşturma: node --test arayuz/tests/test_arayuz_sozlesme.mjs
 * 
 * UI-01 - UI-08 Sözleşme ve Kabul Kriterleri Doğrulaması
 */

import test from 'node:test';
import assert from 'node:assert/strict';

// Basit ve Güvenilir Mock DOM Ortamı
class MockElement {
    constructor(tagName = 'div', id = '') {
        this.tagName = tagName.toUpperCase();
        this._id = id;
        this.className = '';
        this.classList = {
            add: (c) => {
                const parts = this.className ? this.className.split(' ') : [];
                if (!parts.includes(c)) parts.push(c);
                this.className = parts.join(' ');
            },
            remove: (c) => {
                const parts = this.className ? this.className.split(' ') : [];
                this.className = parts.filter(x => x !== c).join(' ');
            },
            contains: (c) => (this.className ? this.className.split(' ').includes(c) : false)
        };
        this._textContent = undefined;
        this.innerHTML = '';
        this.children = [];
        this.parentNode = null;
        this.style = {};
        this.attributes = {};
        this.eventListeners = {};
        this.value = '';
        this.width = 480;
        this.height = 360;

        if (id && global.document && global.document.registerElement) {
            global.document.registerElement(id, this);
        }
    }

    get id() {
        return this._id;
    }

    set id(val) {
        this._id = val;
        if (val && global.document && global.document.registerElement) {
            global.document.registerElement(val, this);
        }
    }

    get textContent() {
        if (this._textContent !== undefined) return this._textContent;
        return this.children.map(c => c.textContent).join(' ');
    }

    set textContent(val) {
        this._textContent = String(val);
        this.children = [];
    }

    focus() {}

    appendChild(child) {
        this._textContent = undefined;
        child.parentNode = this;
        this.children.push(child);
        return child;
    }

    remove() {
        if (this._id && global.document && global.document.elements) {
            global.document.elements.delete(this._id);
        }
        if (this.parentNode) {
            const idx = this.parentNode.children.indexOf(this);
            if (idx !== -1) {
                this.parentNode.children.splice(idx, 1);
            }
        }
    }

    querySelector(selector) {
        for (const child of this.children) {
            if (selector.startsWith('.') && child.className.split(' ').includes(selector.slice(1))) {
                return child;
            }
            if (selector.startsWith('#') && child.id === selector.slice(1)) {
                return child;
            }
            const found = child.querySelector(selector);
            if (found) return found;
        }
        return null;
    }

    querySelectorAll(selector) {
        const results = [];
        for (const child of this.children) {
            if (selector.startsWith('.') && child.className.split(' ').includes(selector.slice(1))) {
                results.push(child);
            }
            if (selector.startsWith('#') && child.id === selector.slice(1)) {
                results.push(child);
            }
            results.push(...child.querySelectorAll(selector));
        }
        return results;
    }

    addEventListener(event, callback) {
        this.eventListeners[event] = this.eventListeners[event] || [];
        this.eventListeners[event].push(callback);
    }

    click() {
        const list = this.eventListeners['click'] || [];
        for (const cb of list) {
            cb({ stopPropagation: () => {} });
        }
    }

    getBoundingClientRect() {
        return { width: this.width, height: this.height, left: 0, top: 0 };
    }

    getContext() {
        return {
            fillRect: () => {},
            clearRect: () => {},
            beginPath: () => {},
            arc: () => {},
            fill: () => {},
            stroke: () => {},
            moveTo: () => {},
            lineTo: () => {},
            closePath: () => {},
            fillText: () => {},
            save: () => {},
            restore: () => {},
            scale: () => {},
            setLineDash: () => {}
        };
    }

    removeAttribute(name) {
        delete this.attributes[name];
    }
}

class MockDocument {
    constructor() {
        this.elements = new Map();
        this.body = new MockElement('body', 'body');
    }

    createElement(tagName) {
        return new MockElement(tagName);
    }

    getElementById(id) {
        return this.elements.get(id) || null;
    }

    registerElement(id, el) {
        this.elements.set(id, el);
    }

    querySelectorAll(selector) {
        const results = [];
        for (const el of this.elements.values()) {
            if (selector.startsWith('[id^="') && selector.endsWith('"]')) {
                const prefix = selector.slice(6, -2);
                if (el.id.startsWith(prefix)) results.push(el);
            } else if (selector.startsWith('.')) {
                const cls = selector.slice(1);
                if (el.className.split(' ').includes(cls)) results.push(el);
            }
        }
        return results;
    }
}

// Global ortam kurulumu
function setupMockEnvironment() {
    const doc = new MockDocument();

    const ids = [
        'hierarchy-container', 'hierarchy-count',
        'active-module-badge', 'active-module-name', 'active-module-status-badge', 'active-module-device-badge',
        'val-time', 'val-feed', 'val-rssi',
        'module-error-banner',
        'val-temp', 'val-hum', 'val-tmax', 'val-l1', 'val-l2', 'val-l3', 'val-notr', 'val-arc',
        'val-tmax-box', 'hotspot-coord', 'current-diff',
        'temp-status', 'hum-status', 'notr-status', 'arc-status',
        'card-temp', 'card-hum', 'card-tmax', 'card-current', 'card-notr', 'card-arc',
        'thermal-source-badge', 'btn-live-thermal', 'btn-toggle-smooth', 'btn-toggle-grid',
        'thermalCanvas', 'hotspot-reticle', 'reticle-temp',
        'thermal-tooltip', 'tooltip-temp', 'tooltip-coord',
        'thermal-status-banner', 'banner-icon', 'banner-title', 'banner-desc',
        'active-alarm-count', 'alarms-container', 'audit-container',
        'operator-id-input',
        'timeseries-metric', 'timeseries-range', 'timeseries-interval', 'btn-refresh-series',
        'timeseriesCanvas', 'timeseries-message', 'timeseries-info', 'timeseries-tooltip',
        'api-status-led', 'api-status-text', 'clock-display'
    ];

    ids.forEach(id => {
        const tagName = id.toLowerCase().includes('canvas') ? 'canvas' : (id.includes('input') ? 'input' : (id.includes('select') ? 'select' : 'div'));
        const el = new MockElement(tagName, id);
        doc.registerElement(id, el);
    });

    // Default operator input value
    doc.getElementById('operator-id-input').value = 'test_operator';

    global.document = doc;
    global.window = {
        location: { hostname: 'localhost', port: '8080', protocol: 'http:' },
        addEventListener: () => {}
    };
    return doc;
}

// --------------------------------------------------------------------------
// TESTLER
// --------------------------------------------------------------------------

async function loadApp() {
    const mod = await import('../app.js');
    return mod.default || globalThis.GridUpApp || mod;
}

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

test('UI-02: Modül seçimi yarış durumu (Race Condition) ve servis hatası izolasyonu', async () => {
    setupMockEnvironment();
    const app = await loadApp();

    // Senaryo: A seçilir, A'nın yanıtı 50ms gecikir. Hemen B seçilir, B 5ms'de döner.
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

    await Promise.all([pA, pB]);

    // B seçili olduğu için ekranda A'ya ait 99.9 kalmamalı, B'nin 24.5 değeri olmalıdır
    const tempEl = document.getElementById('val-temp');
    assert.equal(tempEl.textContent, '24.5', "A'nın geciken yanıtı B ekranını ezmemeli");
    const badgeEl = document.getElementById('active-module-badge');
    assert.equal(badgeEl.textContent, 'MODUL-B', "Başlık MODUL-B olmalı");

    // Servis hatası senaryosu: B'nin detay isteği 500 dönerse açık hata görünmeli, A'nın metrikleri görünmemeli
    global.fetch = async () => ({
        ok: false,
        status: 500,
        json: async () => ({ hata: { mesaj: "Sunucu arızası" } })
    });

    await app.modulDetayYukle('MODUL-C');
    const errBanner = document.getElementById('module-error-banner');
    assert.equal(errBanner.style.display, 'flex', "Hata bandı görünür olmalı");
    assert.equal(document.getElementById('val-temp').textContent, '--', "Hata anında önceki metrikler temizlenmeli");
});

test('UI-03: Canlı ölçüm kalitesi, eksik nötr/ark, null besleme ve faz dengesizliği', async () => {
    setupMockEnvironment();
    const app = await loadApp();

    global.fetch = async () => ({
        ok: true,
        json: async () => ({
            modul_id: 'M-KALITE-TEST',
            aktif: true,
            besleme: null,       // null besleme sebeke yapılmamalı!
            sinyal: null,        // null sinyal
            son_gorulme: '2026-09-19T12:00:00Z',
            son_olcumler: [
                { olcum_tipi: 'ortam_sicaklik', deger: 0.0, birim: 'C', kalite: 'iyi' }, // Gerçek 0
                { olcum_tipi: 'nem', deger: 45.0, birim: '%', kalite: 'supheli' },      // Şüpheli kalite
                { olcum_tipi: 'akim_l1', deger: 10.0, birim: 'A', kalite: 'iyi' },
                { olcum_tipi: 'akim_l2', deger: 10.5, birim: 'A', kalite: 'supheli' },  // L2 şüpheli!
                { olcum_tipi: 'akim_l3', deger: 10.2, birim: 'A', kalite: 'iyi' }
                // akim_notr ve ark_olay EKSİK (dizide yok)
            ]
        })
    });

    await app.modulDetayYukle('M-KALITE-TEST');

    // 1. besleme=null "BİLİNMİYOR" olmalı, "ŞEBEKE" olmamalı
    const feedEl = document.getElementById('val-feed');
    assert.equal(feedEl.textContent, 'BİLİNMİYOR');

    // 2. Gerçek 0 değeri gösterilmeli
    const tempEl = document.getElementById('val-temp');
    assert.equal(tempEl.textContent, '0.0');

    // 3. Eksik nötr akımı ve ark sayacı kesinlikle '0' olmamalı, '--' olmalı
    const notrEl = document.getElementById('val-notr');
    const arcEl = document.getElementById('val-arc');
    assert.equal(notrEl.textContent, '--', 'Eksik nötr akımı -- olmalı');
    assert.equal(arcEl.textContent, '--', 'Eksik ark sayacı -- olmalı');

    // 4. L2 şüpheli olduğundan faz dengesizliği hesaplanamamalı
    const diffEl = document.getElementById('current-diff');
    assert.equal(diffEl.textContent, 'Faz Dengesizliği: Hesaplanamadı', 'Şüpheli faz varken denge güvenilir hesaplanmamalı');

    // 5. Şüpheli ölçüm uyarısı eklenmeli
    const humCard = document.getElementById('card-hum');
    assert.ok(humCard.querySelector('.card-quality-warning'), 'Şüpheli ölçüm kartında uyarı görünmeli');
});

test('UI-04: Gerçek 768 tam kare doğrulama, eksik/bozuk kare reddi ve piksel okuma', async () => {
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
});

test('UI-05: 51 açık + 2 onaylı olayda 53 çözülmemiş olay taranması ve onay akışı', async () => {
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
    assert.equal(postCount, 1, '500 hatasında tek bir POST yapılmalı, sessizce fallback tekrarı yapılmamalı');
    assert.ok(document.getElementById('alarm-card-A-2'), '500 hatasında kart silinmemeli');
});

test('UI-06: Zaman serisi ham ve kovalanmış noktalar, şüpheli işaretleme ve izolasyon', async () => {
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
});

test('UI-07: Operasyon günlüğü artan sıradan en büyük son 30 geçişin alınması ve 61 numaralı geçiş', async () => {
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
                        sonraki: 61,
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

    // Günlük isteği hata verirse eski liste korunmalı ve hata bildirilmeli
    global.fetch = async () => ({ ok: false, status: 500 });
    await app.operasyonGunluguYukle();
    assert.equal(app.state.gunlukHata, true, 'Günlük hatası bayrağı set edilmeli');
    assert.equal(app.state.gecisler.length, 30, 'Eski liste korunmalı');
});

test('UI-08: HTML enjeksiyonu ve XSS koruması doğrulaması', async () => {
    setupMockEnvironment();
    const app = await loadApp();

    const zararliGerekce = '<script>alert("xss")</script><img src=x onerror=alert(1)>';
    const guvenli = app.escapeHtml(zararliGerekce);

    assert.doesNotMatch(guvenli, /<script>/, 'Script etiketi kaçışlanmalı');
    assert.doesNotMatch(guvenli, /<img/, 'Img etiketi kaçışlanmalı');
    assert.match(guvenli, /&lt;script&gt;/, 'Güvenli HTML formatında olmalı');

    // Tek tırnaklı modul_id testi
    const tirnakliId = "MODUL'--DROP";
    const kacisliTirnak = app.escapeHtml(tirnakliId);
    assert.match(kacisliTirnak, /&#39;/, 'Tek tırnak kaçışlanmalı');
});
