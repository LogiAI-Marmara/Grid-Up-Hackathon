# 5. Saha Koşulları Gerekçesi

**Teslimat karşılığı:** T1, T2 · **Değerlendirme kriteri 3** ("saha koşullarında uygulanabilirlik")
**Dayandığı kararlar:** §2.3 TEDAŞ Tablo 1 · §2.2 kısa devre dayanımı · §7.5
**Yöntem:** Şartnameye **atıflı** olmak zorundadır (§7 doküman çıktıları satır 628).

**Kaynak:** TEDAŞ-MLZ/2003-06.B *Alçak Gerilim Dağıtım Panoları Teknik Şartnamesi*
(Şubat 2003 / Ocak 2006 revize / Haziran 2015 revize)

---

## 5.1 Şartnamenin öngördüğü çalışma koşulları (Tablo 1 — birebir)

| Koşul | Bina içi (Dahili) | Bina dışı (Harici) |
|---|---|---|
| **Ortam sıcaklığı, en çok** | 40 °C | 40 °C |
| **24 saat içinde ortalama** | 35 °C | 35 °C |
| **Ortam sıcaklığı, en az** | **−5 °C** | **−25 °C** |
| **Kirlilik derecesi** | Düzey II | Düzey III |
| **Bağıl nem** | +40 °C'de %50 · +20 °C'de %90 | +25 °C'de %100 |
| **Buzlanma** | — | Sınıf 10, 10 mm |
| **Yer sarsıntısı — yatay ivme** | 0,5g | |
| **Yer sarsıntısı — düşey ivme** | 0,4g | |
| **Yükselti** | Aksi belirtilmedikçe 2000 m | |
| **Sistem topraklaması** | Doğrudan topraklı | |

**Koruma derecesi (şartname §2.2.2):**

| Kurulum | Koruma derecesi |
|---|---|
| Bina içi (dahili) | **IP 2X** |
| Bina dışı (harici) | **IP 54** (kaidesiyle birlikte montajlı iken) |

**Muhafaza formu (şartname §2.2.6.1):** Panoların koruma derecesi **en az form 2B**
(TS EN 61439-2) olacaktır.

---

## 5.2 Modülün tasarım sınıfı — bilinçli aşırı tasarım

