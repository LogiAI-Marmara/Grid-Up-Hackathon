# 2. Bileşen Listesi (BOM) ve Modül Birim Maliyeti

**Teslimat karşılığı:** T1, T2 · **Değerlendirme kriteri 8** ("maliyet ve sağlanan fayda")
**Dayandığı kararlar:** §7.5 (bileşen sınıfı) · §7.1 (ölçüm kümesi)
**Bağlayıcı şart:** Bileşenler **endüstriyel sıcaklık sınıfı −40…+85 °C** (§7.5 satır 318)

> **Bu bir satın alma listesi DEĞİLDİR.** Hackathon kapsamında fiziksel donanım üretilmez ve
> satın alınmaz (§1.4). Bu tablo, *"bu iş hangi parçalarla yapılır, neden bunlar, ne kadar tutar,
> karşılığında ne kazanılır"* sorusunun cevabıdır. Distribütör adları yalnızca **fiyat ve teknik
> veri kaynağı** olarak geçer.

**Kur:** 1 USD = 48,66 TL (13.09.2026 serbest piyasa satış kuru — doğrulanmış)
**Fiyat tarihi:** 2026-09-14 · Fiyatlar **1 adet** (prototip) içindir.

---

## 2.1 Ana bileşenler

| # | Bileşen | Parça kodu | Adet | Birim $ | Birim ₺ | İşlevi | Sıcaklık sınıfı | Kaynak |
|---|---|---|---|---|---|---|---|---|
| 1 | **Termal dizi** | `MLX90640ESF-BAA-000-TU` | 1 | 28,62 | 1.393 | 32×24 nokta sıcaklık; nokta bazında erken tespit | −40…+85 °C | Mouser |
| 2 | **Mikrodenetleyici + radyo** | `ESP32-S3-WROOM-1U-N8` | 1 | 5,66 | 275 | Okuma, özet, eşik mantığı, Wi-Fi/BLE, harici anten | −40…+85 °C | DigiKey |
| 3 | **Sıcaklık + nem** | `SHT31-DIS-B2.5KS` | 1 | 4,50 | 219 | Referans çizgisi + yoğuşma riski | −40…+125 °C | DigiKey |
| 4 | **AC/DC güç modülü** | `RECOM RAC05-05SK/277` | 1 | 10,25 | 499 | 230 V → 5 V, izoleli | −40…+90 °C *(5 V tam yükte +75 °C; +90 °C derating ile — yükümüz %15–40, sınır içi)* | Link Electronics |
| 5a | **Yedek depo — süperkapasitör** | `Eaton HV1030-2R7106-R` (10 F / 2,7 V) **×2 seri** | 2 | ~2,40 | ~117 | 5 F / 5,4 V (4,6 V derate) yedek depo; kesintide birkaç dk | −40…+65 °C; **−40…+85 °C** (2,3 V/hücre derate) | DigiKey / Mouser |
| 5b | **Yedek depo — boost çevirici** | `TPS61099` (WSON-6, 0,7–5,5 V giriş → 4,6 V çıkış) | 1 | ~3,48 | ~169 | Süperkapı 1 V'a kadar sömürür; 4,6 V → D2 → +5 V rayı → LDO. Bobin: **2,2 µH** (datasheet §7.3: L 0,7/2,2/2,86 µH) | −40…+125 °C (TJ) | DigiKey |
| 6 | **Anten + kablo** | Panel tipi harici anten + U.FL pigtail | 1 | ~5,00 | ~243 | Panodan dışarı sinyal | — | DigiKey / Data Alliance |
| 7 | **RS-485 alıcı-verici** | Yarıçift yönlü 3,3 V transceiver (MAX3485 sınıfı) | 1 | ~1,50 | ~73 | Modbus hattı fiziksel katmanı | Endüstriyel sınıf seçilecek | — |
| | | | | **63,81** | **3.105** | **Aktif bileşen ara toplamı** | | |

## 2.2 Destek kalemleri

