# kodlar/veri_okuma/cli.py
"""
Grid Up - Komut Satırı Veri Okuma Aracı (CLI)
Terminalden ölçüm verilerini, termal özetleri ve zaman serilerini
hızlıca sorgulamak ve görüntülemek için kullanılır.
"""

from __future__ import annotations
import sys
import json
import argparse
from datetime import datetime, timezone, timedelta
from typing import Optional

# Windows konsol UTF-8 desteği
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Türkiye Saati (Europe/Istanbul - UTC+3)
TZ_TR = timezone(timedelta(hours=3))

def tr_zaman(val) -> str:
    """ISO formatındaki UTC zamanı Türkiye Saatine (TSİ, UTC+3) çevirir."""
    if not val:
        return "-"
    if isinstance(val, datetime):
        return val.astimezone(TZ_TR).strftime("%Y-%m-%d %H:%M:%S (TSİ)")
    try:
        s = str(val).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt.astimezone(TZ_TR).strftime("%Y-%m-%d %H:%M:%S (TSİ)")
    except Exception:
        return str(val).replace("T", " ").replace("Z", "")

from .api_okuyucu import ApiOlcumOkuyucu
from .db_okuyucu import DbOlcumOkuyucu


def ascii_isi_haritasi(pikseller: list[float], genislik: int = 32, yukseklik: int = 24) -> str:
    """768 piksellik termal matrisi terminalde mini bir ASCII harita olarak gösterir."""
    if not pikseller or len(pikseller) < genislik * yukseklik:
        return "Yetersiz piksel verisi"

    min_t = min(pikseller)
    max_t = max(pikseller)
    fark = max_t - min_t or 1.0

    karakterler = " .:-=+*#%@"
    satirlar = []
    for y in range(0, yukseklik, 2):  # Terminal boyutu için her 2 satırda bir
        satir = ""
        for x in range(genislik):
            t = pikseller[y * genislik + x]
            norm = (t - min_t) / fark
            idx = int(norm * (len(karakterler) - 1))
            satir += karakterler[max(0, min(len(karakterler) - 1, idx))]
        satirlar.append(satir)
    return "\n".join(satirlar)


