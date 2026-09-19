# alarm_service.py
"""
Grid Up Hackathon - İZ C: Alarm ve Bildirim Servisi
Sözleşme ⑤ küresel geçiş akışını (/gecisler) dinler.
Seviye yükselmelerini (izle -> uyari / kritik) tespit eder,
anti-flapping (tekrar önleme) koruması ve kalıcı durum saklama ile
servis yeniden başlasa bile aynı geçişlerin tekrar bildirilmesini engeller.
"""

import os
import sys
import time
import json
import html
import logging
import requests
from datetime import datetime, timezone, timedelta

# Türkiye Saati (UTC+3)
TZ_TR = timezone(timedelta(hours=3))

def get_tr_time():
    return datetime.now(TZ_TR).strftime("%Y-%m-%d %H:%M:%S")

try:
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(message)s"
)

# Ortam Değişkenleri (Madde 15: Repoda gömülü anahtar yok, ortam değişkeninden okunur)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
API_URL = os.getenv("API_URL", "http://localhost:8080").rstrip("/")
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "300"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))
STATE_FILE = os.getenv("ALARM_STATE_FILE", os.path.join(os.path.dirname(__file__), "alarm_state.json"))

SEVIYE_DERECESI = {
    "normal": 0,
    "izle": 1,
    "uyari": 2,
    "kritik": 3
}

