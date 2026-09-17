# GridUp modül bağlantı şeması / KiCad .kicad_sch üreteci (elle çizim yok, kaynak model bu dosya).
# Semboller KiCad kütüphanesinden (share/kicad/symbols) okunup lib_symbols'a gömülür; pin uçları kütüphane
# geometrisinden hesaplanır. Netler: 03-pinout.md §3.1–3.6 (I²C GPIO8/9, CT GPIO4–7 ADC1, UART1 GPIO17/18
# + DE/RE GPIO21, besleme algılama GPIO1, genişleme GPIO10/11; RAC05 → D1 → 5 V → LDO 3V3; süperkap 2× HV seri + R_şarj → boost 4,6 V → D2).
# Kullanım: python gen_sch.py [--kicad-symbols DIR] → GridUp-Modul.kicad_sch + GridUp-Modul.kicad_pro
import os, sys, json, math, uuid, re

HERE = os.path.dirname(os.path.abspath(__file__))
SYMDIR = None
for a in sys.argv[1:]:
    if a.startswith('--kicad-symbols='): SYMDIR = a.split('=', 1)[1]
if SYMDIR is None:
    for c in [os.path.expandvars(r'%LOCALAPPDATA%\Programs\KiCad\10.0\share\kicad\symbols'),
              r'C:\Program Files\KiCad\10.0\share\kicad\symbols', r'C:\Program Files\KiCad\9.0\share\kicad\symbols',
              '/usr/share/kicad/symbols']:
        if os.path.isdir(c): SYMDIR = c; break
assert SYMDIR, 'KiCad sembol klasörü bulunamadı (--kicad-symbols=DIR)'
PROJECT = 'GridUp-Modul'
ROOT_UUID = '6f1e2a3b-0000-4000-8000-000000000001'

# ---------------- S-expression ----------------
class Sym(str): pass
def parse(text):
    i, n = 0, len(text)
    def tok():
        nonlocal i
        while i < n and text[i] in ' \t\r\n': i += 1
        if i >= n: return None
        c = text[i]
        if c in '()': i += 1; return c
        if c == '"':
            j = i + 1; out = []
            while text[j] != '"':
                if text[j] == '\\': out.append(text[j + 1]); j += 2
                else: out.append(text[j]); j += 1
            i = j + 1; return out and ''.join(out) or ''
        j = i
        while j < n and text[j] not in ' \t\r\n()': j += 1
        s = text[i:j]; i = j; return Sym(s)
    def read(t):
        if t == '(':
            lst = []
            while True:
                t2 = tok()
                if t2 == ')': return lst
                lst.append(read(t2))
        return t
    return read(tok())

def q(s): return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
def ser(x, ind=0):
    if isinstance(x, list):
        if not x: return '()'
        head = ser(x[0]) if not isinstance(x[0], list) else ser(x[0], ind + 1)
        simple = all(not isinstance(e, list) for e in x)
        if simple: return '(' + ' '.join(ser(e) for e in x) + ')'
        parts = ['(' + head]
        for e in x[1:]:
            if isinstance(e, list): parts.append('\n' + '\t' * (ind + 1) + ser(e, ind + 1))
            else: parts[-1] += ' ' + ser(e)
        return ''.join(parts) + '\n' + '\t' * ind + ')'
    if isinstance(x, Sym): return str(x)
    return q(str(x))

def find(node, key):
    return [e for e in node if isinstance(e, list) and e and e[0] == key]
def find1(node, key):
    f = find(node, key); return f[0] if f else None

# ---------------- kütüphane ----------------
_libcache = {}
def lib_tree(lib):
    if lib not in _libcache:
        _libcache[lib] = parse(open(os.path.join(SYMDIR, lib + '.kicad_sym'), encoding='utf-8').read())
    return _libcache[lib]

def lib_symbol(lib, name, flatten=True):
    """Kütüphane sembolü; extends varsa taban sembolle düzleştirilir (KiCad'in yaptığı gibi: taban gövde +
    türetilmiş özellikler). Adı lib:name yapılır."""
    tree = lib_tree(lib)
    s = next(e for e in find(tree, 'symbol') if e[1] == name)
    ext = find1(s, 'extends')
    if ext:
        base = lib_symbol(lib, ext[1]); base_name = ext[1]
        props = {p[1]: p for p in find(s, 'property')}
        out = []
        for e in base:
            if isinstance(e, list) and e and e[0] == 'symbol' and isinstance(e[1], str) and e[1].startswith(base_name + '_'):
                e = [Sym('symbol'), name + e[1][len(base_name):]] + e[2:]
            elif isinstance(e, list) and e and e[0] == 'property' and e[1] in props:
                d = props.pop(e[1])
                if d[2] != '' or e[2] == '': e = d          # boş türetilmiş değer tabanı ezmez (KiCad flatten davranışı)
            out.append(e)
        # tabanda olmayan özellikleri son alt-sembolden önce ekle
        k = next(i for i, e in enumerate(out) if isinstance(e, list) and e and e[0] == 'symbol')
        for p in props.values(): out.insert(k, p); k += 1
        s = out
    s = list(s)
    s[1] = lib + ':' + name
    return s

def scale_pin_fonts(sym, name_sz, num_sz):
    for unit in find(sym, 'symbol'):
        for pin in find(unit, 'pin'):
            for key, sz in (('name', name_sz), ('number', num_sz)):
                node = find1(pin, key); eff = find1(node, 'effects') if node else None
                font = find1(eff, 'font') if eff else None
                if font is not None:
                    sizes = find1(font, 'size')
                    if sizes is not None: sizes[1] = Sym('%g' % sz); sizes[2] = Sym('%g' % sz)
    return sym

def pins_of(sym):
    """[(number, name, x, y_up, angle, type)] / tüm birimlerden."""
    out = []
    for unit in find(sym, 'symbol'):
        for p in find(unit, 'pin'):
            at = find1(p, 'at'); num = find1(p, 'number')[1]; nm = find1(p, 'name')[1]
            out.append((num, nm, float(at[1]), float(at[2]), int(float(at[3])), str(p[1])))
    return out

def mlx90640_symbol():
    """Kütüphanede yok / TO-39 4 pinli özel sembol."""
    def prop(k, v, y, hide=False):
        e = [Sym('property'), k, v, [Sym('at'), Sym('0'), Sym(str(y)), Sym('0')]]
        if hide: e.append([Sym('hide'), Sym('yes')])
        e.append([Sym('effects'), [Sym('font'), [Sym('size'), Sym('1.27'), Sym('1.27')]]])
        return e
    def pin(t, x, y, a, nm, num):
        return [Sym('pin'), Sym(t), Sym('line'), [Sym('at'), Sym(str(x)), Sym(str(y)), Sym(str(a))], [Sym('length'), Sym('2.54')],
                [Sym('name'), nm, [Sym('effects'), [Sym('font'), [Sym('size'), Sym('1.27'), Sym('1.27')]]]],
                [Sym('number'), num, [Sym('effects'), [Sym('font'), [Sym('size'), Sym('1.27'), Sym('1.27')]]]]]
    return [Sym('symbol'), 'GridUp:MLX90640', [Sym('pin_names'), [Sym('offset'), Sym('1.016')]],
            [Sym('exclude_from_sim'), Sym('no')], [Sym('in_bom'), Sym('yes')], [Sym('on_board'), Sym('yes')],
            prop('Reference', 'U', 11.43), prop('Value', 'MLX90640ESF-BAA', -11.43),
            prop('Footprint', 'Package_TO_SOT_THT:TO-39-4', 0, True),
            prop('Datasheet', 'https://www.melexis.com/en/product/MLX90640/', 0, True),
            prop('Description', 'Termal dizi 32x24, 110x75 derece, I2C 0x33', 0, True),
            [Sym('symbol'), 'MLX90640_0_1',
             [Sym('rectangle'), [Sym('start'), Sym('-10.16'), Sym('10.16')], [Sym('end'), Sym('10.16'), Sym('-10.16')],
              [Sym('stroke'), [Sym('width'), Sym('0.254')], [Sym('type'), Sym('default')]], [Sym('fill'), [Sym('type'), Sym('background')]]],
             [Sym('circle'), [Sym('center'), Sym('0'), Sym('0')], [Sym('radius'), Sym('4.0')],
              [Sym('stroke'), [Sym('width'), Sym('0.254')], [Sym('type'), Sym('default')]], [Sym('fill'), [Sym('type'), Sym('none')]]]],
            [Sym('symbol'), 'MLX90640_1_1',
             pin('power_in', 0, 12.7, 270, 'VDD', '1'), pin('power_in', 0, -12.7, 90, 'GND', '2'),
             pin('bidirectional', 12.7, 2.54, 180, 'SDA', '3'), pin('input', 12.7, -2.54, 180, 'SCL', '4')]]

