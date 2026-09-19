# Grid Up Hackathon — İZ C: Operasyon Yüzü Dokümantasyonu (v4 - Final)

**Sorumlu Kulvar:** İZ C (Operasyon Yüzü & Entegrasyon)  
**Tarih:** Eylül 2026  
**Sürüm:** 4.0.0 (Revize & Üretime Hazır)  
**Proje:** Pano/Hücre İçi Anomali Erken Uyarı ve SCADA İzleme Sistemi  

---

## 1. Giriş ve Amaç

Bu doküman, ADM Elektrik ve GDZ Elektrik tarafından düzenlenen **Grid Up Hackathon** kapsamında geliştirilen **Pano/Hücre İçi Anomali Erken Uyarı Sistemi**'nin **İZ C (Operasyon Yüzü)** kulvarına ait güncel mimariyi, bileşen detaylarını, Modbus TCP register haritasını, acil bildirim servisinin kanal kurallarını, modern web arayüzünü ve on-premise kurulum adımlarını tanımlar.

İZ C kulvarı; sahadan toplanan (İZ A) ve yapay zeka/makine öğrenmesi algoritmalarıyla analiz edilen (İZ B) anomali verilerini operatörlerin 7/24 anlık takip edebileceği yüksek standartlı bir SCADA/Monitoring Operasyon Merkezine dönüştürür. Dış SCADA altyapılarına endüstriyel Modbus TCP üzerinden veri aktarırken, sahada görev yapan mühendislere, teslimi izlenen ve tekrarı önlenen acil alarmlar iletir.

### Karşılanan Hackathon Teslimat Kalemleri
* **T4 (Monitoring / İzleme):** Merkezi toplama ve izleme web uygulaması, saha hiyerarşisi (`Saha → Pano → Modül`), 32×24 (768 piksel) termal ısı haritası görselleştirmesi, canlı sıcak nokta (hotspot) reticle takibi ve SCADA entegrasyonu (Modbus TCP haritalama).
* **T6 (On-Premise / Yerel Altyapı):** Public Cloud (AWS, Azure, GCP vb.) kullanılmaksızın şirket içi/yerel sunucu altyapısında çalışma garantisi (`docker-compose.yml` mikroservis kompozisyonu).
* **T7 (Alarm ve Acil Bildirim Mekanizması):** Kritik ve Uyarı seviyelerinde seviye→kanal kuralına göre dış bildirim; kritik için on-prem SMS gateway **zorunlu** kanaldır. Teslim edilemeyen alarm yeniden denenir, olay bazlı tekrar önleme (varsayılan 300 sn) mükerrer bildirimi engeller. **Kanal seçimi (yerel GSM modemi / SMS gateway) ekip kararı olarak açıktır; gerçek SIM üzerinden teslim doğrulanmamıştır.**

---

## 2. Sistem Mimarisi ve Repo Düzeni

Proje dizini, yarışmanın tek repo standartlarına uygun olarak modüler mikroservisler şeklinde yapılandırılmıştır:

```
├── sozlesmeler/               ← Sözleşme JSON şemaları (Ortak)
│   ├── sozlesme_3_anomali.json     ← İZ B -> İZ C: Anomali Çıktı Şeması
│   ├── sozlesme_4_modbus.json      ← İZ C -> Dış SCADA: Modbus Register Haritası
│   └── sozlesme_5_api.json         ← İZ B -> İZ C: Saha & Modül Okuma API'si
├── arayuz/                    ← İZ C: Monitoring & SCADA Operasyon Arayüzü
│   ├── index.html                  ← Modern Semantik SCADA Dashboard Arayüzü
│   ├── style.css                   ← SCADA Koyu Tema, Cam Efekti & Mikro Animasyonlar
│   ├── app.js                      ← Canvas Termal Çizim, Tooltip, Sesli Alarm & API İstemcisi
│   └── Dockerfile                  ← Nginx Alpine Web Sunucusu
├── modbus/                    ← İZ C: SCADA için Modbus TCP Sunucu Servisi
│   ├── modbus_server.py            ← Port 5020 PyModbus Asenkron Sunucu & API Senkronizasyonu
│   ├── test_client.py              ← SCADA İstemci Okuma Doğrulama Testi
│   └── Dockerfile                  ← Modbus Konteyneri
├── alarm/                     ← İZ C: Anomali Geçiş Dinleyici & Alarm Servisi
│   ├── alarm_service.py            ← Geçiş değerlendirme, teslim takibi, tekrar önleme
│   ├── kanallar.py                 ← Kanallar (konsol / on-prem SMS / Telegram) & seviye kuralı
│   ├── durum.py                    ← Atomik kalıcı durum, bozuk dosya politikası
│   ├── test.py                     ← 41 birim/davranış testi (A-01..A-05)
│   ├── entegrasyon_testi.py        ← Gerçek süreç yeniden başlatma testi
│   ├── README.md                   ← Alarm servisi işletme dokümanı
│   └── Dockerfile                  ← Alarm Konteyneri
├── deploy/                    ← İZ C: On-Premise Dağıtım
│   └── docker-compose.yml          ← Tek Komutla 4 Mikroservisli Dağıtım Kompozisyonu
├── docs/                      ← İZ C: Operasyon Yüzü Teknik Dokümantasyonu
│   └── operasyon-yuzu-dokumantasyonu.md
├── mock_api_server.py         ← Saha Simülasyonu, REST API (Port: 8000) & Arayüz Sunucusu
└── Dockerfile.mock            ← Mock API Docker Tanımı
```

