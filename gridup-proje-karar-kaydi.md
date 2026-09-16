# Grid Up Hackathon — Proje Karar Kaydı

**Takım:** 3 kişi
**Teslim:** 20 Eylül 2026
**Belge durumu:** Karar aşaması tamamlandı, üretim aşamasına geçiliyor.

---

## 0. Bu belge nedir, nasıl kullanılır

Bu belge projenin **tek referans kaynağıdır**. İçinde şunlar var:

- Yarışmanın ne istediği ve neyin teslim edileceği
- Alan bilgisi (hiç bilmeyen biri için temel kavramlar)
- Alınmış tüm kararlar, gerekçeleriyle ve **reddedilen alternatifleriyle**
- Bileşenler arası sözleşmeler (veri biçimleri, API)
- Üç iş izinin görev listeleri
- Açık kalan konular

**Kimler için:** Takım üyeleri, projeye sonradan katılan biri, veya projeyi anlaması gereken bir yapay zekâ asistanı. Bu belgeyi baştan sona okuyan biri projeyi tam olarak anlamış olur.

**Değişiklik kuralı:** Bu belgedeki kararlar birden fazla kişiyi bağlar. Değişiklik önerisi takım liderine gider; lider onaylarsa belge güncellenir ve üç kişiye birden duyurulur. Bir iz sahibi kendi başına bu belgedeki bir kararı değiştiremez.

---

## 1. Proje özeti

### 1.1 Yarışma

ADM Elektrik ve GDZ Elektrik (elektrik dağıtım şirketleri) tarafından düzenlenen Grid Up Hackathon. Verilen problem konusu: **Pano/Hücre İçi Anomali Erken Uyarı Sistemi**.

Problem gerçek bir saha ihtiyacından çıkmış; belgeler "Hizmete Özel / Restricted" damgalı.

### 1.2 Problem

Orta gerilim hücreleri ve alçak gerilim panolarında meydana gelen arızaların önemli bir bölümü — sıcaklık artışı, nem, aşırı akım, izolasyon zayıflığı, kısmi deşarj — **kritik arıza gerçekleşmeden önce sinyal verir.**

Ancak mevcut yapılarda bu belirtiler birlikte ve sürekli takip edilmiyor. Problem çoğu zaman ekipman arızası, enerji kesintisi veya yangın riski ortaya çıktıktan sonra fark ediliyor.

### 1.3 Amaç

Pano veya hücre içerisinde oluşabilecek olağandışı durumların erken aşamada fark edilmesini ve ilgili ekiplerin kritik bir arıza gerçekleşmeden önce bilgilendirilmesini sağlayacak, **uçtan uca çalışan bir sistem** geliştirmek.

Çözümün yalnızca anomali tespitiyle sınırlı kalmaması; sahada oluşan bir durumun merkezi operasyon ekipleri tarafından nasıl takip edileceğini de ele alması bekleniyor.

### 1.4 Ne inşa ediyoruz (tek paragraf)

Pano içine yerleştirilen küçük bir elektronik modül, sıcaklık/nem/akım/termal görüntü verilerini toplar ve kablosuz olarak saha gateway'ine gönderir. Gateway verileri şirket içi (on-premise) bir sunucuya iletir. Sunucu veriyi saklar, normal davranıştan sapmaları tespit eder, bir izleme arayüzünde gösterir, mevcut SCADA sistemlerine Modbus üzerinden açar ve kritik durumlarda operasyon ekiplerine SMS/WhatsApp ile bildirim gönderir.

**Hackathon kapsamında fiziksel donanım üretilmeyecektir.** Modül tasarım dokümantasyonu olarak sunulur; veri sentetik olarak üretilir; yazılım tarafı tamamen gerçek ve çalışır durumdadır.

---

## 2. Alan bilgisi — temel kavramlar

Bu bölüm, alanı bilmeyen okuyucu için gerekli minimum bağlamı verir.

### 2.1 Elektrik dağıtım zinciri

Santral → yüksek gerilim hatları → şehir → **trafo** → tüketici.

- **OG (Orta Gerilim):** binlerce volt, şehir içi dağıtım gerilimi
- **AG (Alçak Gerilim):** 220 V / 380 V, tüketiciye giden gerilim
- **Trafo:** ikisi arasındaki dönüştürücü. Sokaktaki gri kabinler veya bina altındaki trafo odaları.
- **OG hücre:** trafonun giriş tarafındaki anahtarlama/koruma dolabı
- **AG pano:** trafonun çıkışındaki dağıtım dolabı. Elektriğin 5-7 ayrı sokağa/binaya dağıtıldığı yer.

### 2.2 Hedef ekipman: 1600 kVA AG Pano

Projede referans alınan pano. TEDAŞ-MLZ/2003-06.B şartnamesine tabi.

| Özellik | Değer |
|---|---|
| Boyut | 1600 mm (en) × 1500 mm (boy) × 450 mm (derinlik) |
| Ana bara | 2 × (100 × 10 mm²) kalaylı elektrolitik bakır |
| Akım trafosu | 2500 / 5 |
| Besleme çıkışı | 5 + 2 yedek |
| İç ihtiyaç devreleri | T.M. iç ihtiyaç 20 A, iç ihtiyaç 6 A, ölçü 2 A (gG sigorta) |

**İçinde ne var:** kalın bakır baralar, onlarca sigorta ve klemens, ve çok sayıda kablo. Brief'in "aşırı kablo yığını ve kalabalığı" dediği durum budur.

**Not:** Şartname panoda modem kullanılabileceğini belirtiyor ve teknik çizimde "Modem" kutusu görünüyor — yani panoda hâlihazırda iç ihtiyaç devresinden beslenen bir haberleşme cihazı bulunabiliyor.

### 2.3 Çalışma koşulları (TEDAŞ şartnamesi, Tablo 1)

| | Bina içi | Bina dışı |
|---|---|---|
| Ortam sıcaklığı (en çok) | 40 °C | 40 °C |
| Ortam sıcaklığı (en az) | −5 °C | −25 °C |
| 24 saat ortalaması | 35 °C | 35 °C |
| Bağıl nem | +40 °C'de %50, +20 °C'de %90 | +25 °C'de %100 |
| Kirlilik derecesi | Düzey II | Düzey III |
| Koruma sınıfı | IP 2X | IP 54 |
| Yer sarsıntısı | 0,5g yatay / 0,4g düşey | |

Ayrıca şartnamede ayrı bir "Kısa Devre Dayanımı" bölümü vardır: kısa devre anında baralar arasında güçlü elektromanyetik kuvvet oluşur ve pano fiziksel olarak sarsılır.

### 2.4 Arıza mekanizmaları

