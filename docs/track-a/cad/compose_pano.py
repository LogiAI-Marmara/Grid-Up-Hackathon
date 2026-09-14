import json, sys, os, math
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from svgkit import Svg, INK, DIM, MUTED

V = json.load(open(os.path.join(HERE, 'views', 'pano-views.json')))
OUT = sys.argv[1]
S = 1.0
ORANGE = '#e65100'; ORANGE2 = '#ef6c00'; GREEN = '#2e7d32'; BLUE = '#0d47a1'; GREY = '#546e7a'

# model gerçekleri (Fusion GridUp-Pano)
SENS_Z = -53.0            # IR pencere dış yüzü
IRX, IRY = 650.0, 692.5   # IR pencere merkezi (model, Y yukarı)
BACK_Z = -430.0           # montaj plakası ön yüzü
NH_Z = -208.5             # NH ayırıcı ön yüzleri: plaka −430 + s 80 (izolatör 50 + bara grubu 30) + 141,5 (Eaton EBV 00)
D_BACK = SENS_Z - BACK_Z  # 377
D_NH = SENS_Z - NH_Z      # 155.5
def fov(d): return 2*d*math.tan(math.radians(55)), 2*d*math.tan(math.radians(37.5))
WB, HB = fov(D_BACK); WN, HN = fov(D_NH)

svg = Svg(2500, 1830, 'pano')
svg.header = svg.header.replace('viewBox="0 0 2500 1830"', 'viewBox="-90 -90 2500 1830"')
svg.add('<defs>'
        '<pattern id="hatch" width="10" height="10" patternTransform="rotate(45)" patternUnits="userSpaceOnUse"><line x1="0" y1="0" x2="0" y2="10" stroke="#ef6c00" stroke-width="1.5" opacity="0.5"/></pattern>'
        '<pattern id="cut" width="12" height="12" patternTransform="rotate(45)" patternUnits="userSpaceOnUse"><line x1="0" y1="0" x2="0" y2="12" stroke="#78909c" stroke-width="2"/></pattern>'
        '<marker id="arw-red" markerWidth="10" markerHeight="10" refX="6" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 z" fill="#c62828"/></marker>'
        '</defs>')
svg.text(1160, -45, 'Modül yerleşimi ve termal görüş hattı — 1600 kVA AG pano (TEDAŞ-MLZ/2003-06.B, EK-II/14)', 34, INK, 'middle', '700')

def col_of(n):
    if n.startswith('NH') or n.startswith('Klemens'): return ORANGE
    if n.startswith('GridUp-'): return GREEN
    if n.startswith('Pano') or n == 'Kapak': return '#37474f'
    return '#78909c'

# ================= SOL: ÖNDEN GÖRÜNÜŞ =================
svg.add('<g id="on-gorunus">')
svg.text(800, -8, 'ÖNDEN GÖRÜNÜŞ — kapak açık (A × B = 1600 × 1500 mm)', 24, DIM, 'middle', '700')
svg.add('<rect x="0" y="0" width="1600" height="1500" fill="#fafafa"/>')
# bölgeler (TEDAŞ çiziminden, ±30 mm)
svg.add('<rect x="40" y="50" width="1520" height="415" fill="#eceff1" stroke="#90a4ae" stroke-width="2"/>')
svg.text(60, 84, 'Üst bölüm — kumanda / haberleşme (≈50–465 mm)', 21, GREY)
svg.add('<rect x="1290" y="530" width="270" height="540" fill="#eceff1" stroke="#90a4ae" stroke-width="2"/>')
svg.text(1425, 1040, 'ölçü / kontrol sütunu', 15, GREY, 'middle')
svg.add('<rect x="50" y="545" width="1200" height="530" fill="url(#hatch)" stroke="#ef6c00" stroke-width="3"/>')
svg.text(60, 493, 'KRİTİK BÖLGE — NH sigortalı yük ayırıcı sıraları + çıkış klemensleri (≈560–1060 mm)', 21, ORANGE, weight='700')
svg.add('<rect x="40" y="1080" width="1520" height="380" fill="#f5f5f5" stroke="#90a4ae" stroke-width="2" stroke-dasharray="6 4"/>')
svg.text(700, 1300, 'Alt bölüm — kablo yönlendirme boşluğu', 21, '#607d8b', 'middle')
svg.add('<line x1="300" y1="1065" x2="300" y2="1455" stroke="#455a64" stroke-width="2" marker-start="url(#dim)" marker-end="url(#dim)"/>')
svg.text(312, 1265, '"En az 400 mm" (şartname)', 17, DIM)
# cihaz dolguları (bilinen bloklar)
for (x1, y1, x2, y2) in [(90,1050,240,1200),(1290,1050,1490,1140),(1320,790,1530,940),(1320,630,1530,740)]:
    svg.add('<rect x="%g" y="%g" width="%g" height="%g" fill="#cfd8dc"/>' % (x1, 1500-y2, x2-x1, y2-y1))
