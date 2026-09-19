# /modbus/test_client.py
from pymodbus.client import ModbusTcpClient

def test_read_scada():
    client = ModbusTcpClient('localhost', port=5020)
    
    if client.connect():
        # Modül 1 için 100. adresten 11 register oku
        response = client.read_holding_registers(address=100, count=11)
        
        if not response.isError():
            regs = response.registers
            print("=== MODBUS SCADA OKUMASI BAŞARILI ===")
            print(f"Ortam Sıcaklık : {regs[0] / 10.0} °C")
            print(f"Bağıl Nem      : {regs[1] / 10.0} %")
            print(f"L1 Akımı       : {regs[2] / 10.0} A")
            print(f"L2 Akımı       : {regs[3] / 10.0} A")
            print(f"L3 Akımı       : {regs[4] / 10.0} A")
            print(f"Nötr Akımı     : {regs[5] / 10.0} A")
            print(f"Termal Maks    : {regs[6] / 10.0} °C")
            print(f"Alarm Seviyesi : {regs[7]} (0:Normal, 1:İzle, 2:Uyarı, 3:Kritik)")
            print(f"Besleme Durumu : {regs[8]} (0:Şebeke, 1:Yedek)")
            
            # 16-bit signed integer (negatif RSSI değerini geri çevirme)
            raw_rssi = regs[9]
            rssi = raw_rssi if raw_rssi < 0x8000 else raw_rssi - 0x10000
            print(f"RSSI Sinyal    : {rssi} dBm")
            
            print(f"Ark Olay Sayısı: {regs[10]}")
        else:
            print("Hata: Register verileri okunamadı.")
            
        client.close()
    else:
        print("Hata: Modbus sunucusuna (localhost:5020) bağlanılamadı.")

if __name__ == "__main__":
    test_read_scada()