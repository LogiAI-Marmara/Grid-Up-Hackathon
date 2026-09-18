# kodlar/deploy/sim_streamer.py
"""
Grid Up - Canlı Gerçek Zamanlı Simülasyon Akışçısı (Live Real-Time Streamer)
Sözleşme ① paketlerini gerçek zamanlı olarak (sistem UTC saati ile) üretip
Toplama Servisi'ne (POST /paket) iletir.

Bu sayede:
1. Zaman damgası geçmişte (2024 vb.) kalmaz; her an güncel UTC zamanı kullanılır.
2. "Modülden 18 dakikadır ölçüm gelmiyor" veya saat kayması dedektör uyarısı oluşmaz.
3. Arayüzde ve veritabanında kesintisiz, canlı veri akışı sağlanır.
"""

import os
import sys
import time
import random
import logging
from datetime import datetime, timezone, timedelta
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(message)s"
)

TOPLAMA_URL = os.getenv("TOPLAMA_URL", "http://toplama:8000/paket")
MODUL_SAYISI = int(os.getenv("SIM_MODUL_SAYISI", "10"))
ARALIK_SN = float(os.getenv("SIM_ARALIK_SN", "3.0"))
SENARYO_AD = os.getenv("SIM_SENARYO", "").strip() or None
TOHUM = int(os.getenv("SIM_TOHUM", "20260914"))

# Gerekli PYTHONPATH yapılandırması
repo_kok = os.environ.get(
    "REPO_KOK",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "repo", "Grid-Up-Hackathon"))
)
if os.path.exists(os.path.join(repo_kok, "modul-sim")):
    sys.path.insert(0, os.path.join(repo_kok, "modul-sim"))
if os.path.exists(repo_kok):
    sys.path.insert(0, repo_kok)

try:
    from modul_sim.ayar import topoloji
    from modul_sim.fizik import Hava
    from modul_sim.modul import Modul
    from modul_sim.runner import PaylasilanHava
    from modul_sim.senaryo import senaryo_olustur
except ImportError as e:
    logging.error(f"modul_sim kütüphanesi içe aktarılamadı: {e}. sys.path={sys.path}")
    raise


def toplama_bekle(url: str, azami_sn: int = 60) -> bool:
    """Toplama servisinin /saglik ucunun 200 dönmesini bekler."""
    saglik_url = url.rsplit("/", 1)[0] + "/saglik"
    logging.info(f"⏳ Toplama servisi kontrol ediliyor: {saglik_url}")
    baslangic = time.time()
    while time.time() - baslangic < azami_sn:
        try:
            r = requests.get(saglik_url, timeout=3)
            if r.status_code == 200:
                logging.info("✅ Toplama servisi hazır ve yanıt veriyor.")
                return True
        except Exception:
            pass
        time.sleep(2)
    logging.warning("⚠️ Toplama servisi yanıt vermedi, doğrudan gönderim denenecek.")
    return False


def filo_hazirla(modul_sayisi: int, tohum: int, senaryo_ad: str | None = None):
    """Canlı simülasyon için modül filosunu başlatır."""
    sahalar = topoloji(modul_sayisi, tohum)
    simdi = datetime.now(timezone.utc).replace(microsecond=0)
    moduller = []

    for saha in sahalar:
        hava = PaylasilanHava(Hava(saha.hava, random.Random(saha.tohum ^ 0xC0FFEE)))
        for m_ayar in saha.modul_ayarlari:
            senaryo = senaryo_olustur(senaryo_ad) if senaryo_ad else None
            modul = Modul(
                m_ayar,
                hava,
                baslangic=simdi,
                senaryo=senaryo
            )
            moduller.append(modul)

    logging.info(f"🛰️ Toplam {len(moduller)} modül canlı simülasyona hazırlandı.")
    return moduller


def main():
    logging.info("==================================================")
    logging.info("🚀 GRID UP CANLI MODÜL SİMÜLATÖRÜ BAŞLATILIYOR")
    logging.info(f"📍 Hedef: {TOPLAMA_URL}")
    logging.info(f"📊 Modül Sayısı: {MODUL_SAYISI}, Örnekleme Aralığı: {ARALIK_SN} sn")
    if SENARYO_AD:
        logging.info(f"⚠️ Aktif Senaryo: {SENARYO_AD}")
    logging.info("==================================================")

    toplama_bekle(TOPLAMA_URL)
    moduller = filo_hazirla(MODUL_SAYISI, TOHUM, SENARYO_AD)

    session = requests.Session()
    gonderilen_toplam = 0
    hata_sayisi = 0

    while True:
        try:
            # Her döngüde güncel gerçek dünya UTC zamanı kullanılır
            an = datetime.now(timezone.utc).replace(microsecond=0)

            for modul in moduller:
                uretilen = modul.ilerle(an)
                paket = uretilen.paket

                try:
                    res = session.post(
                        TOPLAMA_URL,
                        json=paket,
                        headers={"Content-Type": "application/json"},
                        timeout=5
                    )
                    if res.status_code in (200, 201):
                        gonderilen_toplam += 1
                    else:
                        logging.warning(f"Toplama reddetti HTTP {res.status_code}: {res.text[:120]}")
                        hata_sayisi += 1
                except Exception as ex:
                    hata_sayisi += 1
                    logging.error(f"Paket gönderme hatası ({modul.modul_id}): {ex}")

            if gonderilen_toplam % (len(moduller) * 5) == 0:
                tr_zaman = datetime.now(timezone(timedelta(hours=3))).strftime("%Y-%m-%d %H:%M:%S")
                logging.info(
                    f"📡 Akış devam ediyor: {gonderilen_toplam} paket başarıyla iletildi "
                    f"(Son Zaman: {tr_zaman} TSİ, Hata: {hata_sayisi})"
                )

            time.sleep(ARALIK_SN)

        except KeyboardInterrupt:
            logging.info("🛑 Simülatör kullanıcı tarafından durduruldu.")
            break
        except Exception as e:
            logging.error(f"Döngü hatası: {e}")
            time.sleep(ARALIK_SN)


if __name__ == "__main__":
    main()
