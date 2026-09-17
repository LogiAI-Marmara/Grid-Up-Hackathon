import json, sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from svgkit import Svg, INK, DIM, MUTED

V = json.load(open(os.path.join(HERE, 'views', 'kutu-views.json')))
M = json.load(open(os.path.join(HERE, 'views', 'montaj-views.json')))
OUT = sys.argv[1]
S = 4
RED = '#c62828'; GREY = '#546e7a'; DARK = '#37474f'
COL = {'IR pencere': RED}
BOXBG = '<rect x="0" y="0" width="480" height="320" rx="16" fill="#eceff1"/>'
GRP = {'ESP32': '#546e7a', 'RAC05': '#ad1457', 'F1': '#ef6c00', 'MOV': '#ef6c00', 'Klemens 230V': '#ef6c00',
       'LDO': '#ad1457', 'D1': '#ad1457', 'D2': '#ad1457', 'R_sarj': '#ad1457', 'Bolucu': '#ad1457',
       'Superkap': '#f9a825', 'Boost': '#ad1457', 'L_boost': '#ad1457', 'R_bal': '#f9a825', 'MAX3485': '#2e7d32', 'R120': '#2e7d32', 'Klemens RS-485': '#2e7d32',
       'R_burden': '#6a1b9a', 'R_bias': '#6a1b9a', 'Klemens CT': '#6a1b9a', 'Genisleme': '#1565c0',
       'MLX90640': '#37474f', 'SHT31': '#1565c0', 'LED': '#43a047', 'PCB': '#2e7d32'}
def col_of(name):
    n = name.split('/')[-1]
    for k, c in GRP.items():
        if n.startswith(k): return c
    return '#546e7a'

svg = Svg(1720, 1400, 'kutu')
svg.add('<defs><pattern id="hatch" width="8" height="8" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">'
        '<line x1="0" y1="0" x2="0" y2="8" stroke="#78909c" stroke-width="1.5"/></pattern>'
        '<pattern id="pcbp" width="12" height="12" patternUnits="userSpaceOnUse"><rect width="12" height="12" fill="#e8f5e9"/><circle cx="6" cy="6" r="1" fill="#a5d6a7"/></pattern></defs>')
svg.text(860, 38, 'Modül kutusu / teknik kroki (120 × 80 × 50 mm, IP54, 1 mm = 4 birim)', 30, INK, 'middle', '700')

# ---------- A / ÖN YÜZ ----------
ox, oy = 60, 100
svg.text(ox + 240, oy - 14, 'A / ÖN YÜZ / klemenslere bakan yüz (120 × 80)', 20, DIM, 'middle', '700')
svg.view(V['on'], ox, oy, S, (0, -80), colors=COL, bg=BOXBG)
def A(x, y): return ox + x * S, oy + (80 - y) * S
x, y = A(60, 42.5)
svg.text(x, y + 68, 'IR geçirgen pencere Ø15', 15, RED, 'middle', '700')
svg.text(x, y + 86, '(standart cam/plastik DEĞİL / §4.4)', 13, RED, 'middle')
svg.text(x, y + 104, 'yükseltilmiş yuva Ø23, 3 mm konik pah / arkasında MLX90640 TO-39', 12, GREY, 'middle')
x, y = A(12, 36)
svg.text(x + 24, y - 4, 'membran vent M6', 13, DARK)
svg.text(x + 24, y + 12, '(SHT31 / IP54 korunur)', 12, GREY)
x, y = A(30, 70)
svg.text(x, y + 26, 'durum LED Ø3', 12, GREY, 'middle')
svg.text(ox + 240, oy + 300, 'kapak: 4 × M3 vida + conta (IP54)', 12, MUTED, 'middle')
svg.dim_h(ox, ox + 480, oy + 345, '120 mm', off=20)
svg.dim_v(ox - 22, oy, oy + 320, '80 mm', off=-16)

