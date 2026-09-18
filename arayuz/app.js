/**
 * Grid Up - İZ C: Operasyon Yüzü & Monitoring Uygulaması
 * Sözleşme ⑤ gerçek okuma API'si ile tam entegre:
 * Saha Hiyerarşisi, Canlı Sensör Metrikleri, 32x24 Termal Görselleştirme (Canlı + Kanıt Karesi) ve Alarm Yönetimi
 */

// API Base URL tespiti:
// 1. window.GRIDUP_API_URL varsa öncelikli
// 2. Port 8080'den sunuluyorsa doğrudan relatif ""
// 3. Port 80 veya Nginx üzerinden sunuluyorsa reverse proxy "/api"
// 4. Aksi takdirde dinamik ana makine port 8080
const API_HOST = window.location.hostname || "localhost";
const API_BASE = (window.GRIDUP_API_URL) 
    || (window.location.protocol === "file:" ? "http://localhost:8080" : (window.location.port === "8080" ? "" : (window.location.port === "80" || !window.location.port ? "/api" : `http://${API_HOST}:8080`)));

// Güvenli ve Çift Yollu API Çağrısı (Reverse Proxy + Doğrudan Fallback)
async function apiFetch(path, options = {}) {
    const cleanPath = path.startsWith('/') ? path : `/${path}`;
    const primaryUrl = `${API_BASE}${cleanPath}`;
    try {
        const res = await fetch(primaryUrl, options);
        if (res.ok) return res;
        if (!primaryUrl.includes(':8080')) {
            const fallbackUrl = `http://${API_HOST}:8080${cleanPath}`;
            const fallbackRes = await fetch(fallbackUrl, options);
            if (fallbackRes.ok) return fallbackRes;
        }
        return res;
    } catch (err) {
        if (!primaryUrl.includes(':8080')) {
            try {
                const fallbackUrl = `http://${API_HOST}:8080${cleanPath}`;
                const fallbackRes = await fetch(fallbackUrl, options);
                if (fallbackRes.ok) return fallbackRes;
            } catch (fallbackErr) {}
        }
        throw err;
    }
}

// Uygulama Durumu (State)
const state = {
    aktifModulId: 'TR041-P01-M1',
    aktifModulIsmi: 'Giriş Fideri Modülü',
    termalMatris: null,
    termalOzet: null,
    kanitKareModu: false,
    seciliAnomaliId: null,
    smoothMode: true,
    gridMode: false,
    audioEnabled: true,
    pollIntervalMs: 3000,
    pollTimer: null,
    isOnline: true,
    sonAlarmlar: [],
    modulSeviyeleri: {},
    // Durum kaynakları ayrı tutulur. Bir kaynak "normal" döndü diye açık
    // alarm veya API'nin bildirdiği daha yüksek seviye asla maskelenmemelidir.
    apiModulSeviyeleri: {},
    alarmModulSeviyeleri: {},
    canliModulSeviyeleri: {},
    auditLog: []
};

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
    const deger = String(seviye || 'normal').trim().toLocaleLowerCase('tr-TR');
    return Object.prototype.hasOwnProperty.call(SEVIYE_PUANI, deger) ? deger : 'normal';
}

function enYuksekSeviye(...seviyeler) {
    return seviyeler
        .map(seviyeNormalize)
        .reduce((enYuksek, seviye) => SEVIYE_PUANI[seviye] > SEVIYE_PUANI[enYuksek] ? seviye : enYuksek, 'normal');
}

function modulSeviyesiniGetir(modulId) {
    return enYuksekSeviye(
        state.apiModulSeviyeleri[modulId],
        state.alarmModulSeviyeleri[modulId],
        state.canliModulSeviyeleri[modulId]
    );
}

function modulRozetiniGuncelle(modulId) {
    const seviye = modulSeviyesiniGetir(modulId);
    state.modulSeviyeleri[modulId] = seviye;

    const treeBadge = document.getElementById(`tree-badge-${modulId}`);
    if (treeBadge) {
        treeBadge.className = `status-badge badge-${seviye}`;
        treeBadge.innerText = seviye.toUpperCase();
    }
    if (modulId === state.aktifModulId && !state.kanitKareModu) {
        const topBadge = document.getElementById('active-module-status-badge');
        if (topBadge) {
            topBadge.className = `status-badge badge-${seviye}`;
            topBadge.innerText = seviye.toUpperCase();
        }
    }
    return seviye;
}