for (y1, y2) in [(820,940),(685,805),(550,670)]:
    for k in range(12):
        x1 = 50 + k*100 + 8
        svg.add('<rect x="%g" y="%g" width="84" height="%g" fill="#fff3e0"/>' % (x1, 1500-y2, y2-y1))
svg.add('<rect x="50" y="%g" width="1200" height="55" fill="#fff3e0"/>' % (1500-495))
# modelden kenarlar
cols = {n: col_of(n) for n in {pl['body'] for pl in V['on']}}
svg.view(V['on'], 0, 0, S, (0, -1500), stroke='#37474f', sw=2, colors=cols)
svg.add('<rect x="0" y="0" width="1600" height="1500" fill="none" stroke="#263238" stroke-width="6"/>')
svg.text(165, 368, 'Sbt.', 18, '#37474f', 'middle'); svg.text(165, 392, 'Komp.', 18, '#37474f', 'middle')
svg.text(1390, 412, 'Modem', 19, '#37474f', 'middle')
svg.add('<rect x="1280" y="350" width="220" height="110" fill="none" stroke="#2e7d32" stroke-width="3" stroke-dasharray="8 5"/>')
svg.text(1390, 335, 'emsal: iç ihtiyaçtan beslenen cihaz', 15, GREEN, 'middle', style='italic')
svg.text(1425, 630, 'T1 ölçü', 17, '#37474f', 'middle'); svg.text(1425, 654, '(enerji analizörü)', 17, '#37474f', 'middle')
svg.text(1425, 822, 'kontrol', 17, '#37474f', 'middle')
for i, y in enumerate([625, 760, 895]): svg.text(1262, y, 'sıra %d' % (i+1), 15, '#bf360c')
svg.text(1262, 1037, 'klemens', 15, '#bf360c')
# TERMAL KAPSAMA — modelden: sensör yüzü → montaj plakası D_BACK, → NH yüzü D_NH
cx, cy = IRX, 1500 - IRY
svg.add('<rect x="%g" y="%g" width="%g" height="%g" fill="#1565c0" opacity="0.13"/>' % (cx-WB/2, cy-HB/2, WB, HB))
svg.add('<rect x="%g" y="%g" width="%g" height="%g" fill="none" stroke="#0d47a1" stroke-width="4" stroke-dasharray="14 8"/>' % (cx-WB/2, cy-HB/2, WB, HB))
svg.add('<rect x="%g" y="%g" width="%g" height="%g" fill="none" stroke="#0d47a1" stroke-width="2.5" stroke-dasharray="6 6"/>' % (cx-WN/2, cy-HN/2, WN, HN))
svg.add('<rect x="560" y="1128" width="620" height="58" fill="#fff" opacity="0.92"/>')
svg.text(870, 1150, 'termal görüş alanı: %d × %d mm montaj plakasında (110°×75° @ %d mm)' % (round(WB), round(HB), round(D_BACK)), 19, BLUE, 'middle', '700')
svg.text(870, 1175, 'iç kesikli: %d × %d mm NH ayırıcı yüzeyinde (@ %d mm)' % (round(WN), round(HN), round(D_NH)), 16, BLUE, 'middle')
# MODÜL — kapak iç yüzündeki konumun izdüşümü (modelden, kesikli)
svg.add('<rect x="590" y="%g" width="120" height="80" rx="6" fill="#2e7d32" opacity="0.18"/>' % (1500-730))
g = ['<g fill="none" stroke="#1b5e20" stroke-width="2.5" stroke-dasharray="9 5">']
for pl in V['modul']:
    if not pl['body'].startswith('GridUp-Kutu/'): continue
    pts = ' '.join('%g,%g' % (p[0], p[1] + 1500) for p in pl['pts'])
    g.append('<polyline points="%s"/>' % pts)