# ---------- B / YAN KESİT (X = 60, IR ekseni; −X'ten bakış, X ≥ 60 yarısı) ----------
ox, oy = 640, 100
svg.text(ox + 114, oy - 14, 'B / YAN KESİT / X = 60 (IR ekseni)', 20, DIM, 'middle', '700')
def B(z, y): return ox + (z + 5) * S, oy + (80 - y) * S
g = ['<g transform="translate(%g,%g)">' % (ox, oy)]
for pl in M['kesit']:
    if pl['kind'] != 'cut': continue
    pts = ' '.join('%g,%g' % ((p[0] + 5) * S, (p[1] + 80) * S) for p in pl['pts'])
    kutu = 'Kutu/' in pl['body']
    fill = 'url(#hatch)' if kutu else col_of(pl['body'])
    op = '' if kutu else ' fill-opacity="0.35"'
    g.append('<polygon points="%s" fill="%s"%s stroke="%s" stroke-width="2"/>' % (pts, fill, op, INK if kutu else col_of(pl['body'])))
g.append('</g>')
svg.add('\n'.join(g))
rest = [pl for pl in M['kesit'] if pl['kind'] != 'cut']
# düzlem arkasındaki PCB parçaları: gövde başına dolu kutu (grup rengi)
fills = []
for name in sorted({pl['body'] for pl in rest if pl['body'].startswith('GridUp-PCB/') and not pl['body'].endswith('/PCB')}):
    pts = [q for pl in rest if pl['body'] == name for q in pl['pts']]
    x0, y0, x1, y1 = min(q[0] for q in pts), min(q[1] for q in pts), max(q[0] for q in pts), max(q[1] for q in pts)
    if (x1 - x0) < 0.5 or (y1 - y0) < 0.5: continue
    fills.append('<rect x="%g" y="%g" width="%g" height="%g" rx="4" fill="%s" fill-opacity="0.18"/>' % (B(x0, 0)[0], oy + (y0 + 80) * S, (x1 - x0) * S, (y1 - y0) * S, col_of(name)))
svg.add(chr(10).join(fills))
# kutu dikmeleri (düzlem arkasında, X=108 / 115): açık gri dolgu
for (y0, y1) in [(9, 15), (65, 71)]:
    svg.add('<rect x="%g" y="%g" width="%g" height="%g" fill="#b0bec5" fill-opacity="0.5"/>' % (B(2, y1)[0], B(2, y1)[1], (39.4 - 2) * S, (y1 - y0) * S))
for (y0, y1) in [(2, 8.5), (71.5, 78)]:
    svg.add('<rect x="%g" y="%g" width="%g" height="%g" fill="#90a4ae" fill-opacity="0.5"/>' % (B(2, y1)[0], B(2, y1)[1], (46 - 2) * S, (y1 - y0) * S))
svg.text(B(20.7, 12)[0], B(20.7, 12)[1] + 4, 'PCB dikmesi Ø6 (M3)', 10, DARK, 'middle')
svg.text(B(24, 74.75)[0], B(24, 74.75)[1] + 4, 'kapak vida direği Ø7', 10, DARK, 'middle')
svg.text(B(20.7, 68)[0], B(20.7, 68)[1] + 4, 'PCB dikmesi Ø6', 10, DARK, 'middle')
rest_col = {n: (GREY if 'Kutu/' in n else col_of(n)) for n in {pl['body'] for pl in rest}}
svg.view(rest, ox, oy, S, (-5, -80), stroke=GREY, sw=1.6, colors=rest_col)
x, y = B(52, 42.5)
svg.add('<line x1="%g" y1="%g" x2="%g" y2="%g" stroke="%s" stroke-width="3" marker-start="url(#arr)"/>' % (x + 40, y, x + 10, y, RED))
svg.text(x + 24, y + 62, 'IR pencere', 12, RED, 'middle', rotate=-90)
x, y = B(41, 42.5); svg.leader(x - 2, y - 12, x - 30, y - 12, ['MLX90640 TO-39 Ø9,3', 'pencereye dayalı'], 11, DARK, 'end')
x, y = B(40.2, 5); svg.add('<circle cx="%g" cy="%g" r="2" fill="#2e7d32"/><line x1="%g" y1="%g" x2="%g" y2="%g" stroke="#2e7d32" stroke-width="1.2"/>' % (x, y, x, y, x, y + 24)); svg.text(x, y + 35, 'PCB 1,6', 10, '#2e7d32', 'middle')
x, y = B(34.15, 22.75); svg.text(x, y - 4, '2× süperkap.', 12, '#f57f17', 'middle'); svg.text(x, y + 12, 'Ø10,5 yatık', 11, '#f57f17', 'middle')
x, y = B(28.5, 60.35); svg.text(x, y - 2, 'RAC05', 12, '#ad1457', 'middle', '700'); svg.text(x, y + 12, '21,8 mm', 10, '#ad1457', 'middle')
x, y = B(-5, 41); svg.text(x - 10, y, 'DIN klips', 12, DARK, 'middle', rotate=-90)
svg.dim_h(B(0, 0)[0], B(50, 0)[0], oy + 345, '50 mm', off=20)
svg.text(ox + 114, oy + 392, 'bakış yönü → (klemenslere)', 12, MUTED, 'middle')

