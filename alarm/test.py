# test.py
"""
Grid Up Hackathon - İZ C: Alarm Servisi Testleri

Testler İZ_C_ALTI_GOREV_TEKNIK_INCELEME.md §6'daki A-01..A-06 bulgularına göre
gruplanmıştır; her sınıf bir bulgunun kabul kanıtını karşılar.

Hiçbir test gerçek operasyon veritabanına, gerçek `/gecisler` ucuna ya da
gerçek bir alıcıya (SMS/Telegram) bağlanmaz: HTTP oturumu ve kanallar sahte
nesnelerle değiştirilir. Docker kalıcılığı birim testiyle değil, README'de
tarif edilen yeniden oluşturma denemesiyle doğrulanır.
"""

import json
import logging
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def setUpModule():
    """Servis logları testlerin çıktısını boğmasın.

    `assertLogs` çağrıldığı logger'ın seviyesini kendisi geçici olarak
    düşürdüğü için, hata yollarını doğrulayan testler bundan etkilenmez.
    ALARM_TEST_LOG=1 ile normal seviyeye dönülür.
    """
    if not os.getenv("ALARM_TEST_LOG"):
        logging.getLogger("alarm").setLevel(logging.CRITICAL)

from alarm_service import (  # noqa: E402
    BASARISIZ,
    BASTIRILDI,
    ILGISIZ,
    TESLIM_EDILDI,
    AlarmManager,
)
from durum import (  # noqa: E402
    BozukDurumHatasi,
    DurumDeposu,
    DurumYazmaHatasi,
    bos_durum,
)
from kanallar import (  # noqa: E402
    HATA,
    SEVIYE_DERECESI,
    TESLIM,
    YAPILANDIRILMAMIS,
    Bildirim,
    Kanal,
    KanalSonucu,
    KonsolKanali,
    SmsGatewayKanali,
    kanal_kurali_coz,
)

# ---------------------------------------------------------------------------
# Sahte nesneler
# ---------------------------------------------------------------------------


class SahteKanal(Kanal):
    """Sıraya dizilmiş sonuçları döndüren kanal. `cagrilar` gönderim kanıtıdır."""

    def __init__(self, ad="sms", sonuclar=None, yapilandirildi=True):
        self.ad = ad
        self._yapilandirildi = yapilandirildi
        self.sonuclar = list(sonuclar or [])
        self.cagrilar = []

    def yapilandirildi_mi(self):
        return self._yapilandirildi

    def eksikler(self):
        return [] if self._yapilandirildi else ["SAHTE_AYAR"]

    def gonder(self, bildirim):
        self.cagrilar.append(bildirim)
        if not self._yapilandirildi:
            return KanalSonucu(self.ad, YAPILANDIRILMAMIS, "ayar yok")
        durum = self.sonuclar.pop(0) if self.sonuclar else TESLIM
        return KanalSonucu(self.ad, durum, f"sahte:{durum}")


class SahteYanit:
    def __init__(self, status_code=200, govde=None, text=""):
        self.status_code = status_code
        self._govde = {} if govde is None else govde
        self.text = text

    def json(self):
        return self._govde


class SahteAPI:
    """`/gecisler` sayfalarını ve `/anomaliler/{id}` detaylarını taklit eder."""

    def __init__(self, sayfalar=None, detaylar=None, detay_kodu=200):
        self.sayfalar = list(sayfalar or [])
        self.detaylar = detaylar or {}
        self.detay_kodu = detay_kodu
        self.gecis_istekleri = []
        self.detay_istekleri = []

    def get(self, url, params=None, timeout=None):
        if url.endswith("/gecisler"):
            self.gecis_istekleri.append(dict(params or {}))
            veriler = self.sayfalar.pop(0) if self.sayfalar else []
            return SahteYanit(
                200,
                {
                    "veriler": veriler,
                    "sonraki": veriler[-1]["id"] if veriler else None,
                    "limit": 100,
                },
            )

        anomali_id = url.rsplit("/", 1)[-1]
        self.detay_istekleri.append(anomali_id)
        if self.detay_kodu == "baglanti":
            raise ConnectionError("detay ucu kapalı")
        if self.detay_kodu != 200:
            return SahteYanit(self.detay_kodu, {}, "detay hatası")
        return SahteYanit(200, self.detaylar.get(anomali_id, {}))