| Arıza | Nasıl gelişir | Zaman ölçeği |
|---|---|---|
| **Gevşek klemens** | Vida gevşer → temas yüzeyi küçülür → direnç artar → o nokta ısınır → erir/tutuşur | Günler–haftalar |
| **Nem / yoğuşma** | Rutubet → yalıtım zayıflar → kaçak akım | Günler–aylar |
| **Aşırı yük** | Akım tasarım sınırını zorlar → genel ısınma | Saatler–günler |
| **Kısmi deşarj (PD)** | Yalıtım içindeki mikro boşluklarda minik kıvılcımlar → yalıtımı aşındırır → delinme | Aylar–yıllar |
| **Ark flaş** | İki iletken arası havada dev kıvılcım. Ölümcül, yangın çıkarır. | Milisaniye |

Ark flaş **önceden tahmin edilemez**; anında algılanıp elektriğin kesilmesi gerekir (ABB TVOC-2 gibi hazır ürünlerin işi). Diğerleri erken uyarıya uygundur.

### 2.5 Sensör kavramları

- **Akım trafosu (CT):** Kablonun etrafına geçen halka. İçinden geçen akımın oluşturduğu manyetik alan halkada küçük bir akım indükler. Kabloya dokunmadan ölçüm yapılır. Üzerinde bir oran yazar (örn. 600/0,1 A); ölçülen değer çarpanla çarpılarak gerçek akım bulunur. **Split-core / clamp-on** tipi pense gibi açılır, canlı panoya elektrik kesmeden takılabilir.
- **Termal dizi sensörü:** 32×24 = 768 noktadan aynı anda sıcaklık ölçen kızılötesi çip. Fotoğraf değil, sıcaklık değerlerinden oluşan bir matris üretir. Görüş hattı gerektirir.
- **HFCT:** Kısmi deşarj sensörü. Topraklama kablosuna geçirilen halka, yüksek frekanslı gürültüyü dinler (1–60 MHz, 17 mV/mA, 50 Ω yük).
- **Optik ark sensörü (TVOC-2):** Ark parlamasının ışığını görür, 1 ms altında tepki verir, SIL-2 sertifikalı.

### 2.6 Haberleşme kavramları

- **Modbus:** Sanayide 40 yıldır kullanılan basit protokol. Her cihazın numaralanmış "register"ları (kutucukları) vardır; "şu numaralı register'ı ver" dersin, bir sayı döner. Sayı bir çarpanla ölçeklenir.
- **SCADA:** Dağıtım şirketinin merkezindeki büyük izleme sistemi.
- **RTU:** Sahadaki uzak terminal birimi, SCADA'ya veri taşır.
- **On-premise:** Şirketin kendi binasındaki kendi sunucusu. **Public cloud** (AWS, Google vb.) bunun karşıtıdır ve bu projede **yasaktır**.
- **Edge:** Verinin oluştuğu yerde, sahada yapılan işlem.
- **Gateway:** Sahadaki modüllerden veriyi toplayıp merkeze ileten ara cihaz.

---

## 3. Teslimat kalemleri (brief'ten, birebir)

| Kod | Kalem | Özet |
|---|---|---|
| **T1** | Kabin içi fiziksel modül / prototip tasarımı | Saha kullanımına uygun modül tasarlanmalı. Fiziksel sensör/ekipman kullanımı zorunlu değil; modülün konsepti, bileşen seçimi, şeması veya prototip tasarımı sunulmalı. |
| **T2** | Elektronik tasarım dokümantasyonu | PCB/kart yapısı, giriş-çıkış bağlantıları, bağlantı şemaları, temel bileşenler |
| **T3** | Yazılım mimarisi | Mikrodenetleyici kodları, programın çalışma mantığı, akış diyagramı, frontend tasarımları ve kaynak kodları |
| **T4** | Monitoring | Merkezi toplama ve izleme uygulaması. SCADA entegrasyonu (Modbus haritalama), on-premise altyapı, SMS/WhatsApp alarm |
| **T5** | Ölçeklenebilirlik ve kaynak kullanımı | "En az 100 modülden gelen veriyi işleyebilecek şekilde tasarlanması ve gerekli kaynak kullanımının değerlendirilmesi" |
| **T6** | On-premise / özel altyapı | Public Cloud kullanılmamalı |
| **T7** | Alarm ve acil bildirim mekanizması | Kritik durumda SMS/WhatsApp vb. anlık bildirim |

### Sunum ve demoda gösterilmesi beklenenler

- Fiziksel modül **veya** çalışan prototip
- Uçtan uca veri akışı
- Monitoring/SCADA ekranları
- Örnek normal ve anormal çalışma senaryoları
- Alarm oluşması ve bildirim mekanizması
- Sistem mimarisi
- Gerçek saha uygulaması ve ölçeklendirme yaklaşımı

---

## 4. Değerlendirme kriterleri

1. Problemin doğru anlaşılması
2. Anomali ve risk tespit yaklaşımının başarısı
3. Çözümün saha koşullarında uygulanabilirliği
4. Uçtan uca sistem yaklaşımı
5. Mevcut operasyon sistemleriyle entegrasyon kabiliyeti
6. Ölçeklenebilirlik
7. Kullanıcı/operasyon deneyimi
8. Maliyet ve sağlanan fayda
9. Yenilikçilik

**Önemli okuma:** 9 kriterden yalnızca 1'i algoritma. Geri kalanı sistem mühendisliği, uygulanabilirlik ve sunum. Bu, "çok iyi bir model yapalım" stratejisinin yanlış olduğunu söylüyor — **çalışan, gösterilebilir, uçtan uca bir demo** önceliklidir.

---

## 5. Kısıtlar

Brief'ten birebir:

- "Hackathon kapsamında **fiziksel sensör veya endüstriyel ekipman satın alınması** ve gerçek bir pano üzerinde saha kurulumu yapılması **beklenmemektedir**."
- "Gerçek saha verisine veya fiziksel sensörlere erişimin mümkün olmadığı durumlarda sistemin çalışması örnek veya **sentetik veriler üzerinden gösterilebilir**."
- "Çözüm kapsamında **Public Cloud kullanılmamalıdır**."
- "Tüm veri kaynaklarını kullanılması zorunlu değildir. Hangi verilerin problemi çözmek açısından anlamlı olduğuna ve bunların nasıl birlikte değerlendirileceğine takımınız karar vermelidir."
- Gerçek saha sistemlerine bağlantı kurulması beklenmiyor; Modbus haritalama göstermek yeterli.

---

## 6. Verilen materyaller ve durumu

