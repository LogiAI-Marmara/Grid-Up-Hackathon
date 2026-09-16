"""The sentence the operator reads.

Contract 3 makes `gerekce` mandatory and non-empty, and section 4.2 explains why
that single requirement decides the detection method: an operator who cannot see
why an alarm fired stops trusting the system and switches it off. "Model said
0.87" cannot be written here, which is most of the argument against putting a
model in the core.

Every template is a function that takes the triggering layer's actual numbers and
returns one Turkish sentence. Three rules hold for all of them:

1. Real numbers, never adjectives. "+27.3 C in 6 hours", not "a significant rise".
2. Say what did *not* change, when that is the finding. "current unchanged
   (310 -> 308 A)" is the whole reason a temperature rise means resistance.
3. End with the physical interpretation, because that is what turns a number into
   a work order.

Text is Turkish because an operator reads it; identifiers and comments are not.
"""

from __future__ import annotations

from .sozlesme import OlcumTipi

__all__ = [
    "sayi",
    "kalite_bozuk",
    "donuk_sensor",
    "aralik_disi",
    "modul_sessiz",
    "saat_kaymasi",
    "ileri_tarihli",
    "besleme_kaybi",
    "sinyal_zayif",
    "mutlak_sicaklik",
    "mutlak_ortam",
    "mutlak_nem",
    "mutlak_faz",
    "ark_olayi",
    "taban_sapmasi",
    "taban_egilimi",
    "akim_sicaklik",
    "faz_faz",
    "komsu_piksel",
    "modul_modul",
]

#: Human-readable channel names. `termal_maks` is a column name; "hot spot" is
#: what the person holding the work order is looking for.
KANAL_ADI: dict[OlcumTipi, str] = {
    OlcumTipi.ORTAM_SICAKLIK: "ortam sıcaklığı",
    OlcumTipi.NEM: "bağıl nem",
    OlcumTipi.AKIM_L1: "L1 akımı",
    OlcumTipi.AKIM_L2: "L2 akımı",
    OlcumTipi.AKIM_L3: "L3 akımı",
    OlcumTipi.AKIM_NOTR: "nötr akımı",
    OlcumTipi.TERMAL_MAKS: "sıcak nokta",
    OlcumTipi.TERMAL_ORT: "yüzey ortalama sıcaklığı",
    OlcumTipi.ARK_OLAY: "ark sayacı",
}

BIRIM_ADI: dict[OlcumTipi, str] = {
    OlcumTipi.ORTAM_SICAKLIK: "°C",
    OlcumTipi.NEM: "%",
    OlcumTipi.AKIM_L1: "A",
    OlcumTipi.AKIM_L2: "A",
    OlcumTipi.AKIM_L3: "A",
    OlcumTipi.AKIM_NOTR: "A",
    OlcumTipi.TERMAL_MAKS: "°C",
    OlcumTipi.TERMAL_ORT: "°C",
    OlcumTipi.ARK_OLAY: "olay",
}


def sayi(deger: float, basamak: int = 1) -> str:
    """Format a number for an operator: fixed decimals, no scientific notation.

    Trailing ".0" is kept rather than trimmed. A column of "45.0 / 46.2 / 51.8"
    is read at a glance; "45 / 46.2 / 51.8" is not.
    """
    return f"{deger:.{basamak}f}"


def _kanal(olcum_tipi: OlcumTipi) -> str:
    return KANAL_ADI.get(olcum_tipi, olcum_tipi.value)


def _birim(olcum_tipi: OlcumTipi) -> str:
    return BIRIM_ADI.get(olcum_tipi, "")


# --------------------------------------------------------------------------
# Layer 0 — sensor health
# --------------------------------------------------------------------------


def kalite_bozuk(olcum_tipi: OlcumTipi, bozuk: int, toplam: int, kalite: str) -> str:
    yuzde = 100.0 * bozuk / toplam if toplam else 0.0
    return (
        f"{_kanal(olcum_tipi).capitalize()} kanalında son pencerede {toplam} ölçümün "
        f"{bozuk} tanesi (%{sayi(yuzde, 0)}) '{kalite}' kalitesinde geldi. "
        f"Ölçüm güvenilir değil; bu kanal için sıcaklık/akım değerlendirmesi yapılmadı. "
        f"Sensör veya kablo bağlantısı kontrol edilmeli."
    )


