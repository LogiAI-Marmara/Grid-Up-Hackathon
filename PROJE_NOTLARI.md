# Grid-Up Hackathon - Proje Notları & Veri Özeti

**Düzenleyen:** ADM & GDZ Elektrik (Skillcamp by Patika.dev)  
**Takım:** İsmail, Efe (thozoz), Onur (1-4 kişilik takım yapısı)  
**Proje Konusu:** OG Hücreleri ve AG Panolarda Pano İçi Anomali Erken Uyarı Sistemi  
**Yerel Çalışma Dizini:** `/home/hermes/grid-up/`  
**Drive Veri Dizini:** `/home/hermes/grid-up/drive_data/Hackathon Verileri/`

---

## 1. Hackathon Takvimi ve Ödül Havuzu
- **Resmi Başlangıç:** 10 Eylül 2026
- **Geliştirme & Son Teslim:** **20 Eylül 2026** (Skillcamp üzerinden teslim edilecek)
- **Jüri Değerlendirmesi:** 21 – 28 Eylül 2026 (Finalistlerin seçimi)
- **Final Sunumları (Demo Day):** **6 Ekim 2026** (Online canlı sunum)
- **Ödüller (Toplam 200.000 TL):**
  - 🥇 1. Takım: 100.000 TL
  - 🥈 2. Takım: 70.000 TL
  - 🥉 3. Takım: 30.000 TL

---

## 2. Skillcamp Platformu & İletişim Akışı
- **Platform:** Skillcamp (Patika.dev kurumsal platformu).
- **Soru-Cevap:** Tüm teknik ve idari sorular Skillcamp platformu üzerinden iletilir. Sorular ve GDZ/ADM teknik ekiplerinden gelen yanıtlar tüm takımlara açık/şeffaftır.
- **Teslim Ekranı:** Platformun sol menüsündeki teslim paneli üzerinden proje dosyaları, rapor ve kodlar yüklenecektir.

---

## 3. Problem Tanımı ve Saha Gerçekleri
- **Kritik Riskler:** OG hücreleri ve 1600 kVA AG dağıtım panolarında yangın, ark patlaması, aşırı akım, aşırı ısınma, izolasyon delinmesi ve plansız enerji kesintileri.
- **Saha Zorluğu (Mission-Critical):** Panolar aşırı kablo yığınına sahiptir. Yeni eklenecek kablolu sensörler kaosu artırır ve montaj sırasında şebekeyi riske atar.
- **Tasarım Beklentisi:** 
  - Tercihen **kablosuz**, **tak-çalıştır**, **bakım gerektirmeyen**, panoda planlı kesinti ihtiyacını minimuma indiren modüler tasarım.
  - Zorlu pano ortamı (yüksek sıcaklık, yoğun manyetik alan, toz).

---

## 4. Zorunlu Teknik Çıktılar & Kısıtlar
1. **On-Premise Mimari:** Public Cloud (AWS, Azure vb.) yasaktır. Sistem yerel şirket sunucularında veya özel altyapıda koşmalıdır.
2. **SCADA / Modbus Haritalama:** Saha RTU/SCADA sistemleriyle konuşabilecek Modbus register haritası çıkarılmalıdır.
3. **Anomali ve Erken Uyarı Algoritması:**
   - Normal vs. anormal çalışma ayrımı.
   - Yangın/patlama gerçekleşmeden önceki öncül sinyallerin (kısmi deşarj, optik ark ışığı, sıcaklık gradyanı, harmonik/aşırı akım) tespiti.
4. **Monitoring & Canlı Arayüz:** Merkezi operasyon ekipleri için anlık pano durumu, alarm seviyeleri ve geçmiş trend grafikleri.
5. **Alarm / Bildirim Sistemi:** Ekiplere anlık SMS / WhatsApp entegrasyonu (webhook / API).
6. **Fiziksel Kurulum Şart Değil:** Donanım satın alma veya panoya montaj beklenmiyor; şematik/blok diyagram, bileşen seçimi ve sentetik/simüle veriyle çalışan prototip yeterlidir.
7. **Ölçeklenebilirlik:** En az 100 panoyu eşzamanlı izleyebilecek hafif mimari.

---

## 5. İndirilen Drive Dokümanları & Veriler
- `Grid Up Hackathon Proje Konusu.pdf`: Şartname ve puanlama kriterleri.
- `İstenen Veriler.xlsx`: 
  - **Akım:** 100mA/125mA sekonder, 600A primer sentetik zaman serisi verileri.
  - **Ark:** ABB TVOC-2 Modbus register referansı.
  - **PD (Kısmi Deşarj):** EA Technology HFCT-30/50 yüksek frekanslı akım trafosu.
  - **Sıcaklık & Nem:** Ortam ve yüzey sıcaklığı.
- `1SFC170017M0201_Rev_D_TVOC-2_Modbus_Manual.pdf` & `tvoc.pdf`: ABB Arc Guard TVOC-2 optik ark sensörü Modbus RTU kılavuzu.
- `MPR-53CS_Modbus_Register_Map_EN.pdf`: ENTES enerji analizörü register yapısı.
- `DS_HFCT30_eng.pdf` & `DS_HFCT50_eng.pdf`: Kısmi deşarj için HFCT sensör veri föyleri.
- `1600kVA AG Pano Teknik Özellikleri.pdf` & `AG Pano Teknik Çizim-1600kVA.pdf`: Referans 1600kVA pano yerleşimi ve TEDAŞ şartnamesi.
- `youtube_transcript.txt`: Açılış etkinliğinin tam transkripti ve jüri/teknik ekip vurguları.
