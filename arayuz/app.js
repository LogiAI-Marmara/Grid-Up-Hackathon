/**
 * Grid Up - İZ C: Operasyon Yüzü & Monitoring Uygulaması
 * Sözleşme ⑤ ve IZ_C_ARAYUZ_GOREV_TANIMI.md kabul kriterlerine tam uyumlu sürüm.
 * UI-01 - UI-08 gereksinimlerini eksiksiz karşılar.
 */

// API Base URL tespiti (açık ve kestirilebilir sıra):
//   1. window.GRIDUP_API_URL verilmişse ona uyulur (dağıtım kararı).
//   2. file:// ile açıldıysa vekil yoktur; doğrudan API'ye gidilir.
//   3. Sayfa 8080'den geliyorsa API sayfayı zaten kendisi sunuyordur; göreli yol.
//   4. Diğer tüm HTTP(S) durumlarında sayfa Nginx arkasındadır → /api vekili.
//      (Konteyner 80 yerine 8081 gibi bir konak portuna bağlandığında da vekil
//      yolu korunur; port tahminine dayalı `http://host:8080` sapması yapılmaz.)
const API_HOST = (typeof window !== 'undefined' && window.location && window.location.hostname) || "localhost";
const API_BASE = (typeof window !== 'undefined' && window.GRIDUP_API_URL)
    || (typeof window !== 'undefined' && window.location && window.location.protocol === "file:"
        ? `http://${API_HOST}:8080`
        : (typeof window !== 'undefined' && window.location && window.location.port === "8080"
            ? ""
            : "/api"));

// Vekil (Nginx) katmanının arkadaki API'ye ulaşamadığını söyleyen durum kodları.
const AGGECIDI_HATALARI = new Set([502, 503, 504]);

// Güvenli API Çağrısı (UI-02: 4xx/5xx durumunda sessizce 8080'e fallback yapmaz, POST'u tekrarlamaz)
async function apiFetch(path, options = {}) {
    const cleanPath = path.startsWith('/') ? path : `/${path}`;
    const primaryUrl = `${API_BASE}${cleanPath}`;
    try {
        const res = await fetch(primaryUrl, options);
        // UI-07 kural 4: Gösterge yalnız API'ye ERİŞİLEBİLDİĞİNİ söyler. HTTP 4xx/5xx
        // de erişilebilir bir API'dir; ilgili bölüm kendi hatasını ayrıca gösterir.
        // İstisna: 502/503/504. Dağıtımda tarayıcı API'ye hiç değmez, Nginx'e
        // (/api vekili) konuşur; bu üçü vekilin "arkadaki API'ye ulaşamadım"
        // demesidir. Gerçek yığında görüldü: analiz_api durdurulunca Nginx 502/504
        // döndü ve gösterge "API ÇEVRİMİÇİ" kaldı.
        setOnlineStatus(!AGGECIDI_HATALARI.has(res.status));
        return res;
    } catch (err) {
        // Ağ/DNS/zaman aşımı: API'ye hiç ulaşılamadı
        setOnlineStatus(false);
        throw err;
    }
}

// Güvenli HTML Kaçış Yardımcısı (UI-08 XSS Koruması)
function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// Uygulama Durumu (State)
const state = {
    aktifModulId: null,
    aktifModulIsmi: '',
    // UI-02: Ekranda hâlihazırda verisi boyalı olan modül (aktifModulId'den ayrıdır)
    ekrandakiModulId: null,
    // UI-07: Hiyerarşi bir kez başarıyla ağaca basıldı mı? Sayfa API kesintisi
    // sırasında açıldıysa false kalır ve periyodik tarama yeniden dener.
    hiyerarsiYuklendi: false,
    termalMatris: null,
    // UI-04: Ekrandaki 768 piksel ÖLÇÜLMÜŞ tam kare mi, yoksa özetten türetilmiş tahmin mi?
    termalMatrisOlculdu: false,
    termalOzet: null,
    kanitKareModu: false,
    seciliAnomaliId: null,
    kanitAnomali: null,
    smoothMode: true,
    gridMode: false,
    audioEnabled: true,
    pollIntervalMs: 3000,
    pollTimer: null,
    isOnline: true,
    // Modül çalışma durumları (/moduller'den: aktif, sessiz, pasif)
    modulDurumlari: {},
    // Modül alarm seviyeleri (/sahalar ve açık anomalilerden: normal, izle, uyari, kritik)
    apiModulSeviyeleri: {},
    alarmModulSeviyeleri: {},
    cozulmemisAnomaliler: [],
    // Operasyon günlüğü (en büyük son 30 geçiş kaydı)
    gecisler: [],
    sonGecisId: null,
    gunlukHata: false,
    // Zaman serisi grafiği
    seriKanal: 'ortam_sicaklik',
    seriAralik: '',
    seriZamanAralik: '',
    seriNoktalar: [],
    seriCokluVeri: null,
    aktifSeriCizimVerisi: null,
    seriHataMesaji: null,
    sonGorulmeZamani: null,
    seriBasZamanMs: null,
    seriBitZamanMs: null,
    seriesPollCounter: 0
};

// Asenkron Yarış Durumu (Race Condition) Sayaçları (UI-02, UI-04, UI-06)
let detailRequestToken = 0;
// Ekrana başarıyla boyanan son modül-detay isteğinin jetonu. Geç gelen bir HATA,
// kendisinden yeni bir BAŞARI yoksa yine de boyanır (aşağıda, catch'te).
let detailLastOkToken = 0;
let detailInFlight = false;
let detailInFlightSince = 0;
// Süren istek bu süreyi aşarsa tarama yeni istek açabilir: hiç yanıt vermeyen
// bir bağlantı (fetch'in zaman aşımı yoktur) taramayı sonsuza kadar kilitlemesin.
const DETAY_ISTEK_KILIT_MS = 30000;
let thermalRequestToken = 0;
let seriesRequestToken = 0;
let evidenceRequestToken = 0;

// UI-04 kural 2: Ölçülmemiş termal görselin üzerinde sürekli duran zorunlu ibare
const SENTETIK_GORSEL_UYARISI = 'Özetten üretilmiş tahmini görsel — ölçülmüş piksel değildir';

// UI-03: Desteklenen kanal/birim eşleşmeleri sözlüğü
const DESTEKLENEN_BIRIMLER = {
    'ortam_sicaklik': ['C', '°C'],
    'nem': ['%'],
    'akim_l1': ['A'],
    'akim_l2': ['A'],
    'akim_l3': ['A'],
    'akim_notr': ['A'],
    'ark_olay': ['adet', 'sayi', '']
};

function birimGecerliMi(olcumTipi, birim) {
    if (!olcumTipi || !DESTEKLENEN_BIRIMLER[olcumTipi]) return true;
    if (birim === null || birim === undefined) return true;
    const b = String(birim).trim();
    const gecerliler = DESTEKLENEN_BIRIMLER[olcumTipi];
    return gecerliler.some(g => g.toLowerCase() === b.toLowerCase());
}