| Dosya | İçerik | Durum |
|---|---|---|
| `Grid Up Hackathon Proje Konusu.pdf` | Asıl brief, 5 sayfa | Ana kaynak |
| `AG PANO MALZEME ŞARTNAMESİ.pdf` | TEDAŞ-MLZ/2003-06.B, AG dağıtım panoları teknik şartnamesi | Saha koşulları, koruma sınıfları, iç ihtiyaç devreleri |
| `1600kVA AG Pano Teknik Özellikleri.pdf` | Donanım listesi (bara, akım trafosu, çıkış sayısı) | Referans |
| `AG Pano Teknik Çizim-1600kVA.pdf` | Pano yerleşim çizimi ve ölçüleri | **Modül yerleşim krokisi için doğrudan kullanılacak** |
| `MPR-53CS_Modbus_Register_Map_EN.pdf` | Enerji analizörü register haritası | Akım/gerilim/güç/THD hazır okunabilir; ayrıca çarpan kullanımı için emsal |
| `1SFC...TVOC-2_Modbus_Manual.pdf` | ABB ark dedektörü Modbus haritası | Trip 100-149, diagnostik 200-225, hata 300+ |
| `tvoc.pdf` | TVOC-2 ürün kataloğu | Ark korumasının çalışma prensibi |
| `DS_HFCT30_eng.pdf`, `DS_HFCT50_eng.pdf` | Kısmi deşarj sensörü datasheet'leri | Referans (kullanılmıyor) |
| `İstenen Veriler.xlsx` | Örnek sensör verisi | **Aşağıya bakınız** |

### Excel dosyasının gerçek durumu

4 sekme var, 3'ü boş:

- **Akım Sensörü** — tek dolu sekme. 152 satır, 15 dakika aralıklı, **sadece L1 fazı**. Sensör 100 mA / 600 A, yani **6000 çarpan** (örn. 53 mA × 6000 = 318 A). Değerler 15–89 mA arasında düzgün rastgele dağılmış: **günlük periyodiklik yok, anomali etiketi yok.** Gerçekçi bir yük profili değil.
- **ARC** — boş. Not: "ABB TVOC-2 markası verilerinden Modbus ile okunarak alınacaktır"
- **PD** — boş. Not: "PD tespiti için HFCT sensörleri"
- **Sıcaklık_Nem** — tamamen boş

**Sonuç:** Bu dosya bir veri seti değil, **veri kanallarının iskeleti**. Gerçekçi sentetik veri üretmek takımın işidir.

---

## 7. Alınan kararlar

Her karar: ne karar verildi, neden, hangi alternatifler neden reddedildi.

---

### 7.1 Ölçüm kümesi

**Karar:** Sistem şu büyüklükleri ölçer:

| Ölçüm | Nasıl | Rolü |
|---|---|---|
| Ortam sıcaklığı | Dijital sensör | Referans çizgisi — kabin içi sıcaklığın anormal olup olmadığı ancak dış ortamla karşılaştırılarak anlaşılır |
| Nem | Dijital sensör | Yoğuşma ve izolasyon riski |
| Yüzey sıcaklığı | **32×24 termal dizi sensörü** | En yaygın arıza nedeni olan gevşek klemensi nokta bazında erken yakalar |
| Akım (L1/L2/L3/nötr) | Split-core CT **veya** panodaki enerji analizöründen Modbus | Yük takibi + sıcaklıkla korelasyon |
| Ark olayları | TVOC-2'den Modbus ile okuma | Olay kaydı (tespit değil) |

**Gerekçeler:**

- **Termal dizi kritik:** Ortam sıcaklığı "kabin ısındı" der, termal dizi "7 numaralı klemens ısındı" der. Erken uyarı iddiasını gerçek kılan ölçüm budur. Brief veri türleri listesinde "Yüzey veya kablo sıcaklığı" ve "Termal görüntü veya benzeri sensör çıktıları" açıkça sayılmıştır.
- **Akım-sıcaklık korelasyonu projenin en savunulabilir teknik iddiasıdır:** *akım artmadığı halde sıcaklık artıyorsa, bağlantı direnci artıyor demektir.* Brief bunu doğrudan istiyor: "Kablolardan geçen akım ile ortam ve yüzey sıcaklık değişimlerinin birlikte değerlendirilmesi".
- **Enerji analizöründen okuma seçeneği:** Panoda analizör varsa akım için yeni sensör ve kablo gerekmez. Bu, brief'in "yeni eklenecek sensörler kablo kalabalığını kaotik hale getirebilir" şikâyetine doğrudan cevaptır.
- **Ark için kendimiz bir şey yapmıyoruz:** Ark algılama güvenlik sertifikası gerektiren bir iştir (TVOC-2 SIL-2 sertifikalı). Sadece hazır cihazın kayıtlarını okuyoruz.

**Kapsama hesabı (termal dizi):** Pano derinliği 450 mm; kapak içine konan sensör hedefe ~40 cm mesafededir. Geniş açılı versiyon bu mesafeden kabaca **114 × 61 cm** görür. Pano 160 × 150 cm olduğundan tek sensör tamamını görmez, ancak en kritik bölge olan **çıkış klemens sırasını** kapsar.

**Ertelenen karar — fark katmanı:** Çekirdek kümenin üzerine "kısmi deşarj (PD)" veya "akustik/ultrasonik" eklenip eklenmeyeceği **ertelenmiştir.**

- **Neden ertelenebilir:** `olcum_tipi` ve `tip` enum olarak tanımlandığı, ölçüm kaydı uzun formatta tutulduğu ve dedektör arayüzü sabitlendiği için yeni bir ölçüm eklemek şema değişikliği gerektirmiyor. Ekleme maliyeti: üretece bir kanal, bir dedektör, dokümana bir blok.
- **Şartı:** Modül dokümanında **genişleme payı** açıkça belirtilecek ("modül ek ölçüm kanalları için genişletilebilir arayüz taşır").
- **PD'nin gerçek maliyeti** hesaplama süresi değil, öğrenme ve inandırıcılıktır: PD verisi rastgele sayı değildir, darbelerin 50 Hz dalga şekline göre belirli fazlarda yoğunlaşması gibi karakteristik bir yapısı vardır. Bilmeden üretilen veri, alanı bilen bir jüri üyesi tarafından anında fark edilir.
- **Akustik**, PD'nin yapılabilir karşılığıdır: 40 kHz bandı, 60 MHz değil; sinyal sezgiseldir; benzer arıza sınıfına bakar. Riski pano içi gürültünün yanlış alarm üretmesidir.
- **İkisi birden neden yapılmıyor:** Teknik olarak çelişmiyorlar. Sebep (a) öğrenme yükü, (b) aynı arıza sınıfına bakmaları — ikincisinin marjinal kazancı düşük, (c) savunulamayan her kanal tüm sistemin güvenilirliğini düşürür.

---

### 7.2 Örnekleme sıklığı

**Karar:**

| Ölçüm | Sıklık |
|---|---|
| Akım | 1–5 sn okunur, 10 sn ortalaması kaydedilir |
| Termal özet | 10–30 sn |
| Termal tam kare | Sadece anomali anında |
| Ortam sıcaklık / nem | 30–60 sn |
| Ark | Olay bazlı, örnekleme yok |

**Gerekçe:** Bu uygulama için tek bir sektör standardı yok. Elimizdeki örnek verinin 15 dakikalık olması **enerji/sayaç okuma** standardından gelir (yük profili), durum izleme standardından değil — kopyalanmamalıdır.