def gecis(id, anomali_id="an_001", onceki="izle", yeni="uyari", alan="seviye"):
    return {
        "id": id,
        "anomali_id": anomali_id,
        "alan": alan,
        "onceki": onceki,
        "yeni": yeni,
        "zaman": "2026-09-17T10:00:00Z",
        "aktor": "tarama",
    }


class AlarmTestTabani(unittest.TestCase):
    """Her test kendi geçici dizinini ve durum dosyasını kullanır."""

    def setUp(self):
        self.dizin = tempfile.mkdtemp(prefix="alarm-test-")
        self.durum_yolu = os.path.join(self.dizin, "alarm_state.json")

    def tearDown(self):
        shutil.rmtree(self.dizin, ignore_errors=True)

    def yonetici(self, api=None, sms=None, kural="uyari:konsol,sms!|kritik:konsol,sms!", **kw):
        kanallar = {"konsol": KonsolKanali(), "sms": sms or SahteKanal("sms")}
        kw.setdefault("cooldown_seconds", 300)
        kw.setdefault("yeniden_deneme_taban", 0)
        kw.setdefault("yeniden_deneme_tavan", 0)
        return AlarmManager(
            api_url="http://sahte",
            state_file=self.durum_yolu,
            kanallar=kanallar,
            kanal_kurali=kural,
            oturum=api or SahteAPI(),
            **kw,
        )


# ---------------------------------------------------------------------------
# A-01: Başarısız bildirim işlenmiş sayılmamalı
# ---------------------------------------------------------------------------