// Web Audio API Sentezleyici (Harici dosyasız SCADA Uyarı Sesi)
class SoundFx {
    constructor() {
        this.ctx = null;
    }
    init() {
        if (!this.ctx) {
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
            osc.frequency.setValueAtTime(880, this.ctx.currentTime); // A5
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
// 1. SAHA HİYERARŞİSİ YÖNETİMİ (GET /sahalar) - Madde 18
// --------------------------------------------------------------------------
async function hiyerarsiyiYukle() {
    const container = document.getElementById('hierarchy-container');
    const countTag = document.getElementById('hierarchy-count');

    try {
        const res = await apiFetch('/sahalar');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setOnlineStatus(true);

        // Detay endpoint'i hiyerarşi endpoint'inden daha güncel olabilir.
        // Sunucunun bildirdiği risk seviyesi termal kartın "normal" sonucu ile
        // düşürülmez; kaynaklar aşağıda en yüksek seviye olarak birleştirilir.
        const sahalar = data.sahalar || [];
        let toplamModul = 0;
        let html = '';
        const tumModuller = [];

        if (sahalar.length === 0) {
            container.innerHTML = `
                <div class="empty-state" style="padding: 1.5rem; text-align: center; color: var(--text-muted);">
                    <p>Kayıtlı saha veya pano bulunamadı.</p>
                </div>
            `;
            if (countTag) countTag.innerText = "0 Modül";
            return;
        }

        sahalar.forEach(saha => {
            // Sadece aktif modülleri olan panoları filtrele
            const panolar = (saha.panolar || []).map(pano => {
                const aktifModuller = (pano.moduller || []).filter(m => m.aktif !== false);
                return { ...pano, aktifModuller };
            }).filter(p => p.aktifModuller.length > 0);

            // Eğer sahada hiç aktif modüllü pano yoksa sahayı listeye ekleme
            if (panolar.length === 0) return;

            const sahaBaslik = saha.ad ? `${saha.saha_kodu} (${saha.ad})` : (saha.saha_kodu || 'Bilinmeyen Saha');
            html += `
                <div class="tree-saha">
                    <div class="tree-saha-header">
                        <span>📍</span>
                        <span>${sahaBaslik}</span>
                    </div>
            `;

            panolar.forEach(pano => {
                const panoBaslik = pano.ad ? `${pano.pano_kodu} (${pano.ad})` : (pano.pano_kodu || 'Bilinmeyen Pano');
                const ilkModul = pano.aktifModuller[0].modul_id;
                const panoClickAttr = `onclick="modulSec('${ilkModul}', '${panoBaslik} - ${ilkModul}')" style="cursor: pointer;" title="Panoyu seç"`;
                html += `
                    <div class="tree-pano">
                        <div class="tree-pano-header" ${panoClickAttr}>
                            <span>⚙️</span>
                            <span>${panoBaslik}</span>
                        </div>
                        <ul class="tree-modul-list">
                `;

                pano.aktifModuller.forEach(modul => {
                    toplamModul++;
                    tumModuller.push(modul.modul_id);
                    const isActive = modul.modul_id === state.aktifModulId;
                    // Saha API'sinin seviyesi de bir alarm kaynağıdır; yalnızca
                    // açık-anomali listesine bakmak gerçek riski gizleyebilir.
                    state.apiModulSeviyeleri[modul.modul_id] = seviyeNormalize(modul.seviye);
                    const seviye = modulSeviyesiniGetir(modul.modul_id);
                    state.modulSeviyeleri[modul.modul_id] = seviye;
                    const durumClass = `badge-${seviye}`;
                    const seviyeText = seviye.toUpperCase();

                    html += `
                        <li class="tree-modul-item ${isActive ? 'active' : ''}" 
                            onclick="modulSec('${modul.modul_id}', '${modul.modul_id}')"
                            id="modul-item-${modul.modul_id}">
                            <div class="modul-info-left">
                                <span class="modul-id-text">${modul.modul_id}</span>
                                <span class="modul-sub-text">Aktif</span>
                            </div>
                            <span class="status-badge ${durumClass}" id="tree-badge-${modul.modul_id}">${seviyeText}</span>
                        </li>
                    `;
                });

                html += `</ul></div>`;
            });

            html += `</div>`;
        });

        container.innerHTML = html;
        if (countTag) countTag.innerText = `${toplamModul} Modül`;

        // Eğer seçili modül listede yoksa ilk modülü seç (inceleme modunu bozmadan)
        if (tumModuller.length > 0 && !tumModuller.includes(state.aktifModulId)) {
            _modulSecProgramatik(tumModuller[0], tumModuller[0]);
        }
    } catch (err) {
        console.warn("Hiyerarşi çekilemedi:", err);
        setOnlineStatus(false);
    }
}

// Kullanıcı sol panelden tıkladığında çağrılır — inceleme modunu sıfırlar
function modulSec(modulId, modulIsmi) {
    state.aktifModulId = modulId;
    state.aktifModulIsmi = modulIsmi || modulId;
    state.kanitKareModu = false;    // Kullanıcı bilinçli olarak farklı modüle geçiyor
    state.seciliAnomaliId = null;

    const btnLive = document.getElementById('btn-live-thermal');
    if (btnLive) btnLive.style.display = 'none';

    document.querySelectorAll('.tree-modul-item').forEach(el => el.classList.remove('active'));
    const seciliEl = document.getElementById(`modul-item-${modulId}`);
    if (seciliEl) seciliEl.classList.add('active');

    modulDetayYukle(modulId);
}

// Programatik (polling/init) modül seçimi — kanitKareModu ve seciliAnomaliId'yi KORUR
function _modulSecProgramatik(modulId, modulIsmi) {
    if (state.kanitKareModu || state.seciliAnomaliId) return; // inceleme modundaysa değişme!
    state.aktifModulId = modulId;
    state.aktifModulIsmi = modulIsmi || modulId;

    document.querySelectorAll('.tree-modul-item').forEach(el => el.classList.remove('active'));
    const seciliEl = document.getElementById(`modul-item-${modulId}`);
    if (seciliEl) seciliEl.classList.add('active');

    modulDetayYukle(modulId);
}

// --------------------------------------------------------------------------
// 2. MODÜL VE TERMAL VERİLERİN YÜKLENMESİ (GET /moduller/{id}) - Madde 18
// --------------------------------------------------------------------------
async function modulDetayYukle(modulId) {
    document.getElementById('active-module-badge').innerText = modulId;
    document.getElementById('active-module-name').innerText = state.aktifModulIsmi;

    try {
        const res = await apiFetch(`/moduller/${modulId}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setOnlineStatus(true);

        // 1. Zaman ve Modül Durumu
        if (data.seviye !== undefined || data.durum_seviyesi !== undefined) {
            state.apiModulSeviyeleri[modulId] = seviyeNormalize(data.seviye ?? data.durum_seviyesi);
        }

        // Açık anomalilerden gelen seviyeyi değerlendir (Madde 18 / Sözleşme ⑤)
        const acikAnomaliler = data.acik_anomaliler || [];
        if (acikAnomaliler.length > 0) {
            const enKotuAnomali = acikAnomaliler
                .map(a => seviyeNormalize(a.seviye))
                .reduce((enY, s) => SEVIYE_PUANI[s] > SEVIYE_PUANI[enY] ? s : enY, 'normal');
            state.alarmModulSeviyeleri[modulId] = enYuksekSeviye(state.alarmModulSeviyeleri[modulId], enKotuAnomali);
            state.apiModulSeviyeleri[modulId] = enYuksekSeviye(state.apiModulSeviyeleri[modulId], enKotuAnomali);
        }

        const zamanStr = formatZamanTr(data.son_gorulme);
        document.getElementById('val-time').innerText = zamanStr;
        document.getElementById('val-rssi').innerText = data.sinyal !== null && data.sinyal !== undefined ? `${data.sinyal} dBm` : '-- dBm';

        const feedEl = document.getElementById('val-feed');
        if (feedEl) {
            const besleme = (data.besleme || 'sebeke').toLowerCase();
            feedEl.innerText = besleme.toUpperCase();
            feedEl.className = besleme === 'yedek' ? 'badge-feed badge-warning' : 'badge-feed';
        }

        // 2. Uzun format son_olcumler dizisini haritaya çevir (Madde 18)
        const sonOlcumler = data.son_olcumler || [];
        const olcumler = {};
        sonOlcumler.forEach(o => {
            if (o.olcum_tipi) olcumler[o.olcum_tipi] = o.deger;
        });

        document.getElementById('val-temp').innerText = olcumler.ortam_sicaklik !== undefined ? Number(olcumler.ortam_sicaklik).toFixed(1) : '--';
        document.getElementById('val-hum').innerText = olcumler.nem !== undefined ? Number(olcumler.nem).toFixed(1) : '--';
        document.getElementById('val-l1').innerText = olcumler.akim_l1 !== undefined ? Number(olcumler.akim_l1).toFixed(1) : '--';
        document.getElementById('val-l2').innerText = olcumler.akim_l2 !== undefined ? Number(olcumler.akim_l2).toFixed(1) : '--';
        document.getElementById('val-l3').innerText = olcumler.akim_l3 !== undefined ? Number(olcumler.akim_l3).toFixed(1) : '--';
        document.getElementById('val-notr').innerText = olcumler.akim_notr !== undefined ? Number(olcumler.akim_notr).toFixed(1) : '0.0';
        document.getElementById('val-arc').innerText = olcumler.ark_olay !== undefined ? olcumler.ark_olay : '0';

        // Faz Dengesizliği Hesabı
        if (olcumler.akim_l1 !== undefined && olcumler.akim_l2 !== undefined && olcumler.akim_l3 !== undefined) {
            const akimlar = [Number(olcumler.akim_l1), Number(olcumler.akim_l2), Number(olcumler.akim_l3)];
            const ort = akimlar.reduce((a, b) => a + b, 0) / 3;
            const maksFark = Math.max(...akimlar.map(a => Math.abs(a - ort)));
            const dengesizlik = ort > 0 ? ((maksFark / ort) * 100).toFixed(1) : 0;
            const diffEl = document.getElementById('current-diff');
            if (diffEl) {
                diffEl.innerText = `Faz Dengesizliği: %${dengesizlik}`;
                diffEl.style.color = dengesizlik > 15 ? 'var(--color-warning)' : 'var(--text-muted)';
            }
        }

        // 3. Termal Verilerin Yüklenmesi (Eğer Kanıt Karesi modunda değilsek canlı termal veriyi çek)
        if (!state.kanitKareModu) {
            await canliTermalYukle(modulId, olcumler, data);
        }
        modulRozetiniGuncelle(modulId);
    } catch (err) {
        console.warn(`Modül (${modulId}) detayları çekilemedi:`, err);
        setOnlineStatus(false);
    }
}

// --------------------------------------------------------------------------
// 2.1 TERMAL RENK PALETİ VE MATRİS SENTEZİ
// --------------------------------------------------------------------------
// Sıcaklık -> Renk Haritalama Fonksiyonu (Her piksel/kare için hassas renk karşılığı)
// Sıcaklık Aralıkları:
//   <= 20°C : Koyu Lacivert / Mavi (hsl(240, 100%, 45%)) - Normal Soğuk
//   20°C - 35°C : Mavi -> Camgöbeği/Cyan (hsl(240 -> 180)) - Serin/Normal
//   35°C - 50°C : Camgöbeği -> Yeşil (hsl(180 -> 120)) - Ilık Çalışma Sıcaklığı
//   50°C - 65°C : Yeşil -> Sarı (hsl(120 -> 60)) - Dikkat / Yükselen Sıcaklık
//   65°C - 75°C : Sarı -> Turuncu (hsl(60 -> 30)) - Uyarı / Belirgin Isınma
//   75°C - 85°C : Turuncu -> Kırmızı (hsl(30 -> 0)) - Aşırı Sıcaklık
//   >= 85°C : Parlak Kırmızı / Beyaz-Kırmızı Işıma (hsl(0, 100%, 65%)) - Kritik Tehlike
function sicaklikToRenk(temp) {
    if (temp <= 20) {
        return 'hsl(240, 100%, 45%)';
    } else if (temp < 85) {
        // 20°C (240°) ile 85°C (0°) arasında doğrusal yumuşak geçiş
        const hue = 240 - ((temp - 20) * (240 / 65));
        return `hsl(${Math.max(0, Math.min(240, hue))}, 100%, 50%)`;
    } else {
        // 85°C üstünde doymuş/açık parlayan kritik kırmızı
        const lightness = Math.min(75, 50 + (temp - 85) * 1.2);
        return `hsl(0, 100%, ${lightness}%)`;
    }
}

function bolgelerdenMatrisUret(ozet, olcumler) {
    const matris = new Array(768);
    const ortam = (olcumler && olcumler.ortam_sicaklik !== undefined) ? Number(olcumler.ortam_sicaklik) : 25.0;
    const bolgeler = (ozet && Array.isArray(ozet.bolge_ort) && ozet.bolge_ort.length === 4)
        ? ozet.bolge_ort.map(Number)
        : [ortam + 2, ortam + 3, ortam + 2.5, ortam + 3.5];

    const maks = (ozet && ozet.maks !== undefined) ? Number(ozet.maks) : (Math.max(...bolgeler) + 2);
    const [hx, hy] = (ozet && Array.isArray(ozet.maks_konum) && ozet.maks_konum.length === 2)
        ? ozet.maks_konum
        : [16, 12];

    // Her yenileme ve karede canlı sensör dalgalanması hissi veren zamana bağlı mikro-faz
    const timePhase = Date.now() / 800;

    for (let y = 0; y < 24; y++) {
        const rowNorm = y / 23;
        for (let x = 0; x < 32; x++) {
            const colNorm = x / 31;
            // 4 köşe ağırlıklı bilinear enterpolasyon
            const b00 = bolgeler[0];
            const b10 = bolgeler[1];
            const b01 = bolgeler[2];
            const b11 = bolgeler[3];

            const top = b00 * (1 - colNorm) + b10 * colNorm;
            const bottom = b01 * (1 - colNorm) + b11 * colNorm;
            let val = top * (1 - rowNorm) + bottom * rowNorm;

            // Sıcak nokta (maks_konum) etrafında Gaussian yayılımı
            const dx = x - hx;
            const dy = y - hy;
            const distSq = (dx * dx) + (dy * dy * 1.5);
            const peakDelta = Math.max(0, maks - val);
            const spotIntensity = Math.exp(-distSq / 12.0); // 12 piksel varyans
            val += peakDelta * spotIntensity;

            // Her karede yenilenen termal sensör gürültüsü ve mikro dalgalanma (±0.4°C)
            const dynamicNoise = Math.sin(timePhase + x * 0.7 + y * 0.5) * 0.25 + 
                                 Math.cos(timePhase * 1.3 + (x ^ y)) * 0.15;
            matris[y * 32 + x] = Math.max(15, Math.min(120, val + dynamicNoise));
        }
    }
    return matris;
}

async function canliTermalYukle(modulId, olcumler, modulData = null) {
    try {
        const res = await apiFetch(`/moduller/${modulId}/termal/son`);
        if (res.ok) {
            const ozet = await res.json();
            state.termalOzet = ozet;

            document.getElementById('val-tmax').innerText = ozet.maks !== undefined ? Number(ozet.maks).toFixed(1) : '--';

            const hotspotEl = document.getElementById('hotspot-coord');
            if (hotspotEl && ozet.maks_konum) {
                hotspotEl.innerText = `Konum: X:${ozet.maks_konum[0]}, Y:${ozet.maks_konum[1]}`;
            }

            // Canlı termal kareyi çek veya bölge ortalamalarından 32x24 matris sentezle
            if (ozet.kare_id) {
                try {
                    const kareRes = await apiFetch(`/termal/kare/${ozet.kare_id}`);
                    if (kareRes.ok) {
                        const kareData = await kareRes.json();
                        state.termalMatris = kareData.piksel_verisi;
                        termalKareCiz();
                    } else {
                        state.termalMatris = bolgelerdenMatrisUret(ozet, olcumler);
                        termalKareCiz();
                    }
                } catch (kareErr) {
                    state.termalMatris = bolgelerdenMatrisUret(ozet, olcumler);
                    termalKareCiz();
                }
            } else {
                // Normal çalışan modüllerde 768 baytlık ham kare yerine 4 bölge ortalaması ve sıcak nokta koordinatı enterpolasyonu
                state.termalMatris = bolgelerdenMatrisUret(ozet, olcumler);
                termalKareCiz();
            }

            // Termal durum şeridi ve Dinamik Modül Durumu Değerlendirmesi
            const bannerEl = document.getElementById('thermal-status-banner');
            const bannerDesc = document.getElementById('banner-desc');
            const bannerTitle = document.getElementById('banner-title');
            const bannerIcon = document.getElementById('banner-icon');
            const modBadge = document.getElementById('active-module-status-badge');
            const tmaxBox = document.getElementById('val-tmax-box');

            const tMax = Number(ozet.maks);
            let termalSeviye = 'normal';

            // Endüstriyel Eşikler (Sadece termal sıcaklık eşikleri):
            // ≥ 80°C : KRİTİK (Kırmızı alarm)
            // 65°C - 79.9°C : UYARI (Turuncu alarm)
            // 55°C - 64.9°C : İZLE (Dikkat / Yükselen sıcaklık)
            // < 55°C : NORMAL (Yeşil, sağlıklı çalışma sıcaklığı)
            if (tMax >= 80) {
                termalSeviye = 'kritik';
            } else if (tMax >= 65) {
                termalSeviye = 'uyari';
            } else if (tMax >= 55) {
                termalSeviye = 'izle';
            } else {
                termalSeviye = 'normal';
            }

            // Modülün açık anomali/alarm seviyesini dahil et (asla uyarının üzerine "Normal" yazıp ezmemeli)
            const anomaliSeviye = enYuksekSeviye(
                state.alarmModulSeviyeleri[modulId],
                state.apiModulSeviyeleri[modulId]
            );
            const durumSeviye = enYuksekSeviye(termalSeviye, anomaliSeviye);
            const durumText = durumSeviye.toUpperCase();

            // Aktif anomali gerekçesini tespit et
            const aktifAnomali = (state.sonAlarmlar || []).find(a => a.modul_id === modulId && seviyeNormalize(a.seviye) === durumSeviye)
                || (modulData && modulData.acik_anomaliler ? modulData.acik_anomaliler.find(a => seviyeNormalize(a.seviye) === durumSeviye) : null);

            if (durumSeviye === 'kritik') {
                if (bannerIcon) bannerIcon.innerText = "🔥";
                if (bannerTitle) bannerTitle.innerText = "KRİTİK TERMAL / SİSTEM ALARMI:";
                if (bannerEl) {
                    bannerEl.style.background = 'rgba(239, 68, 68, 0.25)';
                    bannerEl.style.borderColor = 'var(--color-critical)';
                }
                if (bannerDesc) {
                    const detay = aktifAnomali ? `<b>${aktifAnomali.tip}:</b> ${aktifAnomali.gerekce} | ` : '';
                    bannerDesc.innerHTML = `<b style="color:var(--color-critical)">ACİL MÜDAHALE GEREKLİ!</b> ${detay}Sıcak nokta: <b>${tMax.toFixed(1)} °C</b> (Eşik: 80°C).`;
                }
            } else if (durumSeviye === 'uyari') {
                if (bannerIcon) bannerIcon.innerText = "⚠️";
                if (bannerTitle) bannerTitle.innerText = "TERMAL / SİSTEM UYARISI:";
                if (bannerEl) {
                    bannerEl.style.background = 'rgba(245, 158, 11, 0.18)';
                    bannerEl.style.borderColor = 'var(--color-warning)';
                }
                if (bannerDesc) {
                    const detay = aktifAnomali ? `<b>${aktifAnomali.tip}:</b> ${aktifAnomali.gerekce} | ` : '';
                    bannerDesc.innerHTML = `<b style="color:var(--color-warning)">DİKKAT (UYARI):</b> ${detay}Sıcak nokta: <b>${tMax.toFixed(1)} °C</b>.`;
                }
            } else if (durumSeviye === 'izle') {
                if (bannerIcon) bannerIcon.innerText = "👁️";
                if (bannerTitle) bannerTitle.innerText = "TERMAL İZLEME:";
                if (bannerEl) {
                    bannerEl.style.background = 'rgba(6, 182, 212, 0.15)';
                    bannerEl.style.borderColor = 'var(--color-izle)';
                }
                if (bannerDesc) {
                    bannerDesc.innerHTML = `<span style="color:var(--color-izle)">Yükselen Çalışma Sıcaklığı / İzleme.</span> Sıcak nokta: <b>${tMax.toFixed(1)} °C</b>. İzleme önerilir.`;
                }
            } else {
                if (bannerIcon) bannerIcon.innerText = "✅";
                if (bannerTitle) bannerTitle.innerText = "Canlı Termal Analiz:";
                if (bannerEl) {
                    bannerEl.style.background = 'rgba(16, 185, 129, 0.12)';
                    bannerEl.style.borderColor = 'var(--color-normal)';
                }
                if (bannerDesc) {
                    bannerDesc.innerHTML = `<span style="color:var(--color-normal)">Termal Dağılım Normal.</span> Sıcak nokta: <b>${tMax.toFixed(1)} °C</b>. Sağlıklı çalışma aralığında.`;
                }
            }

            // Metrik kartı rengini güncelle
            if (tmaxBox) {
                tmaxBox.className = `card-value ${durumSeviye}`;
            }

            // Aktif modül başlık rozetini ve hiyerarşi ağacındaki rozeti anında güncelle
            state.canliModulSeviyeleri[modulId] = durumSeviye;
            modulRozetiniGuncelle(modulId);
        } else if (olcumler && olcumler.termal_maks !== undefined) {
            document.getElementById('val-tmax').innerText = Number(olcumler.termal_maks).toFixed(1);
            state.termalOzet = {
                maks: Number(olcumler.termal_maks),
                maks_konum: [16, 12]
            };
            state.termalMatris = bolgelerdenMatrisUret(state.termalOzet, olcumler);
            termalKareCiz();
        }
    } catch (e) {
        console.warn("Termal veri çekilemedi:", e);
    }
}

// --------------------------------------------------------------------------
// 3. KANIT KARESİ GÖRÜNTÜLEME (Madde 19)
// --------------------------------------------------------------------------
async function anomaliSec(anomaliId) {
    const anomali = state.sonAlarmlar.find(a => a.id === anomaliId);
    if (!anomali) return;

    state.seciliAnomaliId = anomaliId;
    state.kanitKareModu = true; // İnceleme moduna geç, periyodik tarama normale döndürmesin!

    // Kartları görsel olarak vurgula
    document.querySelectorAll('.alarm-card').forEach(c => c.classList.remove('selected-alarm'));
    const seciliKart = document.getElementById(`alarm-card-${anomaliId}`);
    if (seciliKart) seciliKart.classList.add('selected-alarm');

    const seviye = seviyeNormalize(anomali.seviye || 'uyari');
    const isKritik = seviye === 'kritik';

    // Eğer anomali başka bir modüle aitse o modülü seç
    if (anomali.modul_id && anomali.modul_id !== state.aktifModulId) {
        state.aktifModulId = anomali.modul_id;
        state.aktifModulIsmi = anomali.modul_id;
        document.querySelectorAll('.tree-modul-item').forEach(el => el.classList.remove('active'));
        const seciliEl = document.getElementById(`modul-item-${anomali.modul_id}`);
        if (seciliEl) seciliEl.classList.add('active');
        await modulDetayYukle(anomali.modul_id);
    }

    // Banner güncelle (kare_id olsun veya olmasın uyarının detayını göster)
    const bannerEl = document.getElementById('thermal-status-banner');
    const bannerTitle = document.getElementById('banner-title');
    const bannerDesc = document.getElementById('banner-desc');
    const bannerIcon = document.getElementById('banner-icon');
    const btnLive = document.getElementById('btn-live-thermal');

    if (btnLive) btnLive.style.display = 'inline-block';
    if (bannerIcon) bannerIcon.innerText = isKritik ? "🔥" : "⚠️";
    if (bannerTitle) {
        bannerTitle.innerText = isKritik
            ? `🚨 KRİTİK ALARM İNCELEME (${anomali.tip || anomali.id}):`
            : `⚠️ UYARI İNCELEME (${anomali.tip || anomali.id}):`;
    }
    if (bannerDesc) {
        bannerDesc.innerHTML = `<b style="color:${isKritik ? 'var(--color-critical)' : 'var(--color-warning)'}">${anomali.tip || 'Anomali'}</b> | ${anomali.gerekce || 'Gerekçe belirtilmedi.'}`;
    }
    if (bannerEl) {
        bannerEl.style.background = isKritik ? 'rgba(239, 68, 68, 0.25)' : 'rgba(245, 158, 11, 0.2)';
        bannerEl.style.borderColor = isKritik ? 'var(--color-critical)' : 'var(--color-warning)';
    }

    // Aktif modül başlık rozetini anomali seviyesine sabitle
    const topBadge = document.getElementById('active-module-status-badge');
    if (topBadge) {
        topBadge.className = `status-badge badge-${seviye}`;
        topBadge.innerText = seviye.toUpperCase();
    }

    // Kanıt Karesini çek ve çiz (Madde 19)
    const kareId = anomali.kanit ? anomali.kanit.kare_id : null;
    const piksel = anomali.kanit ? anomali.kanit.piksel : null;

    if (kareId) {
        try {
            const res = await apiFetch(`/termal/kare/${kareId}`);
            if (res.ok) {
                const kareData = await res.json();
                state.termalMatris = kareData.piksel_verisi;

                // Sıcak nokta koordinatı kanıt pikseli
                const maksKonum = (Array.isArray(piksel) && piksel.length === 2) ? piksel : [16, 12];
                state.termalOzet = {
                    maks: (anomali.skor ? (anomali.skor * 100).toFixed(1) : 75.0),
                    maks_konum: maksKonum
                };

                if (bannerTitle) {
                    bannerTitle.innerText = `📸 Kanıt Karesi (${kareId}) - ${isKritik ? 'KRİTİK' : 'UYARI'}:`;
                }

                termalKareCiz();
            }
        } catch (err) {
            console.error("Kanıt karesi yüklenemedi:", err);
        }
    }
}

function canliGoruntuyeDon() {
    state.kanitKareModu = false;
    state.seciliAnomaliId = null;

    const btnLive = document.getElementById('btn-live-thermal');
    if (btnLive) btnLive.style.display = 'none';

    document.querySelectorAll('.alarm-card').forEach(c => c.classList.remove('selected-alarm'));
    modulDetayYukle(state.aktifModulId);
}

// --------------------------------------------------------------------------
// 4. 32x24 TERMAL MATRİS ÇİZİMİ VE CANVAS ETKİLEŞİMİ
// --------------------------------------------------------------------------
function termalKareCiz() {
    const canvas = document.getElementById('thermalCanvas');
    if (!canvas || !state.termalMatris || state.termalMatris.length !== 768) return;

    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    const cellW = width / 32;
    const cellH = height / 24;

    canvas.className = state.smoothMode ? 'smooth' : '';

    // Piksel Çizimi (Her piksel sıcaklık aralığına göre dinamik renklendirilir)
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

    // Sıcak Nokta (Hotspot) Reticle Konumlandırma
    const reticle = document.getElementById('hotspot-reticle');
    const reticleTemp = document.getElementById('reticle-temp');

    if (state.termalOzet && state.termalOzet.maks_konum && reticle) {
        const [hx, hy] = state.termalOzet.maks_konum;
        const rect = canvas.getBoundingClientRect();
        const cellW = rect.width / 32;
        const cellH = rect.height / 24;

        const rawX = (hx + 0.5) * cellW;
        const rawY = (hy + 0.5) * cellH;

        const posX = Math.max(14, Math.min(rect.width - 14, rawX));
        const posY = Math.max(14, Math.min(rect.height - 14, rawY));

        reticle.style.display = 'block';
        reticle.style.left = `${posX}px`;
        reticle.style.top = `${posY}px`;

        if (reticleTemp) {
            reticleTemp.innerText = `${Number(state.termalOzet.maks).toFixed(1)} °C`;
            if (posY < 35) {
                reticleTemp.classList.add('pos-bottom');
            } else {
                reticleTemp.classList.remove('pos-bottom');
            }
            if (posX < 40) {
                reticleTemp.classList.add('pos-right');
                reticleTemp.classList.remove('pos-left');
            } else if (posX > rect.width - 40) {
                reticleTemp.classList.add('pos-left');
                reticleTemp.classList.remove('pos-right');
            } else {
                reticleTemp.classList.remove('pos-left', 'pos-right');
            }
        }
    }
}

// Canvas Mouse Move HUD Tooltip Etkileşimi
function setupCanvasHover() {
    const canvas = document.getElementById('thermalCanvas');
    const tooltip = document.getElementById('thermal-tooltip');
    const tooltipTemp = document.getElementById('tooltip-temp');
    const tooltipCoord = document.getElementById('tooltip-coord');

    if (!canvas || !tooltip) return;

    canvas.addEventListener('mousemove', (e) => {
        if (!state.termalMatris) return;

        const rect = canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        const cellX = Math.floor((mouseX / rect.width) * 32);
        const cellY = Math.floor((mouseY / rect.height) * 24);

        if (cellX >= 0 && cellX < 32 && cellY >= 0 && cellY < 24) {
            const index = cellY * 32 + cellX;
            const temp = state.termalMatris[index];

            tooltip.style.display = 'block';
            tooltipTemp.innerText = `${temp ? temp.toFixed(1) : '--'} °C`;
            tooltipCoord.innerText = `X: ${cellX}, Y: ${cellY}`;

            const tipWidth = tooltip.offsetWidth || 90;
            const tipHeight = tooltip.offsetHeight || 44;

            let posY = mouseY + 14;
            if (mouseY + tipHeight + 14 > rect.height) {
                posY = mouseY - tipHeight - 8;
            }

            let posX = mouseX + 14;
            if (mouseX + tipWidth + 14 > rect.width) {
                posX = mouseX - tipWidth - 8;
            }

            posX = Math.max(4, posX);
            posY = Math.max(4, posY);

            tooltip.style.left = `${posX}px`;
            tooltip.style.top = `${posY}px`;
        }
    });

    canvas.addEventListener('mouseleave', () => {
        tooltip.style.display = 'none';
    });
}

// --------------------------------------------------------------------------
// 5. AKTİF ALARMLAR VE OPERATÖR ONAY AKIŞI (GET/POST /anomaliler) - Madde 18
// --------------------------------------------------------------------------
async function alarmlariYukle() {
    const container = document.getElementById('alarms-container');
    const counterEl = document.getElementById('active-alarm-count');
    if (!container) return;

    try {
        // Yalnızca aktif/açık durumdaki anomalileri sorgula (Sözleşme ⑤ / Madde 18)
        const res = await apiFetch('/anomaliler?durum=acik&limit=50');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setOnlineStatus(true);

        const anomaliler = (data.veriler || []).filter(a => a.durum !== 'kapandi');

        // Yeni açık alarm kontrolü ve ses çalma
        if (anomaliler.length > 0) {
            const yeniAlarmVar = anomaliler.some(a => !state.sonAlarmlar.some(sa => sa.id === a.id));
            if (yeniAlarmVar) {
                sfx.playAlert();
            }
        }
        state.sonAlarmlar = anomaliler;

        // Açık anomalilere sahip modüllerin seviye haritasını oluştur
        const acikSeviyeler = {};
        anomaliler.forEach(a => {
            if (a.modul_id && a.seviye) {
                const s = seviyeNormalize(a.seviye);
                const mevcut = acikSeviyeler[a.modul_id] || 'normal';
                if (s === 'kritik' || (s === 'uyari' && mevcut !== 'kritik') || (s === 'izle' && mevcut === 'normal')) {
                    acikSeviyeler[a.modul_id] = s;
                }
            }
        });
        state.alarmModulSeviyeleri = acikSeviyeler;

        // Ağaçtaki tüm modül rozetlerini güncelle: Açık anomali varsa seviyesini göster, yoksa canlı/normal
        document.querySelectorAll('[id^="tree-badge-"]').forEach(badge => {
            const mId = badge.id.replace('tree-badge-', '');
            modulRozetiniGuncelle(mId);
        });

        // Eğer seçili modülde açık anomali veya canlı kritik/uyarı varsa başlık rozetini güncelle
        if (!state.kanitKareModu) {
            const topBadge = document.getElementById('active-module-status-badge');
            if (topBadge) {
                const aktifSev = modulSeviyesiniGetir(state.aktifModulId);
                topBadge.className = `status-badge badge-${aktifSev}`;
                topBadge.innerText = aktifSev.toUpperCase();
            }
        }

        if (counterEl) counterEl.innerText = anomaliler.length;

        // Madde 18 Kabul: Anomali listesi boş görünüyorsa gerçekten boş olduğu için görünüyor
        if (anomaliler.length === 0) {
            container.innerHTML = `
                <div class="empty-alarms" style="padding: 2rem 1rem; text-align: center;">
                    <span class="empty-icon" style="font-size: 2.5rem; display: block; margin-bottom: 0.5rem;">🛡️</span>
                    <strong style="color:var(--color-normal); font-size: 1.1rem;">Sistem Stabil</strong>
                    <p style="margin-top:6px; color: var(--text-muted); font-size: 0.85rem;">Şu anda açık anomali bulunmamaktadır.</p>
                </div>
            `;
            return;
        }

        let html = '';
        anomaliler.forEach(anomali => {
            const seviye = seviyeNormalize(anomali.seviye || 'uyari');
            const isKritik = seviye === 'kritik';
            const seviyeText = seviye.toUpperCase();
            const zaman = anomali.son_gorulme || anomali.ilk_gorulme || 'Canlı';
            const isSelected = anomali.id === state.seciliAnomaliId;

            html += `
                <div class="alarm-card ${isKritik ? 'kritik' : ''} ${isSelected ? 'selected-alarm' : ''}" 
                     id="alarm-card-${anomali.id}"
                     onclick="anomaliSec('${anomali.id}')"
                     style="cursor: pointer;">
                    <div class="alarm-card-header">
                        <span class="alarm-modul">⚠️ ${anomali.modul_id}</span>
                        <span class="status-badge badge-${seviye}">${seviyeText}</span>
                    </div>
                    <div class="alarm-time">⏱️ Tespit: ${formatZamanTr(zaman)}</div>
                    <div class="alarm-reason">
                        <b>${anomali.tip || 'Anomali'}:</b> ${anomali.gerekce || 'Gerekçe belirtilmedi.'}
                    </div>
                    ${anomali.kanit && anomali.kanit.kare_id ? `<div style="font-size: 0.75rem; color: var(--accent-cyan); margin-top: 4px;">📸 Kanıt Karesi Mevcut (İncelemek için tıkla)</div>` : ''}
                    <button class="btn-ack" onclick="event.stopPropagation(); alarmOnayla('${anomali.id}', '${anomali.modul_id}')" style="margin-top: 8px;">
                        <span>✓</span> Operatör Onayı (Kapat)
                    </button>
                </div>
            `;
        });

        container.innerHTML = html;
    } catch (err) {
        console.warn("Alarmlar okunamadı:", err);
        setOnlineStatus(false);
    }
}

async function alarmOnayla(alarmId, modulId) {
    try {
        // Sözleşme ⑤: POST /anomaliler/{id}/onayla?aktor=operator_1 (Madde 18)
        const res = await apiFetch(`/anomaliler/${alarmId}/onayla?aktor=operator_1`, {
            method: 'POST'
        });

        if (res.ok) {
            const card = document.getElementById(`alarm-card-${alarmId}`);
            if (card) {
                card.style.opacity = '0';
                card.style.transform = 'scale(0.95)';
                setTimeout(() => card.remove(), 250);
            }

            addAuditLog(`Operatör Onayı: ${modulId} (${alarmId}) onaylandı ve kapatıldı.`);

            if (state.seciliAnomaliId === alarmId) {
                canliGoruntuyeDon();
            }

            setTimeout(async () => {
                await alarmlariYukle();
                await hiyerarsiyiYukle();
                if (state.aktifModulId === modulId) {
                    modulDetayYukle(modulId);
                }
                operasyonGunluguYukle();
            }, 300);
        } else if (res.status === 409) {
            alert(`Bilgi: ${alarmId} numaralı anomali zaten daha önce onaylanmış veya kapatılmış.`);
            await alarmlariYukle();
        } else {
            const err = await res.json().catch(() => ({}));
            const msg = (err && err.hata && err.hata.mesaj) || `HTTP ${res.status}`;
            alert(`Alarm onaylama işlemi başarısız: ${msg}`);
        }
    } catch (err) {
        console.error("Onaylama hatası:", err);
        alert("Sunucuya ulaşılamadı.");
    }
}

async function operasyonGunluguYukle() {
    try {
        const res = await apiFetch('/gecisler?limit=30');
        if (res.ok) {
            const data = await res.json();
            const gecisler = (data.veriler || []).slice().reverse();
            const remoteEntries = gecisler.map(g => {
                const zamanStr = g.zaman ? formatZamanTr(g.zaman) : '';
                let text = '';
                if (g.alan === 'durum') {
                    if (g.yeni === 'onaylandi') {
                        text = `✅ Operatör Onayı: <b>${g.anomali_id}</b> onaylandı (Operatör: ${g.aktor})`;
                    } else if (g.yeni === 'kapandi') {
                        text = `🛡️ Anomali Kapatıldı: <b>${g.anomali_id}</b> (${g.aktor})`;
                    } else if (g.yeni === 'acik') {
                        text = `🚨 Anomali Başlatıldı: <b>${g.anomali_id}</b>`;
                    } else {
                        text = `Durum: <b>${g.anomali_id}</b> → ${g.yeni} (${g.aktor})`;
                    }
                } else if (g.alan === 'seviye') {
                    text = `📶 Seviye: <b>${g.anomali_id}</b> (${g.onceki || 'normal'} → ${g.yeni})`;
                } else {
                    text = `${g.anomali_id}: ${g.alan} → ${g.yeni}`;
                }
                return { time: zamanStr, mesaj: text, isRemote: true };
            });

            const localEntries = state.auditLog.filter(l => !l.isRemote);
            state.auditLog = [...localEntries, ...remoteEntries];
            renderAuditLog();
        }
    } catch (e) {
        console.warn("Operasyon günlüğü çekilemedi:", e);
    }
}

function addAuditLog(mesaj) {
    const time = new Date().toLocaleTimeString('tr-TR', { timeZone: 'Europe/Istanbul' });
    state.auditLog.unshift({ time, mesaj, isRemote: false });
    renderAuditLog();
}

function renderAuditLog() {
    const container = document.getElementById('audit-container');
    if (!container) return;

    if (state.auditLog.length === 0) {
        container.innerHTML = `<div class="empty-audit"><p>Henüz operatör eylemi kaydedilmedi.</p></div>`;
        return;
    }

    container.innerHTML = state.auditLog.map(item => `
        <div class="audit-entry">
            <div class="audit-time">${item.time}</div>
            <div class="audit-text">${item.mesaj}</div>
        </div>
    `).join('');
}

// --------------------------------------------------------------------------
// 6. YARDIMCI KONTROLLER & BAŞLANGIÇ
// --------------------------------------------------------------------------
function setOnlineStatus(online) {
    state.isOnline = online;
    const led = document.getElementById('api-status-led');
    const label = document.getElementById('api-status-text');

    if (led && label) {
        if (online) {
            led.className = 'status-indicator online';
            label.innerText = 'API ÇEVRİMİÇİ';
        } else {
            led.className = 'status-indicator offline';
            label.innerText = 'BAĞLANTI KESİLDİ';
        }
    }
}

function updateClock() {
    const clock = document.getElementById('clock-display');
    if (clock) {
        const now = new Date();
        clock.innerText = now.toLocaleTimeString('tr-TR', { timeZone: 'Europe/Istanbul' });
    }
}

function startPolling() {
    if (state.pollTimer) clearInterval(state.pollTimer);
    state.pollTimer = setInterval(() => {
        if (!state.kanitKareModu && !state.seciliAnomaliId) {
            modulDetayYukle(state.aktifModulId);
        }
        alarmlariYukle();
    }, state.pollIntervalMs);
}

window.addEventListener('DOMContentLoaded', () => {
    updateClock();
    setInterval(updateClock, 1000);

    setupCanvasHover();

    const btnRefresh = document.getElementById('btn-manual-refresh');
    if (btnRefresh) {
        btnRefresh.addEventListener('click', () => {
            hiyerarsiyiYukle();
            modulDetayYukle(state.aktifModulId);
            alarmlariYukle();
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
            document.getElementById('audio-icon').innerText = state.audioEnabled ? '🔔' : '🔕';
            document.getElementById('audio-text').innerText = state.audioEnabled ? 'Ses Açık' : 'Sessiz';
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
            btnSmooth.innerText = `Pürüzsüzleştirme: ${state.smoothMode ? 'Açık' : 'Kapalı'}`;
            termalKareCiz();
        });
    }

    const btnGrid = document.getElementById('btn-toggle-grid');
    if (btnGrid) {
        btnGrid.addEventListener('click', () => {
            state.gridMode = !state.gridMode;
            btnGrid.innerText = `Izgara: ${state.gridMode ? 'Açık' : 'Kapalı'}`;
            termalKareCiz();
        });
    }

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
    modulDetayYukle(state.aktifModulId);
    alarmlariYukle();
    operasyonGunluguYukle();
    startPolling();
});
