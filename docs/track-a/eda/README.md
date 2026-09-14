# EDA kaynağı ve şema üreteci (KiCad)

`03-baglanti-semasi.svg` elle yazılmış SVG'dir; bu klasör aynı şemanın **KiCad** karşılığını taşır:
gerçek bir `.kicad_sch` (ERC'den geçmiş, netlist'i 03-pinout §3.1 ile otomatik doğrulanmış) ve ondan
üretilen `03-baglanti-semasi-kicad.svg`. `cad/` klasörüyle aynı felsefe: **elle çizim yok, kaynak model var.**

## Dosyalar

| Dosya | İçerik |
|---|---|
| `gen_sch.py` | Şema üreteci. Sembolleri KiCad kütüphanesinden (`share/kicad/symbols`) okuyup `lib_symbols`'a gömer, `extends` sembolleri düzleştirir; pin uçlarını kütüphane geometrisinden hesaplar; tel / etiket / güç sembolü / NC / not yerleşimi burada. Kütüphanede olmayan MLX90640 için özel sembol (`GridUp.kicad_sym`). |
| `GridUp-Modul.kicad_sch` / `.kicad_pro` | Üretilen şema (tek sayfa, A3) ve proje. `sym-lib-table` / `fp-lib-table` proje-yerel (`${KICAD10_SYMBOL_DIR}` / `${KICAD10_FOOTPRINT_DIR}`); KiCad GUI'de doğrudan açılır. |
| `GridUp-Modul.net` | `kicad-cli sch export netlist` çıktısı (mutlak yol ve zaman damgası temizlenmiş, deterministik) — doğrulamanın girdisi, commit'li. |
| `verify_netlist.py` | Netlist'i beklenen bağlantılarla karşılaştırır: 91 kontrol (GPIO atamaları, güç rayları, D1/D2 yönü, 120 Ω, EN RC, V_bias, CT kanalları). Tek başına: `python verify_netlist.py GridUp-Modul.net`. |
| `svg_min.py` | kicad-cli SVG'sini küçültür (2 MB → ~260 KB): çizgi-font yollarını atar, KiCad'in yazdığı gizli `<text>`'i Arial/Helvetica ile görünür yapar, koordinatları yuvarlar, tarih damgasını siler (deterministik). |
| `build.py` | Zincir: `gen_sch.py` → ERC → netlist + `verify_netlist.py` → SVG → `svg_min.py`. |
| `erc-raporu.txt` | Son ERC çıktısı (`--severity-all`): 0 hata, 0 uyarı. |
| `03-baglanti-semasi-kicad.svg` | Çıktı. Karşılaştırma referansı: `../03-baglanti-semasi.svg` (dokunulmadı). |

## Üretim zinciri

```
gen_sch.py → GridUp-Modul.kicad_sch → kicad-cli sch erc → kicad-cli sch export netlist → verify_netlist.py
                                     → kicad-cli sch export svg → svg_min.py → 03-baglanti-semasi-kicad.svg
```

```
python build.py                    # KiCad 10 (winget KiCad.KiCad) varsayılan yolda; yoksa --kicad-cli=PATH
```

## Şema içeriği (03-pinout.md §3.1–3.6 ile birebir)

- **U1 ESP32-S3-WROOM-1U** (kütüphane sembolü `ESP32-S3-WROOM-1`, aynı pinout): I²C GPIO8/9; CT GPIO4–7 (ADC1_CH3–6);
  besleme algılama GPIO1 (ADC1_CH0); UART1 GPIO17/18 + DE/RE GPIO21; genişleme GPIO10/11; USB D∓ ve UART0 servis
  başlığına; EN 10 k + 1 µF + reset; strapping / flash pinleri NC.
- **U2 MLX90640** (0x33, 100 nF), **U3 SHT31-DIS** (0x44, ADDR → GND, nRESET → 3V3), 2× 4,7 kΩ pull-up.
- **CT ön ucu ×4**: klemens → R_burden + V_bias (2× 100 k + 10 µF) → 1 kΩ / 100 nF RC → CT_L1…CT_N.
- **U4 MAX3485**: RO/DI ↔ UART1, RE+DE ↔ GPIO21, A/B → klemens + 120 Ω.
- **Besleme**: L/N/PE → F1 + MOV → **U5 RAC05-05SK/277** → 5V_RAW (100 k / 47 k → VSENSE) → **D1** Schottky (OR) → +5V rayı
  → **U6 LD1117S33** → +3V3; **R_şarj → C_sc süperkap → D2 → +5V** yedek yolu. PWR_FLAG'ler yalnız ERC için (dış kaynaklar).
- Anten: SMA panel konnektörü (U.FL pigtail RF, şemada net değil). Genişleme 2×5: 3V3 / 5V / GND / SDA / SCL / GPIO10 / 11.

## Neden iki çizim var — elle SVG ve KiCad karşılaştırması

| | `03-baglanti-semasi.svg` (elle) | `eda/03-baglanti-semasi-kicad.svg` (KiCad) |
|---|---|---|
| Rol | **Dokümandaki ana görsel** (03-pinout.md §3.0) | **Kaynak / kanıt**: ERC'den geçmiş şematik, netlist doğrulaması |
| Bilgi içeriği | Aynı netler, aynı pin atamaları (§3.1) | Aynı; ek olarak pin numaraları, ayak izleri, ERC/netlist kanıtı |
| Doğrulama | Elle, tabloya göre | Otomatik: ERC 0/0 + `verify_netlist.py` 91 kontrol |
| Sayfa | 1640 × 1040 birim, blok gruplu, renk kodlu lejant | A3 (420 × 297 mm), KiCad sembol standardı |
| Yazı boyutu, dokümana **1200 px** genişlikte gömülünce | 11–13 birim → **8–9,5 px**, okunur | etiket 1,69 mm → **4,8 px**, notlar 1,33 mm → **3,8 px**, okunmaz |
| Dosya | 21 KB | 260 KB (`svg_min.py` sonrası; ham kicad-cli 2 MB) |

Sonuç: bilgi olarak eşdeğerler; KiCad'in artısı **kanıt** (ERC + netlist), elle SVG'nin artısı **okunurluk** (gömme
ölçeğinde 2× büyük yazı, blok/renk düzeni). Bu yüzden dokümanda ana görsel elle SVG kalır, KiCad dosyaları kaynak
olarak bağlanır; KiCad SVG dokümana gömülmez. Elle SVG değiştirilirse `gen_sch.py` de güncellenir (tek doğruluk kaynağı
03-pinout §3.1 tablosu; `verify_netlist.py` bu tabloyu kodlar).

## Kurallar / notlar

- Net adları KiCad kısıtı gereği boşluksuz (`CT_L1`, `DE_RE`, `5V_RAW`); mm cinsinden 1,27 grid.
- Kavramsal şema — üretim çizimi değildir (karar kaydı §1.4); pasif değerler tipik başlangıç değerleri.
- Ayak izleri (footprint) sembol eşleşmesi için atanmıştır, PCB tasarımı yoktur (`02-pcb-yerlesimi.svg` Fusion'dandır).
- Font: SVG çıktısı Arial/Helvetica (`svg_min.py`); KiCad GUI kendi fontunu kullanır.