// Türkiye Saati (Europe/Istanbul - UTC+3) Formatlayıcı
function formatZamanTr(isoStr) {
    if (!isoStr) return '--:--:--';
    try {
        const d = new Date(isoStr);
        if (isNaN(d.getTime())) return String(isoStr).replace('T', ' ').replace('Z', '');
        return d.toLocaleString('tr-TR', {
            timeZone: 'Europe/Istanbul',
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    } catch (e) {
        return String(isoStr).replace('T', ' ').replace('Z', '');
    }
}

const SEVIYE_PUANI = { normal: 0, izle: 1, uyari: 2, kritik: 3 };

function seviyeNormalize(seviye) {
    if (!seviye) return null;
    const deger = String(seviye).trim().toLocaleLowerCase('tr-TR');
    return Object.prototype.hasOwnProperty.call(SEVIYE_PUANI, deger) ? deger : null;
}

function enYuksekSeviye(...seviyeler) {
    const gecerliler = seviyeler.map(seviyeNormalize).filter(Boolean);
    if (gecerliler.length === 0) return 'normal';
    return gecerliler.reduce((enY, s) => SEVIYE_PUANI[s] > SEVIYE_PUANI[enY] ? s : enY, 'normal');
}

function modulSeviyesiniGetir(modulId) {
    // UI-03 kural 8: Resmî seviye yalnız API'nin tanınan `seviye` değerinden ve
    // kapanmamış anomalilerden gelir. Değer hiç yoksa ya da tanınmıyorsa (bozuk,
    // yazım hatalı, eksik) "normal" İDDİA EDİLMEZ; "bilinmiyor" gösterilir.
    const apiSev = state.apiModulSeviyeleri[modulId];
    const alarmSev = state.alarmModulSeviyeleri[modulId];

    const taninanlar = [apiSev, alarmSev].filter(s => seviyeNormalize(s) !== null);
    if (taninanlar.length === 0) {
        return 'bilinmiyor';
    }
    return enYuksekSeviye(...taninanlar);
}

function modulRozetiniGuncelle(modulId) {
    const seviye = modulSeviyesiniGetir(modulId);
    const treeBadge = document.getElementById(`tree-badge-${modulId}`);
    if (treeBadge) {
        if (seviye === 'bilinmiyor') {
            treeBadge.className = 'status-badge';
            treeBadge.style.background = 'rgba(100, 116, 139, 0.25)';
            treeBadge.style.color = 'var(--text-muted)';
            treeBadge.innerText = 'SEVİYE BİLİNMİYOR';
        } else {
            treeBadge.removeAttribute('style');
            treeBadge.className = `status-badge badge-${seviye}`;
            treeBadge.innerText = seviye.toUpperCase();
        }
    }
    if (modulId === state.aktifModulId && !state.kanitKareModu) {
        const topBadge = document.getElementById('active-module-status-badge');
        if (topBadge) {
            if (seviye === 'bilinmiyor') {
                topBadge.className = 'status-badge';
                topBadge.style.background = 'rgba(100, 116, 139, 0.25)';
                topBadge.style.color = 'var(--text-muted)';
                topBadge.innerText = 'SEVİYE BİLİNMİYOR';
            } else {
                topBadge.removeAttribute('style');
                topBadge.className = `status-badge badge-${seviye}`;
                topBadge.innerText = seviye.toUpperCase();
            }
        }
    }
    return seviye;
}

// Web Audio API Sentezleyici
class SoundFx {
    constructor() {
        this.ctx = null;
    }
    init() {
        if (!this.ctx && typeof window !== 'undefined') {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            if (AudioContext) this.ctx = new AudioContext();
        }
    }
    playAlert() {
        if (!state.audioEnabled) return;
        try {
            this.init();
            if (!this.ctx) return;
            if (this.ctx.state === 'suspended') this.ctx.resume();

            const osc = this.ctx.createOscillator();
            const gain = this.ctx.createGain();
            osc.type = 'triangle';
            osc.frequency.setValueAtTime(880, this.ctx.currentTime);
            osc.frequency.exponentialRampToValueAtTime(440, this.ctx.currentTime + 0.18);

            gain.gain.setValueAtTime(0.2, this.ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, this.ctx.currentTime + 0.2);

            osc.connect(gain);
            gain.connect(this.ctx.destination);
            osc.start();
            osc.stop(this.ctx.currentTime + 0.22);
        } catch (e) {
            console.warn("Audio uyarısı çalınamadı:", e);
        }
    }
}
const sfx = new SoundFx();

// --------------------------------------------------------------------------
// UI-01 & UI-08: SAHA HİYERARŞİSİ VE MODÜL DURUMU
// --------------------------------------------------------------------------
async function tumModulDurumlariniCek() {
    const durumHaritasi = {};
    let ofset = 0;
    const limit = 50;
    let devam = true;

    while (devam) {
        try {
            const res = await apiFetch(`/moduller?limit=${limit}&ofset=${ofset}`);
            if (!res.ok) break;
            const data = await res.json();
            const veriler = data.veriler || [];
            veriler.forEach(m => {
                if (m.modul_id) {
                    const isPasif = (m.durum === 'pasif' || m.aktif === false);
                    const durum = isPasif ? 'pasif' : (m.durum || (m.aktif ? 'aktif' : 'bilinmiyor'));
                    durumHaritasi[m.modul_id] = {
                        durum: durum,
                        son_gorulme: m.son_gorulme,
                        seviye: m.seviye,
                        aktif: !isPasif
                    };
                }
            });
            ofset += veriler.length;
            if (veriler.length === 0 || ofset >= (data.toplam || 0)) {
                devam = false;
            }
        } catch (err) {
            console.warn("Modül durumu sayfalama hatası:", err);
            break;
        }
    }
    return durumHaritasi;
}

// UI-01: Modülün cihaz durumunu (aktif, sessiz, pasif) ağaçta ve seçiliyse üst panelde anında güncelle
function modulCihazDurumunuAğactaGuncelle(modulId, durum, aktif) {
    let cihazDurumuText = 'Durum bilinmiyor';
    let cihazDurumuClass = '';

    if (aktif === false || durum === 'pasif') {
        cihazDurumuText = 'Pasif';
        cihazDurumuClass = 'pasif';
    } else if (durum === 'sessiz') {
        cihazDurumuText = 'Sessiz';
        cihazDurumuClass = 'sessiz';
    } else if (durum === 'aktif') {
        cihazDurumuText = 'Aktif';
    }

    // State'i de senkronize et
    if (!state.modulDurumlari[modulId]) {
        state.modulDurumlari[modulId] = {};
    }
    const finalDurum = (aktif === false || durum === 'pasif') ? 'pasif' : (durum || 'bilinmiyor');
    state.modulDurumlari[modulId].durum = finalDurum;
    state.modulDurumlari[modulId].aktif = !(aktif === false || durum === 'pasif');

    const subSpan = document.getElementById(`modul-sub-text-${modulId}`);
    if (subSpan) {
        subSpan.className = `modul-sub-text ${cihazDurumuClass}`.trim();
        subSpan.textContent = cihazDurumuText;
    }

    const itemEl = document.getElementById(`modul-item-${modulId}`);
    if (itemEl) {
        if (itemEl.classList) {
            itemEl.classList.remove('device-aktif', 'device-sessiz', 'device-pasif');
            if (cihazDurumuClass) itemEl.classList.add(`device-${cihazDurumuClass}`);
        }
    }

    // Eğer bu modül seçili modül ise üst panel rozetini de güncelle
    if (modulId === state.aktifModulId) {
        const deviceBadge = document.getElementById('active-module-device-badge');
        if (deviceBadge) {
            const devKey = (aktif === false || durum === 'pasif') ? 'pasif' : (durum || 'bilinmiyor');
            deviceBadge.className = `status-badge badge-device-${devKey}`;
            deviceBadge.textContent = `CİHAZ: ${cihazDurumuText.toLocaleUpperCase('tr-TR')}`;
        }
    }
}

// UI-01: Periyodik olarak tüm modüllerin güncel durumlarını /moduller'den çekip ağacı dinamik güncelle
async function modulDurumlariniGuncelle() {
    try {
        const yeniDurumlar = await tumModulDurumlariniCek();
        if (!yeniDurumlar || Object.keys(yeniDurumlar).length === 0) return;

        state.modulDurumlari = { ...state.modulDurumlari, ...yeniDurumlar };

        for (const [mId, info] of Object.entries(yeniDurumlar)) {
            modulCihazDurumunuAğactaGuncelle(mId, info.durum, info.aktif);
            if (info.seviye !== undefined) {
                state.apiModulSeviyeleri[mId] = seviyeNormalize(info.seviye);
                modulRozetiniGuncelle(mId);
            }
        }
    } catch (err) {
        console.warn("Modül durumları güncelleme hatası:", err);
    }
}

let hiyerarsiInFlight = false;

async function hiyerarsiyiYukle() {
    const container = document.getElementById('hierarchy-container');
    const countTag = document.getElementById('hierarchy-count');
    if (!container) return;
    if (hiyerarsiInFlight) return;
    hiyerarsiInFlight = true;

    try {
        // Önce modüllerin yetkili aktif/sessiz/pasif durumlarını sayfalı olarak al
        const modulDurumlari = await tumModulDurumlariniCek();
        state.modulDurumlari = modulDurumlari;

        const res = await apiFetch('/sahalar');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        const sahalar = data.sahalar || [];
        container.innerHTML = '';

        if (sahalar.length === 0) {
            const emptyEl = document.createElement('div');
            emptyEl.className = 'empty-state';
            emptyEl.style.padding = '1.5rem';
            emptyEl.style.textAlign = 'center';
            emptyEl.style.color = 'var(--text-muted)';
            emptyEl.textContent = 'Kayıtlı saha bulunamadı.';
            container.appendChild(emptyEl);
            if (countTag) countTag.textContent = '0 Modül';
            return;
        }

        let toplamModulSayisi = 0;
        const tumModuller = [];

        sahalar.forEach(saha => {
            const sahaDiv = document.createElement('div');
            sahaDiv.className = 'tree-saha';

            const sahaHeader = document.createElement('div');
            sahaHeader.className = 'tree-saha-header';
            const sahaIcon = document.createElement('span');
            sahaIcon.textContent = '📍';
            const sahaBaslikText = document.createElement('span');
            sahaBaslikText.textContent = saha.ad ? `${saha.saha_kodu} (${saha.ad})` : (saha.saha_kodu || 'Bilinmeyen Saha');
            sahaHeader.appendChild(sahaIcon);
            sahaHeader.appendChild(sahaBaslikText);
            sahaDiv.appendChild(sahaHeader);

            const panolar = saha.panolar || [];
            if (panolar.length === 0) {
                const bosPano = document.createElement('div');
                bosPano.className = 'tree-pano-empty';
                bosPano.textContent = 'Bu sahada kayıtlı pano yok.';
                sahaDiv.appendChild(bosPano);
            }

            panolar.forEach(pano => {
                const panoDiv = document.createElement('div');
                panoDiv.className = 'tree-pano';

                const panoHeader = document.createElement('div');
                panoHeader.className = 'tree-pano-header';
                const panoIcon = document.createElement('span');
                panoIcon.textContent = '⚙️';
                const panoBaslikText = document.createElement('span');
                const panoBaslik = pano.ad ? `${pano.pano_kodu} (${pano.ad})` : (pano.pano_kodu || 'Bilinmeyen Pano');
                panoBaslikText.textContent = panoBaslik;
                panoHeader.appendChild(panoIcon);
                panoHeader.appendChild(panoBaslikText);

                const moduller = pano.moduller || [];
                if (moduller.length > 0) {
                    // UI-01 kural 4: Tıklamanın hangi modülü seçeceği açıkça anlaşılır olmalı;
                    // boş panoda sahte modül seçilmez (bu dal zaten yalnız dolu panoda çalışır).
                    const ilkModulId = moduller[0].modul_id;
                    panoHeader.style.cursor = 'pointer';
                    panoHeader.title = `İlk modülü seç: ${ilkModulId}`;
                    const ilkModulIpucu = document.createElement('span');
                    ilkModulIpucu.className = 'pano-ilk-modul-hint';
                    ilkModulIpucu.textContent = `↳ ilk modül: ${ilkModulId}`;
                    panoHeader.appendChild(ilkModulIpucu);
                    panoHeader.addEventListener('click', () => {
                        modulSec(ilkModulId, `${panoBaslik} - ${ilkModulId}`);
                    });
                }
                panoDiv.appendChild(panoHeader);

                if (moduller.length === 0) {
                    const bosModul = document.createElement('div');
                    bosModul.className = 'tree-pano-empty';
                    bosModul.textContent = 'Bu panoda modül bulunmuyor (Boş Pano).';
                    panoDiv.appendChild(bosModul);
                } else {
                    const ul = document.createElement('ul');
                    ul.className = 'tree-modul-list';

                    moduller.forEach(modul => {
                        toplamModulSayisi++;
                        tumModuller.push(modul.modul_id);
                        const mId = modul.modul_id;

                        // Modülün yetkili cihaz durumu
                        const yetkiliDurum = modulDurumlari[mId] ? modulDurumlari[mId].durum : null;
                        let cihazDurumuText = 'Durum bilinmiyor';
                        let cihazDurumuClass = '';

                        if (modul.aktif === false || yetkiliDurum === 'pasif') {
                            cihazDurumuText = 'Pasif';
                            cihazDurumuClass = 'pasif';
                        } else if (yetkiliDurum === 'sessiz') {
                            cihazDurumuText = 'Sessiz';
                            cihazDurumuClass = 'sessiz';
                        } else if (yetkiliDurum === 'aktif') {
                            cihazDurumuText = 'Aktif';
                        }

                        // Alarm seviyesi
                        const apiSeviye = seviyeNormalize(modul.seviye);
                        state.apiModulSeviyeleri[mId] = apiSeviye;

                        const li = document.createElement('li');
                        li.className = `tree-modul-item ${mId === state.aktifModulId ? 'active' : ''}`;
                        li.id = `modul-item-${mId}`;
                        li.addEventListener('click', () => {
                            modulSec(mId, mId);
                        });

                        const infoLeft = document.createElement('div');
                        infoLeft.className = 'modul-info-left';

                        const idSpan = document.createElement('span');
                        idSpan.className = 'modul-id-text';
                        idSpan.textContent = mId;

                        const subSpan = document.createElement('span');
                        subSpan.id = `modul-sub-text-${mId}`;
                        subSpan.className = `modul-sub-text ${cihazDurumuClass}`.trim();
                        subSpan.textContent = cihazDurumuText;

                        infoLeft.appendChild(idSpan);
                        infoLeft.appendChild(subSpan);

                        const badgeSpan = document.createElement('span');
                        badgeSpan.id = `tree-badge-${mId}`;
                        const currentSev = modulSeviyesiniGetir(mId);
                        if (currentSev === 'bilinmiyor') {
                            badgeSpan.className = 'status-badge';
                            badgeSpan.style.background = 'rgba(100, 116, 139, 0.25)';
                            badgeSpan.style.color = 'var(--text-muted)';
                            badgeSpan.textContent = 'SEVİYE BİLİNMİYOR';
                        } else {
                            badgeSpan.className = `status-badge badge-${currentSev}`;
                            badgeSpan.textContent = currentSev.toUpperCase();
                        }

                        li.appendChild(infoLeft);
                        li.appendChild(badgeSpan);
                        ul.appendChild(li);
                    });
                    panoDiv.appendChild(ul);
                }
                sahaDiv.appendChild(panoDiv);
            });
            container.appendChild(sahaDiv);
        });

        if (countTag) countTag.textContent = `${toplamModulSayisi} Modül`;
        state.hiyerarsiYuklendi = true;

        // Seçili modül listede yoksa ilk geçerli modülü otomatik seç
        if (tumModuller.length > 0 && (!state.aktifModulId || !tumModuller.includes(state.aktifModulId))) {
            _modulSecProgramatik(tumModuller[0], tumModuller[0]);
        }
    } catch (err) {
        console.warn("Hiyerarşi yükleme hatası:", err);
        // UI-02: Tek bir servisin hatası genel online durumunu ezmemeli, ağaç içine hata basılır.
        // Ölçüt "çocuk yok" değil "ağaç hiç basılmadı": index.html'deki "Hiyerarşi
        // taranıyor..." yer tutucusu da bir çocuktur ve hata mesajını örtüyordu.
        if (!state.hiyerarsiYuklendi) {
            container.innerHTML = `
                <div class="empty-state" style="padding: 1.5rem; text-align: center; color: #fca5a5;">
                    <p>⚠️ Hiyerarşi verisi alınamadı (${escapeHtml(err.message || 'Hata')}). Bağlantı gelince yeniden denenecek.</p>
                </div>
            `;
        }
    } finally {
        hiyerarsiInFlight = false;
    }
}

// --------------------------------------------------------------------------
// UI-02 & UI-03: MODÜL SEÇİMİ, ASENKRON İZOLASYON VE CANLI ÖLÇÜMLER
// --------------------------------------------------------------------------
function modulSec(modulId, modulIsmi) {
    state.aktifModulId = modulId;
    state.aktifModulIsmi = modulIsmi || modulId;
    state.kanitKareModu = false;
    state.seciliAnomaliId = null;
    state.kanitAnomali = null;

    const btnLive = document.getElementById('btn-live-thermal');
    if (btnLive) btnLive.style.display = 'none';

    document.querySelectorAll('.tree-modul-item').forEach(el => {
        if (el && el.classList) el.classList.remove('active');
    });
    const seciliEl = document.getElementById(`modul-item-${modulId}`);
    if (seciliEl && seciliEl.classList) seciliEl.classList.add('active');

    modulDetayYukle(modulId);
    zamanSerisiYukle();
}

function _modulSecProgramatik(modulId, modulIsmi) {
    if (state.kanitKareModu || state.seciliAnomaliId) return;
    state.aktifModulId = modulId;
    state.aktifModulIsmi = modulIsmi || modulId;

    document.querySelectorAll('.tree-modul-item').forEach(el => {
        if (el && el.classList) el.classList.remove('active');
    });
    const seciliEl = document.getElementById(`modul-item-${modulId}`);
    if (seciliEl && seciliEl.classList) seciliEl.classList.add('active');

    resetModulEkranGorunumu(modulId, state.aktifModulIsmi);
    modulDetayYukle(modulId);
    zamanSerisiYukle();
}

// UI-02: Modül seçildiğinde alanları anında temizleyen yardımcı fonksiyon
// Ölçüm kartlarını "--" durumuna alır. Modül değişiminde ve modül detayı
// alınamadığında kullanılır: hata anında bayat değerler ekranda kalmamalı (UI-02).
function olcumKartlariniSifirla() {
    const kartDegerleri = ['val-temp', 'val-hum', 'val-tmax', 'val-l1', 'val-l2', 'val-l3', 'val-notr', 'val-arc'];
    kartDegerleri.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = '--';
    });
    const kartAltyazilari = ['temp-status', 'hum-status', 'hotspot-coord', 'notr-status', 'arc-status'];
    kartAltyazilari.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = 'Veri yok';
    });

    const diffEl = document.getElementById('current-diff');
    if (diffEl) {
        diffEl.textContent = 'Faz Dengesizliği: Hesaplanamadı';
        diffEl.style.color = 'var(--text-muted)';
    }

    // Varsa önceki kalite uyarılarını temizle
    document.querySelectorAll('.card-quality-warning, .card-quality-bad, .card-unit-warning').forEach(e => e.remove());
}

function resetModulEkranGorunumu(modulId, modulIsmi) {
    // UI-02: Ekran bundan sonra bu modüle aittir
    state.ekrandakiModulId = modulId;
    const badgeEl = document.getElementById('active-module-badge');
    const nameEl = document.getElementById('active-module-name');
    const statusBadge = document.getElementById('active-module-status-badge');
    const deviceBadge = document.getElementById('active-module-device-badge');
    const errorBanner = document.getElementById('module-error-banner');

    if (badgeEl) badgeEl.textContent = modulId;
    if (nameEl) nameEl.textContent = modulIsmi || modulId;
    if (statusBadge) {
        statusBadge.className = 'status-badge badge-normal';
        statusBadge.textContent = 'YÜKLENİYOR...';
        statusBadge.removeAttribute('style');
    }
    if (deviceBadge) {
        deviceBadge.className = 'status-badge badge-device';
        deviceBadge.textContent = 'CİHAZ: --';
    }
    if (errorBanner) {
        errorBanner.style.display = 'none';
        errorBanner.textContent = '';
    }

    const valTime = document.getElementById('val-time');
    const valFeed = document.getElementById('val-feed');
    const valRssi = document.getElementById('val-rssi');

    if (valTime) valTime.textContent = '--:--:--';
    if (valFeed) {
        valFeed.textContent = 'BİLİNMİYOR';
        valFeed.className = 'badge-feed';
    }
    if (valRssi) valRssi.textContent = 'Bilinmiyor';
    const valDurumZaman = document.getElementById('val-durum-zaman');
    if (valDurumZaman) valDurumZaman.textContent = '🛈 Durum bildirimi: Yükleniyor...';

    olcumKartlariniSifirla();

    // Termal reticle gizle
    const reticle = document.getElementById('hotspot-reticle');
    if (reticle) reticle.style.display = 'none';
    const reticleTempReset = document.getElementById('reticle-temp');
    if (reticleTempReset && reticleTempReset.classList) {
        reticleTempReset.classList.remove('pos-bottom');
        reticleTempReset.classList.remove('pos-left');
        reticleTempReset.classList.remove('pos-right');
    }

    const bannerDesc = document.getElementById('banner-desc');
    const bannerTitle = document.getElementById('banner-title');
    const bannerIcon = document.getElementById('banner-icon');
    if (bannerTitle) bannerTitle.textContent = 'Termal Durum:';
    if (bannerDesc) bannerDesc.textContent = 'Termal veri bekleniyor...';
    if (bannerIcon) bannerIcon.textContent = 'ℹ️';

    const sourceBadge = document.getElementById('thermal-source-badge');
    if (sourceBadge) {
        sourceBadge.className = 'thermal-resolution';
        sourceBadge.textContent = 'Veri Bekleniyor';
    }

    // UI-02: Termal görseli ve durumunu anında temizle (eski modülün görüntüsü kalmasın)
    state.termalMatris = null;
    state.termalMatrisOlculdu = false;
    state.termalOzet = null;
    state.kanitKareModu = false;
    state.termalKaynak = 'canli';
    state.seciliAnomaliId = null;
    state.kanitAnomali = null;
    ++evidenceRequestToken;

    const tCanvas = document.getElementById('thermalCanvas');
    if (tCanvas) {
        const tCtx = tCanvas.getContext('2d');
        if (tCtx) {
            tCtx.clearRect(0, 0, tCanvas.width, tCanvas.height);
            tCtx.fillStyle = '#070b14';
            tCtx.fillRect(0, 0, tCanvas.width, tCanvas.height);
        }
    }
    termalKareCiz();

    // UI-02 / UI-06: Zaman serisi alanını anında sıfırla
    state.seriNoktalar = [];
    state.seriCokluVeri = null;
    state.aktifSeriCizimVerisi = null;
    const tsCanvas = document.getElementById('timeseriesCanvas');
    if (tsCanvas) {
        const tsCtx = tsCanvas.getContext('2d');
        if (tsCtx) {
            tsCtx.clearRect(0, 0, tsCanvas.width, tsCanvas.height);
            tsCtx.fillStyle = '#070b14';
            tsCtx.fillRect(0, 0, tsCanvas.width, tsCanvas.height);
        }
    }
    const tsMsg = document.getElementById('timeseries-message');
    if (tsMsg) {
        tsMsg.style.display = 'flex';
        tsMsg.className = 'timeseries-message';
        tsMsg.textContent = 'Zaman serisi yükleniyor...';
    }
    const tsInfo = document.getElementById('timeseries-info');
    if (tsInfo) tsInfo.textContent = 'Yükleniyor...';
    const tsTooltip = document.getElementById('timeseries-tooltip');
    if (tsTooltip) tsTooltip.style.display = 'none';
}

