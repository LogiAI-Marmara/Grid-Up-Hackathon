# 3. Bağlantı ve Pinout Tablosu

**Teslimat karşılığı:** T2 (giriş-çıkış bağlantıları, bağlantı şemaları)
**Dayandığı kararlar:** §7.1 ölçüm kümesi · §7.4 haberleşme
**Biçim notu:** §7 karar kaydı satır 626: *"Çizim olmak zorunda değil, tablo da olabilir."*
Bu doküman tablo biçimindedir; arayüz özeti ve blok şema için bkz. [1. doküman](01-blok-sema.md).

---

## 3.1 Arayüzler ve kullanılan pinler (öneri)

> **Durum:** Aşağıdaki pin atamaları **tasarım önerisidir**, PCB yerleşimi sırasında
> doğrulanacaktır. Pin numaraları Espressif datasheet'inden (ESP32-S3-WROOM-1U, v1.8)
> doğrulanmış **kısıtlara** uyacak şekilde seçilmiştir; atamanın kendisi bu dokümanın kararıdır.

| Arayüz | Sinyal | GPIO | Gerekçe / kısıt |
|---|---|---|---|
| **I²C (paylaşımlı)** | SDA | GPIO8 | Strapping değil, USB değil, flash değil — serbest |
| | SCL | GPIO9 | Aynı; I²C hattı iki sensör tarafından paylaşılır |
| **Akım kanalı A** | CT L1 | GPIO4 | **ADC1_CH3** — Wi-Fi ile birlikte kullanılabilir |
| **Akım kanalı B** | CT L2 | GPIO5 | **ADC1_CH4** |
| **Akım kanalı C** | CT L3 | GPIO6 | **ADC1_CH5** |
| **Akım kanalı D** | CT nötr | GPIO7 | **ADC1_CH6** |
| **Modbus hattı** | UART TX | GPIO17 | Datasheet: `U1TXD` |
| | UART RX | GPIO18 | Datasheet: `U1RXD` |
| | DE/RE (yön) | GPIO21 | RS-485 alıcı-verici yön kontrolü |
| **Genişleme payı** | (ayrılmış) | GPIO10, GPIO11 | Kullanılmıyor; PD/akustik için ayrıldı (§7.1 satır 237) |
| **Anten** | U.FL | — | GPIO değil; `1U` varyantının harici konnektörü |
| **Besleme** | 3V3 / GND | — | AC/DC modül çıkışı |
| **Reset** | EN | — | Kart üzerinde RC + buton |

### ⚠️ Kritik teknik kısıt — ADC2 Wi-Fi ile kullanılamaz

ESP32-S3'te **ADC2 kanalları, Wi-Fi aktifken kullanılamaz** (Wi-Fi radyosu ADC2'yi paylaşır).
Modülümüz sürekli Wi-Fi üzerinden veri gönderdiği için, 4 akım kanalının **tamamı ADC1'e**
atanmak zorundadır.

- ✓ ADC1_CH3…CH6 → GPIO4, GPIO5, GPIO6, GPIO7 (L1, L2, L3, nötr) — **seçilen**
- ✗ ADC2 kanalları — haberleşme aktifken güvenilir okunamaz, bu nedenle kullanılmaz

Bu kısıt, "analizör yoksa 4 split-core CT" senaryosunda tasarımı doğrudan belirler.
Alternatif: harici bir ADC çipi (I²C/SPI üzerinden) kullanmak — BOM'da opsiyonel kalem olarak
listelenmiştir.

### Kullanılmayan / kaçınılan pinler