class TestA01TeslimTakibi(AlarmTestTabani):
    def test_hata_sonra_basari_ayni_gecis_yeniden_denenir(self):
        """Önce HTTP 500, sonra başarı: ilk deneme teslim iddia etmez."""
        sms = SahteKanal("sms", sonuclar=[HATA, TESLIM])
        api = SahteAPI(
            sayfalar=[[gecis(101, "an_001", "izle", "kritik")], []],
            detaylar={"an_001": {"modul_id": "TR041-P01-M1", "gerekce": "ısındı", "skor": 0.9}},
        )
        yon = self.yonetici(api=api, sms=sms)

        yon.poll_transitions()
        # İlk tur: gönderim denendi, başarısız. Teslim de cooldown da iddia edilmez.
        self.assertEqual(len(sms.cagrilar), 1)
        self.assertEqual(yon.state["son_bildirim"], {})
        self.assertIn("101", yon.state["bekleyen"])

        # Kalıcı dosya da başarıyı iddia etmemeli: bekleyen iş diskte duruyor.
        with open(self.durum_yolu, encoding="utf-8") as f:
            kalici = json.load(f)
        self.assertIn("101", kalici["bekleyen"])
        self.assertEqual(kalici["son_bildirim"], {})

        # İkinci tur: aynı geçiş yeniden denenir ve bu kez teslim edilir.
        yon.poll_transitions()
        self.assertEqual(len(sms.cagrilar), 2)
        self.assertEqual(sms.cagrilar[1].gecis_id, 101)
        self.assertEqual(yon.state["bekleyen"], {})
        self.assertEqual(len(yon.state["son_bildirim"]), 1)

    def test_basaridan_sonra_gereksiz_tekrar_yok(self):
        """Teslimden sonraki normal poll aynı geçişi tekrar bildirmez."""
        sms = SahteKanal("sms")
        api = SahteAPI(sayfalar=[[gecis(101, "an_001", "izle", "kritik")], [], []])
        yon = self.yonetici(api=api, sms=sms)

        yon.poll_transitions()
        yon.poll_transitions()
        yon.poll_transitions()

        self.assertEqual(len(sms.cagrilar), 1)
        # İmleç ilerledi: sonraki istekler 101'den sonrasını sordu.
        self.assertEqual(api.gecis_istekleri[1].get("sonra"), 101)

    def test_basarisiz_gecisin_otesine_atlanmaz(self):
        """Arka arkaya gelen geçişlerde başarısız olan kaybolmaz."""
        # 101 başarısız, 102 başarılı, sonra 101 yeniden denenip başarılı olur.
        sms = SahteKanal("sms", sonuclar=[HATA, TESLIM, TESLIM])
        api = SahteAPI(
            sayfalar=[
                [
                    gecis(101, "an_001", "izle", "kritik"),
                    gecis(102, "an_002", "izle", "kritik"),
                ],
                [],
            ]
        )
        yon = self.yonetici(api=api, sms=sms)

        yon.poll_transitions()
        self.assertEqual([b.gecis_id for b in sms.cagrilar], [101, 102])
        # İmleç 102'ye ilerledi ama 101 atlanmadı: kuyrukta tam gövdesiyle duruyor.
        self.assertEqual(yon.state["son_gecis_id"], 102)
        self.assertIn("101", yon.state["bekleyen"])
        self.assertEqual(yon.state["bekleyen"]["101"]["gecis"]["anomali_id"], "an_001")

        yon.poll_transitions()
        self.assertEqual([b.gecis_id for b in sms.cagrilar], [101, 102, 101])
        self.assertEqual(yon.state["bekleyen"], {})

    def test_zaman_asimi_teslim_sayilmaz(self):
        """Bağlantı hatası (zaman aşımı) teslim değildir."""

        class ZamanAsimiKanali(SahteKanal):
            def gonder(self, bildirim):
                self.cagrilar.append(bildirim)
                return KanalSonucu(self.ad, HATA, "ReadTimeout")

        sms = ZamanAsimiKanali("sms")
        api = SahteAPI(sayfalar=[[gecis(101, "an_001", "izle", "kritik")]])
        yon = self.yonetici(api=api, sms=sms)
        yon.poll_transitions()

        self.assertIn("101", yon.state["bekleyen"])
        self.assertEqual(yon.state["son_bildirim"], {})

    def test_log_tek_basina_teslim_kaniti_degil(self):
        """Konsol başarılı olsa bile zorunlu dış kanal başarısızsa teslim yok."""
        sms = SahteKanal("sms", sonuclar=[HATA])
        api = SahteAPI(sayfalar=[[gecis(101, "an_001", "izle", "kritik")]])
        yon = self.yonetici(api=api, sms=sms)
        sonuc = yon.evaluate_transition(gecis(101, "an_001", "izle", "kritik"))
        self.assertEqual(sonuc, BASARISIZ)


# ---------------------------------------------------------------------------
# A-02: Tekrar önleme ayrı olayları ve kritik yükselmeyi bastırmamalı
# ---------------------------------------------------------------------------