class AlarmManager:
    def __init__(self, api_url=API_URL, cooldown_seconds=COOLDOWN_SECONDS, state_file=STATE_FILE):
        self.api_url = api_url.rstrip("/")
        self.cooldown = cooldown_seconds
        self.state_file = state_file
        self.state = self.load_state()

    def load_state(self) -> dict:
        """Kalıcı durumu dosyadan yükler (Madde 21: kaldığı yeri hatırlar)"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    logging.info(f"📂 Önceki durum yüklendi: son_gecis_id={data.get('son_gecis_id')}")
                    return data
            except Exception as e:
                logging.warning(f"Durum dosyası okunamadı, sıfırdan başlanıyor: {e}")
        return {"son_gecis_id": None, "last_alert_times": {}}

    def save_state(self):
        """Kalıcı durumu kaydeder"""
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logging.error(f"Durum dosyası yazılamadı: {e}")

    def fetch_anomaly_detail(self, anomali_id: str) -> dict | None:
        """Anomali detayını (gerekçe, kanıt, modul_id) çeker"""
        url = f"{self.api_url}/anomaliler/{anomali_id}"
        try:
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                return res.json()
        except Exception as e:
            logging.warning(f"Anomali detayı alınamadı ({anomali_id}): {e}")
        return None

    def evaluate_transition(self, gecis: dict):
        """
        Geçiş kaydını değerlendirir.
        Yalnızca seviye yükselmelerinde (normal/izle -> uyari/kritik veya uyari -> kritik) alarm tetikler.
        """
        alan = gecis.get("alan")
        if alan != "seviye":
            return

        onceki = str(gecis.get("onceki") or "normal").lower()
        yeni = str(gecis.get("yeni") or "normal").lower()

        onceki_puan = SEVIYE_DERECESI.get(onceki, 0)
        yeni_puan = SEVIYE_DERECESI.get(yeni, 0)

        # Yalnızca seviye arttıysa ve yeni seviye uyarı veya kritik ise
        if yeni_puan > onceki_puan and yeni in ["uyari", "kritik"]:
            anomali_id = gecis.get("anomali_id")
            detay = self.fetch_anomaly_detail(anomali_id) if anomali_id else None

            modul_id = (detay.get("modul_id") if detay else None) or "Bilinmeyen Modül"
            gerekce = (detay.get("gerekce") if detay else None) or f"Seviye geçişi: {onceki} -> {yeni}"
            skor = detay.get("skor") if detay else None
            zaman = gecis.get("zaman") or get_tr_time()

            now = time.time()
            last_alerts = self.state.setdefault("last_alert_times", {})

            # Anti-flapping (Tekrar Önleme) Mekanizması
            if modul_id in last_alerts:
                gecen_sure = now - last_alerts[modul_id]
                if gecen_sure < self.cooldown:
                    kalan_sure = int(self.cooldown - gecen_sure)
                    logging.info(
                        f"⏳ [ANTI-FLAPPING] {modul_id} bekleme süresinde (Kalan: {kalan_sure} sn). "
                        f"Geçiş ID {gecis.get('id')} bildirimi atlandı."
                    )
                    return

            self.emit_notification(
                modul_id=modul_id,
                anomali_id=anomali_id,
                seviye=yeni,
                onceki_seviye=onceki,
                gerekce=gerekce,
                zaman=zaman,
                skor=skor
            )
            last_alerts[modul_id] = now

    def emit_notification(self, modul_id, anomali_id, seviye, onceki_seviye, gerekce, zaman, skor):
        """Bildirimi kanallara (Log, GSM/SMS veya Telegram) dağıtır"""
        seviye_str = seviye.upper()
        skor_bilgisi = f" (Skor: %{int(skor * 100)})" if skor is not None else ""
        bildirim_metni = (
            f"🚨 [GRID UP ALARM] {modul_id} [{seviye_str}] (Önceki: {onceki_seviye}){skor_bilgisi}\n"
            f"   Olay ID: {anomali_id} | Zaman: {zaman}\n"
            f"   Gerekçe: {gerekce}"
        )
        logging.info(bildirim_metni)

        # Telegram bot yapılandırılmışsa Telegram'a ilet
        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            self._send_telegram(modul_id, seviye_str, onceki_seviye, gerekce, zaman, skor)

    def _send_telegram(self, modul_id, seviye, onceki_seviye, gerekce, zaman, skor):
        skor_satiri = f"📊 <b>Skor:</b> <code>%{int(skor * 100)}</code>\n" if skor is not None else ""
        mesaj = (
            f"🚨 <b>GRID UP ARIZA ALARMI ({seviye})</b>\n\n"
            f"📍 <b>Modül:</b> <code>{html.escape(modul_id)}</code>\n"
            f"📈 <b>Geçiş:</b> <code>{onceki_seviye} ➔ {seviye.lower()}</code>\n"
            f"⏱️ <b>Zaman:</b> <code>{html.escape(str(zaman))}</code>\n"
            f"{skor_satiri}"
            f"💡 <b>Tespit Gerekçesi:</b>\n<i>{html.escape(gerekce)}</i>\n\n"
            f"🔗 <i>Lütfen Operasyon Arayüzü üzerinden inceleyip onaylayınız.</i>"
        )
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": mesaj,
            "parse_mode": "HTML"
        }
        try:
            res = requests.post(url, json=payload, timeout=6)
            if res.status_code == 200:
                logging.info(f"✅ Telegram bildirimi başarıyla iletildi: {modul_id}")
            else:
                logging.error(f"❌ Telegram API Hatası: HTTP {res.status_code} - {res.text}")
        except Exception as e:
            logging.error(f"❌ Telegram Bağlantı Hatası: {e}")

    def poll_transitions(self):
        """GET /gecisler ucundan son işlenen id'den sonrasını sayfalar"""
        params = {"limit": 100}
        son_id = self.state.get("son_gecis_id")
        if son_id is not None:
            params["sonra"] = son_id

        url = f"{self.api_url}/gecisler"
        try:
            res = requests.get(url, params=params, timeout=5)
            if res.status_code != 200:
                logging.warning(f"⚠️ /gecisler HTTP {res.status_code} döndü: {res.text}")
                return

            govde = res.json()
            veriler = govde.get("veriler", [])
            for gecis in veriler:
                self.evaluate_transition(gecis)
                self.state["son_gecis_id"] = gecis["id"]

            if veriler:
                self.save_state()
                logging.debug(f"İşlenen geçiş sayısı: {len(veriler)}, güncel son_gecis_id: {self.state['son_gecis_id']}")

        except requests.exceptions.ConnectionError:
            logging.debug(f"🔌 API sunucusuna ulaşılamıyor ({url}). Yeniden denenecek...")
        except Exception as e:
            logging.error(f"Geçiş akışı sorgulama hatası: {e}")

def run_service():
    logging.info("🚀 Grid Up Alarm Servisi Başlatıldı.")
    logging.info(f"📡 API Hedefi: {API_URL}")
    logging.info(f"⏱️ Cooldown Süresi: {COOLDOWN_SECONDS} sn | Sorgu Aralığı: {POLL_INTERVAL} sn")
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        logging.info("📱 Telegram bildirim kanalı aktif.")
    else:
        logging.info("ℹ️ Telegram yapılandırılmadı (ortam değişkeni yok); alarmlar yerel konsola/loglara yazılacak.")

    manager = AlarmManager(api_url=API_URL, cooldown_seconds=COOLDOWN_SECONDS, state_file=STATE_FILE)

    while True:
        manager.poll_transitions()
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run_service()