---

## 3. Teknik Sözleşmeler (Contracts)

İZ C kulvarı, yarışma şartnamesinde tanımlanan üç temel teknik sözleşmeyi uygular:

### Sözleşme ③ — Anomali Çıktısı (`sozlesmeler/sozlesme_3_anomali.json`)
İZ B tarafından üretilen ve anomali tespiti gerçekleştiğinde alarm servisi ve web arayüzü tarafından tüketilen veri yapısıdır:
```json
{
  "id": "an_00412",
  "modul_id": "TR041-P01-M1",
  "zaman": "10:24:30",
  "skor": 0.89,
  "seviye": "uyari",
  "tip": "sicak_nokta",
  "gerekce": "L2 çıkış klemensi 34 dk içinde +18 °C yükseldi, akım sabit kaldı."
}
```

### Sözleşme ④ — Modbus TCP Register Haritası (`sozlesmeler/sozlesme_4_modbus.json`)
Dış SCADA/RTU sistemlerine 5020 portu üzerinden açılan holding register yapısıdır. Her modül için **20 register'lık sabit blok** ayrılmıştır. Başlangıç adresi formülü:
$$\text{Adres} = 100 + (N - 1) \times 20$$

### Sözleşme ⑤ — Okuma API'si (`sozlesmeler/sozlesme_5_api.json`)
* `GET /api/sahalar`: `Saha → Pano → Modül` hiyerarşisi ve anlık modül sağlık durumları (`normal`, `izle`, `uyari`, `kritik`).
* `GET /api/moduller/{id}`: Ortam sıcaklığı, nem, 3-faz akımları (L1, L2, L3), nötr akımı, besleme kaynağı, RSSI sinyali, ark olay sayısı, termal özet ve 32×24 (768 piksel) matris.
* `GET /api/anomaliler`: Aktif ve operatör onayı bekleyen açık anomaliler listesi.
* `POST /api/anomaliler/{id}/onayla`: Operatörün anomaliyi inceleyip kapatma akışı.

---

## 4. SCADA Entegrasyonu: Modbus TCP Sunucusu (`/modbus`)

Dış SCADA ve RTU sistemlerinin sahadaki elektriksel ve termal parametreleri endüstriyel standartlarda okuyabilmesi için PyModbus altyapısında asenkron bir Modbus TCP sunucusu (`modbus_server.py`) kurulmuştur.

### Register Tablosu (Modül 1: 100..119, Modül 2: 120..139)

