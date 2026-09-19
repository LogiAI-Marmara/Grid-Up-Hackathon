#!/usr/bin/env python3
# entegrasyon_testi.py
"""Alarm servisinin süreç düzeyinde yeniden başlatma testi (A-01 + A-04).

Birim testleri `AlarmManager`'ı bellekte yeniden kurar; bu betik servisi
gerçekten ayrı bir süreç olarak başlatır, öldürür ve yeniden başlatır.
Aradaki fark önemli: durum dosyasının gerçekten diske inip inmediğini,
gerçek HTTP istemcisinin gerçek bir uca konuşup konuşmadığını ve
yeniden başlatmanın bekleyen alarmı sürdürüp sürdürmediğini yalnız bu
gösterir.

Sahte olan ne: `/gecisler` ve `/anomaliler/{id}` uçları ile SMS gateway.
Gerçek olan ne: alarm servisi süreci, HTTP taşıma, durum dosyası, yeniden
başlatma. Hiçbir aşamada gerçek bir telefona SMS gitmez — bu betiğin
"teslim edildi" dediği şey, sahte gateway'in isteği kabul etmesidir.

Konteyner düzeyi (docker compose down/up ile volume kalıcılığı) BU BETİĞİN
KAPSAMINDA DEĞİLDİR; README'deki "Konteyner kabul testi" bölümüne bakın.

Çalıştırma:  python3 entegrasyon_testi.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BURASI = os.path.dirname(os.path.abspath(__file__))

# Paylaşılan sahte durum
_kilit = threading.Lock()
GECISLER = [
    {
        "id": 101,
        "anomali_id": "an_kritik_1",
        "alan": "seviye",
        "onceki": "uyari",
        "yeni": "kritik",
        "zaman": "2026-09-19T12:00:00Z",
        "aktor": "tarama",
    }
]
SMS_KABUL_ET = False
SMS_TESLIMLERI = []


class Uc(BaseHTTPRequestHandler):
    def _json(self, kod, govde):
        ham = json.dumps(govde).encode("utf-8")
        self.send_response(kod)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(ham)))
        self.end_headers()
        self.wfile.write(ham)

    def do_GET(self):
        yol = self.path.split("?")[0]
        if yol == "/gecisler":
            sonra = None
            if "sonra=" in self.path:
                sonra = int(self.path.split("sonra=")[1].split("&")[0])
            with _kilit:
                veriler = [g for g in GECISLER if sonra is None or g["id"] > sonra]
            return self._json(
                200,
                {
                    "veriler": veriler,
                    "sonraki": veriler[-1]["id"] if veriler else None,
                    "limit": 100,
                },
            )
        if yol.startswith("/anomaliler/"):
            return self._json(
                200,
                {
                    "id": yol.rsplit("/", 1)[-1],
                    "modul_id": "TR041-P01-M1",
                    "gerekce": "L2 klemensi 3 penceredir komşularından 18 K sıcak.",
                    "skor": 0.93,
                },
            )
        return self._json(404, {"hata": "yok"})

    def do_POST(self):
        if self.path == "/sms":
            uzunluk = int(self.headers.get("Content-Length", 0))
            govde = json.loads(self.rfile.read(uzunluk) or b"{}")
            with _kilit:
                kabul = SMS_KABUL_ET
                if kabul:
                    SMS_TESLIMLERI.append(govde)
            if not kabul:
                return self._json(500, {"hata": "gateway kapalı"})
            return self._json(202, {"durum": "kuyruğa alındı"})
        return self._json(404, {"hata": "yok"})

    def log_message(self, *a):
        pass


def servisi_calistir(durum_yolu, port, saniye):
    """Alarm servisini gerçek bir süreç olarak `saniye` kadar çalıştırır."""
    ortam = dict(os.environ)
    ortam.update(
        {
            "API_URL": f"http://127.0.0.1:{port}",
            "ALARM_STATE_FILE": durum_yolu,
            "POLL_INTERVAL": "1",
            "COOLDOWN_SECONDS": "300",
            "ALARM_YENIDEN_DENEME_TABAN": "1",
            "ALARM_YENIDEN_DENEME_TAVAN": "2",
            "ALARM_KANAL_KURALI": "uyari:konsol,sms|kritik:konsol,sms!",
            "SMS_GATEWAY_URL": f"http://127.0.0.1:{port}/sms",
            "SMS_ALICILAR": "+905551112233",
            "TELEGRAM_BOT_TOKEN": "",
            "TELEGRAM_CHAT_ID": "",
            "PYTHONUNBUFFERED": "1",
        }
    )
    surec = subprocess.Popen(
        [sys.executable, os.path.join(BURASI, "alarm_service.py")],
        env=ortam,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    time.sleep(saniye)
    surec.terminate()
    try:
        cikti, _ = surec.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        surec.kill()
        cikti, _ = surec.communicate()
    return cikti


def bekle(kosul, zaman_asimi=10.0):
    bitis = time.time() + zaman_asimi
    while time.time() < bitis:
        if kosul():
            return True
        time.sleep(0.1)
    return False


def main() -> int:
    global SMS_KABUL_ET

    sunucu = ThreadingHTTPServer(("127.0.0.1", 0), Uc)
    port = sunucu.server_address[1]
    threading.Thread(target=sunucu.serve_forever, daemon=True).start()

    dizin = tempfile.mkdtemp(prefix="alarm-entegrasyon-")
    durum_yolu = os.path.join(dizin, "alarm_state.json")
    hatalar = []

    def kontrol(ad, kosul, ayrinti=""):
        if kosul:
            print(f"  ✅ {ad}")
        else:
            print(f"  ❌ {ad} {ayrinti}")
            hatalar.append(ad)

    try:
        # --- Aşama 1: gateway kapalı. Alarm teslim edilemez, kaybolmaz. -----
        print("\n[1] Gateway KAPALI iken kritik geçiş geliyor")
        with _kilit:
            SMS_KABUL_ET = False
        servisi_calistir(durum_yolu, port, 4)

        kontrol("durum dosyası yazıldı", os.path.exists(durum_yolu))
        durum = json.load(open(durum_yolu, encoding="utf-8"))
        kontrol("hiçbir SMS teslim edilmedi", len(SMS_TESLIMLERI) == 0, SMS_TESLIMLERI)
        kontrol("geçiş bekleyen kuyruğunda", "101" in durum.get("bekleyen", {}), durum)
        kontrol("teslim/cooldown iddia edilmedi", durum.get("son_bildirim") == {}, durum)

        # --- Aşama 2: süreç yeniden başlar, gateway açılır. ------------------
        print("\n[2] Servis yeniden başlatıldı, gateway AÇIK")
        with _kilit:
            SMS_KABUL_ET = True
        servisi_calistir(durum_yolu, port, 6)

        kontrol(
            "bekleyen alarm yeniden başlatmadan sonra teslim edildi",
            len(SMS_TESLIMLERI) == 1,
            SMS_TESLIMLERI,
        )
        if SMS_TESLIMLERI:
            metin = json.dumps(SMS_TESLIMLERI[0], ensure_ascii=False)
            kontrol("mesaj modül kimliğini taşıyor", "TR041-P01-M1" in metin, metin)
            kontrol("mesaj seviyeyi taşıyor", "KRITIK" in metin, metin)
        durum = json.load(open(durum_yolu, encoding="utf-8"))
        kontrol("bekleyen kuyruğu boşaldı", durum.get("bekleyen") == {}, durum)
        kontrol("cooldown kaydı oluştu", len(durum.get("son_bildirim", {})) == 1, durum)

        # --- Aşama 3: üçüncü başlatma tekrar bildirim üretmemeli. -----------
        print("\n[3] Servis bir kez daha yeniden başlatıldı (tekrar olmamalı)")
        servisi_calistir(durum_yolu, port, 4)
        kontrol(
            "yeniden başlatma aynı geçişi tekrar bildirmedi",
            len(SMS_TESLIMLERI) == 1,
            SMS_TESLIMLERI,
        )

        # --- Aşama 4: aynı modülde ikinci, ayrı anomali bastırılmamalı. -----
        print("\n[4] Aynı modülde ikinci anomali (cooldown içinde) — bastırılmamalı")
        with _kilit:
            GECISLER.append(
                {
                    "id": 102,
                    "anomali_id": "an_kritik_2",
                    "alan": "seviye",
                    "onceki": "izle",
                    "yeni": "kritik",
                    "zaman": "2026-09-19T12:01:00Z",
                    "aktor": "tarama",
                }
            )
        servisi_calistir(durum_yolu, port, 4)
        kontrol(
            "ayrı anomali ayrı bildirildi", len(SMS_TESLIMLERI) == 2, SMS_TESLIMLERI
        )
    finally:
        sunucu.shutdown()

    print()
    if hatalar:
        print(f"SONUÇ: BAŞARISIZ — {len(hatalar)} kontrol geçmedi: {hatalar}")
        return 1
    print("SONUÇ: BAŞARILI — tüm süreç düzeyi kontroller geçti.")
    print(
        "NOT: SMS yalnız sahte gateway tarafından kabul edildi; gerçek bir SIM'den\n"
        "     gerçek bir telefona teslim DOĞRULANMADI."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
