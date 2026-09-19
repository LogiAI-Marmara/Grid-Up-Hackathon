# İZ C — Alarm ve Bildirim Servisi

Sözleşme ⑤'in küresel geçiş akışını (`GET /gecisler?sonra=&limit=`) dinler,
seviye yükselmelerinden hangisinin dış bildirim gerektirdiğine karar verir,
bildirimin **sonucunu** izler, tekrarları önler ve durumu yeniden başlatmada
korur.

Karar kaydı dayanağı: §3/T7 (acil bildirim mekanizması), §12/görev 25 (alarm
servisi, seviye→kanal kuralları, tekrar önleme), §T6 (public cloud yasağı).

---

## 1. Dört ayrı olay, dört ayrı söz

Bu servis bilerek şu dördünü birbirinden ayırır. Teslim raporlarında da
ayrı tutulmalıdır:

| Söz | Ne demek | Kim görebilir |
|---|---|---|
| **loglandı** | Konsol kanalı satırı yazdı | Servis |
| **kanal kabul etti** | SMS gateway / Telegram 2xx döndü | Servis |
| **SMS gerçekten teslim edildi** | Operatörün telefonunda mesaj var | **Servis göremez** |
| **operatör onayladı** | `POST /anomaliler/{id}/onayla` çağrıldı | İZ B / arayüz |

Servis yalnız ilk ikisini bilir. Kod hiçbir yerde üçüncüyü ya da dördüncüyü
iddia etmez; `TESLIM` sonucu "kanal kabul etti" demektir, "abone aldı"
demek değildir.

---

## 2. Çalıştırma

```bash
cd alarm
API_URL=http://localhost:8080 \
SMS_GATEWAY_URL=http://192.168.1.50:8080/message \
SMS_ALICILAR=+905551112233 \
python3 alarm_service.py
```

Servis açılışta yapılandırma uyarılarını yazar: zorunlu bir kanalın ayarı
eksikse, ya da bulut tabanlı bir kanal açıksa, bunu ilk kritik alarmı
beklemeden söyler.

### Ortam değişkenleri

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `API_URL` | `http://localhost:8080` | İZ B okuma API'si |
| `POLL_INTERVAL` | `5` | Sorgu aralığı (sn) |
| `COOLDOWN_SECONDS` | `300` | Eşdeğer bildirim bastırma süresi (sn) |
| `ALARM_STATE_FILE` | `./alarm_state.json` | Kalıcı durum dosyası |
| `ALARM_KANAL_KURALI` | `uyari:konsol,sms\|kritik:konsol,sms!` | Seviye→kanal kuralı |
| `ALARM_BOZUK_DURUM` | `dur` | Bozuk durum dosyasında: `dur` \| `sifirla` |
| `ALARM_YENIDEN_DENEME_TABAN` / `_TAVAN` | `30` / `900` | Yeniden deneme geri çekilmesi (sn) |
| `ALARM_BEKLEYEN_SINIRI` | `500` | Bekleyen bildirim kuyruğu üst sınırı |
| `SMS_GATEWAY_URL` | — | On-prem SMS gateway HTTP ucu |
| `SMS_ALICILAR` | — | Virgülle ayrılmış numaralar |
| `SMS_GATEWAY_TOKEN` / `_KULLANICI` / `_PAROLA` | — | Gateway kimlik doğrulaması |
| `SMS_GATEWAY_ALICI_ALANI` / `_MESAJ_ALANI` | `alicilar` / `mesaj` | JSON yük alan adları |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | — | Telegram (bulut — bkz. §4) |

Repoda gömülü anahtar yoktur (Madde 15); hepsi ortamdan okunur.

---

## 3. Seviye → kanal kuralı

Biçim: `seviye:kanal,kanal!|seviye:kanal`. Sondaki **`!` o kanalı zorunlu
yapar**: başarısız olursa olay teslim edilmiş sayılmaz, tekrar önleme
başlatılmaz ve geçiş yeniden denenmek üzere bekleyen kuyruğuna alınır.
Kuralda adı geçmeyen seviye hiç bildirim üretmez.

Varsayılan:

```
uyari:konsol,sms | kritik:konsol,sms!
```

- `izle` ve `normal` → dış bildirim yok.
- `uyari` → konsol + SMS denenir; SMS hatası olayı bekletmez (uyarı için
  yeniden deneme fırtınası istenmiyor).
- `kritik` → SMS **zorunlu**. Gateway reddederse ya da ulaşılamazsa olay
  teslim edilmiş sayılmaz.

`konsol` hiçbir varsayılan kuralda zorunlu değildir; tek başına bir olayı
teslim edilmiş yapamaz. Kritik alarmın yalnız loga yazılması dış bildirim
sayılmaz, ve servis "hiçbir seviyede zorunlu dış kanal yok" durumunu açılışta
uyarı olarak yazar.

---

## 4. Kanal seçimi ve public cloud kısıtı — **AÇIK BAĞIMLILIK**