| Offset | Adres (M1) | Parametre Adı | Veri Tipi | Çarpan | Birim | Açıklama |
| :---: | :---: | :--- | :---: | :---: | :---: | :--- |
| **+0** | 100 | Ortam Sıcaklığı | UInt16 | 0.1 | °C | Değer / 10 (Örn: 347 = 34.7 °C) |
| **+1** | 101 | Bağıl Nem | UInt16 | 0.1 | % | Değer / 10 (Örn: 450 = 45.0 %) |
| **+2** | 102 | L1 Faz Akımı | UInt16 | 0.1 | A | Değer / 10 (Örn: 1205 = 120.5 A) |
| **+3** | 103 | L2 Faz Akımı | UInt16 | 0.1 | A | Değer / 10 (Örn: 1594 = 159.4 A) |
| **+4** | 104 | L3 Faz Akımı | UInt16 | 0.1 | A | Değer / 10 (Örn: 1198 = 119.8 A) |
| **+5** | 105 | Nötr Akımı | UInt16 | 0.1 | A | Değer / 10 (Örn: 24 = 2.4 A) |
| **+6** | 106 | Termal Maks. Sıcaklık | UInt16 | 0.1 | °C | Değer / 10 (Örn: 835 = 83.5 °C) |
| **+7** | 107 | Anomali Seviyesi | UInt16 | 1 | Enum | 0: Normal, 1: İzle, 2: Uyarı, 3: Kritik |
| **+8** | 108 | Modül Besleme Durumu | UInt16 | 1 | Enum | 0: Şebeke, 1: Yedek (Akü/UPS) |
| **+9** | 109 | Sinyal Gücü (RSSI) | Int16 | 1 | dBm | İşaretli 16-bit tamsayı (Örn: -72 dBm) |
| **+10** | 110 | Ark Olay Sayısı | UInt16 | 1 | Sayaç | TVOC-2 optik koruma trip sayısı |
| **+11..19**| 111–119 | *Yedek Kanallar* | UInt16 | - | - | Genişleme için ayrılmış |

### Çift Modlu Çalışma (Dual-Mode Sync)
Modbus servisi, çalışma anında `API_URL` üzerinden canlı modül verilerini periyodik olarak sorgular. REST API erişilebilir durumdaysa canlı ölçümler register'lara yazılır; bağlantı koparsa dahili güvenli simülasyon moduna kesintisiz geçerek SCADA hattının boş kalmasını engeller.

---

## 5. Alarm ve Acil Bildirim Servisi (`/alarm`)

Kritik arızanın operatörün gözünden kaçmaması için `GET /gecisler` akışını
dinleyen, çok kanallı bir alarm servisi geliştirilmiştir. Ayrıntılı işletme
dokümanı: **`alarm/README.md`**.

### 5.1 Dört ayrı olay, dört ayrı söz

Servis şunları bilerek birbirinden ayırır ve raporlarda da ayrı tutulmalıdır:

| Söz | Ne demek | Kim görebilir |
|---|---|---|
| **loglandı** | Konsol kanalı satırı yazdı | Servis |
| **kanal kabul etti** | SMS gateway / Telegram 2xx döndü | Servis |
| **SMS gerçekten teslim edildi** | Operatörün telefonunda mesaj var | **Servis göremez** |
| **operatör onayladı** | `POST /anomaliler/{id}/onayla` çağrıldı | İZ B / arayüz |

### 5.2 Seviye → kanal kuralı

`ALARM_KANAL_KURALI` ile tanımlanır; sondaki `!` o kanalı **zorunlu** yapar.
Varsayılan: `uyari:konsol,sms | kritik:konsol,sms!`

* `normal`, `izle` → dış bildirim yok.
* `uyari` → konsol + SMS denenir; SMS hatası olayı bekletmez.
* `kritik` → SMS **zorunlu**; gateway reddederse olay teslim edilmiş sayılmaz.

`konsol` hiçbir varsayılan kuralda zorunlu değildir: kritik alarmın yalnız
loga yazılması dış bildirim sayılmaz.

### 5.3 Kanal seçimi ve public cloud kısıtı — **AÇIK BAĞIMLILIK**

Karar kaydı §T6 public cloud'u yasaklar. `sms` kanalı belirli bir ürüne bağlı
değildir: yapılandırılabilir alan adlarıyla yerel bir HTTP uca POST eder, yani
yerel GSM modemi, Android SMS Gateway veya kurum içi gateway aynı adaptörle
sürülür. **Hangisinin kullanılacağı henüz seçilmemiştir.**

Telegram kanalı korunmuştur ama **bulut** olarak işaretlidir, varsayılan
kuralda yer almaz ve açıkken servis §T6 ile çeliştiğini açılışta yazar.
WhatsApp Business API de bulut tarafında çalışır ve aynı çelişkiyi taşır.

**Gerçek bir SIM'den gerçek bir telefona uçtan uca SMS teslimi
DOĞRULANMAMIŞTIR;** testlerdeki "teslim", sahte bir gateway'in isteği kabul
etmesidir. Maliyet ve fiilî teslim ayrıca doğrulanmalıdır.