# ---------- E / ALT YÜZ ----------
ox, oy = 980, 100
svg.text(ox + 240, oy - 14, 'E / ALT YÜZ / kablo girişleri (120 × 50)', 20, DIM, 'middle', '700')
svg.view(V['alt'], ox, oy, S, (0, -52), colors=COL,
         bg='<rect x="0" y="8" width="480" height="200" rx="12" fill="#eceff1"/>')
def E(x, z): return ox + x * S, oy + (52 - z) * S
for (xm, d, t1, t2) in [(17.5, 12.5, 'RS-485', 'PG7 Ø12,5'), (40, 6.4, 'SMA panel', 'Ø6,4 → anten'),
                        (65, 12.5, 'CT ×4', 'PG7 Ø12,5'), (102.5, 12.5, '230 V AC', 'PG7 Ø12,5')]:
    x, y = E(xm, 23)
    r = d / 2 * S + 6
    svg.add('<g stroke="#455a64" stroke-width="0.8"><line x1="%g" y1="%g" x2="%g" y2="%g"/><line x1="%g" y1="%g" x2="%g" y2="%g"/></g>' % (x - r, y, x + r, y, x, y - r, x, y + r))
    svg.text(x, y + 52, t1, 13, DARK, 'middle', '700')
    svg.text(x, y + 68, t2, 12, GREY, 'middle')
svg.text(ox + 240, oy + 250, 'her giriş kendi klemensinin altında; 230 V sağ uçta, alçak gerilim girişlerinden ayrı', 11, MUTED, 'middle')
svg.text(ox + 240, oy + 266, 'RS-485: analizör / TVOC-2 · SMA: dış anten · CT: analizör yoksa', 11, MUTED, 'middle')
svg.text(ox + 240, oy + 282, 'kablolar menteşeye doğru iner (kıvrım payı, §4.7); merkez Z = 23', 11, MUTED, 'middle')
svg.dim_v(ox - 22, E(0, 50)[1], E(0, 0)[1], '50 mm', off=-16)

# ---------- D / ARKA YÜZ ----------
ox, oy = 60, 560
svg.text(ox + 240, oy - 14, 'D / ARKA YÜZ / sabitleme (kapağa bakan)', 20, DIM, 'middle', '700')
svg.view(V['arka'], ox, oy, S, (-120, -80), colors=COL, bg=BOXBG)
def D(x, y): return ox + (120 - x) * S, oy + (80 - y) * S
x, y = D(60, 41)
svg.text(x, y - 6, 'DIN klips', 13, DARK, 'middle', '700')
svg.text(x, y + 12, '(35 mm ray, kanal 35,5)', 12, GREY, 'middle')
svg.text(x, y + 30, 'yaylı, aletsiz', 11, GREY, 'middle')
for xm in (17.5, 102.5):
    x, y = D(xm, 45.25)
    svg.text(x, y + 34, 'oval yuva M5 15 × 5,5', 12, DARK, 'middle')
svg.text(ox + 240, oy + 40, 'mevcut cıvata / kapak çerçevesi için (yeni delik YOK)', 12, DARK, 'middle')
svg.text(ox + 240, oy + 266, '4× mıknatıs pedi Ø7 (köşeler, 1 mm cep) / yalnız konumlandırma/kadraj', 12, RED, 'middle')
svg.text(ox + 240, oy + 283, 'mekanik tutma DEĞİL (§4.8) / akım trafolarından uzak (§7.5 satır 337)', 11, RED, 'middle')

