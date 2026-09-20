# İZ B — Analiz Katmanı Karar Kaydı

**Proje:** Grid Up Hackathon — Pano/Hücre İçi Anomali Erken Uyarı Sistemi
**İz sahibi:** Efe (takım kaptanı)
**Belge tarihi:** 15 Eylül 2026
**Üst belge:** `gridup-proje-karar-kaydi.md` (proje geneli)
**Repo:** https://github.com/LogiAI-Marmara/Grid-Up-Hackathon

---

## 1. İZ B nedir

### 1.1 Projedeki yeri

```
İZ A            │ ①② │ İZ B              │ ③⑤ │ İZ C
Veri yolu       │────>│ Analiz            │────>│ Operasyon yüzü
ve saha tarafı  │     │                   │  ④  │
```

**Sahip olduğu soru:** Veriden anomali nasıl çıkar?
**Sahip olduğu sözleşmeler:** ③ anomali çıktısı, ⑤ okuma API'si
**Girdi:** İZ A'nın veritabanına yazdığı ölçüm ve termal kare tabloları
**Çıktı:** Anomali kayıtları (İZ C okur), okuma API'si (İZ C tüketir)
**Teslimat karşılığı:** T3 (yazılım mimarisinin analiz kısmı), T4'ün veri tarafı, T5 (ölçeklenebilirlik)

### 1.2 Ne yapar

1. Veritabanına düşen ölçümleri sürekli değerlendirir
2. Normal davranıştan sapmayı tespit eder ve seviyelendirir
3. Operatörün okuyacağı gerekçe cümlesini üretir
4. Bulguları anomali tablosuna yazar
5. İZ C'nin tükettiği okuma API'sini sunar
6. 100 modül yükünde çalıştığını ölçer ve raporlar

### 1.3 Ne yapmaz — sınırlar

| Yapmaz | Kim yapar |
|---|---|
| Veri üretmek, toplamak, veritabanına yazmak | İZ A |
| Arayüz, grafik çizme, ısı haritası görüntüleme | İZ C |
| Modbus register sunucusu | İZ C |
| On-prem kompozisyon | İZ C |

**İlke:** Veriyi üretmek İZ B'nin, görselleştirmek İZ C'nin. İZ C var olmayan veriyi çizemez; dolayısıyla "hangi veri üretilsin" soruları İZ B'nin kararıdır.

---

## 2. Alan bilgisi — analiz katmanı kavramları

Üst belgenin Bölüm 2'si elektrik ve donanım kavramlarını anlatır. Bu bölüm yalnızca İZ B'yi anlamak için gerekenleri ekler.

### 2.1 Taban çizgisi (baseline)

"Bu modül için normal ne demek" sorusunun sayısal cevabı. Sabit bir eşik değil, **geçmiş veriden hesaplanan bir bant.**

Neden sabit eşik yetmez: her panonun yükü farklıdır. Bir sanayi bölgesindeki pano gündüz 400 A çeker, bir konut panosu akşam 120 A. Tek bir "normal sıcaklık" değeri ikisine birden uymaz; uydurulmaya çalışılırsa ya yanlış alarm yağar ya da gerçek arıza kaçar.

### 2.2 Robust istatistik — medyan ve MAD

Ortalama ve standart sapma tek bir uç değerden bozulur. Bozuk bir sensör 500 °C yazarsa ortalama zıplar, standart sapma şişer ve o modülün taban çizgisi günlerce bozuk kalır.

- **Medyan:** sıralanmış değerlerin ortancası. Uç değerden etkilenmez.
- **MAD (Median Absolute Deviation):** her değerin medyandan uzaklığının medyanı. Standart sapmanın robust karşılığı.

"Robust" bu bozulmazlığı anlatır. İZ B taban çizgisini medyan + MAD ile kurar.

### 2.3 İki anomali türü

Bu ayrım dedektörün tüm mimarisini belirler.

**Tür A — Eğilim anomalisi (erken uyarı).** Şu an ortada arıza yok. Sistem çalışıyor, kimse bir şey fark etmiyor. Ama bir büyüklük bozulma eğrisinde ilerliyor.

Gevşek klemens örneğiyle:

| Zaman | Ne oluyor | Nokta sıcaklığı | Sistemin çıktısı |
|---|---|---|---|
| Gün 0 | Vida gevşedi | Ortamdan +5 °C | Normal, görünmez |
| Gün 10 | Temas direnci arttı | +15 °C | `izle` — eğilim başladı |
| Gün 25 | Artış hızlanıyor | +35 °C | `uyari` — planlı bakıma al |
| Gün 40 | Yalıtım zorlanıyor | 130 °C | `kritik` — acil müdahale |

Gün 10'da üretilen kayıt "şu an bir şey bozuk" demez. **"Bu nokta bozulma sürecinde, bakım ekibi bir dahaki turda buraya uğrasın"** der. Brief'in "kritik arıza gerçekleşmeden önce bilgilendirme" iddiası tam olarak budur.

**Tür B — Durum anomalisi.** Nem %95'e çıktı, faz dengesizliği oluştu, TVOC-2 ark kaydetti. Eğilim değil, **şu anki durum** yanlış. Erken uyarı iddiası yok.

### 2.4 Seviye = zaman ufku

`seviye` alanı bir aciliyet etiketi değil, **ne kadar zaman kaldığının** ifadesidir:

| Seviye | Zaman ufku | Operasyonel karşılık |
|---|---|---|
| `normal` | — | Kayıt yok |
| `izle` | Haftalar–aylar | Kaydet, takip et, müdahale yok |
| `uyari` | Günler | Planlı bakıma gir |
| `kritik` | Saatler, veya mutlak güvenlik eşiği aşıldı | Hemen |

### 2.5 Kazanılan süre (lead time)

Sistem uyarı verdiği an ile arızanın kritik hale geldiği an arasındaki fark. **Erken uyarı sisteminin asıl ürünü budur.** "Anomali tespit ettik" değil, "14 saat önceden haber verdik" ölçülebilir bir iddiadır.

### 2.6 Yanlış alarm oranı

Hiçbir şey olmadığı halde üretilen alarm sayısı. Sahada bir izleme sistemini öldüren metrik budur: operatör güvenini kaybedince sistemi kapatır veya bildirimleri susturur, ve gerçek alarm geldiğinde kimse bakmaz.

Bu yüzden tespit oranı tek başına yanıltıcıdır — her şeye alarm veren bir sistem %100 yakalar ve hiçbir işe yaramaz.

### 2.7 Etiketli ve kör test

**Etiket = cevap anahtarı.** Veri setinin yanında duran ayrı bir dosya:

```
senaryo_01: modul TR041-P01-M1, tip gevsek_klemens,
            baslangic 2026-09-08T14:00Z, kritik_esik 2026-09-10T03:00Z
temiz:      TR041-P01-M2, TR052-P01-M1
```

Bu dosya veritabanına girmez, dedektör onu görmez.

- **Etiketli test:** anahtar bende. Geliştirirken kullanılır; hata yapınca nerede yapıldığı hemen görülür.
- **Kör test:** anahtar üreticide (İZ A). Ben taramayı yaparım, çıktıyı dondururum, **sonra** anahtar açılır.

Fark: etiketli testte farkında olmadan cevaba göre ayar yapılır — "bu senaryoyu kaçırdım, eşiği indireyim" — ve dedektör o veri setine özel hale gelir. Kör test bunu imkânsız kılar.

**Kör olan ne, olmayan ne:**

| Kör olan | Kör olmayan |
|---|---|
| Hangi modülde senaryo var | Ölçümün ne olduğu (`olcum_tipi`) |
| Senaryonun türü | Birimi (°C, A, %) |
| Ne zaman başladığı | Fiziksel limitler (şartnameden) |
| Hangi modüllerin temiz olduğu | Modülün hangi panoda olduğu |

**Dedektör alan bilgisiyle donatılmıştır ve bu tasarımın kendisidir.** Bilmeseydi "değer 6 saatte 45'ten 72'ye çıktı" cümlesinde kalır, bunun tehlikeli olup olmadığını, hangi zaman ufkunda sorun çıkaracağını, operatöre ne yazacağını söyleyemezdi. Sözleşme ③'ün `gerekce` alanı üretilemezdi.

