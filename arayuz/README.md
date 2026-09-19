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

İmajı kurar, önce **API yokken** arayüzün ayağa kalkabildiğini (Nginx üst akış
adını çalışma anında çözer; sabit `proxy_pass` ile "host not found in upstream"
deyip hiç açılmıyordu), sonra sahte bir `analiz_api` yanına koyup hem statik
dosyayı hem `/api/...` vekil yolunu, hem de yapılandırma dosyalarının web
kökünde yayımlanmadığını sınar. Çalışan bir Docker artalan süreci ister;
Windows'ta Git Bash ile koşar.

Son koşum: 19 Eylül 2026, Docker Desktop 29.5 — dört kontrol de geçti.

### Manuel operatör senaryosu

19 Eylül 2026'da gerçek yığında (compose: `veritabani`, `analiz_api`, `toplama`,
`arayuz`, `alarm_service`; `deploy/smoke_seed.py` ile 28 modül / 14 anomali)
Chrome'da elle geçildi. Sonuçlar:

| Adım | Beklenen | Görülen |
|---|---|---|
| Modül geçişi (TR041-P01-M1 → P01-M2) | Başlık, rozet ve tüm kartlar yeni modüle döner | 32.0 → 31.9 °C, 80.2 → 50.4 °C, KRITIK → NORMAL, anında |
| Özet/tam kare ayrımı | Tam kare yoksa görselin üstünde sürekli uyarı | P01-M1 "Ölçülmüş Tam Kare"; P01-M2 "Tam kare mevcut değil" + görselin üstünde "Özetten üretilmiş tahmini görsel" |
| Şüpheli ölçüm (TR063-P01-M1, `termal_maks` kalite=supheli, `/termal/son` 404) | Değer + "⚠️ Şüpheli ölçüm" işareti | **İlk turda hata:** kart "--" / "Termal Veri Yok" diyordu, şüpheli 153.9 °C hiç görünmüyordu. Düzeltildi; şimdi 153.9 °C + uyarı + kalite altyazısı |
| Eksik ölçüm (`ark_olay` yok) | "Veri yok", 0 uydurulmaz | "-- Trip / Veri yok" |
| Boş operatör kimliğiyle onay | POST yapılmaz, uyarı | Uyarı çıktı, istek gitmedi |
| Onay (op-efe, an_00014) | Kart kalır, "Onaylandı — Olay Devam Ediyor"; günlükte operatör satırı | Aynen; günlük `ID 35: Operatör Onayı: an_00014 (Operatör: op-efe)` |
| API kesintisi (`analiz_api` durduruldu, Nginx 502/504) | "BAĞLANTI KESİLDİ", hata şeridi, bayat değer kalmaz | **İlk turda hata:** gösterge "API ÇEVRİMİÇİ" kaldı, şerit hiç çıkmadı, 32.0 °C bayat kaldı. Düzeltildi; şimdi "BAĞLANTI KESİLDİ", "HATA" rozeti, şerit, kartlar "--" |
| Kesintide açılan sayfa | API dönünce ağaç kendiliğinden dolar | **İlk turda hata:** "Hiyerarşi taranıyor..." sonsuza kadar kalıyordu. Düzeltildi |
| Toparlanma (API geri geldi) | Gösterge, rozet, kartlar döner; şerit kalkar | **İlk turda hata:** şerit kalıyordu. Düzeltildi; 10 sn içinde tam toparlanma |

Bu senaryoda "SMS/Telegram gönderildi" iddiası **yoktur**; arayüz yalnız API'yi
görür.

### Nginx vekili ve DNS

`nginx.conf` `/api/` isteklerini `analiz_api:8080`'e vekiller ve adı çalışma
anında **Docker'ın gömülü DNS'i `127.0.0.11`** ile çözer; böylece API kapalıyken
Nginx açılabilir, API sonradan gelince veya yeniden oluşturulup IP'si değişince
yeniden başlatma gerekmez. Bilinen sınır: imaj Docker/Compose dışında
(çıplak makine, Kubernetes, Docker uyumlu DNS vermeyen Podman) çalıştırılırsa
`resolver` satırı o ortamın DNS adresiyle değiştirilmelidir.

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
- **"BAĞLANTI KESİLDİ"** isteğin hiç tamamlanamadığı (ağ/DNS/zaman aşımı)
  durumda **ve** vekilin 502/503/504 döndürdüğü durumda yazılır. Dağıtımda
  tarayıcı API'ye hiç değmez, Nginx'e konuşur; bu üç kod Nginx'in "arkadaki
  API'ye ulaşamadım" demesidir.
- Kesinti sırasında seçili modülün kartları "--" olur ve kırmızı şerit çıkar;
  API dönünce şerit kalkar, sayfa kesintide açıldıysa ağaç kendiliğinden dolar.
  Periyodik tarama süren bir isteğin üstüne yenisini bindirmez (vekil hatası
  saniyeler sürebilir).
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