async function modulDetayYukle(modulId, isPolling = false) {
    if (!modulId) return;

    // Periyodik tarama, süren bir isteğin üstüne yenisini bindirmez. Vekil
    // 502/504'ü saniyeler sonra döndürdüğünde 3 sn'lik tarama istekleri
    // birikiyor, her biri bir sonrakince "eski" sayılıp düşüyor ve hata hiç
    // boyanmıyordu: operatör ekranda bayat değerleri sağlıklı sanıyordu.
    if (isPolling && detailInFlight && (Date.now() - detailInFlightSince) < DETAY_ISTEK_KILIT_MS) return;

    // UI-02: Asenkron yarış durumu koruması için istek jetonu
    const currentToken = ++detailRequestToken;
    detailInFlight = true;
    detailInFlightSince = Date.now();

    // UI-02: "Ekranda hangi modülün verisi boyalı?" sorusunun yanıtı state.aktifModulId
    // OLAMAZ: modulSec() çağrıdan önce aktif modülü değiştirdiği için karşılaştırma
    // daima eşit çıkar ve önceki modülün değerleri yeni başlık altında ekranda kalırdı.
    // Bu yüzden boyanmış modül ayrı izlenir.
    const modulDegisti = (state.ekrandakiModulId !== modulId);
    state.aktifModulId = modulId;

    // UI-02: Önceki modülün verilerini bir an bile göstermemek için modül DEĞİŞTİĞİNDE veya ilk seçimde sıfırla.
    // Periyodik canlı telemetri taraması (isPolling=true) sırasında aynı modül için ekranı ve zaman serisi grafiğini asla sıfırlama!
    if (modulDegisti && !isPolling) {
        resetModulEkranGorunumu(modulId, state.aktifModulIsmi);
    }

    try {
        const res = await apiFetch(`/moduller/${encodeURIComponent(modulId)}`);

        // Geç gelen yanıt kontrolü
        if (currentToken !== detailRequestToken) return;

        if (!res.ok) {
            throw new Error(`HTTP ${res.status}`);
        }

        const data = await res.json();
        if (currentToken !== detailRequestToken) return;
        detailLastOkToken = currentToken;

        // Bağlantı geri geldi: kesinti sırasında basılan hata şeridi kalkmalı.
        // Yalnız modül değişiminde temizlenmesi yetmiyordu; aynı modülde kalan
        // operatör API döndükten sonra da "detay verisi alınamadı" görüyordu.
        const kesintiSeridi = document.getElementById('module-error-banner');
        if (kesintiSeridi) {
            kesintiSeridi.style.display = 'none';
            kesintiSeridi.textContent = '';
        }

        // Son görülme referans zamanını kaydet
        if (data.son_gorulme) {
            state.sonGorulmeZamani = data.son_gorulme;
        }

        const badgeEl = document.getElementById('active-module-badge');
        const nameEl = document.getElementById('active-module-name');
        if (badgeEl && (!badgeEl.textContent || badgeEl.textContent === '--')) {
            badgeEl.textContent = modulId;
        }
        if (nameEl && (!nameEl.textContent || nameEl.textContent === 'Modül Seçiniz')) {
            nameEl.textContent = state.aktifModulIsmi || modulId;
        }

        // 1. Cihaz Durumu ve Zaman (UI-01)
        const modulDurumKaydi = state.modulDurumlari[modulId] || {};
        let cihazDurumu = modulDurumKaydi.durum;
        if (data.aktif === false) {
            cihazDurumu = 'pasif';
        } else if (data.durum) {
            cihazDurumu = data.durum;
        } else if (!cihazDurumu) {
            cihazDurumu = 'bilinmiyor';
        }

        // Ağaçtaki ve üst başlıktaki cihaz durumunu hemen güncelle ve state'i senkronize et
        modulCihazDurumunuAğactaGuncelle(modulId, cihazDurumu, data.aktif);

        // Son görülme zamanı (TSİ)
        const valTime = document.getElementById('val-time');
        if (valTime) {
            valTime.textContent = formatZamanTr(data.son_gorulme);
        }

        // Besleme: data.besleme null/undefined ise "BİLİNMİYOR" göster
        const feedEl = document.getElementById('val-feed');
        if (feedEl) {
            if (data.besleme) {
                const beslemeStr = String(data.besleme).toLowerCase();
                feedEl.textContent = beslemeStr.toUpperCase();
                feedEl.className = beslemeStr === 'yedek' ? 'badge-feed badge-warning' : 'badge-feed';
            } else {
                feedEl.textContent = 'BİLİNMİYOR';
                feedEl.className = 'badge-feed';
            }
        }

        // Sinyal (RSSI): null ise "Bilinmiyor"
        const rssiEl = document.getElementById('val-rssi');
        if (rssiEl) {
            if (data.sinyal !== null && data.sinyal !== undefined && !isNaN(Number(data.sinyal))) {
                rssiEl.textContent = `${data.sinyal} dBm`;
            } else {
                rssiEl.textContent = 'Bilinmiyor';
            }
        }

        // UI-03 kural 3: besleme/sinyal `modul_durum` kaydından gelir; bunların NE ZAMAN
        // bildirildiğini yalnız `durum_zaman` söyler. durum_zaman yoksa bu değerlerin
        // güncel olduğu iddia edilmez.
        const durumZamanEl = document.getElementById('val-durum-zaman');
        if (durumZamanEl) {
            if (data.durum_zaman) {
                durumZamanEl.textContent = `🛈 Durum bildirimi: ${formatZamanTr(data.durum_zaman)} TSİ`;
            } else {
                durumZamanEl.textContent = '🛈 Durum bildirimi: Bilinmiyor (besleme/RSSI güncelliği doğrulanamıyor)';
            }
        }

        // 2. Canlı Ölçümler (UI-03 Kuralları: birim kontrolü, her kanalın kalite ve zamanı)
        const sonOlcumler = Array.isArray(data.son_olcumler) ? data.son_olcumler : [];
        const olcumMap = {};
        sonOlcumler.forEach(o => {
            if (o && o.olcum_tipi) {
                olcumMap[o.olcum_tipi] = o;
            }
        });

        // Metrik kartlarını güvenli doldur
        olcumKartiniGuncelle('val-temp', 'card-temp', 'temp-status', olcumMap.ortam_sicaklik, 'Sensör: SHT31', 1, 'ortam_sicaklik');
        olcumKartiniGuncelle('val-hum', 'card-hum', 'hum-status', olcumMap.nem, 'Optimum: %40-60', 1, 'nem');
        olcumKartiniGuncelle('val-notr', 'card-notr', 'notr-status', olcumMap.akim_notr, 'Dönüş Hattı Akımı', 1, 'akim_notr');
        olcumKartiniGuncelle('val-arc', 'card-arc', 'arc-status', olcumMap.ark_olay, 'TVOC-2 Optik Koruma', 0, 'ark_olay');

        // 3-Faz Akım Yükü (L1, L2, L3) birim, kalite ve zaman kontrolleri
        const oL1 = olcumMap.akim_l1;
        const oL2 = olcumMap.akim_l2;
        const oL3 = olcumMap.akim_l3;
        const cardCurrent = document.getElementById('card-current');

        if (cardCurrent) {
            const eskiWarn = cardCurrent.querySelector('.card-quality-warning, .card-quality-bad, .card-unit-warning');
            if (eskiWarn) eskiWarn.remove();
        }

        const l1Uyumsuz = oL1 && !birimGecerliMi('akim_l1', oL1.birim);
        const l2Uyumsuz = oL2 && !birimGecerliMi('akim_l2', oL2.birim);
        const l3Uyumsuz = oL3 && !birimGecerliMi('akim_l3', oL3.birim);

        const valL1 = document.getElementById('val-l1');
        const valL2 = document.getElementById('val-l2');
        const valL3 = document.getElementById('val-l3');

        if (valL1) {
            if (l1Uyumsuz) valL1.textContent = 'Birim Uyumsuz';
            else if (!oL1 || oL1.deger === null || oL1.kalite === 'yok' || isNaN(Number(oL1.deger))) valL1.textContent = '--';
            else valL1.textContent = Number(oL1.deger).toFixed(1);
        }
        if (valL2) {
            if (l2Uyumsuz) valL2.textContent = 'Birim Uyumsuz';
            else if (!oL2 || oL2.deger === null || oL2.kalite === 'yok' || isNaN(Number(oL2.deger))) valL2.textContent = '--';
            else valL2.textContent = Number(oL2.deger).toFixed(1);
        }
        if (valL3) {
            if (l3Uyumsuz) valL3.textContent = 'Birim Uyumsuz';
            else if (!oL3 || oL3.deger === null || oL3.kalite === 'yok' || isNaN(Number(oL3.deger))) valL3.textContent = '--';
            else valL3.textContent = Number(oL3.deger).toFixed(1);
        }

        const fazlarSupheli = (oL1 && oL1.kalite === 'supheli') || (oL2 && oL2.kalite === 'supheli') || (oL3 && oL3.kalite === 'supheli');
        if (cardCurrent) {
            if (l1Uyumsuz || l2Uyumsuz || l3Uyumsuz) {
                const warn = document.createElement('span');
                warn.className = 'card-quality-warning card-unit-warning';
                warn.textContent = '⚠️ Akım Birim Uyumsuz';
                cardCurrent.appendChild(warn);
            } else if (fazlarSupheli) {
                const warn = document.createElement('span');
                warn.className = 'card-quality-warning';
                warn.textContent = '⚠️ Şüpheli faz ölçümü';
                cardCurrent.appendChild(warn);
            }
        }

        // Faz Dengesizliği: Yalnızca L1, L2, L3'ün üçü de varsa, birimleri geçerli, sayısal ve kalite=iyi ise hesaplanır
        const diffEl = document.getElementById('current-diff');

        if (oL1 && oL2 && oL3 &&
            !l1Uyumsuz && !l2Uyumsuz && !l3Uyumsuz &&
            oL1.kalite === 'iyi' && oL2.kalite === 'iyi' && oL3.kalite === 'iyi' &&
            oL1.deger !== null && oL2.deger !== null && oL3.deger !== null &&
            !isNaN(Number(oL1.deger)) && !isNaN(Number(oL2.deger)) && !isNaN(Number(oL3.deger))) {

            const a1 = Number(oL1.deger);
            const a2 = Number(oL2.deger);
            const a3 = Number(oL3.deger);
            const ort = (a1 + a2 + a3) / 3;
            const maksFark = Math.max(Math.abs(a1 - ort), Math.abs(a2 - ort), Math.abs(a3 - ort));
            const dengesizlik = ort > 0 ? ((maksFark / ort) * 100).toFixed(1) : '0.0';

            if (diffEl) {
                diffEl.textContent = `Faz Dengesizliği: %${dengesizlik}`;
                diffEl.style.color = Number(dengesizlik) > 15 ? 'var(--color-warning)' : 'var(--text-muted)';
            }
        } else {
            if (diffEl) {
                diffEl.textContent = 'Faz Dengesizliği: Hesaplanamadı';
                diffEl.style.color = 'var(--text-muted)';
            }
        }

        // 3. Alarm Seviyesi Senkronizasyonu (UI-03 kuralı: API normal ve açık anomali yoksa normale döner)
        const acikAnomaliler = Array.isArray(data.acik_anomaliler) ? data.acik_anomaliler : [];
        if (acikAnomaliler.length > 0) {
            const enKotu = acikAnomaliler
                .map(a => seviyeNormalize(a.seviye))
                .filter(Boolean)
                .reduce((enY, s) => SEVIYE_PUANI[s] > SEVIYE_PUANI[enY] ? s : enY, 'normal');
            state.alarmModulSeviyeleri[modulId] = enKotu;
        } else {
            // Açık anomali yoksa alarm seviyesi kalıntısı temizlenir
            delete state.alarmModulSeviyeleri[modulId];
        }

        if (data.seviye !== undefined) {
            state.apiModulSeviyeleri[modulId] = seviyeNormalize(data.seviye);
        }

        modulRozetiniGuncelle(modulId);

        // 4. Termal Veri Yükleme
        if (!state.kanitKareModu) {
            await canliTermalYukle(modulId, olcumMap);
        }
    } catch (err) {
        // Geç gelen hata: bu istek eskimiş olsa da, ekranda ondan yeni bir BAŞARILI
        // boyama yoksa ve modül hâlâ seçiliyse hata gösterilir; aksi hâlde bayat
        // değerler "sağlıklı" görünmeye devam eder (UI-02).
        if (modulId !== state.aktifModulId) return;
        if (currentToken !== detailRequestToken && detailLastOkToken > currentToken) return;
        console.warn(`Modül detayı yüklenemedi (${modulId}):`, err);

        // UI-02: Hata anında önceki metrikleri ve termal görüntüyü sıfırla
        olcumKartlariniSifirla();
        state.termalMatris = null;
        state.termalMatrisOlculdu = false;
        state.termalOzet = null;
        termalKareCiz();

        const errorBanner = document.getElementById('module-error-banner');
        if (errorBanner) {
            errorBanner.style.display = 'flex';
            errorBanner.textContent = `⚠️ Modül (${modulId}) detay verisi alınamadı: ${err.message || 'Hata'}`;
        }
        const topBadge = document.getElementById('active-module-status-badge');
        if (topBadge) {
            topBadge.className = 'status-badge';
            topBadge.style.background = 'rgba(239, 68, 68, 0.25)';
            topBadge.style.color = 'var(--color-critical)';
            topBadge.textContent = 'HATA';
        }
    } finally {
        if (currentToken === detailRequestToken) detailInFlight = false;
    }
}

