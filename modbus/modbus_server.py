# /modbus/modbus_server.py
"""
Grid Up Hackathon - İZ C: Modbus TCP Sunucu Servisi
Sözleşme ④ uyarınca canlı modül verilerini dış SCADA/RTU sistemlerine
5020 portu üzerinden sunar.
Başlangıç Adresi = 100 + (N - 1) * 20
Gerçek API'den (Sözleşme ⑤) beslenir; veri gelmediğinde register'lara sıfır yazılmaz,
son geçerli durum korunur.
"""

import os
import sys
import logging
import asyncio
import aiohttp

try:
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

from pymodbus.server import StartAsyncTcpServer
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusSlaveContext, ModbusServerContext

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(message)s"
)

# Anomali seviyeleri ve besleme durumu haritalaması (Sözleşme ④)
SEVIYE_MAP = {"normal": 0, "izle": 1, "uyari": 2, "kritik": 3}
BESLEME_MAP = {"sebeke": 0, "yedek": 1}

API_URL = os.getenv("API_URL", "http://localhost:8080").rstrip("/")
MODBUS_PORT = int(os.getenv("MODBUS_PORT", "5020"))
MODBUS_HOST = os.getenv("MODBUS_HOST", "0.0.0.0")
POLL_INTERVAL = float(os.getenv("MODBUS_POLL_INTERVAL", "5.0"))

class ModbusService:
    def __init__(self, max_moduller=10):
        self.max_moduller = max_moduller
        # Her modül için 20 register kapsayan blok (Adres 100'den başlar)
        total_registers = 100 + (max_moduller * 20) + 10
        self.registers = [0] * total_registers

        # PyModbus Holding Registers (hr) veri alanı
        self.store = ModbusSlaveContext(hr=ModbusSequentialDataBlock(0, self.registers))
        self.context = ModbusServerContext(slaves=self.store, single=True)
        # Modüllerin son geçerli değerlerini saklama (veri gelmediğinde sıfır yazılmaması için)
        self.modul_hafizasi: dict[int, list[int]] = {}

    def update_modul_data(self, modul_index: int, modul_detay: dict, termal_ozet: dict | None = None):
        """
        Modül verilerini Sözleşme ④'teki kurallara göre register'lara yazar.
        modul_index: 1-indexed (Örn: Modül 1 -> adres 100, Modül 2 -> adres 120)
        Veri gelmediğinde/eksik olduğunda sıfır yazılmaz, önceki değer korunur.
        """
        base_addr = 100 + (modul_index - 1) * 20
        mevcut_degerler = self.modul_hafizasi.get(modul_index, [0] * 20)

        # 1. Uzun format son_olcumler haritası
        son_olcumler = modul_detay.get("son_olcumler") or []
        olcumler = {o["olcum_tipi"]: o["deger"] for o in son_olcumler if "olcum_tipi" in o and "deger" in o}

        # 2. Termal Maksimum Sıcaklık
        termal_maks = None
        if termal_ozet and "maks" in termal_ozet and termal_ozet["maks"] is not None:
            termal_maks = termal_ozet["maks"]
        elif "termal_maks" in olcumler:
            termal_maks = olcumler["termal_maks"]

        # Yeni değerleri hazırla (varsa güncelle, yoksa önceki değeri koru - Madde 20)
        yeni_degerler = list(mevcut_degerler)

        if "ortam_sicaklik" in olcumler and olcumler["ortam_sicaklik"] is not None:
            yeni_degerler[0] = int(round(float(olcumler["ortam_sicaklik"]) * 10)) & 0xFFFF
        if "nem" in olcumler and olcumler["nem"] is not None:
            yeni_degerler[1] = int(round(float(olcumler["nem"]) * 10)) & 0xFFFF
        if "akim_l1" in olcumler and olcumler["akim_l1"] is not None:
            yeni_degerler[2] = int(round(float(olcumler["akim_l1"]) * 10)) & 0xFFFF
        if "akim_l2" in olcumler and olcumler["akim_l2"] is not None:
            yeni_degerler[3] = int(round(float(olcumler["akim_l2"]) * 10)) & 0xFFFF
        if "akim_l3" in olcumler and olcumler["akim_l3"] is not None:
            yeni_degerler[4] = int(round(float(olcumler["akim_l3"]) * 10)) & 0xFFFF
        if "akim_notr" in olcumler and olcumler["akim_notr"] is not None:
            yeni_degerler[5] = int(round(float(olcumler["akim_notr"]) * 10)) & 0xFFFF
        if termal_maks is not None:
            yeni_degerler[6] = int(round(float(termal_maks) * 10)) & 0xFFFF

        # 3. Anomali Seviyesi
        if "acik_anomaliler" in modul_detay and modul_detay["acik_anomaliler"] is not None:
            acik_anomaliler = modul_detay["acik_anomaliler"]
            en_kotu_seviye = 0
            for a in acik_anomaliler:
                s = str(a.get("seviye") or "normal").lower()
                en_kotu_seviye = max(en_kotu_seviye, SEVIYE_MAP.get(s, 0))
            yeni_degerler[7] = en_kotu_seviye & 0xFFFF
        elif "seviye" in modul_detay and modul_detay["seviye"] is not None:
            seviye_str = str(modul_detay["seviye"]).lower()
            yeni_degerler[7] = SEVIYE_MAP.get(seviye_str, 0) & 0xFFFF

        # 4. Besleme Durumu
        if "besleme" in modul_detay and modul_detay["besleme"] is not None:
            besleme_str = str(modul_detay["besleme"]).lower()
            yeni_degerler[8] = BESLEME_MAP.get(besleme_str, 0) & 0xFFFF

        # 5. Sinyal (RSSI)
        if "sinyal" in modul_detay and modul_detay["sinyal"] is not None:
            yeni_degerler[9] = int(modul_detay["sinyal"]) & 0xFFFF

        if "ark_olay" in olcumler and olcumler["ark_olay"] is not None:
            yeni_degerler[10] = int(olcumler["ark_olay"]) & 0xFFFF

        # Datastore güncelle ve hafızayı tazele
        self.modul_hafizasi[modul_index] = yeni_degerler
        self.store.setValues(3, base_addr, yeni_degerler)
        logging.debug(f"Modül {modul_index} (Adres {base_addr}) register'ları güncellendi.")

