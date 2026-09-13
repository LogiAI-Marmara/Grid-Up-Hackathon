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
| 4 | **AC/DC güç modülü** | `RECOM RAC05-05SK/277` | 1 | 10,25 | 499 | 230 V → 5 V, izoleli | −40…+90 °C | Link Electronics |
| 5 | **Yedek depo (süperkapasitör)** | Eaton PM/HV serisi *(seçim açık — bkz. 2.5)* | 1 | ~5,00 | ~243 | Kesintide birkaç dk; "besleme kaybı" alarmı | −40 °C (derating'li) | Eaton |
| 6 | **Anten + kablo** | Panel tipi harici anten + U.FL pigtail | 1 | ~5,00 | ~243 | Panodan dışarı sinyal | — | DigiKey / Data Alliance |
| 7 | **RS-485 alıcı-verici** | Yarıçift yönlü transceiver (örn. MAX485 sınıfı) | 1 | ~1,50 | ~73 | Modbus hattı fiziksel katmanı | Endüstriyel sınıf seçilecek | — |
| | | | | **60,53** | **2.945** | **Aktif bileşen ara toplamı** | | |

## 2.2 Destek kalemleri

| # | Kalem | Adet | Birim $ | Birim ₺ | Not |
|---|---|---|---|---|---|
| 8 | PCB (küçük, 2 katman) | 1 | ~3,00 | ~146 | Kutu içi ölçülere göre |
| 9 | Kutu (IP54) | 1 | ~8,00 | ~389 | Ölçü revizyonu bekliyor — bkz. [4. doküman](04-mekanik-yerlesim.md) |
| 10 | Kızılötesi açıklık / pencere | 1 | ~3,00 | ~146 | Malzeme kararı [4. doküman](04-mekanik-yerlesim.md) |
| 11 | Klemens, kablo, konnektör | — | ~5,00 | ~243 | |
| 12 | Regülatör + pasif bileşenler | — | ~3,00 | ~146 | |
| | | | **22,00** | **1.071** | **Destek ara toplamı** |

**Fiyat güvenilirliği:** 1–4 ve 7 numaralı kalemler **distribütör liste fiyatıdır** (doğrulanmış).
5, 6 ve 8–12 numaralı kalemler **tahmindir** (~ işaretiyle gösterilmiştir) ve BOM kesinleştirilirken
tedarik araştırması gerektirir.

---

## 2.3 Modül birim maliyeti

| Senaryo | Birim maliyet | Not |
|---|---|---|
| **Panoda analizör VARSA** (akım Modbus'tan okunur) | **$82,53 ≈ ₺4.016** | CT gerekmez — **hedef senaryo** |
| Panoda analizör YOKSA (4× split-core CT) | $92,13 ≈ ₺4.483 | CT tanesi ~$2,40 (OEM liste fiyatı, düşük güvenilirlik) |

**Ölçek karşılığı (bilgi amaçlı):**

| Ölçek | Tutar |
|---|---|
| Demo (9 modül) | ~$743 ≈ ₺36.100 |
| 100 modül (T5 senaryosu) | ~$8.253 ≈ ₺401.600 |

> **Dikkat — tam sistem maliyeti bundan fazladır.** Bu tablo yalnız **modül** maliyetidir. Saha
> gateway'i, on-prem sunucu ve yazılım altyapısı ayrıca değerlendirilir (İZ C kapsamı). 100 modül
> birden fazla sahaya dağıldığı için saha başına en az bir gateway gerekir (§7.4 satır 306).

---

## 2.4 Maliyet ve sağlanan fayda (kriter 8'in karşılığı)

### Baskın kalem ve neden savunulabilir

**Termal sensör, aktif bileşen maliyetinin %47'si, toplam modül maliyetinin %35'idir.**
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

## 2.5 ⚠️ Açık kalem — yedek depo bileşen seçimi

Bu kalem **doküman içinde karara bağlanacaktır**; karar kaydı seçimi izime bırakmıştır (§7.3 satır 268:
*"süperkapasitör **veya** küçük hücre"*). Seçilen yöntem **süperkapasitördür**; bileşen seçiminde
şu sürtünme vardır:

| Aday | Sıcaklık aralığı | Sorun |
|---|---|---|
| Panasonic EECF5R5H105 (1 F / 5,5 V) | **−25…+85 °C** | −40 °C şartını karşılamıyor |
| Panasonic NF / EEC-S5R5 (1–1,5 F) | −25…+70 °C | Aynı |
| Kamcap SE serisi | −25…+70 °C | Aynı |
| **Eaton PM serisi** | −40…+60 °C; genişletilmiş **−40…+85 °C** | +85 °C'de gerilim **3,9 V'a derate** |
| **Eaton HV serisi** | −40…+65 °C; genişletilmiş −40…+85 °C | 2,7 V anma; +85 °C'de **2,3 V'a derate** |

**Gerçek durum:** *"5,5 V + −40…+85 °C"* kombinasyonu tek parçada bulunamamıştır. −40 °C'ye inen
seriler +85 °C'de gerilim derating ister. **Dokümana dürüstçe yazılacak yaklaşım:**

1. **Amaç enerji sağlamak değil:** kesinti anında birkaç dakika yaşayıp *"besleme kaybı"* alarmını
   gönderebilmek (§7.3 satır 269). Bu, gereken enerjiyi **çok küçük** tutar.
2. **Ömür hesabı sürekli çalışma üzerinden YAPILMAZ** — *"yılda kaç kesinti × birkaç dakika"*
   üzerinden yapılır. Float durumda bekleyen depo, panonun bakım periyodundan uzun ömür verir
   (§7.3 satır 282).
3. **Alternatif karşılaştırma olarak korunur:** karşılaştırma tablosu yukarıdaki gibi dokümanda
   kalır; tek seçenek savunmak yerine gerekçeli sunum yapılır (§7.3 satır 284'teki ilkeyle aynı).

**Kod tarafı etkisi:** Yok. `modul_durum.besleme` alanı `sebeke` | `yedek` değerlerini taşır; hangi
depo teknolojisinin kullanıldığı sözleşmeye yansımaz.

---

## 2.6 ⚠️ Tespit edilen kısıtlar (dokümana gerekçe olarak girecek)

| # | Kısıt | Sonuç |
|---|---|---|
| 1 | **MCU'nun PSRAM'li varyantı −40…+65 °C** — PSRAM'siz varyant −40…+85 °C | −40…+85 °C şartı için **PSRAM'siz N8 zorunlu**. Kısıt bedava: 768 değerlik kare ~3 KB, PSRAM gereksiz |
| 2 | **Standart 230 V AC/DC modüller −25 °C'de başlıyor** (RECOM RAC02, Mornsun LD03, Hi-Link HLK-PM01) | −40 °C için **277 VAC serisi** (RAC05-K/277, −40…+90 °C) seçildi. Gerekçe dokümanda yazılır |
| 3 | **"5,5 V + −40…+85 °C" süperkapasitör yok** | Bkz. 2.5 — derating veya alternatif |
| 4 | **Termal sensör −40…+85 °C hedef sıcaklık −40…+300 °C** | ✓ Şartı karşılıyor |
| 5 | **Tedarik süresi:** MLX90640 Mouser'da *non-stocked*, **12–16 hafta** | Prototip üretimi planlanırsa erken sipariş gerekir. **Hackathon'u etkilemez** (fiziksel donanım üretilmiyor) |

---

## 2.7 Bileşen seçiminin gerekçeleri (özet)

| Bileşen | Neden bu | Reddedilen alternatif |
|---|---|---|
| **MLX90640 (110°×75°)** | Kapsama hesabı §7.1'deki 114×61 cm değerini birebir veriyor; 32×24 = nokta başına ~3,6×2,5 cm (klemens ölçeği); −40…+85 °C | Dar açılı 55° varyant: 40 cm'de ~41×28 cm görür, klemens sırasını kapsamaz |
| **ESP32-S3-WROOM-1U-N8** | Harici anten konnektörü (`1U`) + −40…+85 °C (`N8`, PSRAM'siz); Wi-Fi/BLE dahili; I²C/UART/ADC mevcut | PSRAM'li varyant: −40…+65 °C'de kalır. PCB antenli varyant: metal panoda çalışmaz |
| **SHT31** | −40…+125 °C (ihtiyacın üzerinde), ±0,2 °C, I²C | — |
| **RECOM RAC05-05SK/277** | −40…+90 °C şartını karşılayan tek makul modül; 4 kVAC izolasyon; encapsulated | Standart 230 V modüller −25 °C'de başlar |
| **Süperkapasitör** | Float şarjlı bekler, döngü yükü yok, bakım yükü ~0 | **Ana kaynak olarak pil:** reddedildi — bakım gerektirir, termal dizi tüketimi pil ömrünü aylara indirir (§7.3 satır 280) |
| **Analizör okuma (varsa)** | Panoya yeni sensör/kablo eklemez — brief'in kablo kalabalığı şikâyetine cevap | Split-core CT: analizör yoksa kullanılır, pense tipi olduğu için kesintisiz takılır |
| **TVOC-2 okuma** | Ark algılama SIL-2 sertifikasyonu gerektirir; ark erken uyarıya uygun değil | Kendi ark dedektörümüzü yapmak: sertifikasyon + milisaniye ölçeği nedeniyle mümkün değil |

---

## 2.8 Sözleşmeye bağlılık kontrolü

- [ ] Tüm bileşenler −40…+85 °C endüstriyel sınıfta mı (istisnalar gerekçeli mi)? → 2.5'te bir istisna var, gerekçeli
- [ ] Ölçüm tipleri `olcum_tipi` enum'ıyla uyumlu mu? → [1. doküman §1.4](01-blok-sema.md)
- [ ] `modul_durum.besleme` alanı `sebeke`/`yedek` değerlerini üretebiliyor mu? → Evet (süperkapasitör)
- [ ] Genişleme payı hem donanımda hem BOM'da mı? → Ayrılmış pinler var, ek parça gerekmiyor
- [ ] Anten panodan dışarı çıkabiliyor mu? → Evet, mevcut kablo girişi + U.FL pigtail