> **Bu madde tamamlanmamıştır.** Kanal kararı ekipten beklenmektedir.

Karar kaydı §T6 public cloud'u yasaklıyor; §12'deki alarm notu şunu söylüyor:
*"WhatsApp Business API bir bulut hizmetidir ve public cloud yasağıyla
çelişir. Tutarlı çözüm yerel GSM/SMS modemi veya on-prem SMS gateway'dir."*

Kodun aldığı tavır:

- **`sms` kanalı** belirli bir ürüne bağlı değildir. Yapılandırılabilir bir
  yerel HTTP ucuna JSON POST eder; alan adları (`SMS_GATEWAY_ALICI_ALANI`,
  `SMS_GATEWAY_MESAJ_ALANI`) ayarlanabilir olduğu için Android SMS Gateway
  (`phoneNumbers`/`message`), yerel bir GSM modem servisi ya da kurum içi bir
  gateway aynı adaptörle sürülür. **Hangisinin kullanılacağı seçilmemiştir.**
- **`telegram` kanalı** çalışır durumda ama `bulut = True` işaretli,
  varsayılan kuralda yok ve açıldığında servis §T6 ile çeliştiğini açıkça
  yazar. Demo dışında kullanılması ekip kararı gerektirir.
- **WhatsApp API** değerlendirilirse: Business API bulut tarafında çalışır ve
  §T6 ile çelişir. Bu çelişki gizlenmeden karara bağlanmalıdır.

### Doğrulanmamış olan

Telefon/SIM üzerinden gönderim **otomatik olarak ücretsiz sayılmamıştır** ve
**gerçek alıcıya teslim doğrulanmamıştır**. Testlerdeki "teslim" sahte bir
gateway'in isteği kabul etmesidir. Gerçek bir SIM'den gerçek bir telefona
uçtan uca SMS gönderimi **yapılmamıştır**; maliyet ve fiilî teslim ayrıca
doğrulanmalıdır.

---

## 5. Tekrar önleme

Anahtar **olaydır, modül değil**: `anomali:<anomali_id>|seviye:<yeni_seviye>`.

- Aynı moduldeki iki ayrı anomali birbirini bastırmaz.
- `uyari → kritik` yükselmesi önceki `uyari` bildiriminin bekleme süresine
  takılmaz (farklı seviye = farklı anahtar).
- Aynı olayın aynı seviyedeki eşdeğer tekrarı bastırılır — "aynı alarm 50 kez
  gitmesin" (§12/görev 25) burada karşılanır.
- **Başarısız teslim tekrar önleme başlatmaz**: kanal hatası kendi yeniden
  denemesini bastıramaz. Bilinçli bastırma ve kanal hatası loglarda da ayrı
  ifadelerle görünür.
- `anomali_id` gelmezse anahtar geçiş id'sine düşer; geçiş id'leri tekil
  olduğu için hiçbir şeyi bastırmaz. Şüphe bastırma yönünde değil, bildirme
  yönünde çözülür.

`anomali_id` geçişin kendisinde gelir ve `/anomaliler/{id}` detayına bağlı
değildir. Detay API'si bozulduğunda ayrı olaylar tek anonim alarmda
**birleşmez**; bildirim yine gönderilir, ama modül ve gerekçe uydurulmaz:
mesajda eksikliğin kendisi (`DETAY ALINAMADI`, `modul: BILINMIYOR`) ve olay
kimliği yazar. Geçişi bekletmek yerine göndermek bilinçli bir tercihtir —
geciken alarm, kaybolan alarma yakındır; olay kimliği ve seviye operatörün
harekete geçmesi için yeterlidir.

---

## 6. Kalıcı durum ve teslim takibi

`alarm_state.json` dört şey tutar: `son_gecis_id`, `bekleyen`, `son_bildirim`,
`dusen_bildirim`.

**`son_gecis_id` bir çekme imlecidir, "buraya kadar bitti" işareti değildir.**
Teslim edilemeyen geçiş `bekleyen` kuyruğuna **tam gövdesiyle** taşınır ve
imleçle aynı dosyada, **tek atomik yazımla** kalıcılaşır. Böylece:

- imleç ilerler — kalıcı olarak başarısız tek bir olay, arkasındaki kritik
  alarmları rehin almaz;
- ama başarısız geçiş atlanmaz — kuyrukta durur, üstel geri çekilmeyle yeniden
  denenir ve yeniden başlatmadan sağ çıkar.

Gerçek imleç bu ikilidir.

### Hata yolları görünürdür

- **Yazılamayan durum başarı sayılmaz.** `save_state` hatada belleği son
  kalıcı anlık görüntüye geri alır ve ERROR yazar. Diske inmemiş bir imleçle
  devam edilseydi, o aralıktaki alarmlar ne yeniden denenir ne bildirilmiş
  olurdu — tam olarak sessiz alarm kaybı.