| # | Kalem | Adet | Birim $ | Birim ₺ | Not |
|---|---|---|---|---|---|
| 8 | PCB (110 × 70 mm, 2 katman) | 1 | ~3,00 | ~146 | Kart yerleşimi: [02-pcb-yerlesimi.svg](02-pcb-yerlesimi.svg) (bkz. 2.2a) |
| 9 | Kutu (IP54, 120 × 80 × 50 mm) | 1 | ~8,00 | ~389 | Nihai ölçü — bkz. [4. doküman](04-mekanik-yerlesim.md) |
| 10 | Kızılötesi açıklık / pencere | 1 | ~3,00 | ~146 | Malzeme kararı [4. doküman](04-mekanik-yerlesim.md) |
| 11 | Klemens, kablo, konnektör | — | ~5,00 | ~243 | |
| 12 | Regülatör + pasif bileşenler | — | ~3,00 | ~146 | |
| | | | **22,00** | **1.071** | **Destek ara toplamı** |

**Fiyat güvenilirliği:** 1–4 ve 7 numaralı kalemler **distribütör liste fiyatıdır** (doğrulanmış).
5, 6 ve 8–12 numaralı kalemler **tahmindir** (~ işaretiyle gösterilmiştir) ve BOM kesinleştirilirken
tedarik araştırması gerektirir.

---

### 2.2a Kart yerleşimi (T2 "PCB/kart yapısı")

![PCB yerleşimi — 110 × 70 mm, ön yüzden bakış](02-pcb-yerlesimi.svg)

*(Fusion 360 modeli `GridUp-PCB.f3d`'den projeksiyon, 1 mm = 8 birim. Ön yüz kutu penceresine bakar: MLX90640, SHT31, LED ve pasifler;
arka yüzde ESP32, RAC05, süperkapasitör (2 × Ø10,5 × 31,5 mm maks. zarf, yatık), boost çevirici, klemensler
(230 V giriş klemensi **3 kutup L/N/PE, 5,08 mm adım → 15,24 mm**, X 84–99,25). 230 V birincil bölge sağ şeritte, ≥ 6 mm creepage
ve yarıkla ayrılmış. Kart kutu içinde (5, 5) mm ofsetlidir. **Koordinat konvansiyonu: model (kutu) koordinatı esas alınır** —
[04-kutu-krokisi.svg](04-kutu-krokisi.svg) ile aynı; SVG çizimleri `y` aşağı olduğu için görüntüde ters görünür. Örnek: MLX90640
kutu koordinatı (55, 37,5), IR pencere (60, 42,5). Hatlar
[03-baglanti-semasi.svg](03-baglanti-semasi.svg) ile aynıdır.)*

---

## 2.3 Modül birim maliyeti