// UI-03: Ölçüm kartı güncelleme yardımcısı (birim, kalite ve zaman doğrulamasıyla)
function olcumKartiniGuncelle(valId, cardId, statusSubId, olcum, defaultSub, ondalik, olcumTipi) {
    const valEl = document.getElementById(valId);
    const cardEl = cardId ? document.getElementById(cardId) : null;
    const subEl = statusSubId ? document.getElementById(statusSubId) : null;

    // Önceki kalite ve birim uyarılarını temizle
    if (cardEl) {
        const eskiUyari = cardEl.querySelector('.card-quality-warning, .card-quality-bad, .card-unit-warning');
        if (eskiUyari) eskiUyari.remove();
    }

    // UI-03 kural 1 & 2: Kayıt yoksa, deger=null ise veya kalite='yok' ise kart
    // "Veri yok" gösterir. Sabit kart altyazısı bu durumu ÖRTMEMELİDİR: aksi hâlde
    // eksik ölçüm, sensör adını taşıyan sağlıklı bir kart gibi okunur.
    if (!olcum || olcum.deger === null || olcum.deger === undefined || olcum.kalite === 'yok') {
        if (valEl) valEl.textContent = '--';
        if (subEl) {
            const zamanEki = (olcum && olcum.zaman) ? ` | ${formatZamanTr(olcum.zaman)} TSİ` : '';
            subEl.textContent = (olcum && olcum.kalite === 'yok')
                ? `Veri yok (kalite: yok)${zamanEki}`
                : 'Veri yok';
        }
        if (cardEl && olcum && olcum.kalite === 'yok') {
            const badSpan = document.createElement('span');
            badSpan.className = 'card-quality-bad';
            badSpan.textContent = '⛔ Ölçüm yok (kalite: yok)';
            cardEl.appendChild(badSpan);
        }
        return;
    }

    const tip = olcumTipi || olcum.olcum_tipi;
    // UI-03 Kural 5: Desteklenen kanal/birim eşleşmesi doğrulanır
    if (!birimGecerliMi(tip, olcum.birim)) {
        if (valEl) valEl.textContent = '--';
        if (subEl) subEl.textContent = `Birim uyumsuz (${olcum.birim || 'belirtilmemiş'})`;
        if (cardEl) {
            const warnSpan = document.createElement('span');
            warnSpan.className = 'card-quality-warning card-unit-warning';
            warnSpan.textContent = `⚠️ Birim Uyumsuz (${olcum.birim})`;
            cardEl.appendChild(warnSpan);
        }
        return;
    }

    const valNum = Number(olcum.deger);
    if (isNaN(valNum)) {
        if (valEl) valEl.textContent = '--';
        return;
    }

    if (valEl) {
        valEl.textContent = ondalik > 0 ? valNum.toFixed(ondalik) : String(Math.round(valNum));
    }

    // UI-03 Kural 4: Her gösterilen kanalın kendi zaman damgası ve kalite bilgisi
    if (subEl) {
        const zamanStr = olcum.zaman ? `${formatZamanTr(olcum.zaman)} TSİ` : 'Zaman yok';
        const kaliteStr = olcum.kalite ? ` [Kalite: ${olcum.kalite}]` : '';
        subEl.textContent = `${defaultSub ? defaultSub + ' | ' : ''}${zamanStr}${kaliteStr}`;
    }

    if (olcum.kalite === 'supheli' && cardEl) {
        const warnSpan = document.createElement('span');
        warnSpan.className = 'card-quality-warning';
        warnSpan.textContent = '⚠️ Şüpheli ölçüm';
        cardEl.appendChild(warnSpan);
    }
}

// --------------------------------------------------------------------------
// UI-04: TERMAL MATRİS, GERÇEK KARE DOĞRULAMA VE GÖRSELLEŞTİRME
// --------------------------------------------------------------------------
function sicaklikToRenk(temp) {
    if (temp <= 20) {
        return 'hsl(240, 100%, 45%)';
    } else if (temp < 85) {
        const hue = 240 - ((temp - 20) * (240 / 65));
        return `hsl(${Math.max(0, Math.min(240, hue))}, 100%, 50%)`;
    } else {
        const lightness = Math.min(75, 50 + (temp - 85) * 1.2);
        return `hsl(0, 100%, ${lightness}%)`;
    }
}

// Özetten tahmini matris üretme (UI-04: Sahte gürültü / dinamik animasyon eklenmez!)
function bolgelerdenTahminiMatrisUret(ozet, olcumMap) {
    const matris = new Array(768);
    const ortam = (olcumMap && olcumMap.ortam_sicaklik && olcumMap.ortam_sicaklik.deger !== null)
        ? Number(olcumMap.ortam_sicaklik.deger)
        : 25.0;

    const bolgeler = (ozet && Array.isArray(ozet.bolge_ort) && ozet.bolge_ort.length === 4)
        ? ozet.bolge_ort.map(Number)
        : [ortam, ortam, ortam, ortam];

    const maks = (ozet && ozet.maks !== undefined && ozet.maks !== null)
        ? Number(ozet.maks)
        : Math.max(...bolgeler);

    const [hx, hy] = (ozet && Array.isArray(ozet.maks_konum) && ozet.maks_konum.length === 2)
        ? ozet.maks_konum
        : [16, 12];

    for (let y = 0; y < 24; y++) {
        const rowNorm = y / 23;
        for (let x = 0; x < 32; x++) {
            const colNorm = x / 31;
            const b00 = bolgeler[0];
            const b10 = bolgeler[1];
            const b01 = bolgeler[2];
            const b11 = bolgeler[3];

            const top = b00 * (1 - colNorm) + b10 * colNorm;
            const bottom = b01 * (1 - colNorm) + b11 * colNorm;
            let val = top * (1 - rowNorm) + bottom * rowNorm;

            const dx = x - hx;
            const dy = y - hy;
            const distSq = (dx * dx) + (dy * dy * 1.5);
            const peakDelta = Math.max(0, maks - val);
            const spotIntensity = Math.exp(-distSq / 12.0);
            val += peakDelta * spotIntensity;

            // Statik, deterministik değer (sahte sensör gürültüsü YOKTUR)
            matris[y * 32 + x] = Math.max(10, Math.min(130, val));
        }
    }
    return matris;
}

// 768 Sonlu Sayısal Piksel Doğrulama (UI-04 Kural 1)
function tamKareyiDogrula(kareData, beklenenModulId, beklenenZaman) {
    if (!kareData) return false;
    if (kareData.satir_sayisi !== 24 || kareData.sutun_sayisi !== 32) return false;
    if (!Array.isArray(kareData.piksel_verisi) || kareData.piksel_verisi.length !== 768) return false;

    // Tüm pikseller sonlu sayı olmalıdır (NaN, null, string reddedilir)
    for (let i = 0; i < 768; i++) {
        const val = kareData.piksel_verisi[i];
        if (typeof val !== 'number' || !Number.isFinite(val)) {
            return false;
        }
    }

    if (beklenenModulId && kareData.modul_id !== beklenenModulId) return false;
    if (beklenenZaman && kareData.zaman !== beklenenZaman) return false;

    return true;
}

async function canliTermalYukle(modulId, olcumMap) {
    const currentToken = ++thermalRequestToken;
    const sourceBadge = document.getElementById('thermal-source-badge');
    const valTmax = document.getElementById('val-tmax');
    const hotspotEl = document.getElementById('hotspot-coord');
    const bannerTitle = document.getElementById('banner-title');
    const bannerDesc = document.getElementById('banner-desc');
    const bannerIcon = document.getElementById('banner-icon');

    try {
        const res = await apiFetch(`/moduller/${encodeURIComponent(modulId)}/termal/son`);
        if (currentToken !== thermalRequestToken) return;

        if (res.ok) {
            const ozet = await res.json();
            if (currentToken !== thermalRequestToken) return;

            state.termalOzet = ozet;
            // Özet varken kart özetten dolar; 404 dalının bıraktığı kalite uyarısı kalmasın.
            const tmaxCard = document.getElementById('card-tmax');
            if (tmaxCard) {
                const eskiUyari = tmaxCard.querySelector('.card-quality-warning, .card-quality-bad, .card-unit-warning');
                if (eskiUyari) eskiUyari.remove();
            }
            if (valTmax && ozet.maks !== undefined && ozet.maks !== null) {
                valTmax.textContent = Number(ozet.maks).toFixed(1);
            }
            if (hotspotEl && ozet.maks_konum) {
                hotspotEl.textContent = `Konum: X:${ozet.maks_konum[0]}, Y:${ozet.maks_konum[1]}`;
            }

            let tamKareGosterildi = false;

            if (ozet.kare_id) {
                try {
                    const kareRes = await apiFetch(`/termal/kare/${encodeURIComponent(ozet.kare_id)}`);
                    if (currentToken === thermalRequestToken && kareRes.ok) {
                        const kareData = await kareRes.json();
                        if (tamKareyiDogrula(kareData, modulId, ozet.zaman)) {
                            state.termalMatris = kareData.piksel_verisi;
                            state.termalMatrisOlculdu = true;
                            tamKareGosterildi = true;
                            if (sourceBadge) {
                                sourceBadge.className = 'thermal-resolution source-tam';
                                sourceBadge.textContent = 'Ölçülmüş Tam Kare';
                            }
                            termalKareCiz();
                        }
                    }
                } catch (e) {
                    console.warn("Tam kare isteği başarısız:", e);
                }
            }

            if (!tamKareGosterildi && currentToken === thermalRequestToken) {
                // UI-04 Kural 2: Tam kare yoksa açıkça tahmini görsel olduğu belirtilir
                state.termalMatrisOlculdu = false;
                state.termalMatris = bolgelerdenTahminiMatrisUret(ozet, olcumMap);
                if (sourceBadge) {
                    sourceBadge.className = 'thermal-resolution source-ozet';
                    sourceBadge.textContent = 'Tam kare mevcut değil; yalnız termal özet var';
                }
                termalKareCiz();
            }

            if (bannerTitle) bannerTitle.textContent = 'Termal Özet Analizi:';
            if (bannerIcon) bannerIcon.textContent = '🔥';
            if (bannerDesc) {
                bannerDesc.textContent = `Sıcak nokta: ${ozet.maks !== undefined ? Number(ozet.maks).toFixed(1) + ' °C' : '--'} (Zaman: ${formatZamanTr(ozet.zaman)} TSİ)`;
            }
        } else {
            // Özet yok. Kart yine de son_olcumler'deki termal_maks kanalını gösterir:
            // aksi hâlde şüpheli bir termal ölçüm (kalite=supheli, örn. 153.9 °C) ile
            // hiç ölçüm olmaması aynı "Termal Veri Yok" görünümüne çöker (UI-03).
            // Matris çizilmez; kanıt karesi yok.
            if (sourceBadge) {
                sourceBadge.className = 'thermal-resolution source-hata';
                sourceBadge.textContent = 'Termal Veri Yok';
            }
            state.termalMatris = null;
            state.termalMatrisOlculdu = false;
            state.termalOzet = null;
            const sonTermal = olcumMap && olcumMap.termal_maks;
            if (sonTermal && sonTermal.deger !== null && sonTermal.deger !== undefined && sonTermal.kalite !== 'yok') {
                olcumKartiniGuncelle('val-tmax', 'card-tmax', 'hotspot-coord', sonTermal, 'Konum: -- (özet yok)', 1, 'termal_maks');
                if (sourceBadge) sourceBadge.textContent = 'Termal özet yok; yalnız son termal_maks ölçümü var';
                if (bannerDesc) {
                    bannerDesc.textContent = `Termal özet/kare yok. Son termal_maks ölçümü: ${Number(sonTermal.deger).toFixed(1)} °C (Zaman: ${formatZamanTr(sonTermal.zaman)} TSİ, kalite: ${sonTermal.kalite || 'belirtilmemiş'}).`;
                }
            } else {
                olcumKartiniGuncelle('val-tmax', 'card-tmax', 'hotspot-coord', sonTermal || null, 'Konum: --', 1, 'termal_maks');
                if (bannerDesc) bannerDesc.textContent = 'Bu modül için termal ölçüm kaydı bulunmuyor.';
            }
            termalKareCiz();
        }
    } catch (err) {
        if (currentToken !== thermalRequestToken) return;
        console.warn("Termal veri hatası:", err);
    }
}

