/**
 * Grid Up - İZ C: Operasyon Yüzü & Monitoring Uygulaması
 * Sözleşme ⑤ ve IZ_C_ARAYUZ_GOREV_TANIMI.md kabul kriterlerine tam uyumlu sürüm.
 * UI-01 - UI-08 gereksinimlerini eksiksiz karşılar.
 */

// API Base URL tespiti:
const API_HOST = (typeof window !== 'undefined' && window.location && window.location.hostname) || "localhost";
const API_BASE = (typeof window !== 'undefined' && window.GRIDUP_API_URL)
    || (typeof window !== 'undefined' && window.location && window.location.protocol === "file:"
        ? "http://localhost:8080"
        : (typeof window !== 'undefined' && window.location && window.location.port === "8080"
            ? ""
            : (typeof window !== 'undefined' && window.location && (window.location.port === "80" || !window.location.port)
                ? "/api"
                : `http://${API_HOST}:8080`)));

// Güvenli API Çağrısı (UI-02: 4xx/5xx durumunda sessizce 8080'e fallback yapmaz, POST'u tekrarlamaz)
async function apiFetch(path, options = {}) {
    const cleanPath = path.startsWith('/') ? path : `/${path}`;
    const primaryUrl = `${API_BASE}${cleanPath}`;
    return await fetch(primaryUrl, options);
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
    termalMatris: null,
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
    seriNoktalar: [],
    seriHataMesaji: null
};