class TestA02TekrarOnleme(AlarmTestTabani):
    def test_ayni_modulde_iki_anomali_ayri_bildirilir(self):
        sms = SahteKanal("sms")
        api = SahteAPI(
            detaylar={
                "an_A": {"modul_id": "TR041-P01-M1", "gerekce": "A", "skor": 0.8},
                "an_B": {"modul_id": "TR041-P01-M1", "gerekce": "B", "skor": 0.9},
            }
        )
        yon = self.yonetici(api=api, sms=sms)

        self.assertEqual(yon.evaluate_transition(gecis(1, "an_A", "izle", "uyari")), TESLIM_EDILDI)
        self.assertEqual(yon.evaluate_transition(gecis(2, "an_B", "izle", "uyari")), TESLIM_EDILDI)
        self.assertEqual(len(sms.cagrilar), 2)

    def test_uyari_kritik_yukselmesi_bastirilmaz(self):
        """Gerçek eskalasyon: aynı olay, uyarıdan kritiğe, cooldown içinde."""
        sms = SahteKanal("sms")
        api = SahteAPI(detaylar={"an_A": {"modul_id": "TR041-P01-M1", "gerekce": "A"}})
        yon = self.yonetici(api=api, sms=sms)

        self.assertEqual(yon.evaluate_transition(gecis(1, "an_A", "izle", "uyari")), TESLIM_EDILDI)
        self.assertEqual(yon.evaluate_transition(gecis(2, "an_A", "uyari", "kritik")), TESLIM_EDILDI)

        self.assertEqual([b.seviye for b in sms.cagrilar], ["uyari", "kritik"])

    def test_mukerrer_esdeger_bildirim_50_kez_gitmez(self):
        sms = SahteKanal("sms")
        api = SahteAPI(detaylar={"an_A": {"modul_id": "TR041-P01-M1"}})
        yon = self.yonetici(api=api, sms=sms)

        sonuclar = [
            yon.evaluate_transition(gecis(100 + i, "an_A", "izle", "uyari"))
            for i in range(50)
        ]
        self.assertEqual(sonuclar[0], TESLIM_EDILDI)
        self.assertTrue(all(s == BASTIRILDI for s in sonuclar[1:]))
        self.assertEqual(len(sms.cagrilar), 1)

    def test_kanal_hatasi_cooldown_baslatmaz(self):
        """Başarısız teslim kendi yeniden denemesini bastıramaz."""
        sms = SahteKanal("sms", sonuclar=[HATA, TESLIM])
        api = SahteAPI(detaylar={"an_A": {"modul_id": "TR041-P01-M1"}})
        yon = self.yonetici(api=api, sms=sms)

        self.assertEqual(yon.evaluate_transition(gecis(1, "an_A", "izle", "kritik")), BASARISIZ)
        self.assertEqual(yon.state["son_bildirim"], {})
        # Hemen ardından gelen yeniden deneme bastırılmamalı.
        self.assertEqual(yon.evaluate_transition(gecis(1, "an_A", "izle", "kritik")), TESLIM_EDILDI)

    def test_seviye_dususu_ve_durum_alani_bildirim_uretmez(self):
        sms = SahteKanal("sms")
        yon = self.yonetici(sms=sms)
        self.assertEqual(yon.evaluate_transition(gecis(1, "an_A", "kritik", "izle")), ILGISIZ)
        self.assertEqual(
            yon.evaluate_transition(gecis(2, "an_A", "acik", "onaylandi", alan="durum")),
            ILGISIZ,
        )
        self.assertEqual(len(sms.cagrilar), 0)

    def test_seviye_dereceleri(self):
        self.assertLess(SEVIYE_DERECESI["normal"], SEVIYE_DERECESI["izle"])
        self.assertLess(SEVIYE_DERECESI["izle"], SEVIYE_DERECESI["uyari"])
        self.assertLess(SEVIYE_DERECESI["uyari"], SEVIYE_DERECESI["kritik"])


# ---------------------------------------------------------------------------
# A-03: Seviye->kanal kuralı ve on-prem dış bildirim
# ---------------------------------------------------------------------------


