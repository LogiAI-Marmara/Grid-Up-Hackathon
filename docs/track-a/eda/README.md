# EDA kaynağı ve şema üreteci (KiCad)

`docs/track-a/03-baglanti-semasi.svg` bu klasördeki **KiCad şematiğinden** üretilir: gerçek bir `.kicad_sch`
(ERC'den geçmiş, netlist'i 03-pinout §3.1 ile otomatik doğrulanmış) → `kicad-cli` → gömülebilir SVG.
`cad/` klasörüyle aynı felsefe: **elle çizim yok, kaynak model var.** (Önceki elle yazılmış SVG git geçmişinde: `f5bf9be` ve öncesi.)

## Dosyalar

| Dosya | İçerik |
|---|---|
| `gen_sch.py` | Şema üreteci. Sembolleri KiCad kütüphanesinden (`share/kicad/symbols`) okuyup `lib_symbols`'a gömer, `extends` sembolleri düzleştirir; pin uçlarını kütüphane geometrisinden hesaplar; tel / etiket / güç sembolü / NC / not yerleşimi burada. Kütüphanede olmayan MLX90640 için özel sembol (`GridUp.kicad_sym`). |
| `GridUp-Modul.kicad_sch` / `.kicad_pro` | Üretilen şema (tek sayfa, özel 340 × 300 mm kâğıt; SVG'de çerçeve atılır) ve proje. `sym-lib-table` / `fp-lib-table` proje-yerel (`${KICAD10_SYMBOL_DIR}` / `${KICAD10_FOOTPRINT_DIR}`); KiCad GUI'de doğrudan açılır. |
| `GridUp-Modul.net` | `kicad-cli sch export netlist` çıktısı (mutlak yol ve zaman damgası temizlenmiş, deterministik) — doğrulamanın girdisi, commit'li. |
| `verify_netlist.py` | Netlist'i beklenen bağlantılarla karşılaştırır: 103 kontrol (GPIO atamaları, güç rayları, D1/D2 yönü, süperkap zinciri + boost, 120 Ω, EN RC, V_bias, CT kanalları). Tek başına: `python verify_netlist.py GridUp-Modul.net`. |
| `svg_min.py` | kicad-cli SVG'sini gömülebilir yapar (2 MB → ~280 KB): çizgi-font yollarını atar, KiCad'in yazdığı gizli `<text>`'i Arial/Helvetica ile görünür yapar (renk = grubun stroke rengi), viewBox'ı içeriğe kırpar, koordinatları yuvarlar, tarih damgasını siler (deterministik). |
| `build.py` | Zincir: `gen_sch.py` → ERC → netlist + `verify_netlist.py` → SVG → `svg_min.py`. |
| `erc-raporu.txt` | Son ERC çıktısı (`--severity-all`): 0 hata, 0 uyarı. |
| `../03-baglanti-semasi.svg` | Çıktı (dokümandaki şema). `build.py --out=PATH` ile başka yere de yazılabilir. |

## Üretim zinciri

```
gen_sch.py → GridUp-Modul.kicad_sch → kicad-cli sch erc → kicad-cli sch export netlist → verify_netlist.py
                                     → kicad-cli sch export svg (çerçevesiz, atlama yaylı) → svg_min.py → ../03-baglanti-semasi.svg
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
  → **U6 AP7361C-33E** (1 A, dropout ≈0,3 V) → +3V3; yedek yolu **R_şarj → C32 + C33 (2× Eaton HV1030 10 F / 2,7 V seri, R53/R54 dengeleme) → U7 TPS61099 boost 4,6 V → D2 → +5V**
  (float 4,6 V: +85 °C'de 2,3 V/hücre; ~50 J → ~5 dk @ 50 mA). PWR_FLAG'ler yalnız ERC için (dış kaynaklar; SW pini kütüphanede power_in).
- Anten: SMA panel konnektörü (U.FL pigtail RF, şemada net değil). Genişleme 2×5: 3V3 / 5V / GND / SDA / SCL / GPIO10 / 11.

## Yerleşim ve okunurluk (gömme için tasarım)

- **Sinyal akışı soldan sağa:** sol sütun girişler — CT ön ucu üstte (ESP üst pinleri IO4–7), I²C sensörler altta
  (IO8–9) → besleme telleri kesişmeden ESP'ye girer; orta ESP32-S3; sağ sütun çıkışlar (servis başlığı, RS-485,
  anten, genişleme); altta besleme zinciri.
- **Ana hatlar tel:** I²C bus (SDA/SCL dikey), CT_L1…N (kesişmesiz merdiven), UART1 ↔ MAX3485 (çip `mirror x` ile
  aynalı → pin sırası ESP ile aynı, tek kesişme). Güç netleri sembol; VSENSE, V_BIAS, 5V_RAW ve servis/genişleme
  başlıkları etiket (aynı ad = aynı net). Kaçınılmaz kesişmeler `--draw-hop-over` ile atlama yayı.
- **Renk kodu** (tel + etiket): 3V3 kırmızı, 5 V/230 V koyu kırmızı, GND/PE gri, I²C mavi, UART/RS-485 mor, analog
  turuncu; her blok açık tonlu dolgu + renkli başlık; lejant sağ üstte.
- **Yazı boyutu:** etiket 2,0 mm, not 1,8, başlık 2,2, pin adı 1,6; içerik ~305 × 252 mm → dokümana 1200 px
  genişlikte gömülünce etiket ≈ 8 px, not ≈ 7 px (eski elle SVG: 8–9,5 px). Çerçeve/başlık bloğu export'ta atılır,
  viewBox içeriğe kırpılır.
- **Elle SVG'den KiCad'e geçiş gerekçesi:** elle SVG'de metin kutularından taşmalar ve doğrulanmamış bağlantılar
  vardı; KiCad şematik tek doğruluk kaynağı (03-pinout §3.1 → `verify_netlist.py`), ERC + netlist kanıtı, her
  değişiklik script'te ve deterministik. Eksisi: KiCad sembol dili (NC pinler dahil büyük ESP32 dikdörtgeni), not
  yerleşimi daha az özgür, 21 KB → ~280 KB.

## Kurallar / notlar

- Net adları KiCad kısıtı gereği boşluksuz (`CT_L1`, `DE_RE`, `5V_RAW`); mm cinsinden 1,27 grid.
- Kavramsal şema — üretim çizimi değildir (karar kaydı §1.4); pasif değerler tipik başlangıç değerleri.
- Ayak izleri (footprint) sembol eşleşmesi için atanmıştır, PCB tasarımı yoktur (`02-pcb-yerlesimi.svg` Fusion'dandır).
- Font: SVG çıktısı Arial/Helvetica (`svg_min.py`); KiCad GUI kendi fontunu kullanır.
