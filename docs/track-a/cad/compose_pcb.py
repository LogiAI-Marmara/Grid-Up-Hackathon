import json, sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from svgkit import Svg, INK, DIM, MUTED

V = json.load(open(os.path.join(HERE, 'views', 'pcb-views.json')))
OUT = sys.argv[1]
S = 8
OX, OY = 80, 80
ORIG = (0, -70)  # on/arka_thru: x = X, y = -Y  → kart sol-üst = (0,-70)

def px(x, y): return OX + x * S, OY + (70 - y) * S  # model mm → sayfa

GRP = {  # gövde adı → renk grubu
    'ESP32': '#546e7a', 'RAC05': '#ad1457', 'F1': '#ef6c00', 'MOV': '#ef6c00', 'Klemens 230V': '#ef6c00',
    'LDO': '#ad1457', 'D1': '#ad1457', 'D2': '#ad1457', 'R_sarj': '#ad1457', 'Bolucu': '#ad1457',
    'Superkap': '#f9a825', 'Boost': '#ad1457', 'L_boost': '#ad1457', 'R_bal': '#f9a825', 'MAX3485': '#2e7d32', 'R120': '#2e7d32', 'Klemens RS-485': '#2e7d32',
    'R_burden': '#6a1b9a', 'R_bias': '#6a1b9a', 'Klemens CT': '#6a1b9a', 'Genisleme': '#1565c0',
}
def col_of(name):
    for k, c in GRP.items():
        if name.startswith(k): return c
    return '#546e7a'

svg = Svg(1500, 720, 'pcb')
svg.text(750, 34, 'Kart yerleşimi / PCB 110 × 70 mm, ön yüzden bakış (1 mm = 8 birim)', 24, INK, 'middle', '700')

# ---- kart zemini, 230 V bölgesi, sınır
svg.add('<defs><pattern id="pcb" width="16" height="16" patternUnits="userSpaceOnUse"><rect width="16" height="16" fill="#e8f5e9"/><circle cx="8" cy="8" r="1" fill="#a5d6a7"/></pattern>'
        '<pattern id="hv" width="10" height="10" patternTransform="rotate(45)" patternUnits="userSpaceOnUse"><line x1="0" y1="0" x2="0" y2="10" stroke="#ef6c00" stroke-width="1.5" opacity="0.5"/></pattern></defs>')
svg.add('<rect x="%d" y="%d" width="880" height="560" rx="16" fill="url(#pcb)"/>' % (OX, OY))
svg.add('<rect x="%d" y="%d" width="224" height="560" rx="16" fill="url(#hv)"/>' % (OX + 656, OY))
svg.add('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#ef6c00" stroke-width="3" stroke-dasharray="10 5"/>' % (OX + 656, OY, OX + 656, OY + 560))
x, y = px(96, 40)
svg.text(x, y, '230 V BİRİNCİL BÖLGE', 11, '#c62828', 'middle', '700')
svg.text(x, y + 16, 'izolasyon sınırı ≥ 6 mm creepage', 10, '#607d8b', 'middle')
svg.text(x, y + 30, 'alt yarıda frezelenmiş yarık (slot)', 10, '#607d8b', 'middle')
svg.text(x, y + 44, 'RAC05 bariyeri sınırın üstünde', 10, '#607d8b', 'middle')
# IR pencere ekseni Ø15 keepout (kutu penceresi) / çizim notu
x, y = px(55, 37.5)
svg.add('<circle cx="%g" cy="%g" r="60" fill="none" stroke="#c62828" stroke-width="1.5"/>' % (x, y))
# M3 keepout Ø5,5
for (mx, my) in [(7, 7), (103, 7), (7, 63), (103, 63)]:
    x, y = px(mx, my)
    svg.add('<circle cx="%g" cy="%g" r="22" fill="none" stroke="#78909c" stroke-width="1"/>' % (x, y))
svg.text(OX + 90, OY + 20, 'M3 × 4 (7, 7) / kutu dikmeleri Ø6', 10, '#607d8b')

# ---- arka yüz parçaları (kart üzerinden, kesikli)
g = ['<g fill="none" stroke-width="1.8" stroke-dasharray="6 3" stroke-linejoin="round">']
for pl in V['arka_thru']:
    pts = ' '.join('%g,%g' % (OX + (p[0] - ORIG[0]) * S, OY + (p[1] - ORIG[1]) * S) for p in pl['pts'])
    g.append('<polyline points="%s" stroke="%s"/>' % (pts, col_of(pl['body'])))