# ---------- C / İÇ GÖRÜNÜŞ (kapak açık) ----------
ox, oy = 640, 560
svg.text(ox + 240, oy - 14, 'C / İÇ GÖRÜNÜŞ / kapak açık, önden (PCB 110 × 70)', 20, DIM, 'middle', '700')
svg.add('<g transform="translate(%g,%g)"><rect x="0" y="0" width="480" height="320" rx="16" fill="#eceff1"/>'
        '<rect x="20" y="20" width="440" height="280" rx="8" fill="url(#pcbp)"/>'
        '<rect x="348" y="20" width="112" height="280" fill="#fff3e0" opacity="0.8"/>'
        '<line x1="348" y1="20" x2="348" y2="300" stroke="#ef6c00" stroke-width="2" stroke-dasharray="6 3"/></g>' % (ox, oy))
def C(x, y): return ox + x * S, oy + (80 - y) * S
g = ['<g transform="translate(%g,%g)" fill="none" stroke-width="1.3" stroke-dasharray="5 3">' % (ox, oy)]
for pl in M['ic_thru']:
    if not pl['body'].startswith('GridUp-PCB/'): continue
    pts = ' '.join('%g,%g' % (p[0] * S, (p[1] + 80) * S) for p in pl['pts'])
    g.append('<polyline points="%s" stroke="%s"/>' % (pts, col_of(pl['body'])))
g.append('</g>')
svg.add('\n'.join(g))
ic_col = {n: col_of(n) for n in {pl['body'] for pl in M['ic']}}
svg.view(M['ic'], ox, oy, S, (0, -80), stroke=INK, sw=1.4, colors=ic_col)
svg.text(C(60, 42.5)[0], C(60, 42.5)[1] + 34, 'MLX90640', 11, DARK, 'middle', '700')
svg.text(C(12, 36)[0], C(12, 36)[1] + 22, 'SHT31', 10, '#1565c0', 'middle')
svg.text(C(24, 55.4)[0], C(24, 55.4)[1], 'ESP32-S3', 10, '#455a64', 'middle')
svg.text(C(84.85, 60.35)[0], C(84.85, 60.35)[1], 'RAC05', 10, '#ad1457', 'middle')
svg.text(C(71.5, 22.75)[0], C(71.5, 22.75)[1], '2× süperkap.', 10, '#f57f17', 'middle')
svg.text(C(10, 22.6)[0], C(10, 22.6)[1], 'RS-485', 9, '#2e7d32', 'middle')
svg.text(C(44, 9)[0], C(44, 9)[1], 'CT ×4', 9, '#6a1b9a', 'middle')
svg.text(C(22.5, 13.75)[0], C(22.5, 13.75)[1], 'genişleme', 9, '#1565c0', 'middle')
svg.text(C(99, 9.5)[0], C(99, 9.5)[1], '230 V', 9, '#ef6c00', 'middle')
svg.text(C(101, 40)[0], C(101, 40)[1], '230 V bölgesi', 10, '#e65100', 'middle')
svg.text(ox + 240, oy + 338, 'düz = ön yüz + gövde, kesikli = arka yüz parçaları / ayrıntı: 02-pcb-yerlesimi.svg', 11, MUTED, 'middle')

# ---------- F / İZOMETRİK ----------
ox, oy = 640, 1020
svg.text(ox + 240, oy - 14, 'F / İZOMETRİK / Fusion 360 modeli', 20, DIM, 'middle', '700')
mnx, mny, mxx, mxy = svg.bbox(V['iso'])
SI = min(2.6, 300 / (mxy - mny), 470 / (mxx - mnx))
w, h = (mxx - mnx) * SI, (mxy - mny) * SI
svg.view(V['iso'], ox + (480 - w) / 2, oy + 10 + (300 - h) / 2, SI, (mnx, mny), colors=COL, sw=1.3)
print('iso SI', round(SI, 2), 'h', round(h))
svg.text(ox + 240, oy + 338, 'kaynak: GridUp-Kutu.f3d + GridUp-PCB.f3d (montaj) / görünüşler modelden projeksiyon, gizli çizgiler ayıklandı', 11, MUTED, 'middle')

