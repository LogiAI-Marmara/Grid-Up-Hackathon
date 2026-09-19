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
SMS_GATEWAY_KULLANICI=admin SMS_GATEWAY_PAROLA=<cihazdaki-parola> \
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
| `SMS_GATEWAY_URL` | — | Telefonun yerel sunucu ucu, örn. `http://192.168.1.50:8080/message` |
| `SMS_ALICILAR` | — | Virgülle ayrılmış numaralar |
| `SMS_GATEWAY_KULLANICI` / `_PAROLA` | — | Cihazın Basic auth bilgileri |
| `SMS_GATEWAY_TOKEN` | — | Basic auth yerine JWT kullanılıyorsa |
| `SMS_GATEWAY_ALICI_ALANI` / `_MESAJ_ALANI` | `phoneNumbers` / `textMessage.text` | JSON yük alan yolları (nokta = iç içe) |
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

## 4. Acil bildirim kanalı — Android SMS Gateway (yerel sunucu)

**Kanal seçildi:** "SMS Gateway for Android" uygulamasının **yerel sunucu**
kipi. Telefonun kendi SIM'i üzerinden SMS atar ve LAN'da bir HTTP sunucusu
açar; alarm servisi ona POST eder.

### 4.1 Neden bu

Karar kaydı §T6 public cloud'u yasaklıyor, §12'deki alarm notu da WhatsApp
Business API'nin bulut hizmeti olduğunu ve tutarlı çözümün yerel GSM/SMS yolu
olduğunu söylüyor. Yerel sunucu kipinde mesaj kurumun ağından çıkmaz: alarm
sunucusu → telefon → GSM şebekesi. Arada üçüncü bir sunucu yok.

### 4.2 ⚠️ Yerel kip şart, bulut kipi değil

Aynı uygulamanın bir de **bulut kipi** var ve mesajı `sms-gate.app`
sunucuları üzerinden geçirir. **Bu kip §T6 ile çelişir ve kullanılmamalıdır.**
Uygulamada yalnız "Local server" açılmalı.

### 4.3 Cihazın API'si

Kodun varsayılanları bu gövdeye göre ayarlıdır:

```
POST http://<telefon-ip>:8080/message      (Basic auth)
Content-Type: application/json

{"textMessage": {"text": "..."}, "phoneNumbers": ["+905551112233"]}
```

Cihaz **202 Accepted** döner. Düz bir `message` alanı eski/deprecated biçimdir
ve üretilmez — `test_android_sms_gateway_yuku_dokumanla_birebir` gövdenin
şeklini sınar.

Alan adları noktalı yol kabul ettiği için kurum içi düz bir gateway'e geçiş
kod değil **ayar** değişikliğidir (`SMS_GATEWAY_MESAJ_ALANI=mesaj`).

### 4.4 Kurulum

1. Telefona uygulamayı kur, **Local server**'ı aç.
2. Uygulamanın gösterdiği IP, kullanıcı adı ve parolayı `deploy/.env`'e yaz.
3. Telefon alarm sunucusuyla aynı ağda olmalı; IP'nin sabitlenmesi
   (DHCP rezervasyonu) önerilir, yoksa yeniden bağlanmada URL kayar.
4. Telefon şarjda ve uygulama arka planda çalışır durumda kalmalı.

### 4.5 ⚠️ Doğrulanmamış olan

**Gerçek bir telefondan gerçek bir alıcıya SMS gönderilmedi.** Testlerdeki
"teslim", cihazın API'sini taklit eden sahte bir gateway'in 202 dönmesidir.
Uçtan uca doğrulanması gerekenler:

- telefonun gerçekten SMS atması ve alıcıya ulaşması,
- SIM'in mesaj kotası / birim ücreti (telefon üzerinden gönderim otomatik
  olarak ücretsiz değildir),
- telefon uyku/arka plan kısıtlarında gönderimin sürmesi,
- uzun mesajın bölünmesi (alarm metni tek SMS sınırını aşabilir).

Bunlar yapılana kadar "SMS gerçekten teslim edildi" denemez; kodun
söyleyebildiği en fazlası "cihaz isteği kabul etti"dir.

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