| Pin | Neden kullanılmıyor |
|---|---|
| **GPIO0, GPIO3, GPIO45, GPIO46** | **Strapping pinleri** — açılış davranışını belirler. GPIO0/46 boot modu, GPIO3 JTAG kaynağı, GPIO45/46 VDD_SPI gerilimi. Sensör/aktüatör bağlanmaz. |
| **GPIO19, GPIO20** | USB D−/D+ — seri debug/olası firmware güncellemesi için ayrılır |
| **GPIO43, GPIO44** | U0TXD/U0RXD — seri konsol/debug için ayrılır |
| **GPIO26–GPIO32** | Modül içindeki QSPI flash / (varsa) PSRAM tarafından kullanılır, modül pinlerinde yoktur |
| **GPIO35–GPIO37 (modül pin 28–30)** | Datasheet notu: bu pinlerin varsayılan işlevleri **flash'a ayrılmıştır**; kullanılması önerilmez |

> **Neden bunu yazma gereği duyduk:** Strapping pinine yanlışlıkla sensör bağlamak, cihazın
> açılış modunu bozar ve sahada "rastgele çalışmayan modül" olarak görünür — teşhisi zor bir hata
> türüdür. Bu yüzden yasak pinler açıkça listelenmiştir.

---

## 3.2 Sensör bağlantıları

