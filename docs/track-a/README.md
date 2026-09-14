# İZ A — Veri Yolu ve Saha Tarafı · Donanım Tasarım Dokümantasyonu

Bu klasör, Grid Up Hackathon'unda **İZ A**'nın donanım tarafındaki teslimat karşılığıdır:
**T1** (kabin içi modül tasarımı, bileşen seçimi) ve **T2** (elektronik tasarım dokümantasyonu:
kart yapısı, giriş-çıkış bağlantıları, bağlantı şemaları, temel bileşenler).

> **Tasarım dokümanıdır, ürün değildir.** Hackathon kapsamında fiziksel donanım üretilmez ve
> satın alınmaz (karar kaydı §1.4). Bu belgeler modülün nasıl inşa edileceğini tanımlar; veri
> sentetik olarak üretilir, yazılım tarafı gerçek ve çalışır durumdadır.

---

## Dokümanlar

| # | Doküman | İçerik | Karşıladığı teslimat |
|---|---|---|---|
| 1 | [Modül blok şeması](01-blok-sema.md) | Sensörler, mikrodenetleyici, radyo, besleme, yedek depo; arayüzler | T1, T2 |
| 2 | [Bileşen listesi (BOM) ve birim maliyet](02-bom.md) | Parça, adet, işlev, yaklaşık fiyat, modül birim maliyeti + [kart yerleşimi](02-pcb-yerlesimi.svg) | T1, T2 · değerlendirme kriteri 8 |
| 3 | [Bağlantı ve pinout tablosu](03-pinout.md) | Hangi bileşen hangi arayüzle bağlı (I²C, SPI/UART, RS-485, besleme) + [bağlantı şeması](03-baglanti-semasi.svg) | T2 |
| 4 | [Mekanik yerleşim ve görüş hattı](04-mekanik-yerlesim.md) | Kutu ölçüsü, panodaki konum, kadraj krokisi ([yerleşim](04-yerlesim-krokisi.svg) · [kutu](04-kutu-krokisi.svg)), sabitleme | T1, T2 |
| 5 | [Saha koşulları gerekçesi](05-saha-kosullari.md) | Sıcaklık, nem, IP, manyetik alan, kısa devre darbesi, yabancı cisim | T1, T2 · kriter 3 |
| 6 | [Montaj prosedürü](06-montaj-proseduru.md) | 7 adım, süre, "kesinti yok" gerekçesi | T1 · kriter 3 |
| 7 | [Modül yazılım akış diyagramı](07-yazilim-akis.md) | Uyan → oku → özetle → eşik kontrol → gönder | T3 (modül kısmı) |

---

## İzlenebilirlik — her doküman hangi karara dayanıyor

Bu tablo, "bu doküman neden böyle yazılmış" sorusunun cevabıdır. Atıflar
[`gridup-proje-karar-kaydi.md`](../../gridup-proje-karar-kaydi.md) bölümlerinedir.

| Doküman | Dayandığı kararlar | Bağlayıcı şartlar |
|---|---|---|
| 1. Blok şema | §7.1 ölçüm kümesi · §7.3 besleme · §7.4 haberleşme | **Genişleme payı** ifadesi (§7.1 satır 237) |
| 2. BOM | §7.5 kutu ve bileşen sınıfı · §7.1 kapsama | Bileşenler −40…+85 °C endüstriyel sınıf (§7.5 satır 318) |
| 3. Pinout | §7.1 (akım: CT veya analizör) · §7.4 | Analizör varsa akım için ek sensör gerekmez |
| 4. Mekanik yerleşim | §7.5 kutu/konum/sabitleme · §7.1 kapsama hesabı | **Sabitleme metni** (§7.5 satır 331) · **IR pencere** (§7.5 satır 323) |
| 5. Saha koşulları | §2.3 TEDAŞ Tablo 1 · §2.2 kısa devre dayanımı · §7.5 | Şartnameye atıflı olmak zorunda |
| 6. Montaj prosedürü | §7.5 satır 343–351 | 7 adım birebir, kesinti yok, ~15–20 dk |
| 7. Yazılım akışı | §7.2 örnekleme · §7.4 veri politikası | Diyagram **koddan** türetilir, tahminle değil |

### Karar kaydının birebir şart koştuğu ifadeler (atlanamaz)

1. **Genişleme payı** (§7.1 satır 237): *"modül ek ölçüm kanalları için genişletilebilir arayüz taşır"*
   — PD/akustik fark katmanı ertelendiği için zorunlu.