// UI-04: Kanıt Karesi İnceleme
async function anomaliSec(anomaliId) {
    // UI-05 kural 1: Olayın yüklenmiş listede bulunmaması onu yok sayma gerekçesi
    // değildir; ayrıntı doğrudan /anomaliler/{id} ucundan okunur.
    let anomali = state.cozulmemisAnomaliler.find(a => a.id === anomaliId);
    if (!anomali) {
        try {
            const detayRes = await apiFetch(`/anomaliler/${encodeURIComponent(anomaliId)}`);
            if (!detayRes.ok) return;
            anomali = await detayRes.json();
        } catch (e) {
            console.warn(`Anomali ayrıntısı okunamadı (${anomaliId}):`, e);
            return;
        }
        if (!anomali || !anomali.id) return;
    }

    // UI-04: Asenkron yarış durumu (geç gelen kanıt yanıtı) için jeton
    const currentToken = ++evidenceRequestToken;

    state.seciliAnomaliId = anomaliId;
    state.kanitAnomali = anomali;
    state.kanitKareModu = true;
    state.termalKaynak = 'kanit';

    // Alarm seçildiğinde ilgili modülü de seçili yap ve rozetini senkronize et
    if (anomali.modul_id && anomali.modul_id !== state.aktifModulId) {
        state.aktifModulId = anomali.modul_id;
        state.aktifModulIsmi = anomali.modul_id;
        document.querySelectorAll('.tree-modul-item').forEach(el => {
            if (el && el.classList) el.classList.remove('active');
        });
        const seciliEl = document.getElementById(`modul-item-${anomali.modul_id}`);
        if (seciliEl && seciliEl.classList) seciliEl.classList.add('active');
        const badgeEl = document.getElementById('active-module-badge');
        const nameEl = document.getElementById('active-module-name');
        if (badgeEl) badgeEl.textContent = anomali.modul_id;
        if (nameEl) nameEl.textContent = anomali.modul_id;
        modulRozetiniGuncelle(anomali.modul_id);
    }

    document.querySelectorAll('.alarm-card').forEach(c => c.classList.remove('selected-alarm'));
    const seciliKart = document.getElementById(`alarm-card-${anomaliId}`);
    if (seciliKart) seciliKart.classList.add('selected-alarm');

    const btnLive = document.getElementById('btn-live-thermal');
    if (btnLive) btnLive.style.display = 'inline-block';

    const sourceBadge = document.getElementById('thermal-source-badge');
    const bannerTitle = document.getElementById('banner-title');
    const bannerDesc = document.getElementById('banner-desc');
    const bannerIcon = document.getElementById('banner-icon');
    const valTmax = document.getElementById('val-tmax');
    const hotspotEl = document.getElementById('hotspot-coord');

    const kareId = anomali.kanit ? anomali.kanit.kare_id : null;
    const kanitPiksel = (anomali.kanit && Array.isArray(anomali.kanit.piksel) && anomali.kanit.piksel.length === 2)
        ? anomali.kanit.piksel
        : null;

    if (bannerTitle) bannerTitle.textContent = `📸 Kanıt İnceleme (${anomali.tip || anomali.id}):`;
    if (bannerIcon) bannerIcon.textContent = '🚨';
    if (bannerDesc) {
        bannerDesc.textContent = `${anomali.gerekce || 'Gerekçe sağlanmadı.'} (Tespit: ${formatZamanTr(anomali.ilk_gorulme)} TSİ)`;
    }

    if (kareId) {
        try {
            const res = await apiFetch(`/termal/kare/${encodeURIComponent(kareId)}`);
            // UI-04: Geç gelen kanıt kontrolü (seçim değişmişse veya canlıya dönülmüşse işleme alma)
            if (currentToken !== evidenceRequestToken || state.seciliAnomaliId !== anomaliId || !state.kanitKareModu) return;

            if (res.ok) {
                const kareData = await res.json();
                if (currentToken !== evidenceRequestToken || state.seciliAnomaliId !== anomaliId || !state.kanitKareModu) return;

                if (tamKareyiDogrula(kareData, anomali.modul_id, null)) {
                    state.termalMatris = kareData.piksel_verisi;
                    state.termalMatrisOlculdu = true;

                    // UI-04 Kural 3: Sıcaklık anomali skorundan (°C'ye çevrilerek) ALINMAZ!
                    // Hedef pikseli varsa piksel_verisi[y*32+x], yoksa gerçek piksel maksimumu
                    let hedefSicaklik = null;
                    let maksKonum = kanitPiksel;

                    if (kanitPiksel) {
                        const [px, py] = kanitPiksel;
                        if (px >= 0 && px < 32 && py >= 0 && py < 24) {
                            hedefSicaklik = kareData.piksel_verisi[py * 32 + px];
                        }
                    }

                    if (hedefSicaklik === null) {
                        hedefSicaklik = Math.max(...kareData.piksel_verisi);
                    }

                    state.termalOzet = {
                        maks: hedefSicaklik,
                        maks_konum: maksKonum || [16, 12]
                    };

                    if (sourceBadge) {
                        sourceBadge.className = 'thermal-resolution source-tam';
                        sourceBadge.textContent = `Kanıt Karesi (${kareId}) — Ölçülmüş Tam Kare`;
                    }
                    if (valTmax) valTmax.textContent = Number(hedefSicaklik).toFixed(1);
                    if (hotspotEl && maksKonum) hotspotEl.textContent = `Konum: X:${maksKonum[0]}, Y:${maksKonum[1]}`;

                    termalKareCiz();
                    return;
                }
            }
        } catch (e) {
            console.warn("Kanıt karesi yüklenemedi:", e);
        }
    }

    if (currentToken !== evidenceRequestToken || state.seciliAnomaliId !== anomaliId || !state.kanitKareModu) return;

    // Kare yoksa veya doğrulanamadıysa eski kare kanıt diye sunulmaz!
    state.termalMatris = null;
    state.termalMatrisOlculdu = false;
    state.termalOzet = null;
    if (sourceBadge) {
        sourceBadge.className = 'thermal-resolution source-hata';
        sourceBadge.textContent = 'Kanıt Karesi Mevcut Değil';
    }
    if (valTmax) valTmax.textContent = '--';
    if (hotspotEl) hotspotEl.textContent = 'Konum: --';
    termalKareCiz();
}

function canliGoruntuyeDon() {
    // UI-04: Canlı görünüme dönülürken bekleyen kanıt isteklerini geçersiz kıl
    ++evidenceRequestToken;
    state.kanitKareModu = false;
    state.termalKaynak = 'canli';
    state.seciliAnomaliId = null;
    state.kanitAnomali = null;

    const btnLive = document.getElementById('btn-live-thermal');
    if (btnLive) btnLive.style.display = 'none';

    document.querySelectorAll('.alarm-card').forEach(c => c.classList.remove('selected-alarm'));

    // Canlı görünüme dönünce seçili modülün güncel verisini yeniden yükle
    if (state.aktifModulId) {
        modulDetayYukle(state.aktifModulId);
    }
}

