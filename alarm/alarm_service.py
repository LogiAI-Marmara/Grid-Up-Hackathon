# alarm_service.py
"""
Grid Up Hackathon - İZ C: Telegram Alarm ve Bildirim Servisi
Sözleşme ③ anomali akışını dinler, anti-flapping (tekrar önleme) koruması uygular
ve Telegram Bot API üzerinden gerekçe odaklı acil bildirim iletir.
"""

import os
import sys
import time
import html
import logging
import requests
from datetime import datetime, timezone, timedelta

# Türkiye Saati (UTC+3)
TZ_TR = timezone(timedelta(hours=3))

def get_tr_time():
    return datetime.now(TZ_TR).strftime("%H:%M:%S")

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

# Ortam Değişkenleri veya Varsayılanlar
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8873044049:AAGinNH2GIrIcWAUh-pmviqWm16d_-nDB7I")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "659539927")
API_URL = os.getenv("API_URL", "http://localhost:8000/api/anomaliler")
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "300"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))

class AlarmManager:
    def __init__(self, cooldown_seconds=COOLDOWN_SECONDS):
        self.cooldown = cooldown_seconds
        self.last_alert_times = {}

    def process_anomalies(self, anomalies):
        """Gelen anomali listesini filtreler ve bildirim gönderimini değerlendirir"""
        if not isinstance(anomalies, list):
            return

        for anomaly in anomalies:
            seviye = str(anomaly.get("seviye", "")).lower()
            if seviye in ["uyari", "kritik"]:
                self._evaluate_and_send(anomaly)

    def _evaluate_and_send(self, anomaly):
        modul_id = anomaly.get("modul_id", "Bilinmeyen Modül")
        now = time.time()

        # Anti-flapping (Tekrar Önleme) Mekanizması
        if modul_id in self.last_alert_times:
            gecen_sure = now - self.last_alert_times[modul_id]
            if gecen_sure < self.cooldown:
                kalan_sure = int(self.cooldown - gecen_sure)
                logging.info(f"⏳ [ANTI-FLAPPING] {modul_id} bekleme süresinde (Kalan: {kalan_sure} sn). Bildirim atlandı.")
                return

        basarili = self.send_telegram_notification(anomaly)
        if basarili:
            self.last_alert_times[modul_id] = now

    def send_telegram_notification(self, anomaly):
        """Telegram Bot API sendMessage uç noktasına HTML formatlı acil durum mesajı yollar"""
        seviye = str(anomaly.get("seviye", "BILINMIYOR")).upper()
        modul_id = html.escape(str(anomaly.get("modul_id", "Bilinmeyen Modül")))
        gerekce = html.escape(str(anomaly.get("gerekce", "Gerekçe belirtilmedi.")))
        zaman = html.escape(str(anomaly.get("zaman", get_tr_time())))
        skor = anomaly.get("skor", None)


        skor_satiri = f"📊 <b>Anomali Skoru:</b> <code>%{int(skor * 100)}</code>\n" if skor is not None else ""

        mesaj = (
            f"🚨 <b>GRID UP ARIZA ALARMI ({seviye})</b>\n\n"
            f"📍 <b>Modül:</b> <code>{modul_id}</code>\n"
            f"⏱️ <b>Tespit Zamanı:</b> <code>{zaman}</code>\n"
            f"{skor_satiri}"
            f"💡 <b>Tespit Gerekçesi:</b>\n<i>{gerekce}</i>\n\n"
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
                logging.info(f"✅ Telegram bildirimi başarıyla iletildi: {modul_id} [{seviye}]")
                return True
            else:
                logging.error(f"❌ Telegram API Hatası: HTTP {res.status_code} - {res.text}")
                return False
        except requests.exceptions.RequestException as e:
            logging.error(f"❌ Telegram Bağlantı Hatası: {e}")
            return False

def run_service():
    manager = AlarmManager(cooldown_seconds=COOLDOWN_SECONDS)
    logging.info(f"🚀 Grid Up Alarm Servisi Başlatıldı.")
    logging.info(f"📡 Hedef API: {API_URL}")
    logging.info(f"⏱️ Anti-Flapping Cooldown: {COOLDOWN_SECONDS} saniye")

    while True:
        try:
            res = requests.get(API_URL, timeout=4)
            if res.status_code == 200:
                anomaliler = res.json()
                manager.process_anomalies(anomaliler)
            else:
                logging.warning(f"⚠️ API beklenmeyen HTTP kodu döndü: {res.status_code}")
        except requests.exceptions.ConnectionError:
            logging.debug(f"🔌 API sunucusuna ulaşılamıyor ({API_URL}). Yeniden denenecek...")
        except Exception as e:
            logging.error(f"Beklenmeyen Hata: {e}")

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run_service()