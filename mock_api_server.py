# mock_api_server.py
"""
Grid Up Hackathon - İZ C: Monitoring Arayüzü ve Mock API Sunucusu
Port: 8000
Sözleşme ③, ④ ve ⑤ ile tam uyumlu REST API ve Arayüz Sunucusu
"""

import os
import sys
import mimetypes
import json
import random
import time
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# Türkiye Saati (UTC+3) Tanımı
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


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARAYUZ_DIR = os.path.join(BASE_DIR, "arayuz")

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Eşzamanlı gelen isteklerin birbirini kilitlemesini önleyen çoklu iş parçacıklı sunucu"""
    daemon_threads = True

AKTIF_ANOMALILER = [
    {
        "id": "an_00412",
        "modul_id": "TR041-P01-M1",
        "zaman": get_tr_time(),
        "skor": 0.89,
        "seviye": "uyari",
        "tip": "sicak_nokta",
        "gerekce": "L2 çıkış klemensi 34 dk içinde +18 °C yükseldi, akım sabit kaldı."
    }
]


SAHA_HIYERARSISI = [
    {
        "saha_id": "TR041 (Konak Trafo Merkezi)",
        "panolar": [
            {
                "pano_id": "TR041-P01 (Ana Dağıtım Hücresi)",
                "moduller": [
                    { "modul_id": "TR041-P01-M1", "durum": "uyari", "isim": "Giriş Fideri Modülü" },
                    { "modul_id": "TR041-P01-M2", "durum": "normal", "isim": "Çıkış Fideri Modülü" }
                ]
            },
            {
                "pano_id": "TR041-P02 (Kompansasyon Hücresi)",
                "moduller": [
                    { "modul_id": "TR041-P02-M1", "durum": "normal", "isim": "Kondansatör Grubu 1" }
                ]
            }
        ]
    }
]

class MockServerHandler(BaseHTTPRequestHandler):
    def _send_response_data(self, status_code, content_type, data_bytes):
        """Content-Length ve CORS başlıklarını ekleyerek yanıt gönderici"""
        try:
            self.send_response(status_code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data_bytes)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(data_bytes)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass

    def do_OPTIONS(self):
        self._send_response_data(200, 'text/plain', b'')

    def do_GET(self):
        global AKTIF_ANOMALILER

        clean_path = self.path.split('?')[0]

        # 1. API - Saha Hiyerarşisi (Sözleşme ⑤)
        if clean_path == '/api/sahalar':
            # Güncel anomali durumlarını modüllere yansıt
            aktif_uyarilar = {a['modul_id']: a['seviye'] for a in AKTIF_ANOMALILER}
            kopya_sahalar = json.loads(json.dumps(SAHA_HIYERARSISI))
            for saha in kopya_sahalar:
                for pano in saha['panolar']:
                    for modul in pano['moduller']:
                        if modul['modul_id'] in aktif_uyarilar:
                            modul['durum'] = aktif_uyarilar[modul['modul_id']]
                        else:
                            modul['durum'] = 'normal'
            body = json.dumps(kopya_sahalar, ensure_ascii=False).encode('utf-8')
            self._send_response_data(200, 'application/json; charset=utf-8', body)
            return

        # 2. API - Modül Detayları & Termal Veri (Sözleşme ④ ve ⑤)
        elif clean_path.startswith('/api/moduller/'):
            modul_id = clean_path.split('/')[-1]
            anomali_var = any(a['modul_id'] == modul_id for a in AKTIF_ANOMALILER)

            if "M2" in modul_id or not anomali_var:
                # Normal çalışan modül simülasyonu
                termal_kare = [round(random.uniform(25.0, 31.5), 1) for _ in range(768)]
                maks_t = max(termal_kare)
                maks_idx = termal_kare.index(maks_t)
                hx, hy = maks_idx % 32, maks_idx // 32
                akim_l1 = round(random.uniform(119.5, 121.5), 1)
                akim_l2 = round(random.uniform(120.0, 122.0), 1)
                akim_l3 = round(random.uniform(119.0, 121.0), 1)
                akim_notr = round(random.uniform(0.5, 1.2), 1)
                seviye = "normal"
                ark_olay = 0
                ortam_t = round(random.uniform(28.0, 30.5), 1)
                nem = round(random.uniform(40.0, 45.0), 1)
            else:
                # Anomali / Aşırı ısınma simülasyonu (M1 veya anomali içeren modül)
                termal_kare = [round(random.uniform(26.0, 34.0), 1) for _ in range(768)]
                hx, hy = 14, 10
                h_idx = hy * 32 + hx
                # Sıcak nokta çekirdeği ve çevresi
                termal_kare[h_idx] = 83.5
                if h_idx + 1 < 768: termal_kare[h_idx + 1] = 76.2
                if h_idx - 1 >= 0: termal_kare[h_idx - 1] = 73.8
                if h_idx + 32 < 768: termal_kare[h_idx + 32] = 72.1
                if h_idx - 32 >= 0: termal_kare[h_idx - 32] = 70.4
                maks_t = 83.5
                akim_l1 = 120.5
                akim_l2 = 159.4  # Aşırı akım / klemenste aşırı yük
                akim_l3 = 119.8
                akim_notr = 2.4
                seviye = "uyari"
                ark_olay = 0
                ortam_t = 34.7
                nem = 45.0

            payload = {
                "modul_id": modul_id,
                "zaman": get_tr_time(),
                "ortam_sicaklik": ortam_t,

                "nem": nem,
                "akim_l1": akim_l1,
                "akim_l2": akim_l2,
                "akim_l3": akim_l3,
                "akim_notr": akim_notr,
                "besleme": "sebeke",
                "sinyal": -72,
                "ark_olay": ark_olay,
                "seviye": seviye,
                "termal_ozet": {
                    "maks": maks_t,
                    "maks_konum": [hx, hy],
                    "ort": round(sum(termal_kare) / len(termal_kare), 1)
                },
                "termal_kare": termal_kare
            }
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self._send_response_data(200, 'application/json; charset=utf-8', body)
            return

        # 3. API - Anomali Listesi (Sözleşme ③)
        elif clean_path == '/api/anomaliler':
            body = json.dumps(AKTIF_ANOMALILER, ensure_ascii=False).encode('utf-8')
            self._send_response_data(200, 'application/json; charset=utf-8', body)
            return

        # 4. Statik Dosyalar (arayuz/ klasöründen servis)
        file_path = None
        if clean_path in ('/', '/index.html'):
            file_path = os.path.join(ARAYUZ_DIR, 'index.html')
        elif clean_path.endswith(('.js', '.css', '.html', '.svg', '.png', '.ico')):
            potential_path = os.path.join(ARAYUZ_DIR, clean_path.lstrip('/'))
            if os.path.isfile(potential_path):
                file_path = potential_path

        if file_path and os.path.isfile(file_path):
            mime_type, _ = mimetypes.guess_type(file_path)
            content_type = mime_type or 'text/plain'
            if 'text' in content_type or 'javascript' in content_type:
                content_type += '; charset=utf-8'
            with open(file_path, 'rb') as f:
                content = f.read()
            self._send_response_data(200, content_type, content)
            return

        self._send_response_data(404, 'text/plain; charset=utf-8', b'404 Not Found')

    def do_POST(self):
        global AKTIF_ANOMALILER
        clean_path = self.path.split('?')[0]

        # Operatör Onayı Akışı: POST /api/anomaliler/{id}/onayla
        if '/onayla' in clean_path:
            parcalar = clean_path.strip('/').split('/')
            if len(parcalar) >= 3:
                alarm_id = parcalar[2]
                onaylananlar = [a for a in AKTIF_ANOMALILER if a.get('id') == alarm_id]
                AKTIF_ANOMALILER = [a for a in AKTIF_ANOMALILER if a.get('id') != alarm_id]

                resp = {
                    "status": "basarili",
                    "mesaj": f"Alarm {alarm_id} operatör tarafından onaylandı ve kapatıldı.",
                    "onaylanan": onaylananlar[0] if onaylananlar else None,
                    "kalan_aktif_alarm": len(AKTIF_ANOMALILER)
                }
                body = json.dumps(resp, ensure_ascii=False).encode('utf-8')
                self._send_response_data(200, 'application/json; charset=utf-8', body)
                return

        self._send_response_data(400, 'text/plain; charset=utf-8', b'Bad Request')

if __name__ == "__main__":
    server = ThreadedHTTPServer(('0.0.0.0', 8000), MockServerHandler)
    print("🚀 Mock API & Dashboard Başlatıldı: http://localhost:8000")
    print("📂 Arayüz Klasörü Servis Ediliyor:", ARAYUZ_DIR)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Sunucu durduruldu.")
        server.server_close()