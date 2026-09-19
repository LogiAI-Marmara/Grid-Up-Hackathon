# durum.py
"""Alarm servisinin kalıcı durumu: atomik yazma ve bozuk dosya politikası.

Neden ayrı modül (A-04): iki kural var ve ikisi de çağıran tarafta kolayca
unutuluyor.

1. Yazılamayan durum kalıcı başarı sanılmaz. `kaydet` sessizce loglayıp
   dönmez, `DurumYazmaHatasi` fırlatır; çağıran belleği son kalıcı
   anlık görüntüye geri almak zorundadır. Aksi halde süreç, diske hiç
   inmemiş bir cursor'la çalışmaya devam eder ve yeniden başlatmada
   o aralıktaki alarmlar ikinci kez değil, hiç işlenmemiş gibi değil,
   *kayıp* olarak ortaya çıkar.
2. Bozuk durum dosyası sessizce boş duruma çevrilmez. Varsayılan politika
   `dur`: servis açılmaz. Bu, konteyner'ı yeniden başlatma döngüsüne sokar
   ama görünürdür; alternatifi tüm geçmişi yok sayıp her şeyi yeniden
   bildirmek ya da teslim geçmişini sessizce kaybetmektir.
"""

from __future__ import annotations

import json
import logging
import os
import time

DURUM_SURUMU = 2

_GUNLUK = logging.getLogger("alarm.durum")


class DurumYazmaHatasi(RuntimeError):
    """Durum diske yazılamadı. Çağıran belleği geri almak zorundadır."""


class BozukDurumHatasi(RuntimeError):
    """Mevcut durum dosyası okunamadı veya çözümlenemedi."""


def bos_durum() -> dict:
    """Hiç durum yokken kullanılan taban.

    `son_gecis_id` yalnızca *çekme* imlecidir; "bu id'ye kadar her şey
    teslim edildi" demek değildir. Bitmemiş iş `bekleyen` içindedir ve
    ikisi aynı dosyada, tek atomik yazımla birlikte kalıcılaşır. Gerçek
    imleç bu ikilidir.
    """
    return {
        "surum": DURUM_SURUMU,
        "son_gecis_id": None,
        "bekleyen": {},
        "son_bildirim": {},
        "dusen_bildirim": 0,
    }


def _dogrula(veri: object) -> dict:
    if not isinstance(veri, dict):
        raise BozukDurumHatasi("durum dosyasının kökü nesne değil")

    son_id = veri.get("son_gecis_id")
    if son_id is not None and not isinstance(son_id, int):
        raise BozukDurumHatasi(f"son_gecis_id tamsayı ya da null olmalı: {son_id!r}")
    for alan in ("bekleyen", "son_bildirim"):
        if not isinstance(veri.get(alan, {}), dict):
            raise BozukDurumHatasi(f"{alan} nesne olmalı")
    return veri


def _surum_yukselt(veri: dict) -> dict:
    """v1 -> v2.

    v1'de tekrar önleme `last_alert_times` içinde `modul_id` ile
    anahtarlanıyordu (A-02/A-05'in kaynağı). O anahtarlar yeni şemada
    yanlış bastırma üretir, bu yüzden taşınmaz. `son_gecis_id` taşınır:
    değerli olan kısım odur, atılırsa tüm geçmiş yeniden bildirilir.
    """
    if veri.get("surum") == DURUM_SURUMU:
        veri.setdefault("bekleyen", {})
        veri.setdefault("son_bildirim", {})
        veri.setdefault("dusen_bildirim", 0)
        return veri

    eski_cooldown = veri.get("last_alert_times")
    yeni = bos_durum()
    yeni["son_gecis_id"] = veri.get("son_gecis_id")
    if eski_cooldown:
        _GUNLUK.warning(
            "Durum dosyası v1'den v2'ye taşındı. %d adet modül anahtarlı cooldown "
            "kaydı düşürüldü (v2 anahtarı anomali+seviye). son_gecis_id=%s korundu; "
            "ilk turda bu modüller için bir tekrar bildirim görülebilir.",
            len(eski_cooldown),
            yeni["son_gecis_id"],
        )
    return yeni


