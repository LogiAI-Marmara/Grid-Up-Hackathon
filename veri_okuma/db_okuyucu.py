# veri_okuma/db_okuyucu.py
"""
Grid Up - PostgreSQL Veritabanı Doğrudan Veri Okuyucu
PostgreSQL (gridup veritabanı) üzerinden doğrudan SQL sorguları ile
ölçüm, termal kare ve modül durumlarını çeker.
"""

from __future__ import annotations
import os
import struct
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None


class DbOlcumOkuyucu:
    """PostgreSQL doğrudan okuma sınıfı."""

    VARSAYILAN_DSN = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:gridup@127.0.0.1:5432/gridup"
    )

    def __init__(self, dsn: Optional[str] = None):
        if psycopg is None:
            raise ImportError(
                "psycopg kütüphanesi yüklü değil! Kurulum: pip install psycopg[binary]"
            )
        self.dsn = dsn or self.VARSAYILAN_DSN

    def _baglan(self):
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def modulleri_getir(self) -> List[Dict[str, Any]]:
        """Veritabanında kayıtlı tüm modülleri döner."""
        sql = """
            SELECT m.modul_id, m.saha_kodu, m.pano_kodu, m.aktif,
                   m.olusturuldu, m.guncellendi
            FROM gridup.modul m
            ORDER BY m.saha_kodu, m.pano_kodu, m.modul_id;
        """
        with self._baglan() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                return cur.fetchall()

    def son_olcumleri_getir(self, modul_id: str) -> Dict[str, Any]:
        """
        Modüle ait her ölçüm tipinin en son kaydedilen değerini döner.
        Dönüş: {
            'modul_id': 'TR041-P01-M1',
            'son_zaman': datetime,
            'olcumler': {'akim_l1': 99.3, 'ortam_sicaklik': 28.1, ...}
        }
        """
        sql = """
            SELECT DISTINCT ON (olcum_tipi)
                olcum_tipi, deger, birim, kalite, zaman, alindi_zaman
            FROM gridup.olcum
            WHERE modul_id = %s
            ORDER BY olcum_tipi, zaman DESC;
        """
        with self._baglan() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (modul_id,))
                satirlar = cur.fetchall()

        olcumler = {}
        son_zaman = None
        for s in satirlar:
            olcumler[s["olcum_tipi"]] = {
                "deger": s["deger"],
                "birim": s["birim"],
                "kalite": s["kalite"],
                "zaman": s["zaman"].isoformat() if s["zaman"] else None
            }
            if son_zaman is None or (s["zaman"] and s["zaman"] > son_zaman):
                son_zaman = s["zaman"]

        return {
            "modul_id": modul_id,
            "son_zaman": son_zaman.isoformat() if son_zaman else None,
            "olcumler": olcumler
        }

    def zaman_serisi_getir(
        self,
        modul_id: str,
        olcum_tipi: str,
        baslangic: Optional[datetime] = None,
        bitis: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Belirli bir modül ve ölçüm tipi için zaman serisi noktalarını döner.
        """
        filtreler = ["modul_id = %s", "olcum_tipi = %s"]
        parametreler: List[Any] = [modul_id, olcum_tipi]

        if baslangic:
            filtreler.append("zaman >= %s")
            parametreler.append(baslangic)
        if bitis:
            filtreler.append("zaman <= %s")
            parametreler.append(bitis)

        sql = f"""
            SELECT zaman, deger, birim, kalite, alindi_zaman
            FROM gridup.olcum
            WHERE {' AND '.join(filtreler)}
            ORDER BY zaman DESC
            LIMIT %s;
        """
        parametreler.append(limit)

        with self._baglan() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, parametreler)
                return cur.fetchall()

    def termal_kare_getir(
        self,
        kare_id: Optional[str] = None,
        modul_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Termal kareyi veritabanından çeker ve 1536 baytlık piksel verisini
        32x24 (768 elemanlı) °C değerlerine çözerek döner.
        """
        if kare_id:
            sql = """
                SELECT kare_id, modul_id, zaman, piksel_verisi,
                       satir_sayisi, sutun_sayisi, alindi_zaman
                FROM gridup.termal_kare
                WHERE kare_id = %s;
            """
            params = (kare_id,)
        elif modul_id:
            sql = """
                SELECT kare_id, modul_id, zaman, piksel_verisi,
                       satir_sayisi, sutun_sayisi, alindi_zaman
                FROM gridup.termal_kare
                WHERE modul_id = %s
                ORDER BY zaman DESC
                LIMIT 1;
            """
            params = (modul_id,)
        else:
            raise ValueError("kare_id veya modul_id parametrelerinden biri verilmelidir.")

        with self._baglan() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                satir = cur.fetchone()

        if not satir:
            return None

        ham_baytlar = bytes(satir["piksel_verisi"])
        eleman_sayisi = len(ham_baytlar) // 2
        # Küçük-endian int16 çözümü, 0.1 °C hassasiyeti (bölü 10.0)
        ham_degerler = struct.unpack(f"<{eleman_sayisi}h", ham_baytlar)
        pikseller = [round(v / 10.0, 1) for v in ham_degerler]

        return {
            "kare_id": satir["kare_id"],
            "modul_id": satir["modul_id"],
            "zaman": satir["zaman"].isoformat() if satir["zaman"] else None,
            "satir_sayisi": satir["satir_sayisi"],
            "sutun_sayisi": satir["sutun_sayisi"],
            "pikseller": pikseller,
            "istatistik": {
                "min": min(pikseller),
                "maks": max(pikseller),
                "ortalama": round(sum(pikseller) / len(pikseller), 2)
            }
        }

    def modul_durumu_getir(self, modul_id: str) -> Optional[Dict[str, Any]]:
        """Modüle ait son besleme ve sinyal durumunu döner."""
        sql = """
            SELECT modul_id, zaman, besleme, sinyal, yazilim_surumu, alindi_zaman
            FROM gridup.modul_durum
            WHERE modul_id = %s
            ORDER BY zaman DESC
            LIMIT 1;
        """
        with self._baglan() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (modul_id,))
                return cur.fetchone()
