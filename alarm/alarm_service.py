# alarm_service.py
"""
Grid Up Hackathon - İZ C: Alarm ve Bildirim Servisi

Sözleşme ⑤'in küresel geçiş akışını (`GET /gecisler?sonra=&limit=`) tüketir,
seviye yükselmelerinden hangisinin dış bildirim gerektirdiğine karar verir,
bildirimin *sonucunu* izler ve bitmemiş işi yeniden başlatmaya dayanacak
şekilde saklar.

Tasarımın üç taşıyıcı kararı:

1. Teslim üç durumludur (bkz. `kanallar.py`). "Loglandı", "kanal kabul etti" ve
   "operatörün telefonuna düştü" aynı şey değildir; kod yalnız ilk ikisini
   görebilir ve üçüncüsünü iddia etmez.

2. `son_gecis_id` bir *çekme* imlecidir, bir "buraya kadar bitti" işareti
   değil. Teslim edilemeyen geçiş `bekleyen` kuyruğuna tam gövdesiyle taşınır
   ve imleçle aynı dosyada, aynı atomik yazımla kalıcılaşır. Böylece imleç
   ileri gider (kalıcı olarak başarısız tek bir olay arkasındaki kritik
   alarmları rehin almaz) ama başarısız geçiş atlanmış olmaz.

3. Tekrar önleme anahtarı olaydır, modül değil: `anomali_id` + hedef seviye.
   Aynı moduldeki iki ayrı anomali birbirini bastırmaz ve `uyari -> kritik`
   yükselmesi önceki `uyari` bildiriminin bekleme süresine takılmaz.

Kabul edilen sınır: kanal olumlu yanıt verdikten sonra, durum diske inmeden
süreç ölürse o bildirim yeniden gönderilebilir. Tekrar bildirim ile sessiz
alarm kaybı arasında tercih yapılmıştır; tekrar bildirim seçilmiştir.
"""

from __future__ import annotations

import copy
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

from durum import BozukDurumHatasi, DurumDeposu, DurumYazmaHatasi
from kanallar import (
    SEVIYE_DERECESI,
    TESLIM,
    VARSAYILAN_KURAL,
    YAPILANDIRILMAMIS,
    Bildirim,
    kanal_kurali_coz,
    ortamdan_kanallar,
)

# Türkiye Saati (UTC+3)
TZ_TR = timezone(timedelta(hours=3))


def get_tr_time() -> str:
    return datetime.now(TZ_TR).strftime("%Y-%m-%d %H:%M:%S")


try:
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.stderr.encoding != "utf-8":
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")
_GUNLUK = logging.getLogger("alarm")

# Ortam değişkenleri (Madde 15: repoda gömülü anahtar yok)
API_URL = os.getenv("API_URL", "http://localhost:8080").rstrip("/")
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "300"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))
SAYFA_BOYUTU = int(os.getenv("ALARM_SAYFA_BOYUTU", "100"))
STATE_FILE = os.getenv("ALARM_STATE_FILE", os.path.join(os.path.dirname(__file__), "alarm_state.json"))
BOZUK_DURUM = os.getenv("ALARM_BOZUK_DURUM", "dur")
KANAL_KURALI = os.getenv("ALARM_KANAL_KURALI", VARSAYILAN_KURAL)
YENIDEN_DENEME_TABAN = int(os.getenv("ALARM_YENIDEN_DENEME_TABAN", "30"))
YENIDEN_DENEME_TAVAN = int(os.getenv("ALARM_YENIDEN_DENEME_TAVAN", "900"))
BEKLEYEN_SINIRI = int(os.getenv("ALARM_BEKLEYEN_SINIRI", "500"))

# Geçiş değerlendirme sonuçları
ILGISIZ = "ilgisiz"          # bildirim gerektirmiyor (alan/seviye kuralı dışı)
BASTIRILDI = "bastirildi"    # bilinçli tekrar önleme
TESLIM_EDILDI = "teslim"     # zorunlu kanalların hepsi olumlu yanıt verdi
BASARISIZ = "basarisiz"      # zorunlu kanal başarısız/yapılandırılmamış