g.append('</g>')
svg.add('\n'.join(g))
svg.add('<line x1="%g" y1="%g" x2="%g" y2="%g" stroke="#1b5e20" stroke-width="2"/><line x1="%g" y1="%g" x2="%g" y2="%g" stroke="#1b5e20" stroke-width="2"/>' % (cx-25, cy, cx+25, cy, cx, cy-25, cx, cy+25))
svg.add('<rect x="715" y="765" width="360" height="92" fill="#fff" opacity="0.92" stroke="#2e7d32" stroke-width="1.5"/>')
svg.text(728, 790, 'MODÜL — kapak iç yüzünde', 18, '#1b5e20', weight='700')
svg.text(728, 814, 'kutu 120 × 80, X 590–710 / IR merkezi (%g, %g) mm' % (IRX, 1500-IRY), 15, GREEN)
svg.text(728, 836, 'bakış: sayfaya dik (→ yan kesit) / klemense DİK', 15, GREEN)
svg.text(728, 852, 'kesikli çizgi = ön düzlemde, kapağa bağlı (model: GridUp-Pano.f3d)', 13, '#558b2f', style='italic')
svg.add('<line x1="-40" y1="0" x2="-40" y2="1500" stroke="#455a64" stroke-width="2" marker-start="url(#dim)" marker-end="url(#dim)"/>')
svg.text(-50, 750, 'B = 1500 mm', 22, DIM, 'middle', rotate=-90)
svg.add('<line x1="0" y1="1545" x2="1600" y2="1545" stroke="#455a64" stroke-width="2" marker-start="url(#dim)" marker-end="url(#dim)"/>')
svg.text(800, 1580, 'A = 1600 mm', 22, DIM, 'middle')
svg.add('</g>')

# ================= SAĞ: YAN KESİT (X = 650) =================
OX = 1810
svg.add('<g id="yan-kesit" transform="translate(%d,0)">' % OX)
svg.text(240, -8, 'YAN KESİT — X = 650 (C × B = 450 × 1500 mm)', 24, DIM, 'middle', '700')
svg.add('<rect x="-22" y="0" width="472" height="1500" fill="#fafafa"/>')
# kesit poligonları: x = -Z, y = 1500 - Y
cuts = [pl for pl in V['kesit'] if pl['kind'] == 'cut']
rest = [pl for pl in V['kesit'] if pl['kind'] != 'cut']
for pl in cuts:
    pts = ' '.join('%g,%g' % (p[0], p[1] + 1500) for p in pl['pts'])
    n = pl['body']
    if n.startswith('Pano') or n == 'Kapak':
        svg.add('<polygon points="%s" fill="url(#cut)" stroke="#263238" stroke-width="2"/>' % pts)
    else:
        svg.add('<polygon points="%s" fill="%s" fill-opacity="0.35" stroke="%s" stroke-width="2"/>' % (pts, col_of(n), col_of(n)))
# düzlem arkasındaki cihazlar: dolgu
for name in sorted({pl['body'] for pl in rest if not (pl['body'].startswith('Pano') or pl['body'] == 'Kapak')}):
    pts = [q for pl in rest if pl['body'] == name for q in pl['pts']]
    x0, y0, x1, y1 = min(q[0] for q in pts), min(q[1] for q in pts), max(q[0] for q in pts), max(q[1] for q in pts)
    if x1-x0 < 0.5 or y1-y0 < 0.5: continue
    svg.add('<rect x="%g" y="%g" width="%g" height="%g" fill="%s" fill-opacity="0.15"/>' % (x0, y0+1500, x1-x0, y1-y0, col_of(name)))