Asıl belirleyici fizik: **olayın kendi zaman sabitinden daha sık örneklemek bilgi kazandırmaz.** Panoda ısı yavaş yayılır; gevşek bir bağlantı dakikalar–saatler içinde ısınır. Akım hızlı değişir, ancak sıcaklıkla korelasyon kurulacaksa akımın da sıcaklığın zaman ölçeğinde değerlendirilmesi gerekir.

Sık örneklemenin maliyeti sensör yıpranması değildir (katı hal sensörlerinde yoktur); veri hacmi ve **gürültüdür** — yumuşatılmazsa yanlış alarm üretir.

---

### 7.3 Besleme

**Karar:**
- **Ana kaynak:** Panonun iç ihtiyaç devresi (230 V)
- **Yedek:** Kısa süreli enerji deposu (süperkapasitör veya küçük hücre)
- **Yedeğin amacı:** Besleme kesildiğinde birkaç dakika yaşayıp **"besleme kaybı" alarmını gönderebilmek.** İzleme sisteminde "veri gelmiyor" ile "cihaz öldü, sebebi şu" arasında büyük fark vardır.

**Gerekçe:** TEDAŞ şartnamesinde panoda üç ayrı yardımcı devre tanımlıdır (T.M. iç ihtiyaç 20 A, iç ihtiyaç 6 A, ölçü 2 A), her birinin kendi sigortası vardır. Ayrıca şartname panoda modem kullanılabileceğini belirtir ve teknik çizimde modem kutusu görünür — **yani iç ihtiyaç devresinden beslenen bir haberleşme cihazı için emsal mevcuttur.**

Kurulumda yalnızca ilgili yardımcı devrenin sigortası çekilir; **abonelere giden elektrik kesilmez.**

**Reddedilen alternatifler:**

| Alternatif | Red gerekçesi |
|---|---|
| **Enerji hasadı** (akım trafosundan enerji çekme) | En zarif çözüm — sıfır kablo, sıfır bakım. Ancak: (1) akım yokken modül tamamen susar, yani hat enerjisiz kaldığında tam da izlenmesi gereken anda cihaz ölür; (2) elde edilen güç birkaç yüz mW seviyesinde, termal sensör + radyo için kısıtlı; (3) CT ucu açık kalırsa tehlikeli gerilim oluşur, koruma devresi gerekir; (4) tasarım yükü yüksek. |
| **Ana kaynak olarak pil** | Bakım gerektirir. Brief açıkça "tak çalıştır bakım gerektirmeyen bir sistem" istiyor. 5000 panoluk bir yaygınlaştırmada pil değişimi savunulamaz. Ayrıca termal dizi taşıyan bir modülün tüketimi pil ömrünü aylara indirir. |

**Not:** "230 V + yedek depo" ile "pil ile çalışma" farklı şeylerdir. Yedek depo sürekli 230 V'tan şarjlı durur, yalnızca kesintide devreye girer, sürekli boşalıp dolmadığı için ömrü panonun bakım periyodundan uzundur. Bakım yükü pratikte sıfırdır.

**Dokümanda ayrıca belirtilecek:** Yardımcı besleme devresi bulunmayan sahalar için enerji hasadı bir **varyant** olarak konumlandırılır. Tek seçenek savunmak yerine alternatifleri gerekçeleriyle sunmak daha güçlüdür.

---

### 7.4 Haberleşme

**Karar — iki kademeli mimari:**

```
Modül  --(kablosuz, birkaç metre)-->  Saha Gateway  --(mevcut altyapı)-->  Merkez
```

- **Panodan çıkış:** Dış anten. Panonun dışına küçük bir anten, kısa kabloyla içerideki modüle bağlanır. Panoda zaten kablo giriş noktaları vardır.
- **Gateway:** Trafo binası içinde, 230 V beslemeli, boyut kısıtı olmayan ara cihaz. **Kendi gateway'imizi öneriyoruz**; mevcut modem/RTU altyapısı varsa alternatif yol olarak dokümante edilir.
- **Veri politikası: Normalde özet, anomali anında tam kare.** Modül termal sensörden 768 değer okur, kartta işler ve normalde sadece özeti gönderir (maksimum sıcaklık, sıcak nokta koordinatı, bölge ortalamaları). Anomali tespit ettiğinde tam kareyi "kanıt görüntüsü" olarak gönderir.

**Gerekçeler:**
- Problem ikiye bölününce küçülüyor: modülün sinyali binadan çıkmak zorunda değil, sadece panodan çıkıp odaya ulaşmak zorunda.
- Özet + olay bazlı tam kare politikası bant genişliğini düşük tutar ve "edge'de işlem yapıyoruz" iddiasının somut karşılığıdır.

**Önemli sonuç:** Bu politika, **modülün anomaliyi kendi başına tanıyabilmesini zorunlu kılar** — yoksa tam kareyi ne zaman göndereceğini bilemez. Dolayısıyla tespit iki katmanlıdır: modülde basit eşik mantığı, merkezde asıl dedektör. Bu ayrıca **merkezden modüle ayar gönderme** ihtiyacını doğurur (eşik değiştirmek için 100 sahayı gezmek mümkün değildir) — bu, T5 ölçeklenebilirlik açısından kazançtır.

**Varsayım:** Saha başına birkaç modül; 100 modül birden fazla sahaya dağılır. Bu varsayım tasarımı değiştirmez, yalnızca T5'teki kaynak hesabına temel oluşturur.

---

### 7.5 Montaj ve kutu

**Kutu:**

| | |
|---|---|
| Boyut | ~10 × 7 × 3,5 cm mertebesi |
| Koruma | IP54 muhafaza (pano zaten IP2X/IP54; modül için toz ve temas koruması) |
| Bileşen sıcaklık aralığı | Endüstriyel, −40…+85 °C |
| Termal sensör konumu | **Kutunun yüzeyinde, dışa bakan yuvada** |

**Bileşen sıcaklığı gerekçesi:** Şartname ortam için −25…+40 °C öngörür, ancak pano içi baradan gelen ısıyla bundan sıcaktır. Ticari sıcaklık aralığı yetersizdir.

**Kritik detay — kızılötesi pencere:** Normal cam veya plastik kızılötesini geçirmez. Termal sensör kutunun içine konup kapağın arkasından baktırılamaz; kutu yüzeyinde kendi yuvasında, dışarı bakar konumda olmalıdır.

**Konum:** Modül klemenslere **dik bakmalıdır.** Yan duvar veya tavan yerleşiminde yüzeye çok eğik açıyla bakılır ve ölçüm bozulur. Geometrik olarak doğru yer kapak içi veya ön çerçevedir.

Kapak içi yerleşimin iki kısıtı: kapak açılınca görüş kaybolur (pratikte sorun değil, kapak açıksa orada bir insan vardır) ve kablo menteşeden geçer (menteşe yakınında kıvrım payı bırakılır).