def sht31_symbol():
    """Kütüphane sembolü (Sensor_Humidity:SHT31-DIS) çok sıkışık / aynı pin numaralarıyla geniş özel sembol."""
    def prop(k, v, y, hide=False):
        e = [Sym('property'), k, v, [Sym('at'), Sym('0'), Sym(str(y)), Sym('0')]]
        if hide: e.append([Sym('hide'), Sym('yes')])
        e.append([Sym('effects'), [Sym('font'), [Sym('size'), Sym('1.27'), Sym('1.27')]]])
        return e
    def pin(t, x, y, a, nm, num):
        return [Sym('pin'), Sym(t), Sym('line'), [Sym('at'), Sym(str(x)), Sym(str(y)), Sym(str(a))], [Sym('length'), Sym('2.54')],
                [Sym('name'), nm, [Sym('effects'), [Sym('font'), [Sym('size'), Sym('1.27'), Sym('1.27')]]]],
                [Sym('number'), num, [Sym('effects'), [Sym('font'), [Sym('size'), Sym('1.27'), Sym('1.27')]]]]]
    return [Sym('symbol'), 'GridUp:SHT31', [Sym('pin_names'), [Sym('offset'), Sym('1.016')]],
            [Sym('exclude_from_sim'), Sym('no')], [Sym('in_bom'), Sym('yes')], [Sym('on_board'), Sym('yes')],
            prop('Reference', 'U', 11.43), prop('Value', 'SHT31-DIS-B', -11.43),
            prop('Footprint', 'Sensor_Humidity:Sensirion_DFN-8-1EP_2.5x2.5mm_P0.5mm_EP1.1x1.7mm', 0, True),
            prop('Datasheet', 'https://sensirion.com/products/catalog/SHT31-DIS-B', 0, True),
            prop('Description', 'Sicaklik + nem, I2C 0x44/0x45', 0, True),
            [Sym('symbol'), 'SHT31_0_1',
             [Sym('rectangle'), [Sym('start'), Sym('-7.62'), Sym('7.62')], [Sym('end'), Sym('7.62'), Sym('-7.62')],
              [Sym('stroke'), [Sym('width'), Sym('0.254')], [Sym('type'), Sym('default')]], [Sym('fill'), [Sym('type'), Sym('background')]]]],
            [Sym('symbol'), 'SHT31_1_1',
             pin('power_in', 0, 10.16, 270, 'VDD', '5'), pin('power_in', 0, -10.16, 90, 'VSS', '8'),
             pin('bidirectional', 10.16, 5.08, 180, 'SDA', '1'), pin('input', 10.16, 0, 180, 'SCL', '4'), pin('output', 10.16, -5.08, 180, 'ALERT', '3'),
             pin('input', -10.16, 5.08, 0, 'ADDR', '2'), pin('input', -10.16, 0, 0, '~{RESET}', '6'), pin('passive', -10.16, -5.08, 0, 'R', '7')]]