g.append('</g>')
svg.add('\n'.join(g))
# ---- ön yüz (düz)
svg.add('<circle cx="%g" cy="%g" r="36" fill="#37474f"/>' % px(55, 37.5))
svg.add('<circle cx="%g" cy="%g" r="14" fill="#90a4ae"/>' % px(55, 37.5))
svg.add('<rect x="%g" y="%g" width="20" height="20" fill="#1565c0"/>' % (px(7, 31)[0] - 10, px(7, 31)[1] - 10))
svg.add('<circle cx="%g" cy="%g" r="8" fill="#43a047"/>' % px(25, 65))
svg.view(V['on'], OX, OY, S, ORIG, stroke=INK, sw=2)

# ---- etiketler
BG = '#e8f5e9'   # kart zemini: etiket arka planı (halo)
L = lambda x, y, t, size=11, fill='#37474f', anchor='start', w=None: svg.text(x, y, t, size, fill, anchor, w, halo=BG)
SUB = '#607d8b'
x, y = px(52, 50.5)
L(x, y - 4, 'MLX90640ESF-BAA-000-TU', 11, '#37474f', 'middle', '700')
L(x, y + 10, 'TO-39 Ø9,3 / I²C 0x33 / merkez (55, 37,5) mm', 10, SUB, 'middle')
L(x, y + 24, 'Ø15 kapak penceresi izdüşümü / ön yüz boş', 10, '#c62828', 'middle')
x, y = px(29, 40.6)
L(x, y, '2× 4,7k pull-up + 100 nF', 10, SUB)
x, y = px(7, 31)
L(x + 50, y - 12, 'SHT31-DIS-B', 11, '#37474f', 'start', '700')
L(x + 50, y + 2, 'I²C 0x44 / vent hizası', 10, SUB)
L(x + 50, y + 16, 'ısı kaynaklarından uzak', 10, SUB)
svg.add('<path d="M%g %g h72 v72" fill="none" stroke="#1565c0" stroke-width="2"/>' % (x - 44, y - 44))
L(x - 44, y - 50, 'ısı yarığı (kart yalıtımı)', 10, '#1565c0')
x, y = px(25, 65)
L(x + 12, y - 6, 'durum LED', 10, SUB)
x, y = px(29, 54.4)
L(x, y, 'EN: 10k + 1µF + reset', 10, SUB)
x, y = px(19, 50.4)
L(x, y - 6, 'ESP32-S3-WROOM-1U-N8', 11, '#37474f', 'middle', '700')
L(x, y + 8, '18 × 19,2 / arka yüz', 10, SUB, 'middle')
L(x, y + 22, 'U.FL kenarda → kutu SMA', 10, SUB, 'middle')
x, y = px(72.5, 57.5)
L(x, y - 6, 'RECOM RAC05-05SK/277', 11, '#ad1457', 'middle', '700')
L(x, y + 8, '31,7 × 26,7 × 21,8 / arka yüz', 10, SUB, 'middle')
L(x, y + 22, 'sol 5 V ikincil / sağ 230 V birincil', 10, SUB, 'middle')
L(px(65, 66)[0], px(65, 66)[1], '+5V / GND', 10, SUB); L(px(95, 66)[0], px(95, 66)[1], 'L / N / PE', 10, SUB, 'end')
x, y = px(91, 23.6); L(x, y + 30, 'F1 (SMD)', 10, SUB, 'middle')
x, y = px(100, 23.5); L(x, y + 44, 'MOV Ø7', 10, SUB, 'middle')
x, y = px(91.6, 4.5); L(x, y - 42, '230 V klemens', 11, '#37474f', 'middle'); L(x, y - 57, '3 kutup L/N/PE, 5,08 mm', 10, SUB, 'middle')
x, y = px(73.25, 37.5); L(x, y - 2, 'LDO', 9, SUB, 'middle'); L(x, y + 9, '3,3 V', 9, SUB, 'middle')
x, y = px(78.9, 36.3); L(x, y + 17, 'D1 (OR) üst / D2 alt', 9, SUB, 'middle')
x, y = px(62.5, 45); svg.leader(x, y, px(65, 48.5)[0], px(65, 48.5)[1], ['R_şarj 22 Ω'], 10, SUB, 'start', dot=False, halo=BG)
x, y = px(77.5, 29.25); L(x - 6, y + 4, 'bölücü→GPIO1', 10, SUB, 'end')
x, y = px(66.5, 17.75)
L(x, y - 4, '2× süperkapasitör seri', 11, '#f57f17', 'middle', '700')
L(x, y + 10, 'Eaton HV1030 Ø10,5 × 31,5 yatık / arka yüz', 10, SUB, 'middle')
L(x, y + 24, '10 F 2,7 V ×2 → 5 F 4,6 V / 02-bom §2.5', 10, SUB, 'middle')
x, y = px(43.5, 33); svg.leader(x, y, px(38, 30)[0], px(38, 30)[1], ['boost U7 + L', 'çıkış 4,6 V → D2'], 10, SUB, 'end', dot=False, halo=BG)
x, y = px(48, 27.75); L(x - 6, y + 4, 'dengeleme 2×', 10, SUB, 'end')
x, y = px(41.25, 18); L(x - 6, y, 'MAX3485', 10, SUB, 'end')
x, y = px(48, 16); L(x + 8, y + 4, '120 Ω', 10, SUB)
x, y = px(5, 18.6); L(x, y - 70, 'RS-485', 11, '#2e7d32', 'middle'); L(x, y + 54, 'A/B/GND', 10, '#2e7d32', 'middle')
x, y = px(32, 14.5); L(x, y - 12, '4× R_burden + bias (3V3/2)', 10, '#6a1b9a', 'middle')
x, y = px(39, 7.5); L(x, y - 14, 'CT klemens 8 kutup, 3,5 mm / L1 L2 L3 N', 11, '#37474f', 'middle')
x, y = px(17.5, 8.75); L(x, y + 36, 'genişleme 2×5 / §7.1', 11, '#1565c0', 'middle'); L(x, y + 50, 'I²C/UART/3V3/5V/GND', 9, SUB, 'middle')

