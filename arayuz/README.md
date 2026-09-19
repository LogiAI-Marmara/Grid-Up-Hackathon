# İZ C — Monitoring Arayüzü

Operasyon yüzü: saha hiyerarşisi, canlı ölçümler, termal matris, zaman serisi,
çözülmemiş anomaliler ve operasyon günlüğü. Tükettiği API: `analiz/analiz/api.py`.

## Çalıştırma

| Yol | Komut | API adresi |
|---|---|---|
| Nginx (önerilen) | `docker build -t gridup-arayuz arayuz/ && docker run -p 8081:80 gridup-arayuz` | `/api` vekili |
| Doğrudan API | API'yi 8080'de çalıştırıp sayfayı 8080'den sun | göreli (`''`) |
| Dosyadan aç | `index.html`'i tarayıcıda aç | `http://<host>:8080` |

Adres çözümü `app.js` başındaki `API_BASE` ile yapılır. Dağıtımda
`window.GRIDUP_API_URL` tanımlanırsa her şeyin önüne geçer. Konteyner 80 dışında
bir konak portuna bağlandığında da `/api` vekil yolu korunur.

## Testler

Repo kökünden:

```sh
node --test "arayuz/tests/test_*.mjs"
```

ya da eşdeğeri:

```sh
npm test --prefix arayuz
```

Node 18+ dışında bağımlılık yoktur; test koşucusu Node'un kendi
`node:test` modülüdür, `npm install` gerekmez. Testler sahte (mock) bir DOM ve
sahte `fetch` kullanır; **gerçek operasyon veritabanına veya canlı API'ye
bağlanmaz**.

- `tests/harness.mjs` — paylaşılan sahte DOM ortamı
- `tests/test_arayuz_sozlesme.mjs` — UI-01..UI-08 sözleşme testleri
- `tests/test_arayuz_kabul.mjs` — operatör yolundan geçen ek kabul testleri

### Docker/Nginx doğrulaması

```sh
sh arayuz/dogrulama/docker_dogrula.sh
```

İmajı kurar, sahte bir `analiz_api` yanına koyar ve hem statik dosyayı hem
`/api/...` vekil yolunu sınar. Çalışan bir Docker artalan süreci ister.

## Arayüz neyi gösterir, neyi göstermez

Bu bölüm operatörün ekranda gördüğü ayrımların sözlüğüdür. Aynı kelimenin iki
farklı şeye gelmesi bu panelde en kolay yapılan hatadır.

### Cihaz durumu ≠ alarm seviyesi

- **Cihaz durumu** (`aktif` / `sessiz` / `pasif`) modülün veri/işletim durumudur.
  Yetkili kaynağı `GET /moduller` yanıtının `durum` alanıdır; `/moduller`
  sayfaları `toplam` bitene kadar taranır, ilk sayfa "tüm modüller" sanılmaz.
- **Alarm seviyesi** (`normal` / `izle` / `uyari` / `kritik`) API'den gelir ve
  ayrı bir rozettir. Arayüz termal sıcaklıktan kendi resmî seviyesini üretmez.
- Durumu bilinmeyen modül **"Durum bilinmiyor"** yazar; "Aktif" uydurulmaz.
  Tanınmayan ya da hiç gelmeyen seviye **"SEVİYE BİLİNMİYOR"** olur, sessizce
  "normal" yapılmaz.

### Özet ≠ gerçek tam kare

- **"Ölçülmüş Tam Kare"** yalnız `GET /termal/kare/{id}` yanıtı 768 sonlu
  sayısal piksel içerdiğinde, `modul_id` ve `zaman` eşleştiğinde yazılır.
- `kare_id=null` ya da kare isteği başarısızsa **"Tam kare mevcut değil; yalnız
  termal özet var"** denir. Bu durumda çizilen 768 piksel özetten türetilmiş bir
  tahmindir ve görüntünün üzerinde **"Özetten üretilmiş tahmini görsel —
  ölçülmüş piksel değildir"** şeridi sürekli durur. Sahte sensör gürültüsü
  eklenmez; görsel deterministiktir.