def donuk_sensor(olcum_tipi: OlcumTipi, ardisik: int, deger: float, dakika: float) -> str:
    return (
        f"{_kanal(olcum_tipi).capitalize()} {ardisik} ardışık ölçümde "
        f"({sayi(dakika, 0)} dakika) {sayi(deger, 2)} {_birim(olcum_tipi)} değerinde "
        f"hiç değişmedi. Fiziksel bir büyüklüğün bu kadar sabit kalması beklenmez; "
        f"sensör donmuş olabilir. Bu kanal değerlendirme dışı bırakıldı."
    )


def aralik_disi(olcum_tipi: OlcumTipi, deger: float, alt: float, ust: float) -> str:
    birim = _birim(olcum_tipi)
    return (
        f"{_kanal(olcum_tipi).capitalize()} {sayi(deger, 1)} {birim} okudu; "
        f"fiziksel geçerli aralık {sayi(alt, 0)}–{sayi(ust, 0)} {birim}. "
        f"Bu bir ölçüm değeri değil, arızalı sensör göstergesidir. "
        f"Anomali olarak değil sensör arızası olarak kaydedildi."
    )


def modul_sessiz(dakika: float, son_zaman: str) -> str:
    return (
        f"Modülden {sayi(dakika, 0)} dakikadır ölçüm gelmiyor "
        f"(son ölçüm {son_zaman}). Besleme kaybı, radyo bağlantısı veya modül "
        f"arızası olabilir. Sistem sessizce ölmedi; bu kayıt onun kanıtıdır."
    )


def saat_kaymasi(kayma_sn: float, esik_sn: float) -> str:
    """Every reading in the window arrived at least `kayma_sn` after its own timestamp."""
    return (
        f"Penceredeki hiçbir ölçüm taze değil: ölçüm zamanı ile toplama zamanı arasındaki "
        f"fark en az {sayi(kayma_sn, 0)} saniye (eşik {sayi(esik_sn, 0)} saniye); modül "
        f"saati geri kaymış görünüyor. Gecikmeli gelen eski veri olsaydı en az bir ölçüm "
        f"taze olurdu. Zaman damgası bozuk veri üzerinde eğilim hesabı güvenilmez olur, "
        f"saat senkronu kontrol edilmeli."
    )


def ileri_tarihli(kayma_sn: float, zaman: str) -> str:
    """A reading was measured after the collector received it — certain drift."""
    return (
        f"Ölçüm zamanı toplama zamanından {sayi(abs(kayma_sn), 0)} saniye ileride "
        f"({zaman}); bir modül toplayıcının geleceğinde ölçüm yapamaz, modül saati ileri "
        f"kaymış. Zaman damgası bozuk veri üzerinde eğilim hesabı güvenilmez olur, saat "
        f"senkronu kontrol edilmeli."
    )


def besleme_kaybi(ardisik: int, dakika: float, ilk_zaman: str) -> str:
    return (
        f"Modül {sayi(dakika, 0)} dakikadır ({ardisik} pakettir, {ilk_zaman} itibarıyla) "
        f"yedek beslemede; şebeke beslemesi kesilmiş. Süperkapasitör sınırlı süre dayanır "
        f"— pano beslemesi ve modül sigortası kontrol edilmeli."
    )


def sinyal_zayif(medyan_dbm: float, esik_dbm: float, ornek: int) -> str:
    return (
        f"Alınan sinyal gücü son {ornek} pakette medyan {sayi(medyan_dbm, 0)} dBm "
        f"(eşik {sayi(esik_dbm, 0)} dBm); bağlantı zayıflıyor, paket kaybı ve sessizlik "
        f"başlayabilir. Anten ve konum kontrol edilmeli."
    )


