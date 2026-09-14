# listener.py
import time
import requests
from alarm_service import AlarmManager

manager = AlarmManager(cooldown_seconds=300)

print("🚀 Alarm Servisi Mock API'yi dinliyor (http://localhost:8000/api/anomaliler)...")

while True:
    try:
        # Sunucu kapalı veya yavaş olduğunda kodun asılı kalmaması için timeout=4
        response = requests.get("http://localhost:8000/api/anomaliler", timeout=4)
        if response.status_code == 200:
            anomaliler = response.json()
            manager.process_anomalies(anomaliler)
    except requests.exceptions.ConnectionError:
        print("[BAĞLANTI BEKLENİYOR] Mock API (localhost:8000) henüz aktif değil...")
    except requests.exceptions.Timeout:
        print("[ZAMAN AŞIMI] API yanıt vermedi.")
    except Exception as e:
        print(f"Hata: {e}")
    
    time.sleep(5)