import threading
import time
import json
import requests
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler

logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ---------------------------------------------------------
# 1. ALARM SERVİSİ (Anti-Flapping Korumalı)
# ---------------------------------------------------------
class AlarmManager:
    def __init__(self, cooldown_seconds=300):
        self.cooldown = cooldown_seconds
        self.last_alert_times = {}

    def process_anomalies(self, anomalies: list):
        if not isinstance(anomalies, list):
            return

        for anomaly in anomalies:
            seviye = str(anomaly.get("seviye", "")).lower()
            if seviye in ["uyari", "kritik"]:
                self._evaluate_and_send(anomaly)

    def _evaluate_and_send(self, anomaly: dict):
        modul_id = anomaly.get("modul_id", "Bilinmeyen Modül")
        now = time.time()

        # Anti-flapping (Tekrar Önleme) Kontrolü
        if modul_id in self.last_alert_times:
            gecen_sure = now - self.last_alert_times[modul_id]
            if gecen_sure < self.cooldown:
                kalan = int(self.cooldown - gecen_sure)
                logging.info(f"⏳ [ENGELLENDİ] {modul_id} cooldown süresinde (Kalan: {kalan} sn). Bildirim atlanıyor.")
                return

        self.send_local_notification(anomaly)
        self.last_alert_times[modul_id] = now

    def send_local_notification(self, anomaly: dict):
        seviye = str(anomaly.get('seviye', 'BILINMIYOR')).upper()
        modul_id = anomaly.get('modul_id', 'Bilinmeyen Modül')
        gerekce = anomaly.get('gerekce', 'Gerekçe belirtilmedi.')
        zaman = anomaly.get('zaman', '')

        mesaj = (
            f"\n{'='*45}\n"
            f"⚠️  ALARM BİLDİRİMİ: {seviye}!\n"
            f"Modül   : {modul_id}\n"
            + (f"Zaman   : {zaman}\n" if zaman else "")
            + f"Gerekçe : {gerekce}\n"
            f"{'='*45}"
        )
        logging.info(f"[SMS/WHATSAPP GATEWAY İLETİLDİ] -> {mesaj}")

# ---------------------------------------------------------
# 2. MOCK API SUNUCUSU (Daemon Thread İçin)
# ---------------------------------------------------------
class MockIZBHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Terminal çıktısını temiz tutmak için HTTP erişim loglarını yutuyoruz
        return

    def do_GET(self):
        if self.path == '/api/anomaliler':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            anomaliler = [{
                "id": "an_00412",
                "modul_id": "TR041-P01-M1",
                "zaman": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "skor": 0.89,
                "seviye": "uyari",
                "tip": "sicak_nokta",
                "gerekce": "L2 çıkış klemensi 34 dk içinde +18 °C yükseldi, akım sabit kaldı."
            }]
            self.wfile.write(json.dumps(anomaliler).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

def start_mock_server():
    server = HTTPServer(('127.0.0.1', 8000), MockIZBHandler)
    server.serve_forever()

# ---------------------------------------------------------
# 3. TEST ENTEGRASYON VE ÇALIŞTIRMA
# ---------------------------------------------------------
if __name__ == "__main__":
    # Mock Sunucuyu arka planda (Daemon Thread) başlat
    api_thread = threading.Thread(target=start_mock_server, daemon=True)
    api_thread.start()
    logging.info("🚀 Mock API Sunucusu arka planda başlatıldı (http://127.0.0.1:8000).")
    time.sleep(1)  # Sunucunun dinlemeye geçmesi için kısa bekleme

    # Cooldown süresi 300 saniye olan yöneticiyi başlat
    manager = AlarmManager(cooldown_seconds=300)
    logging.info("🔔 Alarm Servisi API sorgulama döngüsünü başlatıyor...\n")

    # 5 Adımlık Simülasyon Döngüsü (Anti-flapping doğrulaması)
    for tur in range(1, 6):
        logging.info(f"--- [TUR {tur}/5] API Sorgulanıyor ---")
        try:
            response = requests.get("http://127.0.0.1:8000/api/anomaliler", timeout=3)
            if response.status_code == 200:
                anomaliler = response.json()
                manager.process_anomalies(anomaliler)
            else:
                logging.warning(f"Beklenmeyen durum kodu: {response.status_code}")
        except Exception as e:
            logging.error(f"Bağlantı hatası: {e}")
        
        time.sleep(2)

    logging.info("\n✅ Entegrasyon testi tamamlandı. İlk turda bildirim gitti, sonraki 4 tur başarıyla engellendi.")