Biz genel amaçlı anomali dedektörü yapmıyoruz; **pano izleme dedektörü** yapıyoruz.

---

## 3. Karar K1 — Dedektörün veriye bağlanma ve tetiklenme biçimi

### 3.1 Karar

**Periyodik veritabanı taraması.** Dedektör arka planda dönen bir iştir. Sabit periyotla veritabanına sorar, en son işlediği noktadan sonrasını alır, etkilenen modüller için pencereli değerlendirme yapar, bulguyu yazar.

İZ A'nın kodu ile temas etmez; tek temas noktası veritabanı tablolarıdır.

### 3.2 Neden bu karar önemliydi

İZ A ile İZ B arasındaki **sınırın nerede çizildiği** kararıdır. Sınır yanlış yere çizilirse iki iz birbirine yapışır ve paralel geliştirme akışı bozulur. Ayrıca T5 kaynak ölçümünün neyi ölçeceğini ve erken uyarının gecikmesini bu karar belirler.

### 3.3 Reddedilen alternatifler

| Alternatif | Red gerekçesi |
|---|---|
| **Toplama servisinin dedektörü çağırması** (push) | En düşük gecikme, ama: (1) İZ A ile kod düzeyinde sıkı bağ; (2) dedektördeki yavaşlık veya hata ingest'i durdurur; (3) **geçmiş veriye tespit yeniden uygulanamaz** — algoritma değiştiğinde geçen haftayı tekrar tarayamazsın; (4) geç gelen paketler için ayrı kod gerekir |
| **Mesaj kuyruğu** (Redis/NATS/Kafka) | Ölçek için doğru cevap, gevşek bağ. Ancak: (1) yeni altyapı bileşeni → on-prem kompozisyonuna ek, İZ C'ye yük; (2) 100 modül ≈ 60 satır/saniye — bu hacimde kuyruğun çözdüğü bir problem yok; (3) İZ A ile ayrıca kuyruk sözleşmesi anlaşması gerekir |

### 3.4 Gerekçe

1. **Geçmişe yeniden uygulanabilirlik.** Algoritma değiştiğinde işaretçi geri alınır ve son N gün baştan taranır. Hackathonda algoritma defalarca değişecek; bu özellik olmadan her değişiklikten sonra yeni veri beklemek gerekir.
2. **Doğrulama.** Etiketli test verisi tabloya basılır, dedektör aynı veri üzerinde defalarca koşturulur. Döngüsel doğrulama tuzağının panzehiri bu tekrarlanabilirliktir.
3. **T5 ölçümü temiz çıkar.** "Bir tur N satırı X saniyede işledi, Y MB kullandı" — tek değişkenli, ayrıştırması kolay ölçüm.
4. **Geç gelen veri kendiliğinden yakalanır.** Modül 5 dakika sinyal kaybedip 300 satırı birden gönderirse hepsi alınır; özel kod gerekmez.
5. Paralel geliştirme kolaylığı.

---

## 4. Karar K2 — Tespit yöntemi ailesi ve başarı kanıtı

### 4.1 Karar

**Dört katmanlı dedektör. Çekirdekte makine öğrenmesi yok.**


### 4.2 Neden bu karar önemliydi

Değerlendirme kriterlerinin 2. maddesi — "anomali ve risk tespit yaklaşımının başarısı" — tamamen buradan geçiyor. Ayrıca sözleşme ③'ün `gerekce` alanı zorunlu: operatörün okuyacağı cümle üretilemiyorsa o yöntem bu projede kullanılamaz.

### 4.3 Reddedilen alternatifler

**Salt sabit eşik kuralları.** Hızlı ve açıklanabilir, ama tek başına erken uyarı veremez: eşik ancak sorun büyüdüğünde aşılır. Ayrıca her panonun yükü farklı olduğundan tek eşik tüm sahalara uymaz. **Tamamen reddedilmedi — katman 1 olarak korundu.**

**Makine öğrenmesi (Isolation Forest, autoencoder, LSTM vb.).** Bu projede teknik olarak mümkün ama savunulamaz:

| Sorun | Açıklama |
|---|---|
| Eğitim verisi | Kendi ürettiğimiz sentetik veri. Model gerçek pano davranışını değil **bizim simülasyon varsayımlarımızı** öğrenir |
| `gerekce` üretilemez | "Model 0.87 dedi" operatöre hiçbir şey anlatmaz. Sözleşme ③ ihlali |
| Doğrulama döngüsel olur | Kendi ürettiğimiz dağılımı öğrenip kendi ürettiğimiz anomaliyi bulur — hiçbir şey kanıtlanmaz |
| Jüri sorusu | "Bu modeli neyle eğittiniz?" sorusunun savunulabilir cevabı yok |


Fark katmanı olarak sonradan eklenmek istenirse: mimari buna kapalı değil, ancak çekirdek tespit hiçbir zaman modele bağlanmaz.

### 4.4 Kanıt stratejisi

**Düzenli kör testler.** Tek seferlik kör test yeterli değildir; her büyük dedektör değişikliğinden sonra yeni tohumla (seed) yeni set üretilir, eski set etiketli geliştirme setine dönüşür.

**Protokol:**

1. İZ A üreteci çalıştırır: N gün, M modül. Rastgele seçtiği modüllere senaryo enjekte eder, **bir kısmını hiç dokunmadan bırakır.**
2. Bana yalnızca veri verilir; etiket dosyası üreticide kalır.
3. Dedektör çalıştırılır, çıktı dondurulur.
4. Anahtar açılır, dört metrik hesaplanır.

**İki tuzak — İZ A'ya iletilecek:**

- **Temiz modül olmazsa test değersizdir.** Her modülde senaryo varsa "hepsine alarm ver" diyen bir dedektör %100 tespit oranı alır. Yanlış alarm ancak temiz modüller varsa ölçülebilir.
- **Kör set bir kez kullanılır.** Sonuç görüldükten sonra dedektör düzeltilip aynı set tekrar çalıştırılırsa set körlüğünü kaybeder. Yeni tur için yeni tohum gerekir.

**Ölçülecek metrikler — dördü birlikte raporlanır:**

| Metrik | Neyi gösterir |
|---|---|
| Senaryo başına tespit oranı | Yedi arıza senaryosundan kaçını yakaladık |
| **Kazanılan süre** | Kritik eşiğe varmadan kaç saat önce uyardık — projenin asıl ürünü |
| Yanlış alarm oranı (modül-gün başına) | Sahada kullanılabilir mi |
| Sensör arızası ayrımı | Bozuk sensörü anomali sanıyor muyuz |

---

## 5. Dedektör mimarisi — dört katman

Katmanlar sırayla çalışır. Her biri farklı bir arıza sınıfına bakar; hiçbiri diğerinin yerini tutmaz.

### Katman 0 — Sensör sağlığı filtresi

**Her şeyden önce çalışır.** Girdi: `kalite` alanı, donuk değer kontrolü (N tur boyunca hiç değişmeyen ölçüm), fiziksel olarak imkânsız değerler.

Bozuk sensör `sensor_arizasi` tipinde kayıt üretir ve **o kanal için diğer katmanlar atlanır.**

Gerekçe: sensör bozulunca değer 0 veya uç bir sayı gelir ve bu anomali gibi görünür. Bu ayrım yapılmazsa sistem her bozuk sensörde yangın alarmı verir — ve bu, operatör güvenini en hızlı yok eden şeydir.

### Katman 1 — Mutlak sınırlar

Taban çizgisinden **bağımsız** çalışır: modülün "normali" ne olursa olsun 130 °C kritiktir.

Kapsadığı senaryolar: nem eşiği aşımı, mutlak yüzey/ortam sıcaklığı, faz dengesizliği yüzdesi, ark olayı kaydı.

Kaynağı: TEDAŞ şartnamesi, malzeme sıcaklık sınırları, ve Bölüm 9'daki delta T kriterleri. **Tür B (durum anomalisi)** karşılığıdır.

### Katman 2 — Taban çizgisinden sapma

Her modül-kanal için robust istatistikle (medyan + MAD) normal bant hesaplanır. İki şey ölçülür:

- **Sapmanın büyüklüğü:** değer bandın ne kadar dışında
- **Sapmanın eğilimi:** son N saatte artıyor mu, hızlanıyor mu

**Eğilim olmadan erken uyarı yoktur.** Bir noktanın 60 °C olması değil, iki haftada 45'ten 60'a çıkmış olması anlamlıdır. Bu katman **Tür A (eğilim anomalisi)** karşılığıdır ve projenin erken uyarı iddiasını taşır.

**Tasarım notu — taban çizgisi zehirlenmesi:** Taban çizgisi kayan pencereyle güncellenirse, yavaş gelişen bir arıza zamanla "yeni normal" olarak öğrenilir ve anomali kaçar. Bunun önüne geçmek için taban çizgisi penceresi, tespit penceresinden belirgin biçimde uzun tutulur ve anomali açıkken taban çizgisi güncellenmez. Bu bir uygulama kararıdır, kodda açıkça belgelenecektir.

### Katman 3 — İlişki katmanı

Tek kanala bakarak görülemeyecek olanı görür. **Projenin özgün teknik iddiası burasıdır.**

| Karşılaştırma | Ne gösterir |
|---|---|
| **Akım–sıcaklık** | Akım sabit, sıcaklık artıyor → bağlantı direnci artıyor |
| **Faz–faz** | L1 ve L3 normal, L2 ısınıyor → tek fazda sorun. Ortam değişimini kendiliğinden eler |
| **Termal matriste komşu piksel** | Tüm kare ısındıysa ortam ısınmış; tek piksel ayrıştıysa gevşek klemens |
| **Modül–modül** | Aynı sahadaki modüller birlikte ısındıysa hava sıcak; biri ayrıştıysa o panoda sorun var |

Bu katman aynı zamanda **yanlış alarmı düşüren** katmandır: yaz sıcağında tüm panolar ısınır ve katman 2 tek başına alarm yağmuru üretir; karşılaştırma bunu eler.

### Skor, seviye ve gerekçe

Her katman kendi sapmasını normalleştirilmiş bir skora çevirir. Seviye eşikleri Bölüm 2.4'teki zaman ufkuna bağlanır. `gerekce` cümlesi, tetikleyen katmandan ve sayılardan şablonla üretilir.

Örnek uçtan uca akış:

```
Gelen satır:
{"modul_id":"TR041-P01-M1","olcum_tipi":"termal_maks","deger":72.4,"birim":"C"}

Çekilen pencere (son 6 saat):
  termal_maks    : 45.1 → 72.4   (+27.3 °C)
  akim_l2        : 310  → 308 A  (değişmedi)
  ortam_sicaklik : 31.2 → 31.8   (değişmedi)

Katman 0: kalite = iyi, değer donuk değil        → geç
Katman 1: 72 °C < 90 °C mutlak sınır              → tetiklenmez
Katman 2: modül medyanı 46 °C, MAD 2.1;
          değer bandın çok dışında, artış eğilimi → TETİKLENİR
Katman 3: akım sabit, ortam sabit, sıcaklık artıyor
          → ısı yükten gelmiyor → direnç artışı   → TETİKLENİR

Üretilen kayıt:
{"seviye":"uyari","tip":"akim_sicaklik_sapmasi","skor":0.81,
 "gerekce":"L2 çıkış bölgesi 6 saatte +27 °C yükseldi, akım (310→308 A)
            ve ortam sıcaklığı değişmedi. Bağlantı direnci artışı belirtisi."}
```

---

## 6. Karar K3 — Anomali kaydının yaşam döngüsü

### 6.1 Karar

**Olay (episode) modeli: aç → güncelle → kapat.** Ayrıca her durum geçişi ayrı bir journal tablosuna yazılır.

### 6.2 Neden bu karar önemliydi

Bir gevşek klemens arızası 3 gün sürer. 10 saniyelik turla bu **25.920 tur** demektir. Her turda kayıt yazılsaydı tek bir gevşek vida için 25.920 anomali satırı oluşurdu.

Sonuçları İZ B'de kalmazdı:

- İZ C'nin anomali listesi kullanılamaz hale gelirdi
- Alarm servisi 25.920 bildirim atmamak için tekrar önleme yazmak zorunda kalırdı — ama sorun kaynaktaydı
- `durum: acik | onaylandi | kapandi` alanı anlamsızlaşırdı: operatör 25.920 satırdan hangisini onaylayacak?
- Kazanılan süre metriği hesaplanamazdı

### 6.3 Reddedilen alternatifler

| Alternatif | Red gerekçesi |
|---|---|
| **Her turda yeni kayıt** | Yukarıdaki hacim sorunu. Ayrıca "aynı arıza mı yeni arıza mı" sorusunu İZ C'ye devreder — ama bu soruyu cevaplayacak bilgi (hangi katman tetiklendi, aynı piksel mi, koşul kesintisiz mi) yalnızca dedektörde vardır. İZ C'de tahminle çözülür ve yanlış çözülür |
| **Skor geçmişi için ayrı tablo** | Skor her turda değişir → olay başına binlerce satır. Operatör skor eğrisini değil sıcaklık eğrisini görmek ister; sıcaklık eğrisi zaten ham ölçüm serisinden çizilebilir. Skor seyri yalnızca test çıktısında tutulur |

### 6.4 Sektör dayanağı

Bu karar keyfi değil; endüstriyel alarm yönetiminin yerleşik modelidir.

**ANSI/ISA-18.2** (*Management of Alarm Systems for the Process Industries*, 2016 baskısı) alarmı bir **durum makinesi** olarak tanımlar. Standardın durumları: Normal, Unacknowledged, Acknowledged, Return-to-Normal Unacknowledged, Latched Unack/Ack, Shelved, Suppressed by Design, Out-of-Service.

Bizim `acik | onaylandi | kapandi` bunun sadeleştirilmiş üç durumlu halidir — aynı model.

**SCADA ürünlerinde** (Ignition, Geo SCADA, Vijeo Citect) bu iki ayrı yapı olarak yaşar:

| | Ne tutar | Satır sayısı |
|---|---|---|
| **Alarm summary / status table** | Şu anda aktif alarmlar | Alarm başına 1 satır |
| **Alarm journal** | Her durum geçişi — aktif oldu, onaylandı, normale döndü | Geçiş başına 1 satır, kalıcı |

Journal'ın ayrı tutulmasının gerekçesi yalnızca görüntüleme değil **denetim izidir (audit trail)**: "bu alarm ne zaman geldi, kim ne zaman gördü, ne zaman kapandı" elektrik dağıtımında düzenleyici bir sorudur. Operatör onayı da bir geçiştir ve kim/ne zaman bilgisi taşır.

### 6.5 Uygulama kuralları

- **Olay kimliği:** aynı `modul_id` + aynı `tip` + kapanmamış → aynı olay
- **Kapanma:** koşul üst üste ~30 dakika sağlanmazsa `kapandi`. Histerezis, anlık dalgalanmada olayın açılıp kapanmasını (chattering) önler
- **Seviye yükselmesi ayrı bir olaydır:** `izle → uyari` geçişi alarm servisine haber verilecek bir değişimdir; `uyari` içinde skorun 0.81'den 0.83'e çıkması değildir

---

## 7. Sözleşmeler

### 7.1 İZ B'nin tükettiği (İZ A üretir)

- **① Ölçüm kaydı** — uzun formatta ölçüm satırları
- **② Modül paketi** — `termal_ozet`, `termal_kare`, `modul_durum`
- Termal kare tablosu, modül tablosu, veritabanı şeması

Bunlar üst belgede tanımlıdır ve İZ B tarafından değiştirilemez.

### 7.2 İZ B'nin ürettiği — sözleşme ③, önerilen değişikliklerle

Üst belgedeki hale K3 kararının gerektirdiği alanlar eklenir:

```json
{
  "id": "an_00412",
  "modul_id": "TR041-P01-M1",
  "tip": "akim_sicaklik_sapmasi",
  "seviye": "uyari",
  "maks_seviye": "uyari",
  "skor": 0.81,
  "ilk_gorulme": "2026-09-08T14:20:00Z",
  "son_gorulme": "2026-09-09T06:40:00Z",
  "durum": "acik",
  "gerekce": "L2 çıkış bölgesi 6 saatte +27 °C yükseldi, akım (310→308 A) ve ortam sıcaklığı değişmedi. Bağlantı direnci artışı belirtisi.",
  "kanit": { "kare_id": "kr_0091", "piksel": [14, 9] }
}
```