# ---- ölçüler
svg.dim_h(OX, OX + 880, OY + 590, '110 mm', size=12)
svg.dim_v(OX - 30, OY, OY + 560, '70 mm', size=12)

# ---- izometrik küçük görünüş (kartın altında sağda) / notlar panelinin altına sığmaz; sağ panel içine
NX, NY = 1000, 80
svg.add('<rect x="%d" y="%d" width="460" height="560" fill="#fff" stroke="#90a4ae" stroke-width="2"/>' % (NX, NY))
svg.text(NX + 16, NY + 28, 'Yerleşim kuralları', 13, INK, weight='700')
notes = [
    ('Bakış:', ' ön yüz = kutu penceresine bakan taraf.'),
    (None, 'Düz = ön yüz parçası, kesikli = arka yüz (kart üzerinden);'),
    (None, 'ince düz halka = boş bırakılacak alan (IR ekseni, M3 çevresi).'),
    ('Ön yüz', ' (pencere ile PCB arası 6 mm): yalnız alçak'),
    (None, 'parçalar / MLX90640 (TO-39, 6 mm), SHT31, LED,'),
    (None, 'pasifler. IR pencere ekseninde Ø15 boş alan.'),
    ('Arka yüz', ' (39 mm derinlik): ESP32 modülü, RAC05 (21,8 mm),'),
    (None, '2× süperkap yatık (Ø10,5 × 31,5) + boost, klemensler,'),
    (None, 'MAX3485. Kablolar kutunun alt yüzünden, klemens sırasıyla girer.'),
    ('Güvenlik:', ' 230 V birincil bölge sağ şeritte (x ≥ 82),'),
    (None, '≥ 6 mm creepage + alt yarıda 1 mm yarık (Y 0–40);'),
    (None, 'RAC05\'in izolasyon bariyeri sınırı köprüler.'),
    (None, 'Sigorta + MOV birincil tarafta.'),
    ('Isı:', ' SHT31 kartın sol kenarında, RAC05 ve LDO\'dan en'),
    (None, 'uzak noktada; çevresinde ısı yarığı. MLX90640 kendi'),
    (None, 'sıcaklığını ölçer (Ta), ısıdan uzak.'),
    ('RF:', ' ESP32 kart kenarında, U.FL pigtail kısa; dahili'),
    (None, 'anten kullanılmadığı için keepout yok.'),
    ('Katman:', ' 2 katman, alt katman GND dolgu; birincil'),
    (None, 'bölgede dolgu yok (yalıtım).'),
    ('Montaj:', ' 4× M3 delik (7, 7) vb. → kutu dikmeleri Ø6, kutu (12, 12);'),
    (None, 'kart kutuda (5, 5) ofsetli, ön yüzü kapaktan 5 mm geride.'),
    ('Konum uyumu:', ' MLX (55, 37,5) / SHT31 (7, 31) / LED (25, 65)'),
    (None, '[model, Y yukarı] = kutu koordinatı − 5 mm.'),
]
y = NY + 56
for i, (b, t) in enumerate(notes):
    if b: svg.add('<text x="%d" y="%d" font-size="12" fill="#37474f"><tspan font-weight="700">%s</tspan>%s</text>' % (NX + 16, y, b, t))
    else: svg.text(NX + 16, y, t, 12, '#37474f')
    y += 16 if (i + 1 < len(notes) and notes[i + 1][0] is None) else 22