| Parametre | Şartname (en kötü durum) | Modül tasarımı | Sonuç |
|---|---|---|---|
| Alt sıcaklık | **−25 °C** (bina dışı) | **−40 °C** | ✓ Pay bırakıldı |
| Üst sıcaklık (ortam) | +40 °C | **+85 °C** | ✓ Pano içi ısı artışı için pay |
| Nem | +25 °C'de %100 | SHT31 ile ölçülür (0–100 %RH) | ✓ |
| Kirlilik | Düzey III (bina dışı) | IP54 muhafaza | ✓ |
| Sarsıntı | 0,5g yatay / 0,4g düşey | Mekanik sabitleme (yeni delik yok) | ✓ |
| Yükselti | 2000 m | (AC/DC modül 5000 m'e kadar) | ✓ |

### Neden −25 °C değil de −40 °C seçildi?

Karar kaydı §7.5 satır 318 bileşenler için **−40…+85 °C endüstriyel sınıf** şart koşar. Gerekçe
satır 321'de açıktır:

> *"Şartname ortam için −25…+40 °C öngörür, ancak **pano içi baradan gelen ısıyla bundan sıcaktır.**
> Ticari sıcaklık aralığı yetersizdir."*

**Bu, projenin savunulabilir aşırı tasarımıdır:** modül **panonun içindedir**, yani dış ortam
sıcaklığı + pano içi ısı artışına maruz kalır. Şartname +40 °C dış ortam öngörse bile, baraların
ve klemenslerin yaydığı ısıyla pano içi daha sıcaktır. Ayrıca **sistem tam da ısı arttığında
çalışmak zorundadır** — yazın en sıcak gününde, arızanın en olası olduğu anda.

### ⚠️ Tespit edilen sürtünme (dürüstçe belirtilmelidir)

Endüstriyel sınıf seçimi bazı bileşenlerde **tedarik kısıtı** doğuruyor:

| Bileşen | Sorun | Çözüm |
|---|---|---|
| Standart 230 V AC/DC modüller | −25 °C'de başlıyor | 277 VAC serisi seçildi (−40…+90 °C; 5 V tam yükte +75 °C, +90 °C derating ile) |
| 5,5 V süperkapasitörler | −25 °C'de başlıyor | Geniş aralıklı seri + gerilim derating |
| MCU PSRAM'li varyant | −40…+65 °C | PSRAM'siz varyant (bedava kısıt) |

**Sonuç:** Sınıf şartı, tasarımı kısıtlamış **ama engellememiştir** — üç durumda da uygun bileşen
bulunmuştur. Ayrıntı: [2. doküman §2.6](02-bom.md).

---

## 5.3 Kısa devre darbesi — mekanik gerekçenin kökü

**Şartname §2.2.4 (birebir):**
> *"Panoların tasarımı ve cihazların seçiminde Tablo:3b'de belirtilen kısa devre akımları dikkate
> alınacak ve panolar anma kısa devre akımlarında oluşacak **termik ve dinamik zorlamalara**
> dayanacaktır."*

**Ne olur:** Kısa devre anında baralar arasında çok büyük elektromanyetik kuvvet oluşur ve **pano
fiziksel olarak sarsılır.** Karar kaydı §2.3 satır 96 bunu ayrı bir başlık olarak not eder.

**Bunun modül tasarımına etkisi — üç yerde:**

1. **Sabitleme (en kritik):** Salt manyetik tutma **yeterli değildir**; tam da sistemin çalışması
   gereken anda (kısa devre) modül yerinden oynayabilir. Bu nedenle mekanik tutma **her durumda
   mevcut bir yapı elemanına** dayanır (§7.5 satır 335).
2. **Görüş hattı:** Termal sensörün değeri nişan almasına bağlıdır. Birkaç santim kayma klemens
   sırasını kadraj dışına çıkarır ve sistem **sessizce kör olur** — fark edilmesi en zor arıza türü.
3. **Kablo yönlendirme:** Menteşe yakınında kıvrım payı bırakılır (§7.5 satır 327) ki sarsıntı
   kabloyu koparmasın.

**Uyarı işareti:** Bu yüzden `ark_olay` ölçümü, erken uyarı değil **olay kaydı**dır (§7.1 satır 230).
Kısa devre/ark milisaniye ölçeğinde gelişir; önlemek değil, kaydetmek mümkündür.

---

## 5.4 İç ark dayanımı

**Şartname §2.2.5 (birebir):**
> *"Pano içinde ark oluşumunu önleyici ve süresini kısaltıcı önlemler alınacaktır. Küçük bir
> olasılıkla dahi olsa, oluşabilecek bir iç ark durumunda insanların korunması için gerekli
> önlemler alınmış olacaktır."*

**Modülün etkisi:** Modül, panoya **yeni delik açmadan** sabitlendiği için beyan edilen iç ark
dayanımını **etkilemez** (§7.5 satır 333). Bu, sabitleme kuralının ikinci gerekçesidir:

> *"pano tip testli bir muhafazadır, gövdeye yeni delik açmak beyan edilen IP sınıfını ve **iç ark
> dayanımını** etkileyebilir."*

Ayrıca modül, **canlı pano içinde yerinden çıkabilecek bir cisim** olamaz — bu kabul edilemez bir
risktir (§7.5 satır 333).

---

## 5.5 Elektromanyetik ortam

**Şartname §2.2.6.1:** Panoların koruma derecesi en az **form 2B** (TS EN 61439-2) olacaktır;
dikey inen çıplak ana baraların önüne kapaklar konur ve **akım trafolarının bulunduğu kısım
vidalı kapakla kapatılır.**

**Modül için çıkan sonuçlar:**

| Etken | Risk | Önlem |
|---|---|---|
| **Güçlü manyetik alan** | Mıknatıslı sabitleme akım trafolarını etkileyebilir | Mıknatıs akım trafolarından ve baralardan **uzağa** konur (§7.5 satır 337) |
| Bara gürültüsü | Sensör hatlarında indüklenen gürültü | I²C kısa mesafe (kart içi); RS-485 diferansiyel |
| Anahtarlama geçici rejimleri | Okuma bozulması | RS-485 diferansiyel sinyalleşme + hat sonlandırma |
| **Pano ana akım trafosu** | 2500/5 (donanım listesinden) | Mıknatıs ve modül manyetik elemanlarından uzak tutulur |

**Not — mıknatısın rolü sınırlıdır:** Mıknatıs yalnızca **konumlandırma ve kadraj ayarı** için
kullanılır; mekanik tutma görevi görmez (§7.5 satır 331).

---

## 5.6 Yabancı cisim ve temas riski

| Risk | Şartname dayanağı | Modül önlemi |
|---|---|---|
| Toz girişi | §2.2.2: harici tip **IP 54** | IP54 muhafaza |
| Su sıçraması | §2.2.2: harici tip **IP 54** | IP54 muhafaza |
| Gerilimli bölümlere dokunma | §2.2.6.1: form 2B, örtü plakaları, yalıtkan terminal koruyucuları | Modül yalıtılmış kutu içinde; 230 V hattı içeride |
| Ekran/kablo sıkışması | §2.2.10 pano içi bağlantılar | Menteşe yakınında kıvrım payı |
| **Modülün kendisi yabancı cisim olması** | İç ark dayanımı (§2.2.5) | Yeni delik yok + mekanik sabitleme zorunlu |

---

## 5.7 Nem ve yoğuşma

| Durum | Değer |
|---|---|
| Şartname bağıl nem (bina içi) | +40 °C'de %50 · +20 °C'de %90 |
| Şartname bağıl nem (bina dışı) | +25 °C'de %100 |
| **Modül ölçümü** | SHT31 ile sürekli izlenir (`nem` ölçüm tipi) |

**Bu, hem bir koşul hem bir ölçüm konusudur.** Nem iki işlevi görür (§7.1 satır 220):

1. **İzlenen büyüklük:** Nem yükselmesi / yoğuşma riski (§7.6 senaryo 4)
2. **Fiziksel risk:** Rutubet → yalıtım zayıflar → kaçak akım (§2.4)

**Modülün kendi korunması:** IP54 muhafaza, yoğuşmaya karşı modülü korur; buna ek olarak nem
ölçümü **kritik bir erken uyarı sinyali** olarak sisteme girer.

---

## 5.8 Sarsıntı ve titreşim

| Kaynak | Değer |
|---|---|
| Şartname yer sarsıntısı | 0,5g yatay / 0,4g düşey |
| Trafo titreşimi | Sürekli (yıllar boyunca) |
| Kısa devre sarsıntısı | Ani ve şiddetli |

**Kural (§7.5 satır 335):** *"trafo ve baraların sürekli titreşimi yıllar içinde mıknatısla duran
nesneyi 'yürütür'."*

**Önlem:** DIN rayı, mevcut cıvata delikleri veya kapak çerçevesi ile **mekanik sabitleme.**

---

## 5.9 Kutu yerleşiminin koruma derecesine etkisi

| Kurulum tipi | Panonun derecesi | Modül gereksinimi | Karşılanıyor mu |
|---|---|---|---|
| Bina içi (dahili) | IP 2X | IP54 (aşırı tasarım) | ✓ Fazlasıyla |
| Bina dışı (harici) | IP 54 | IP54 | ✓ Birebir |

**Tasarım kararı:** Modül **tek bir varyantta IP54** olarak tasarlanır. Böylece hem dahili hem
harici panolarda aynı modül kullanılabilir — **tek ürün, iki kurulum tipi** (üretim ve stok
basitleşmesi). Bu, T5 ölçeklenebilirlik açısından da avantajdır.

**IR pencere notu:** Sensörün baktığı yüzeyde IR geçirgen pencere kullanılır; bu, IP54 korumasının
delinmesini önler. Ayrıntı: [4. doküman §4.4](04-mekanik-yerlesim.md).

---

## 5.10 Uygunluk tablosu (şartname → modül)

| Şartname maddesi | Gereklilik | Modül karşılığı | Durum |
|---|---|---|---|
| §1.4 Tablo 1 | −25…+40 °C ortam | Bileşenler −40…+85 °C | ✓ |
| §1.4 Tablo 1 | Bağıl nem %100'e kadar | IP54 + SHT31 ile izleme | ✓ |
| §1.4 Tablo 1 | 0,5g / 0,4g sarsıntı | Mekanik sabitleme | ✓ |
| §1.4 Tablo 1 | Düzey II/III kirlilik | IP54 muhafaza | ✓ |
| §2.2.2 | IP 2X / IP 54 | IP54 (tek varyant) | ✓ |
| §2.2.4 | Kısa devre termik + dinamik | Mekanik sabitleme + görüş hattı koruması | ✓ |
| §2.2.5 | İç ark dayanımı korunmalı | Yeni delik açılmaz | ✓ |
| §2.2.6.1 | Form 2B, dokunma koruması | Yalıtılmış modül kutusu | ✓ |
| §2.2.8.6 | Kablo giriş/çıkış noktaları | Anten mevcut girişten çıkar | ✓ |
| §2.2.12 | İç ihtiyaç devreleri (20/6/2 A) | Ana besleme kaynağı | ✓ |

---

## 5.11 Kapsam dışı

- Panonun kendi tip deneyleri (ısınma, kısa devre, iç ark) — pano üreticisinin yükümlülüğü
- EMC/uyumluluk sertifikasyonu — prototip üretimi yok (§1.4)
- Saha topraklama detayı — pano üreticisinin sorumluluğunda