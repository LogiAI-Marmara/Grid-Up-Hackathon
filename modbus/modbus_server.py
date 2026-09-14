# /modbus/modbus_server.py
"""
Grid Up Hackathon - İZ C: Modbus TCP Sunucu Servisi
Sözleşme ④ uyarınca canlı modül verilerini dış SCADA/RTU sistemlerine
5020 portu üzerinden sunar.
Başlangıç Adresi = 100 + (N - 1) * 20
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

API_URL = os.getenv("API_URL", "http://localhost:8000/api")
MODBUS_PORT = int(os.getenv("MODBUS_PORT", "5020"))
MODBUS_HOST = os.getenv("MODBUS_HOST", "0.0.0.0")

class ModbusService:
    def __init__(self, max_moduller=10):
        self.max_moduller = max_moduller
        # Her modül için 20 register kapsayan blok (Adres 100'den başlar)
        total_registers = 100 + (max_moduller * 20)
        self.registers = [0] * total_registers

        # PyModbus Holding Registers (hr) veri alanı
        self.store = ModbusSlaveContext(hr=ModbusSequentialDataBlock(0, self.registers))
        self.context = ModbusServerContext(slaves=self.store, single=True)

    def update_modul_data(self, modul_index: int, data: dict):
        """
        Modül verilerini Sözleşme ④'teki çarpan kurallarına göre register'lara yazar.
        modul_index: 1-indexed (Örn: Modül 1 -> adres 100, Modül 2 -> adres 120)
        """
        base_addr = 100 + (modul_index - 1) * 20

        # Termal özet içinden veya doğrudan maksimum sıcaklık alma
        termal_maks = data.get("termal_maks", 0)
        if termal_maks == 0 and isinstance(data.get("termal_ozet"), dict):
            termal_maks = data["termal_ozet"].get("maks", 0)

        # Veri dönüşümleri (Çarpan: x10 ölçekleme)
        ortam_temp = int(round(float(data.get("ortam_sicaklik", 0)) * 10))
        nem = int(round(float(data.get("nem", 0)) * 10))
        akim_l1 = int(round(float(data.get("akim_l1", 0)) * 10))
        akim_l2 = int(round(float(data.get("akim_l2", 0)) * 10))
        akim_l3 = int(round(float(data.get("akim_l3", 0)) * 10))
        akim_notr = int(round(float(data.get("akim_notr", 0)) * 10))
        t_maks = int(round(float(termal_maks) * 10))
        seviye_enum = SEVIYE_MAP.get(str(data.get("seviye", "normal")).lower(), 0)
        besleme_enum = BESLEME_MAP.get(str(data.get("besleme", "sebeke")).lower(), 0)
        rssi = int(data.get("sinyal", -72)) & 0xFFFF
        ark_sayisi = int(data.get("ark_olay", 0))

        modul_values = [
            ortam_temp,    # +0: Ortam Sıcaklık (UInt16, x10)
            nem,           # +1: Nem (UInt16, x10)
            akim_l1,       # +2: Akım L1 (UInt16, x10)
            akim_l2,       # +3: Akım L2 (UInt16, x10)
            akim_l3,       # +4: Akım L3 (UInt16, x10)
            akim_notr,     # +5: Akım Nötr (UInt16, x10)
            t_maks,        # +6: Termal Maks (UInt16, x10)
            seviye_enum,   # +7: Anomali Seviyesi (0-3)
            besleme_enum,  # +8: Besleme Kaynağı (0: Şebeke, 1: Yedek)
            rssi,          # +9: RSSI Sinyal (Int16)
            ark_sayisi     # +10: Ark Olay Sayısı (Sayaç)
        ] + [0] * 9        # +11..+19: Yedek kanallar

        # Datastore güncelleme (Holding Register işlev kodu: 3)
        self.store.setValues(3, base_addr, modul_values)
        logging.debug(f"Modül {modul_index} (Adres {base_addr}) Modbus register'ları güncellendi.")

async def sync_data_loop(service: ModbusService):
    """API'den canlı veri çeken, API yoksa simülasyon uygulayan döngü"""
    moduller = [
        (1, "TR041-P01-M1"),
        (2, "TR041-P01-M2")
    ]

    async with aiohttp.ClientSession() as session:
        while True:
            for idx, modul_id in moduller:
                url = f"{API_URL}/moduller/{modul_id}"
                data_alindi = False
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            service.update_modul_data(idx, data)
                            data_alindi = True
                except Exception:
                    pass

                # API'ye ulaşılamadıysa dahili simülasyon fallback
                if not data_alindi:
                    sample_data = {
                        "ortam_sicaklik": 34.7 if idx == 1 else 29.2,
                        "nem": 45.0 if idx == 1 else 42.0,
                        "akim_l1": 120.5 if idx == 1 else 118.0,
                        "akim_l2": 159.4 if idx == 1 else 118.5,
                        "akim_l3": 119.8 if idx == 1 else 117.9,
                        "akim_notr": 2.4 if idx == 1 else 0.8,
                        "termal_maks": 83.5 if idx == 1 else 31.2,
                        "seviye": "uyari" if idx == 1 else "normal",
                        "besleme": "sebeke",
                        "sinyal": -72,
                        "ark_olay": 0
                    }
                    service.update_modul_data(idx, sample_data)

            await asyncio.sleep(4)

async def main():
    service = ModbusService(max_moduller=10)
    asyncio.create_task(sync_data_loop(service))

    logging.info(f"🚀 Modbus TCP SCADA Sunucusu Başlatılıyor: {MODBUS_HOST}:{MODBUS_PORT}")
    logging.info(f"📋 Sözleşme ④ Register Bloğu: Adres 100 - 139 (Modül 1 ve Modül 2)")
    await StartAsyncTcpServer(context=service.context, address=(MODBUS_HOST, MODBUS_PORT))

if __name__ == "__main__":
    asyncio.run(main())