# --------------------------------------------------------------------------
# Layer 1 — absolute limits
# --------------------------------------------------------------------------


def mutlak_sicaklik(deger: float, esik: float, ortam: float | None) -> str:
    cumle = (
        f"Sıcak nokta {sayi(deger)} °C ölçüldü; mutlak sınır {sayi(esik, 0)} °C. "
    )
    if ortam is not None:
        cumle += f"Ortam sıcaklığı {sayi(ortam)} °C, aradaki fark {sayi(deger - ortam)} °C. "
    cumle += "Taban çizgisinden bağımsız sınır aşımı; yalıtım ve bağlantı zorlanıyor."
    return cumle


def mutlak_ortam(deger: float, esik: float) -> str:
    return (
        f"Pano içi ortam sıcaklığı {sayi(deger)} °C, mutlak sınır {sayi(esik, 0)} °C. "
        f"Pano geneli aşırı ısınmış; havalandırma veya toplam yük gözden geçirilmeli."
    )


def mutlak_nem(deger: float, esik: float, ortam: float | None) -> str:
    cumle = f"Bağıl nem %{sayi(deger)}, eşik %{sayi(esik, 0)}. "
    if ortam is not None:
        cumle += f"Ortam sıcaklığı {sayi(ortam)} °C. "
    cumle += "Yoğuşma ve yüzey kaçak akımı riski; pano sızdırmazlığı kontrol edilmeli."
    return cumle


def mutlak_faz(
    dengesizlik: float, esik: float, akimlar: dict[str, float], notr: float | None
) -> str:
    dokum = ", ".join(f"{ad} {sayi(deger, 0)} A" for ad, deger in akimlar.items())
    cumle = (
        f"Faz dengesizliği %{sayi(dengesizlik)}, eşik %{sayi(esik, 0)} ({dokum}). "
    )
    if notr is not None:
        cumle += f"Nötr akımı {sayi(notr, 0)} A. "
    cumle += "Dengesiz yük dağılımı nötr iletkeni ve trafoyu zorlar."
    return cumle


def ark_olayi(sayac: float, zaman: str) -> str:
    return (
        f"Ark koruma cihazı {sayi(sayac, 0)} olay kaydetti (son kayıt {zaman}). "
        f"Ark olayı anlık ve yıkıcıdır; tespit cihazın kendi trip kaydından okunmuştur. "
        f"Pano enerjisiz bırakılmadan içeri müdahale edilmemelidir."
    )


# --------------------------------------------------------------------------
# Layer 2 — baseline deviation
# --------------------------------------------------------------------------


def taban_sapmasi(
    olcum_tipi: OlcumTipi,
    deger: float,
    medyan: float,
    mad: float,
    z: float,
    ornek: int,
    gun: float,
) -> str:
    birim = _birim(olcum_tipi)
    return (
        f"{_kanal(olcum_tipi).capitalize()} {sayi(deger)} {birim}; bu modülün son "
        f"{sayi(gun, 0)} günlük normali medyan {sayi(medyan)} {birim}, MAD "
        f"{sayi(mad, 2)} {birim} ({ornek} ölçüm). Değer taban çizgisinin "
        f"{sayi(abs(z))} robust sapma dışında. Sabit bir eşik değil, bu modülün "
        f"kendi geçmişine göre sapma."
    )


def taban_egilimi(
    olcum_tipi: OlcumTipi,
    ilk: float,
    son: float,
    saat: float,
    egim_saatlik: float,
    medyan: float | None,
) -> str:
    birim = _birim(olcum_tipi)
    fark = son - ilk
    isaret = "+" if fark >= 0 else ""
    cumle = (
        f"{_kanal(olcum_tipi).capitalize()} son {sayi(saat)} saatte {sayi(ilk)} → "
        f"{sayi(son)} {birim} ({isaret}{sayi(fark)} {birim}, saatte "
        f"{sayi(egim_saatlik, 2)} {birim}). "
    )
    if medyan is not None:
        cumle += f"Modülün taban çizgisi medyanı {sayi(medyan)} {birim}. "
    cumle += (
        "Şu anki değer tek başına sınır aşmıyor; bozulma eğilimi sürerse sınıra "
        "ulaşacak. Erken uyarı kaydıdır."
    )
    return cumle


