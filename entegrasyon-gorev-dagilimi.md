# Entegrasyon — Görev Dağılımı

**Üst belge:** `gridup-proje-karar-kaydi.md`  
**Kapsam:** Yalnızca entegrasyon aşaması.  

---

## 0. Bu belge nedir

Üç PR incelendikten sonra alınan kararları izlere dağıtan belgedir. İçinde yalnızca karara bağlanmış maddeler vardır.

- **Ortak bölüm** — üç izi birden bağlayan kararlar ve sözleşmeler. Herkes okur.
- **İz bölümleri** — her sahibin neyi teslim edeceği ve kendi kabul kriterleri.

Her madde **hedef ve kabul kriteri** olarak yazılmıştır, uygulama adımı olarak değil. Hangi fonksiyonun değişeceği, kodun nasıl organize edileceği iz sahibinin kararıdır (üst belge, Kural 5).

Ortak bölümdeki maddeler üç kişiyi bağlar; değişiklik önerisi lidere gider.

---

## 1. Bu aşamada ne yapılıyor

Zincirin uçtan uca bağlanması. A'nın yazdığını B okuyor, B'nin ürettiğini C tüketiyor, hepsi tek komutla ayağa kalkıyor.

Sorusu: **veri aktı mı.**

İçeriğin doğruluğu bu aşamanın konusu değil — dedektör doğru anomaliyi mi buluyor, eşikler yerinde mi, üretilen veri makul mü. Sonraki aşamaya bırakılmıştır.

---

## 2. Ortak kararlar

### 2.1 Sözleşme sahipliği tek kaynağa iner

| Sözleşme | Sahibi |
|---|---|
| ① ölçüm kaydı, ② modül paketi | İZ A |
| ③ anomali çıktısı, ⑤ okuma API'si | İZ B |
| ④ Modbus register haritası | İZ C |

Aynı sözleşmenin ikinci bir kopyası hiçbir izde durmaz. Bir iz, başka bir izin sözleşmesini kendi klasöründe yeniden tanımlamaz.

**③ için geçerli biçim** olay modelidir. Tek anlık `zaman` alanı taşıyan sürüm geçersizdir:

```json
{
  "id": "an_00412",
  "sira": 412,
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

Bir anomali bir **olaydır**: açılır, güncellenir, kapanır. `seviye` anlık değeri, `maks_seviye` olayın gördüğü en kötü seviyeyi taşır. `sira` monoton artan sıra numarasıdır ve yeni olayların sayfalanmasına yarar.

### 2.2 Ortak sözlüğe `asiri_yuk` eklendi

```
tip: sicak_nokta | akim_sicaklik_sapmasi | faz_dengesizligi | nem_yuksek |
     ortam_sicaklik_yuksek | asiri_yuk | ark | sensor_arizasi | modul_saglik