**Sabitleme — dokümanda yer alacak ifade:**

> Modül, panoya **yeni delik açmadan**, mevcut montaj imkânları kullanılarak sabitlenir (DIN rayı, mevcut cıvata delikleri veya kapak çerçevesi). Mıknatıslı taban konumlandırma ve kadraj ayarı için kullanılır; mekanik tutma her durumda mevcut bir yapı elemanına dayanır.
>
> Gerekçe: pano tip testli bir muhafazadır, gövdeye yeni delik açmak beyan edilen IP sınıfını ve iç ark dayanımını etkileyebilir. Ayrıca canlı pano içinde yerinden çıkabilecek bir cisim kabul edilemez bir risktir; bu nedenle sadece manyetik tutma tek başına yeterli görülmemiştir.

**Neden salt mıknatıs yeterli değil:** (1) Kısa devre anında pano fiziksel olarak sarsılır — tam da sistemin çalışması gereken an; (2) trafo ve baraların sürekli titreşimi yıllar içinde mıknatısla duran nesneyi "yürütür"; (3) panoda çalışan teknisyen çarpabilir. Asıl gerekçe ise tasarıma özeldir: **termal sensörün değeri nişan almasına bağlıdır.** Birkaç santim kayma veya hafif dönme, izlenen klemens sırasını kadraj dışına çıkarır ve sistem **sessizce kör olur** — fark edilmesi en zor arıza türü.

**Tasarım notu:** Güçlü mıknatıs panodaki akım trafolarının yakınına konmamalıdır (manyetik alan ölçümü etkileyebilir). Kapak içi yerleşimde mesafe zaten mevcuttur.

**Pano başına modül sayısı:** 1 modül baz senaryo (kritik bölge: çıkış klemens sırası). Tam pano kapsaması gereken panolarda 2. modül eklenir.

**Montaj prosedürü:**

1. Yardımcı devre sigortası çekilir — **abonelere giden elektrik kesilmez**
2. Pano kapağı açılır
3. Modül konumlandırılır, klemens sırasına hizalanır
4. Besleme kablosu iç ihtiyaç klemensine bağlanır
5. Anten kablosu mevcut kablo giriş noktasından dışarı çıkarılır, anten dışa monte edilir
6. Sigorta takılır, modül gateway'e kaydolur
7. Ekrandan kapsama doğrulanır

**Tek teknisyen, ~15–20 dakika, kesinti yok.**

---

### 7.6 Arıza senaryoları (projenin iddiası)

Bu liste **"neyi erken yakaladığımızı iddia ediyoruz"** sorusunun cevabıdır. Üç izi birden bağlar: İZ A üretir, İZ B tespit eder, İZ C gösterir. **Bir iz sahibi kendi başına senaryo ekleyemez.**

| # | Senaryo | Belirtisi | Neyle yakalanır |
|---|---|---|---|
| 1 | Gevşek klemens | Tek noktada yavaş ısınma, akım sabit | Termal + akım korelasyonu |
| 2 | Aşırı yük ısınması | Akım yüksek, genel sıcaklık artışı | Akım + ortam sıcaklık |
| 3 | Faz dengesizliği | Fazlar arası fark, nötr akımı artışı | Akım |
| 4 | Nem yükselmesi | Nem eşiği aşımı, yoğuşma riski | Nem + sıcaklık |
| 5 | Ark olayı | TVOC-2 trip kaydı | Ark okuma |
| 6 | Sensör arızası | Ölçüm donuyor veya saçmalıyor | `kalite` alanı |
| 7 | Modül sağlığı | Besleme kaybı, sinyal zayıflığı, saat kayması | `modul_durum` |

Son iki madde arıza değil **sistemin kendi sağlığıdır** — "sistemimiz sessizce ölmez" demenin karşılığıdır ve jüri açısından değerlidir.

**Genişletme:** Fark katmanı eklenirse liste bir satır büyür; mimari ve sözleşmeler değişmez, yalnızca `tip` enum'una bir değer ve üretece bir senaryo eklenir. Değişiklik lider kararıdır ve üç kişiye duyurulur.

---

### 7.7 Demo topolojisi

- **Demo senaryosu:** ~3 saha × 2 pano × 1–2 modül ≈ 8–10 modül. Ekranda hem hiyerarşi görünür hem karmaşa olmaz.
- **Yük senaryosu:** 100 modül, sentetik, yalnızca performans ölçümü için.

**Not:** Brief'in T5 maddesi 100 modülü **ekranda göstermeyi değil**, "işleyebilecek şekilde tasarlanmasını ve gerekli kaynak kullanımının değerlendirilmesini" istiyor. İZ B'nin yük testi + kaynak raporu bu maddeyi karşılar. Vakit kalırsa arayüzde de gösterilmesi bonustur.

Bu sayılar sonradan kolayca değiştirilebilir.

---

## 8. Sistem mimarisi

```
┌─────────────────────────── PANO ────────────────────────────┐
│                                                              │
│   Ortam sıc/nem ──┐                                          │
│   Termal dizi ────┼──> MODÜL ──> radyo ──> dış anten         │
│   Akım (CT/Modbus)┘    (MCU)                                 │
│   TVOC-2 (Modbus) ┘     │                                    │
│                          └── 230 V iç ihtiyaç + yedek depo   │
└──────────────────────────────┼───────────────────────────────┘
                               │ kablosuz
                    ┌──────────▼──────────┐
                    │  SAHA GATEWAY       │   (trafo binası içi)
                    └──────────┬──────────┘
                               │
        ══════════════ ON-PREMISE SUNUCU ══════════════
        │                                              │
        │  Toplama servisi ──> PostgreSQL              │
        │                          │                   │
        │                          ├──> Anomali motoru │
        │                          │         │         │
        │                          │         ├──> Alarm servisi ──> SMS/WhatsApp
        │                          │         │                     │
        │                          └─────────┴──> Okuma API'si     │
        │                                            │             │
        │                                    ┌───────┴──────┐      │
        │                                    │  Monitoring  │      │
        │                                    │   arayüzü    │      │
        │                                    └──────────────┘      │
        │                          └──> Modbus TCP sunucusu ──> SCADA
        ════════════════════════════════════════════════
```

---

## 9. Sözleşmeler

Bu beş sözleşme izler arasındaki sınırdır. **Değişimi lidere sorulur.** Repo'da `/sozlesmeler` klasöründe tutulur.

### ① Ölçüm kaydı

```json
{
  "modul_id": "TR041-P01-M1",
  "zaman": "2026-09-14T09:31:20Z",
  "olcum_tipi": "ortam_sicaklik",
  "deger": 34.7,
  "birim": "C",
  "kalite": "iyi"
}
```

**Neden dar/uzun format:** Yeni ölçüm tipi eklemek yeni bir satırdır, şema değişmez. Fark katmanını erteleyebilmenin teknik dayanağı budur.