class TestA03KanalKurali(AlarmTestTabani):
    def test_kural_cozumu_zorunlulari_ayirir(self):
        kurallar = kanal_kurali_coz("uyari:konsol,sms|kritik:konsol,sms!")
        self.assertEqual(kurallar["uyari"].kanallar, ("konsol", "sms"))
        self.assertEqual(kurallar["uyari"].zorunlular, frozenset())
        self.assertEqual(kurallar["kritik"].zorunlular, frozenset({"sms"}))

    def test_gecersiz_kural_reddedilir(self):
        for kotu in ("", "kritik", "bilinmeyen:konsol", "kritik:"):
            with self.assertRaises(ValueError):
                kanal_kurali_coz(kotu)

    def test_uyaride_opsiyonel_kritikte_zorunlu(self):
        """Varsayılan kural: SMS hatası uyarıyı teslim saydırır, kritiği saydırmaz."""
        sms = SahteKanal("sms", sonuclar=[HATA, HATA])
        api = SahteAPI(detaylar={"an_A": {"modul_id": "M1"}})
        yon = self.yonetici(api=api, sms=sms, kural="uyari:konsol,sms|kritik:konsol,sms!")

        self.assertEqual(yon.evaluate_transition(gecis(1, "an_A", "izle", "uyari")), TESLIM_EDILDI)
        self.assertEqual(yon.evaluate_transition(gecis(2, "an_B", "izle", "kritik")), BASARISIZ)

    def test_yapilandirilmamis_zorunlu_kanal_gonderildi_demez(self):
        sms = SahteKanal("sms", yapilandirildi=False)
        api = SahteAPI(detaylar={"an_A": {"modul_id": "M1"}})
        yon = self.yonetici(api=api, sms=sms)

        self.assertEqual(yon.evaluate_transition(gecis(1, "an_A", "izle", "kritik")), BASARISIZ)
        self.assertEqual(yon.state["son_bildirim"], {})

    def test_yapilandirma_uyarisi_eksik_zorunlu_kanali_soyler(self):
        yon = self.yonetici(sms=SahteKanal("sms", yapilandirildi=False))
        uyarilar = " ".join(yon.yapilandirma_uyarilari())
        self.assertIn("ZORUNLU", uyarilar)
        self.assertIn("sms", uyarilar)

    def test_yalniz_konsol_kurali_uyari_verir(self):
        """Kritik alarmın yalnız konsola yazılması dış bildirim sayılmaz."""
        yon = self.yonetici(kural="kritik:konsol")
        uyarilar = " ".join(yon.yapilandirma_uyarilari())
        self.assertIn("zorunlu dış bildirim kanalı yok", uyarilar)

    def test_bulut_kanali_acikken_celiski_uyarisi(self):
        from kanallar import TelegramKanali

        kanallar = {"konsol": KonsolKanali(), "telegram": TelegramKanali("t", "c")}
        yon = AlarmManager(
            api_url="http://sahte",
            state_file=self.durum_yolu,
            kanallar=kanallar,
            kanal_kurali="kritik:konsol,telegram!",
            oturum=SahteAPI(),
        )
        uyarilar = " ".join(yon.yapilandirma_uyarilari())
        self.assertIn("public cloud", uyarilar)


class TestA03SmsGateway(unittest.TestCase):
    """Gerçek gateway adaptörünün dört yolu — sahte HTTP oturumuyla."""

    def bildirim(self):
        return Bildirim(
            gecis_id=1,
            anomali_id="an_A",
            seviye="kritik",
            onceki_seviye="uyari",
            zaman="2026-09-17T10:00:00Z",
            modul_id="TR041-P01-M1",
            gerekce="L2 klemensi ısındı",
            skor=0.91,
            detay_alindi=True,
        )

    def test_olumlu_yanit(self):
        cagrilar = []

        class Oturum:
            def post(self, url, **kw):
                cagrilar.append((url, kw))
                return SahteYanit(202, text="queued")

        kanal = SmsGatewayKanali(
            url="http://192.168.1.50:8080/message",
            alicilar=["+905551112233"],
            alici_alani="phoneNumbers",
            mesaj_alani="message",
            oturum=Oturum(),
        )
        sonuc = kanal.gonder(self.bildirim())
        self.assertEqual(sonuc.durum, TESLIM)
        # Alan adları yapılandırıldığı gibi kullanıldı: ürün seçimi koda gömülü değil.
        self.assertIn("phoneNumbers", cagrilar[0][1]["json"])
        self.assertIn("TR041-P01-M1", cagrilar[0][1]["json"]["message"])

    def test_reddedilme(self):
        class Oturum:
            def post(self, url, **kw):
                return SahteYanit(401, text="unauthorized")

        kanal = SmsGatewayKanali(url="http://x/m", alicilar=["+9055"], oturum=Oturum())
        sonuc = kanal.gonder(self.bildirim())
        self.assertEqual(sonuc.durum, HATA)
        self.assertIn("401", sonuc.detay)

    def test_baglanti_kesintisi(self):
        class Oturum:
            def post(self, url, **kw):
                raise OSError("connection refused")

        kanal = SmsGatewayKanali(url="http://x/m", alicilar=["+9055"], oturum=Oturum())
        self.assertEqual(kanal.gonder(self.bildirim()).durum, HATA)

    def test_yanlis_yapilandirma_gonderim_denemez(self):
        class Oturum:
            def post(self, url, **kw):
                raise AssertionError("yapılandırılmamış kanal gönderim denememeli")

        # Alıcı listesi boş: URL var ama kanal eksik yapılandırılmış.
        kanal = SmsGatewayKanali(url="http://x/m", alicilar=[], oturum=Oturum())
        sonuc = kanal.gonder(self.bildirim())
        self.assertEqual(sonuc.durum, YAPILANDIRILMAMIS)
        self.assertIn("SMS_ALICILAR", sonuc.detay)