class DurumDeposu:
    """Tek bir JSON dosyasını atomik okuyup yazar."""

    def __init__(self, yol: str, bozuk_politika: str = "dur"):
        self.yol = yol
        if bozuk_politika not in ("dur", "sifirla"):
            raise ValueError(
                f"bozuk_politika 'dur' veya 'sifirla' olmalı: {bozuk_politika!r}"
            )
        self.bozuk_politika = bozuk_politika

    def yukle(self) -> dict:
        if not os.path.exists(self.yol):
            _GUNLUK.info("Durum dosyası yok, sıfırdan başlanıyor: %s", self.yol)
            return bos_durum()

        try:
            with open(self.yol, "r", encoding="utf-8") as f:
                veri = json.load(f)
            return _surum_yukselt(_dogrula(veri))
        except BozukDurumHatasi as hata:
            return self._bozuk(str(hata))
        except (OSError, ValueError) as hata:
            return self._bozuk(f"{type(hata).__name__}: {hata}")

    def _bozuk(self, sebep: str) -> dict:
        if self.bozuk_politika == "dur":
            _GUNLUK.error(
                "Durum dosyası bozuk (%s): %s. Servis açılmıyor. Dosya olduğu gibi "
                "bırakıldı; inceleyip düzeltin ya da geçmişi bilerek feda etmek için "
                "ALARM_BOZUK_DURUM=sifirla ile başlatın.",
                self.yol,
                sebep,
            )
            raise BozukDurumHatasi(f"{self.yol}: {sebep}")

        yedek = f"{self.yol}.bozuk-{int(time.time())}"
        try:
            os.replace(self.yol, yedek)
            _GUNLUK.error(
                "Durum dosyası bozuk (%s) ve ALARM_BOZUK_DURUM=sifirla verildi. "
                "Dosya %s adına alındı, boş durumla devam ediliyor: geçmiş teslim "
                "kayıtları kaybedildi ve eski geçişler yeniden bildirilebilir.",
                sebep,
                yedek,
            )
        except OSError as hata:
            _GUNLUK.error(
                "Bozuk durum dosyası yedeğe alınamadı (%s); boş durumla devam "
                "ediliyor ve bir sonraki yazım dosyanın üzerine yazacak.",
                hata,
            )
        return bos_durum()

    def kaydet(self, durum: dict) -> None:
        """Atomik yazar. Başarısızlıkta `DurumYazmaHatasi` fırlatır.

        Geçici dosya + fsync + `os.replace`: yarım yazılmış bir JSON'un
        kalıcı dosyanın yerini alması mümkün değil. Dizin de fsync'lenir,
        yoksa ani güç kesintisinde rename kaybolabilir.
        """
        dizin = os.path.dirname(os.path.abspath(self.yol)) or "."
        gecici = f"{self.yol}.tmp"
        try:
            os.makedirs(dizin, exist_ok=True)
            with open(gecici, "w", encoding="utf-8") as f:
                json.dump(durum, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(gecici, self.yol)
            try:
                dfd = os.open(dizin, os.O_RDONLY)
                try:
                    os.fsync(dfd)
                finally:
                    os.close(dfd)
            except OSError:
                pass  # her dosya sisteminde dizin fsync'i desteklenmiyor
        except (OSError, TypeError, ValueError) as hata:
            # OSError disk/izin; TypeError ve ValueError json.dump'tan gelir
            # (seri hale getirilemeyen bir değer duruma sızmışsa). Üçü de
            # aynı şey demek: durum diske inmedi. Çağıranın tek bir hata
            # tipi görmesi gerekiyor, yoksa beklenmeyen tip save_state'i
            # geçip servisi öldürüyor.
            try:
                if os.path.exists(gecici):
                    os.remove(gecici)
            except OSError:
                pass
            raise DurumYazmaHatasi(f"{self.yol}: {type(hata).__name__}: {hata}") from hata