# ---------- NOTLAR ----------
ox, oy = 1160, 400
svg.add('<rect x="%d" y="%d" width="500" height="560" fill="#fff" stroke="#90a4ae" stroke-width="2"/>' % (ox, oy))
svg.text(ox + 16, oy + 30, 'Tasarım notları', 18, INK, weight='700')
notes = [
    ('Ölçü:', ' 120 × 80 × 50 mm, duvar 2 mm, köşe R4. Karar kaydı hedefi'),
    (None, '~100×70×35; RAC05 (31,7 × 26,7 × 21,8) + 2× süperkap (Ø10,5 × 31,5'),
    (None, 'yatık) sığmadığı için büyüdü (§4.6).'),
    ('IR pencere:', ' MLX90640 8–14 µm bandında çalışır; standart'),
    (None, 'cam/plastik geçirmez. Pencere IR geçirgen malzeme (Ge/kalkojenit'),
    (None, 'veya ince polietilen film), conta ile IP54 korunur (§4.4).'),
    ('Sensör yuvası:', ' TO-39 pencereye dayalı; yuva 3 mm konik pah ile açılır,'),
    (None, 'kutu kenarı görüş açısını (110°×75°) kesmez.'),
    ('Nem/sıcaklık:', ' SHT31 kabin havasını görmeli → IP54 membran'),
    (None, 'vent M6 (PTFE) arkasında; su/toz geçmez, hava/nem geçer.'),
    ('Isı:', ' AC/DC modül PCB\'nin arkasında, sensörlerden uzak; SHT31'),
    (None, 'güç modülüne en uzak köşede (öz-ısınma hatası).'),
    ('Kablolar:', ' tüm girişler alt yüzde, soldan sağa RS-485 / SMA / CT / 230 V;'),
    (None, 'her giriş kendi klemensinin altında, 230 V kablosu alçak gerilim'),
    (None, 'bölgesini geçmez. Kapak içi montajda kablolar menteşeye iner, kıvrım'),
    (None, 'payı bırakılır (§4.7). Anten kablosu SMA\'dan pano dışına (§7.4).'),
    ('Sabitleme:', ' DIN klips veya oval yuvalardan mevcut cıvataya;'),
    (None, 'mıknatıs pedleri sadece hizalama. Yeni delik açılmaz (§4.8).'),
    ('Sıcaklık sınıfı:', ' tüm bileşenler −40…+85 °C endüstriyel;'),
    (None, 'kutu malzemesi UV/ısı dayanımlı PC veya alüminyum döküm.'),
    ('PCB:', ' 110 × 70, kutu içinde (5, 5, 39,4) mm, 4 × Ø6 dikme üstünde'),
    (None, '(M3); ön yüzü kapaktan 5 mm geride, PCB koordinatı = kutu − 5 mm'),
    (None, '(02-pcb-yerlesimi.svg).'),
    ('Genişleme payı:', ' 2×5 başlık ayrılmış I²C/UART / PD/akustik'),
    (None, 'fark katmanı için (§7.1 şartı); kutuda ilgili yüzde kör tapa.'),
]
y = oy + 62
for i, (b, t) in enumerate(notes):
    if b:
        svg.add('<text x="%d" y="%d" font-size="13" fill="%s"><tspan font-weight="700">%s</tspan>%s</text>' % (ox + 16, y, DARK, b, t))
    else:
        svg.text(ox + 16, y, t, 13, DARK)
    y += 17 if (i + 1 < len(notes) and notes[i + 1][0] is None) else 22
svg.text(ox + 16, y + 4, 'Kavramsal tasarım / üretim çizimi değildir (§1.4: fiziksel donanım yok).', 12, MUTED)