- Kanıt karesinde gösterilen sıcaklık `piksel_verisi[y*32+x]`'ten okunur.
  Anomali `skor`u **hiçbir koşulda** °C'ye çevrilmez.
- Renk skalası bir **ısı ölçeğidir**, alarm eşiği değildir.

### Onay ≠ kapanma

- Mevcut API'de operatöre açık bir `kapat` ucu **yoktur**. `POST
  /anomaliler/{id}/onayla` olayı yalnız `acik → onaylandi` yapar.
- Onaylanan olay listeden düşmez; **"Onaylandı — olay devam ediyor"** durumuna
  geçer. `acik` ve `onaylandi` olayların ikisi de "çözülmemiş" sayılır ve
  sayfalama `sonraki` imleciyle sonuna kadar taranır.
- `kapandi` geçişi sunucunun otomatik kararıdır; günlükte görünür.
- Onay için operatör kimliği zorunludur ve boşsa istek gönderilmez. Bu alan
  **gerçek kimlik doğrulaması değildir**; girilen ad denetim kaydına aktör
  olarak yazılır.

### Canlı ≠ eski

- Üstteki **"Cihaz Son Görülme"** `son_gorulme` alanıdır: cihazın ağda son
  görüldüğü an. Her ölçüm kanalının kendi `zaman` damgası ayrıca kartında
  görünür; tüm kanallar aynı anda ölçülmüş sayılmaz.
- **"Durum bildirimi"** alanı `durum_zaman`dır: besleme ve RSSI'nin bildirildiği
  an. Bu zaman yoksa bu iki değerin güncelliği iddia edilmez.
- Ölçüm kalitesi ayrı okunur: `iyi` gösterilir, `supheli` aynı kartta
  "Şüpheli ölçüm" uyarısıyla gösterilir, `yok` ise sayı olsa bile "Veri yok"
  sayılır. `0` yalnız API gerçekten `deger=0` gönderdiğinde görünür; eksik
  ölçüm `0` yapılmaz.
- Faz dengesizliği yalnız L1/L2/L3'ün üçü de mevcut, sayısal, birimi geçerli ve
  `kalite=iyi` iken hesaplanır; aksi hâlde "Hesaplanamadı" yazar.

### API erişimi ≠ modül sağlığı

- Üst çubuktaki **"API ÇEVRİMİÇİ"** göstergesi yalnız API'ye *erişilebildiğini*
  söyler. HTTP 500 de erişilebilir bir API'dir: gösterge çevrimiçi kalır,
  başarısız bölüm kendi hatasını ayrıca gösterir.
- **"BAĞLANTI KESİLDİ"** yalnız isteğin hiç tamamlanamadığı (ağ/DNS/zaman
  aşımı) durumda yazılır.
- Hiyerarşi, modül detayı, alarm listesi ve günlük ayrı isteklerdir; birinin
  başarısı diğerinin hatasını silmez.
- Operasyon günlüğü **sunucunun** geçiş akışıdır (`GET /gecisler`). Arayüzün
  kendi ürettiği satırlar denetim kaydı olarak sunulmaz. Akış `id` artan
  sıradadır; "son 30 geçiş" iddiası ancak imleçle sonuna kadar tarandıktan
  sonra kurulur. Günlük alınamazsa "Günlük güncellenemedi" görünür ve son
  başarılı liste korunur.

## Kapsam dışı / açık bağımlılıklar

- **Manuel "Kapat" işlemi** arayüzde yoktur; API'de karşılığı yok. İstenirse
  İz B sözleşme kararı gerektiren ayrı bir görevdir.
- **Kullanıcı kimlik doğrulaması** yoktur; operatör alanı serbest metindir.
- `deploy/docker-compose.yml`'in genel onarımı bu görevin kapsamı dışındadır.