### 5.4 Tekrar önleme

Anahtar **olaydır, modül değil**: `anomali_id + hedef seviye`.

* Aynı moduldeki iki ayrı anomali birbirini bastırmaz.
* `uyari → kritik` yükselmesi önceki `uyari` bildiriminin bekleme süresine
  takılmaz.
* Aynı olayın aynı seviyedeki eşdeğer tekrarı `COOLDOWN_SECONDS` (varsayılan
  300 sn) boyunca bastırılır — "aynı alarm 50 kez gitmesin".
* **Başarısız teslim tekrar önleme başlatmaz**: kanal hatası kendi yeniden
  denemesini bastıramaz.

### 5.5 Teslim takibi ve kalıcı durum

Zorunlu kanal başarısızsa olay teslim edilmiş sayılmaz; geçiş tam gövdesiyle
`bekleyen` kuyruğuna alınır ve imleçle **aynı atomik yazımda** kalıcılaşır.
İmleç ilerler (tek bir başarısız olay arkasındaki kritik alarmları rehin
almaz) ama başarısız geçiş atlanmaz: üstel geri çekilmeyle yeniden denenir ve
servis/konteyner yeniden başlatmasından sağ çıkar.

Durum `/durum/alarm_state.json` altında, `gridup_alarm_durum` volume'unda
tutulur. Yazma hatası başarı sayılmaz, bozuk durum dosyası sessizce
sıfırlanmaz (varsayılan: servis açılmaz).

**Kabul edilen sınır:** kanal olumlu yanıt verdikten sonra durum diske inmeden
süreç ölürse o bildirim yeniden gönderilebilir. Tekrar bildirim ile sessiz
alarm kaybı arasında tercih yapılmış, tekrar bildirim seçilmiştir.

### 5.6 Ortam değişkenleri

`API_URL`, `POLL_INTERVAL`, `COOLDOWN_SECONDS`, `ALARM_KANAL_KURALI`,
`ALARM_STATE_FILE`, `ALARM_BOZUK_DURUM`, `SMS_GATEWAY_URL`, `SMS_ALICILAR`,
`SMS_GATEWAY_TOKEN`, `SMS_GATEWAY_ALICI_ALANI`, `SMS_GATEWAY_MESAJ_ALANI`,
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. Tam liste `alarm/README.md` §2'de.
Repoda gömülü anahtar yoktur (Madde 15).

---

## 6. SCADA & Monitoring Operasyon Arayüzü (`/arayuz`)

Modern SCADA Operasyon Merkezleri standartlarında geliştirilen web arayüzü (`index.html`, `style.css`, `app.js`), operatörün tüm sahayı tek ekrandan analiz etmesini sağlar.

### Arayüz Yetenekleri
* **Saha Hiyerarşisi Ağacı (Sol Panel):** `Saha → Pano → Modül` yapısı, anlık durum LED rozetleri (Normal: Yeşil, İzle: Mavi, Uyarı: Sarı, Kritik: Kırmızı) ve modüller arası anında geçiş.
* **6'lı Kritik Metrik Paneli:**
  1. Ortam Sıcaklığı (°C - SHT31)
  2. Bağıl Nem (% - SHT31)
  3. Termal Maks. Sıcaklık (°C - MLX90640 Hotspot)
  4. 3-Faz Akım Yükü (L1, L2, L3 ve otomatik Faz Dengesizliği % hesabı)
  5. Nötr Dönüş Hattı Akımı (A)
  6. TVOC-2 Ark Olay Sayacı & RSSI Sinyal Gücü
* **32×24 Termal Matris Isı Haritası (Canvas Engine):**
  - MLX90640 sensöründen gelen 768 piksellik matrisi HSL renk skalasıyla (20°C Soğuk Mavi → 85°C Aşırı Sıcak Kırmızı) görselleştirir.
  - **Canlı Hotspot Reticle:** Sıcak noktanın ($X, Y$) koordinatına animasyonlu hedef halkası ve derece etiketi yerleştirir.
  - **Fare Hover HUD Tooltip:** Kullanıcı canvas üzerinde fareyi gezdirdiğinde anlık piksel koordinatını (`X: 14, Y: 10`) ve o noktadaki sıcaklığı (`83.5 °C`) gösterir.
  - **Pürüzsüzleştirme (Bilinear/Smooth) & Izgara (Grid) Seçenekleri.**
