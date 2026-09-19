# kanallar.py
"""Bildirim kanalları ve seviye->kanal kuralı.

A-01'in çekirdeği burada: `gonder` üç ayrı sonuç döndürür ve çağıran bu üçünü
karıştıramaz.

* `TESLIM`            — kanal olumlu yanıt verdi.
* `HATA`              — kanal reddetti ya da ulaşılamadı; yeniden denenebilir.
* `YAPILANDIRILMAMIS` — kanalın ayarı yok; deneme bile yapılmadı.

Loga yazmak teslim değildir: `KonsolKanali` hiçbir kuralda *zorunlu*
işaretlenmez, bu yüzden tek başına bir olayı "teslim edildi" yapamaz.

A-03 / public cloud: karar kaydı §T6 public cloud'u yasaklıyor, §12 not'u
WhatsApp Business API'nin bir bulut hizmeti olduğunu ve tutarlı çözümün yerel
GSM/SMS modemi ya da on-prem SMS gateway olduğunu söylüyor. Bu yüzden
`SmsGatewayKanali` belirli bir ürüne değil, yapılandırılabilir bir yerel HTTP
uç noktasına yazar: Android SMS Gateway, yerel bir GSM modem servisi ya da
kurum içi bir gateway aynı adaptörle sürülür. `TelegramKanali` çalışır durumda
bırakıldı ama `bulut = True` ile işaretli ve açıldığında servis başlangıçta
bunun kısıtla çeliştiğini yüksek sesle söyler.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

import requests

_GUNLUK = logging.getLogger("alarm.kanal")

TESLIM = "teslim"
HATA = "hata"
YAPILANDIRILMAMIS = "yapilandirilmamis"

SEVIYE_DERECESI = {"normal": 0, "izle": 1, "uyari": 2, "kritik": 3}


@dataclass
class Bildirim:
    """Tek bir geçişten üretilen bildirim.

    `modul_id` ve `gerekce` `Optional`: detay API'si yanıt vermediğinde bunlar
    *yok*, "Bilinmeyen Modül" değil (A-05). `detay_alindi` bu ayrımı taşır ve
    mesaj metnine eksikliğin kendisi yazılır.
    """

    gecis_id: int
    anomali_id: Optional[str]
    seviye: str
    onceki_seviye: str
    zaman: str
    modul_id: Optional[str] = None
    gerekce: Optional[str] = None
    skor: Optional[float] = None
    detay_alindi: bool = False

    def olay_adi(self) -> str:
        if self.modul_id:
            return self.modul_id
        if self.anomali_id:
            return f"olay {self.anomali_id}"
        return f"geçiş #{self.gecis_id}"

    def kisa_metin(self) -> str:
        """SMS için sığ ve tek parça metin."""
        parcalar = [
            f"GRID UP {self.seviye.upper()}",
            self.modul_id or "modul: BILINMIYOR",
            f"olay {self.anomali_id or '?'}",
            f"{self.onceki_seviye}->{self.seviye}",
            self.zaman,
        ]
        if self.skor is not None:
            parcalar.append(f"skor %{int(self.skor * 100)}")
        if self.gerekce:
            parcalar.append(self.gerekce[:80])
        if not self.detay_alindi:
            parcalar.append("DETAY ALINAMADI")
        return " | ".join(parcalar)


@dataclass
class KanalSonucu:
    kanal: str
    durum: str
    detay: str = ""

    @property
    def basarili(self) -> bool:
        return self.durum == TESLIM


class Kanal:
    ad = "kanal"
    bulut = False

    def yapilandirildi_mi(self) -> bool:
        raise NotImplementedError

    def gonder(self, bildirim: Bildirim) -> KanalSonucu:
        raise NotImplementedError


class KonsolKanali(Kanal):
    """Her zaman açık, her zaman başarılı — ve hiçbir zaman dış bildirim.

    Kuralda zorunlu işaretlenmediği sürece tek başına bir olayı teslim
    edilmiş yapamaz; kritik alarmın yalnız konsola yazılması dış bildirim
    sayılmaz.
    """

    ad = "konsol"

    def yapilandirildi_mi(self) -> bool:
        return True

    def gonder(self, bildirim: Bildirim) -> KanalSonucu:
        skor_bilgisi = (
            f" (skor %{int(bildirim.skor * 100)})" if bildirim.skor is not None else ""
        )
        satirlar = [
            f"🚨 [GRID UP ALARM] {bildirim.olay_adi()} "
            f"[{bildirim.seviye.upper()}] (önceki: {bildirim.onceki_seviye})"
            f"{skor_bilgisi}",
            f"   Geçiş #{bildirim.gecis_id} | Olay ID: {bildirim.anomali_id or '-'} "
            f"| Zaman: {bildirim.zaman}",
        ]
        if bildirim.detay_alindi:
            satirlar.append(f"   Gerekçe: {bildirim.gerekce or '-'}")
        else:
            satirlar.append(
                "   Gerekçe: DETAY ALINAMADI — /anomaliler/{id} yanıt vermedi, "
                "modül ve gerekçe bu bildirimde yok."
            )
        _GUNLUK.info("\n".join(satirlar))
        return KanalSonucu(self.ad, TESLIM, "loga yazıldı")


class SmsGatewayKanali(Kanal):
    """On-prem HTTP SMS gateway adaptörü.

    Yük biçimi alan adlarıyla ayarlanabilir, çünkü seçilecek gateway henüz
    kesinleşmedi: Android SMS Gateway `phoneNumbers`/`message`, kurum içi bir
    gateway başka bir şey bekleyebilir. Ürün seçimi buraya gömülmüyor.

    Gönderimin "kabul edildi" olması SMS'in gerçekten abonesine ulaştığı
    anlamına gelmez; gateway'in kabulü ile operatörün telefonundaki teslim iki
    ayrı aşamadır ve bu kanal yalnız birincisini görebilir.
    """

    ad = "sms"

    def __init__(
        self,
        url: str = "",
        alicilar: Optional[list] = None,
        token: str = "",
        kullanici: str = "",
        parola: str = "",
        alici_alani: str = "alicilar",
        mesaj_alani: str = "mesaj",
        zaman_asimi: float = 10.0,
        oturum=None,
    ):
        self.url = (url or "").strip()
        self.alicilar = [a.strip() for a in (alicilar or []) if a and a.strip()]
        self.token = (token or "").strip()
        self.kullanici = (kullanici or "").strip()
        self.parola = parola or ""
        self.alici_alani = alici_alani
        self.mesaj_alani = mesaj_alani
        self.zaman_asimi = zaman_asimi
        self.oturum = oturum or requests

    def yapilandirildi_mi(self) -> bool:
        return bool(self.url and self.alicilar)

    def eksikler(self) -> list:
        eksik = []
        if not self.url:
            eksik.append("SMS_GATEWAY_URL")
        if not self.alicilar:
            eksik.append("SMS_ALICILAR")
        return eksik

    def gonder(self, bildirim: Bildirim) -> KanalSonucu:
        if not self.yapilandirildi_mi():
            return KanalSonucu(
                self.ad,
                YAPILANDIRILMAMIS,
                "eksik ayar: " + ", ".join(self.eksikler()),
            )

        yuk = {
            self.alici_alani: self.alicilar,
            self.mesaj_alani: bildirim.kisa_metin(),
        }
        basliklar = {}
        kimlik = None
        if self.token:
            basliklar["Authorization"] = f"Bearer {self.token}"
        elif self.kullanici:
            kimlik = (self.kullanici, self.parola)

        try:
            yanit = self.oturum.post(
                self.url,
                json=yuk,
                headers=basliklar or None,
                auth=kimlik,
                timeout=self.zaman_asimi,
            )
        except Exception as hata:  # requests'in tüm ağ hataları
            return KanalSonucu(self.ad, HATA, f"{type(hata).__name__}: {hata}")

        kod = getattr(yanit, "status_code", 0)
        if 200 <= kod < 300:
            return KanalSonucu(self.ad, TESLIM, f"gateway kabul etti (HTTP {kod})")
        govde = str(getattr(yanit, "text", ""))[:200]
        return KanalSonucu(self.ad, HATA, f"HTTP {kod}: {govde}")


class TelegramKanali(Kanal):
    """Telegram Bot API.

    `bulut = True`: api.telegram.org kurum dışı bir bulut hizmetidir ve karar
    kaydının public cloud yasağıyla çelişir. Silinmedi çünkü demo için
    çalışıyor, ama varsayılan kuralda yok ve açıldığında servis bunu
    başlangıçta uyarı olarak yazar.
    """

    ad = "telegram"
    bulut = True

    def __init__(self, token: str = "", chat_id: str = "", zaman_asimi: float = 10.0, oturum=None):
        self.token = (token or "").strip()
        self.chat_id = (chat_id or "").strip()
        self.zaman_asimi = zaman_asimi
        self.oturum = oturum or requests

    def yapilandirildi_mi(self) -> bool:
        return bool(self.token and self.chat_id)

    def eksikler(self) -> list:
        eksik = []
        if not self.token:
            eksik.append("TELEGRAM_BOT_TOKEN")
        if not self.chat_id:
            eksik.append("TELEGRAM_CHAT_ID")
        return eksik

    def gonder(self, bildirim: Bildirim) -> KanalSonucu:
        if not self.yapilandirildi_mi():
            return KanalSonucu(
                self.ad, YAPILANDIRILMAMIS, "eksik ayar: " + ", ".join(self.eksikler())
            )

        import html

        if bildirim.detay_alindi:
            gerekce_satiri = (
                f"💡 <b>Gerekçe:</b>\n<i>{html.escape(bildirim.gerekce or '-')}</i>"
            )
        else:
            gerekce_satiri = (
                "⚠️ <b>Detay alınamadı</b> — modül ve gerekçe bu bildirimde yok."
            )
        skor_satiri = (
            f"📊 <b>Skor:</b> <code>%{int(bildirim.skor * 100)}</code>\n"
            if bildirim.skor is not None
            else ""
        )
        modul_satiri = (
            f"📍 <b>Modül:</b> <code>{html.escape(bildirim.modul_id)}</code>\n"
            if bildirim.modul_id
            else "📍 <b>Modül:</b> <code>bilinmiyor</code>\n"
        )
        mesaj = (
            f"🚨 <b>GRID UP ARIZA ALARMI ({bildirim.seviye.upper()})</b>\n\n"
            f"{modul_satiri}"
            f"🆔 <b>Olay:</b> <code>{html.escape(str(bildirim.anomali_id or '-'))}</code>\n"
            f"📈 <b>Geçiş:</b> <code>{bildirim.onceki_seviye} ➔ {bildirim.seviye}</code>\n"
            f"⏱️ <b>Zaman:</b> <code>{html.escape(str(bildirim.zaman))}</code>\n"
            f"{skor_satiri}\n"
            f"{gerekce_satiri}"
        )
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            yanit = self.oturum.post(
                url,
                json={"chat_id": self.chat_id, "text": mesaj, "parse_mode": "HTML"},
                timeout=self.zaman_asimi,
            )
        except Exception as hata:
            return KanalSonucu(self.ad, HATA, f"{type(hata).__name__}: {hata}")

        kod = getattr(yanit, "status_code", 0)
        if 200 <= kod < 300:
            return KanalSonucu(self.ad, TESLIM, f"HTTP {kod}")
        govde = str(getattr(yanit, "text", ""))[:200]
        return KanalSonucu(self.ad, HATA, f"HTTP {kod}: {govde}")


@dataclass
class KanalKurali:
    """Bir seviye için denenecek kanallar ve bunlardan hangilerinin zorunlu olduğu."""

    seviye: str
    kanallar: tuple = ()
    zorunlular: frozenset = field(default_factory=frozenset)


VARSAYILAN_KURAL = "uyari:konsol,sms|kritik:konsol,sms!"


def kanal_kurali_coz(metin: str) -> dict:
    """`"uyari:konsol,sms|kritik:konsol,sms!"` -> {seviye: KanalKurali}.

    Sondaki `!` o kanalı zorunlu yapar: başarısız olursa olay teslim edilmiş
    sayılmaz ve yeniden denenir. Kuralda adı geçmeyen seviye hiç bildirim
    üretmez.
    """
    kurallar = {}
    for parca in (metin or "").split("|"):
        parca = parca.strip()
        if not parca:
            continue
        seviye, ayrac, kanal_listesi = parca.partition(":")
        seviye = seviye.strip().lower()
        if not ayrac:
            raise ValueError(f"kural parçasında ':' yok: {parca!r}")
        if seviye not in SEVIYE_DERECESI:
            raise ValueError(f"bilinmeyen seviye: {seviye!r}")

        adlar, zorunlular = [], set()
        for ham in kanal_listesi.split(","):
            ad = ham.strip().lower()
            if not ad:
                continue
            if ad.endswith("!"):
                ad = ad[:-1].strip()
                zorunlular.add(ad)
            if not ad:
                raise ValueError(f"boş kanal adı: {parca!r}")
            adlar.append(ad)
        if not adlar:
            raise ValueError(f"kuralda kanal yok: {parca!r}")
        kurallar[seviye] = KanalKurali(seviye, tuple(adlar), frozenset(zorunlular))
    if not kurallar:
        raise ValueError("kanal kuralı boş")
    return kurallar


def ortamdan_kanallar(ortam=None) -> dict:
    """Ortam değişkenlerinden kanal sözlüğü kurar."""
    ortam = os.environ if ortam is None else ortam
    alicilar = [
        p.strip() for p in ortam.get("SMS_ALICILAR", "").split(",") if p.strip()
    ]
    return {
        KonsolKanali.ad: KonsolKanali(),
        SmsGatewayKanali.ad: SmsGatewayKanali(
            url=ortam.get("SMS_GATEWAY_URL", ""),
            alicilar=alicilar,
            token=ortam.get("SMS_GATEWAY_TOKEN", ""),
            kullanici=ortam.get("SMS_GATEWAY_KULLANICI", ""),
            parola=ortam.get("SMS_GATEWAY_PAROLA", ""),
            alici_alani=ortam.get("SMS_GATEWAY_ALICI_ALANI", "alicilar"),
            mesaj_alani=ortam.get("SMS_GATEWAY_MESAJ_ALANI", "mesaj"),
        ),
        TelegramKanali.ad: TelegramKanali(
            token=ortam.get("TELEGRAM_BOT_TOKEN", ""),
            chat_id=ortam.get("TELEGRAM_CHAT_ID", ""),
        ),
    }
