# veri_okuma/ornek_kullanim.py
"""
Grid Up - Veri Okuma Paketi Örnek Kullanım Kılavuzu

Bu dosya, Grid Up sistemindeki ölçümleri kendi Python kodunuzda
nasıl okuyacağınızı gösterir.
"""

import sys
import os

# Üst dizini path'e ekle
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    reconfig_out = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfig_out):
        reconfig_out(encoding="utf-8")
except Exception:
    pass

from veri_okuma import ApiOlcumOkuyucu, DbOlcumOkuyucu, son_olcumler_api, son_olcumler_db


def ornek_1_api_ile_kolay_okuma():
    print("=== ÖRNEK 1: API Üzerinden Hızlı Ölçüm Okuma ===")
    modul = "TR041-P01-M1"
    olcumler = son_olcumler_api(modul)
    print(f"{modul} Anlık Ölçümler:")
    for tip, val in olcumler.items():
        print(f"  - {tip}: {val}")


def ornek_2_api_ile_detayli_okuma():
    print("\n=== ÖRNEK 2: API Nesnesi ile Detaylı ve Termal Okuma ===")
    api = ApiOlcumOkuyucu("http://localhost:8080")

    # 1. Modül Detayı
    detay = api.modul_detay("TR041-P01-M1")
    print(f"Modül: {detay.get('modul_id')}, Seviye: {detay.get('seviye')}, Besleme: {detay.get('besleme')}")

    # 2. Termal Özet
    termal = api.termal_son("TR041-P01-M1")
    print(f"Maks Sıcaklık: {termal.get('maks')} °C, Sıcak Nokta: {termal.get('maks_konum')}")

    # 3. Zaman Serisi
    seri = api.zaman_serisi("TR041-P01-M1", "akim_l1")
    print(f"L1 Akımı Geçmiş Nokta Sayısı: {len(seri.get('noktalar', []))}")


def ornek_3_db_ile_dogrudan_okuma():
    print("\n=== ÖRNEK 3: PostgreSQL Doğrudan SQL Okuma ===")
    try:
        db = DbOlcumOkuyucu()
        sonuc = db.son_olcumleri_getir("TR041-P01-M1")
        print(f"DB'den Okunan Son Zaman: {sonuc.get('son_zaman')}")
        for tip, info in sonuc.get("olcumler", {}).items():
            print(f"  - {tip}: {info['deger']} {info['birim']} ({info['kalite']})")
    except Exception as e:
        print("DB okuma hatası:", e)


if __name__ == "__main__":
    ornek_1_api_ile_kolay_okuma()
    ornek_2_api_ile_detayli_okuma()
    ornek_3_db_ile_dogrudan_okuma()