def calistir(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="veri_oku",
        description="Grid Up - Ölçüm ve Sensör Verisi Okuma Aracı"
    )
    parser.add_argument("--modul", "-m", help="Sorgulanacak modül ID'si (Örn: TR041-P01-M1)")
    parser.add_argument("--kaynak", choices=["api", "db"], default="api", help="Veri kaynağı: 'api' (varsayılan port 8080) veya 'db' (PostgreSQL)")
    parser.add_argument("--api-url", default="http://localhost:8080", help="API temel adresi")
    parser.add_argument("--dsn", default=None, help="PostgreSQL bağlantı dizesi (DSN)")
    parser.add_argument("--listele", "-l", action="store_true", help="Tüm kayıtlı modülleri listeler")
    parser.add_argument("--seri", "-s", help="Zaman serisi ölçüm tipi (Örn: akim_l1, ortam_sicaklik, nem)")
    parser.add_argument("--limit", type=int, default=10, help="Zaman serisi için kayıt limiti (varsayılan: 10)")
    parser.add_argument("--termal", "-t", action="store_true", help="Son termal kamera özetini ve matrisini göster")
    parser.add_argument("--json", "-j", action="store_true", help="Çıktıyı JSON formatında ver")

    args = parser.parse_args(argv)

    if args.kaynak == "api":
        api = ApiOlcumOkuyucu(api_url=args.api_url)
    else:
        db = DbOlcumOkuyucu(dsn=args.dsn)

    # 1. Modül Listesi
    if args.listele:
        if args.kaynak == "api":
            moduller = api.moduller()
        else:
            moduller = db.modulleri_getir()

        if args.json:
            print(json.dumps(moduller, ensure_ascii=False, indent=2))
            return 0

        print(f"\n📡 KAYITLI MODÜLLER ({len(moduller)} Adet)")
        print("-" * 75)
        print(f"{'MODÜL ID':<18} | {'SAHA':<8} | {'PANO':<8} | {'DURUM/SEVİYE':<15} | {'SON GÖRÜLME'}")
        print("-" * 75)
        for m in moduller:
            mid = m.get("modul_id", "-")
            saha = m.get("saha_kodu", "-")
            pano = m.get("pano_kodu", "-")
            seviye = m.get("seviye") or m.get("durum") or ("Aktif" if m.get("aktif") else "Pasif")
            son = tr_zaman(m.get("son_gorulme") or m.get("guncellendi"))
            print(f"{mid:<18} | {saha:<8} | {pano:<8} | {str(seviye).upper():<15} | {son}")
        print("-" * 75)
        return 0

    if not args.modul:
        print("Lütfen sorgulamak için bir modül belirtin (--modul TR041-P01-M1) veya listelemek için --listele kullanın.")
        return 1

    # 2. Termal Sorgulama
    if args.termal:
        if args.kaynak == "api":
            ozet = api.termal_son(args.modul)
            kare_id = ozet.get("kare_id")
            kare = api.termal_kare(kare_id) if kare_id else {}
            pikseller = kare.get("piksel_verisi") or []
        else:
            kare = db.termal_kare_getir(modul_id=args.modul)
            ozet = kare or {}
            pikseller = kare.get("pikseller") if kare else []

        if args.json:
            print(json.dumps({"ozet": ozet, "pikseller": pikseller}, ensure_ascii=False, indent=2))
            return 0

        print(f"\n🌡️ TERMAL KAMERA SONUCU: {args.modul}")
        print("-" * 60)
        print(f"Zaman        : {tr_zaman(ozet.get('zaman'))}")
        print(f"Maks Sıcaklık: {ozet.get('maks', ozet.get('istatistik', {}).get('maks', '-'))} °C")
        if "maks_konum" in ozet:
            print(f"Sıcak Nokta  : X={ozet['maks_konum'][0]}, Y={ozet['maks_konum'][1]}")
        if "bolge_ort" in ozet:
            print(f"Bölge Ort.   : {ozet['bolge_ort']} °C")

        if pikseller:
            print("\n📸 ASCII Termal Isı Haritası (32x24):")
            print("-" * 34)
            print(ascii_isi_haritasi(pikseller))
            print("-" * 34)
        return 0

    # 3. Zaman Serisi
    if args.seri:
        if args.kaynak == "api":
            seri_veri = api.zaman_serisi(args.modul, args.seri)
            noktalar = seri_veri.get("noktalar", [])[:args.limit]
        else:
            noktalar = db.zaman_serisi_getir(args.modul, args.seri, limit=args.limit)

        if args.json:
            print(json.dumps(noktalar, ensure_ascii=False, indent=2, default=str))
            return 0

        print(f"\n📈 ZAMAN SERİSİ: {args.modul} -> {args.seri} (Son {len(noktalar)} Kayıt)")
        print("-" * 55)
        print(f"{'ZAMAN':<25} | {'DEĞER':<10} | {'BİRİM':<6} | {'KALİTE'}")
        print("-" * 55)
        for n in noktalar:
            zaman = tr_zaman(n.get("zaman"))
            deger = n.get("deger", "-")
            birim = n.get("birim", "")
            kalite = n.get("kalite", "iyi")
            print(f"{zaman:<25} | {deger:<10} | {birim:<6} | {kalite}")
        print("-" * 55)
        return 0

    # 4. Anlık En Son Ölçümler (Varsayılan)
    if args.kaynak == "api":
        detay = api.modul_detay(args.modul)
        olcumler = api.son_olcumler(args.modul)
        durum_bilgi = {
            "son_gorulme": detay.get("son_gorulme"),
            "besleme": detay.get("besleme"),
            "sinyal": detay.get("sinyal"),
            "seviye": detay.get("seviye")
        }
    else:
        db_sonuc = db.son_olcumleri_getir(args.modul)
        olcum_harita = db_sonuc.get("olcumler", {})
        olcumler = {k: v["deger"] for k, v in olcum_harita.items()}
        modul_durum = db.modul_durumu_getir(args.modul) or {}
        durum_bilgi = {
            "son_gorulme": db_sonuc.get("son_zaman"),
            "besleme": modul_durum.get("besleme"),
            "sinyal": modul_durum.get("sinyal"),
            "seviye": "bilinmiyor"
        }

    if args.json:
        print(json.dumps({"modul_id": args.modul, "durum": durum_bilgi, "olcumler": olcumler}, ensure_ascii=False, indent=2))
        return 0

    print(f"\n⚡ ANLIK ÖLÇÜM SONUÇLARI: {args.modul}")
    print(f"Kaynak      : {args.kaynak.upper()}")
    print(f"Son Görülme : {tr_zaman(durum_bilgi.get('son_gorulme'))}")
    print(f"Besleme     : {str(durum_bilgi.get('besleme') or '-').upper()} | Sinyal: {durum_bilgi.get('sinyal') or '--'} dBm | Seviye: {str(durum_bilgi.get('seviye') or '-').upper()}")
    print("-" * 50)
    print(f"{'ÖLÇÜM TİPİ':<25} | {'DEĞER':<15}")
    print("-" * 50)

    birimler = {
        "ortam_sicaklik": "°C",
        "nem": "%",
        "akim_l1": "A",
        "akim_l2": "A",
        "akim_l3": "A",
        "akim_notr": "A",
        "termal_maks": "°C",
        "termal_ort": "°C",
        "ark_olay": "adet"
    }

    for tip, deger in olcumler.items():
        birim = birimler.get(tip, "")
        val_str = f"{deger} {birim}".strip()
        print(f"{tip:<25} | {val_str:<15}")
    print("-" * 50)

    return 0


if __name__ == "__main__":
    sys.exit(calistir())