function termalKareCiz() {
    // UI-04 kural 2: Ölçülmemiş (özetten türetilmiş) görselde uyarı şeridi görüntünün
    // üzerinde SÜREKLİ görünür; ölçülmüş tam karede ise kaldırılır.
    const sentetikUyari = document.getElementById('thermal-synthetic-overlay');
    if (sentetikUyari) {
        const sentetikGoster = Boolean(state.termalMatris) && state.termalMatrisOlculdu !== true;
        if (sentetikGoster) {
            // İbarenin metni koda bağlıdır: şablon değişse de uyarı aynı kalır.
            sentetikUyari.textContent = SENTETIK_GORSEL_UYARISI;
            sentetikUyari.style.display = 'block';
        } else {
            sentetikUyari.style.display = 'none';
        }
    }

    const canvas = document.getElementById('thermalCanvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;

    ctx.clearRect(0, 0, width, height);

    if (!state.termalMatris || state.termalMatris.length !== 768) {
        ctx.fillStyle = '#0c1220';
        ctx.fillRect(0, 0, width, height);
        ctx.fillStyle = '#64748b';
        ctx.font = '14px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('Görüntülenecek termal kare yok', width / 2, height / 2);
        const reticle = document.getElementById('hotspot-reticle');
        if (reticle) reticle.style.display = 'none';
        return;
    }

    const cellW = width / 32;
    const cellH = height / 24;
    canvas.className = state.smoothMode ? 'smooth' : '';

    for (let y = 0; y < 24; y++) {
        for (let x = 0; x < 32; x++) {
            const temp = state.termalMatris[y * 32 + x];
            ctx.fillStyle = sicaklikToRenk(temp);
            ctx.fillRect(x * cellW, y * cellH, cellW, cellH);

            if (state.gridMode) {
                ctx.strokeStyle = 'rgba(0, 0, 0, 0.15)';
                ctx.lineWidth = 0.5;
                ctx.strokeRect(x * cellW, y * cellH, cellW, cellH);
            }
        }
    }

    // Sıcak nokta reticle gösterimi
    const reticle = document.getElementById('hotspot-reticle');
    const reticleTemp = document.getElementById('reticle-temp');

    if (state.termalOzet && state.termalOzet.maks_konum && reticle) {
        const [hx, hy] = state.termalOzet.maks_konum;
        const rect = canvas.getBoundingClientRect ? canvas.getBoundingClientRect() : { width: 480, height: 360 };
        const rw = rect.width || width;
        const rh = rect.height || height;
        const cW = rw / 32;
        const cH = rh / 24;

        const posX = Math.max(14, Math.min(rw - 14, (hx + 0.5) * cW));
        const posY = Math.max(14, Math.min(rh - 14, (hy + 0.5) * cH));

        reticle.style.display = 'block';
        reticle.style.left = `${posX}px`;
        reticle.style.top = `${posY}px`;

        if (reticleTemp) {
            const val = state.termalOzet.maks !== undefined ? Number(state.termalOzet.maks).toFixed(1) : '--';
            reticleTemp.textContent = `${val} °C`;

            // Üst sınıra yakınsa (posY < 55 veya hy <= 3) derece etiketini reticle altına al (kesilmeyi kesin olarak önle)
            if (posY < 55 || hy <= 3) {
                reticleTemp.style.top = '28px';
                reticleTemp.style.bottom = 'auto';
                reticleTemp.classList.add('pos-bottom');
            } else {
                reticleTemp.style.top = '-26px';
                reticleTemp.style.bottom = 'auto';
                reticleTemp.classList.remove('pos-bottom');
            }

            // Yatay sınırlarda sağa/sola taşmayı engelle
            if (posX < 55) {
                reticleTemp.style.left = '0';
                reticleTemp.style.right = 'auto';
                reticleTemp.style.transform = 'none';
                reticleTemp.classList.add('pos-right');
                reticleTemp.classList.remove('pos-left');
            } else if (posX > rw - 55) {
                reticleTemp.style.left = 'auto';
                reticleTemp.style.right = '0';
                reticleTemp.style.transform = 'none';
                reticleTemp.classList.add('pos-left');
                reticleTemp.classList.remove('pos-right');
            } else {
                reticleTemp.style.left = '50%';
                reticleTemp.style.right = 'auto';
                reticleTemp.style.transform = 'translateX(-50%)';
                reticleTemp.classList.remove('pos-left');
                reticleTemp.classList.remove('pos-right');
            }
        }
    }
}

function setupCanvasHover() {
    const canvas = document.getElementById('thermalCanvas');
    const tooltip = document.getElementById('thermal-tooltip');
    const tooltipTemp = document.getElementById('tooltip-temp');
    const tooltipCoord = document.getElementById('tooltip-coord');

    if (!canvas || !tooltip) return;

    canvas.addEventListener('mousemove', (e) => {
        if (!state.termalMatris || state.termalMatris.length !== 768) return;

        const rect = canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        const cellX = Math.floor((mouseX / rect.width) * 32);
        const cellY = Math.floor((mouseY / rect.height) * 24);

        if (cellX >= 0 && cellX < 32 && cellY >= 0 && cellY < 24) {
            const index = cellY * 32 + cellX;
            const temp = state.termalMatris[index];

            tooltip.style.display = 'block';
            tooltipTemp.textContent = `${typeof temp === 'number' ? temp.toFixed(1) : '--'} °C`;
            tooltipCoord.textContent = `X: ${cellX}, Y: ${cellY}`;

            let posX = mouseX + 14;
            let posY = mouseY + 14;
            if (posX + 100 > rect.width) posX = mouseX - 100;
            if (posY + 50 > rect.height) posY = mouseY - 50;

            tooltip.style.left = `${Math.max(4, posX)}px`;
            tooltip.style.top = `${Math.max(4, posY)}px`;
        }
    });

    canvas.addEventListener('mouseleave', () => {
        tooltip.style.display = 'none';
    });
}

// --------------------------------------------------------------------------
// UI-05: ÇÖZÜLMEMİŞ ALARMLAR LİSTESİ VE OPERATÖR ONAYI
// --------------------------------------------------------------------------
// UI-05 kural 2: `sonraki` imleci sonuna kadar izlenir; ilk 50 olay "hepsi" sanılmaz.
// Sayfalama döngüsü ilerlemeyen bir imleçte (bozuk/vekil yanıt) sonsuza kadar dönmemeli:
// imleç artmıyorsa tarama durdurulur.
async function sayfaliAnomalileriGetir(durumFiltresi) {
    const sonuclar = [];
    let sonra = null;
    let devam = true;
    const limit = 50;

    while (devam) {
        let url = `/anomaliler?durum=${encodeURIComponent(durumFiltresi)}&limit=${limit}`;
        if (sonra !== null) {
            url += `&sonra=${encodeURIComponent(sonra)}`;
        }
        const res = await apiFetch(url);
        if (!res.ok) {
            throw new Error(`HTTP ${res.status}: Alarm servisi hatası (${durumFiltresi})`);
        }
        const data = await res.json();
        const veriler = data.veriler || [];
        sonuclar.push(...veriler);

        const sonraki = data.sonraki;
        const ilerledi = (sonraki !== null && sonraki !== undefined && sonraki !== sonra);
        if (ilerledi && veriler.length > 0) {
            sonra = sonraki;
        } else {
            devam = false;
        }
    }
    return sonuclar;
}

async function alarmlariYukle() {
    const container = document.getElementById('alarms-container');
    const counterEl = document.getElementById('active-alarm-count');
    if (!container) return;

    try {
        // UI-05 Kural 1 & 2: Hem acik hem onaylandi listelenir; sayfalar sonuna kadar taranır
        const [aciklar, onaylilar] = await Promise.all([
            sayfaliAnomalileriGetir('acik'),
            sayfaliAnomalileriGetir('onaylandi')
        ]);

        const cozulmemisler = [...aciklar, ...onaylilar].sort((a, b) => (b.sira || 0) - (a.sira || 0));

        // Yeni açık alarm ses çalma kontrolü
        if (aciklar.length > 0) {
            const yeniVar = aciklar.some(a => !state.cozulmemisAnomaliler.some(sa => sa.id === a.id));
            if (yeniVar) {
                sfx.playAlert();
            }
        }

        state.cozulmemisAnomaliler = cozulmemisler;

        if (counterEl) {
            counterEl.textContent = String(cozulmemisler.length);
        }

        container.innerHTML = '';

        if (cozulmemisler.length === 0) {
            const emptyDiv = document.createElement('div');
            emptyDiv.className = 'empty-alarms';
            emptyDiv.innerHTML = `
                <span class="empty-icon">🛡️</span>
                <strong style="color:var(--color-normal); font-size: 1.1rem;">Sistem Stabil</strong>
                <p style="margin-top:6px; color: var(--text-muted); font-size: 0.85rem;">Şu anda açık veya onay bekleyen anomali bulunmamaktadır.</p>
            `;
            container.appendChild(emptyDiv);
            return;
        }

        cozulmemisler.forEach(anomali => {
            const seviye = seviyeNormalize(anomali.seviye) || 'uyari';
            const isKritik = seviye === 'kritik';
            const isOnayli = anomali.durum === 'onaylandi';
            const isSelected = anomali.id === state.seciliAnomaliId;

            const card = document.createElement('div');
            card.className = `alarm-card ${isKritik ? 'kritik' : ''} ${isSelected ? 'selected-alarm' : ''}`;
            card.id = `alarm-card-${anomali.id}`;
            card.style.cursor = 'pointer';
            card.addEventListener('click', () => {
                anomaliSec(anomali.id);
            });

            const cardHeader = document.createElement('div');
            cardHeader.className = 'alarm-card-header';

            const modSpan = document.createElement('span');
            modSpan.className = 'alarm-modul';
            modSpan.textContent = `⚠️ ${anomali.modul_id}`;

            const badgeSpan = document.createElement('span');
            badgeSpan.className = `status-badge badge-${seviye}`;
            badgeSpan.textContent = seviye.toUpperCase();

            cardHeader.appendChild(modSpan);
            cardHeader.appendChild(badgeSpan);
            card.appendChild(cardHeader);

            const timeDiv = document.createElement('div');
            timeDiv.className = 'alarm-time';
            const zaman = anomali.son_gorulme || anomali.ilk_gorulme;
            timeDiv.textContent = `⏱️ Tespit: ${formatZamanTr(zaman)} TSİ`;
            card.appendChild(timeDiv);

            const reasonDiv = document.createElement('div');
            reasonDiv.className = 'alarm-reason';
            const tipText = anomali.tip ? `${anomali.tip}: ` : '';
            const gerekceText = anomali.gerekce || 'Gerekçe sağlanmadı.';
            reasonDiv.textContent = `${tipText}${gerekceText}`;
            card.appendChild(reasonDiv);

            if (anomali.kanit && anomali.kanit.kare_id) {
                const kanitNotice = document.createElement('div');
                kanitNotice.style.fontSize = '0.75rem';
                kanitNotice.style.color = 'var(--accent-cyan)';
                kanitNotice.style.marginTop = '4px';
                kanitNotice.textContent = '📸 Kanıt Karesi Mevcut (İncelemek için tıkla)';
                card.appendChild(kanitNotice);
            }

            const btnAck = document.createElement('button');
            btnAck.className = `btn-ack ${isOnayli ? 'ack-done' : ''}`;
            btnAck.style.marginTop = '8px';

            if (isOnayli) {
                btnAck.textContent = '✓ Onaylandı — Olay Devam Ediyor';
                btnAck.disabled = true;
            } else {
                btnAck.textContent = '✓ Operatör Onayı';
                btnAck.addEventListener('click', (e) => {
                    e.stopPropagation();
                    alarmOnayla(anomali.id, anomali.modul_id);
                });
            }

            card.appendChild(btnAck);
            container.appendChild(card);
        });
    } catch (err) {
        console.warn("Alarmlar yüklenemedi:", err);
        // UI-05: Alarm servisi hata verdiğinde kesinlikle 'Sistem Stabil' denmez!
        if (counterEl) {
            counterEl.textContent = '--';
        }
        container.innerHTML = '';
        const errDiv = document.createElement('div');
        errDiv.className = 'empty-alarms alarm-error-state';
        errDiv.innerHTML = `
            <span class="empty-icon">⚠️</span>
            <strong style="color:var(--color-critical); font-size: 1.1rem;">Alarm Servisi Hatası</strong>
            <p style="margin-top:6px; color: var(--text-muted); font-size: 0.85rem;">Alarm servisi ile bağlantı kurulamadı veya sunucu hatası oluştu (${escapeHtml(err.message || 'Hata')}).</p>
        `;
        container.appendChild(errDiv);
    }
}

async function alarmOnayla(alarmId, modulId) {
    const opInput = document.getElementById('operator-id-input');
    const aktor = opInput ? opInput.value.trim() : '';

    if (!aktor) {
        alert("Onay işlemi için geçerli ve boş olmayan bir 'Operatör Kimliği' girilmelidir.");
        if (opInput && typeof opInput.focus === 'function') opInput.focus();
        return;
    }

    try {
        const res = await apiFetch(`/anomaliler/${encodeURIComponent(alarmId)}/onayla?aktor=${encodeURIComponent(aktor)}`, {
            method: 'POST'
        });

        if (res.ok) {
            const data = await res.json();
            // UI-05: Başarılı yanıtta durum=onaylandi olur; kart silinmez, onaylandı durumuna geçer!
            if (data.durum === 'onaylandi') {
                const card = document.getElementById(`alarm-card-${alarmId}`);
                if (card) {
                    const btn = card.querySelector('.btn-ack');
                    if (btn) {
                        btn.className = 'btn-ack ack-done';
                        btn.textContent = '✓ Onaylandı — Olay Devam Ediyor';
                        btn.disabled = true;
                    }
                }
            }
            await alarmlariYukle();
            operasyonGunluguYukle();
        } else if (res.status === 409) {
            // UI-05 Kural 5: 409 durumunda olay API'den yeniden okunur ve gerçek durum gösterilir
            try {
                const checkRes = await apiFetch(`/anomaliler/${encodeURIComponent(alarmId)}`);
                if (checkRes.ok) {
                    const freshData = await checkRes.json();
                    if (freshData.durum === 'kapandi') {
                        const card = document.getElementById(`alarm-card-${alarmId}`);
                        if (card) card.remove();
                    }
                }
            } catch (e) {}
            await alarmlariYukle();
            alert(`Bilgi: Anomali (${alarmId}) zaten onaylanmış veya kapanmış durumda.`);
        } else {
            const err = await res.json().catch(() => ({}));
            const msg = (err && err.hata && err.hata.mesaj) || `HTTP ${res.status}`;
            alert(`Onay işlemi başarısız: ${msg}`);
        }
    } catch (err) {
        console.error("Onaylama hatası:", err);
        alert("Sunucuya bağlanılamadı. Onay iletilemedi.");
    }
}

// --------------------------------------------------------------------------
// UI-06: ZAMAN SERİSİ GRAFİĞİ (ORTAM, TERMAL MAKS, L1, L2, L3 VE TÜM METRİKLER)
// --------------------------------------------------------------------------

function getMetrikAyar(metrik) {
    const ayarlar = {
        'ortam_sicaklik': { ad: 'Ortam Sıcaklığı', birim: '°C', renk: '#38bdf8' },
        'termal_maks': { ad: 'Termal Maks. Sıcaklık', birim: '°C', renk: '#ef4444' },
        'termal_ort': { ad: 'Termal Ort. Sıcaklık', birim: '°C', renk: '#f97316' },
        'akim_l1': { ad: 'Akım L1', birim: 'A', renk: '#f59e0b' },
        'akim_l2': { ad: 'Akım L2', birim: 'A', renk: '#10b981' },
        'akim_l3': { ad: 'Akım L3', birim: 'A', renk: '#f43f5e' },
        'akim_notr': { ad: 'Nötr Akımı', birim: 'A', renk: '#a855f7' },
        'nem': { ad: 'Bağıl Nem', birim: '%', renk: '#0ea5e9' },
        'ark_olay': { ad: 'Ark Olay Sayısı', birim: 'adet', renk: '#dc2626' }
    };
    return ayarlar[metrik] || { ad: metrik, birim: '', renk: '#38bdf8' };
}

function getZamanAraligiBas(aralikKodu, refZamanStr) {
    if (!aralikKodu) return null;
    const refDate = refZamanStr ? new Date(refZamanStr) : new Date();
    const refMs = !isNaN(refDate.getTime()) ? refDate.getTime() : Date.now();
    let diffMs = 0;
    switch (aralikKodu) {
        case '1h': diffMs = 1 * 3600 * 1000; break;
        case '6h': diffMs = 6 * 3600 * 1000; break;
        case '24h': diffMs = 24 * 3600 * 1000; break;
        case '7d': diffMs = 7 * 24 * 3600 * 1000; break;
        default: return null;
    }
    return new Date(refMs - diffMs).toISOString();
}

function handleCokFazlaNokta(intervalSelect, currentAralik) {
    const kovaSirasi = ['', '10s', '1m', '5m', '15m', '1h', '1d'];
    const idx = kovaSirasi.indexOf(currentAralik || '');
    const sonrakiKova = (idx >= 0 && idx < kovaSirasi.length - 1) ? kovaSirasi[idx + 1] : '1h';

    if (intervalSelect) {
        intervalSelect.value = sonrakiKova;
    }
    state.seriAralik = sonrakiKova;

    const infoEl = document.getElementById('timeseries-info');
    if (infoEl) {
        infoEl.textContent = `⚠️ 5000 nokta aşıldığı için kova otomatik olarak '${sonrakiKova}' seçildi.`;
    }

    return zamanSerisiYukle();
}

async function zamanSerisiYukle() {
    const modulId = state.aktifModulId;
    if (!modulId) return;

    const currentToken = ++seriesRequestToken;
    const metricSelect = document.getElementById('timeseries-metric');
    const intervalSelect = document.getElementById('timeseries-interval');
    const rangeSelect = document.getElementById('timeseries-range');
    const msgEl = document.getElementById('timeseries-message');
    const infoEl = document.getElementById('timeseries-info');

    const metrik = (metricSelect && metricSelect.value) || state.seriKanal || 'ortam_sicaklik';
    const aralik = (intervalSelect && intervalSelect.value) || state.seriAralik || '';
    const range = (rangeSelect && rangeSelect.value) !== undefined ? rangeSelect.value : (state.seriZamanAralik || '');

    if (msgEl && (!state.seriNoktalar || state.seriNoktalar.length === 0)) {
        msgEl.style.display = 'flex';
        msgEl.className = 'timeseries-message';
        msgEl.textContent = 'Zaman serisi yükleniyor...';
    }

    // bas zamanı hesapla (geçmiş filtresi)
    const refZaman = state.sonGorulmeZamani || new Date().toISOString();
    const basZaman = getZamanAraligiBas(range, refZaman);
    state.seriBasZamanMs = basZaman ? new Date(basZaman).getTime() : null;
    state.seriBitZamanMs = range ? (!isNaN(new Date(refZaman).getTime()) ? new Date(refZaman).getTime() : Date.now()) : null;
    // UI-06 kural 2: Pencerenin bitiş ucu da API'ye açıkça bildirilir; aksi hâlde
    // sunucu "şimdiye kadar" varsayar ve çizilen aralık ile istenen aralık ayrışır.
    const bitZaman = (range && state.seriBitZamanMs !== null)
        ? new Date(state.seriBitZamanMs).toISOString()
        : null;

    // 3-Faz Akımları (L1, L2, L3) çoklu karşılaştırma
    if (metrik === 'akim_hepsi') {
        try {
            const fetchFaz = async (fazTip) => {
                let url = `/moduller/${encodeURIComponent(modulId)}/seri?tip=${encodeURIComponent(fazTip)}`;
                if (aralik) url += `&aralik=${encodeURIComponent(aralik)}`;
                if (basZaman) url += `&bas=${encodeURIComponent(basZaman)}`;
                if (bitZaman) url += `&bit=${encodeURIComponent(bitZaman)}`;
                const res = await apiFetch(url);
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw { status: res.status, data: err };
                }
                return await res.json();
            };

            const [resL1, resL2, resL3] = await Promise.all([
                fetchFaz('akim_l1'),
                fetchFaz('akim_l2'),
                fetchFaz('akim_l3')
            ]);

            if (currentToken !== seriesRequestToken) return;

            const ptsL1 = Array.isArray(resL1.noktalar) ? resL1.noktalar : [];
            const ptsL2 = Array.isArray(resL2.noktalar) ? resL2.noktalar : [];
            const ptsL3 = Array.isArray(resL3.noktalar) ? resL3.noktalar : [];

            state.seriNoktalar = ptsL1;
            state.seriCokluVeri = { l1: ptsL1, l2: ptsL2, l3: ptsL3 };

            if (ptsL1.length === 0 && ptsL2.length === 0 && ptsL3.length === 0) {
                if (msgEl) {
                    msgEl.style.display = 'flex';
                    msgEl.className = 'timeseries-message';
                    msgEl.textContent = 'Bu aralıkta ölçüm yok';
                }
                if (infoEl) infoEl.textContent = '3-Faz Akımları — Ölçüm bulunamadı';
                zamanSerisiCizGenel([], metrik, aralik, state.seriCokluVeri);
                return;
            }

            if (msgEl) msgEl.style.display = 'none';
            if (infoEl) {
                const maxLen = Math.max(ptsL1.length, ptsL2.length, ptsL3.length);
                infoEl.textContent = `3-Faz Akımları (L1, L2, L3) (A) — ${maxLen} nokta (${aralik ? 'Kova: ' + aralik : 'Ham'})`;
            }

            zamanSerisiCizGenel(ptsL1, metrik, aralik, state.seriCokluVeri);
            return;
        } catch (err) {
            if (currentToken !== seriesRequestToken) return;
            if (err && err.data && err.data.hata && err.data.hata.kod === 'cok_fazla_nokta') {
                return handleCokFazlaNokta(intervalSelect, aralik);
            }
            console.warn("3-Faz zaman serisi hatası:", err);
            if (msgEl) {
                msgEl.style.display = 'flex';
                msgEl.className = 'timeseries-message error';
                msgEl.textContent = 'Grafik yüklenemedi.';
            }
            state.seriNoktalar = [];
            state.seriCokluVeri = null;
            zamanSerisiCizGenel([], metrik, aralik, null);
            return;
        }
    }

    // Tekil metrik akışı
    try {
        let url = `/moduller/${encodeURIComponent(modulId)}/seri?tip=${encodeURIComponent(metrik)}`;
        if (aralik) url += `&aralik=${encodeURIComponent(aralik)}`;
        if (basZaman) url += `&bas=${encodeURIComponent(basZaman)}`;
        if (bitZaman) url += `&bit=${encodeURIComponent(bitZaman)}`;

        const res = await apiFetch(url);
        if (currentToken !== seriesRequestToken) return;

        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            if (currentToken !== seriesRequestToken) return;

            if (errData && errData.hata && errData.hata.kod === 'cok_fazla_nokta') {
                return handleCokFazlaNokta(intervalSelect, aralik);
            } else {
                if (msgEl) {
                    msgEl.style.display = 'flex';
                    msgEl.className = 'timeseries-message error';
                    msgEl.textContent = 'Grafik yüklenemedi.';
                }
            }
            state.seriNoktalar = [];
            state.seriCokluVeri = null;
            zamanSerisiCizGenel([], metrik, aralik, null);
            return;
        }

        const data = await res.json();
        if (currentToken !== seriesRequestToken) return;

        const noktalar = Array.isArray(data.noktalar) ? data.noktalar : [];
        state.seriNoktalar = noktalar;
        state.seriCokluVeri = null;

        if (noktalar.length === 0) {
            if (msgEl) {
                msgEl.style.display = 'flex';
                msgEl.className = 'timeseries-message';
                msgEl.textContent = 'Bu aralıkta ölçüm yok';
            }
            const ayar = getMetrikAyar(metrik);
            if (infoEl) infoEl.textContent = `${ayar.ad} — Ölçüm bulunamadı`;
            zamanSerisiCizGenel([], metrik, aralik, null);
            return;
        }

        if (msgEl) msgEl.style.display = 'none';
        const ayar = getMetrikAyar(metrik);
        if (infoEl) {
            infoEl.textContent = `${ayar.ad} (${ayar.birim}) — ${noktalar.length} nokta (${aralik ? 'Kova: ' + aralik : 'Ham'})`;
        }

        zamanSerisiCizGenel(noktalar, metrik, aralik, null);
    } catch (err) {
        if (currentToken !== seriesRequestToken) return;
        console.warn("Zaman serisi hatası:", err);
        if (msgEl) {
            msgEl.style.display = 'flex';
            msgEl.className = 'timeseries-message error';
            msgEl.textContent = 'Grafik yüklenemedi.';
        }
        state.seriNoktalar = [];
        state.seriCokluVeri = null;
        zamanSerisiCizGenel([], metrik, aralik, null);
    }
}

function parseNoktalar(rawNoktalar, isAralik) {
    if (!Array.isArray(rawNoktalar)) return [];
    return rawNoktalar.map((pt, idx) => {
        let val = null;
        if (pt.val !== undefined && pt.val !== null) {
            val = pt.val;
        } else if (isAralik) {
            val = pt.ort !== undefined ? pt.ort : pt.deger;
        } else {
            val = pt.deger !== undefined ? pt.deger : pt.ort;
        }
        const num = (val !== null && val !== undefined) ? Number(val) : null;
        const isSupheli = pt.supheli !== undefined ? Boolean(pt.supheli) : (isAralik ? ((pt.supheli || 0) > 0) : (pt.kalite !== 'iyi'));
        const asgariNum = (pt.asgari !== undefined && pt.asgari !== null) ? Number(pt.asgari) : null;
        const azamiNum = (pt.azami !== undefined && pt.azami !== null) ? Number(pt.azami) : null;
        const t = pt.t !== undefined ? pt.t : (pt.zaman ? new Date(pt.zaman).getTime() : NaN);
        return {
            idx,
            val: (num !== null && !isNaN(num)) ? num : null,
            asgari: (asgariNum !== null && !isNaN(asgariNum)) ? asgariNum : null,
            azami: (azamiNum !== null && !isNaN(azamiNum)) ? azamiNum : null,
            zaman: pt.zaman,
            t: !isNaN(t) ? t : idx,
            kalite: pt.kalite,
            supheli: isSupheli,
            aralik: isAralik
        };
    }).filter(p => p.val !== null);
}

