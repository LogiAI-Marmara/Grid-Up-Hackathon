# firmware — ESP32-S3 modül yazılımı (iskelet)

Grid Up Hackathon, İZ A. Brief T3 *"mikrodenetleyici üzerinde çalışan kaynak kodlar"* kaleminin karşılığı.

**Ne olduğu:** `modul-sim/modul_sim/modul.py`'deki modül mantığının (dokuz adım, 07 §7.1 akış diyagramı)
ESP32-S3-WROOM-1U-N8 için C++ karşılığı. Aynı sabitler (`include/ayar.h` ↔ `ayar.py`), aynı pinler
(`include/pinler.h` ↔ `docs/track-a/03-pinout.md` §3.1), aynı paket (sözleşme ②, `POST /paket`).

**Ne olmadığı:** Fiziksel modül üretilmedi (karar kaydı §1.4). Kod **PlatformIO'da derlenir** (ESP32-S3,
RAM %26, flash %28), **donanım üzerinde doğrulanmadı.** Sensör sürücüleri üretici kütüphaneleridir;
CT ön ucu sabitleri (`CT_ORAN`, `R_BURDEN_OHM`) ve Modbus register adresleri (`ANALIZOR_REG_*`,
`TVOC2_REG_TRIP`) sahadaki cihaza göre ayarlanacak **varsayımlardır**, `ayar.h`'de işaretli.
Arıza senaryoları burada yoktur; onlar simülatörün işidir (`modul-sim`, 7 senaryo).

## Derleme

```bash
cd firmware
pio run                     # derle (ilk seferde xtensa araç zinciri iner)
pio run -t upload           # yükle (kart yoksa gerek yok)
```

Ağ ve kimlik `build_flags` ile verilir, kaynakta sır yok:

```ini
build_flags = -DWIFI_SSID=\"saha\" -DWIFI_SIFRE=\"...\" -DTOPLAMA_URL=\"http://gateway:8000/paket\" -DMODUL_ID=\"TR041-P01-M1\"
```

## Akış (modul.py ile birebir, 07 §7.8)

| Adım | `modul.py` | `main.cpp` |
|---|---|---|
| 1–2 | dünya + senaryo (sentetik) | sahada fiziksel; sensör okumasının içinde |
| 3 | akım: 2 sn alt örnek, 30 sn ort. | `akimOku()` × 15: CT RMS (`ctRmsAmper`, 100 ms @ 2 kHz) veya Modbus analizör |
| 4 | kabin havası | `Adafruit_SHT31` sıcaklık + nem |
| 5 | ark sayacı | `arkTetikOku()`: TVOC-2 trip register farkı, kümülatif sayaç |
| 6 | modül saati | SNTP → UTC ISO 8601 `Z`; saat yoksa paket atlanır (uydurulmaz) |
| 7 | termal: 5 alt kare ort., kare + özet | `termalAltKareEkle()` (6 sn'de bir) → `termalKareBitir()`: yuvarla → maks, konum, 4 bölge |
| 8 | ölçüm satırları (①) | `olcumSatiri()`; yalnız `kalite: yok` `null` taşır; ortam/nem 2 çevrimde bir |
| 9 | modül sağlığı | `besleme` VSENSE'ten (5V_RAW < 4 V → `yedek`), `sinyal` = `WiFi.RSSI()`, sürüm |
| gönder | `UretilenPaket` | `HTTPClient.POST(TOPLAMA_URL)` |

**Politika:** her 30 sn bir paket, termal özet + 768 değerlik kare her pakette, koşulsuz
(entegrasyon kararı madde 2; `entegrasyon-gorev-dagilimi.md` §2.4). Modülde eşik yok, hüküm merkezde.

**Düşük güç:** süperkap gerilimi ölçülmüyor (03'te pin yok); yedekte 3 dk geçince (`YEDEK_DUSUK_GUC_S`,
02-bom §2.5 bütçe ~5 dk) yalnız `modul_durum` (+ varsa `ark_olay`) gönderilir, verici gücü kısılır.
Simülatördeki `dusuk_guc` dalının karşılığı.

## Bilinçli eksikler

- Merkezden modüle ayar protokolü (§7.4): `ayar.h` sabitleri yapılandırma adayı, kanal yok
- OTA, TLS, paket tamponlama (Wi-Fi yokken paket düşer, `modul_durum.sinyal` bunu gösterir)
- Analizör register haritası: model belli değil; `ANALIZOR_VAR=false` varsayılan, CT yolu aktif
- MLX90640 yayma katsayısı: kütüphane varsayılanı 0,95; klemens için 0,60 (01 §1.2) sahada ayarlanır