**Eklenen alanlar:** `ilk_gorulme`, `son_gorulme`, `maks_seviye`.
(`zaman` alanı `ilk_gorulme` + `son_gorulme` ikilisiyle değiştirildi; `seviye` artık anlık değeri taşır.)

**Yeni tablo — `anomali_gecis` (journal):**

| Alan | Açıklama |
|---|---|
| `anomali_id` | Hangi olaya ait |
| `zaman` | Geçişin zamanı |
| `onceki` / `yeni` | Durum veya seviye değişimi |
| `aktor` | `sistem` veya operatör kimliği |

Ayrıca anomali tablosunda **monoton artan sıra numarası** ve zaman indeksi bulunur — alarm servisinin "en son işlediğim yerden sonrasını" kaçırmadan okuyabilmesi için.

### 7.3 İZ B'nin ürettiği — sözleşme ⑤, okuma API'si

Üst belgedeki uç noktalara ek olarak:

```
GET /anomaliler/{id}/gecisler    → olayın durum geçişleri (journal)
```

Diğer uç noktalar üst belgedeki gibidir.

---

## 8. Ölçeklenebilirlik — T5

Brief'in T5 maddesi 100 modülü ekranda göstermeyi değil, *"işleyebilecek şekilde tasarlanmasını ve gerekli kaynak kullanımının değerlendirilmesini"* istiyor. İZ B'nin yük testi + kaynak raporu bu maddeyi karşılar.


---

## 9. Standart ve kaynak dayanakları

Eşiklerin nereden geldiği jürinin soracağı ilk sorudur. "Biz uygun gördük" ile yayınlanmış kaynağa atıf arasında büyük fark vardır.

### 9.1 Alarm yönetimi

**ANSI/ISA-18.2-2016** — alarm durum makinesi, shelving/suppression kavramları, chattering alarm önleme. K3 kararının dayanağı.

### 9.2 Termografi ile bağlantı denetimi — delta T kriterleri

Infraspection Institute standardında (2016 baskısı) aktarılan NETA kriterleri iki farklı karşılaştırma tabanı kullanır:

| Delta T | Benzer bileşene göre | Ortam havasına göre |
|---|---|---|
| Priority 4 | 1–3 °C | 1–10 °C |
| Priority 3 | 4–15 °C | 11–20 °C |
| Priority 2 | — | 21–40 °C |
| Priority 1 | >15 °C | >40 °C |

Bu tasarımı üç noktada doğrular:

- **"Benzer bileşenle karşılaştırma" birincil yöntemdir** — katman 3'teki faz–faz ve komşu piksel karşılaştırmasının karşılığı
- **Ortam havasına göre delta ikinci tabandır** — ortam sensörü koyma kararının gerekçesi
- **Öncelik sınıfları seviye enum'una eşlenebilir** — eşikler uydurulmak yerine yayınlanmış kaynağa dayandırılır

**Sınır:** Bu kriterler anlık denetim içindir (teknisyen kamerayla gelir, bakar, gider), sürekli izleme için değil. Kaynağın kendisi "kesin bilim değil, önceliklendirme aracı" demektedir. Katman 1'de referans olarak kullanılır; katman 2'nin eğilim tespiti bunun ötesinde bir şeydir ve projenin kattığı değer orasıdır.

### 9.3 Kaynaklar

- ANSI/ISA-18.2-2016, *Management of Alarm Systems for the Process Industries*
- ICONICS GENESIS dokümantasyonu — ISA-18.2 alarm state transition diagram
- Inductive Automation (Ignition) — alarm journal ve alarm status table ayrımı
- Schneider Electric Geo SCADA — Alarm Summary dokümantasyonu
- Infraspection Institute, *Standard for Infrared Inspection of Electrical Systems & Rotating Equipment*, 2016
- TEDAŞ-MLZ/2003-06.B — AG dağıtım panoları teknik şartnamesi