# ---------------------------------------------------------------------------
# A-04: Durum yeniden başlatmada korunur, hatalar görünür
# ---------------------------------------------------------------------------


class TestA04Kalicilik(AlarmTestTabani):
    def test_yeniden_baslatma_ayni_gecisi_tekrar_bildirmez(self):
        sms1 = SahteKanal("sms")
        api1 = SahteAPI(sayfalar=[[gecis(101, "an_A", "izle", "kritik")]])
        yon1 = self.yonetici(api=api1, sms=sms1)
        yon1.poll_transitions()
        self.assertEqual(len(sms1.cagrilar), 1)

        # Yeni servis örneği, aynı durum dosyası.
        sms2 = SahteKanal("sms")
        api2 = SahteAPI(sayfalar=[[]])
        yon2 = self.yonetici(api=api2, sms=sms2)
        self.assertEqual(yon2.state["son_gecis_id"], 101)
        yon2.poll_transitions()

        self.assertEqual(len(sms2.cagrilar), 0)
        self.assertEqual(api2.gecis_istekleri[0].get("sonra"), 101)

    def test_yeniden_baslatma_bekleyeni_surdurur(self):
        """Teslim edilememiş geçiş yeniden başlatmada kaybolmaz."""
        sms1 = SahteKanal("sms", sonuclar=[HATA])
        api1 = SahteAPI(sayfalar=[[gecis(101, "an_A", "izle", "kritik")]])
        self.yonetici(api=api1, sms=sms1).poll_transitions()

        sms2 = SahteKanal("sms", sonuclar=[TESLIM])
        api2 = SahteAPI(sayfalar=[[]])
        yon2 = self.yonetici(api=api2, sms=sms2)
        self.assertIn("101", yon2.state["bekleyen"])
        yon2.poll_transitions()

        self.assertEqual([b.gecis_id for b in sms2.cagrilar], [101])
        self.assertEqual(yon2.state["bekleyen"], {})

    def test_yazilamayan_durum_basarili_sayilmaz(self):
        sms = SahteKanal("sms")
        api = SahteAPI(sayfalar=[[gecis(101, "an_A", "izle", "kritik")]])
        yon = self.yonetici(api=api, sms=sms)

        def patlat(durum):
            raise DurumYazmaHatasi("disk dolu")

        yon.depo.kaydet = patlat
        with self.assertLogs("alarm", level="ERROR"):
            yon.poll_transitions()

        # Bellek son kalıcı hale döndü: imleç ilerlemiş gibi davranmıyoruz.
        self.assertIsNone(yon.state["son_gecis_id"])
        self.assertFalse(os.path.exists(self.durum_yolu))

    def test_bozuk_durum_sessizce_sifirlanmaz(self):
        with open(self.durum_yolu, "w", encoding="utf-8") as f:
            f.write("{bu gecerli json degil")

        depo = DurumDeposu(self.durum_yolu)
        with self.assertRaises(BozukDurumHatasi):
            depo.yukle()
        # Dosya operatör incelesin diye olduğu gibi duruyor.
        self.assertTrue(os.path.exists(self.durum_yolu))

    def test_bozuk_durum_acik_izinle_yedege_alinir(self):
        with open(self.durum_yolu, "w", encoding="utf-8") as f:
            f.write("bozuk")

        depo = DurumDeposu(self.durum_yolu, bozuk_politika="sifirla")
        with self.assertLogs("alarm.durum", level="ERROR"):
            durum = depo.yukle()
        self.assertEqual(durum, bos_durum())
        yedekler = [a for a in os.listdir(self.dizin) if ".bozuk-" in a]
        self.assertEqual(len(yedekler), 1)

    def test_tutarsiz_sema_bozuk_sayilir(self):
        with open(self.durum_yolu, "w", encoding="utf-8") as f:
            json.dump({"son_gecis_id": "yüz bir"}, f)
        with self.assertRaises(BozukDurumHatasi):
            DurumDeposu(self.durum_yolu).yukle()

    def test_v1_durumu_imleci_koruyarak_tasinir(self):
        with open(self.durum_yolu, "w", encoding="utf-8") as f:
            json.dump({"son_gecis_id": 1234, "last_alert_times": {"M1": 1.0}}, f)

        durum = DurumDeposu(self.durum_yolu).yukle()
        self.assertEqual(durum["son_gecis_id"], 1234)
        self.assertEqual(durum["son_bildirim"], {})

    def test_yazim_atomik(self):
        depo = DurumDeposu(self.durum_yolu)
        durum = bos_durum()
        durum["son_gecis_id"] = 7
        depo.kaydet(durum)
        self.assertFalse(os.path.exists(self.durum_yolu + ".tmp"))
        self.assertEqual(depo.yukle()["son_gecis_id"], 7)