rcol = {n: col_of(n) for n in {pl['body'] for pl in rest}}
svg.view(rest, 0, 0, S, (0, -1500), stroke='#78909c', sw=1.5, colors=rcol)
svg.add('<rect x="-22" y="0" width="472" height="1500" fill="none" stroke="#263238" stroke-width="3"/>')
svg.text(420, 1478, 'montaj plakası (20 mm) ▸', 14, GREY, 'end')
svg.text(-6, 1400, 'ön kapak 22 mm (menteşe altta)', 15, '#37474f', rotate=-90)
svg.text(335, 1128, 'kritik bölge', 15, ORANGE, 'end', '700')
svg.text(370, 380, 'kumanda', 14, GREY, 'end')
sx, sy = -SENS_Z, 1500 - IRY
# görüş konisi (modelden: apex sensör yüzü, 75° dikey)
hb = D_BACK*math.tan(math.radians(37.5)); hn = D_NH*math.tan(math.radians(37.5))
svg.add('<polygon points="%g,%g %g,%g %g,%g" fill="#1565c0" opacity="0.16"/>' % (sx, sy, 430, sy-hb, 430, sy+hb))
svg.add('<polygon points="%g,%g %g,%g %g,%g" fill="none" stroke="#0d47a1" stroke-width="3" stroke-dasharray="12 7"/>' % (sx, sy, 430, sy-hb, 430, sy+hb))
# modül etiketi
sx, sy = -SENS_Z, 1500 - IRY
svg.text(30, sy - 55, 'MODÜL', 14, '#1b5e20', 'middle', '700')
svg.text(2, sy - 40, 'kutu 50 + klips 5 mm', 12, '#1b5e20')
svg.add('<line x1="%g" y1="%g" x2="430" y2="%g" stroke="#0d47a1" stroke-width="1.5" stroke-dasharray="4 6"/>' % (sx, sy, sy))
svg.add('<line x1="%g" y1="%g" x2="%g" y2="%g" stroke="#0d47a1" stroke-width="2" stroke-dasharray="3 5"/>' % (-NH_Z, sy-hn, -NH_Z, sy+hn))
svg.text(235, sy-12, '75° (dikey)', 18, BLUE, 'middle', '700')
svg.text(225, 1165, 'plakada %d / NH yüzünde %d mm yükseklik' % (round(2*hb), round(2*hn)), 15, BLUE, 'middle')
svg.add('<line x1="%g" y1="%g" x2="%g" y2="%g" stroke="#c62828" stroke-width="5" marker-end="url(#arw-red)"/>' % (sx+10, sy+35, sx+115, sy+35))
svg.text(sx+62, sy+65, 'bakış yönü', 18, '#c62828', 'middle', '700')
svg.add('<line x1="%g" y1="1230" x2="430" y2="1230" stroke="#455a64" stroke-width="2" marker-start="url(#dim)" marker-end="url(#dim)"/>' % sx)
svg.text((sx+430)/2, 1220, 'sensör → plaka %d mm / NH yüzü %d mm' % (round(D_BACK), round(D_NH)), 16, DIM, 'middle')
svg.add('<line x1="0" y1="1545" x2="450" y2="1545" stroke="#455a64" stroke-width="2" marker-start="url(#dim)" marker-end="url(#dim)"/>')
svg.text(225, 1580, 'C = 450 mm', 22, DIM, 'middle')
svg.add('</g>')

