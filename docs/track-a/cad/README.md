# CAD kaynakları ve çizim üreteci

`docs/track-a` altındaki üç kroki (`02-pcb-yerlesimi.svg`, `04-kutu-krokisi.svg`, `04-yerlesim-krokisi.svg`)
elle çizilmez; **Fusion 360 modellerinden** üretilir. Bu klasör kaynak modelleri ve üretim zincirini taşır.

## Modeller

| Dosya | İçerik | Koordinat |
|---|---|---|
| `GridUp-Kutu.f3d` / `.step` | Modül kutusu 120 × 80 × 50: gövde (2 mm duvar, R4), kapak 4 mm, IR yuva Ø23 / pencere Ø15, vent M6, LED, 4 × M3 köşe direği Ø7, 4 × PCB dikmesi Ø6, alt yüz PG7 ×3 + SMA, DIN klips, oval M5 yuvalar, mıknatıs cepleri | X sağ, Y yukarı, Z ön yüz normali (kapak Z 46–50) |
| `GridUp-PCB.f3d` / `.step` | Kart 110 × 70 × 1,6 + 31 parça gövdesi (ön: MLX90640 TO-39, SHT31, LED, pasifler / arka: ESP32, RAC05, süperkap yatık, klemensler, MAX3485, …); M3 delikler (7,7) vb.; köşelerde Ø8 direk boşluğu; 1 mm izolasyon yarığı | kart köşesi orijin; **PCB koordinatı = kutu koordinatı − 5 mm** |
| `GridUp-Kutu-Montaj.f3d` / `.step` | Kutu + PCB (PCB kutuda (5, 5, 39,4)); yan kesit ve iç görünüş buradan | kutu koordinatı |
| `GridUp-Pano.f3d` / `.step` | 1600 kVA AG pano 1600 × 1500 × 450 (2 mm sac, 20 mm montaj plakası, 22 mm kapak), 36 NH ayırıcı + klemens + T1/kontrol/kumanda/modem blokları, montaj kapak iç yüzünde (IR merkezi 650, 692,5) | X sağ, Y yukarı, Z öne; kapak iç yüzü Z = 0, plaka Z = −430 |

`.f3d` dosyaları thozoz hub / Default Project'teki bulut belgelerinin arşivleridir (montaj arşivi referansları içermez;
tam geometri için `.step`).

## Üretim zinciri

```
model_*.py  →  Fusion belgesi  →  proj.py + cfg_*.json  →  views/*-views.json  →  compose_*.py + svgkit.py  →  SVG
```

1. **Model script'leri** (`model_kutu.py`, `model_pcb.py`, `model_montaj.py`, `model_pano.py`): Fusion API ile geometriyi
   sıfırdan kurar. Fusion içinde çalışır (MCP `fusion_mcp_execute` script veya *Utilities → Scripts*). Türkçe karakter
   içeren gövde adları `chr()` ile verilir (MCP metni latin-1 okuyor).
2. **`proj.py`**: aktif tasarımdan ortografik projeksiyon. Kenarlar + silindir siluetleri; görünürlük
   `Component.findBRepUsingRay` ile parça parça test edilir (gizli çizgi ayıklama); `clip` ile yarım-uzay,
   `section` ile `TemporaryBRepManager.planeIntersection` kesit poligonları. Görünüşler `cfg_*.json` içinde
   (`d` bakış vektörü, `u` yukarı, `include/exclude(_prefix)`, `clip`, `section`). Çıktı mm cinsinden polyline
   listesi (`y` aşağı). Fusion'da:
   ```python
   globals()['CFG_PATH'] = r'<repo>/docs/track-a/cad/cfg_kutu.json'
   exec(compile(open(r'<repo>/docs/track-a/cad/proj.py', encoding='utf-8').read(), 'proj.py', 'exec'), globals())
   ```
   Hangi cfg hangi belgede: `cfg_kutu` → GridUp-Kutu, `cfg_pcb` → GridUp-PCB, `cfg_montaj` → GridUp-Kutu-Montaj,
   `cfg_pano` → GridUp-Pano (montajı açmadan önce *referansları güncelle*).
3. **`compose_*.py`** (Fusion gerekmez, düz Python 3): `views/*.json` + etiket/ölçü/not → SVG.
   ```
   python compose_kutu.py ../04-kutu-krokisi.svg
   python compose_pcb.py  ../02-pcb-yerlesimi.svg
   python compose_pano.py ../04-yerlesim-krokisi.svg
   ```
   `views/` klasörü commit'lidir; Fusion'a erişim olmadan da SVG yeniden üretilebilir (etiket düzeltmesi vb.).

## Kurallar

- Ölçüler mm; SVG ölçekleri: kutu 1 mm = 4 birim, PCB 1 mm = 8, pano 1 mm = 1.
- Font Arial/Helvetica; ayraç " / "; LF satır sonu (`newline=''`).
- Kutu ↔ PCB senkronu: ön yüz özellikleri (IR pencere, vent, LED) kutu koordinatında tanımlı; PCB'de aynı parça
  −5 mm. PCB dikmeleri kutu (12,12)/(108,12)/(12,68)/(108,68) = PCB (7,7)/(103,7)/(7,63)/(103,63).
- Kavramsal tasarım — üretim çizimi değildir (karar kaydı §1.4).