| Senaryo | Birim maliyet | Not |
|---|---|---|
| **Panoda analizör VARSA** (akım Modbus'tan okunur) | **$85,81 ≈ ₺4.175** | CT gerekmez — **hedef senaryo** |
| Panoda analizör YOKSA (4× split-core CT) | $95,41 ≈ ₺4.642 | CT tanesi ~$2,40 (OEM liste fiyatı, düşük güvenilirlik) |

**Ölçek karşılığı (bilgi amaçlı):**

| Ölçek | Tutar |
|---|---|
| Demo (9 modül) | ~$772 ≈ ₺37.575 |
| 100 modül (T5 senaryosu) | ~$8.581 ≈ ₺417.500 |

> **Dikkat — tam sistem maliyeti bundan fazladır.** Bu tablo yalnız **modül** maliyetidir. Saha
> gateway'i, on-prem sunucu ve yazılım altyapısı ayrıca değerlendirilir (İZ C kapsamı). 100 modül
> birden fazla sahaya dağıldığı için saha başına en az bir gateway gerekir (§7.4 satır 306).

---

## 2.4 Maliyet ve sağlanan fayda (kriter 8'in karşılığı)

### Baskın kalem ve neden savunulabilir

**Termal sensör, aktif bileşen maliyetinin %45'i, toplam modül maliyetinin %33'üdür.**
Bu, "tek pahalı parça" eleştirisinin hedefidir — ve cevabı şudur:

| Yaklaşım | Maliyet | Sorun |
|---|---|---|
| **Termal dizi (seçilen)** | 1 sensör, $28,62 | — |
| Nokta sıcaklık sensörleriyle aynı kapsama | Her klemense bir sensör | Onlarca klemens × sensör + her birine kablo → **brief'in "kablo kalabalığı kaotik hale gelir" şikâyeti** (§7.1 satır 229) |
| Ölçüm yok, sadece akım | ~$0 | **Arızanın yerini söyleyemez** — *"akım arttı"* der ama *"hangi klemens"* diyemez |

**Kritik içgörü:** Projenin en yaygın arıza nedeni olan gevşek klemens, **akım sabitken** tek noktada
ısınma olarak kendini gösterir (§7.6 senaryo 1). Akım ölçümü bunu **görmez**. Termal dizi, bu
senaryoyu yakalayan tek ölçümdür. Yani $28,62'lik kalem, projenin **ana iddiasının maliyetidir**;
onu çıkarmak sistemi "akım izleme"ye indirger ve ayırt edici değeri ortadan kaldırır.

### Karşılığında ne kazanılıyor

| Kazanılan | Dayanak |
|---|---|
| Nokta bazında tespit (hangi klemens) | §7.1 satır 227 |
| Akım-sıcaklık korelasyonu: *akım artmadan sıcaklık artıyorsa bağlantı direnci artıyor* | §7.1 satır 228 — projenin en savunulabilir teknik iddiası |
| Kanıt niteliğinde tam kare (operatöre "görsel" kanıt) | §7.4 satır 298 |
| Genişleme payı sayesinde sonradan PD/akustik eklenebilir | §7.1 satır 237 |

### Analizör senaryosunun maliyet etkisi

Panoda **zaten analizör varsa** ($10 tasarruf ve 4 CT bağlantısı ortadan kalkar):

- Akım için **yeni sensör gerekmez** (§7.1 satır 229)
- Panoya **hiçbir yeni kablo** eklenmez — brief'in şikâyetine doğrudan cevap
- Modül kurulumu sadeleşir, montaj süresi kısalır

**Tasarım kararı:** Her iki senaryo da desteklenir; analizör varlığı sahaya göre değişebilir.
Bu esneklik **ek maliyet getirmez** çünkü yazılım aynı ölçüm tipini (`akim_l1`…) farklı kaynaktan
doldurur.

---

## 2.5 Yedek depo bileşen seçimi — **karara bağlandı**

Karar kaydı §7.3 satır 268 seçimi izime bırakmıştır (*"süperkapasitör **veya** küçük hücre"*).
**Seçim: süperkapasitör — Eaton HV serisi, 2 × 10 F seri (5 F / 5,4 V) + boost çevirici.**

### Aday karşılaştırması

| Aday | Sıcaklık aralığı | Sonuç |
|---|---|---|
| Panasonic EECF5R5H105 (1 F / 5,5 V) | **−25…+85 °C** | ✗ −40 °C şartını karşılamıyor |
| Panasonic NF / EEC-S5R5 (1–1,5 F) | −25…+70 °C | ✗ Aynı |
| Kamcap SE serisi | −25…+70 °C | ✗ Aynı |
| Eaton PM serisi (5,0 V / 1 F modül) | −40…+60 °C; genişletilmiş **−40…+85 °C** | △ Ama enerji yetersiz (aşağıya bak) |
| **Eaton HV serisi (2,7 V / 10 F hücre)** | −40…+65 °C; genişletilmiş **−40…+85 °C** | ✓ **Seçildi** |

**Gerçek durum:** *"5,5 V + −40…+85 °C"* kombinasyonu **tek parçada yoktur** — −40 °C'ye inen seriler
+85 °C'de gerilim derating ister. Bu yüzden seçim **enerji bütçesiyle** yapılmıştır.

### Kararı belirleyen hesap

E = ½C(V₁²−V₂²). Yedek modda (`dusuk_guc`) termal dizi ve radyo birlikte beslenemez; yalnızca
*"besleme kaybı"* paketi gönderilir → ~50 mA @ 3,3 V ≈ 165 mW.

> **Float gerilimi — devredeki gerçek değer.** Süperkap **5 V rayından**, `R_şarj = 22 Ω` üzerinden
> şarj olur ve **gerilim sınırlayıcı yoktur**; bu yüzden float gerilimi raya yaklaşır:
> 5 V − D1 (Schottky) ≈ **4,7 V**. Dolayısıyla **5,4 V (2S anma) ile hesaplanan 70 J devrede
> ulaşılamaz** — gerçekçi üst sınır **≈4,7 V ≈ 52 J ≈ ~5 dk**'dır. Tablonun ikinci satırı
> (+85 °C derate, 4,6 V → 50 J) bu gerçeğe zaten yakındır ve **kararın dayanağı odur**.

| Senaryo | Kullanılabilir enerji | 50 mA'da süre |
|---|---|---|
| ~~HV 2×10 F (5 F / 5,4 V) + boost~~ *(devrede ulaşılmaz — float 4,7 V)* | ~~70 J~~ | ~~~7 dk~~ |
| **HV 2×10 F, 4,7 V float (D1 sonrası ray) + boost** | **≈53 J** | **~5,3 dk** |
| **HV 2×10 F, +85 °C derate (4,6 V) + boost** | **50 J** | **~5 dk** |
| HV 2×10 F + LDO (3,6 V'ta durur) | 23 J *(4,7 V float)* | ~2,3 dk |
| Eaton PM 1 F + LDO | 8 J | ~50 sn |
| **Eaton PM 1 F, +85 °C derate (3,9 V) + LDO** | **1 J** | **~7 sn** ✗ |

**Üç sonuç:**
1. **HV, PM'den ~8,7× fazla enerji verir** — hücre voltajı 2,7 V olduğu için seri bağlandığında
   tüm pencere kullanılır; PM'in 5,4 V'lik modülü 3,6 V LDO dropout'una kadar iner.
2. **Boost şart:** LDO 3,6 V'ta dururken (~30 J, ≈90 sn) çöpe gider; boost süperkapı **1 V'a
   kadar** sömürür → **%74 daha fazla enerji** (4,7 V float'ta 23 J → 53 J).
3. **PM'in derating senaryosu çöker:** +85 °C'de PM 3,9 V'a derate olur, 3,6 V dropout'u kalır →
   pencere **0,3 V** → **~7 saniye.** Alarm paketini bile gönderemez. Bu, kararı tek başına verir.

**Karar kaydı §7.3 uyumu:** *"besleme kesildiğinde birkaç dakika yaşayıp 'besleme kaybı' alarmını
gönderebilmek"* — hedef 3–5 dk ≈ 30–50 J. Gerçek devre koşullarında (4,7 V float) HV + boost
**≈53 J ≈ 5,3 dk**; +85 °C'de **50 J ≈ 5 dk** — **karşılıyor**. PM 1 F (**8 J / 1 J**)
**karşılamıyor**.

**Ömür notu:** Ömür sürekli çalışma üzerinden hesaplanmaz — *"yılda kaç kesinti × birkaç dakika"*
üzerinden hesaplanır. Float durumda bekleyen depo, panonun bakım periyodundan uzun ömür verir
(§7.3 satır 282). Veri sayfası ömrü **1000 saat @ 65 °C** (tam anma geriliminde); bizim kullanım
(float + seyrek deşarj + derate) bunun çok altında.

**Kod tarafı etkisi:** Yok. `modul_durum.besleme` alanı `sebeke` | `yedek` değerlerini taşır; hangi
depo teknolojisinin kullanıldığı sözleşmeye yansımaz.

---

## 2.6 ⚠️ Tespit edilen kısıtlar (dokümana gerekçe olarak girecek)

| # | Kısıt | Sonuç |
|---|---|---|
| 1 | **MCU'nun PSRAM'li varyantı −40…+65 °C** — PSRAM'siz varyant −40…+85 °C | −40…+85 °C şartı için **PSRAM'siz N8 zorunlu**. Kısıt bedava: 768 değerlik kare ~3 KB, PSRAM gereksiz |
| 2 | **Standart 230 V AC/DC modüller −25 °C'de başlıyor** (RECOM RAC02, Mornsun LD03, Hi-Link HLK-PM01) | −40 °C için **277 VAC serisi** (RAC05-K/277, −40…+90 °C — 5 V tam yükte +75 °C, +90 °C derating ile) seçildi. Gerekçe dokümanda yazılır |
| 3 | **"5,5 V + −40…+85 °C" süperkapasitör yok** | Bkz. 2.5 — **HV serisi 2×10 F + boost** seçildi; enerji bütçesiyle gerekçelendi |
| 4 | **Termal sensör −40…+85 °C hedef sıcaklık −40…+300 °C** | ✓ Şartı karşılıyor |
| 5 | **Tedarik süresi:** MLX90640 Mouser'da *non-stocked*, **12–16 hafta** | Prototip üretimi planlanırsa erken sipariş gerekir. **Hackathon'u etkilemez** (fiziksel donanım üretilmiyor) |

---

## 2.7 Bileşen seçiminin gerekçeleri (özet)

| Bileşen | Neden bu | Reddedilen alternatif |
|---|---|---|
| **MLX90640 (110°×75°)** | Gerçek montaj derinliğinde (377 mm plaka / 155,5 mm NH yüzü) kapsama 1077 × 579 ve 444 × 239 mm; 32×24 = nokta başına ~3,4×2,4 cm (plaka) ve 1,4×1,0 cm (NH — klemens adımından küçük, nokta bazında tespit); −40…+85 °C | Dar açılı 55° varyant: 377 mm'de ~39×24 cm görür, klemens sırasını kapsamaz |
| **ESP32-S3-WROOM-1U-N8** | Harici anten konnektörü (`1U`) + −40…+85 °C (`N8`, PSRAM'siz); Wi-Fi/BLE dahili; I²C/UART/ADC mevcut | PSRAM'li varyant: −40…+65 °C'de kalır. PCB antenli varyant: metal panoda çalışmaz |
| **SHT31** | −40…+125 °C (ihtiyacın üzerinde), ±0,2 °C, I²C | — |
| **RECOM RAC05-05SK/277** | −40…+90 °C şartını karşılayan tek makul modül; 4,2 kVAC izolasyon; encapsulated | **5 V çıkışta tam yükte −40…+75 °C**; +90 °C'ye **yalnız derating grafiğiyle** (düşük yükte) çıkılır — bizim yük %15–40, sınır içinde. Standart 230 V modüller −25 °C'de başlar |
| **Süperkapasitör** | Float şarjlı bekler, döngü yükü yok, bakım yükü ~0 | **Ana kaynak olarak pil:** reddedildi — bakım gerektirir, termal dizi tüketimi pil ömrünü aylara indirir (§7.3 satır 280) |
| **Analizör okuma (varsa)** | Panoya yeni sensör/kablo eklemez — brief'in kablo kalabalığı şikâyetine cevap | Split-core CT: analizör yoksa kullanılır, pense tipi olduğu için kesintisiz takılır |
| **TVOC-2 okuma** | Ark algılama SIL-2 sertifikasyonu gerektirir; ark erken uyarıya uygun değil | Kendi ark dedektörümüzü yapmak: sertifikasyon + milisaniye ölçeği nedeniyle mümkün değil |

---

## 2.8 Sözleşmeye bağlılık kontrolü

- [x] Tüm bileşenler −40…+85 °C endüstriyel sınıfta mı (istisnalar gerekçeli mi)? → 2.5'te bir istisna var, gerekçeli
- [x] Ölçüm tipleri `olcum_tipi` enum'ıyla uyumlu mu? → [1. doküman §1.4](01-blok-sema.md)
- [x] `modul_durum.besleme` alanı `sebeke`/`yedek` değerlerini üretebiliyor mu? → Evet (süperkapasitör)
- [x] Genişleme payı hem donanımda hem BOM'da mı? → Ayrılmış pinler var, ek parça gerekmiyor
- [x] Anten panodan dışarı çıkabiliyor mu? → Evet, mevcut kablo girişi + U.FL pigtail