2. **Enerji hasadı varyantı** (§7.3 satır 284): yardımcı besleme devresi olmayan sahalar için
   alternatif olarak konumlandırılacak.
3. **Sabitleme metni** (§7.5 satır 331–333): yeni delik açılmadan; mıknatıs yalnız konumlandırma için.
4. **Kızılötesi pencere** (§7.5 satır 323): cam/plastik IR'yi geçirmez → sensör kutunun yüzeyinde,
   dışa bakar halde.
5. **Mıknatıs + CT uyarısı** (§7.5 satır 337): güçlü mıknatıs akım trafolarının yakınına konmaz.
6. **Örnekleme tablosu** (§7.2): akım 1–5 sn (10 sn ort.), termal özet 10–30 sn, tam kare yalnız
   anomali anında, ortam/nem 30–60 sn, ark olay bazlı.
7. **Ark tespiti iddiası yok** (§7.1 satır 230): ark algılamayı biz yapmıyoruz; TVOC-2 kaydını
   okuyoruz. "Tespit" diye yazmak yanlış beyan olur.

---

## Ortak sözlüklere bağlılık

Bileşen adları, ölçüm tipleri, birimler ve zaman biçimi
[`/sozlesmeler`](../../sozlesmeler) altındaki sözleşmelerle aynı olmak zorundadır:

- `olcum_tipi`: `ortam_sicaklik`, `nem`, `akim_l1`, `akim_l2`, `akim_l3`, `akim_notr`,
  `termal_maks`, `termal_ort`, `ark_olay`
- `kalite`: `iyi`, `supheli`, `yok`
- `modul_durum.besleme`: `sebeke` | `yedek`
- `modul_id`: `{saha}-{pano}-{modul}` → örn. `TR041-P01-M1`
- Zaman: UTC, ISO 8601 (`YYYY-MM-DDTHH:MM:SSZ`)
- Birimler: DB'de gerçek birimde ondalıklı (°C, A, %)

Dokümanlarda bir modülden söz edilirken bu kimlik biçimi kullanılır; hiyerarşi (saha → pano →
modül) kimliğin içinde taşındığı için hem izleme arayüzündeki ağaç hem de 100 modüllük yük
testindeki gruplama kendiliğinden oluşur.

**Sözleşme değişikliği bu klasörün yetkisinde değildir.** Bir değişiklik gerekiyorsa takım
liderine iletilir ve üç ize birden duyurulur (§0 değişiklik kuralı).

---

## Termal dizi seçiminin karar kaydıyla bağı

Termal sensör olarak **MLX90640 (110°×75° görüş açılı, BAA kodu)** seçilmiştir. Bu, karar
kaydının kapsama hesabıyla matematiksel olarak örtüşür:

- §7.1 satır 232: *"Pano derinliği 450 mm; kapak içine konan sensör hedefe ~40 cm mesafededir.
  Geniş açılı versiyon bu mesafeden kabaca **114 × 61 cm** görür."*
- 40 cm'de 114 × 61 cm'lik görüş alanı, tan hesabıyla **~110° × 75°** açıya denk gelir.
- MLX90640'ın geniş açılı varyantı tam olarak **110° × 75°**'dir (Melexis datasheet, device
  marking: `A` = 110°, `B` = 55°).

Yani karar kaydındaki hesap, bu parçanın geniş açılı varyantını zaten varsaymıştır. **Çelişki yok,
sözleşme değişikliği yok** — bu, izin kendi bileşen seçimidir.

**Kapsama sınırı (dürüstçe):** Pano 160 × 150 cm olduğundan tek sensör tamamını görmez; en kritik
bölge olan **çıkış klemens sırasını** kapsar (§7.1 satır 232 ve §7.5 satır 339). Tam kapsama
gereken panolarda 2. modül eklenir.

---

## Terimler

- **Modül:** panonun içine yerleştirilen, bu dokümanlarda tanımlanan elektronik kutu.
- **Saha gateway'i:** trafo binası içinde, modüllerden veriyi toplayıp merkeze ileten ara cihaz.
  Bu dokümanların kapsamı **dışındadır** (İZ C).
- **Merkez / on-prem sunucu:** şirket içi sunucu; toplama servisi, anomali motoru, arayüz,
  Modbus sunucusu ve alarm servisi burada çalışır (İZ B ve İZ C).
- **Tedarikçi / distribütör adları:** yalnız fiyat ve teknik veri **kaynağı** olarak geçer;
  hackathon kapsamında sipariş verilmez.