# lejant (sol alt boşluk)
ox, oy = 60, 1020
svg.add('<rect x="%d" y="%d" width="480" height="150" fill="#fff" stroke="#90a4ae" stroke-width="1.5"/>' % (ox, oy))
svg.text(ox + 16, oy + 28, 'Lejant', 15, INK, weight='700')
svg.add('<rect x="%d" y="%d" width="40" height="16" fill="url(#hatch)" stroke="%s" stroke-width="1.5"/>' % (ox + 16, oy + 44, INK))
svg.text(ox + 66, oy + 57, 'kesilen kutu malzemesi (X = 60 düzlemi)', 12, DARK)
svg.add('<rect x="%d" y="%d" width="40" height="16" fill="#f9a825" fill-opacity="0.35" stroke="#f9a825" stroke-width="1.5"/>' % (ox + 16, oy + 70))
svg.text(ox + 66, oy + 83, 'kesilen parça (renk: parça grubu)', 12, DARK)
svg.add('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="1.3" stroke-dasharray="5 3"/>' % (ox + 16, oy + 104, ox + 56, oy + 104, '#546e7a'))
svg.text(ox + 66, oy + 108, 'arka yüz parçası (kart üzerinden görünür)', 12, DARK)
svg.add('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="1.5"/>' % (ox + 16, oy + 128, ox + 56, oy + 128, INK))
svg.text(ox + 66, oy + 132, 'görünür kenar (modelden, ışın testiyle ayıklanmış)', 12, DARK)

comment = """    Modül kutusu / teknik kroki (04-mekanik-yerlesim.md §4.5–4.6, §4.4 IR pencere).
    Kaynak: Fusion 360 modelleri GridUp-Kutu.f3d + GridUp-PCB.f3d, montaj GridUp-Kutu-Montaj.f3d (thozoz hub / Default Project).
    Görünüşler modelden API ile ortografik projeksiyon (kenarlar + silindir siluetleri, gizli çizgiler ışın testiyle ayıklandı);
    kesit TemporaryBRepManager.planeIntersection ile X = 60 düzleminden. Ölçek: 1 mm = 4 birim (izometrik 2,6).
    Model koordinatı: X sağ, Y yukarı, Z ön yüz normali. SVG y aşağı: svg_y = 80 − Y.
    Kutu 120 × 80 × 50 mm: gövde Z 0..46 (duvar 2 mm, köşe R4, 4 × Ø7 kapak vida direği köşelerde, 4 × Ø6 PCB dikmesi Z 2..39,4 kutu (12,12) (108,12) (12,68) (108,68) = PCB (7,7) vb., M3), kapak Z 46..50 (4 mm), 4 × M3 (5,5) (115,5) (5,75) (115,75).
    Ön yüz (Z=50): IR pencere Ø15 merkez model (60, 42,5) [svg (60, 37,5)]; yuva Ø23 +2 mm, 3 mm pah; pencere plakası Ø15 × 1 (Z 47..48).
      Membran vent M6 model (12, 36) [svg (12, 44)], Ø9 halka. Durum LED Ø3,2 model (30, 70) [svg (30, 10)].
    Alt yüz (Y=0), merkez Z=23, soldan sağa PCB klemens sırasıyla: RS-485 PG7 Ø12,5 x=17,5 / SMA Ø6,4 x=40 / CT PG7 Ø12,5 x=65 / 230 V PG7 Ø12,5 x=102,5.
    Arka yüz (Z=0): DIN klips 35 × 42 × 5 merkez (60, 41), ray kanalı 35,5 × 3; oval yuva M5 15 × 5,5 merkez (17,5, 45,25) ve (102,5, 45,25);
      mıknatıs cepleri Ø7 × 1 mm köşelerde (7,5, 7,5) vb.
    PCB 110 × 70 × 1,6 kutu içinde (5, 5, 39,4) → ön yüzü Z=41, MLX90640 tepesi Z=47 (pencereye dayalı); PCB koordinatı = kutu − 5 mm.
    Bileşen ölçüleri datasheet'lerden: MLX90640 TO-39 Ø9,3 × 5,7 / ESP32-S3-WROOM-1U 18 × 19,2 × 3,2 / RAC05-05SK/277 31,7 × 26,7 × 21,8 / 2× Eaton HV1030 Ø10,5 × 31,5 yatık.
    Üretim çizimi değildir."""
n = svg.write(OUT, comment)
print('written', OUT, n)
