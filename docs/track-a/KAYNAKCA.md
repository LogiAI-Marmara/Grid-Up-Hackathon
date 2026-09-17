# KAYNAKÇA — dış veri kaynakları ve doğrulama durumu

Bu dosya, dokümanlarda geçen **her dış teknik değerin** kaynağını ve o değerin nasıl
doğrulandığını listeler. Amaç: jüri bir sayıyı sorguladığında "bu nereden geldi" sorusunun
tek adımda cevaplanması.

**Doğrulama durumu sütunu:**

| İşaret | Anlamı |
|---|---|
| **OKUNDU** | Kaynak PDF'in kendisinden okundu (metin katmanı veya render); değer birebir |
| **ÖZET** | Yalnız arama sonucu / distribütör sayfası özetinden alındı; kaynak PDF teyit edilmedi |
| **ATIF** | Değer kaynakta adıyla anılıyor ama bu proje kapsamında sayfa bazında teyit edilmedi |
| **SEÇİM** | Kaynak bir *aralık* verir; dokümandaki değer bu aralıktan yapılan mühendislik **seçimidir** |

> **PDF'ler repoda tutulmaz.** Kaynak dosyalar büyük (toplam ~46 MB, en büyüğü 32 MB) ve
> bir kısmı (TEDAŞ şartnamesi) yarışma organizasyonundan geldi — public repoda yeniden
> dağıtımı bu projenin kararı değildir. Aşağıdaki URL'ler ve doküman numaraları aynı
> kanıtı sağlar.

---

## 1. Bileşen veri sayfaları

### 1.1 Süperkapasitör — Eaton HV1030-2R7106-R