# ---------------------------------------------------------------------------
# A-05: Detay alınamadığında olaylar birleşmemeli
# ---------------------------------------------------------------------------


class TestA05DetaySizDavranis(AlarmTestTabani):
    def test_detay_hatasinda_iki_olay_birbirini_bastirmaz(self):
        sms = SahteKanal("sms")
        api = SahteAPI(detay_kodu=500)
        yon = self.yonetici(api=api, sms=sms)

        self.assertEqual(yon.evaluate_transition(gecis(1, "an_A", "izle", "kritik")), TESLIM_EDILDI)
        self.assertEqual(yon.evaluate_transition(gecis(2, "an_B", "izle", "kritik")), TESLIM_EDILDI)
        self.assertEqual(len(sms.cagrilar), 2)
        self.assertEqual([b.anomali_id for b in sms.cagrilar], ["an_A", "an_B"])

    def test_detay_baglanti_hatasinda_da_ayrisir(self):
        sms = SahteKanal("sms")
        yon = self.yonetici(api=SahteAPI(detay_kodu="baglanti"), sms=sms)
        yon.evaluate_transition(gecis(1, "an_A", "izle", "kritik"))
        yon.evaluate_transition(gecis(2, "an_B", "izle", "kritik"))
        self.assertEqual(len(sms.cagrilar), 2)

    def test_uydurma_modul_adi_uretilmez(self):
        sms = SahteKanal("sms")
        yon = self.yonetici(api=SahteAPI(detay_kodu=500), sms=sms)
        yon.evaluate_transition(gecis(1, "an_A", "izle", "kritik"))

        b = sms.cagrilar[0]
        self.assertIsNone(b.modul_id)
        self.assertIsNone(b.gerekce)
        self.assertFalse(b.detay_alindi)
        # Olay kimliği ve eksik bilgi mesajda açıkça görünür.
        self.assertIn("an_A", b.kisa_metin())
        self.assertIn("DETAY ALINAMADI", b.kisa_metin())
        self.assertIn("BILINMIYOR", b.kisa_metin())

    def test_bastirma_anahtari_detaya_bagli_degil(self):
        a = AlarmManager.bastirma_anahtari(gecis(1, "an_A", "izle", "kritik"), "kritik")
        b = AlarmManager.bastirma_anahtari(gecis(2, "an_B", "izle", "kritik"), "kritik")
        self.assertNotEqual(a, b)
        self.assertIn("an_A", a)

    def test_anomali_id_yoksa_anahtar_tekil_kalir(self):
        """Kimliksiz geçişler tek anonim alarmda birleşmez."""
        a = AlarmManager.bastirma_anahtari({"id": 1, "anomali_id": None}, "kritik")
        b = AlarmManager.bastirma_anahtari({"id": 2, "anomali_id": None}, "kritik")
        self.assertNotEqual(a, b)