- **Bozuk durum dosyası sessizce sıfırlanmaz.** Varsayılan `ALARM_BOZUK_DURUM=dur`
  ile servis açılmaz (çıkış kodu 2) ve dosya operatör incelesin diye olduğu
  gibi bırakılır. Geçmişi bilerek feda etmek için `sifirla` gerekir; o zaman
  dosya `.bozuk-<zaman>` adına alınır ve ne kaybedildiği loglanır.
- **Kuyruk taşması sessiz değildir.** `ALARM_BEKLEYEN_SINIRI` aşılırsa en eski
  geçiş düşürülür, `dusen_bildirim` sayacı artar ve ERROR yazılır.

### Kabul edilen sınır

Kanal olumlu yanıt verdikten sonra, durum diske inmeden süreç ölürse o
bildirim **yeniden gönderilebilir**. Tekrar bildirim ile sessiz alarm kaybı
arasında tercih yapılmış, tekrar bildirim seçilmiştir.

---

## 7. Testler

### Birim + davranış testleri — **çalıştırıldı, 40/40 geçiyor**

```bash
cd alarm && python3 -m unittest test -v
```

A-01..A-05'in olumlu ve olumsuz senaryoları: gerçek `uyari → kritik`
yükselmesi, aynı modülde farklı anomaliler, HTTP 500 / zaman aşımı / bağlantı
kesintisi, yanlış yapılandırılmış kanal, durum yazma hatası, bozuk durum
dosyası, v1→v2 taşıma, kuyruk sınırı. Hiçbiri gerçek veritabanına, gerçek
`/gecisler` ucuna veya gerçek bir alıcıya bağlanmaz.

### Süreç düzeyi entegrasyon testi — **çalıştırıldı, geçiyor**

```bash
cd alarm && python3 entegrasyon_testi.py
```

Servisi **gerçek ayrı süreç** olarak başlatır, öldürür, yeniden başlatır;
gerçek HTTP taşıması ve gerçek durum dosyası kullanır. Gateway kapalıyken
alarmın teslim sayılmadığını, yeniden başlatmadan sonra bekleyen alarmın
teslim edildiğini, üçüncü başlatmanın tekrar üretmediğini ve aynı moduldeki
ikinci anomalinin bastırılmadığını gösterir. SMS gateway sahtedir.

### Konteyner kabul testi — **ÇALIŞTIRILMADI**

Bu ortamda Docker daemon erişilebilir değil (`docker info` başarısız), bu
yüzden konteyner yeniden oluşturma denemesi **yapılmamıştır**. A-04'ün
konteyner düzeyi kabul kanıtı bu bakımdan **açıktır** — compose değişikliği
uygulanmış olsa da (§8) çalıştığı doğrulanmadı.

Docker'ı olan birinin koşturması gereken adımlar:

```bash
cd deploy
docker compose up -d alarm_service
# kritik bir geçiş üretilip bildirildikten sonra:
docker compose down
docker compose up -d alarm_service
docker compose logs alarm_service   # aynı geçiş YENİDEN bildirilmemeli
docker volume inspect deploy_gridup_alarm_durum
```

Beklenen: ikinci açılışta log `📂 Durum yüklendi: son_gecis_id=<önceki id>`
yazmalı ve aynı geçiş için ikinci bir bildirim çıkmamalıdır.

---

## 8. Compose ve kalıcı volume

`alarm/Dockerfile` durumu `/durum/alarm_state.json` altında tutar ve `/durum`
için `VOLUME` bildirir. `deploy/docker-compose.yml` bu dalda buna göre
**güncellenmiştir**:

- `alarm_service` servisine `gridup_alarm_durum:/durum` volume'u bağlandı,
- `ALARM_STATE_FILE`, `ALARM_KANAL_KURALI` ve SMS gateway ortam değişkenleri
  eklendi,
- `volumes:` bölümüne `gridup_alarm_durum` tanımı eklendi,
- `deploy/.env.example` yeni değişkenlerle ve Telegram'ın bulut olduğu notuyla
  güncellendi.

Bu sayede `docker compose down && up` alarm durumunu (imleç, bekleyen
bildirimler, tekrar önleme kayıtları) korur.

> **Not:** `deploy/docker-compose.yml` bu görevin tek sahipliğinde değildir;
> değişiklik alarm servisinin ihtiyacı kadar tutulmuş, başka servise
> dokunulmamıştır. Compose sahibinin gözden geçirmesi beklenir.
>
> **Doğrulanmayan:** Bu ortamda Docker daemon yok; compose dosyası YAML
> olarak doğrulandı ama **ayağa kaldırılmadı** (bkz. §7).

## 9. Kapsam dışı

Arayüzün alarm kartları ve onay düğmesi, Modbus, İZ B'nin seviye eşikleri ve
olay kapatma mantığı bu servisin işi değildir. Operatörün `onayla` işlemi
bildirim teslimi değildir ve olayı `kapandi` durumuna geçirmez.