class AlarmManager:
    def __init__(
        self,
        api_url=API_URL,
        cooldown_seconds=COOLDOWN_SECONDS,
        state_file=STATE_FILE,
        kanallar=None,
        kanal_kurali=None,
        bozuk_politika=BOZUK_DURUM,
        sayfa_boyutu=SAYFA_BOYUTU,
        yeniden_deneme_taban=YENIDEN_DENEME_TABAN,
        yeniden_deneme_tavan=YENIDEN_DENEME_TAVAN,
        bekleyen_siniri=BEKLEYEN_SINIRI,
        oturum=None,
    ):
        self.api_url = api_url.rstrip("/")
        self.cooldown = cooldown_seconds
        self.state_file = state_file
        self.sayfa_boyutu = sayfa_boyutu
        self.yeniden_deneme_taban = yeniden_deneme_taban
        self.yeniden_deneme_tavan = yeniden_deneme_tavan
        self.bekleyen_siniri = bekleyen_siniri
        self.oturum = oturum or requests

        self.kanallar = ortamdan_kanallar() if kanallar is None else kanallar
        self.kurallar = kanal_kurali_coz(
            KANAL_KURALI if kanal_kurali is None else kanal_kurali
        )

        self.depo = DurumDeposu(state_file, bozuk_politika=bozuk_politika)
        self.state = self.depo.yukle()
        # Son kalıcı anlık görüntü: yazma başarısız olursa belleği buna döneriz,
        # böylece diske inmemiş bir imleçle çalışmaya devam etmeyiz (A-04).
        self._kalici = copy.deepcopy(self.state)
        _GUNLUK.info(
            "📂 Durum yüklendi: son_gecis_id=%s, bekleyen=%d, cooldown kaydı=%d",
            self.state.get("son_gecis_id"),
            len(self.state.get("bekleyen", {})),
            len(self.state.get("son_bildirim", {})),
        )

    # ------------------------------------------------------------------
    # Yapılandırma görünürlüğü
    # ------------------------------------------------------------------

    def yapilandirma_uyarilari(self) -> list:
        """Başlangıçta yazılan uyarılar.

        Zorunlu bir kanalın ayarı yoksa bunu *açılışta* söylemek gerekir;
        ilk kritik alarma kadar beklemek, sorunu tam da onu bilmenin en pahalı
        olduğu ana erteler (A-03).
        """
        uyarilar = []
        for seviye, kural in sorted(self.kurallar.items()):
            for ad in kural.kanallar:
                kanal = self.kanallar.get(ad)
                if kanal is None:
                    uyarilar.append(
                        f"Kuralda tanımsız kanal adı var: {seviye} -> {ad!r}. "
                        f"Bilinen kanallar: {sorted(self.kanallar)}"
                    )
                    continue
                if not kanal.yapilandirildi_mi():
                    agirlik = "ZORUNLU" if ad in kural.zorunlular else "opsiyonel"
                    uyarilar.append(
                        f"{seviye} seviyesinde {agirlik} kanal '{ad}' "
                        f"yapılandırılmamış ({', '.join(getattr(kanal, 'eksikler', lambda: [])()) or 'ayar yok'})."
                        + (
                            " Bu seviyedeki olaylar dış bildirim ALMAYACAK, teslim "
                            "edilmiş sayılmayacak ve bekleyen kuyruğunda birikecek."
                            if ad in kural.zorunlular
                            else ""
                        )
                    )
                if getattr(kanal, "bulut", False) and kanal.yapilandirildi_mi():
                    uyarilar.append(
                        f"'{ad}' kanalı kurum dışı bir bulut hizmeti kullanıyor. "
                        "Karar kaydı §T6 public cloud'u yasaklıyor; bu kanalın açık "
                        "olması o kısıtla çelişir ve ekip kararı gerektirir."
                    )
        # Hiçbir seviyede dış (konsol olmayan) zorunlu kanal yoksa bu da bir uyarıdır.
        dis_zorunlu = {
            ad
            for kural in self.kurallar.values()
            for ad in kural.zorunlular
            if ad != "konsol"
        }
        if not dis_zorunlu:
            uyarilar.append(
                "Hiçbir seviyede zorunlu dış bildirim kanalı yok. Kritik alarm yalnız "
                "loga yazılacak; bu karar kaydı §T7'nin beklediği acil bildirim değildir."
            )
        return uyarilar

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def fetch_anomaly_detail(self, anomali_id):
        """Detayı çeker. `(detay, alindi_mi)` döner.

        İkinci değer önemli: `None` detay ile "detay alındı ama modül boş"
        farkını çağıranın görmesi gerekiyor, yoksa A-05'teki uydurma modül
        adına geri dönülür.
        """
        url = f"{self.api_url}/anomaliler/{anomali_id}"
        try:
            res = self.oturum.get(url, timeout=5)
            if getattr(res, "status_code", 0) == 200:
                return res.json(), True
            _GUNLUK.warning("Anomali detayı HTTP %s (%s)", res.status_code, anomali_id)
        except Exception as hata:
            _GUNLUK.warning("Anomali detayı alınamadı (%s): %s", anomali_id, hata)
        return None, False

    # ------------------------------------------------------------------
    # Tekrar önleme
    # ------------------------------------------------------------------

    @staticmethod
    def bastirma_anahtari(gecis: dict, yeni_seviye: str) -> str:
        """Tekrar önleme anahtarı: olay kimliği + hedef seviye.

        `anomali_id` geçişin kendisinde gelir ve detay API'sine bağlı değildir
        (A-05). Yine de yoksa anahtar geçiş id'sine düşer: geçiş id'leri
        tekildir, yani hiçbir şeyi bastırmaz. Alarm tarafında şüphede kalmak
        bastırma yönünde değil, bildirme yönünde çözülür.
        """
        anomali_id = gecis.get("anomali_id")
        if anomali_id:
            return f"anomali:{anomali_id}|seviye:{yeni_seviye}"
        return f"gecis:{gecis.get('id')}"

    def bastirilmali_mi(self, anahtar: str, simdi: float):
        son = self.state.setdefault("son_bildirim", {}).get(anahtar)
        if son is None:
            return False, 0
        gecen = simdi - son
        if gecen < self.cooldown:
            return True, int(self.cooldown - gecen)
        return False, 0

    # ------------------------------------------------------------------
    # Değerlendirme ve gönderim
    # ------------------------------------------------------------------

    def evaluate_transition(self, gecis: dict) -> str:
        """Tek bir geçişi değerlendirir ve sonucunu döndürür.

        Dönüş değeri çağıranın imleç/kuyruk kararını sürer; `None` dönmez,
        çünkü "bildirim gerekmiyordu" ile "gönderemedim" arasındaki farkın
        kaybolması A-01'in ta kendisiydi.
        """
        if gecis.get("alan") != "seviye":
            return ILGISIZ

        onceki = str(gecis.get("onceki") or "normal").lower()
        yeni = str(gecis.get("yeni") or "normal").lower()
        onceki_puan = SEVIYE_DERECESI.get(onceki, 0)
        yeni_puan = SEVIYE_DERECESI.get(yeni, 0)

        if not (yeni_puan > onceki_puan and yeni in self.kurallar):
            return ILGISIZ

        simdi = time.time()
        anahtar = self.bastirma_anahtari(gecis, yeni)
        bastir, kalan = self.bastirilmali_mi(anahtar, simdi)
        if bastir:
            _GUNLUK.info(
                "⏳ [TEKRAR ÖNLEME] %s için eşdeğer bildirim %d sn daha bastırılıyor. "
                "Geçiş #%s atlandı (bilinçli bastırma, kanal hatası değil).",
                anahtar,
                kalan,
                gecis.get("id"),
            )
            return BASTIRILDI

        anomali_id = gecis.get("anomali_id")
        detay, detay_alindi = (
            self.fetch_anomaly_detail(anomali_id) if anomali_id else (None, False)
        )
        detay = detay or {}

        bildirim = Bildirim(
            gecis_id=gecis.get("id"),
            anomali_id=anomali_id,
            seviye=yeni,
            onceki_seviye=onceki,
            zaman=gecis.get("zaman") or get_tr_time(),
            modul_id=detay.get("modul_id") if detay_alindi else None,
            gerekce=(detay.get("gerekce") if detay_alindi else None)
            or (f"Seviye geçişi: {onceki} -> {yeni}" if detay_alindi else None),
            skor=detay.get("skor") if detay_alindi else None,
            detay_alindi=detay_alindi,
        )

        sonuc = self.emit_notification(bildirim, self.kurallar[yeni])
        if sonuc == TESLIM_EDILDI:
            # Cooldown yalnız gerçek teslimde başlar: başarısız bir gönderim
            # kendi yeniden denemesini bastıramaz (A-02).
            self.state.setdefault("son_bildirim", {})[anahtar] = simdi
        return sonuc

    def emit_notification(self, bildirim: Bildirim, kural) -> str:
        """Bildirimi kuraldaki kanallara dağıtır ve teslim kararını döndürür."""
        sonuclar = []
        for ad in kural.kanallar:
            kanal = self.kanallar.get(ad)
            if kanal is None:
                _GUNLUK.error("Tanımsız kanal adı kuralda: %r", ad)
                sonuclar.append((ad, YAPILANDIRILMAMIS, "kanal tanımlı değil"))
                continue
            sonuc = kanal.gonder(bildirim)
            sonuclar.append((ad, sonuc.durum, sonuc.detay))
            if sonuc.durum == TESLIM:
                _GUNLUK.info("✅ %s: %s", ad, sonuc.detay)
            elif sonuc.durum == YAPILANDIRILMAMIS:
                _GUNLUK.warning("⚙️ %s kanalı yapılandırılmamış: %s", ad, sonuc.detay)
            else:
                _GUNLUK.error("❌ %s gönderimi başarısız: %s", ad, sonuc.detay)

        durumlar = {ad: durum for ad, durum, _ in sonuclar}
        eksik_zorunlular = [
            ad for ad in kural.zorunlular if durumlar.get(ad) != TESLIM
        ]
        if eksik_zorunlular:
            _GUNLUK.error(
                "🚨 Geçiş #%s (%s, %s) TESLİM EDİLEMEDİ: zorunlu kanal(lar) %s. "
                "Olay bekleyen kuyruğuna alınıyor, cooldown başlatılmıyor.",
                bildirim.gecis_id,
                bildirim.anomali_id,
                bildirim.seviye,
                ", ".join(f"{ad}={durumlar.get(ad)}" for ad in eksik_zorunlular),
            )
            return BASARISIZ
        return TESLIM_EDILDI

    # ------------------------------------------------------------------
    # Bekleyen kuyruğu
    # ------------------------------------------------------------------

    def _bekleyene_al(self, gecis: dict, simdi: float):
        bekleyen = self.state.setdefault("bekleyen", {})
        anahtar = str(gecis.get("id"))
        kayit = bekleyen.get(anahtar) or {"gecis": gecis, "deneme": 0}
        kayit["gecis"] = gecis
        kayit["deneme"] = int(kayit.get("deneme", 0)) + 1
        gecikme = min(
            self.yeniden_deneme_taban * (2 ** (kayit["deneme"] - 1)),
            self.yeniden_deneme_tavan,
        )
        kayit["sonraki_deneme"] = simdi + gecikme
        bekleyen[anahtar] = kayit

        if len(bekleyen) > self.bekleyen_siniri:
            # En eski geçişi düşürmek zorundayız; sessizce değil.
            dusen = min(bekleyen, key=lambda k: int(k))
            bekleyen.pop(dusen, None)
            self.state["dusen_bildirim"] = int(self.state.get("dusen_bildirim", 0)) + 1
            _GUNLUK.error(
                "🚨 Bekleyen bildirim kuyruğu %d sınırını aştı; geçiş #%s KALICI OLARAK "
                "DÜŞÜRÜLDÜ ve hiç teslim edilmedi. Toplam düşen: %d. Kanal "
                "yapılandırmasını kontrol edin.",
                self.bekleyen_siniri,
                dusen,
                self.state["dusen_bildirim"],
            )

    def bekleyenleri_dene(self, simdi=None) -> int:
        """Zamanı gelmiş bekleyen bildirimleri yeniden dener."""
        simdi = time.time() if simdi is None else simdi
        bekleyen = self.state.setdefault("bekleyen", {})
        if not bekleyen:
            return 0

        denenen = 0
        for anahtar in sorted(bekleyen, key=lambda k: int(k)):
            kayit = bekleyen.get(anahtar)
            if kayit is None or kayit.get("sonraki_deneme", 0) > simdi:
                continue
            denenen += 1
            gecis = kayit.get("gecis") or {}
            _GUNLUK.info(
                "🔁 Bekleyen geçiş #%s yeniden deneniyor (deneme %s).",
                anahtar,
                kayit.get("deneme"),
            )
            sonuc = self.evaluate_transition(gecis)
            if sonuc == BASARISIZ:
                self._bekleyene_al(gecis, simdi)
            else:
                bekleyen.pop(anahtar, None)
        return denenen

    # ------------------------------------------------------------------
    # Kalıcılık
    # ------------------------------------------------------------------

    def save_state(self) -> bool:
        """Durumu yazar. Başarısızlıkta belleği son kalıcı hale geri alır.

        Geri alma şart: yazamadığımız bir imleçle devam edersek, bu turda
        işlenen geçişler bellekte "bitti" olur ama diskte hiç olmaz. Süreç
        ölünce o aralık ne yeniden denenir ne de bildirilmiştir — tam olarak
        sessiz alarm kaybı.
        """
        try:
            self.depo.kaydet(self.state)
        except DurumYazmaHatasi as hata:
            _GUNLUK.error(
                "🚨 Durum yazılamadı (%s). Bellek son kalıcı duruma geri alınıyor "
                "(son_gecis_id=%s); bu turdaki geçişler yeniden işlenecek ve bir "
                "tekrar bildirim görülebilir. İşleme başarılı sayılmadı.",
                hata,
                self._kalici.get("son_gecis_id"),
            )
            self.state = copy.deepcopy(self._kalici)
            return False
        self._kalici = copy.deepcopy(self.state)
        return True

    # ------------------------------------------------------------------
    # Akış
    # ------------------------------------------------------------------

    def poll_transitions(self):
        """Önce bekleyenleri dener, sonra yeni sayfayı çeker."""
        degisti = self.bekleyenleri_dene() > 0

        params = {"limit": self.sayfa_boyutu}
        son_id = self.state.get("son_gecis_id")
        if son_id is not None:
            params["sonra"] = son_id

        url = f"{self.api_url}/gecisler"
        try:
            res = self.oturum.get(url, params=params, timeout=5)
            if getattr(res, "status_code", 0) != 200:
                _GUNLUK.warning(
                    "⚠️ /gecisler HTTP %s döndü: %s",
                    res.status_code,
                    str(getattr(res, "text", ""))[:200],
                )
                if degisti:
                    self.save_state()
                return

            veriler = (res.json() or {}).get("veriler", []) or []
            simdi = time.time()
            for gecis in veriler:
                gecis_id = gecis.get("id")
                if not isinstance(gecis_id, int):
                    # İmleç bu satırın id'si üzerine kurulu; id yoksa ilerletmek
                    # sonraki sayfanın nereden başlayacağını bilinmez yapar.
                    _GUNLUK.error(
                        "Geçiş kaydında geçerli 'id' yok, atlanıyor: %r", gecis
                    )
                    continue
                sonuc = self.evaluate_transition(gecis)
                if sonuc == BASARISIZ:
                    # İmleç ilerler ama geçiş atlanmaz: tam gövdesiyle
                    # bekleyen kuyruğunda, imleçle aynı atomik yazımda.
                    self._bekleyene_al(gecis, simdi)
                self.state["son_gecis_id"] = gecis_id
                degisti = True

            if degisti:
                self.save_state()
            if veriler:
                _GUNLUK.debug(
                    "İşlenen geçiş: %d, son_gecis_id=%s, bekleyen=%d",
                    len(veriler),
                    self.state.get("son_gecis_id"),
                    len(self.state.get("bekleyen", {})),
                )

        except requests.exceptions.ConnectionError:
            _GUNLUK.debug("🔌 API sunucusuna ulaşılamıyor (%s). Yeniden denenecek...", url)
            if degisti:
                self.save_state()
        except Exception as hata:
            _GUNLUK.error("Geçiş akışı sorgulama hatası: %s", hata)
            if degisti:
                self.save_state()


def run_service():
    _GUNLUK.info("🚀 Grid Up Alarm Servisi Başlatıldı.")
    _GUNLUK.info("📡 API Hedefi: %s", API_URL)
    _GUNLUK.info(
        "⏱️ Tekrar önleme: %s sn | Sorgu aralığı: %s sn | Durum: %s",
        COOLDOWN_SECONDS,
        POLL_INTERVAL,
        STATE_FILE,
    )
    _GUNLUK.info("📋 Seviye→kanal kuralı: %s", KANAL_KURALI)

    try:
        manager = AlarmManager()
    except BozukDurumHatasi:
        _GUNLUK.error("Bozuk durum dosyası nedeniyle servis başlatılmadı.")
        raise SystemExit(2)
    except ValueError as hata:
        _GUNLUK.error("Kanal kuralı çözümlenemedi (ALARM_KANAL_KURALI): %s", hata)
        raise SystemExit(2)

    for uyari in manager.yapilandirma_uyarilari():
        _GUNLUK.warning("⚠️ %s", uyari)

    while True:
        manager.poll_transitions()
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run_service()