```

**Gerekçe:** Aşırı yük senaryosunun sözlükte karşılığı yoktu ve üç iz üç farklı eşleme varsayıyordu. `akim_sicaklik_sapmasi` kullanılamaz — ilişki katmanı aşırı yükte bilerek tetiklenmiyor. `sicak_nokta`ya eşlenirse gevşek klemensle aynı tipe düşer ve ikisini ayıran iddia çıktıda görünmez olur.

### 2.3 Modül durumu veritabanında saklanır

Modül paketindeki `modul_durum` alanları (`besleme`, `sinyal`, `yazilim_surumu`) şu an toplama sırasında düşüyor; veritabanında karşılıkları yok.

**Karar:** Bu alanlar kendi tablolarında, **her pakette bir satır** olarak saklanır. Satırlar alt alta durduğu için hem anlık değer hem değişim ve eğilim okunabilir.

Tablo `gridup.modul_durum`, alanları:

| Alan | İçerik |
|---|---|
| `modul_id` | Modül kimliği |
| `zaman` | Paketin ölçüm zamanı |
| `besleme` | `sebeke` \| `yedek` |
| `sinyal` | Alınan sinyal gücü, dBm, tam sayı (negatif) |
| `yazilim_surumu` | Paketteki sürüm |
| `alindi_zaman` | Toplama servisinin damgası |

**Neden her pakette:** Yalnızca güncel değer tutulursa besleme kaybının ne zaman başladığı ve sinyalin zayıflama eğilimi kaybolur; ikisi de senaryo 7'nin içeriği.

### 2.4 Termal tam kare her ölçüm anında gönderilir ve saklanır

Mevcut politika — normalde özet, yalnızca modülün kendi eşiği tetiklendiğinde tam kare — kaldırılmıştır.

- Modül her ölçüm anında tam kareyi gönderir. Koşul yoktur.
- Ölçüm sıklığı **30 saniye**.
- Modül sensörü bu aralıktan daha hızlı okur ve aradaki kareleri ortalayarak tek kare üretir. Amaç gürültüyü düşürmek; eğilim tespiti için lazım olan hassasiyettir, hız değil.
- Termal özet karenin türevidir, dolayısıyla sıklığı kareninkiyle aynıdır.
- Kare veritabanında **ikili biçimde** saklanır. API'nin dışarı verdiği biçim değişmez — tüketiciler yine 768 sayılık dizi alır.

İkili kodlama, A yazdığı ve B çözdüğü için sözleşmedir:

| | |
|---|---|
| Tip | int16, işaretli |
| Bayt sırası | little-endian |
| Birim | 0,1 °C (değer 452 → 45,2 °C) |
| Düzen | satır öncelikli, 768 değer, toplam 1536 bayt |

**Bunun kaldırdıkları:**

- Modül içi eşik mantığı ortadan kalkar. Varlık sebebi karenin ne zaman gönderileceğine karar vermekti.
- Kanıt karesinin "en yakını hangisi, yoksa ne gösterilir" sorunu ortadan kalkar; her olay anının kendi karesi vardır.
- Geçmişe dönük yeniden tarama gerçekten mümkün hale gelir. Mevcut politikada geçmiş veri, o zamanki eşiğin gönderdikleriyle sınırlı kalıyordu.

**Gerekçe:** Eski politikanın dayanağı ölçülmemişti. 100 modül, 30 saniye, ikili biçimle günlük yaklaşık 430 MB — ölçüm tablosunun kendisiyle aynı mertebede. Bant genişliği tarafında 30 saniyede 1536 bayt, yani LoRa sınıfı bir radyo dışında her seçenek için önemsiz.

### 2.5 Saat kayması ile gecikmiş veri ayrılır

Modül saati (`zaman`) ile sunucu saati (`alindi_zaman`) arasındaki fark iki sebeple açılabilir:

1. Paket yolda gecikmiştir (iletişim kuyruğu, ağ kesintisi).
2. Modülün yerel saati kaymıştır.

İlki geçicidir ve sonraki pakette fark sıfıra yaklaşır. İkincisi süreklidir ve her pakette aynı yönde büyür.

**Karar:**
- Toplama servisi `alindi_zaman`ı her satıra basar.
- Analiz motoru saat kayması arızasını tespit ederken farkın **zaman içindeki eğilimini** izler, tek paketteki mutlak farkı değil.
- Bir modülün `zaman`ı gelecekte görünüyorsa da paket reddedilmez; `alindi_zaman` doğru zamanı taşır, farkın yönü saat kaymasının yönünü verir.

---

## 3. İZ A — Yapılacaklar (madde 1–5)

### Madde 1 — Modül durumu veritabanında saklanır
- `toplama/migrations/` altına yeni migrasyon: `gridup.modul_durum` tablosu.
- `toplama/kayit.py`: modül paketinden `modul_durum` alanlarını oku ve bu tabloya yaz.
- **Kabul:** Simülatörden gelen paketin ardından `SELECT * FROM gridup.modul_durum` satır döner.

### Madde 2 — Termal tam kare her ölçüm anında gönderilir
- `modul-sim`: `modul.py` içindeki eşik denetimi kalkar, her pakete `termal_kare` eklenir.
- Ölçüm sıklığı 30 saniye olarak ayarlanır (`ayar.py`).
- Ara karelerin ortalaması alınarak gürültü düşürülür.
- **Kabul:** Simülatörün ürettiği her pakette `termal_kare` vardır; `len(termal_kare) == 768`.

### Madde 3 — Termal kare veritabanında ikili saklanır
- `toplama/migrations/` altına yeni migrasyon: `piksel_verisi` kolonu `bytea` olur veya ikili saklayan yeni sütun/tablo açılır.
- `toplama/kayit.py`: 768 ondalık sayıyı int16 little-endian 1536 bayta kodlar ve yazar.
- **Kabul:** `OCTET_LENGTH(piksel_verisi) == 1536`.

### Madde 4 — Ortak sözlüğe `asiri_yuk` eklenir
- `sozlesmeler/enums.py` içinde `Tip.ASIRI_YUK = "asiri_yuk"`.
- `sozlesmeler/anomali.schema.json` güncellenir.
- Simülatörde aşırı yük senaryosu bu tipi üretir.
- **Kabul:** `python sozlesmeler/dogrula.py` geçer.

### Madde 5 — Anomali şeması tek kaynağa iner
- `sozlesmeler/anomali.schema.json` olay modeline (bölüm 2.1) güncellenir.
- **Kabul:** B'nin ürettiği olay çıktısı bu şemadan geçer.

---

## 4. İZ B — Yapılacaklar (madde 6–14)

### Madde 6 — İkili termal kareyi çözme
- Veritabanından okunan 1536 baytlık `bytea`'yı 768 elemanlı diziye geri çeviren fonksiyon.
- **Kabul:** `A`'nın kodladığı kare `B` tarafından çözüldüğünde değer farkı en fazla 0,1 °C'dir (yuvarlama).

### Madde 7 — `asiri_yuk` dedektörü
- Aşırı yük senaryosu için dedektör kuralı: üç faz akımı birden yüksek + pano sıcaklığı genel artış + `sicak_nokta` yok.
- Üretilen anomali tipi: `asiri_yuk`.
- **Kabul:** Aşırı yük sentetik verisinde `tip="asiri_yuk"` üretilir.

### Madde 8 — Modül durumu tablosundan okuma
- Dedektörler ve API, modül sağlığı (besleme, sinyal) için `gridup.modul_durum` tablosunu sorgular.
- **Kabul:** Besleme kaybı `gridup.modul_durum` üzerinden tespit edilir.

### Madde 9 — Saat kayması eğilim kontrolü
- `zaman` ile `alindi_zaman` farkının eğilimini hesaplayan mantık (bölüm 2.5).
- **Kabul:** Sabit gecikmeli veri alarm üretmez; sürekli büyüyen fark alarm üretir.

### Madde 10 — Olay yaşam döngüsü (K3)
- Anomali bir kez açılır (`durum="acik"`), güncellenir (`son_gorulme`, `maks_seviye`), koşul bitince ve histerezis süresi dolunca kapanır (`durum="kapandi"`).
- Her geçiş `gridup.anomali_gecis` tablosuna yazılır.
- **Kabul:** Aynı anomali her tarama turunda yeni satır açmaz, mevcut satırı günceller.

### Madde 11 — Okuma API'si (Sözleşme ⑤)
- REST + JSON uç noktaları: `/sahalar`, `/moduller`, `/moduller/{id}`, `/moduller/{id}/seri`, `/moduller/{id}/termal/son`, `/termal/kare/{id}`, `/anomaliler`, `/anomaliler/{id}/gecisler`, `/gecisler`, `/saglik`.
- **Kabul:** İZ C arayüzü ve alarm servisi bu uç noktaları sorgulayarak çalışır.

### Madde 12 — Kör test etiket dosyası biçimi
- Kör test aracının beklediği zemin gerçeği (ground truth) etiket formatının tanımlanması ve dokümante edilmesi.
- **Kabul:** Biçim belgelenmiştir; İZ A sentetik üreteci bu biçimde çıktı verebilir.

### Madde 13 — Kör test değerlendirme aracı
- Dedektör çıktılarını etiket dosyasıyla karşılaştıran ve 4 metriği (doğruluk, anomali yakalama, yanlış alarm, erken uyarı süresi) hesaplayan CLI aracı.
- **Kabul:** `python -m analiz degerlendir --etiket ...` çalışır ve metrikleri basar.

### Madde 14 — Duman testi kontrolleri
- Sistemin sağlıklı çalıştığını doğrulayan duman testi kontrolleri (`analiz.duman`).
- **Kabul:** Duman testi koşucusu bu kontrolleri çağırır ve başarılı döner.

---

## 5. İZ C — Yapılacaklar (madde 15–22)

### Madde 15 — Okuma API'sine bağlanma
- Arayüz ve servisler mock API yerine İZ B'nin Sözleşme ⑤ API'sini hedefler.
- **Kabul:** `http://analiz_api:8080` üzerinden canlı veriler arayüzde akar.