| | |
|---|---|
| **Kaynak** | Eaton *HV Supercapacitors — Cylindrical cells*, **Teknik Veri 4376**, Ocak 2020 (May 2016'yı geçersiz kılar) |
| **URL** | `eaton.com/content/dam/eaton/products/electronic-components/resources/data-sheet/eaton-hv-supercapacitors-cylindrical-cells-data-sheet.pdf` |
| **Yer** | "Dimensions (mm)" tablosu, `HV1030-2R7106-R` satırı |
| **Alınan değerler** | `ØD nominal 10,0` · **`ØD maksimum 10,5`** · **`L maksimum 31,5`** · `F ±0,50 5,0` · `Ød 0,60` · kütle 3,2 g |
| **Diğer** | 10 F, 2,7 V anma, ESR 0,034 Ω, sızıntı 23 µA, ömür 1000 h @ +65 °C, −40…+65 °C; **genişletilmiş −40…+85 °C (2,3 V'a lineer derating)** |
| **Durum** | **OKUNDU** — PDF metin katmanından birebir |
| **Kullanıldığı yer** | §2.1 (5a), §2.5, §4.6 |

> Mekanik yerleşimde **maksimum zarf** (Ø10,5 × 31,5) esas alınır; nominal (10,0) değil.
> Bu, hem bu dokümanda hem `model_pcb.py`'de uygulanmıştır.

### 1.2 Süperkapasitör — Eaton PM-5R0V105-R (karşılaştırma, seçilmedi)

| | |
|---|---|
| **Kaynak** | Eaton PM Supercapacitor data sheet + Eaton SKU sayfası `PM-5R0V105-R` |
| **URL** | `eaton.com/de/en-gb/skuPage.PM-5R0V105-R.html` |
| **Alınan değerler** | 1 F / 5,0 V; **16,8 × 8,5 × 21,5 mm** (dikey); −40…+60 °C, genişletilmiş −40…+85 °C |
| **Durum** | **ÖZET** — distribütör/SKU sayfası özetinden; üretici PDF'i sayfa bazında teyit edilmedi |
| **Kullanıldığı yer** | §2.5 (elenme gerekçesi), §4.6 (karşılaştırma notu) |

> Enerji bütçesi hesabıyla elendi: +85 °C'de 3,9 V'a derate + LDO dropout (3,6 V) → pencere
> 0,3 V → **~1 J ≈ 7 sn**. Ayrıntı §2.5.

### 1.3 NH dikey sigortalı yük ayırıcı — Eaton EBV 00

| | |
|---|---|
| **Kaynak** | Eaton EBV serisi NH yük ayırıcı kataloğu, **Pub. 10275**, sayfa 5 (EBV 00) |
| **Alınan değerler** | Bara bağlantı noktasından toplam derinlik **141,5 mm** (alt 5 / 44 / 45, üst 106 / 134 / 141,5) |
| **Durum** | **OKUNDU** — PDF metin katmanı bozuk (`0x13–0x1C → 0–9`, `0x0F → "."` eşlemesiyle çözüldü), değerler kullanıcı okumasıyla çapraz doğrulandı |
| **Kullanıldığı yer** | §4.3, §5 |

### 1.4 Bara mesnet izolatörü yüksekliği — **SEÇİM**

| | |
|---|---|
| **Kaynak** | Socomec *Busbar Supports* kataloğu (SB/SM serisi) + UL polyester standoff (M8/M10) |
| **Alınan değerler** | SB/SM `L` değerleri **33 / 40 / 45 / 50 / 60 / 65 / 70 mm**; UL standoff **40–71 mm** |
| **Dokümandaki değer** | **50 mm** |
| **Durum** | **SEÇİM** — kaynak bir *aralık* verir, şartname mm dayatmaz; 50 mm aralığın ortası olarak seçildi. **Katalog PDF'i teyit edilmedi (ÖZET düzeyinde)** |
| **Kullanıldığı yer** | §4.3 |

> Bu, dokümanın **bilinçli belirsizlik** noktasıdır: şartname (§2.2.10.2) yalnız "mesnet
> izolatörleri" der ve TS EN 60269-1'e atıf yapar; mm vermez. TEDAŞ EK-II/14 çiziminde
> standoff ölçüsü yoktur. Farklı seçim kapsamayı değiştirir — duyarlılık tablosu §4.3'te.

### 1.5 AC/DC güç modülü — RECOM RAC05-05SK/277

| | |
|---|---|
| **Kaynak** | RECOM *RAC05-K/277* serisi veri sayfası, REV. 5/2022 |
| **URL** | `recom-power.com/pdf/Powerline_AC-DC/RAC05-K_277.pdf` |
| **Yer** | "DIMENSION AND PHYSICAL CHARACTERISTICS" |
| **Alınan değerler** | **31,7 × 26,7 × 21,8 mm** (THT/wired), 31,5 g; giriş 85–305 VAC; 5 V / 1000 mA; **izolasyon 4,2 kVAC** (I/P→O/P, 1 dk); **çalışma sıcaklığı −40…+90 °C** — *5 V çıkışta tam yükte −40…+75 °C; +90 °C yalnız derating grafiğiyle (düşük yükte)* |
| **Durum** | **OKUNDU** — PDF metin katmanından birebir |
| **Kullanıldığı yer** | §2.1 (4), §2.6 (2), §4.6, 01 blok şema dipnotu, 05 |

> **Sıcaklık sınıfı — dipnot gerekli:** Veri sayfası "Operating Temperature Range @ natural
> convection, full load" altında **5 V çıkış için −40…+75 °C** verir; tablonun altındaki satır
> "refer to Derating Graph" ile **all others −40…+90 °C** der. Yani +90 °C'ye **tam yükte değil,
> derating eğrisiyle** çıkılır. Modülümüzün çekişi 5 W anma gücünün **~%15–40**'ı olduğundan
> eğride +85…+90 °C bölgesi kullanılabilir → **şartname karşılanır**. Dokümanlarda uç değer
> **dipnotla** yazılır ("+90 °C derating ile"), çıplak "−40…+90 °C" yanıltıcıdır.
> Ayrıca izolasyon **4,2 kVAC** (önce "4 kVAC" yazılmıştı).

### 1.6 Termal dizi — Melexis MLX90640ESF-BAA-000-TU

| | |
|---|---|
| **Kaynak** | Melexis MLX90640 veri sayfası, **REV 12 — 3 Aralık 2019**, doküman 3901090640 |
| **URL** | `melexis.com/-/media/files/documents/datasheets/mlx90640-datasheet-melexis.pdf` |
| **Alınan değerler** | Sipariş kodu §16: **`xxA` → FOV = 110° × 75°**, `xxB` → 55° × 35° — yani **BAA = geniş açılı** (lazer markalama §15.3: `A` = 110°, `B` = 55°); mekanik çizim §15.2 (Şekil 29): **Ø9,30 ±0,15 × 5,70 ±0,30** gövde, bacak 6 ±0,50, pencere Ø2,60; I²C varsayılan **SA = 0x33**; FM+ **1 MHz**'e kadar (EEPROM işlemleri maks. 400 kHz); **NETD 0,1 K RMS @1 Hz**; akım **< 23 mA**; 3,3 V; ortam **−40…+85 °C**, hedef **−40…+300 °C**; yayma katsayısı yazılımda verilir (**§11.2.2.5.4**) |
| **Durum** | **OKUNDU** — PDF metin katmanı + mekanik çizim sayfası (s. 57) görsel olarak okundu. **Not:** bazı ikincil kaynaklar BAA/BAB'ı ters verir; datasheet sipariş kodu tablosu esas alındı |
| **Kullanıldığı yer** | 01 (sensör gerekçesi), 02 §2.1 (1), 03 §3.2, README |

### 1.7 MCU + radyo — Espressif ESP32-S3-WROOM-1U-N8

| | |
|---|---|
| **Kaynak** | Espressif *ESP32-S3-WROOM-1 & WROOM-1U* veri sayfası, **v1.8** |
| **URL** | `documentation.espressif.com/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf` |
| **Alınan değerler** | 18,0 × 19,2 × 3,2 mm; **IO35/IO36/IO37 Octal SPI PSRAM'li varyantlarda (ESP32-S3R8/R16V) PSRAM'e bağlıdır, başka amaçla kullanılamaz**; N8 varyantında PSRAM yoktur → bu pinler serbesttir. Strapping: IO0/IO3/IO45/IO46. U1TXD=IO17, U1RXD=IO18 |
| **Durum** | **OKUNDU** — pin tablosu (§3-1) birebir doğrulandı: IO1 = ADC1_CH0 · IO4/5/6/7 = ADC1_CH3/CH4/CH5/CH6 · IO10 = ADC1_CH9 · IO17 = U1TXD · IO18 = U1RXD · IO35/36/37 = modül pin 28/29/30 (yalnız Octal PSRAM'li R8/R16V'de bağlı) · strapping tablosu (§4-1) GPIO0 / GPIO3 / GPIO45 / GPIO46 · varyant tablosu (Tablo 1-2): 1U-N8 18,0 × 19,2 × 3,2 mm, **−40 ~ 85 °C**; N…R8 / N16R16V **−40 ~ 65 °C** |
| **Kullanıldığı yer** | §2.1 (2), §2.6 (1), 03 §3.1–3.7 |

### 1.8 Sıcaklık + nem — Sensirion SHT31-DIS-B2.5KS

| | |
|---|---|
| **Kaynak** | Sensirion SHT31 veri sayfası |
| **Alınan değerler** | I²C adres **0x44** (ADDR=GND) / **0x45** (ADDR=VDD); **−40…+125 °C**; sıcaklık doğruluğu tipik **±0,2 °C**; DFN **2,5 × 2,5 × 0,9 mm** |
| **Durum** | **ÖZET** — Sensirion PDF'i bu oturumda açılamadı (DNS), değerler üç bağımsız kaynakla (Sensirion doküman sürümü 7 / Aralık 2022 alıntısı, DigiKey HTML datasheet, Adafruit breakout dokümanı) teyit edildi; DFN ölçüsü modeldeki gövdeyle birebir |
| **Kullanıldığı yer** | §2.1 (3), 03 §3.2 |

### 1.9 RS-485 alıcı-verici — MAX3485 sınıfı

| | |
|---|---|
| **Kaynak** | Üretici veri sayfası (sınıf düzeyinde seçim; parça kodu kesinleşmedi) |
| **Alınan değerler** | Yarıçift yönlü, 3,3 V; DI/RO/DE/RE |
| **Durum** | **ATIF** — parça seçimi açık (§2.1 kalem 7) |
| **Kullanıldığı yer** | §2.1 (7), 03 §3.5 |

### 1.10 LDO — Diodes AP7361C-33E

| | |
|---|---|
| **Kaynak** | Diodes *AP7361C* veri sayfası, DS37274 Rev. 5-2 (Ekim 2020) |
| **URL** | `diodes.com/assets/Datasheets/AP7361C.pdf` |
| **Alınan değerler** | 3,3 V / 1 A; **dropout ≈ 0,3 V**; paketler: U-DFN3030-8, SOT89-5, **SOT223**, TO252 (DPAK), SO-8EP; **θJA: U-DFN3030-8 70 / DPAK 95 / SOT223 110 / SO-8EP 100 / SOT89-5 150 °C/W**; **TJ −40…+150 °C**, termal kapanma +150 °C |
| **Durum** | **OKUNDU** (θJA tablosu birebir; dropout seçim gerekçesinde kullanıldı) |
| **Kullanıldığı yer** | 03 şema (U6), §2.4 termal notu, `eda/README.md` |

> **Termal değerlendirme (SOT-223):** θJA = 110 °C/W, termal kapanma +150 °C. Akım bütçesi
> (Wi-Fi tepe ~350 mA + MLX 23 + SHT31 ~2 + RS-485 ~10 ≈ **385 mA**) ve 5 V rayı ≈4,7 V iken
> LDO kaybı **P = (4,7 − 3,3) × 0,385 ≈ 0,54 W** → +85 °C ortamda **TJ ≈ 85 + 110 × 0,54 ≈ 144 °C**,
> yani kapanma sınırına **~6 °C** kalır. **Ortalama akımda güvenlidir**, ancak tepe yükte pay
> dardır.
>
> **Karar: SOT-223 kalır; layout ile telafi.** Datasheet θJA'sı (110 °C/W, Note 9) minimum pad
> ile ölçülmüştür; tab (pin 2, GND) altında **≥ 1 cm² bakır alan + termal via dizisi** ve arka yüz
> GND dolgusuyla gerçek θJA **85–95 °C/W** bandına iner → **TJ ≈ 131–136 °C**, pay 14–19 °C. Tepe
> yük kısa sürelidir (Wi-Fi paket başına ms mertebesi); ortalama ~100 mA'da TJ ≈ 100 °C. 150 °C
> arıza değil koruma eşiğidir. Yedek modda ray 4,3 V ve yük ~50 mA olduğundan kayıp düşer.
> **Paket alternatifleri neden seçilmedi:** TO252 (DPAK, 95 °C/W) PCB'de LDO penceresine (Y 33,5–42,
> 8,5 mm) dik sığmaz — yatay (90°) konumda X 47–76,75 boşluğuna sığar (boost + L X 43,5–46,5'e taşındı), gerekirse `model_pcb.py`'de
> yapılır; U-DFN3030-8 (70 °C/W) ve SO-8EP (100 °C/W) 8 pinlidir → şema/netlist revizyonu gerekir.
> Layout notu: [04-mekanik-yerlesim.md §4.6](04-mekanik-yerlesim.md).

### 1.11 Boost çevirici — TI TPS61099

| | |
|---|---|
| **Kaynak** | Texas Instruments *TPS61099x Synchronous Boost Converter with Ultra-Low Quiescent Current* veri sayfası |
| **URL** | `ti.com/lit/ds/symlink/tps61099.pdf` |
| **Yer** | §7.3 Recommended Operating Conditions |
| **Alınan değerler** | VIN **0,7–5,5 V**; VOUT 1,8–5,5 V; **L (bobin) MIN 0,7 / NOM 2,2 / MAX 2,86 µH**; CIN 1,0/10 µF; COUT 10/20/100 µF; **TJ −40…+125 °C**; WSON-6 |
| **Dokümandaki değer** | Çıkış **4,6 V** (FB bölücü), bobin **2,2 µH** |
| **Durum** | **OKUNDU** (§7.3 tablosu birebir; ilk yazılan 4,7 µH spesifikasyon dışıydı → 2,2 µH'ye düzeltildi) |
| **Kullanıldığı yer** | §2.1 (5b), §2.5, 03 §3.4, `eda/gen_sch.py` (U7 + L1) |

> **Düzeltme kaydı:** İlk taslakta bobin **4,7 µH** yazılmıştı; veri sayfasının §7.3 tablosu
> üst sınırı **2,86 µH** verir, yani 4,7 µH **spesifikasyon dışıdır**. Tipik değer **2,2 µH**'ye
> çekildi (şema `gen_sch.py` + bu künye).

---

## 2. Standartlar ve şartnameler

### 2.1 TEDAŞ-MLZ/2003-06.B — Alçak Gerilim Dağıtım Panoları Teknik Şartnamesi

| | |
|---|---|
| **Sürüm** | Şubat 2003 / Ocak 2006 revize / Haziran 2015 revize |
| **Kaynak** | Yarışma organizasyonu tarafından sağlandı (proje kapsamında dağıtılmadı) |
| **Alınan değerler** | §2.2.10.2–.3: baralar **mesnet izolatörleri** ile taşınır; DSYA baralara **cıvatalanır**, plakaya yatmaz. **EK-I/8 Tablo 8**: 1600 kVA → bara kesiti **2×(100×10) mm²**, bara adımı **185 mm**. EK-II/14: pano teknik çizimi (dış karkas C = 450 mm) |
| **Durum** | **OKUNDU** — şartname metni ve tablolarından birebir (satır 771/781/799/803, 1789–1791) |
| **Kullanıldığı yer** | §2.2a, §4.3, 05 (tamamı) |

### 2.2 TS EN 60269-1 / TS EN 61439-2

| | |
|---|---|
| **Kaynak** | Standart metinleri (satın alınmadı) |
| **Alınan değerler** | Şartnamenin atıf yaptığı standartlar: sigorta sistemleri (60269-1), AG panoların genel kuralları (61439-2) |
| **Durum** | **ATIF** — şartname üzerinden anılıyor; standart metni incelenmedi |
| **Kullanıldığı yer** | §4.3, 05 |

---

## 3. Doğrulanmamış / dikkat edilecek noktalar

| # | Konu | Durum |
|---|---|---|
| 1 | **Socomec izolatör katalogu** | Yalnız arama özetinden (ÖZET); katalog PDF'i açılmadı. §4.3'te **SEÇİM** olarak işaretli — belirsizlik gizlenmiyor |
| 2 | **Eaton PM-5R0V105-R ölçüleri** | Distribütör/SKU özetinden; üretici PDF'i teyit edilmedi. Karar gerekçesi zaten enerji bütçesi (ölçü değil) |
| 3 | **MLX90640 Mouser tedarik süresi** (12–16 hafta) | Distribütör siteden; hackathon fiziksel üretim yapmadığı için etkisiz (§2.6) |
| 4 | **MAX3485 parça kodu** | Sınıf düzeyinde; kesin parça seçimi yapılmadı (§2.1 kalem 7) |
| 5 | **CT (split-core) fiyatı** | OEM liste fiyatı, §2.3'te "düşük güvenilirlik" olarak işaretli |

---

## 4. Yeniden üretilebilirlik

Tüm sayısal doğrulama `temp/kontrol.py` ile yapılır (depo dışı, gitignore'lu):

```bash
python3 temp/kontrol.py
```

Bu script BOM aritmetiğini `02-bom.md`'den **kazıyıp** toplar ve dokümandaki iddiayla
karşılaştırır, iki düzlemli kapsama geometrisini hesaplar, SVG metin taşmalarını ölçer.

Şema/mekanik tarafta: `eda/verify_netlist.py` (103 kontrol) ve `eda/build.py` (KRİTİK: elle
SVG düzenlenmez, `03-baglanti-semasi.svg` bu script'ten üretilir).