def max3485_symbol():
    """Kütüphane sembolü (Interface_UART:MAX3485) aynalanınca içi karışıyor / sade kutu, aynı pin numaraları."""
    def prop(k, v, y, hide=False):
        e = [Sym('property'), k, v, [Sym('at'), Sym('0'), Sym(str(y)), Sym('0')]]
        if hide: e.append([Sym('hide'), Sym('yes')])
        e.append([Sym('effects'), [Sym('font'), [Sym('size'), Sym('1.27'), Sym('1.27')]]])
        return e
    def pin(t, x, y, a, nm, num):
        return [Sym('pin'), Sym(t), Sym('line'), [Sym('at'), Sym(str(x)), Sym(str(y)), Sym(str(a))], [Sym('length'), Sym('2.54')],
                [Sym('name'), nm, [Sym('effects'), [Sym('font'), [Sym('size'), Sym('1.27'), Sym('1.27')]]]],
                [Sym('number'), num, [Sym('effects'), [Sym('font'), [Sym('size'), Sym('1.27'), Sym('1.27')]]]]]
    return [Sym('symbol'), 'GridUp:MAX3485', [Sym('pin_names'), [Sym('offset'), Sym('1.016')]],
            [Sym('exclude_from_sim'), Sym('no')], [Sym('in_bom'), Sym('yes')], [Sym('on_board'), Sym('yes')],
            prop('Reference', 'U', 13.97), prop('Value', 'MAX3485', -13.97),
            prop('Footprint', 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm', 0, True),
            prop('Datasheet', 'https://www.analog.com/media/en/technical-documentation/data-sheets/MAX3483-MAX3491.pdf', 0, True),
            prop('Description', 'RS-485 alici-verici 3,3 V yaricift', 0, True),
            [Sym('symbol'), 'MAX3485_0_1',
             [Sym('rectangle'), [Sym('start'), Sym('-7.62'), Sym('10.16')], [Sym('end'), Sym('7.62'), Sym('-10.16')],
              [Sym('stroke'), [Sym('width'), Sym('0.254')], [Sym('type'), Sym('default')]], [Sym('fill'), [Sym('type'), Sym('background')]]]],
            [Sym('symbol'), 'MAX3485_1_1',
             pin('power_in', 0, 12.7, 270, 'VCC', '8'), pin('power_in', 0, -12.7, 90, 'GND', '5'),
             pin('input', -10.16, 5.08, 0, 'DI', '4'), pin('input', -10.16, 0, 0, 'DE', '3'), pin('input', -10.16, -2.54, 0, '~{RE}', '2'), pin('output', -10.16, -5.08, 0, 'RO', '1'),
             pin('bidirectional', 10.16, -2.54, 180, 'B', '7'), pin('bidirectional', 10.16, -7.62, 180, 'A', '6')]]

def rac05_symbol():
    """Converter_ACDC:RAC05-05SK kopyası; NC pini (3) kütüphanede gizli / 0 mm: diğer pinler gibi görünür yap
    (sağda 2,54 mm bacak, pasif tip → sadece şemadaki mavi X görünür, kütüphane uyuşmazlığı uyarısı yok).
    DC simgesi (kesikli+düz çizgi) NC yazısının altında kalmasın diye 1 mm sola."""
    sym = scale_pin_fonts(lib_symbol('Converter_ACDC', 'RAC05-05SK'), SZ_PIN, SZ_PINNUM)
    for unit in find(sym, 'symbol'):
        for pin in find(unit, 'pin'):
            if find1(pin, 'name')[1] == 'NC':
                pin[:] = [x for x in pin if not (isinstance(x, list) and x and x[0] == Sym('hide'))]
                pin[1] = Sym('passive')
                find1(pin, 'at')[1:] = [Sym('10.16'), Sym('0'), Sym('180')]
        for pl in find(unit, 'polyline'):
            pts = find1(pl, 'pts')
            xs_ = [float(xy[1]) for xy in pts[1:]]
            if min(xs_) > 0 and max(xs_) - min(xs_) < 4:   # sağ yarıdaki kısa yatay çizgiler = DC simgesi
                for xy in pts[1:]: xy[1] = Sym('%g' % (float(xy[1]) - 1.0))
    sym[1] = 'GridUp:RAC05-05SK'
    return sym

# ---------------- şema ----------------
def g(v): return Sym('%g' % round(v, 4))
_uuid_n = [0]
def new_uuid():   # deterministik: aynı girdi → aynı dosya (diff sadece gerçek değişiklikte)
    _uuid_n[0] += 1
    return str(uuid.uuid5(uuid.UUID(ROOT_UUID), 'gridup-%d' % _uuid_n[0]))
FONT = lambda: [Sym('effects'), [Sym('font'), [Sym('size'), Sym('1.27'), Sym('1.27')]]]
# Yazı boyutları (mm). Hedef: doküman 1200 px genişlikte gömülünce etiket ≥ 8 px (içerik genişliği ~290 mm).
SZ_LABEL, SZ_PROP, SZ_NOTE, SZ_HEAD, SZ_TITLE, SZ_PIN, SZ_PINNUM = 1.7, 1.7, 1.8, 2.2, 3.2, 1.6, 1.3
# Net tipine göre renk (tel + etiket): elle SVG'deki lejantla aynı mantık
COL = {'3V3': (198, 40, 40), '5V': (140, 0, 0), 'GND': (70, 70, 70), 'I2C': (21, 101, 192), 'UART': (106, 27, 154),
       'ANA': (230, 120, 0), 'DEF': (0, 132, 0)}
def net_color(name):
    n = name.upper()
    if n in ('+3V3', '3V3'): return COL['3V3']
    if n in ('+5V', '5V_RAW', 'L', 'N'): return COL['5V']
    if n in ('GND', 'EARTH_PROTECTIVE', 'PE'): return COL['GND']
    if n in ('SDA', 'SCL'): return COL['I2C']
    if n.startswith(('U1', 'U0', 'USB', 'DE_RE')): return COL['UART']
    if n.startswith(('CT_', 'VSENSE', 'V_BIAS')): return COL['ANA']
    if n.startswith('GPIO'): return COL['DEF']   # genişleme: 'diğer' yeşili
    return None
def color_node(c, a=1.0): return [Sym('color'), Sym(str(c[0])), Sym(str(c[1])), Sym(str(c[2])), Sym('%g' % a)]

class Part:
    def __init__(self, sch, lib_id, ref, value, at, rot=0, mirror=None, footprint='', fields=None):
        self.lib_id, self.ref, self.value, self.at, self.rot, self.mirror = lib_id, ref, value, at, rot, mirror
        self.sym = sch.libsyms[lib_id]
        self.pins = {}      # number -> (X, Y, outward dx, dy)
        self.byname = {}
        for num, nm, x, y, ang, typ in pins_of(self.sym):
            X, Y = self.xform(x, y)
            ox, oy = -math.cos(math.radians(ang)), -math.sin(math.radians(ang))   # dışa doğru (sembol uzayı: y yukarı; açı gövdeye bakar)
            OX, OY = self.xform(ox, oy, vec=True)
            self.pins[num] = (X, Y, OX, OY, nm, typ)
            self.byname.setdefault(nm, num)
        self.footprint = footprint; self.fields = fields or {}
    def xform(self, x, y, vec=False):
        if self.mirror == 'y': x = -x
        if self.mirror == 'x': y = -y
        t = math.radians(self.rot)
        xr, yr = x * math.cos(t) - y * math.sin(t), x * math.sin(t) + y * math.cos(t)
        X, Y = xr, -yr
        if vec: return round(X, 4), round(Y, 4)
        return round(self.at[0] + X, 4), round(self.at[1] + Y, 4)
    def p(self, key):
        num = key if key in self.pins else self.byname[key]
        X, Y, *_ = self.pins[num]; return (X, Y)
    def out(self, key):
        num = key if key in self.pins else self.byname[key]
        return self.pins[num][2:4]
    def stub(self, key, L=5.08):
        """pin ucundan dışa L uzunlukta nokta"""
        X, Y = self.p(key); ox, oy = self.out(key)
        return (round(X + ox * L, 4), round(Y + oy * L, 4))

class Sch:
    def __init__(self):
        self.libsyms = {}; self.items = []; self.parts = []; self.pwr_n = 0
    def use(self, lib, name):
        lid = lib + ':' + name
        if lid not in self.libsyms: self.libsyms[lid] = scale_pin_fonts(lib_symbol(lib, name), SZ_PIN, SZ_PINNUM)
        return lid
    def part(self, lib_id, ref, value, at, rot=0, mirror=None, ref_at=None, val_at=None, hide_value=False, footprint='', fields=None):
        P = Part(self, lib_id, ref, value, at, rot, mirror, footprint, fields); self.parts.append(P)
        P.ref_at, P.val_at, P.hide_value = ref_at, val_at, hide_value
        return P
    def power(self, name, at, rot=0):
        self.pwr_n += 1
        lid = self.use('power', name)
        P = self.part(lid, '#PWR%02d' % self.pwr_n, name, at, rot); P.is_power = True
        if rot == 0 and name != 'GND':   # ok yukarı: değer okun tam üstünde, ortalı (KiCad varsayılanı gibi)
            P.val_at = (at[0], at[1] - 3.6); P.just = 'center'
        return P
    def flag(self, at, rot=0):
        self.pwr_n += 1
        lid = self.use('power', 'PWR_FLAG')
        P = self.part(lid, '#FLG%02d' % self.pwr_n, 'PWR_FLAG', at, rot, hide_value=True); P.is_power = True
        return P
    def wire(self, *pts, color=None):
        for a, b in zip(pts, pts[1:]):
            if a == b: continue
            stroke = [Sym('stroke'), [Sym('width'), Sym('0')], [Sym('type'), Sym('default')]]
            if color: stroke.append(color_node(color))
            self.items.append([Sym('wire'), [Sym('pts'), [Sym('xy'), g(a[0]), g(a[1])], [Sym('xy'), g(b[0]), g(b[1])]], stroke, [Sym('uuid'), new_uuid()]])
    def gline(self, a, b, color, width=0.5):   # grafik çizgi (elektriksel değil) / lejant için
        self.items.append([Sym('polyline'), [Sym('pts'), [Sym('xy'), g(a[0]), g(a[1])], [Sym('xy'), g(b[0]), g(b[1])]],
                           [Sym('stroke'), [Sym('width'), g(width)], [Sym('type'), Sym('solid')], color_node(color)], [Sym('uuid'), new_uuid()]])
    def junction(self, at):
        self.items.append([Sym('junction'), [Sym('at'), g(at[0]), g(at[1])], [Sym('diameter'), Sym('0')],
                           [Sym('color'), Sym('0'), Sym('0'), Sym('0'), Sym('0')], [Sym('uuid'), new_uuid()]])
    def label(self, text, at, rot=0):
        just = {0: 'left bottom', 180: 'right bottom', 90: 'left bottom', 270: 'right bottom'}[rot]
        font = [Sym('font'), [Sym('size'), g(SZ_LABEL), g(SZ_LABEL)]]
        c = net_color(text)
        if c: font.append(color_node(c))
        self.items.append([Sym('label'), text, [Sym('at'), g(at[0]), g(at[1]), Sym(str(rot))],
                           [Sym('effects'), font, [Sym('justify')] + [Sym(j) for j in just.split()]],
                           [Sym('uuid'), new_uuid()]])
    def nc(self, at):
        self.items.append([Sym('no_connect'), [Sym('at'), g(at[0]), g(at[1])], [Sym('uuid'), new_uuid()]])
    def text(self, s, at, size=SZ_NOTE, bold=False, italic=False, rot=0, color=None, just='left'):
        font = [Sym('font'), [Sym('size'), g(size), g(size)]]
        if bold: font.append([Sym('bold'), Sym('yes')])
        if italic: font.append([Sym('italic'), Sym('yes')])
        if color: font.append(color_node(color))
        self.items.append([Sym('text'), s, [Sym('exclude_from_sim'), Sym('no')], [Sym('at'), g(at[0]), g(at[1]), Sym(str(rot))],
                           [Sym('effects'), font, [Sym('justify'), Sym(just), Sym('bottom')]], [Sym('uuid'), new_uuid()]])
    def rect(self, a, b, color=(120, 120, 120), tint=0.08, title=None):
        # kicad-cli SVG alfa uygulamıyor → dolgu açık ton (beyaza doğru karıştırılmış), çerçeve tam renk
        fill = tuple(int(round(255 - (255 - c) * tint)) for c in color)
        self.items.insert(0, [Sym('rectangle'), [Sym('start'), g(a[0]), g(a[1])], [Sym('end'), g(b[0]), g(b[1])],
                           [Sym('stroke'), [Sym('width'), Sym('0.25')], [Sym('type'), Sym('solid')], color_node(color)],
                           [Sym('fill'), [Sym('type'), Sym('color')], color_node(fill)], [Sym('uuid'), new_uuid()]])
        if title: self.text(title, (a[0] + 1.5, a[1] + SZ_HEAD + 1.0), SZ_HEAD, bold=True, color=color)
    # pin ucu + kısa tel + etiket / güç sembolü / NC
    def pin_label(self, P, key, text, L=5.08):
        a = P.p(key); b = P.stub(key, L); self.wire(a, b, color=net_color(text))
        ox, oy = P.out(key)
        rot = 0 if ox > 0.5 else 180 if ox < -0.5 else (90 if oy < -0.5 else 270)
        self.label(text, b, rot)
        return b
    def pin_power(self, P, key, name, L=2.54, rot=None):
        a = P.p(key); b = P.stub(key, L); self.wire(a, b, color=net_color(name))
        ox, oy = P.out(key)
        if rot is None:
            rot = 0 if oy < 0 else 180 if oy > 0 else (90 if ox > 0.5 else 270)   # gövde tel yönüne doğru
            if name == 'GND': rot = (rot + 180) % 360
        return self.power(name, b, rot)
    def pin_nc(self, P, key): self.nc(P.p(key))

    def emit(self, title):
        out = [Sym('kicad_sch'), [Sym('version'), Sym('20250610')], [Sym('generator'), 'gen_sch'], [Sym('generator_version'), '10.0'],
               [Sym('uuid'), ROOT_UUID], [Sym('paper'), 'User', Sym('340'), Sym('300')],
               [Sym('title_block'), [Sym('title'), title], [Sym('date'), '2026-09-14'], [Sym('rev'), '1'], [Sym('company'), 'Grid Up Hackathon / İZ A'],
                [Sym('comment'), Sym('1'), 'Kavramsal şema / üretim çizimi değildir (karar kaydı §1.4). Pasif değerler tipik başlangıç değerleri.'],
                [Sym('comment'), Sym('2'), 'Pin atamaları 03-pinout.md §3.1 ile aynı; kaynak: eda/gen_sch.py']],
               [Sym('lib_symbols')] + list(self.libsyms.values())]
        out += self.items
        for P in self.parts:
            X, Y = P.at
            e = [Sym('symbol'), [Sym('lib_id'), P.lib_id], [Sym('at'), g(X), g(Y), Sym(str(P.rot))]]
            if P.mirror: e.append([Sym('mirror'), Sym(P.mirror)])
            e += [[Sym('unit'), Sym('1')], [Sym('exclude_from_sim'), Sym('no')], [Sym('in_bom'), Sym('yes')], [Sym('on_board'), Sym('yes')],
                  [Sym('dnp'), Sym('no')], [Sym('uuid'), new_uuid()]]
            ispwr = getattr(P, 'is_power', False)
            ra = P.ref_at or (X + 2.54, Y - 2.54); va = P.val_at or (X + 2.54, Y + 1.27)
            pa = str((360 - P.rot) % 360)   # metin sembolle dönmesin
            def prop(k, v, at, hide):
                pe = [Sym('property'), k, v, [Sym('at'), g(at[0]), g(at[1]), Sym(pa)]]
                if hide: pe.append([Sym('hide'), Sym('yes')])
                fx = [Sym('effects'), [Sym('font'), [Sym('size'), g(SZ_PROP), g(SZ_PROP)]]]
                if getattr(P, 'just', 'left') != 'center': fx.append([Sym('justify'), Sym(getattr(P, 'just', 'left'))])   # center = justify yok
                pe.append(fx)
                return pe
            e.append(prop('Reference', P.ref, ra, ispwr))
            e.append(prop('Value', P.value, va, P.hide_value))
            e.append(prop('Footprint', P.footprint, (X, Y), True))
            e.append(prop('Datasheet', '', (X, Y), True))
            e.append(prop('Description', '', (X, Y), True))
            for k, v in P.fields.items(): e.append(prop(k, v, (X, Y), True))
            for num in P.pins: e.append([Sym('pin'), num, [Sym('uuid'), new_uuid()]])
            e.append([Sym('instances'), [Sym('project'), PROJECT, [Sym('path'), '/' + ROOT_UUID, [Sym('reference'), P.ref], [Sym('unit'), Sym('1')]]]])
            out.append(e)
        out.append([Sym('sheet_instances'), [Sym('path'), '/', [Sym('page'), '1']]])
        return ser(out) + '\n'

# ======================================================================
def build():
    """Yerleşim (sinyal akışı soldan sağa, y aşağı, mm, 1,27 ızgara):
         sol sütun  : CT ön ucu (üst, ESP üst pinleri IO4–7) / I²C sensörler (alt, IO8–9)  → teller kesişmez
         orta       : ESP32-S3 (EN devresi, NC pinler, notlar)
         sağ sütun  : servis başlığı (etiket) / RS-485 (MAX3485 aynalı → pin sırası ESP ile aynı, kesişmesiz) / anten / genişleme
         alt        : besleme zinciri (güç netleri sembolle)
       Ana hatlar tel: I²C bus (SDA x=124,46 / SCL x=127), CT_L1…N, UART1 ↔ MAX3485. Etiket: VSENSE, V_BIAS, 5V_RAW,
       servis/genişleme başlıkları (aynı ad = aynı net). Kaçınılmaz kesişmeler kicad-cli --draw-hop-over ile atlama yayı."""
    S = Sch()
    S.libsyms['GridUp:MLX90640'] = mlx90640_symbol(); S.libsyms['GridUp:SHT31'] = sht31_symbol(); S.libsyms['GridUp:MAX3485'] = max3485_symbol()
    R = S.use('Device', 'R'); C = S.use('Device', 'C'); CP = S.use('Device', 'C_Polarized')
    DS = S.use('Device', 'D_Schottky'); FU = S.use('Device', 'Fuse'); RV = S.use('Device', 'Varistor')
    ESP = S.use('RF_Module', 'ESP32-S3-WROOM-1'); SHT = 'GridUp:SHT31'
    MAX = 'GridUp:MAX3485'; RAC = 'GridUp:RAC05-05SK'; S.libsyms[RAC] = rac05_symbol()
    LDO = S.use('Regulator_Linear', 'AP7361C-33E'); SW = S.use('Switch', 'SW_Push')
    BOOST = S.use('Regulator_Switching', 'TPS61099DRV'); IND = S.use('Device', 'L')
    C02 = S.use('Connector_Generic', 'Conn_01x02'); C03 = S.use('Connector_Generic', 'Conn_01x03')
    C04 = S.use('Connector_Generic', 'Conn_01x04'); C25 = S.use('Connector_Generic', 'Conn_02x05_Odd_Even')
    COAX = S.use('Connector', 'Conn_Coaxial')
    I2C, ANA, UART = COL['I2C'], COL['ANA'], COL['UART']

    # ---------- başlık / lejant ----------
    S.text('Modül bağlantı şeması / ESP32-S3-WROOM-1U etrafında (03-pinout §3.1–3.6)', (25.4, 33.0), SZ_TITLE, bold=True)
    S.text('KiCad şematik (eda/GridUp-Modul.kicad_sch): ERC 0 hata / 0 uyarı, netlist §3.1 tablosuyla otomatik doğrulanmış. Kavramsal / üretim çizimi değildir (§1.4); pasif değerler tipik.', (25.4, 37.5), SZ_NOTE)
    S.text('Lejant (tel / etiket rengi) / aynı adlı etiketler aynı nettir;', (222.0, 26.0), SZ_NOTE, bold=True)
    S.text('tel kesişmeleri atlama yayıyla gösterilir (bağlantı yok):', (222.0, 28.5), SZ_NOTE, bold=True)
    legend = [('3V3', COL['3V3']), ('5 V / 230 V', COL['5V']), ('GND / PE', COL['GND']), ('I²C', I2C),
              ('UART / RS-485', UART), ('analog (CT, algılama)', ANA), ('diğer / bileşen içi', COL['DEF'])]
    for k, (name, c) in enumerate(legend):
        row, colm = divmod(k, 4)
        x = 222.0 + colm * (26.0 if row == 0 else 34.0); y = 33.0 + row * 4.5
        S.gline((x, y - 0.7), (x + 5.0, y - 0.7), c); S.text(name, (x + 6.0, y), SZ_NOTE, color=c)

    # ================= ORTA: ESP32-S3 =================
    S.rect((130.0, 42.0), (222.0, 150.0), COL['DEF'], title='ESP32-S3-WROOM-1U-N8 / Wi-Fi/BLE, U.FL anten')
    U1 = S.part(ESP, 'U1', 'ESP32-S3-WROOM-1U-N8', (185.42, 100.33), ref_at=(171.2, 131.5), val_at=(183.0, 134.0),
                footprint='RF_Module:ESP32-S3-WROOM-1U')
    U1.just = 'right'   # ref/val GND teline sağdan dayalı
    S.pin_power(U1, '3V3', '+3V3'); S.pin_power(U1, '40', 'GND')      # 3V3 üst, GND alt (1/40/41 aynı nokta)
    for k, v in {'IO1': 'VSENSE', 'IO10': 'GPIO10', 'IO11': 'GPIO11'}.items(): S.pin_label(U1, k, v)
    for k, v in {'USB_D-': 'USB_DN', 'USB_D+': 'USB_DP', 'TXD0': 'U0TXD', 'RXD0': 'U0RXD'}.items(): S.pin_label(U1, k, v)
    for k in ['IO0', 'IO2', 'IO3', 'IO12', 'IO13', 'IO14', 'IO15', 'IO16', 'IO35', 'IO36', 'IO37', 'IO38', 'IO39', 'IO40', 'IO41', 'IO42',
              'IO45', 'IO46', 'IO47', 'IO48']:
        S.pin_nc(U1, k)
    S.text('ADC yalnız ADC1 (ADC2 Wi-Fi ile çalışmaz); strapping IO0/3/45/46 boş bırakılır', (132.08, 140.0), SZ_NOTE, italic=True)
    S.text('IO35–37: N8 modülünde serbest (R8/R16V PSRAM kullanır), gereksinim yok → NC', (132.08, 143.0), SZ_NOTE, italic=True)
    S.text('U.FL harici anten (1U) / sembolde pin yok, bkz. J8; GPIO10/11 → genişleme (J6)', (132.08, 146.0), SZ_NOTE, italic=True)
    # EN: 10k → 3V3, 1 µF → GND, reset butonu
    en = U1.p('EN'); n_en = (149.86, en[1]); S.wire(en, n_en)
    Ren = S.part(R, 'R1', '10k', (149.86, en[1] - 3.81), ref_at=(151.13, en[1] - 6.35), val_at=(151.13, en[1] - 3.81))
    S.wire(Ren.p('2'), n_en); S.pin_power(Ren, '1', '+3V3')
    Cen = S.part(C, 'C1', '1 µF', (149.86, en[1] + 3.81), ref_at=(143.51, en[1] + 2.54), val_at=(142.24, en[1] + 5.08))
    S.wire(n_en, Cen.p('1')); S.pin_power(Cen, '2', 'GND')
    SW1 = S.part(SW, 'SW1', 'Reset', (140.97, en[1]), ref_at=(138.43, en[1] - 3.81), val_at=(137.16, en[1] - 6.35))
    S.wire(SW1.p('2'), n_en); S.junction(n_en)
    S.pin_power(SW1, '1', 'GND', L=2.54, rot=0)
    S.text('EN: RC + reset butonu', (132.08, en[1] - 17.5), SZ_NOTE, italic=True)

    # ================= SOL ÜST: CT ön ucu ×4 → IO4–IO7 =================
    S.rect((27.94, 42.0), (121.0, 136.0), ANA, title='CT ×4 (analizör yoksa) / burden, V_bias, RC → ADC1')
    trunk_x = [119.38, 116.84, 114.3, 111.76]           # satır 1 en sağ dikey → kesişmesiz merdiven
    for k, (nm, pin) in enumerate([('CT L1', 'IO4'), ('CT L2', 'IO5'), ('CT L3', 'IO6'), ('CT nötr', 'IO7')]):
        y0 = 54.61 + k * 15.24
        J = S.part(C02, 'J%d' % (2 + k), nm, (43.18, y0), mirror='y', ref_at=(53.34, y0 - 1.5), val_at=(33.02, y0 - 1.27),
                   footprint='TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-3-2-5.08_1x02_P5.08mm_Horizontal')
        J.just = 'right'   # aynalı sembolde KiCad hizayı da aynalar: 'right' → metin sağa akar, çerçeve içinde kalır
        hot = J.p('1'); ret = J.p('2')
        nA = (60.96, hot[1]); S.wire(hot, nA, color=ANA)
        Rb = S.part(R, 'R%d' % (10 + k), 'R_burden', (60.96, hot[1] + 3.81), ref_at=(62.23, hot[1] + 1.27), val_at=(62.23, hot[1] + 3.81))
        S.wire(nA, Rb.p('1'), color=ANA); S.junction(nA)
        nB2 = Rb.p('2'); S.wire(ret, (54.61, ret[1]), (54.61, nB2[1]), nB2, color=ANA); S.junction(nB2)   # CT dönüş → V_bias
        vb = (nB2[0], nB2[1] + 3.81); S.wire(nB2, vb, color=ANA); S.label('V_BIAS', vb, 0)
        Rr = S.part(R, 'R%d' % (20 + k), '1k', (76.2, hot[1]), rot=90, ref_at=(70.5, hot[1] - 2.0), val_at=(78.0, hot[1] - 2.0))
        S.wire(nA, Rr.p('1'), color=ANA)
        nB = (88.9, hot[1]); S.wire(Rr.p('2'), nB, color=ANA); S.junction(nB)
        Cr = S.part(C, 'C%d' % (10 + k), '100 nF', (88.9, hot[1] + 3.81), ref_at=(90.17, hot[1] + 1.27), val_at=(90.17, hot[1] + 3.81))
        S.wire(nB, Cr.p('1'), color=ANA); S.pin_power(Cr, '2', 'GND')
        tx = trunk_x[k]; pe = U1.p(pin)
        S.wire(nB, (tx, hot[1]), (tx, pe[1]), pe, color=ANA)          # satır → dikey → ESP pini
        if abs(pe[1] - hot[1]) > 6:  S.label(['CT_L1', 'CT_L2', 'CT_L3', 'CT_N'][k], (tx, pe[1] - 1.27), 90)   # dikey gövde üstünde
        else:                         S.label(['CT_L1', 'CT_L2', 'CT_L3', 'CT_N'][k], (104.14, hot[1]), 0)
    # V_bias = 3V3/2: 2× 100 kΩ + 10 µF (CT ön yargı)
    Rv1 = S.part(R, 'R30', '100k', (33.02, 114.3), ref_at=(34.29, 111.76), val_at=(34.29, 114.3))
    S.pin_power(Rv1, '1', '+3V3', L=2.54)
    nV = (33.02, 120.65); S.wire(Rv1.p('2'), nV, color=ANA)
    Rv2 = S.part(R, 'R31', '100k', (33.02, 127.0), ref_at=(34.29, 124.46), val_at=(34.29, 127.0))
    S.wire(nV, Rv2.p('1'), color=ANA); S.pin_power(Rv2, '2', 'GND', L=1.27)
    S.wire(nV, (44.45, nV[1]), color=ANA); S.junction(nV)
    Cv = S.part(C, 'C20', '10 µF', (44.45, 127.0), ref_at=(45.72, 124.46), val_at=(45.72, 127.0))
    S.wire((44.45, nV[1]), Cv.p('1'), color=ANA); S.pin_power(Cv, '2', 'GND', L=1.27); S.junction((44.45, nV[1]))
    S.wire((44.45, nV[1]), (53.34, nV[1]), color=ANA); S.label('V_BIAS', (53.34, nV[1]), 0)
    S.text('V_BIAS = 3V3 / 2 = 1,65 V (CT DC ofseti)', (66.04, 121.92), SZ_NOTE, italic=True)
    S.text('R_burden = 1,5 V / I_sek,tepe', (66.04, 124.46), SZ_NOTE, italic=True)
    S.text('(CT oranına göre; CT seçimi 02-bom §2.3)', (66.04, 127.0), SZ_NOTE, italic=True)

    # ================= SOL ALT: I²C sensörler → IO8/IO9 (bus) =================
    S.rect((27.94, 139.7), (121.0, 214.63), I2C, title='I²C / MLX90640 0x33 + SHT31 0x44, tek hat 400 kHz+')
    BX_SDA, BX_SCL = 124.46, 127.0
    sda_pin, scl_pin = U1.p('IO8'), U1.p('IO9')
    U2 = S.part('GridUp:MLX90640', 'U2', 'MLX90640ESF-BAA', (69.85, 163.83), ref_at=(35.56, 167.64), val_at=(35.56, 170.18),
                footprint='Package_TO_SOT_THT:TO-39-4')
    S.pin_power(U2, 'GND', 'GND')
    vdd = U2.p('VDD'); n_vdd = (69.85, vdd[1] - 1.27); S.wire(vdd, n_vdd, color=COL['3V3']); S.power('+3V3', n_vdd)
    S.wire(n_vdd, (52.07, n_vdd[1]), color=COL['3V3']); S.junction(n_vdd)
    Cm1 = S.part(C, 'C2', '100 nF', (52.07, n_vdd[1] + 3.81), ref_at=(44.45, n_vdd[1] + 2.54), val_at=(41.66, n_vdd[1] + 6.1))
    S.wire((52.07, n_vdd[1]), Cm1.p('1'), color=COL['3V3']); Pc = S.pin_power(Cm1, '2', 'GND')
    Pc.val_at = (Cm1.p('2')[0] - 2.0, Cm1.p('2')[1] + 2.54 + 1.27); Pc.just = 'right'   # GND etiketi solda (sağda U2 kutusu)
    S.text('termal dizi 32×24, ≤23 mA', (30.5, 179.6), SZ_NOTE, italic=True)
    S.text('görüş açısı 110°×75°', (30.5, 182.4), SZ_NOTE, italic=True)
    U3 = S.part(SHT, 'U3', 'SHT31-DIS-B', (69.85, 196.85), ref_at=(35.56, 203.5), val_at=(35.56, 206.0),
                footprint='Sensor_Humidity:Sensirion_DFN-8-1EP_2.5x2.5mm_P0.5mm_EP1.1x1.7mm')
    v3 = U3.p('VDD'); n3 = (v3[0], v3[1] - 1.27); S.wire(v3, n3, (62.23, n3[1]), color=net_color('+3V3')); S.power('+3V3', (62.23, n3[1]))   # ok solda: U2 GND ile karşı karşıya durmasın
    S.pin_power(U3, '8', 'GND')
    Pg = S.pin_power(U3, 'ADDR', 'GND', L=10.16, rot=270); Pv = S.pin_power(U3, '~{RESET}', '+3V3', L=15.24, rot=90)
    ga, ra = U3.p('ADDR'), U3.p('~{RESET}')
    Pg.val_at = (ga[0] - 10.16 - 1.27, ga[1] - 2.0); Pg.just = 'center'        # yatay GND: etiket sembolün üstünde
    Pv.val_at = (ra[0] - 15.24 - 1.27, ra[1] + 3.3); Pv.just = 'center'        # yatay +3V3: etiket sembolün altında
    S.pin_nc(U3, 'ALERT'); S.pin_nc(U3, 'R')
    S.text('sıcaklık + nem', (119.5, 209.5), SZ_NOTE, italic=True, just='right')
    S.text('ADDR → GND: 0x44', (119.5, 212.35), SZ_NOTE, italic=True, just='right')
    # bus: SDA x=124,46 (IO8 satırından SHT SDA'ya), SCL x=127 (IO9 satırından SHT SCL'ye)
    m_sda, m_scl, s_sda, s_scl = U2.p('SDA'), U2.p('SCL'), U3.p('SDA'), U3.p('SCL')
    S.wire(sda_pin, (BX_SDA, sda_pin[1]), (BX_SDA, s_sda[1]), color=I2C)
    S.wire(scl_pin, (BX_SCL, scl_pin[1]), (BX_SCL, s_scl[1]), color=I2C)
    S.wire(m_sda, (BX_SDA, m_sda[1]), color=I2C); S.junction((BX_SDA, m_sda[1]))
    S.wire(m_scl, (BX_SCL, m_scl[1]), color=I2C); S.junction((BX_SCL, m_scl[1]))     # SDA dikeyini keser → atlama
    S.wire(s_sda, (BX_SDA, s_sda[1]), color=I2C); S.wire(s_scl, (BX_SCL, s_scl[1]), color=I2C)
    S.label('SDA', (BX_SDA + 1.27, sda_pin[1]), 0); S.label('SCL', (BX_SCL + 1.27 + 6.35, scl_pin[1]), 0)
    # pull-up'lar 2× 4,7 kΩ → 3V3
    for i, (x, bx, net) in enumerate([(113.03, BX_SDA, 'SDA'), (100.33, BX_SCL, 'SCL')]):   # SDA sağda/üstte, SCL solda/altta → yatay teller gövde kesmez
        yb = 184.15 + i * 5.08
        Rp = S.part(R, 'R%d' % (2 + i), '4,7k', (x, yb - 3.81), ref_at=(x - 6.0, yb - 6.35), val_at=(x - 6.6, yb - 3.81))
        S.pin_power(Rp, '1', '+3V3', L=1.27)
        S.wire(Rp.p('2'), (x, yb), (bx, yb), color=I2C); S.junction((bx, yb))

    # ================= SAĞ SÜTUN =================
    # servis başlığı (etiket / sahada bağlı değil)
    S.rect((222.0, 42.0), (322.0, 58.0), UART, title='Servis başlığı / USB + UART0, sahada bağlı değil')
    J9 = S.part(C04, 'J9', 'Servis USB/UART0', (259.08, 50.8), ref_at=(263.0, 49.0), val_at=(263.0, 52.0),
                footprint='Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical')
    for num, net in [('1', 'U0TXD'), ('2', 'U0RXD'), ('3', 'USB_DN'), ('4', 'USB_DP')]: S.pin_label(J9, num, net)
    # RS-485: MAX3485 aynalı (mirror x) → DI / DE / RE / RO sırası ESP IO17 / IO21 / IO18 ile kesişmesiz
    S.rect((222.0, 60.5), (322.0, 116.0), UART, title='RS-485 / Modbus RTU / MAX3485 3,3 V, yarıçift, 120 Ω sonlandırma')
    U4 = S.part(MAX, 'U4', 'MAX3485', (254.0, 87.63), ref_at=(233.68, 73.66), val_at=(233.68, 76.2),
                footprint='Package_SO:SOIC-8_3.9x4.9mm_P1.27mm')
    S.pin_power(U4, 'VCC', '+3V3'); S.pin_power(U4, 'GND', 'GND')
    di, de, re_, ro = U4.p('DI'), U4.p('DE'), U4.p('~{RE}'), U4.p('RO')
    p17, p18, p21 = U1.p('IO17'), U1.p('IO18'), U1.p('IO21')
    S.wire(p17, di, color=UART)                                                     # IO17 (U1TXD) → DI, düz
    n_de = (de[0] - 3.81, de[1]); n_re = (re_[0] - 3.81, re_[1])
    S.wire(de, n_de, n_re, re_, color=UART); S.junction(n_re)
    S.wire(p21, (226.06, p21[1]), (226.06, n_re[1]), n_re, color=UART)              # IO21 (DE/RE) → RE+DE
    S.wire(p18, (232.41, p18[1]), (232.41, ro[1]), ro, color=UART)                  # IO18 (U1RXD) → RO
    S.label('U1TXD', (205.74, p17[1]), 0); S.label('DE_RE', (205.74, p21[1]), 0); S.label('U1RXD', (205.74, p18[1]), 0)
    A, B = U4.p('A'), U4.p('B')
    J7 = S.part(C03, 'J7', 'RS-485 klemens 1 B / 2 GND / 3 A', (292.1, (A[1] + B[1]) / 2), ref_at=(289.56, min(A[1], B[1]) - 6.35), val_at=(284.48, max(A[1], B[1]) + 5.08),
                footprint='TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-3-3-5.08_1x03_P5.08mm_Horizontal')
    pT, pG, pB = J7.p('1'), J7.p('2'), J7.p('3')       # üst / orta / alt
    top, bot = (B, A) if B[1] < A[1] else (A, B)
    S.wire(top, (pT[0], top[1]), pT, color=UART); S.wire(bot, (pB[0], bot[1]), pB, color=UART)
    Rt = S.part(R, 'R40', '120 Ω', (274.32, (A[1] + B[1]) / 2), ref_at=(267.5, min(A[1], B[1]) + 2.2), val_at=(270.5, max(A[1], B[1]) + 3.2))
    S.wire((274.32, top[1]), Rt.p('1'), color=UART); S.wire((274.32, bot[1]), Rt.p('2'), color=UART); S.junction((274.32, top[1])); S.junction((274.32, bot[1]))
    Pj = S.pin_power(J7, '2', 'GND', L=7.62, rot=270); Pj.val_at = (pG[0] - 7.62 + 0.8, pG[1] - 1.1); Pj.just = 'center'   # yatay GND: etiket B/A telleri arasında
    S.text('hat: enerji analizörü (slave 1, akım) / TVOC-2 (slave 2, yalnız trip-diag.)', (236.22, 110.0), SZ_NOTE, italic=True)
    S.text('A/B bükümlü çift, ekranlı; son cihazda 2. 120 Ω', (236.22, 113.0), SZ_NOTE, italic=True)
    # anten
    S.rect((222.0, 119.0), (322.0, 150.0), COL['DEF'], title='Anten / U.FL pigtail → SMA panel → dış anten (pano dış yüzü)')
    J8 = S.part(COAX, 'J8', 'SMA panel', (259.08, 133.35), ref_at=(262.9, 131.6), val_at=(262.9, 134.4), footprint='Connector_Coaxial:SMA_Amphenol_132134_Vertical')
    S.pin_nc(J8, '1'); S.pin_power(J8, '2', 'GND')
    S.text('U.FL pigtail (modül konnektörü) / RF, şemada net değil; mevcut kablo girişinden', (228.6, 147.5), SZ_NOTE, italic=True)
    # genişleme
    S.rect((222.0, 153.0), (322.0, 190.0), COL['DEF'], title='Genişleme 2×5 (boş) / PD / akustik için ayrılmış (§7.1); kör tapa')
    J6 = S.part(C25, 'J6', 'Genişleme 2×5', (262.89, 173.99), ref_at=(264.16, 163.5), val_at=(257.81, 184.0), footprint='Connector_PinHeader_2.54mm:PinHeader_2x05_P2.54mm_Vertical')
    for num, name, dx in [('1', '+3V3', -3.81), ('2', '+5V', 3.81)]:
        a0 = J6.p(num); b0 = (a0[0] + dx, a0[1]); c0 = (b0[0], b0[1] - 5.08)
        S.wire(a0, b0, c0, color=net_color(name)); S.power(name, c0)
    g3 = S.pin_power(J6, '3', 'GND', L=22.86, rot=270); g4 = S.pin_power(J6, '4', 'GND', L=15.24, rot=90)   # yatay GND, düz gider
    p3, p4 = J6.p('3'), J6.p('4')
    g3.val_at = (p3[0] - 22.86 - 1.3, p3[1] - 1.6); g3.just = 'center'
    g4.val_at = (p4[0] + 15.24 + 1.3, p4[1] - 1.6); g4.just = 'center'
    S.pin_label(J6, '5', 'SDA'); S.pin_label(J6, '6', 'SCL'); S.pin_label(J6, '7', 'GPIO10'); S.pin_label(J6, '8', 'GPIO11')
    S.pin_nc(J6, '9'); S.pin_nc(J6, '10')

    # ================= ALT: Besleme =================
    S.rect((25.4, 216.4), (322.0, 280.0), COL['5V'], title='Besleme / 230 V iç ihtiyaç → RAC05 5 V → D1 (OR) → 5 V rayı → LDO 3V3; yedek: 2× süperkap seri → boost 4,6 V → D2; algılama D1 öncesi (§3.4, §7.3)')
    yL = 228.6
    J1 = S.part(C03, 'J1', 'İç ihtiyaç L / N / PE', (43.18, yL + 2.54), mirror='y', ref_at=(33.8, yL - 6.35), val_at=(30.5, yL - 3.81),
                footprint='TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-3-3-5.08_1x03_P5.08mm_Horizontal')
    J1.just = 'right'   # aynalı sembol: hiza da aynalanır (bkz. CT klemensleri)
    pL, pN, pPE = J1.p('1'), J1.p('2'), J1.p('3')
    F1 = S.part(FU, 'F1', 'T 1 A', (62.23, pL[1]), rot=90, ref_at=(62.23, pL[1] - 5.2), val_at=(62.23, pL[1] - 2.7)); F1.just = 'center'   # yazı sigortanın tam üstünde
    S.wire(pL, F1.p('1'), color=COL['5V'])
    U5 = S.part(RAC, 'U5', 'RAC05-05SK/277', (88.9, pN[1]), ref_at=(76.2, pL[1] + 9.5), val_at=(76.2, pL[1] + 12.0),
                footprint='Converter_ACDC:Converter_ACDC_RECOM_RAC05-xxSK_THT')
    ac_l, ac_n = U5.p('AC(L)'), U5.p('AC(N)')
    S.wire(F1.p('2'), (F1.p('2')[0], ac_l[1]), ac_l, color=COL['5V'])
    S.wire(pN, (66.04, pN[1]), (66.04, ac_n[1]), ac_n, color=COL['5V'])
    RV1 = S.part(RV, 'RV1', 'MOV 275 V', (71.12, (ac_l[1] + ac_n[1]) / 2), ref_at=(73.0, ac_l[1] - 6.8), val_at=(73.0, ac_l[1] - 4.3))   # etiketler L hattının üstünde, gövdeden kılavuz çizgi
    S.gline((72.5, ac_l[1] + 1.7), (73.8, ac_l[1] - 3.7), COL['GND'], 0.2)
    S.wire((71.12, ac_l[1]), RV1.p('1'), color=COL['5V']); S.wire((71.12, ac_n[1]), RV1.p('2'), color=COL['5V']); S.junction((71.12, ac_l[1])); S.junction((71.12, ac_n[1]))
    S.wire(pPE, (pPE[0] + 2.54, pPE[1]), (pPE[0] + 2.54, pPE[1] + 5.08), color=COL['GND']); PEs = S.power('Earth_Protective', (pPE[0] + 2.54, pPE[1] + 5.08)); PEs.hide_value = True; S.text('PE', (pPE[0] + 4.6, pPE[1] + 7.2), SZ_PROP, color=COL['GND'])
    S.flag((pPE[0] + 2.54, pPE[1] + 2.54)); S.junction((pPE[0] + 2.54, pPE[1] + 2.54))   # PE dış kaynak
    S.flag((F1.p('2')[0] + 2.54, ac_l[1])); S.junction((F1.p('2')[0] + 2.54, ac_l[1]))   # L dış kaynak (ERC); sigorta sonrası net
    S.flag((66.04, ac_n[1]), rot=180); S.junction((66.04, ac_n[1]))                     # N dış kaynak (ERC)
    S.pin_nc(U5, 'NC')
    vout = U5.p('+Vout'); Pg5 = S.pin_power(U5, '-Vout', 'GND', L=2.54, rot=0)
    Pg5.val_at = (U5.p('-Vout')[0] + 2.54, U5.p('-Vout')[1] + 4.2); Pg5.just = 'center'   # GND yazısı üçgenin altında, ortalı
    # 5V_RAW → D1 → +5V rayı (ray sağa doğru: D2 dönüşü, +5V, C30, LDO, +3V3)
    nRaw = (vout[0] + 12.7, vout[1]); S.wire(vout, nRaw, color=COL['5V']); S.junction(nRaw)
    S.label('5V_RAW', (vout[0] + 1.27, vout[1]), 0)
    D1 = S.part(DS, 'D1', 'SS34 (OR)', (nRaw[0] + 6.35, vout[1]), mirror='y', ref_at=(nRaw[0] + 6.35, vout[1] - 5.6), val_at=(nRaw[0] + 6.35, vout[1] - 3.2)); D1.just = 'center'   # diyotun tam üstünde
    S.wire(nRaw, D1.p('A'), color=COL['5V'])
    rail_y = vout[1]; ry = rail_y
    U6 = S.part(LDO, 'U6', 'AP7361C-33E 3,3 V / 1 A', (248.92, rail_y), ref_at=(248.92, rail_y - 6.0), val_at=(248.92, rail_y - 3.5),
                footprint='Package_TO_SOT_SMD:SOT-223-3_TabPin2'); U6.just = 'center'   # yazılar kutunun üstünde, ortalı
    vi, vo = U6.p('VI'), U6.p('VO')
    S.wire(D1.p('K'), vi, color=COL['5V'])
    Pg6 = S.pin_power(U6, 'GND', 'GND'); Pg6.val_at = (U6.p('GND')[0] + 1.7, U6.p('GND')[1] + 2.54 + 1.3)   # GND yazısı sembole yakın
    x5 = 218.44; S.power('+5V', (x5, rail_y)); S.junction((x5, rail_y)); S.flag((x5 + 5.08, rail_y)); S.junction((x5 + 5.08, rail_y))
    Ci = S.part(C, 'C30', '10 µF', (231.14, rail_y + 3.81), ref_at=(233.3, rail_y + 3.4), val_at=(233.3, rail_y + 6.0))
    S.wire((231.14, rail_y), Ci.p('1'), color=COL['5V']); Pgi = S.pin_power(Ci, '2', 'GND'); S.junction((231.14, rail_y))
    Pgi.val_at = (Ci.p('2')[0] + 1.7, Ci.p('2')[1] + 2.54 + 1.3)
    n3 = (vo[0] + 7.62, vo[1]); S.wire(vo, n3, color=COL['3V3']); S.junction(n3); S.power('+3V3', (n3[0] + 5.08, rail_y)); S.wire(n3, (n3[0] + 5.08, rail_y), color=COL['3V3'])
    Co = S.part(C, 'C31', '10 µF', (n3[0], rail_y + 3.81), ref_at=(n3[0] + 2.1, rail_y + 3.4), val_at=(n3[0] + 2.1, rail_y + 6.0))
    S.wire(n3, Co.p('1'), color=COL['3V3']); Pgo = S.pin_power(Co, '2', 'GND'); Pgo.val_at = (Co.p('2')[0] + 1.7, Co.p('2')[1] + 2.54 + 1.3)
    # besleme algılama bölücü (D1 öncesi) → VSENSE etiketi (IO1)
    xd = nRaw[0]
    Rd1 = S.part(R, 'R50', '100k', (xd, rail_y + 7.62), ref_at=(xd + 1.27, rail_y + 5.08), val_at=(xd + 1.27, rail_y + 7.62))
    S.wire(nRaw, Rd1.p('1'), color=COL['5V'])
    nS = (xd, rail_y + 13.97); S.wire(Rd1.p('2'), nS, color=ANA); S.junction(nS)
    Rd2 = S.part(R, 'R51', '47k', (xd, rail_y + 20.32), ref_at=(xd + 1.27, rail_y + 17.78), val_at=(xd + 1.27, rail_y + 20.32))
    S.wire(nS, Rd2.p('1'), color=ANA); Pg51 = S.pin_power(Rd2, '2', 'GND'); Pg51.val_at = (Rd2.p('2')[0] + 1.7, Rd2.p('2')[1] + 2.54 + 1.3)
    S.wire(nS, (xd + 5.08, nS[1]), color=ANA); S.label('VSENSE', (xd + 5.08, nS[1]), 0)
    # süperkap yedek: ray → R_şarj → C32 + C33 (2× HV 2,7 V seri, dengeleme R53/R54) → GND; C_sc → U7 boost 4,6 V → D2 → ray
    xs = 133.35
    S.junction((xs, ry))
    Rs = S.part(R, 'R52', 'R_şarj 22 Ω', (xs, ry + 7.62), ref_at=(xs + 1.27, ry + 5.08), val_at=(xs - 0.4, ry + 7.62))   # Arial'da ortalı yazı sağa kayıyor → sola telafi
    S.wire((xs, ry), Rs.p('1'), color=COL['5V'])
    nC = (xs, ry + 13.97); S.wire(Rs.p('2'), nC); S.junction(nC)
    C32 = S.part(CP, 'C32', 'HV 10 F', (xs, ry + 20.32), ref_at=(xs - 2.54, ry + 19.05), val_at=(xs - 1.9, ry + 21.59)); C32.just = 'right'
    nM = (xs, ry + 24.13); S.wire(nC, C32.p('1')); S.wire(C32.p('2'), nM); S.junction(nM)
    C33 = S.part(CP, 'C33', 'HV 10 F', (xs, ry + 30.48), ref_at=(xs - 2.54, ry + 29.21), val_at=(xs - 1.9, ry + 31.75)); C33.just = 'right'
    nG = (xs, ry + 34.29); S.wire(nM, C33.p('1')); S.wire(C33.p('2'), nG); S.junction(nG); S.power('GND', nG, 0)
    xb = xs + 10.16   # dengeleme dirençleri (hücre başına 10 k); süperkap etiketlerine yer kalsın diye 10 mm sağda
    R53 = S.part(R, 'R53', '10k', (xb, ry + 20.32), ref_at=(xb + 1.27, ry + 17.78), val_at=(xb + 1.27, ry + 20.32))
    R54 = S.part(R, 'R54', '10k', (xb, ry + 30.48), ref_at=(xb + 1.27, ry + 27.94), val_at=(xb + 1.27, ry + 30.48))
    S.wire((xb, nC[1]), R53.p('1')); S.wire(R53.p('2'), (xb, nM[1]), nM); S.junction((xb, nC[1])); S.junction((xb, nM[1]))
    S.wire((xb, nM[1]), R54.p('1')); S.wire(R54.p('2'), (xb, nG[1]), nG)
    # boost U7: VI/EN sol, SW/VOUT/FB sağ, GND alt. Gövde küçük → pin adları küçük yazı (VOUT/GND üst üste binmesin)
    S.libsyms[BOOST] = scale_pin_fonts(S.libsyms[BOOST], 1.1, 1.0)
    ux = 170.18
    U7 = S.part(BOOST, 'U7', 'TPS61099 4,6 V', (ux, ry + 19.05), ref_at=(ux, ry + 32.3), val_at=(ux, ry + 35.0),
                footprint='Package_SON:WSON-6-1EP_2x2mm_P0.65mm_EP1x1.6mm'); U7.just = 'center'   # GND sembolünün altında, ortalı
    vi, en, sw, vb, fb = U7.p('VI'), U7.p('EN'), U7.p('SW'), U7.p('VOUT'), U7.p('FB')
    S.wire(nC, (xb, nC[1]), vi); S.junction(vi); S.wire(vi, en)         # EN = VI (hep açık; Vin < Vout iken yükseltir)
    S.flag((vi[0] - 3.81, vi[1])); S.junction((vi[0] - 3.81, vi[1]))     # süperkap düğümü: dış kaynak (ERC)
    L1 = S.part(IND, 'L1', '2,2 µH', (ux, ry + 8.89), rot=90, ref_at=(ux - 5.1, ry + 7.0), val_at=(ux - 1.9, ry + 7.0))
    S.wire(vi, (vi[0], ry + 8.89), L1.p('1')); S.wire(L1.p('2'), (sw[0], ry + 8.89), sw)
    S.flag((sw[0], ry + 8.89)); S.junction((sw[0], ry + 8.89))                # SW kütüphanede power_in tanımlı → ERC için bayrak
    S.pin_power(U7, '1', 'GND')
    xv = 195.58   # VOUT düğümü: FB bölücü + D2
    S.wire(vb, (xv, vb[1]), color=COL['5V']); S.junction((xv, vb[1]))
    R55 = S.part(R, 'R55', '360k', (xv, ry + 21.59), ref_at=(xv + 1.27, ry + 19.05), val_at=(xv + 1.27, ry + 21.59))
    R56 = S.part(R, 'R56', '100k', (xv, ry + 31.75), ref_at=(xv + 1.27, ry + 29.21), val_at=(xv + 1.27, ry + 31.75))
    S.wire((xv, vb[1]), R55.p('1')); nF = (xv, ry + 27.94); S.wire(R55.p('2'), nF); S.junction(nF); S.wire(nF, R56.p('1')); S.pin_power(R56, '2', 'GND')
    xf = fb[0] + 6.35   # FB dönüşü gövdeden uzak insin
    S.wire(fb, (xf, fb[1]), (xf, nF[1]), nF)
    xD = 208.28
    D2 = S.part(DS, 'D2', 'SS34', (xD, ry + 12.7), rot=270, ref_at=(xD + 2.1, ry + 12.0), val_at=(xD + 2.1, ry + 14.6))
    S.wire((xv, vb[1]), (xD, vb[1]), D2.p('A'), color=COL['5V']); S.wire(D2.p('K'), (xD, ry), color=COL['5V']); S.junction((xD, ry))
    # ---------- notlar (besleme) ----------
    S.text('PE → panonun koruma iletkeni; kutu metal ise gövde PE', (30.48, pPE[1] + 15.5), SZ_NOTE, italic=True)
    S.text('GND: tek yıldız noktası RAC05 çıkışında', (30.48, pPE[1] + 18.3), SZ_NOTE, italic=True)
    S.text('100k/47k → GPIO1 ADC1_CH0: şebeke var/yok → modul_durum.besleme', (35.56, rail_y + 32.5), SZ_NOTE, italic=True)
    xn = 214.0
    S.text('3V3 rayı → ESP32 / MLX90640 / SHT31 / RS-485 / CT bias / genişleme', (xn, ry + 24.0), SZ_NOTE, italic=True)
    S.text('Bütçe: ESP32 Wi-Fi tepe ~350 mA + MLX 23 mA + SHT31 <2 mA + RS-485 ~10 mA', (xn, ry + 26.5), SZ_NOTE, italic=True)
    S.text('→ 5 V/1 A modül; LDO dropout ≈0,3 V (yedekte ray 4,3 V)', (xn, ry + 29.0), SZ_NOTE, italic=True)
    S.text('C32/C33: 2× Eaton HV1030-2R7106-R (10 F, 2,7 V) seri = 5 F; float 4,6 V', (xn, ry + 33.0), SZ_NOTE, italic=True)
    S.text('(+85 °C\'de 2,3 V/hücre, derating); U7 boost 0,7–5,5 V giriş → 4,6 V → D2', (xn, ry + 35.5), SZ_NOTE, italic=True)
    S.text('kesintide ~50 J → ~5 dk @ 50 mA (yalnız alarm paketi; 02-bom §2.5)', (xn, ry + 38.0), SZ_NOTE, italic=True)
    S.text('şebeke varken D2 ters, boost boşta; FB: V_OUT = 1,0 V × (1 + R55/R56) = 4,6 V', (xn, ry + 40.5), SZ_NOTE, italic=True)

    # ---------- notlar ----------
    S.text('Notlar: pin atamaları 03 §3.1 ile aynı; tabloda olmayan tek ekleme GPIO1 besleme algılama. Pasif değerler tipik başlangıç değerleridir.', (35.56, 273.0), SZ_NOTE)
    S.text('Analizör varsa CT ön ucu boş kalır (hedef senaryo, 02-bom §2.3). Kavramsal şema / üretim çizimi değildir (§1.4). Üretim: eda/gen_sch.py → kicad-cli (ERC + SVG).', (35.56, 276.0), SZ_NOTE)
    return S

if __name__ == '__main__':
    S = build()
    with open(os.path.join(HERE, 'GridUp.kicad_sym'), 'w', encoding='utf-8', newline='') as fh:   # özel sembol kütüphanesi (MLX90640)
        ms = list(mlx90640_symbol()); ms[1] = 'MLX90640'
        hs = list(sht31_symbol()); hs[1] = 'SHT31'
        xs = list(max3485_symbol()); xs[1] = 'MAX3485'
        rs = list(rac05_symbol()); rs[1] = 'RAC05-05SK'
        fh.write(ser([Sym('kicad_symbol_lib'), [Sym('version'), Sym('20241209')], [Sym('generator'), 'gen_sch'], [Sym('generator_version'), '10.0'], ms, hs, xs, rs]) + '\n')
    libs = ['Device', 'power', 'RF_Module', 'Sensor_Humidity', 'Interface_UART', 'Converter_ACDC', 'Regulator_Linear', 'Regulator_Switching', 'Switch', 'Connector', 'Connector_Generic']
    with open(os.path.join(HERE, 'sym-lib-table'), 'w', encoding='utf-8', newline='') as fh:
        fh.write('(sym_lib_table\n  (version 7)\n')
        for l in libs: fh.write('  (lib (name "%s")(type "KiCad")(uri "${KICAD10_SYMBOL_DIR}/%s.kicad_sym")(options "")(descr ""))\n' % (l, l))
        fh.write('  (lib (name "GridUp")(type "KiCad")(uri "${KIPRJMOD}/GridUp.kicad_sym")(options "")(descr "proje sembolleri"))\n)\n')
    fps = ['TerminalBlock_Phoenix', 'Connector_Coaxial', 'Connector_PinHeader_2.54mm', 'Converter_ACDC', 'Package_SO', 'Package_SON', 'Package_TO_SOT_SMD', 'Package_TO_SOT_THT', 'RF_Module', 'Sensor_Humidity']
    with open(os.path.join(HERE, 'fp-lib-table'), 'w', encoding='utf-8', newline='') as fh:
        fh.write('(fp_lib_table\n  (version 7)\n')
        for l in fps: fh.write('  (lib (name "%s")(type "KiCad")(uri "${KICAD10_FOOTPRINT_DIR}/%s.pretty")(options "")(descr ""))\n' % (l, l))
        fh.write(')\n')
    out = os.path.join(HERE, PROJECT + '.kicad_sch')
    with open(out, 'w', encoding='utf-8', newline='') as fh: fh.write(S.emit('GridUp modül bağlantı şeması / ESP32-S3-WROOM-1U'))
    pro = os.path.join(HERE, PROJECT + '.kicad_pro')
    if not os.path.exists(pro):
        with open(pro, 'w', encoding='utf-8', newline='') as fh:
            json.dump({"meta": {"filename": PROJECT + ".kicad_pro", "version": 3},
                       "schematic": {"drawing": {"default_font": "KiCad Font", "hop_over_size_choice": 2, "text_offset_ratio": 0.3}, "legacy_lib_dir": "", "legacy_lib_list": []},   # hop_over 0 = atlama yayı kapalı
                       "sheets": [[ROOT_UUID, "Root"]], "text_variables": {}}, fh, indent=2, ensure_ascii=False)
    print('yazıldı', out, len(S.parts), 'parça', len(S.items), 'öğe')