# ================= LEJANT =================
svg.add('<g id="lejant" transform="translate(0,1610)">')
svg.add('<rect x="0" y="0" width="2260" height="110" fill="#fff" stroke="#90a4ae" stroke-width="2"/>')
svg.text(16, 30, 'Lejant', 19, INK, weight='700')
svg.add('<rect x="16" y="50" width="30" height="18" rx="3" fill="#2e7d32" fill-opacity="0.3" stroke="#1b5e20" stroke-dasharray="6 3"/>')
svg.text(56, 65, 'Modül — kapak iç yüzünde (önden görünüşte izdüşüm, kesikli; yan kesitte gövde + PCB)', 17, '#37474f')
svg.add('<rect x="16" y="78" width="30" height="18" fill="#1565c0" opacity="0.3" stroke="#0d47a1" stroke-dasharray="6 3"/>')
svg.text(56, 93, 'Termal görüş alanı (110°×75°, MLX90640 geniş açı) — önde kapsama dikdörtgeni (dış: plaka, iç: NH yüzü), yanda koni', 17, '#37474f')
svg.add('<rect x="1000" y="50" width="30" height="18" fill="#fff3e0" stroke="#e65100"/>')
svg.text(1040, 65, 'NH sigortalı yük ayırıcı sıraları + çıkış klemensleri (kritik bölge)', 17, '#37474f')
svg.add('<rect x="1000" y="78" width="30" height="18" fill="none" stroke="#2e7d32" stroke-width="2" stroke-dasharray="6 3"/>')
svg.text(1040, 93, 'Panoda hâlihazırda bulunan iç ihtiyaç beslemeli cihaz (emsal: Modem)', 17, '#37474f')
svg.text(1660, 65, 'Bölge sınırları TEDAŞ çiziminden orantıyla (±30 mm); kaynak EK-II/14, s. 51.', 15, '#607d8b')
svg.text(1660, 93, '1 birim = 1 mm. Geometri: Fusion 360 GridUp-Pano.f3d (kutu + PCB montajı dahil).', 15, '#607d8b')
svg.add('</g>')

comment = """    Modül yerleşimi ve termal görüş hattı — TEDAŞ-MLZ/2003-06.B, EK-II/14 üzerine.
    Kaynak: Fusion 360 modeli GridUp-Pano.f3d (pano gövdesi 1600 × 1500 × 450, sac 2 mm, montaj plakası 20 mm,
    kapak 22 mm, cihaz blokları; GridUp-Kutu-Montaj kapak iç yüzüne 180° döndürülerek yerleştirildi).
    Görünüşler modelden API ile projeksiyon; kesit X = 650 düzleminden (IR ekseni). Ölçek: 1 birim = 1 mm.
    Model koordinatı: X sağ, Y yukarı, Z öne (kapak iç yüzü Z = 0, montaj plakası ön yüzü Z = −430, NH ön yüzü Z = −360).
    Modül: kutu X 590–710, Y 650–730 (merkez 650, 690), DIN klips Z 0..−5, gövde Z −5..−51, IR pencere dış yüzü Z ≈ −53;
      IR pencere merkezi (650, 692,5) → önden görünüşte (650, 807,5) [y aşağı].
    NH ayırıcı derinliği 141,5 mm bara ön yüzünden (Eaton EBV 00 dikey yük ayırıcı, Pub. 10275 s.5).
    Bara: 3 yatay faz barası, 185 mm adım (şartname Tablo 8 DSYA); kesit 1600 kVA için 2×(100×10) mm² (EK-I/8 Tablo 8):
      faz başına iki bara + 10 mm ara parça = 30 mm grup. Bara standoff'u (s) şartnamede mm olarak verilmemiştir
      (TEDAŞ EK-II/14 yalnız dış siluet, §2.2.10 "mesnet izolatörleri" der); mesnet izolatörü 50 mm seçildi (Socomec
      Busbar Supports kataloğu, L: 33–70 mm / UL standoff 40–71 mm) → s = 50 + 30 = 80 mm, bara ön yüzü Z = −350,
      NH ön yüzü Z = −208,5. İzolatör yüksekliği bir SEÇİMDİR, şartname dayatmıyor; farklı seçim kapsamayı değiştirir.
    Termal kapsama (110° × 75°): sensör → montaj plakası %d mm → %d × %d mm; sensör → NH yüzü %.1f mm → %d × %d mm.
      (Karar kaydı §7.1: "~40 cm, kabaca 114 × 61 cm" — eski kroki 35 mm modül derinliğiyle 395 mm / 1128 × 606 almıştı
       [1143 × 614 = 400 mm]; kutu 50 mm + klips 5 mm olunca mesafe 377 mm'e iner.)
    Bölge sınırları TEDAŞ çiziminden orantıyla ölçülmüştür (±30 mm).""" % (round(D_BACK), round(WB), round(HB), D_NH, round(WN), round(HN))
n = svg.write(OUT, comment)
print('written', OUT, n, 'FOV', round(WB), round(HB), '@', round(D_BACK), '/', round(WN), round(HN), '@', round(D_NH))
