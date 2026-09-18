# test_modbus_service.py
"""
ModbusService update_modul_data mantığını ve veri gelmediğinde sıfır yazılmama kuralını (Madde 20) test eder.
"""

import unittest
from modbus_server import ModbusService

class TestModbusService(unittest.TestCase):
    def test_update_and_zero_protection(self):
        service = ModbusService(max_moduller=2)

        # 1. İlk gerçek ölçüm verisi
        modul_detay_1 = {
            "modul_id": "TR041-P01-M1",
            "besleme": "sebeke",
            "sinyal": -72,
            "seviye": "uyari",
            "son_olcumler": [
                {"olcum_tipi": "ortam_sicaklik", "deger": 34.7},
                {"olcum_tipi": "nem", "deger": 45.2},
                {"olcum_tipi": "akim_l1", "deger": 120.0},
                {"olcum_tipi": "akim_l2", "deger": 150.5},
                {"olcum_tipi": "akim_l3", "deger": 118.0},
                {"olcum_tipi": "akim_notr", "deger": 3.1},
                {"olcum_tipi": "ark_olay", "deger": 1}
            ]
        }
        termal_ozet_1 = {"maks": 82.4}

        service.update_modul_data(1, modul_detay_1, termal_ozet_1)

        # Adres 100'den itibaren oku
        values = service.store.getValues(3, 100, 11)
        self.assertEqual(values[0], 347)   # Ortam sıcaklığı: 34.7 * 10
        self.assertEqual(values[1], 452)   # Nem: 45.2 * 10
        self.assertEqual(values[2], 1200)  # L1: 120.0 * 10
        self.assertEqual(values[3], 1505)  # L2: 150.5 * 10
        self.assertEqual(values[4], 1180)  # L3: 118.0 * 10
        self.assertEqual(values[5], 31)    # Nötr: 3.1 * 10
        self.assertEqual(values[6], 824)   # Termal maks: 82.4 * 10
        self.assertEqual(values[7], 2)     # Anomali seviyesi: uyari (2)
        self.assertEqual(values[8], 0)     # Besleme: sebeke (0)
        self.assertEqual(values[9], (-72) & 0xFFFF) # Sinyal RSSI
        self.assertEqual(values[10], 1)    # Ark olay sayısı: 1

        # 2. Madde 20: Eksik / veri gelmeme durumunda sıfır yazılmaması kontrolü
        # Bir sonraki turda yalnızca nem güncellendi, diğer ölçümler gelmedi
        modul_detay_2 = {
            "modul_id": "TR041-P01-M1",
            "son_olcumler": [
                {"olcum_tipi": "nem", "deger": 50.0}
            ]
        }
        service.update_modul_data(1, modul_detay_2, None)

        values_sonraki = service.store.getValues(3, 100, 11)
        # Nem güncellenmeli (50.0 -> 500)
        self.assertEqual(values_sonraki[1], 500)
        # Diğer alanlar SIFIRLANMAMALI, önceki değerleri korunmalı!
        self.assertEqual(values_sonraki[0], 347)  # Ortam sıcaklığı hala 347
        self.assertEqual(values_sonraki[2], 1200) # L1 akımı hala 1200
        self.assertEqual(values_sonraki[6], 824)  # Termal maks hala 824
        self.assertEqual(values_sonraki[7], 2)    # Seviye hala 2

if __name__ == "__main__":
    unittest.main()