| Bileşen | Arayüz | Adres / yapılandırma | Ortak hat |
|---|---|---|---|
| **MLX90640** (termal dizi) | I²C | **Adres 0x33** (datasheet) | SDA=GPIO8, SCL=GPIO9 |
| **SHT31** (sıcaklık+nem) | I²C | **Adres 0x44** (ADDR pini GND'ye; epsile 0x45) | SDA=GPIO8, SCL=GPIO9 |
| **Enerji analizörü** (varsa) | RS-485 | Modbus slave adresi + seri parametreler analizörden ayarlanır | A/B hattı → UART1 |
| **TVOC-2** (varsa) | RS-485 | Modbus slave adresi ayarlanır | Aynı A/B hattı → UART1 |
| **Split-core CT ×4** (analizör yoksa) | Analog | Burden direnci + yarımsal önyargı | ADC1_CH3…CH6 |

**Adres çakışması yok:** 0x33 (termal) ve 0x44 (SHT31) farklı adreslerdir, bu nedenle tek I²C
hattı ikisini taşıyabilir.

### I²C hattı gerekçesi

I²C, kısa mesafeli (kart üzeri) sensör bağlantısı için uygundur ve her iki sensör de I²C'dir.
**Tek hat kullanılmasının sebebi:** kablo ve pin tasarrufu; modül içindeki mesafe birkaç santim
olduğundan I²C'nin mesafe sınırı sorun değildir.

**Termal dizi için ayrı dikkat:** MLX90640 ham verisi 768 değerdir ve okuması birkaç ardışık
register transferi gerektirir. I²C hızı bu nedenle **400 kHz (fast mode)** veya üzeri
yapılandırılmalıdır; aksi halde 10–30 sn'lik termal özet çevrimi gecikebilir (§7.2).
Datasheet I²C hızını 1 MHz'e kadar desteklendiğini belirtir.

---

## 3.3 RS-485 / Modbus hattı

```
   Modül (master)                    Panodaki cihazlar (slave)
   ┌──────────────
   │  UART1       │
   │  TX  GPIO17 ────┐
   │  RX  GPIO18 ─┼───┤
   │  DE/RE GPIO21┼─┐ │
   └──────────────┘ │ │
                    │ │   ┌─────────────┐
              ┌─────▼─▼───┤ RS-485      │
              │  transceiver│ A/B  ─────────> Enerji analizörü
              ─────────────┘           │
                                        └────> TVOC-2
```

| Özellik | Değer / karar |
|---|---|
| Protokol | Modbus RTU |
| Fiziksel katman | RS-485, yarıçift yönlü (half-duplex) |
| Yön kontrolü | DE/RE pini (GPIO21) TX sırasında sürülür |
| Hat sonlandırma | Hattın iki ucunda 120 Ω sonlandırma direnci |
| Cihaz adresleri | Analizör ve TVOC-2 farklı Modbus slave adreslerine sahip olmalı |

**Neden RS-485:** Pano içi mesafe birkaç metre ve elektromanyetik gürültü yüksektir (baralar,
anahtarlama). RS-485 diferansiyel sinyalleşme kullandığından bu ortamda güvenilirdir.

**Neden ek sensör yerine okuma:** §7.1 satır 229 — panoda analizör varsa akım için yeni sensör
ve kablo gerekmez. Bu, brief'in "kablo kalabalığı" şikâyetine doğrudan cevaptır.

**Ark kanalı önemli not:** TVOC-2'den **yalnızca trip/diagnostik kaydı okunur.** Modül ark
algılamaz; ilgili register haritası `1SFC...TVOC-2_Modbus_Manual.pdf` dosyasındadır
(trip 100–149, diagnostik 200–225, hata 300+). Bu kanal hiçbir yerde "ark tespiti" olarak
adlandırılmaz (§7.1 satır 230).

---

## 3.4 Besleme bağlantısı

```
   230 V iç ihtiyaç                     Modül kartı
   devresi (ilgili sigorta)             ┌───────────────────┐
        │                               │                   │
        ▼                               │                   │
   ┌──────────────┐   5 V      ┌────────┤ 3V3     ESP32     │
   │ AC/DC modül  ├────────────┤        │                   │
   │ RAC05-05SK/277│  ─┬───────┤        │                   │
   └──────────────┘   │        │  ┌─────┤ Süperkapasitör    │
                      │        │  │     │ (float şarj)      │
                      ────────┼──     │                   │
                      float şarj│        └───────────────────
```

| Hat | Kaynak | Hedef | Not |
|---|---|---|---|
| 230 V AC | Pano iç ihtiyaç devresi | AC/DC modül girişi | Yalnız ilgili yardımcı devrenin sigortası çekilir; abonelere giden elektrik kesilmez (§7.3) |
| 5 V DC | AC/DC modül | Kart rayı / süperkapasitör float şarjı | |
| 3V3 | Kart regülatörü | ESP32, sensörler | |
| Kesinti hattı | Süperkapasitör | ESP32 beslemesi | Yalnız besleme kesildiğinde devreye girer |

**Kaçınılacak bağlantı:** Enerji hasadı (CT'den enerji çekme) **varyanttır**, ana tasarım değildir.
§7.3 satır 279'daki red gerekçeleri: akım yokken modül tamamen susar (tam da izlenmesi gereken
anda cihaz ölür), elde edilen güç birkaç yüz mW, CT ucu açık kalırsa tehlikeli gerilim oluşur,
tasarım yükü yüksektir.

---

## 3.5 Anten bağlantısı

| Öğe | Detay |
|---|---|
| Modül konnektörü | U.FL (ESP32-S3-WROOM-**1U**'nun harici anten konnektörü) |
| Kablo | U.FL → panel tipi SMA pigtail, kısa |
| Anten | Panel montajlı harici anten, panonun dış yüzünde |
| Kablo geçişi | Panonun **mevcut kablo giriş noktası** kullanılır (§7.4 satır 296) |

**Neden dış anten:** Pano metal muhafazadır; iç antenle sinyal dışarı çıkmaz ve bu, "modülden veri
gelmiyor" biçiminde **sessiz bir arıza** olarak görünür — fark edilmesi en zor arıza türüdür.

**Neden U.FL:** Modül seçimi (`1U`) zaten harici konnektör için yapılmıştır; anten kablosu
panonun dışına çıkarılırken modül kartında lehim/konektör karmaşası oluşmaz.

**Montaj notu:** Anten kablosu **menteşe yakınında kıvrım payı bırakılarak** yönlendirilir (§7.5).

---

## 3.6 Genişleme arayüzü (bağlayıcı şart)

§7.1 satır 237 zorunlu kılar: *"modül ek ölçüm kanalları için genişletilebilir arayüz taşır."*

| Ayrılan kaynak | Amaç |
|---|---|
| I²C hattına ek adres alanı | Yeni I²C sensör doğrudan eklenebilir (hattın kendisi zaten var) |
| GPIO10, GPIO11 | Dijital/UART genişleme |
| ADC1_CH9 (GPIO10) | Ek analog kanal |
| Yazılımda ayrılmış ölçüm kanalı | `olcum_tipi` enum'ı yeni değer kabul eder; ölçüm kaydı uzun formatta |

**Ekleme maliyeti neden düşük (§7.1 satır 236):** `olcum_tipi` ve `tip` enum olarak tanımlı,
ölçüm kaydı uzun (dar) formatta tutuluyor ve dedektör arayüzü sabit — bu nedenle yeni bir ölçüm
eklemek **şema değişikliği gerektirmez**. Ekleme maliyeti: üretece bir kanal, bir dedektör,
dokümana bir blok.

**Ertelenen fark katmanı:** PD (kısmi deşarj) — 17 mV/mA, 50 Ω yük, 1–60 MHz (§2.5) — ve
akustik (40 kHz bandı) adaylarından biri seçilecek. İkisi birlikte yapılmıyor: aynı arıza
sınıfına bakıyorlar, öğrenme yükü yüksek ve savunulamayan her kanal tüm sistemin güvenilirliğini
düşürür (§7.1 satır 240).

---

## 3.7 Bağlantı özeti (tek tablo)

| # | Bileşen | Arayüz | Pin(ler) | Yön | Not |
|---|---|---|---|---|---|
| 1 | MLX90640 | I²C | GPIO8 (SDA), GPIO9 (SCL) | Çift yönlü | 0x33, 3.3 V, <23 mA |
| 2 | SHT31 | I²C | GPIO8, GPIO9 (paylaşımlı) | Çift yönlü | 0x44 |
| 3 | CT L1 | ADC | GPIO4 (ADC1_CH3) | Giriş | Burden + önyargı |
| 4 | CT L2 | ADC | GPIO5 (ADC1_CH4) | Giriş | |
| 5 | CT L3 | ADC | GPIO6 (ADC1_CH5) | Giriş | |
| 6 | CT nötr | ADC | GPIO7 (ADC1_CH6) | Giriş | |
| 7 | RS-485 transceiver | UART | GPIO17 (TX), GPIO18 (RX), GPIO21 (DE/RE) | Çift yönlü | Modbus RTU |
| 8 | Genişleme | I²C/UART/ADC | I²C hattı + GPIO10, GPIO11 | — | Ayrılmış, boş |
| 9 | Anten | RF | U.FL konnektör | Çıkış | Panel SMA, dış |
| 10 | Besleme | Güç | 3V3, GND, EN | — | AC/DC + süperkapasitör |

---

## 3.8 Doğrulama listesi (PCB öncesi kontrol)

- [ ] Strapping pinlerinden (GPIO0, 3, 45, 46) hiçbirine sensör/aktüatör bağlanmadı mı?
- [ ] Akım kanallarının tamamı **ADC1**'de mi (Wi-Fi aktifken ADC2 çalışmaz)?
- [ ] I²C adresleri çakışıyor mu (0x33 vs 0x44 — çakışma yok)?
- [ ] I²C hattında pull-up dirençleri var mı (tipik 4,7 kΩ)?
- [ ] RS-485 hattında 120 Ω sonlandırma var mı?
- [ ] Anten kablosu için menteşe yakınında kıvrım payı bırakıldı mı?
- [ ] Genişleme pinleri (GPIO10, GPIO11) boş bırakıldı mı ve dokümanda belirtildi mi?
- [ ] Süperkapasitör **float** şarj devresine bağlı mı (ana kaynak değil)?
- [ ] Güçlü mıknatıs akım trafolarının yakınında mı (§7.5 satır 337 uyarısı)?