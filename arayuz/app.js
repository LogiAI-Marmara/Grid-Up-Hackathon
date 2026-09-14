/**
 * Grid Up - İZ C: Operasyon Yüzü & Monitoring Uygulaması
 * Saha Hiyerarşisi, Canlı Sensör Metrikleri, 32x24 Termal Görselleştirme ve Alarm Yönetimi
 */

// API Base URL tespiti: Doğrudan 8000'den açıldıysa /api, port 80/boş ise host:8000/api
const API_BASE = window.location.port === "8000" 
    ? "/api" 
    : `${window.location.protocol}//${window.location.hostname}:8000/api`;


// Uygulama Durumu (State)
const state = {
    aktifModulId: 'TR041-P01-M1',
    aktifModulIsmi: 'Giriş Fideri Modülü',
    termalMatris: null,
    termalOzet: null,
    smoothMode: true,
    gridMode: false,
    audioEnabled: true,
    pollIntervalMs: 3000,
    pollTimer: null,
    isOnline: true,
    sonAlarmlar: [],
    auditLog: []
};

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
// 1. SAHA HİYERARŞİSİ YÖNETİMİ (GET /api/sahalar)
// --------------------------------------------------------------------------
async function hiyerarsiyiYukle() {
    const container = document.getElementById('hierarchy-container');
    const countTag = document.getElementById('hierarchy-count');

    try {
        const res = await fetch(`${API_BASE}/sahalar`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const sahalar = await res.json();
        setOnlineStatus(true);

        let toplamModul = 0;
        let html = '';

        sahalar.forEach(saha => {
            html += `
                <div class="tree-saha">
                    <div class="tree-saha-header">
                        <span>📍</span>
                        <span>${saha.saha_id}</span>
                    </div>
            `;

            saha.panolar.forEach(pano => {
                html += `
                    <div class="tree-pano">
                        <div class="tree-pano-header">
                            <span>⚙️</span>
                            <span>${pano.pano_id}</span>
                        </div>
                        <ul class="tree-modul-list">
                `;

                pano.moduller.forEach(modul => {
                    toplamModul++;
                    const isActive = modul.modul_id === state.aktifModulId;
                    const durumClass = `badge-${modul.durum || 'normal'}`;
                    const durumText = (modul.durum || 'NORMAL').toUpperCase();

                    html += `
                        <li class="tree-modul-item ${isActive ? 'active' : ''}" 
                            onclick="modulSec('${modul.modul_id}', '${modul.isim || modul.modul_id}')"
                            id="modul-item-${modul.modul_id}">
                            <div class="modul-info-left">
                                <span class="modul-id-text">${modul.modul_id}</span>
                                <span class="modul-sub-text">${modul.isim || 'Hücre Modülü'}</span>
                            </div>
                            <span class="status-badge ${durumClass}">${durumText}</span>
                        </li>
                    `;
                });

                html += `</ul></div>`;
            });

            html += `</div>`;
        });

        container.innerHTML = html;
        if (countTag) countTag.innerText = `${toplamModul} Modül`;
    } catch (err) {
        console.warn("Hiyerarşi çekilemedi:", err);
        setOnlineStatus(false);
    }
}

function modulSec(modulId, modulIsmi) {
    state.aktifModulId = modulId;
    state.aktifModulIsmi = modulIsmi;

    document.querySelectorAll('.tree-modul-item').forEach(el => el.classList.remove('active'));
    const seciliEl = document.getElementById(`modul-item-${modulId}`);
    if (seciliEl) seciliEl.classList.add('active');

    modulDetayYukle(modulId);
}

// --------------------------------------------------------------------------
// 2. MODÜL VE TERMAL VERİLERİN YÜKLENMESİ (GET /api/moduller/{id})
// --------------------------------------------------------------------------
async function modulDetayYukle(modulId) {
    document.getElementById('active-module-badge').innerText = modulId;
    document.getElementById('active-module-name').innerText = state.aktifModulIsmi;

    try {
        const res = await fetch(`${API_BASE}/moduller/${modulId}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setOnlineStatus(true);

        // Zaman ve Durumlar
        const zamanStr = data.zaman || new Date().toLocaleTimeString('tr-TR', { timeZone: 'Europe/Istanbul' });
        document.getElementById('val-time').innerText = zamanStr;
        document.getElementById('val-rssi').innerText = `${data.sinyal ?? '--'} dBm`;

        
        const feedEl = document.getElementById('val-feed');
        if (feedEl) {
            feedEl.innerText = (data.besleme || 'sebeke').toUpperCase();
            feedEl.className = data.besleme === 'yedek' ? 'badge-feed badge-warning' : 'badge-feed';
        }

        // Metrik Kartları Değerleri
        document.getElementById('val-temp').innerText = data.ortam_sicaklik?.toFixed(1) ?? '--';
        document.getElementById('val-hum').innerText = data.nem?.toFixed(1) ?? '--';
        document.getElementById('val-tmax').innerText = data.termal_ozet?.maks?.toFixed(1) ?? '--';
        document.getElementById('val-l1').innerText = data.akim_l1?.toFixed(1) ?? '--';
        document.getElementById('val-l2').innerText = data.akim_l2?.toFixed(1) ?? '--';
        document.getElementById('val-l3').innerText = data.akim_l3?.toFixed(1) ?? '--';
        document.getElementById('val-notr').innerText = data.akim_notr?.toFixed(1) ?? '0.0';
        document.getElementById('val-arc').innerText = data.ark_olay ?? '0';

        // Faz Dengesizliği Hesabı
        if (data.akim_l1 && data.akim_l2 && data.akim_l3) {
            const akimlar = [data.akim_l1, data.akim_l2, data.akim_l3];
            const ort = akimlar.reduce((a, b) => a + b, 0) / 3;
            const maksFark = Math.max(...akimlar.map(a => Math.abs(a - ort)));
            const dengesizlik = ort > 0 ? ((maksFark / ort) * 100).toFixed(1) : 0;
            const diffEl = document.getElementById('current-diff');
            if (diffEl) {
                diffEl.innerText = `Faz Dengesizliği: %${dengesizlik}`;
                diffEl.style.color = dengesizlik > 15 ? 'var(--color-warning)' : 'var(--text-muted)';
            }
        }

        // Termal Bilgiler ve Çizim
        state.termalMatris = data.termal_kare;
        state.termalOzet = data.termal_ozet;

        const hotspotEl = document.getElementById('hotspot-coord');
        const bannerEl = document.getElementById('thermal-status-banner');
        const bannerDesc = document.getElementById('banner-desc');

        if (data.termal_ozet && data.termal_ozet.maks_konum) {
            const [hx, hy] = data.termal_ozet.maks_konum;
            if (hotspotEl) hotspotEl.innerText = `Konum: X:${hx}, Y:${hy}`;

            if (data.termal_ozet.maks >= 65) {
                if (bannerEl) {
                    bannerEl.style.background = 'rgba(239, 68, 68, 0.15)';
                    bannerEl.style.borderColor = 'var(--color-critical)';
                }
                if (bannerDesc) {
                    bannerDesc.innerHTML = `<b style="color:var(--color-critical)">AŞIRI SICAKLIK ALARMI!</b> (${data.termal_ozet.maks} °C) - Klemens/Barada ark veya gevşeklik riski tespit edildi.`;
                }
            } else {
                if (bannerEl) {
                    bannerEl.style.background = 'rgba(16, 185, 129, 0.12)';
                    bannerEl.style.borderColor = 'var(--color-normal)';
                }
                if (bannerDesc) {
                    bannerDesc.innerHTML = `<span style="color:var(--color-normal)">Termal Dağılım Normal.</span> Maksimum sıcaklık: ${data.termal_ozet.maks} °C.`;
                }
            }
        }

        termalKareCiz();
    } catch (err) {
        console.warn(`Modül (${modulId}) detayları çekilemedi:`, err);
        setOnlineStatus(false);
    }
}

// --------------------------------------------------------------------------
// 3. 32x24 TERMAL MATRİS ÇİZİMİ VE CANVAS ETKİLEŞİMİ
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

    // Piksel Çizimi
    for (let y = 0; y < 24; y++) {
        for (let x = 0; x < 32; x++) {
            const temp = state.termalMatris[y * 32 + x];
            // 20°C (Mavi - HSL 240) -> 85°C (Kırmızı - HSL 0)
            const hue = Math.max(0, Math.min(240, 240 - ((temp - 20) * (240 / 65))));
            ctx.fillStyle = `hsl(${hue}, 100%, 50%)`;
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

        // Dairenin canvas sınırları dışına taşmasını engelle (clamp)
        const posX = Math.max(14, Math.min(rect.width - 14, rawX));
        const posY = Math.max(14, Math.min(rect.height - 14, rawY));

        reticle.style.display = 'block';
        reticle.style.left = `${posX}px`;
        reticle.style.top = `${posY}px`;

        if (reticleTemp) {
            reticleTemp.innerText = `${state.termalOzet.maks} °C`;

            // AKILLI KONUMLANDIRMA: Eğer sıcak nokta yukarıdaysa (posY < 35px),
            // derece etiketi halkanın ALTINA insin, kesilmesin!
            if (posY < 35) {
                reticleTemp.classList.add('pos-bottom');
            } else {
                reticleTemp.classList.remove('pos-bottom');
            }

            // Yatay kenar kontrolleri (Sol ve sağ taşmaları engelle)
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

            // Tooltip boyutları (tahmini 90x44 px)
            const tipWidth = tooltip.offsetWidth || 90;
            const tipHeight = tooltip.offsetHeight || 44;

            // AKILLI KONUMLANDIRMA:
            // 1. Dikey: Eğer imleç aşağıdaysa tooltip'i imlecin YUKARISINA al
            let posY = mouseY + 14;
            if (mouseY + tipHeight + 14 > rect.height) {
                posY = mouseY - tipHeight - 8;
            }

            // 2. Yatay: Eğer imleç sağdaysa tooltip'i imlecin SOLUNA al
            let posX = mouseX + 14;
            if (mouseX + tipWidth + 14 > rect.width) {
                posX = mouseX - tipWidth - 8;
            }

            // Minimum 4px sınır koruması
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
// 4. AKTİF ALARMLAR VE OPERATÖR ONAY AKIŞI (GET/POST /api/anomaliler)
// --------------------------------------------------------------------------
async function alarmlariYukle() {
    const container = document.getElementById('alarms-container');
    const counterEl = document.getElementById('active-alarm-count');

    try {
        const res = await fetch(`${API_BASE}/anomaliler`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const anomaliler = await res.json();
        setOnlineStatus(true);

        // Yeni alarm kontrolü ve ses çalma
        if (anomaliler.length > 0) {
            const yeniAlarmVar = anomaliler.some(a => !state.sonAlarmlar.some(sa => sa.id === a.id));
            if (yeniAlarmVar) {
                sfx.playAlert();
            }
        }
        state.sonAlarmlar = anomaliler;

        if (counterEl) counterEl.innerText = anomaliler.length;

        if (anomaliler.length === 0) {
            container.innerHTML = `
                <div class="empty-alarms">
                    <span class="empty-icon">🛡️</span>
                    <strong style="color:var(--color-normal);">Sistem Stabil</strong>
                    <p style="margin-top:4px;">Şu anda açık anomali uyarısı bulunmamaktadır.</p>
                </div>
            `;
            return;
        }

        let html = '';
        anomaliler.forEach(anomali => {
            const isKritik = anomali.seviye === 'kritik';
            const seviyeText = (anomali.seviye || 'UYARI').toUpperCase();

            html += `
                <div class="alarm-card ${isKritik ? 'kritik' : ''}" id="alarm-card-${anomali.id}">
                    <div class="alarm-card-header">
                        <span class="alarm-modul">⚠️ ${anomali.modul_id}</span>
                        <span class="status-badge ${isKritik ? 'badge-kritik' : 'badge-uyari'}">${seviyeText}</span>
                    </div>
                    <div class="alarm-time">⏱️ Tespit: ${anomali.zaman || 'Canlı Akış'}</div>
                    <div class="alarm-reason">
                        <b>Gerekçe:</b> ${anomali.gerekce || 'Anomali sebebi belirtilmedi.'}
                    </div>
                    <button class="btn-ack" onclick="alarmOnayla('${anomali.id}', '${anomali.modul_id}')">
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
        const res = await fetch(`${API_BASE}/anomaliler/${alarmId}/onayla`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        if (res.ok) {
            const card = document.getElementById(`alarm-card-${alarmId}`);
            if (card) {
                card.style.opacity = '0';
                card.style.transform = 'scale(0.95)';
                setTimeout(() => card.remove(), 250);
            }

            // Operasyon günlüğüne ekle
            addAuditLog(`Alarm Onaylandı: ${modulId} (ID: ${alarmId})`);

            // Verileri tazele
            setTimeout(() => {
                alarmlariYukle();
                hiyerarsiyiYukle();
                modulDetayYukle(state.aktifModulId);
            }, 300);
        } else {
            alert("Alarm onaylama işlemi sunucu tarafından reddedildi.");
        }
    } catch (err) {
        console.error("Onaylama hatası:", err);
        alert("Sunucuya ulaşılamadı.");
    }
}

function addAuditLog(mesaj) {
    const time = new Date().toLocaleTimeString('tr-TR', { timeZone: 'Europe/Istanbul' });
    state.auditLog.unshift({ time, mesaj });
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
// 5. YARDIMCI KONTROLLER (Saat, Çevrimiçi Durumu, Ayarlar)
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
        modulDetayYukle(state.aktifModulId);
        alarmlariYukle();
    }, state.pollIntervalMs);
}

// --------------------------------------------------------------------------
// 6. BAŞLANGIÇ VE EVENT LISTENER'LAR
// --------------------------------------------------------------------------
window.addEventListener('DOMContentLoaded', () => {
    updateClock();
    setInterval(updateClock, 1000);

    // Canvas etkileşimini başlat
    setupCanvasHover();

    // Buton Dinleyicileri
    const btnRefresh = document.getElementById('btn-manual-refresh');
    if (btnRefresh) {
        btnRefresh.addEventListener('click', () => {
            hiyerarsiyiYukle();
            modulDetayYukle(state.aktifModulId);
            alarmlariYukle();
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

    // Tab geçişleri (Açık Alarmlar vs Operasyon Günlüğü)
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
            renderAuditLog();
        });
    }

    // İlk Yüklemeler
    hiyerarsiyiYukle();
    modulDetayYukle(state.aktifModulId);
    alarmlariYukle();
    startPolling();
});