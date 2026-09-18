# test.py
"""
Grid Up Hackathon - İZ C: Alarm Servisi Birim ve Durum Testleri
Geçiş akışı değerlendirmesi, seviye yükselmesi, anti-flapping ve durum saklamayı doğrular.
"""

import os
import json
import time
import unittest
from unittest.mock import patch, MagicMock
from alarm_service import AlarmManager, SEVIYE_DERECESI

class TestAlarmService(unittest.TestCase):
    def setUp(self):
        self.test_state_file = "test_alarm_state.json"
        if os.path.exists(self.test_state_file):
            os.remove(self.test_state_file)

    def tearDown(self):
        if os.path.exists(self.test_state_file):
            os.remove(self.test_state_file)

    def test_seviye_dereceleri(self):
        self.assertLess(SEVIYE_DERECESI["normal"], SEVIYE_DERECESI["izle"])
        self.assertLess(SEVIYE_DERECESI["izle"], SEVIYE_DERECESI["uyari"])
        self.assertLess(SEVIYE_DERECESI["uyari"], SEVIYE_DERECESI["kritik"])

    def test_state_persistence(self):
        manager = AlarmManager(state_file=self.test_state_file)
        manager.state["son_gecis_id"] = 1234
        manager.save_state()

        # Yeni yönetici oluşturulduğunda eski durum okunabilmeli
        manager2 = AlarmManager(state_file=self.test_state_file)
        self.assertEqual(manager2.state.get("son_gecis_id"), 1234)

    @patch("alarm_service.AlarmManager.fetch_anomaly_detail")
    def test_evaluate_transition_escalation(self, mock_detail):
        mock_detail.return_value = {
            "modul_id": "TR041-P01-M1",
            "gerekce": "L2 klemensi aşırı ısındı.",
            "skor": 0.85
        }

        manager = AlarmManager(cooldown_seconds=10, state_file=self.test_state_file)
        manager.emit_notification = MagicMock()

        # 1. Normal geçiş (izle -> uyari): bildirim gitmeli
        gecis_uyari = {
            "id": 101,
            "anomali_id": "an_001",
            "alan": "seviye",
            "onceki": "izle",
            "yeni": "uyari",
            "zaman": "2026-09-17T10:00:00Z"
        }
        manager.evaluate_transition(gecis_uyari)
        self.assertEqual(manager.emit_notification.call_count, 1)

        # 2. Anti-flapping: Cooldown içinde ikinci kez gelirse tetiklenmemeli
        manager.evaluate_transition(gecis_uyari)
        self.assertEqual(manager.emit_notification.call_count, 1)

        # 3. Seviye düşüşü (uyari -> izle): bildirim tetiklenmemeli
        gecis_dususu = {
            "id": 102,
            "anomali_id": "an_001",
            "alan": "seviye",
            "onceki": "uyari",
            "yeni": "izle",
            "zaman": "2026-09-17T10:01:00Z"
        }
        manager.evaluate_transition(gecis_dususu)
        self.assertEqual(manager.emit_notification.call_count, 1)

    @patch("requests.get")
    def test_poll_transitions(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "veriler": [
                {
                    "id": 501,
                    "anomali_id": "an_005",
                    "alan": "seviye",
                    "onceki": "normal",
                    "yeni": "kritik",
                    "zaman": "2026-09-17T12:00:00Z"
                }
            ],
            "sonraki": 501,
            "limit": 100
        }
        mock_get.return_value = mock_response

        manager = AlarmManager(state_file=self.test_state_file)
        manager.evaluate_transition = MagicMock()
        manager.poll_transitions()

        self.assertEqual(manager.evaluate_transition.call_count, 1)
        self.assertEqual(manager.state.get("son_gecis_id"), 501)

if __name__ == "__main__":
    unittest.main()