# ---------------------------------------------------------------------------
# A-06 ek: akış ve kuyruk davranışı
# ---------------------------------------------------------------------------


class TestAkis(AlarmTestTabani):
    def test_imlec_ve_sayfalama(self):
        api = SahteAPI(
            sayfalar=[
                [gecis(501, "an_005", "normal", "kritik")],
                [gecis(502, "an_006", "normal", "kritik")],
            ]
        )
        yon = self.yonetici(api=api)
        yon.poll_transitions()
        self.assertEqual(yon.state["son_gecis_id"], 501)
        yon.poll_transitions()
        self.assertEqual(yon.state["son_gecis_id"], 502)
        self.assertEqual(api.gecis_istekleri[1].get("sonra"), 501)

    def test_bos_sayfa_imleci_geri_almaz(self):
        """`sonraki` akışın bittiği anlamına gelmez; boş sayfa imleci bozmaz."""
        api = SahteAPI(sayfalar=[[gecis(501, "an_005", "normal", "kritik")], [], []])
        yon = self.yonetici(api=api)
        yon.poll_transitions()
        yon.poll_transitions()
        yon.poll_transitions()
        self.assertEqual(yon.state["son_gecis_id"], 501)

    def test_api_hatasi_imleci_ilerletmez(self):
        class HataliAPI(SahteAPI):
            def get(self, url, params=None, timeout=None):
                if url.endswith("/gecisler"):
                    self.gecis_istekleri.append(dict(params or {}))
                    return SahteYanit(503, {}, "kapalı")
                return super().get(url, params, timeout)

        yon = self.yonetici(api=HataliAPI())
        yon.poll_transitions()
        self.assertIsNone(yon.state["son_gecis_id"])

    def test_bekleyen_kuyrugu_sinirli_ve_dusen_sayilir(self):
        sms = SahteKanal("sms", sonuclar=[HATA] * 10)
        api = SahteAPI(sayfalar=[[gecis(i, f"an_{i}", "izle", "kritik") for i in (1, 2, 3)]])
        yon = self.yonetici(api=api, sms=sms, bekleyen_siniri=2)
        with self.assertLogs("alarm", level="ERROR"):
            yon.poll_transitions()

        self.assertEqual(len(yon.state["bekleyen"]), 2)
        self.assertEqual(yon.state["dusen_bildirim"], 1)
        self.assertNotIn("1", yon.state["bekleyen"])

    def test_idsiz_gecis_imleci_bozmaz(self):
        """Bozuk bir satır imleci bilinmez hale getirmemeli."""
        api = SahteAPI(
            sayfalar=[
                [
                    {"anomali_id": "an_X", "alan": "seviye", "onceki": "izle", "yeni": "kritik"},
                    gecis(700, "an_Y", "izle", "kritik"),
                ]
            ]
        )
        sms = SahteKanal("sms")
        yon = self.yonetici(api=api, sms=sms)
        with self.assertLogs("alarm", level="ERROR"):
            yon.poll_transitions()

        self.assertEqual(yon.state["son_gecis_id"], 700)
        self.assertEqual([b.gecis_id for b in sms.cagrilar], [700])

    def test_yeniden_deneme_zamani_gelmeden_denenmez(self):
        sms = SahteKanal("sms", sonuclar=[HATA])
        api = SahteAPI(sayfalar=[[gecis(101, "an_A", "izle", "kritik")], [], []])
        yon = self.yonetici(
            api=api, sms=sms, yeniden_deneme_taban=3600, yeniden_deneme_tavan=3600
        )
        yon.poll_transitions()
        self.assertEqual(len(sms.cagrilar), 1)
        yon.poll_transitions()
        self.assertEqual(len(sms.cagrilar), 1)  # geri çekilme süresi dolmadı
        self.assertIn("101", yon.state["bekleyen"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