async def sync_data_loop(service: ModbusService):
    """Gerçek API'den canlı veri çeker, veri gelmediğinde sıfır yazmaz (Madde 20)"""
    timeout = aiohttp.ClientTimeout(total=5)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        while True:
            try:
                # 1. Modül listesini API'den al
                modul_listesi = []
                try:
                    async with session.get(f"{API_URL}/moduller?limit={service.max_moduller}") as resp:
                        if resp.status == 200:
                            govde = await resp.json()
                            moduller = govde.get("veriler", [])
                            modul_listesi = [m["modul_id"] for m in moduller if "modul_id" in m]
                except Exception as e:
                    logging.debug(f"Modül listesi alınamadı ({e}), bilinen modüller denenecek...")

                if not modul_listesi:
                    # Fallback varsayılan modül listesi
                    modul_listesi = ["TR041-P01-M1", "TR041-P01-M2"]

                # 2. Her modül için detay ve termal özet çek
                for idx, modul_id in enumerate(modul_listesi[:service.max_moduller], start=1):
                    try:
                        # Modül detayı (son_olcumler, besleme, sinyal)
                        modul_detay = None
                        async with session.get(f"{API_URL}/moduller/{modul_id}") as resp:
                            if resp.status == 200:
                                modul_detay = await resp.json()

                        if modul_detay is None:
                            # Veri gelmediğinde sıfır yazma, geç (Madde 20)
                            continue

                        # Termal özet
                        termal_ozet = None
                        try:
                            async with session.get(f"{API_URL}/moduller/{modul_id}/termal/son") as resp:
                                if resp.status == 200:
                                    termal_ozet = await resp.json()
                        except Exception:
                            pass

                        service.update_modul_data(idx, modul_detay, termal_ozet)

                    except Exception as err:
                        logging.debug(f"Modül {modul_id} güncellenemedi: {err}")
                        # Veri gelmediğinde sıfır yazılmıyor!

            except Exception as e:
                logging.error(f"Modbus senkronizasyon döngüsünde hata: {e}")

            await asyncio.sleep(POLL_INTERVAL)

async def main():
    service = ModbusService(max_moduller=10)
    asyncio.create_task(sync_data_loop(service))

    logging.info(f"🚀 Modbus TCP SCADA Sunucusu Başlatılıyor: {MODBUS_HOST}:{MODBUS_PORT}")
    logging.info(f"📡 API Kaynağı: {API_URL}")
    logging.info("📋 Sözleşme ④ Register Bloğu: Adres 100'den itibaren (Modül başına 20 register)")
    await StartAsyncTcpServer(context=service.context, address=(MODBUS_HOST, MODBUS_PORT))

if __name__ == "__main__":
    asyncio.run(main())