function zamanSerisiCizGenel(noktalar, metrik, aralik, cokluVeri, crosshairX = null) {
    const canvas = document.getElementById('timeseriesCanvas');
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect ? canvas.getBoundingClientRect() : { width: 760, height: 210 };
    const dpr = (typeof window !== 'undefined' && window.devicePixelRatio) || 1;
    const displayWidth = Math.round(rect.width || (canvas.parentElement ? canvas.parentElement.clientWidth : 760) || 760);
    const displayHeight = Math.round(rect.height || 210);

    if (canvas.width !== displayWidth * dpr || canvas.height !== displayHeight * dpr) {
        canvas.width = displayWidth * dpr;
        canvas.height = displayHeight * dpr;
    }

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    if (ctx.setTransform) {
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    } else if (ctx.scale) {
        ctx.scale(dpr, dpr);
    }

    const w = displayWidth;
    const h = displayHeight;

    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = '#070b14';
    ctx.fillRect(0, 0, w, h);

    const isMulti = metrik === 'akim_hepsi';
    let seriesList = [];

    if (isMulti && cokluVeri) {
        const parsedL1 = parseNoktalar(cokluVeri.l1, Boolean(aralik));
        const parsedL2 = parseNoktalar(cokluVeri.l2, Boolean(aralik));
        const parsedL3 = parseNoktalar(cokluVeri.l3, Boolean(aralik));
        seriesList = [
            { id: 'l1', ad: 'L1', renk: '#f59e0b', unit: 'A', parsed: parsedL1 },
            { id: 'l2', ad: 'L2', renk: '#10b981', unit: 'A', parsed: parsedL2 },
            { id: 'l3', ad: 'L3', renk: '#f43f5e', unit: 'A', parsed: parsedL3 }
        ];
    } else {
        const ayar = getMetrikAyar(metrik);
        const parsed = parseNoktalar(noktalar, Boolean(aralik));
        seriesList = [
            { id: metrik, ad: ayar.ad, renk: ayar.renk, unit: ayar.birim, parsed }
        ];
    }

    const allParsedPoints = seriesList.flatMap(s => s.parsed);
    if (allParsedPoints.length === 0) {
        if (ctx.restore) ctx.restore();
        state.aktifSeriCizimVerisi = null;
        return;
    }

    const unit = seriesList[0].unit;

    const paddingLeft = 75;
    const paddingRight = 35;
    const paddingTop = 30;
    const paddingBottom = 35;
    const plotW = Math.max(50, w - paddingLeft - paddingRight);
    const plotH = Math.max(50, h - paddingTop - paddingBottom);

    // Min ve Max Değerler
    let minVal = Infinity;
    let maxVal = -Infinity;
    allParsedPoints.forEach(p => {
        const lo = p.asgari !== null ? Math.min(p.asgari, p.val) : p.val;
        const hi = p.azami !== null ? Math.max(p.azami, p.val) : p.val;
        if (lo < minVal) minVal = lo;
        if (hi > maxVal) maxVal = hi;
    });

    if (minVal === Infinity || maxVal === -Infinity) {
        minVal = 0;
        maxVal = 10;
    }
    if (minVal === maxVal) {
        minVal -= 1;
        maxVal += 1;
    }
    const valSpan = maxVal - minVal;
    const yMin = Math.max(0, minVal - valSpan * 0.05);
    const yMax = maxVal + valSpan * 0.08;
    const yRange = yMax - yMin;

    // Min ve Max Zamanlar (Gerçek zaman aralıklarına göre ölçekleme)
    let minTime = Infinity;
    let maxTime = -Infinity;
    allParsedPoints.forEach(p => {
        if (!isNaN(p.t)) {
            if (p.t < minTime) minTime = p.t;
            if (p.t > maxTime) maxTime = p.t;
        }
    });

    if (minTime === Infinity || maxTime === -Infinity) {
        minTime = Date.now() - 3600000;
        maxTime = Date.now();
    }
    if (minTime === maxTime) {
        minTime -= 1000;
        maxTime += 1000;
    }

    const timeSpan = maxTime - minTime;

    function getScreenX(p, idx, totalLen) {
        if (timeSpan > 0 && !isNaN(p.t)) {
            return paddingLeft + ((p.t - minTime) / timeSpan) * plotW;
        }
        return totalLen > 1 ? paddingLeft + idx * (plotW / (totalLen - 1)) : paddingLeft + plotW / 2;
    }

    function getScreenY(val) {
        return paddingTop + plotH * (1 - (val - yMin) / yRange);
    }

    // Y Ekseni ve Yatay Izgara Çizgileri
    ctx.strokeStyle = '#17233d';
    ctx.lineWidth = 1;
    ctx.fillStyle = '#64748b';
    ctx.font = '10px monospace';
    ctx.textAlign = 'right';

    const ySteps = 4;
    for (let i = 0; i <= ySteps; i++) {
        const ratio = i / ySteps;
        const y = paddingTop + plotH * (1 - ratio);
        const labelVal = (yMin + yRange * ratio).toFixed(1);

        ctx.beginPath();
        ctx.moveTo(paddingLeft, y);
        ctx.lineTo(w - paddingRight, y);
        ctx.stroke();

        ctx.fillText(`${labelVal} ${unit}`, paddingLeft - 8, y + 3);
    }

    // X Ekseni ve Dikey Izgara Çizgileri
    const xSteps = Math.min(5, Math.max(2, Math.floor(plotW / 140)));
    for (let i = 0; i <= xSteps; i++) {
        const ratio = i / xSteps;
        const x = paddingLeft + plotW * ratio;

        ctx.beginPath();
        ctx.moveTo(x, paddingTop);
        ctx.lineTo(x, paddingTop + plotH);
        ctx.stroke();

        if (timeSpan > 0) {
            const curTime = new Date(minTime + timeSpan * ratio);
            const timeStr = curTime.toLocaleTimeString('tr-TR', {
                timeZone: 'Europe/Istanbul',
                hour: '2-digit',
                minute: '2-digit'
            });
            ctx.textAlign = 'center';
            ctx.fillStyle = '#64748b';
            ctx.fillText(timeStr, x, h - 18);
        }
    }

    // Her seriyi çiz
    seriesList.forEach(s => {
        const pts = s.parsed;
        if (pts.length === 0) return;

        pts.forEach((p, idx) => {
            p.screenX = getScreenX(p, idx, pts.length);
            p.screenY = getScreenY(p.val);
        });

        // Kova min-max alanı (aralık seçilmişse)
        if (aralik) {
            ctx.fillStyle = `${s.renk}1a`;
            ctx.beginPath();
            pts.forEach((p, idx) => {
                const azamiVal = p.azami !== null ? p.azami : p.val;
                const yHi = getScreenY(azamiVal);
                if (idx === 0) ctx.moveTo(p.screenX, yHi);
                else ctx.lineTo(p.screenX, yHi);
            });
            for (let idx = pts.length - 1; idx >= 0; idx--) {
                const p = pts[idx];
                const asgariVal = p.asgari !== null ? p.asgari : p.val;
                const yLo = getScreenY(asgariVal);
                ctx.lineTo(p.screenX, yLo);
            }
            ctx.closePath();
            ctx.fill();
        }

        // Ana çizgi (Ölçümler gerçek zaman aralıklarına göre çizilir; eksik zaman aralığı sahte çizgiyle birleştirilmez)
        ctx.strokeStyle = s.renk;
        ctx.lineWidth = isMulti ? 1.8 : 2;
        ctx.beginPath();
        let prevP = null;
        let maxGapMs = Infinity;
        if (timeSpan > 0 && pts.length > 1) {
            const avgDiff = timeSpan / (pts.length - 1);
            maxGapMs = Math.max(60000, avgDiff * 3);
        }

        pts.forEach((p, idx) => {
            const isGap = prevP && (p.t - prevP.t > maxGapMs);
            if (idx === 0 || isGap) {
                ctx.moveTo(p.screenX, p.screenY);
            } else {
                ctx.lineTo(p.screenX, p.screenY);
            }
            prevP = p;
        });
        ctx.stroke();

        // Nokta işaretleyicileri
        const drawAllDots = pts.length <= 60;
        pts.forEach(p => {
            if (drawAllDots || p.supheli) {
                ctx.beginPath();
                ctx.arc(p.screenX, p.screenY, p.supheli ? 4 : 2, 0, Math.PI * 2);
                ctx.fillStyle = p.supheli ? '#f59e0b' : s.renk;
                ctx.fill();

                if (p.supheli) {
                    ctx.strokeStyle = '#000';
                    ctx.lineWidth = 1;
                    ctx.stroke();
                }
            }
        });
    });

    // Başlangıç ve Bitiş Tarih Etiketleri (TSİ)
    ctx.fillStyle = '#94a3b8';
    ctx.font = '10px monospace';
    ctx.textAlign = 'left';
    ctx.fillText(formatZamanTr(new Date(minTime).toISOString()) + ' TSİ', paddingLeft, h - 5);
    ctx.textAlign = 'right';
    ctx.fillText(formatZamanTr(new Date(maxTime).toISOString()) + ' TSİ', w - paddingRight, h - 5);

    // Sağ Üst Lejant
    let legendX = w - paddingRight;
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'right';

    for (let i = seriesList.length - 1; i >= 0; i--) {
        const s = seriesList[i];
        const lastVal = s.parsed.length > 0 ? s.parsed[s.parsed.length - 1].val.toFixed(1) : '--';
        const label = `${s.ad}: ${lastVal} ${s.unit}`;

        ctx.fillStyle = s.renk;
        ctx.beginPath();
        ctx.arc(legendX - 4, paddingTop - 12, 3.5, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = '#cbd5e1';
        ctx.fillText(label, legendX - 12, paddingTop - 9);

        const textMetrics = ctx.measureText ? ctx.measureText(label).width : 60;
        legendX -= (textMetrics + 24);
    }

    // Hover Crosshair
    // Hover Crosshair
    if (crosshairX !== null && crosshairX >= paddingLeft && crosshairX <= paddingLeft + plotW) {
        ctx.strokeStyle = 'rgba(56, 189, 248, 0.7)';
        ctx.lineWidth = 1;
        if (ctx.setLineDash) ctx.setLineDash([4, 3]);
        ctx.beginPath();
        ctx.moveTo(crosshairX, paddingTop);
        ctx.lineTo(crosshairX, paddingTop + plotH);
        ctx.stroke();
        if (ctx.setLineDash) ctx.setLineDash([]);

        // Çizgilerin kesim noktalarında parlak halka göster
        seriesList.forEach(s => {
            const hit = s.parsed.find(p => Math.abs(p.screenX - crosshairX) < 3) || s.parsed[0];
            if (hit && hit.screenY !== undefined) {
                ctx.beginPath();
                ctx.arc(crosshairX, hit.screenY, 4.5, 0, Math.PI * 2);
                ctx.fillStyle = s.renk;
                ctx.fill();
                ctx.strokeStyle = '#ffffff';
                ctx.lineWidth = 1.5;
                ctx.stroke();
            }
        });
    }

    if (ctx.restore) ctx.restore();

    state.aktifSeriCizimVerisi = {
        points: seriesList[0].parsed,
        seriesList,
        plotW,
        plotH,
        paddingLeft,
        paddingRight,
        paddingTop,
        unit,
        isMulti,
        seriesData: isMulti ? { l1: seriesList[0], l2: seriesList[1], l3: seriesList[2] } : null,
        lastCrosshairX: crosshairX
    };
}

// Geriye dönük test uyumluluğu için
function zamanSerisiCiz(noktalar, metrik, aralik) {
    return zamanSerisiCizGenel(noktalar, metrik, aralik, null);
}

function zamanSerisiTekrarCiz(crosshairX) {
    if (!state.aktifSeriCizimVerisi) return;
    const { isMulti } = state.aktifSeriCizimVerisi;
    const metrik = isMulti ? 'akim_hepsi' : state.seriKanal;
    const aralik = state.seriAralik;
    zamanSerisiCizGenel(
        state.seriNoktalar || [],
        metrik,
        aralik,
        state.seriCokluVeri,
        crosshairX
    );
}

function setupTimeseriesHover() {
    const canvas = document.getElementById('timeseriesCanvas');
    const tooltip = document.getElementById('timeseries-tooltip');
    if (!canvas || !tooltip) return;

    canvas.addEventListener('mousemove', (e) => {
        if (!state.aktifSeriCizimVerisi || !state.aktifSeriCizimVerisi.points || state.aktifSeriCizimVerisi.points.length === 0) {
            tooltip.style.display = 'none';
            return;
        }

        const rect = canvas.getBoundingClientRect ? canvas.getBoundingClientRect() : { left: 0, top: 0, width: 760, height: 210 };
        const mouseX = (e.clientX !== undefined ? e.clientX - rect.left : e.offsetX) || 0;
        const mouseY = (e.clientY !== undefined ? e.clientY - rect.top : e.offsetY) || 0;

        const { points, plotW, paddingLeft, paddingRight, paddingTop, plotH, unit, isMulti, seriesData } = state.aktifSeriCizimVerisi;

        if (mouseX < paddingLeft || mouseX > paddingLeft + plotW) {
            tooltip.style.display = 'none';
            if (state.aktifSeriCizimVerisi.lastCrosshairX !== null) {
                zamanSerisiTekrarCiz(null);
            }
            return;
        }

        let closestPt = points[0];
        let minDiff = Math.abs((points[0].screenX || paddingLeft) - mouseX);
        for (let i = 1; i < points.length; i++) {
            const diff = Math.abs((points[i].screenX || paddingLeft) - mouseX);
            if (diff < minDiff) {
                minDiff = diff;
                closestPt = points[i];
            }
        }

        if (!closestPt) {
            tooltip.style.display = 'none';
            if (state.aktifSeriCizimVerisi.lastCrosshairX !== null) {
                zamanSerisiTekrarCiz(null);
            }
            return;
        }

        // Yalnızca farklı bir dikey çizgi konumuna gelindiğinde yeniden çiz
        if (state.aktifSeriCizimVerisi.lastCrosshairX !== closestPt.screenX) {
            zamanSerisiTekrarCiz(closestPt.screenX);
        }

        tooltip.innerHTML = '';
        const zDiv = document.createElement('div');
        zDiv.style.fontWeight = '600';
        zDiv.style.marginBottom = '3px';
        zDiv.style.color = 'var(--accent-cyan)';
        zDiv.textContent = `⏱️ ${formatZamanTr(closestPt.zaman)} TSİ`;
        tooltip.appendChild(zDiv);

        if (isMulti && seriesData) {
            ['l1', 'l2', 'l3'].forEach(k => {
                const s = seriesData[k];
                if (s && s.parsed) {
                    const match = s.parsed.find(p => p.zaman === closestPt.zaman) || s.parsed[closestPt.idx];
                    if (match && match.val !== null) {
                        const row = document.createElement('div');
                        row.style.color = s.renk;
                        row.style.fontWeight = '500';
                        row.textContent = `${s.ad}: ${match.val.toFixed(2)} ${unit}`;
                        tooltip.appendChild(row);
                    }
                }
            });
        } else {
            const vDiv = document.createElement('div');
            vDiv.style.fontWeight = '500';
            if (closestPt.aralik && closestPt.asgari !== null && closestPt.azami !== null) {
                vDiv.textContent = `Ort: ${closestPt.val.toFixed(2)} ${unit} (Min: ${closestPt.asgari.toFixed(1)}, Maks: ${closestPt.azami.toFixed(1)})`;
            } else {
                vDiv.textContent = `Değer: ${closestPt.val.toFixed(2)} ${unit}`;
            }
            tooltip.appendChild(vDiv);

            if (closestPt.supheli) {
                const sDiv = document.createElement('div');
                sDiv.style.color = '#f59e0b';
                sDiv.style.marginTop = '2px';
                sDiv.textContent = `⚠️ Şüpheli Ölçüm (Kalite: ${closestPt.kalite || 'supheli'})`;
                tooltip.appendChild(sDiv);
            }
        }

        tooltip.style.display = 'block';
        const tipWidth = tooltip.offsetWidth || 190;
        const tipHeight = tooltip.offsetHeight || 50;

        let leftPos = closestPt.screenX + 15;
        if (leftPos + tipWidth > rect.width) {
            leftPos = closestPt.screenX - tipWidth - 15;
        }
        let topPos = mouseY < 45 ? (mouseY + 16) : (mouseY - 20);
        topPos = Math.max(8, Math.min(topPos, rect.height - tipHeight - 8));

        tooltip.style.left = `${Math.max(5, leftPos)}px`;
        tooltip.style.top = `${topPos}px`;
    });

    canvas.addEventListener('mouseleave', () => {
        tooltip.style.display = 'none';
        if (state.aktifSeriCizimVerisi && state.aktifSeriCizimVerisi.lastCrosshairX !== null) {
            zamanSerisiTekrarCiz(null);
        }
    });
}

// --------------------------------------------------------------------------
// UI-07: OPERASYON GÜNLÜĞÜ VE KÜRESEL GEÇİŞ AKIŞI
// --------------------------------------------------------------------------
async function operasyonGunluguYukle() {
    const auditContainer = document.getElementById('audit-container');
    if (!auditContainer) return;

    try {
        // UI-07 Kural 1: İlk yüklemede cursor ile son sayfaya kadar taranıp en büyük son 30 id tutulur
        let tumGecisler = [];
        let sonra = state.sonGecisId;
        let devam = true;
        const limit = 50;

        // Eğer ilk kez çağrılıyorsa tüm akışı cursor'la sonuna kadar tara
        if (state.sonGecisId === null) {
            let cursor = null;
            while (devam) {
                let url = `/gecisler?limit=${limit}`;
                if (cursor !== null) {
                    url += `&sonra=${cursor}`;
                }
                const res = await apiFetch(url);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                const veriler = data.veriler || [];
                tumGecisler.push(...veriler);

                if (data.sonraki !== null && data.sonraki !== undefined && veriler.length >= limit && data.sonraki !== cursor) {
                    cursor = data.sonraki;
                } else {
                    devam = false;
                }
            }
            // En büyük 30 id'yi al
            state.gecisler = tumGecisler.slice(-30);
            if (tumGecisler.length > 0) {
                state.sonGecisId = tumGecisler[tumGecisler.length - 1].id;
            }
        } else {
            // UI-07: Sonraki yenilemelerde 50'den fazla yeni kayıt gelirse tüm sayfaları cursor ile tara
            let cursor = state.sonGecisId;
            let tumYeniVeriler = [];
            let devamYeni = true;
            while (devamYeni) {
                const res = await apiFetch(`/gecisler?sonra=${cursor}&limit=${limit}`);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                const veriler = data.veriler || [];
                tumYeniVeriler.push(...veriler);

                if (data.sonraki !== null && data.sonraki !== undefined && veriler.length >= limit && data.sonraki !== cursor) {
                    cursor = data.sonraki;
                } else {
                    devamYeni = false;
                }
            }
            if (tumYeniVeriler.length > 0) {
                state.gecisler = [...state.gecisler, ...tumYeniVeriler].slice(-30);
                state.sonGecisId = tumYeniVeriler[tumYeniVeriler.length - 1].id;
            }
        }

        state.gunlukHata = false;
        renderAuditLog();
    } catch (err) {
        console.warn("Operasyon günlüğü hatası:", err);
        state.gunlukHata = true;
        renderAuditLog();
    }
}

function renderAuditLog() {
    const container = document.getElementById('audit-container');
    if (!container) return;

    container.innerHTML = '';

    if (state.gunlukHata) {
        const errNotice = document.createElement('div');
        errNotice.style.padding = '8px 12px';
        errNotice.style.color = '#fca5a5';
        errNotice.style.fontSize = '0.75rem';
        errNotice.style.background = 'rgba(239, 68, 68, 0.15)';
        errNotice.style.borderRadius = 'var(--radius-sm)';
        errNotice.style.marginBottom = '8px';
        errNotice.textContent = '⚠️ Günlük güncellenemedi (Son başarılı liste korunuyor).';
        container.appendChild(errNotice);
    }

    if (state.gecisler.length === 0) {
        const emptyEl = document.createElement('div');
        emptyEl.className = 'empty-audit';
        emptyEl.innerHTML = '<p>Henüz operatör eylemi veya geçiş kaydedilmedi.</p>';
        container.appendChild(emptyEl);
        return;
    }

    // En günceli en üstte göstermek için ters çevir
    const gosterilecekler = state.gecisler.slice().reverse();

    gosterilecekler.forEach(g => {
        const entry = document.createElement('div');
        entry.className = 'audit-entry';

        const timeEl = document.createElement('div');
        timeEl.className = 'audit-time';
        timeEl.textContent = `${formatZamanTr(g.zaman)} TSİ (ID: ${g.id})`;

        const textEl = document.createElement('div');
        textEl.className = 'audit-text';

        // UI-07 Kural 2: alan=durum ve alan=seviye ayrı anlamla gösterilir; onaylandi asla kapandi yazılmaz!
        if (g.alan === 'durum') {
            if (g.yeni === 'onaylandi') {
                textEl.innerHTML = `✅ Operatör Onayı: <b>${escapeHtml(g.anomali_id)}</b> onaylandı (Operatör: ${escapeHtml(g.aktor || 'Bilinmiyor')})`;
            } else if (g.yeni === 'kapandi') {
                textEl.innerHTML = `🛡️ Anomali Kapatıldı: <b>${escapeHtml(g.anomali_id)}</b>`;
            } else if (g.yeni === 'acik') {
                textEl.innerHTML = `🚨 Yeni Anomali: <b>${escapeHtml(g.anomali_id)}</b> tespit edildi`;
            } else {
                textEl.innerHTML = `Durum Geçişi: <b>${escapeHtml(g.anomali_id)}</b> → ${escapeHtml(g.yeni)}`;
            }
        } else if (g.alan === 'seviye') {
            textEl.innerHTML = `📶 Seviye Değişimi: <b>${escapeHtml(g.anomali_id)}</b> (${escapeHtml(g.onceki || 'normal')} → ${escapeHtml(g.yeni)})`;
        } else {
            textEl.textContent = `${g.anomali_id}: ${g.alan} → ${g.yeni}`;
        }

        entry.appendChild(timeEl);
        entry.appendChild(textEl);
        container.appendChild(entry);
    });
}

// --------------------------------------------------------------------------
// SİSTEM DURUMU, SAAT VE PERİYODİK TARAMA
// --------------------------------------------------------------------------
function setOnlineStatus(online) {
    state.isOnline = online;
    const led = document.getElementById('api-status-led');
    const label = document.getElementById('api-status-text');

    if (led && label) {
        if (online) {
            led.className = 'status-indicator online';
            label.textContent = 'API ÇEVRİMİÇİ';
        } else {
            led.className = 'status-indicator offline';
            label.textContent = 'BAĞLANTI KESİLDİ';
        }
    }
}

function updateClock() {
    const clock = document.getElementById('clock-display');
    if (clock) {
        const now = new Date();
        clock.textContent = now.toLocaleTimeString('tr-TR', { timeZone: 'Europe/Istanbul' }) + ' TSİ';
    }
}

function startPolling() {
    if (state.pollTimer) clearInterval(state.pollTimer);
    state.pollTimer = setInterval(() => {
        // UI-07: Sayfa API kesintisinde açıldıysa ağaç boş kalır; operatörün
        // "Yenile"ye basması beklenmez, bağlantı gelince kendiliğinden dolar.
        if (!state.hiyerarsiYuklendi) {
            hiyerarsiyiYukle();
        }
        if (!state.kanitKareModu && !state.seciliAnomaliId && state.aktifModulId) {
            modulDetayYukle(state.aktifModulId, true);
        }
        modulDurumlariniGuncelle();
        alarmlariYukle();
        operasyonGunluguYukle();
    }, state.pollIntervalMs);
}

// Tarayıcı Olay Bağlantıları
if (typeof window !== 'undefined' && typeof document !== 'undefined') {
    window.addEventListener('DOMContentLoaded', () => {
        updateClock();
        setInterval(updateClock, 1000);

        setupCanvasHover();
        setupTimeseriesHover();

        const btnRefresh = document.getElementById('btn-manual-refresh');
        if (btnRefresh) {
            btnRefresh.addEventListener('click', () => {
                hiyerarsiyiYukle();
                if (state.aktifModulId) modulDetayYukle(state.aktifModulId);
                alarmlariYukle();
                operasyonGunluguYukle();
                zamanSerisiYukle();
            });
        }

        const btnLiveThermal = document.getElementById('btn-live-thermal');
        if (btnLiveThermal) {
            btnLiveThermal.addEventListener('click', () => {
                canliGoruntuyeDon();
            });
        }

        const btnAudio = document.getElementById('btn-audio-toggle');
        if (btnAudio) {
            btnAudio.addEventListener('click', () => {
                state.audioEnabled = !state.audioEnabled;
                const icon = document.getElementById('audio-icon');
                const text = document.getElementById('audio-text');
                if (icon) icon.textContent = state.audioEnabled ? '🔔' : '🔕';
                if (text) text.textContent = state.audioEnabled ? 'Ses Açık' : 'Sessiz';
                if (state.audioEnabled) sfx.playAlert();
            });
        }

        const selectPoll = document.getElementById('poll-interval');
        if (selectPoll) {
            selectPoll.addEventListener('change', (e) => {
                state.pollIntervalMs = parseInt(e.target.value, 10);
                startPolling();
            });
        }

        const btnSmooth = document.getElementById('btn-toggle-smooth');
        if (btnSmooth) {
            btnSmooth.addEventListener('click', () => {
                state.smoothMode = !state.smoothMode;
                btnSmooth.textContent = `Pürüzsüzleştirme: ${state.smoothMode ? 'Açık' : 'Kapalı'}`;
                termalKareCiz();
            });
        }

        const btnGrid = document.getElementById('btn-toggle-grid');
        if (btnGrid) {
            btnGrid.addEventListener('click', () => {
                state.gridMode = !state.gridMode;
                btnGrid.textContent = `Izgara: ${state.gridMode ? 'Açık' : 'Kapalı'}`;
                termalKareCiz();
            });
        }

        // Zaman Serisi Kontrolleri
        const metricSelect = document.getElementById('timeseries-metric');
        if (metricSelect) {
            metricSelect.addEventListener('change', (e) => {
                state.seriKanal = e.target.value;
                zamanSerisiYukle();
            });
        }

        const rangeSelect = document.getElementById('timeseries-range');
        if (rangeSelect) {
            rangeSelect.addEventListener('change', (e) => {
                state.seriZamanAralik = e.target.value;
                zamanSerisiYukle();
            });
        }

        const intervalSelect = document.getElementById('timeseries-interval');
        if (intervalSelect) {
            intervalSelect.addEventListener('change', (e) => {
                state.seriAralik = e.target.value;
                zamanSerisiYukle();
            });
        }

        const btnRefreshSeries = document.getElementById('btn-refresh-series');
        if (btnRefreshSeries) {
            btnRefreshSeries.addEventListener('click', () => {
                zamanSerisiYukle();
            });
        }

        // Sekmeler
        const tabActive = document.getElementById('tab-btn-active');
        const tabHistory = document.getElementById('tab-btn-history');
        const alarmsBox = document.getElementById('alarms-container');
        const auditBox = document.getElementById('audit-container');

        if (tabActive && tabHistory && alarmsBox && auditBox) {
            tabActive.addEventListener('click', () => {
                tabActive.classList.add('active');
                tabHistory.classList.remove('active');
                alarmsBox.style.display = 'flex';
                auditBox.style.display = 'none';
            });

            tabHistory.addEventListener('click', () => {
                tabHistory.classList.add('active');
                tabActive.classList.remove('active');
                alarmsBox.style.display = 'none';
                auditBox.style.display = 'flex';
                operasyonGunluguYukle();
            });
        }

        // İlk yüklemeler
        hiyerarsiyiYukle();
        alarmlariYukle();
        operasyonGunluguYukle();
        startPolling();
    });
}

// Test ve dış ortam erişimi için globalThis ve module.exports desteği
if (typeof globalThis !== 'undefined') {
    globalThis.GridUpApp = {
        state,
        escapeHtml,
        formatZamanTr,
        seviyeNormalize,
        enYuksekSeviye,
        modulSeviyesiniGetir,
        DESTEKLENEN_BIRIMLER,
        SENTETIK_GORSEL_UYARISI,
        birimGecerliMi,
        tamKareyiDogrula,
        bolgelerdenTahminiMatrisUret,
        sicaklikToRenk,
        resetModulEkranGorunumu,
        modulSec,
        modulDetayYukle,
        canliTermalYukle,
        termalKareCiz,
        canliGoruntuyeDon,
        anomaliSec,
        alarmOnayla,
        getMetrikAyar,
        getZamanAraligiBas,
        zamanSerisiYukle,
        zamanSerisiCiz,
        zamanSerisiCizGenel,
        setupTimeseriesHover,
        hiyerarsiyiYukle,
        startPolling,
        modulCihazDurumunuAğactaGuncelle,
        modulDurumlariniGuncelle,
        alarmlariYukle,
        sayfaliAnomalileriGetir,
        operasyonGunluguYukle,
        renderAuditLog,
        olcumKartiniGuncelle,
        modulRozetiniGuncelle,
        setOnlineStatus,
        apiFetch
    };
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = (typeof globalThis !== 'undefined' && globalThis.GridUpApp) ? globalThis.GridUpApp : {};
}