**Hacim kontrolü:** 100 modül × 6 ölçüm tipi × 10 saniyede bir ≈ 60 satır/sn ≈ 5 milyon satır/gün. Birkaç günlük sentetik veri 15–20 milyon satır eder. PostgreSQL için sıradan bir yüktür.

**İstisna:** Termal tam kare bu tabloya girmez (768 değeri 768 satır yapmak anlamsızdır). Ayrı kare tablosunda, `(modul_id, zaman)` ile anahtarlanmış tek bir JSON/blob olarak saklanır.

**`kalite` alanının işlevi:** Sensör bozulunca değer 0 gelir ve bu "anomali" gibi görünür. Sensör arızasıyla gerçek anomaliyi ayırmanın tek yolu bu alandır.

### ② Modül paketi

Modül tek tek ölçüm değil, paket gönderir:

```json
{
  "modul_id": "TR041-P01-M1",
  "zaman": "2026-09-14T09:31:20Z",
  "olcumler": [ /* ① formatında kayıtlar */ ],
  "termal_ozet": {
    "maks": 71.2,
    "maks_konum": [14, 9],
    "bolge_ort": [42.1, 44.8, 51.3, 43.0]
  },
  "termal_kare": null,
  "modul_durum": {
    "besleme": "sebeke",
    "sinyal": -72,
    "yazilim_surumu": "1.0.3"
  }
}
```

- `termal_kare`: normalde `null`, anomali anında 768 elemanlı dizi
- `modul_durum.besleme`: `"sebeke"` | `"yedek"` — yedek depo kararının karşılığı

### ③ Anomali çıktısı

```json
{
  "id": "an_00412",
  "modul_id": "TR041-P01-M1",
  "zaman": "2026-09-14T09:31:20Z",
  "skor": 0.87,
  "seviye": "uyari",
  "tip": "sicak_nokta",
  "gerekce": "L2 çıkış klemensi 34 dk içinde +18 °C yükseldi, akım sabit kaldı.",
  "kanit": { "kare_id": "kr_0091", "piksel": [14, 9] },
  "durum": "acik"
}
```

**`gerekce` alanı kritiktir:** Operatör neden alarm aldığını göremezse sisteme güvenmez ve kapatır. Bu alan aynı zamanda "kullanıcı/operasyon deneyimi" kriterinin karşılığıdır.

**Bu sözleşme sabit kaldığı sürece** dedektörün içi eşik kuralı da olabilir, makine öğrenmesi de. Yöntem seçimini erteleyebilmenin dayanağı budur.

### ④ Modbus register haritası

Dış dünyaya açılan yüz. Modül başına sabit blok — örn. her modüle 20 register:

| Modül | Register aralığı |
|---|---|
| Modül 1 | 100–119 |
| Modül 2 | 120–139 |

Blok içeriği: ortam sıcaklığı, nem, akım L1/L2/L3, nötr, termal maksimum, anomali seviyesi, modül sağlığı.

Değerler tam sayıya çevrilir, çarpan haritada belirtilir. **Emsal:** MPR-53CS haritası aynı yöntemi kullanır (örn. L1 gerilim → çarpan 0,1).

### ⑤ Okuma API'si

REST + JSON. İZ B sağlar, İZ C tüketir.

```
GET  /sahalar                                     → saha → pano → modül hiyerarşisi
GET  /moduller                                    → liste: id, son görülme, durum, seviye
GET  /moduller/{id}                               → detay + her ölçüm tipinin son değeri
GET  /moduller/{id}/seri?tip=&bas=&bit=&aralik=   → zaman serisi
GET  /moduller/{id}/termal/son                    → son termal özet
GET  /termal/kare/{kare_id}                       → tam kare (768 değer)
GET  /anomaliler?modul=&seviye=&bas=&bit=&durum=  → anomali listesi
GET  /anomaliler/{id}                             → gerekçe, kanıt, kare referansı
POST /anomaliler/{id}/onayla                      → operatör onayı
GET  /saglik                                      → servis durumu
```

---

## 10. Ortak sözlükler (enum'lar)

Üç izde birden geçer. Uyuşmazlık sessiz hata üretir.

```
olcum_tipi:  ortam_sicaklik | nem | akim_l1 | akim_l2 | akim_l3 |
             akim_notr | termal_maks | termal_ort | ark_olay

seviye:      normal | izle | uyari | kritik

tip:         sicak_nokta | akim_sicaklik_sapmasi | faz_dengesizligi |
             nem_yuksek | ortam_sicaklik_yuksek | ark | sensor_arizasi |
             modul_saglik

kalite:      iyi | supheli | yok

durum:       acik | onaylandi | kapandi
```

**Not:** Enerji analizöründen **gerilim** de bedava gelir. Ölçüm kümesine dahil edilmedi; istenirse `gerilim_l1..l3` olarak eklenmesi tek satırlık iştir.

---

## 11. Teknik kurallar

### Kimlik ve zaman

- **`modul_id` formatı:** `{saha}-{pano}-{modul}` → örn. `TR041-P01-M1`
  Hiyerarşi kimliğin içindedir; arayüzün ağaç görünümü ve yük testindeki gruplama bedava gelir.