# --------------------------------------------------------------------------
# Layer 3 — relationships
# --------------------------------------------------------------------------


def akim_sicaklik(
    sicaklik_ilk: float,
    sicaklik_son: float,
    saat: float,
    akim_adi: str,
    akim_ilk: float,
    akim_son: float,
    ortam_farki: float,
    yuk_aciklamasi: float,
    aciklanamayan: float,
) -> str:
    """Scenario 1's sentence: the rise, and everything that fails to explain it.

    Written as an accounting: this much heat appeared, the air accounts for this
    much, the load for this much, and this much is left over. The leftover is the
    finding, and stating it as a subtraction is what lets an operator disagree
    with it on the evidence rather than take it on faith.
    """
    fark = sicaklik_son - sicaklik_ilk
    akim_degisim = (
        "değişmedi"
        if abs(akim_son - akim_ilk) < 0.01 * max(abs(akim_ilk), 1.0)
        else f"%{sayi(100 * (akim_son - akim_ilk) / max(abs(akim_ilk), 1e-6))} değişti"
    )
    return (
        f"Sıcak nokta {sayi(saat)} saatte {sayi(sicaklik_ilk)} → {sayi(sicaklik_son)} °C "
        f"(+{sayi(fark)} °C) yükseldi. Aynı sürede {akim_adi} {sayi(akim_ilk, 0)} → "
        f"{sayi(akim_son, 0)} A ({akim_degisim}) ve ortam sıcaklığı "
        f"{sayi(ortam_farki)} °C oynadı. Yük bu artışın {sayi(yuk_aciklamasi)} °C'sini, "
        f"ortam {sayi(ortam_farki)} °C'sini açıklıyor; geriye {sayi(aciklanamayan)} °C "
        f"açıklanamayan ısı kalıyor. Sabit yükte artan ısı artan temas direncidir — "
        f"gevşek klemens veya oksitlenmiş bağlantı."
    )


def faz_faz(faz_adi: str, deger: float, medyan: float, sapma: float, notr: float | None) -> str:
    cumle = (
        f"{faz_adi} akımı {sayi(deger, 0)} A, üç fazın medyanı {sayi(medyan, 0)} A "
        f"(%{sayi(sapma * 100)} sapma). Diğer iki faz birbirine yakın; ortak bir yük "
        f"değişimi üç fazı birden hareket ettirirdi, burada tek faz ayrışıyor"
    )
    if notr is not None:
        cumle += f". Nötr akımı {sayi(notr, 0)} A ile bunu doğruluyor"
    cumle += "."
    return cumle


def komsu_piksel(
    maks: float, bolge_ort: float, ayrisma: float, sutun: int, satir: int, kararlilik: float
) -> str:
    return (
        f"Termal karede en sıcak piksel [{sutun}, {satir}] {sayi(maks)} °C, aynı karenin "
        f"bölge ortalaması {sayi(bolge_ort)} °C — aradaki fark {sayi(ayrisma)} °C. "
        f"Sıcak nokta pencerenin %{sayi(kararlilik * 100, 0)}'inde aynı pikselde kaldı. "
        f"Kare geneli ısınsaydı ortam kaynaklı olurdu; tek piksel ayrıştığı için "
        f"nokta temas ısınmasıdır."
    )


def modul_modul(
    delta: float, komsu_delta: float, komsu_sayisi: int, kapsam: str, saat: float
) -> str:
    return (
        f"Bu modülün sıcak noktası son {sayi(saat)} saatte {sayi(delta)} °C yükseldi; "
        f"aynı {kapsam}daki {komsu_sayisi} modülün medyan artışı {sayi(komsu_delta)} °C. "
        f"Fark {sayi(delta - komsu_delta)} °C. Hava ısınsaydı hepsi birlikte yükselirdi; "
        f"yalnızca bu modül ayrıştığı için sorun bu panodadır."
    )
