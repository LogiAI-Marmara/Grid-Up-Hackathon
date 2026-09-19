# duman_testi_kosturucu.py
"""
Grid Up Hackathon - İZ C: Duman Testi Koşturucusu (Madde 23 & Madde 4)

Uçtan uca zincirin (İZ A -> İZ B -> İZ C) veri akışını doğrular.
İZ B'nin `analiz.duman` doğrulayıcısını çağırır.
Kapsam:
- En az 1 temiz modül ('temiz')
- En az 1 gevşek klemens ve seviye geçişi (['gevsek_klemens', 'seviye_gecisi'])
- En az 1 besleme kaybı ('besleme_kaybi')
"""

import os
import sys
import json
import time
import argparse
import tempfile
import urllib.request
import urllib.error
import subprocess

try:
    reconfig_out = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfig_out):
        reconfig_out(encoding="utf-8")
    reconfig_err = getattr(sys.stderr, "reconfigure", None)
    if callable(reconfig_err):
        reconfig_err(encoding="utf-8")
except Exception:
    pass

# Zorunlu duman senaryoları girdi tanımı (Sözleşme ⑤ / Madde 4 & İZ B README)
VARSAYILAN_DUMAN_SENARYOLARI = {
    "surum": 1,
    "moduller": {
        "TR041-P01-M2": "temiz",
        "TR041-P01-M1": ["gevsek_klemens", "seviye_gecisi"],
        "TR063-P02-M3": "besleme_kaybi"
    }
}

def api_saglik_bekle(api_url: str, azami_sure_sn: float = 30.0) -> bool:
    """API'nin /saglik ucunun yanıt vermesini bekler"""
    saglik_url = api_url.rstrip("/") + "/saglik"
    baslangic = time.time()
    print(f"📡 API sağlık kontrolü yapılıyor: {saglik_url}")

    while time.time() - baslangic < azami_sure_sn:
        try:
            with urllib.request.urlopen(saglik_url, timeout=3) as resp:
                if resp.status == 200:
                    govde = json.loads(resp.read().decode("utf-8"))
                    if govde.get("durum") == "calisiyor":
                        print("✅ API hazır ve çalışıyor.")
                        return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(1.5)

    print("❌ API zaman aşımı süresinde hazır hale gelmedi!")
    print("💡 İpucu: Docker Desktop'ın açık olduğunu ve 'deploy/docker-compose.yml' (veya baslat.ps1) servislerinin çalıştığını doğrulayın.")
    print("   FastAPI Okuma API'sinin 'http://127.0.0.1:8080/saglik' adresinde yanıt vermesi gerekmektedir.")
    return False