### Madde 16 — Modbus TCP sunucusu (Sözleşme ④)
- Modül başına 20 holding register'ı Sözleşme ④ haritasına göre dolduran Modbus TCP sunucusu (Port 5020).
- RSSI signed int16 (Offset 9), çarpanlar ve enum eşlemeleri.
- **Kabul:** Harici Modbus istemcisi register'ları okur; eksik veride sıfır yazılmaz, son değer korunur.

### Madde 17 — Alarm servisi ve geçiş dinleme
- `/gecisler` akışını sayfalı dinleyen, anti-flapping uygulayan Telegram bot alarm servisi.
- Cooldown modül ve anomali bazlı; kritik geçişler gecikmesiz iletilir.
- **Kabul:** Anomali seviye geçişinde Telegram mesajı düşer.

### Madde 18 — Arayüzde uzun format ölçümleri haritalama
- `GET /moduller/{id}` yanıtındaki `son_olcumler` dizisini pano kartlarına ve grafiklere yansıtma.
- **Kabul:** Sıcaklık, nem, akımlar ve faz dengesizliği ekranda görünür.

### Madde 19 — Canlı ısı haritası ve kanıt karesi
- 32×24 termal matrisi Nginx üzerinden görselleştirme. Normalde canlı son kare, alarm tıklandığında olayın kanıt karesini (`/termal/kare/{id}`) gösterme.
- **Kabul:** Termal matris renk paletiyle render edilir.

### Madde 20 — Operatör onay akışı
- Arayüzden operatörün alarmı onaylaması (`POST /anomaliler/{id}/onayla?aktor=...`).
- **Kabul:** Onaylanan anomali arayüzde sarı/onaylandı durumuna geçer, API'ye yansır.

### Madde 21 — Duman testi koşucusu
- Tek komutla tüm servisleri ayağa kaldırıp duman testlerini koşturan script (`duman_testi_kosturucu.py`).
- **Kabul:** Başarılı çıkış kodu `0` ile tamamlanır.

### Madde 22 — On-Premise Docker Compose dağıtımı
- `veritabani`, `toplama`, `analiz_api`, `analiz_tara`, `arayuz`, `modbus_server`, `alarm_service` servislerini içeren taşınabilir `deploy/docker-compose.yml`.
- **Kabul:** `docker compose up --build` komutu tek seferde ve repo dışı bağımlılık olmadan ayağa kalkar.