* **Alarm ve Operatör Onay Akışı (Sağ Panel):**
  - Açık alarmlar kartlar halinde gerekçesiyle birlikte listelenir.
  - **Web Audio API Entegrasyonu:** Yeni bir kritik/uyarı alarmı geldiğinde harici dosya gerektirmeyen profesyonel SCADA bip sesi çalar (Ses Açık/Kapalı butonu mevcuttur).
  - **Operatör Onayı (Kapat):** Butona tıklandığında `POST /api/anomaliler/{id}/onayla` isteği gönderilir ve anomali sistemden düşürülür.
  - **Operasyon Günlüğü (Audit Trail):** Onaylanan alarmlar ve zaman damgaları ikinci sekmede denetim kaydı olarak arşivlenir.

---

## 7. On-Premise Dağıtım Kompozisyonu (`/deploy`)

Yarışmanın **Public Cloud Yasağı (T6)** kuralına tam uyum sağlamak amacıyla tüm mikroservisler konteynerleştirilmiş ve `docker-compose.yml` altında birleştirilmiştir.

### Tek Komutla Kurulum
Saha sunucusunda yerel altyapıyı ayağa kaldırmak için:

```bash
cd deploy
docker compose up -d --build
```

### Servis ve Port Haritası
| Servis | Konteyner Adı | Port | Görev |
| :--- | :--- | :--- | :--- |
| **Monitoring Arayüzü** | `gridup_arayuz` | `80:80` | Nginx üzerinde çalışan modern operasyon arayüzü |
| **SCADA Modbus Sunucusu** | `gridup_modbus` | `5020:5020` | Dış SCADA/RTU sistemlerine Holding Register yayını |
| **Mock API & Dashboard** | `gridup_mock_api` | `8000:8000` | Canlı veri simülasyonu, REST API ve arayüz sunumu |
| **Alarm Servisi** | `gridup_alarm` | Dahili Ağ | Geçiş akışı dinleyicisi, seviye→kanal kuralı, on-prem SMS bildirimi (`gridup_alarm_durum` volume'u ile kalıcı durum) |

---

## 8. Doğrulama ve Canlı Testler

Sistem bileşenleri uçtan uca test edilmiş ve doğrulanmıştır:

1. **Mock API ve REST Uç Noktaları:**
   ```bash
   python mock_api_server.py
   # Tarayıcıda: http://localhost:8000/
   # API Test: curl http://localhost:8000/api/sahalar
   # API Test: curl http://localhost:8000/api/moduller/TR041-P01-M1
   # API Test: curl http://localhost:8000/api/anomaliler
   ```
2. **Modbus TCP Sunucu & İstemci Okuması:**
   ```bash
   python modbus/modbus_server.py
   python modbus/test_client.py
   # 100. register'dan 11 parametre başarıyla okunmuş ve fiziki birimlere dönüştürülmüştür.
   ```
3. **Alarm Servisi Testleri:**
   ```bash
   cd alarm && python3 -m unittest test        # 41 test — A-01..A-05 olumlu/olumsuz yolları
   cd alarm && python3 entegrasyon_testi.py    # servisi gerçek süreç olarak öldürüp yeniden başlatır
   ```
   Her ikisi de geçmektedir. Hiçbiri gerçek veritabanına, gerçek `/gecisler`
   ucuna ya da gerçek bir alıcıya bağlanmaz: HTTP uçları ve SMS gateway
   sahtedir. Bu testler "kanal kabul etti"yi gösterir, **gerçek SMS teslimini
   göstermez**. Konteyner yeniden oluşturma testi (`docker compose down && up`)
   **henüz çalıştırılmamıştır**.

---

## 9. Sonuç

Grid Up Hackathon İZ C (Operasyon Yüzü); endüstriyel SCADA uyumluluğunu, modern web tabanlı izleme panelini, termal matris görselleştirmesini, teslim takibi yapan ve olay bazlı tekrar önleme uygulayan acil bildirim mekanizmasını ve tam yerel (on-premise) dağıtılabilirliği tek bir mimari çatı altında sunmaktadır. Acil bildirim kanalının nihai seçimi ve gerçek SMS teslimi doğrulaması **açık maddedir**.