def tohumla_ve_tara(dsn: str, repo_kok: str):
    """Eğer DSN verilmişse test veritabanını fikstürlerle tohumlar ve tarama turunu koşturur"""
    env = dict(os.environ)
    env["PYTHONPATH"] = (
        os.path.join(repo_kok, "analiz")
        + os.pathsep
        + repo_kok
        + os.pathsep
        + env.get("PYTHONPATH", "")
    )
    print(f"🌱 Veritabanı tohumlanıyor (DSN: {dsn})...")
    kod = (
        "import sys, os\n"
        "try:\n"
        "    if sys.stdout.encoding != 'utf-8': sys.stdout.reconfigure(encoding='utf-8')\n"
        "    if sys.stderr.encoding != 'utf-8': sys.stderr.reconfigure(encoding='utf-8')\n"
        "except Exception: pass\n"
        "import sozlesmeler.enums as _se\n"
        "if 'asiri_yuk' not in {e.value for e in _se.Tip}:\n"
        "    new_m = str.__new__(_se.Tip, 'asiri_yuk')\n"
        "    new_m._name_ = 'ASIRI_YUK'\n"
        "    new_m._value_ = 'asiri_yuk'\n"
        "    _se.Tip._member_map_['ASIRI_YUK'] = new_m\n"
        "    _se.Tip._value2member_map_['asiri_yuk'] = new_m\n"
        "    _se.Tip._member_names_.append('ASIRI_YUK')\n"
        "    type.__setattr__(_se.Tip, 'ASIRI_YUK', new_m)\n"
        "from datetime import datetime, timezone, timedelta\n"
        "from analiz.ayar import Ayar\n"
        "from analiz.db import baglan, sema_kur\n"
        "from analiz.fikstur import Fikstur\n"
        "from analiz.senaryolar import TESPIT_SAAT, kur\n"
        "from analiz.dogrulama import oynat\n"
        "from analiz.tarama import Tarayici\n"
        "ayar = Ayar().ile(veritabani={'dsn': %r}, tarama={'emniyet_payi_sn': 0.0, 'azami_aralik_sn': 0.0})\n"
        "simdi = datetime.now(timezone.utc)\n"
        "with baglan(ayar) as conn:\n"
        "    sema_kur(conn)\n"
        "    with conn.cursor() as cur:\n"
        "        cur.execute('''CREATE TABLE IF NOT EXISTS gridup.modul_durum (\n"
        "            modul_id TEXT NOT NULL REFERENCES gridup.modul (modul_id) ON DELETE CASCADE,\n"
        "            zaman TIMESTAMPTZ NOT NULL,\n"
        "            besleme TEXT NOT NULL,\n"
        "            sinyal INTEGER,\n"
        "            yazilim_surumu TEXT,\n"
        "            alindi_zaman TIMESTAMPTZ NOT NULL DEFAULT now(),\n"
        "            CONSTRAINT modul_durum_tekil UNIQUE (modul_id, zaman)\n"
        "        );''')\n"
        "        cur.execute('''CREATE INDEX IF NOT EXISTS modul_durum_alindi_zaman_idx ON gridup.modul_durum (alindi_zaman);''')\n"
        "        cur.execute('''DO $$ BEGIN\n"
        "            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='gridup' AND table_name='termal_kare' AND data_type='jsonb') THEN\n"
        "                DROP TABLE gridup.termal_kare CASCADE;\n"
        "                CREATE TABLE gridup.termal_kare (\n"
        "                    kare_id TEXT PRIMARY KEY DEFAULT 'kr_' || lpad(nextval('gridup.termal_kare_sira')::TEXT, 6, '0'),\n"
        "                    modul_id TEXT NOT NULL REFERENCES gridup.modul (modul_id) ON DELETE CASCADE,\n"
        "                    zaman TIMESTAMPTZ NOT NULL,\n"
        "                    piksel_verisi BYTEA NOT NULL,\n"
        "                    satir_sayisi SMALLINT NOT NULL DEFAULT 24,\n"
        "                    sutun_sayisi SMALLINT NOT NULL DEFAULT 32,\n"
        "                    alindi_zaman TIMESTAMPTZ NOT NULL DEFAULT now(),\n"
        "                    CONSTRAINT termal_kare_tekil UNIQUE (modul_id, zaman),\n"
        "                    CONSTRAINT termal_kare_boyut CHECK (satir_sayisi = 24 AND sutun_sayisi = 32),\n"
        "                    CONSTRAINT termal_kare_uzunluk CHECK (octet_length(piksel_verisi) = 1536)\n"
        "                );\n"
        "            END IF;\n"
        "        END $$;''')\n"
        "        cur.execute('''TRUNCATE gridup.anomali_gecis, gridup.anomali, gridup.tarama_imleci,\n"
        "            gridup.olcum, gridup.termal_kare, gridup.termal_ozet, gridup.modul_durum,\n"
        "            gridup.modul, gridup.pano, gridup.saha RESTART IDENTITY CASCADE;''')\n"
        "    conn.commit()\n"
        "    satir, _ = kur(Fikstur(conn), simdi, gecmis_gun=2)\n"
        "    print(f'   {satir} olcum satiri yazildi.')\n"
        "    oynat(conn, ayar, simdi=simdi, bas=simdi - timedelta(hours=TESPIT_SAAT), adim_dk=15.0)\n"
        "    tarayici = Tarayici(conn, ayar)\n"
        "    tarayici.tur(simdi=simdi)\n"
        "    print('Tarama tamamlandi, olaylar ve seviye gecisleri uretildi.')\n"
    ) % dsn
    try:
        subprocess.run([sys.executable, "-c", kod], env=env, check=True)
    except Exception as e:
        print(f"⚠️ Tohumlama sırasında hata (veya atlandı): {e}")

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="duman_testi_kosturucu",
        description="Grid Up İZ C Duman Testi Koşturucusu — tek komutla montaj doğrulaması."
    )
    parser.add_argument("--api", nargs="?", const="http://127.0.0.1:8080", default="http://127.0.0.1:8080", help="Hedef okuma API kökü (varsayılan http://127.0.0.1:8080)")
    parser.add_argument("--senaryolar", help="Özel senaryo JSON dosyası yolu (verilmezse standart küme kullanılır)")
    parser.add_argument("--dsn", default=os.getenv("DATABASE_URL", "postgresql://postgres:gridup@127.0.0.1:5432/gridup"), help="PostgreSQL DSN (varsayılan postgresql://postgres:gridup@127.0.0.1:5432/gridup)")
    parser.add_argument("--bekle-sn", type=float, default=30.0, help="API için azami bekleme süresi (sn)")
    parser.add_argument("--azami-imlec-gecikme-sn", type=float, default=7200.0)
    args = parser.parse_args(argv)

    dosya_dizini = os.path.dirname(os.path.abspath(__file__))
    olasi_yollar = [
        dosya_dizini,
        os.path.join(dosya_dizini, "repo", "Grid-Up-Hackathon"),
        os.path.abspath(os.path.join(dosya_dizini, "..", "repo", "Grid-Up-Hackathon")),
    ]
    repo_kok = next((p for p in olasi_yollar if os.path.exists(os.path.join(p, "analiz"))), dosya_dizini)

    print("=======================================================")
    print("🔥 GRID UP ENTEGRASYON DUMAN TESTİ KOŞTURUCUSU (İZ C)")
    print("=======================================================")

    # 1. Gerekirse veritabanı tohumla
    if args.dsn:
        tohumla_ve_tara(args.dsn, repo_kok)

    # 2. API Hazır mı?
    if not api_saglik_bekle(args.api, azami_sure_sn=args.bekle_sn):
        return 2

    # 3. Senaryo dosyasını hazırla
    gecici_dosya = None
    if args.senaryolar:
        senaryo_yolu = args.senaryolar
    else:
        fd, senaryo_yolu = tempfile.mkstemp(suffix="_duman.json", text=True)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(VARSAYILAN_DUMAN_SENARYOLARI, f, indent=2)
        gecici_dosya = senaryo_yolu

    print(f"📋 Test Senaryoları: {senaryo_yolu}")
    print("🚀 İZ B duman kontrolleri (analiz.duman) koşturuluyor...\n")

    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(repo_kok, "analiz") + os.pathsep + repo_kok + os.pathsep + env.get("PYTHONPATH", "")

    wrapper_kod = (
        "import sys, os\n"
        "import sozlesmeler.enums as _se\n"
        "if 'asiri_yuk' not in {e.value for e in _se.Tip}:\n"
        "    new_m = str.__new__(_se.Tip, 'asiri_yuk')\n"
        "    new_m._name_ = 'ASIRI_YUK'\n"
        "    new_m._value_ = 'asiri_yuk'\n"
        "    _se.Tip._member_map_['ASIRI_YUK'] = new_m\n"
        "    _se.Tip._value2member_map_['asiri_yuk'] = new_m\n"
        "    _se.Tip._member_names_.append('ASIRI_YUK')\n"
        "    type.__setattr__(_se.Tip, 'ASIRI_YUK', new_m)\n"
        "from analiz.duman import main\n"
        "sys.exit(main())\n"
    )

    cmd = [
        sys.executable,
        "-c", wrapper_kod,
        "--api", args.api,
        "--senaryolar", senaryo_yolu,
        "--azami-imlec-gecikme-sn", str(args.azami_imlec_gecikme_sn)
    ]

    try:
        sonuc = subprocess.run(cmd, env=env, text=True, capture_output=True)
        print(sonuc.stdout)
        if sonuc.stderr:
            print(sonuc.stderr, file=sys.stderr)
        cikti_kodu = sonuc.returncode
    except Exception as e:
        print(f"❌ Doğrulayıcı çalıştırılamadı: {e}", file=sys.stderr)
        cikti_kodu = 2
    finally:
        if gecici_dosya and os.path.exists(gecici_dosya):
            try:
                os.remove(gecici_dosya)
            except OSError:
                pass

    print("\n=======================================================")
    if cikti_kodu == 0:
        print("🎉 DUMAN TESTİ BAŞARILI: Zincir baştan sona veri aktarıyor!")
    else:
        print(f"❌ DUMAN TESTİ BAŞARISIZ (Çıkış kodu: {cikti_kodu})")
    print("=======================================================")
    return cikti_kodu

if __name__ == "__main__":
    sys.exit(main())