- **Zaman damgası:** Modül kendi damgasını atar (`zaman`); toplama servisi ayrıca `alindi_zaman` ekler.
  *Gerekçe:* ağ gecikirse ölçümün zamanı ölçüldüğü an olmalıdır, alındığı an değil. İki alanın farkı ayrıca **modülün saat kaymasını** görünür kılar (senaryo 7'de kullanılır).
- **Format:** UTC, ISO 8601.

### Birimler

- Veritabanında gerçek birimlerde ve ondalıklı: °C, A, %.
- Modbus'a çıkarken tam sayıya çevrilir, çarpan register haritasında belirtilir.

### Termal kare

- 32 × 24 = 768 değer
- Satır öncelikli düz dizi
- Ondalıklı °C
- Ölçüm tablosunda değil, ayrı kare tablosunda

### Veritabanı: PostgreSQL

Uzun format satır hacmi için fazlasıyla yeterli; termal kare için JSON kolonu doğrudan çalışır; yaygın; Docker'da tek satır.

- SQLite eşzamanlı yazma ve hacim nedeniyle yetersiz kalır.
- Zaman serisi sorguları yavaşlarsa TimescaleDB bir PostgreSQL eklentisidir, sonradan eklenebilir.

**Şirket uyumu notu:** Belgelerde teknoloji yığınına dair hiçbir kısıt yoktur. Tek teknik kısıt public cloud yasağıdır. Entegrasyon beklentisi dar tanımlıdır: *"mevcut RTU/SCADA yapılarıyla entegrasyon yaklaşımını (Modbus Haritalama) göstermesi yeterlidir."* **Uyum ölçülen yer arayüzdür, iç yığın değil.**

### Repo düzeni

Tek repo — yönetilebilirlik, bütünlük ve teslimat kolaylığı için.

```
/sozlesmeler   ← enum'lar, şemalar, API tanımı (ortak; değişimi lidere sorulur)
/modul-sim     ← İZ A: sentetik üreteç + modül mantığı
/toplama       ← İZ A: toplama servisi + db şeması
/analiz        ← İZ B: dedektör + okuma API'si
/arayuz        ← İZ C: monitoring
/modbus        ← İZ C: modbus sunucusu
/alarm         ← İZ C: alarm servisi
/deploy        ← İZ C: kompozisyon, on-prem
/docs          ← herkes kendi yazısı; lider derler
```

**Kural:** Her servis kendi başına ayağa kalkabilir olmalıdır. İZ C'nin on-prem kompozisyonu bunun üzerine kurulur — yani her iz kendi servisinin çalışabilirliğinden, İZ C ise **bir arada** çalışabilirliğinden sorumludur.

### Dil ve framework

İz sahibinin kararıdır. Ortak olmak zorunda olan tek şey veritabanıdır.

---

## 12. İzler ve görev listeleri

Bölme katman bazlıdır (saha / analiz / operasyon yüzü). Teslimat kalemleri T1–T7 zaten katmanlara göre yazılmıştır ve doğal sözleşme noktaları katman sınırlarında oluşur.

```
İZ A            │ ①② │ İZ B              │ ③⑤ │ İZ C
Veri yolu       │────>│ Analiz            │────>│ Operasyon yüzü
ve saha tarafı  │     │                   │  ④  │
```

---

### İZ A — Veri yolu ve saha tarafı

**Sahip olduğu soru:** Veri nasıl doğar, nasıl toplanır?
**Sahip olduğu sözleşmeler:** ① ölçüm kaydı, ② modül paketi
**Bağımlılığı:** Yok — tek başına başlayabilir
**Teslimat karşılığı:** T1, T2, T3'ün modül kısmı

**Doküman çıktıları**

1. **Modül blok şeması** — sensörler, mikrodenetleyici, radyo, besleme, yedek depo. Kutular ve oklar; draw.io yeterli.
2. **Bileşen listesi** — parça, adet, işlevi, yaklaşık fiyat, **modül birim maliyeti**. "Maliyet ve sağlanan fayda" kriterinin karşılığı.
3. **Bağlantı bilgisi** — hangi bileşen hangi arayüz üzerinden bağlı (I²C, SPI, RS-485). Çizim olmak zorunda değil, tablo da olabilir.
4. **Mekanik yerleşim** — kutu ölçüsü, panodaki konum, kadraj/görüş hattı krokisi, sabitleme. *Kolaylık: elimizdeki TEDAŞ pano çiziminin üzerine modülün konumu ve sensörün görüş konisi işaretlenebilir; sıfırdan çizim gerekmez.*
5. **Saha koşulları gerekçesi** — sıcaklık, nem, IP, manyetik alan, kısa devre darbesi, yabancı cisim riski. Şartnameye atıflı.
6. **Montaj prosedürü** — 7 adım, süre, "kesinti yok" gerekçesi.
7. **Modül yazılım akış diyagramı** — uyan → oku → özetle → eşik kontrol → gönder.

**Kod çıktıları**

8. **Sentetik veri üreteci** *(bu izin en büyük tek işi)*
   - Normal çalışma: günlük yük profili, ortam sıcaklık salınımı, gerçekçi gürültü, mevsimsel kayma
   - Termal kare üretimi (32×24 matris: arka plan + sıcak nokta enjeksiyonu)
   - Bölüm 7.6'daki **yedi arıza senaryosunun** tamamı
   - Modül durum alanları (besleme, sinyal, yazılım sürümü)
   - N modülü aynı anda simüle edebilme (demo 8–10, yük testi 100)
   - **Uyarı:** Veri fazla temiz olursa dedektör kolayca çalışır ve hiçbir şey kanıtlanmaz. Gürültü, kayma ve sensör arızası senaryoları zorunludur.
9. **Modül içi eşik mantığı** — tam karenin ne zaman gönderileceğine karar veren kısım
10. **Veri toplama servisi** — paketleri alan uç nokta, doğrulama, veritabanına yazma, `alindi_zaman` ekleme
11. **Veritabanı şeması** — ölçüm tablosu (uzun format), termal kare tablosu, modül tablosu

**Bu izin karakteri:** Kod hacmi düşük, **muhakeme yükü en yüksek.** 7 maddesi dokümandır. Hiçbir derleyici "yanlış yaptın" demez; dokümanın zayıflığını ancak jüri söyler. **Tuzağı:** sessizce incelme. Panzehiri: "bitti" tanımı yukarıdaki 11 maddedir, hepsi gerekçeli olmalıdır.

> İz sahibine not: Zor tasarım kararları bu belgede zaten verilmiştir. Görev sıfırdan karar vermek değil, verilmiş kararları belgelemek, gerekçelendirmek ve sentetik veri üretecini yazmaktır.

---

### İZ B — Analiz

**Sahip olduğu soru:** Veriden anomali nasıl çıkar?
**Sahip olduğu sözleşmeler:** ③ anomali çıktısı, ⑤ okuma API'si
**Bağımlılığı:** İZ A'nın verisine — ancak sözleşmeler belli olduğu için kendi stub verisiyle başlayabilir
**Teslimat karşılığı:** T3, T4'ün veri tarafı, T5

12. **Normal davranış tanımı** — her ölçüm tipi için "normal nedir": dış ortamla fark, değişim hızı, komşu kanal/modül karşılaştırması. *Bu izin ve projenin puan taşıyan merkezi.*
13. **Sıcak nokta dedektörü** — termal matriste anormal bölge bulma, zaman içinde takip
14. **Korelasyon dedektörü** — akım sabit + sıcaklık artıyor → direnç artışı
15. **Nem / çevresel koşul dedektörü**
16. **Sensör sağlığı ayrımı** — `kalite` alanını kullanarak bozuk sensörü gerçek anomaliden ayırma
17. **Skor ve seviye üretimi** — normal / izle / uyari / kritik + eşiklerin gerekçelendirilmesi
18. **`gerekce` metni üretimi** — operatörün okuyacağı cümle
19. **Okuma API'si** — sözleşme ⑤'teki uç noktalar
20. **Ölçeklenebilirlik kanıtı** — 100 modül yükünde ingest + tespit, kaynak kullanımı ölçümü ve raporu (T5)
21. **Tespit yaklaşımının dokümantasyonu**

**Bu izin karakteri:** Derin ama dar. Kalem sayısı az, ama 12. madde tek başına "anomali ve risk tespit yaklaşımının başarısı" kriterinin tamamıdır. **Tuzağı:** döngüsel doğrulama — anomaliyi kendin enjekte edip kendin tespit ettiğinde hiçbir şey kanıtlanmamış olur. Panzehiri: gerçekçi gürültü ve sensör arızası senaryolarının ayırt edilebilmesi.

---

### İZ C — Operasyon yüzü

**Sahip olduğu soru:** Operatör ve dış dünya bu sistemi nasıl görüyor?
**Sahip olduğu sözleşmeler:** ④ Modbus haritası
**Bağımlılığı:** İZ B'nin çıktısına — sahte veriyle başlayabilir
**Teslimat karşılığı:** T4, T6, T7

22. **Monitoring arayüzü** *(bu izin en büyük tek işi)*
    - Saha/pano/modül hiyerarşisi, durum renkleri
    - Modül detayı: canlı değerler, zaman serisi grafikleri
    - Isı haritası görüntüleyici (tam kare)
    - Anomali ve alarm listesi, `gerekce` gösterimi
    - Alarm onaylama / kapatma akışı (`durum` alanı)
23. **Modbus register haritası dokümanı** — modül başına sabit blok, çarpanlarla
24. **Modbus TCP sunucusu** — kendi verimizi dışarı yayınlama
25. **Alarm servisi** — seviye→kanal kuralları, SMS/WhatsApp, **tekrar önleme** (aynı alarm 50 kez gitmemeli)
26. **On-prem kompozisyon** — tüm servisler tek komutla ayağa kalkar; "public cloud yok" iddiasının kanıtı
27. **Kendi kısmının dokümantasyonu**

**Bu izin karakteri:** Hacim ağırlıklı, derinlik az. Beş bağımsız teslimat vardır ve hiçbiri diğerini kolaylaştırmaz. **Tuzağı:** dashboard çekim kuvveti — arayüz işin eğlenceli ve görünür kısmıdır, bütün zaman oraya akar ve Modbus/alarm/on-prem yarım kalır. Halbuki o üçü brief'te açıkça sayılan maddelerdir. Panzehiri: arayüzü güzelleştirmeden önce diğer üçünü çalışır hale getirmek.

**Alarm servisi notu:** WhatsApp Business API bir bulut hizmetidir ve public cloud yasağıyla çelişir. Tutarlı çözüm yerel GSM/SMS modemi veya on-prem SMS gateway'dir. Bu bilinçli bir mimari karar olarak sunulmalıdır; jüri bu çelişkiyi sorabilir.

---

## 13. Entegrasyon ve kilometre taşı

**Erken "çirkin ama tam" zinciri:**

> Sentetik veri üreteci → veritabanı → basit eşik dedektörü → ekranda tek grafik → tek alarm.
> Hiçbiri güzel değil, ama zincir baştan sona akıyor.

Bu noktaya ulaşıldıktan sonra herkes kendi izini derinleştirir ve **her ekleme çalışan bir sisteme yapılır.**

Sona bırakılan entegrasyon, hackathon projelerinin en yaygın ölüm sebebidir. Üç iz sona kadar ayrı çalışıp son gün birleşirse birleşme günü kaybedilir.

---

## 14. Çalışma kuralları

### Karar yetkisi

**Lider kararı** (birden fazla kişiyi bağlayan her şey):
- Teslimat kapsamı ve "bitti" tanımı
- İz sınırları ve sahiplik
- Bu belgedeki tüm sözleşmeler ve ortak sözlükler
- Arıza senaryosu listesi (projenin iddiası)
- Efor dağılımı ve kapsam sınırı
- Organizatörle iletişim

**İz sahibinin kararı** (tek kişiyi ilgilendiren her şey):
- Dil, framework, kütüphane seçimi
- Dedektörün içindeki yöntem
- Arayüzün görsel tasarımı
- Kod organizasyonu, çizim aracı

### Dokümantasyon akışı

Her iz sahibi kendi kısmıyla ilgili yazıyı yazar ve lidere iletir. Lider ana dokümantasyonu oluşturur — son hâli tek ağızdan çıkmış olur.

### Sunum

Sona doğru ele alınacaktır, şimdilik ayrı bir sahibi yoktur; o dönemde uygun olan herhangi biri üstlenir. Demo senaryosunda çok karar gerekiyorsa lider, basit bir şeyse aynı mantık.

### Değişiklik yönetimi

Bu belgedeki bir kararı değiştirme önerisi lidere gider. Onaylanırsa belge güncellenir ve üç kişiye birden duyurulur.

---

## 15. Açık konular

### Organizatöre sorulacaklar (hiçbiri işi bloklamaz)

Brief'in "Sağlanacak Girdiler" bölümünde üç madde vardı; 2,5'i verilmiş durumda. Eksikler:

1. **Kabin içi/dışı fotoğrafları** — modül yerleşimi ve termal sensörün görüş hattı için doğrudan işe yarar. (Kablolama şema ve bağlantı çizimleri TEDAŞ şartnamesi olarak verilmiş sayılabilir.)
2. **Akım verisinin gerçek bir yük profili olup olmadığı** — mevcut veri rastgele görünüyor
3. **L2/L3 fazlarının gelip gelmeyeceği** — faz dengesizliği tespiti bunu gerektirir
4. *(Opsiyonel)* Tercih edilen veya kaçınılması gereken bir teknoloji yığını var mı
5. *(Er geç lazım)* 20 Eylül'de tam olarak ne teslim ediliyor — kod deposu, video, rapor, sunum, canlı demo?

Cevap gelmezse varsayımlar yazılır ve devam edilir.

### Ertelenen kararlar

- **Fark katmanı** (PD veya akustik) — çekirdek sistem çalışır hale geldikten sonra değerlendirilecek. Modül dokümanında genişleme payı bırakılacak.

---

## 16. Hızlı özet (tek bakış)

| Konu | Karar |
|---|---|
| **Ölçümler** | Ortam sıcaklık + nem + 32×24 termal dizi + akım (L1/L2/L3/nötr) + ark olay okuma |
| **Besleme** | 230 V iç ihtiyaç devresi + kısa süreli yedek depo |
| **Haberleşme** | Modül → kablosuz → saha gateway → merkez; dış anten |
| **Veri politikası** | Normalde özet, anomali anında tam termal kare |
| **Montaj** | Kapak içi/ön çerçeve, dik bakış; yeni delik yok; mıknatıs konumlandırma + mevcut yapıya sabitleme |
| **Modül/pano** | 1 baz, gerekirse 2 |
| **Tespit** | İki katmanlı: modülde basit eşik, merkezde asıl dedektör |
| **Veritabanı** | PostgreSQL |
| **Repo** | Tek repo, bileşen bazlı klasörler |
| **Demo** | ~3 saha × 2 pano ≈ 8–10 modül; ayrıca 100 modüllük yük testi |
| **Ekip** | 3 iz: A (veri yolu + saha), B (analiz), C (operasyon yüzü) |
| **Fiziksel donanım** | Yok — tasarım dokümanı + sentetik veri |