svg.text(NX + 16, NY + 526, 'Kaynak: Fusion 360 GridUp-PCB.f3d / üretim çizimi değildir (§1.4).', 10, SUB)
svg.text(NX + 16, NY + 542, 'Pasif değerler 03-baglanti-semasi ile aynı.', 10, SUB)

comment = """    PCB / kart yerleşimi / (T2 "kart yapısı"). Ölçek 1 mm = 8 birim, kart 110 × 70 × 1,6 mm, köşe R2.
    Kaynak: Fusion 360 modeli GridUp-PCB.f3d (thozoz hub / Default Project). Geometri modelden API ile projeksiyon:
    düz çizgi = ön yüz (Z+ yönünden bakış), kesikli = arka yüz parçaları kart üzerinden görünür (aynı bakış, kart gizlenmiş).
    Koordinat: SVG (x, y aşağı) = model (X, 70 − Y). Kart kutu içinde (5, 5) mm ofsetli → PCB koordinatı = kutu koordinatı − 5 mm.
    Ön yüz (Z 1,6 →): MLX90640 TO-39 Ø9,3 × 6 (datasheet Ø9,30 ±0,15 × 5,70 ±0,30 + bacak, maks. zarf) merkez (55, 37,5) [kutu IR pencere (60, 42,5)] / SHT31 2,5 × 2,5 (7, 31) [kutu vent (12, 36)] /
      LED Ø3 (25, 65) [kutu (30, 70)] / pull-up + 100 nF (37,5, 42–46,5) / EN RC (29, 50–52,5) + reset 3 × 3 (32–35, 49,75–52,75).
    Arka yüz (Z 0 ←): ESP32-S3-WROOM-1U 18 × 19,2 × 3,2 (10–28, 40,8–60) / RAC05-05SK/277 31,7 × 26,7 × 21,8 (64–95,7, 42–68,7) /
      F1 (88–94,1, 22,25–25) / MOV 7 × 4 × 8 (96,5–103,5, 21,5–25,5) / 230 V klemens 3p 5,08 (84–99,25, 0,5–8,5) /
      LDO AP7361C SOT-223 (70–76,5, 34–41) / D1 (76,75–81, 39–41,65) / D2 (76,75–81, 35–37,65) / R_şarj (60,5–62,5, 44,5–45,5) / bölücü (77,5–79,5, 28–30,5) /
      boost U7 (43,5–46, 36–38) + L 3×3 (43,5–46,5, 31,5–34,5) / dengeleme R (48–50, 26–29,5) /
      2× süperkap Eaton HV1030 Ø10,5 × 31,5 yatık, eksen Y, merkezler (61, 17,75) (72, 17,75), Y 2–33,5 / MAX3485 SOIC-8 (41,25–46,25, 14–20) / 120 Ω (47,5–48,5, 15–17) /
      RS-485 klemens 3p (1–9, 11–26,25) / R_burden ×4 (25–36, 14–15) + bias (37–39, 13–15) / CT klemens 8p 3,5 (25–53, 0,5–7,5) / genişleme 2×5 (11–24, 6,25–11,25).
    Kart: M3 Ø3,2 (7, 7) (103, 7) (7, 63) (103, 63) → kutu dikmeleri Ø6 kutu (12, 12) vb.; köşelerde Ø8 boşluk (kapak vida direği Ø7); izolasyon yarığı 1 mm (81,5–82,5, Y 0–40); 230 V bölgesi X ≥ 82.
    Üretim çizimi değildir (§1.4)."""
n = svg.write(OUT, comment)
print('written', OUT, n)