// Asenkron Yarış Durumu (Race Condition) Sayaçları (UI-02, UI-06)
let detailRequestToken = 0;
let thermalRequestToken = 0;
let seriesRequestToken = 0;

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
    const apiSev = state.apiModulSeviyeleri[modulId];
    const alarmSev = state.alarmModulSeviyeleri[modulId];

    // Eğer seviye değeri tanınmıyorsa "bilinmiyor" döner
    if (apiSev === null && alarmSev === null) {
        return 'bilinmiyor';
    }
    return enYuksekSeviye(apiSev, alarmSev);
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
                    durumHaritasi[m.modul_id] = {
                        durum: m.durum || 'bilinmiyor',
                        son_gorulme: m.son_gorulme,
                        seviye: m.seviye
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

async function hiyerarsiyiYukle() {
    const container = document.getElementById('hierarchy-container');
    const countTag = document.getElementById('hierarchy-count');
    if (!container) return;

    try {
        // Önce modüllerin yetkili aktif/sessiz/pasif durumlarını sayfalı olarak al
        const modulDurumlari = await tumModulDurumlariniCek();
        state.modulDurumlari = modulDurumlari;

        const res = await apiFetch('/sahalar');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setOnlineStatus(true);

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
                    panoHeader.style.cursor = 'pointer';
                    panoHeader.title = 'İlk modülü seç';
                    panoHeader.addEventListener('click', () => {
                        const ilk = moduller[0];
                        modulSec(ilk.modul_id, `${panoBaslik} - ${ilk.modul_id}`);
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
                        subSpan.className = `modul-sub-text ${cihazDurumuClass}`;
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

        // Seçili modül listede yoksa ilk geçerli modülü otomatik seç
        if (tumModuller.length > 0 && (!state.aktifModulId || !tumModuller.includes(state.aktifModulId))) {
            _modulSecProgramatik(tumModuller[0], tumModuller[0]);
        }
    } catch (err) {
        console.warn("Hiyerarşi yükleme hatası:", err);
        // UI-02: Tek bir servisin hatası genel online durumunu ezmemeli, ağaç içine hata basılır
        if (container.children.length === 0) {
            container.innerHTML = `
                <div class="empty-state" style="padding: 1.5rem; text-align: center; color: #fca5a5;">
                    <p>⚠️ Hiyerarşi verisi alınamadı.</p>
                </div>
            `;
        }
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

    modulDetayYukle(modulId);
    zamanSerisiYukle();
}

// UI-02: Modül seçildiğinde alanları anında temizleyen yardımcı fonksiyon
function resetModulEkranGorunumu(modulId, modulIsmi) {
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

    // 6'lı kartları "--" durumuna al
    const kartDegerleri = ['val-temp', 'val-hum', 'val-tmax', 'val-l1', 'val-l2', 'val-l3', 'val-notr', 'val-arc'];
    kartDegerleri.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = '--';
    });

    const diffEl = document.getElementById('current-diff');
    if (diffEl) {
        diffEl.textContent = 'Faz Dengesizliği: Hesaplanamadı';
        diffEl.style.color = 'var(--text-muted)';
    }

    // Varsa önceki kalite uyarılarını temizle
    document.querySelectorAll('.card-quality-warning, .card-quality-bad').forEach(e => e.remove());

    // Termal reticle gizle
    const reticle = document.getElementById('hotspot-reticle');
    if (reticle) reticle.style.display = 'none';

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
}

async function modulDetayYukle(modulId) {
    if (!modulId) return;

    // UI-02: Asenkron yarış durumu koruması için istek jetonu
    const currentToken = ++detailRequestToken;

    // Önceki modülün verilerini bir an bile göstermemek için anında sıfırla
    resetModulEkranGorunumu(modulId, state.aktifModulIsmi);

    try {
        const res = await apiFetch(`/moduller/${encodeURIComponent(modulId)}`);

        // Geç gelen yanıt kontrolü
        if (currentToken !== detailRequestToken) return;

        if (!res.ok) {
            throw new Error(`HTTP ${res.status}`);
        }

        const data = await res.json();
        if (currentToken !== detailRequestToken) return;

        // 1. Cihaz Durumu ve Zaman
        const modulDurumKaydi = state.modulDurumlari[modulId] || {};
        let cihazDurumu = modulDurumKaydi.durum;
        if (!cihazDurumu) {
            if (data.aktif === false) cihazDurumu = 'pasif';
            else cihazDurumu = 'bilinmiyor';
        }

        const deviceBadge = document.getElementById('active-module-device-badge');
        if (deviceBadge) {
            deviceBadge.className = `status-badge badge-device-${cihazDurumu}`;
            deviceBadge.textContent = `CİHAZ: ${cihazDurumu.toUpperCase()}`;
        }

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

        // 2. Canlı Ölçümler (UI-03 Kuralları)
        const sonOlcumler = Array.isArray(data.son_olcumler) ? data.son_olcumler : [];
        const olcumMap = {};
        sonOlcumler.forEach(o => {
            if (o && o.olcum_tipi) {
                olcumMap[o.olcum_tipi] = o;
            }
        });

        // Metrik kartlarını güvenli doldur
        olcumKartiniGuncelle('val-temp', 'card-temp', 'temp-status', olcumMap.ortam_sicaklik, 'Sensör: SHT31', 1);
        olcumKartiniGuncelle('val-hum', 'card-hum', 'hum-status', olcumMap.nem, 'Optimum: %40-60', 1);
        olcumKartiniGuncelle('val-l1', 'card-current', null, olcumMap.akim_l1, '', 1);
        olcumKartiniGuncelle('val-l2', 'card-current', null, olcumMap.akim_l2, '', 1);
        olcumKartiniGuncelle('val-l3', 'card-current', null, olcumMap.akim_l3, '', 1);
        olcumKartiniGuncelle('val-notr', 'card-notr', 'notr-status', olcumMap.akim_notr, 'Dönüş Hattı Akımı', 1);
        olcumKartiniGuncelle('val-arc', 'card-arc', 'arc-status', olcumMap.ark_olay, 'TVOC-2 Optik Koruma', 0);

        // Faz Dengesizliği: Yalnızca L1, L2, L3'ün üçü de varsa, sayısal ve kalite=iyi ise hesaplanır
        const diffEl = document.getElementById('current-diff');
        const oL1 = olcumMap.akim_l1;
        const oL2 = olcumMap.akim_l2;
        const oL3 = olcumMap.akim_l3;

        if (oL1 && oL2 && oL3 &&
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
        if (currentToken !== detailRequestToken) return;
        console.warn(`Modül detayı yüklenemedi (${modulId}):`, err);

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
    }
}

// UI-03: Ölçüm kartı güncelleme yardımcısı
function olcumKartiniGuncelle(valId, cardId, statusSubId, olcum, defaultSub, ondalik) {
    const valEl = document.getElementById(valId);
    const cardEl = cardId ? document.getElementById(cardId) : null;
    const subEl = statusSubId ? document.getElementById(statusSubId) : null;

    // Önceki kalite uyarılarını temizle
    if (cardEl) {
        const eskiUyari = cardEl.querySelector('.card-quality-warning, .card-quality-bad');
        if (eskiUyari) eskiUyari.remove();
    }

    if (!olcum || olcum.deger === null || olcum.deger === undefined || olcum.kalite === 'yok') {
        if (valEl) valEl.textContent = '--';
        if (subEl) subEl.textContent = defaultSub || 'Veri yok';
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

    if (subEl && olcum.zaman) {
        subEl.textContent = `${defaultSub ? defaultSub + ' | ' : ''}${formatZamanTr(olcum.zaman)} TSİ`;
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
                state.termalMatris = bolgelerdenTahminiMatrisUret(ozet, olcumMap);
                if (sourceBadge) {
                    sourceBadge.className = 'thermal-resolution source-ozet';
                    sourceBadge.textContent = 'Özetten Üretilmiş Tahmini Görsel — Ölçülmüş Piksel Değildir';
                }
                termalKareCiz();
            }

            if (bannerTitle) bannerTitle.textContent = 'Termal Özet Analizi:';
            if (bannerIcon) bannerIcon.textContent = '🔥';
            if (bannerDesc) {
                bannerDesc.textContent = `Sıcak nokta: ${ozet.maks !== undefined ? Number(ozet.maks).toFixed(1) + ' °C' : '--'} (Zaman: ${formatZamanTr(ozet.zaman)} TSİ)`;
            }
        } else {
            // Özet de yoksa
            if (sourceBadge) {
                sourceBadge.className = 'thermal-resolution source-hata';
                sourceBadge.textContent = 'Termal Veri Yok';
            }
            state.termalMatris = null;
            state.termalOzet = null;
            if (valTmax) valTmax.textContent = '--';
            if (hotspotEl) hotspotEl.textContent = 'Konum: --';
            if (bannerDesc) bannerDesc.textContent = 'Bu modül için termal ölçüm kaydı bulunmuyor.';
            termalKareCiz();
        }
    } catch (err) {
        if (currentToken !== thermalRequestToken) return;
        console.warn("Termal veri hatası:", err);
    }
}

// UI-04: Kanıt Karesi İnceleme
async function anomaliSec(anomaliId) {
    const anomali = state.cozulmemisAnomaliler.find(a => a.id === anomaliId);
    if (!anomali) return;

    state.seciliAnomaliId = anomaliId;
    state.kanitAnomali = anomali;
    state.kanitKareModu = true;

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
            if (res.ok) {
                const kareData = await res.json();
                if (tamKareyiDogrula(kareData, anomali.modul_id, null)) {
                    state.termalMatris = kareData.piksel_verisi;

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

    // Kare yoksa veya doğrulanamadıysa eski kare kanıt diye sunulmaz!
    state.termalMatris = null;
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
    state.kanitKareModu = false;
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
        const rect = canvas.getBoundingClientRect();
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
async function sayfaliAnomalileriGetir(durumFiltresi) {
    const sonuclar = [];
    let sonra = null;
    let devam = true;
    const limit = 50;

    while (devam) {
        try {
            let url = `/anomaliler?durum=${durumFiltresi}&limit=${limit}`;
            if (sonra !== null) {
                url += `&sonra=${sonra}`;
            }
            const res = await apiFetch(url);
            if (!res.ok) break;
            const data = await res.json();
            const veriler = data.veriler || [];
            sonuclar.push(...veriler);

            if (data.sonraki !== null && data.sonraki !== undefined && veriler.length > 0) {
                sonra = data.sonraki;
            } else {
                devam = false;
            }
        } catch (err) {
            console.warn(`Anomali (${durumFiltresi}) getirme hatası:`, err);
            break;
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
// UI-06: ZAMAN SERİSİ GRAFİĞİ (ORTAM, TERMAL MAKS, L1, L2, L3)
// --------------------------------------------------------------------------
async function zamanSerisiYukle() {
    const modulId = state.aktifModulId;
    if (!modulId) return;

    const currentToken = ++seriesRequestToken;
    const metricSelect = document.getElementById('timeseries-metric');
    const intervalSelect = document.getElementById('timeseries-interval');
    const msgEl = document.getElementById('timeseries-message');
    const infoEl = document.getElementById('timeseries-info');

    const metrik = (metricSelect && metricSelect.value) || state.seriKanal;
    const aralik = (intervalSelect && intervalSelect.value) || state.seriAralik;

    if (msgEl) {
        msgEl.style.display = 'flex';
        msgEl.className = 'timeseries-message';
        msgEl.textContent = 'Zaman serisi yükleniyor...';
    }

    try {
        let url = `/moduller/${encodeURIComponent(modulId)}/seri?tip=${encodeURIComponent(metrik)}`;
        if (aralik) {
            url += `&aralik=${encodeURIComponent(aralik)}`;
        }

        const res = await apiFetch(url);
        if (currentToken !== seriesRequestToken) return;

        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            if (currentToken !== seriesRequestToken) return;

            if (errData && errData.hata && errData.hata.kod === 'cok_fazla_nokta') {
                if (msgEl) {
                    msgEl.style.display = 'flex';
                    msgEl.className = 'timeseries-message error';
                    msgEl.textContent = 'Çok fazla nokta: Lütfen daha geniş bir kova aralığı seçin.';
                }
            } else {
                if (msgEl) {
                    msgEl.style.display = 'flex';
                    msgEl.className = 'timeseries-message error';
                    msgEl.textContent = 'Grafik yüklenemedi.';
                }
            }
            state.seriNoktalar = [];
            zamanSerisiCiz([], metrik, aralik);
            return;
        }

        const data = await res.json();
        if (currentToken !== seriesRequestToken) return;

        const noktalar = Array.isArray(data.noktalar) ? data.noktalar : [];
        state.seriNoktalar = noktalar;

        if (noktalar.length === 0) {
            if (msgEl) {
                msgEl.style.display = 'flex';
                msgEl.className = 'timeseries-message';
                msgEl.textContent = 'Bu aralıkta ölçüm yok';
            }
            if (infoEl) infoEl.textContent = `${metrik} — Ölçüm bulunamadı`;
            zamanSerisiCiz([], metrik, aralik);
            return;
        }

        if (msgEl) msgEl.style.display = 'none';
        if (infoEl) {
            infoEl.textContent = `${metrik} — ${noktalar.length} nokta (${aralik ? 'Kova: ' + aralik : 'Ham'})`;
        }

        zamanSerisiCiz(noktalar, metrik, aralik);
    } catch (err) {
        if (currentToken !== seriesRequestToken) return;
        console.warn("Zaman serisi hatası:", err);
        if (msgEl) {
            msgEl.style.display = 'flex';
            msgEl.className = 'timeseries-message error';
            msgEl.textContent = 'Grafik yüklenemedi';
        }
        state.seriNoktalar = [];
        zamanSerisiCiz([], metrik, aralik);
    }
}

function zamanSerisiCiz(noktalar, metrik, aralik) {
    const canvas = document.getElementById('timeseriesCanvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;

    ctx.clearRect(0, 0, w, h);

    // Koyu SCADA arka plan
    ctx.fillStyle = '#070b14';
    ctx.fillRect(0, 0, w, h);

    if (!noktalar || noktalar.length === 0) return;

    const isCurrent = metrik.startsWith('akim_');
    const unit = isCurrent ? 'A' : '°C';

    const paddingLeft = 60;
    const paddingRight = 30;
    const paddingTop = 25;
    const paddingBottom = 30;
    const plotW = w - paddingLeft - paddingRight;
    const plotH = h - paddingTop - paddingBottom;

    // Değerleri çıkar
    const parsedPoints = noktalar.map((pt, idx) => {
        const val = aralik ? pt.ort : pt.deger;
        const num = (val !== null && val !== undefined) ? Number(val) : null;
        const isSupheli = aralik ? ((pt.supheli || 0) > 0) : (pt.kalite !== 'iyi');
        return {
            xIdx: idx,
            val: num,
            asgari: pt.asgari !== undefined ? Number(pt.asgari) : null,
            azami: pt.azami !== undefined ? Number(pt.azami) : null,
            zaman: pt.zaman,
            supheli: isSupheli
        };
    }).filter(p => p.val !== null && !isNaN(p.val));

    if (parsedPoints.length === 0) return;

    let minVal = Math.min(...parsedPoints.map(p => p.asgari !== null ? p.asgari : p.val));
    let maxVal = Math.max(...parsedPoints.map(p => p.azami !== null ? p.azami : p.val));
    if (minVal === maxVal) {
        minVal -= 1;
        maxVal += 1;
    }
    const valRange = maxVal - minVal;

    // Izgara ve Y ekseni etiketleri
    ctx.strokeStyle = '#17233d';
    ctx.lineWidth = 1;
    ctx.fillStyle = '#64748b';
    ctx.font = '10px monospace';
    ctx.textAlign = 'right';

    const yAdim = 4;
    for (let i = 0; i <= yAdim; i++) {
        const ratio = i / yAdim;
        const y = paddingTop + plotH * (1 - ratio);
        const labelVal = (minVal + valRange * ratio).toFixed(1);

        ctx.beginPath();
        ctx.moveTo(paddingLeft, y);
        ctx.lineTo(w - paddingRight, y);
        ctx.stroke();

        ctx.fillText(`${labelVal} ${unit}`, paddingLeft - 8, y + 3);
    }

    // X ekseni ve çizgi
    const xStep = parsedPoints.length > 1 ? plotW / (parsedPoints.length - 1) : plotW / 2;

    // Kovalanmış aralık min-max bandı
    if (aralik) {
        ctx.fillStyle = isCurrent ? 'rgba(59, 130, 246, 0.12)' : 'rgba(239, 68, 68, 0.12)';
        ctx.beginPath();
        parsedPoints.forEach((p, idx) => {
            const x = paddingLeft + idx * xStep;
            const yMax = paddingTop + plotH * (1 - (p.azami - minVal) / valRange);
            if (idx === 0) ctx.moveTo(x, yMax);
            else ctx.lineTo(x, yMax);
        });
        for (let idx = parsedPoints.length - 1; idx >= 0; idx--) {
            const p = parsedPoints[idx];
            const x = paddingLeft + idx * xStep;
            const yMin = paddingTop + plotH * (1 - (p.asgari - minVal) / valRange);
            ctx.lineTo(x, yMin);
        }
        ctx.closePath();
        ctx.fill();
    }

    // Ana Seri Çizgisi
    ctx.strokeStyle = isCurrent ? '#38bdf8' : '#ef4444';
    ctx.lineWidth = 2;
    ctx.beginPath();

    parsedPoints.forEach((p, idx) => {
        const x = paddingLeft + idx * xStep;
        const y = paddingTop + plotH * (1 - (p.val - minVal) / valRange);
        if (idx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Noktalar ve Şüpheli Vurguları
    parsedPoints.forEach((p, idx) => {
        const x = paddingLeft + idx * xStep;
        const y = paddingTop + plotH * (1 - (p.val - minVal) / valRange);

        ctx.beginPath();
        ctx.arc(x, y, p.supheli ? 4 : 2, 0, Math.PI * 2);
        ctx.fillStyle = p.supheli ? '#f59e0b' : (isCurrent ? '#38bdf8' : '#ef4444');
        ctx.fill();

        if (p.supheli) {
            ctx.strokeStyle = '#000';
            ctx.lineWidth = 1;
            ctx.stroke();
        }
    });

    // Zaman etiketleri (İlk ve Son)
    ctx.fillStyle = '#94a3b8';
    ctx.font = '10px monospace';
    ctx.textAlign = 'left';
    ctx.fillText(formatZamanTr(parsedPoints[0].zaman) + ' TSİ', paddingLeft, h - 10);
    ctx.textAlign = 'right';
    ctx.fillText(formatZamanTr(parsedPoints[parsedPoints.length - 1].zaman) + ' TSİ', w - paddingRight, h - 10);
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

                if (data.sonraki !== null && data.sonraki !== undefined && veriler.length > 0) {
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
            // Sonraki yenilemelerde yalnız yeni gelenleri al
            const res = await apiFetch(`/gecisler?sonra=${state.sonGecisId}&limit=${limit}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            const yeniVeriler = data.veriler || [];
            if (yeniVeriler.length > 0) {
                state.gecisler = [...state.gecisler, ...yeniVeriler].slice(-30);
                state.sonGecisId = yeniVeriler[yeniVeriler.length - 1].id;
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
        if (!state.kanitKareModu && !state.seciliAnomaliId && state.aktifModulId) {
            modulDetayYukle(state.aktifModulId);
        }
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
        tamKareyiDogrula,
        bolgelerdenTahminiMatrisUret,
        sicaklikToRenk,
        resetModulEkranGorunumu,
        modulSec,
        modulDetayYukle,
        canliTermalYukle,
        anomaliSec,
        alarmOnayla,
        zamanSerisiYukle,
        zamanSerisiCiz,
        hiyerarsiyiYukle,
        alarmlariYukle,
        operasyonGunluguYukle
    };
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = (typeof globalThis !== 'undefined' && globalThis.GridUpApp) ? globalThis.GridUpApp : {};
}
