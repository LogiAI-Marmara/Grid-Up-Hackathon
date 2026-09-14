# GridUp modül bağlantı şeması — KiCad .kicad_sch üreteci (elle çizim yok, kaynak model bu dosya).
# Semboller KiCad kütüphanesinden (share/kicad/symbols) okunup lib_symbols'a gömülür; pin uçları kütüphane
# geometrisinden hesaplanır. Netler: 03-pinout.md §3.1–3.6 (I²C GPIO8/9, CT GPIO4–7 ADC1, UART1 GPIO17/18
# + DE/RE GPIO21, besleme algılama GPIO1, genişleme GPIO10/11; RAC05 → D1 → 5 V → LDO 3V3; süperkap R_şarj + D2).
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

def pins_of(sym):
    """[(number, name, x, y_up, angle, type)] — tüm birimlerden."""
    out = []
    for unit in find(sym, 'symbol'):
        for p in find(unit, 'pin'):
            at = find1(p, 'at'); num = find1(p, 'number')[1]; nm = find1(p, 'name')[1]
            out.append((num, nm, float(at[1]), float(at[2]), int(float(at[3])), str(p[1])))
    return out

def mlx90640_symbol():
    """Kütüphanede yok — TO-39 4 pinli özel sembol."""
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
             [Sym('rectangle'), [Sym('start'), Sym('-7.62'), Sym('7.62')], [Sym('end'), Sym('7.62'), Sym('-7.62')],
              [Sym('stroke'), [Sym('width'), Sym('0.254')], [Sym('type'), Sym('default')]], [Sym('fill'), [Sym('type'), Sym('background')]]],
             [Sym('circle'), [Sym('center'), Sym('0'), Sym('0')], [Sym('radius'), Sym('4.5')],
              [Sym('stroke'), [Sym('width'), Sym('0.254')], [Sym('type'), Sym('default')]], [Sym('fill'), [Sym('type'), Sym('none')]]]],
            [Sym('symbol'), 'MLX90640_1_1',
             pin('power_in', 0, 10.16, 270, 'VDD', '1'), pin('power_in', 0, -10.16, 90, 'GND', '2'),
             pin('bidirectional', 10.16, 2.54, 180, 'SDA', '3'), pin('input', 10.16, -2.54, 180, 'SCL', '4')]]

# ---------------- şema ----------------
def g(v): return Sym('%g' % round(v, 4))
_uuid_n = [0]
def new_uuid():   # deterministik: aynı girdi → aynı dosya (diff sadece gerçek değişiklikte)
    _uuid_n[0] += 1
    return str(uuid.uuid5(uuid.UUID(ROOT_UUID), 'gridup-%d' % _uuid_n[0]))
FONT = lambda: [Sym('effects'), [Sym('font'), [Sym('size'), Sym('1.27'), Sym('1.27')]]]

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
        if lid not in self.libsyms: self.libsyms[lid] = lib_symbol(lib, name)
        return lid
    def part(self, lib_id, ref, value, at, rot=0, mirror=None, ref_at=None, val_at=None, hide_value=False, footprint='', fields=None):
        P = Part(self, lib_id, ref, value, at, rot, mirror, footprint, fields); self.parts.append(P)
        P.ref_at, P.val_at, P.hide_value = ref_at, val_at, hide_value
        return P
    def power(self, name, at, rot=0):
        self.pwr_n += 1
        lid = self.use('power', name)
        P = self.part(lid, '#PWR%02d' % self.pwr_n, name, at, rot); P.is_power = True
        return P
    def flag(self, at, rot=0):
        self.pwr_n += 1
        lid = self.use('power', 'PWR_FLAG')
        P = self.part(lid, '#FLG%02d' % self.pwr_n, 'PWR_FLAG', at, rot, hide_value=True); P.is_power = True
        return P
    def wire(self, *pts):
        for a, b in zip(pts, pts[1:]):
            if a == b: continue
            self.items.append([Sym('wire'), [Sym('pts'), [Sym('xy'), g(a[0]), g(a[1])], [Sym('xy'), g(b[0]), g(b[1])]],
                               [Sym('stroke'), [Sym('width'), Sym('0')], [Sym('type'), Sym('default')]], [Sym('uuid'), new_uuid()]])
    def junction(self, at):
        self.items.append([Sym('junction'), [Sym('at'), g(at[0]), g(at[1])], [Sym('diameter'), Sym('0')],
                           [Sym('color'), Sym('0'), Sym('0'), Sym('0'), Sym('0')], [Sym('uuid'), new_uuid()]])
    def label(self, text, at, rot=0):
        just = {0: 'left bottom', 180: 'right bottom', 90: 'left bottom', 270: 'right bottom'}[rot]
        self.items.append([Sym('label'), text, [Sym('at'), g(at[0]), g(at[1]), Sym(str(rot))],
                           [Sym('effects'), [Sym('font'), [Sym('size'), Sym('1.27'), Sym('1.27')]], [Sym('justify')] + [Sym(j) for j in just.split()]],
                           [Sym('uuid'), new_uuid()]])
    def nc(self, at):
        self.items.append([Sym('no_connect'), [Sym('at'), g(at[0]), g(at[1])], [Sym('uuid'), new_uuid()]])
    def text(self, s, at, size=1.27, bold=False, italic=False, rot=0):
        font = [Sym('font'), [Sym('size'), g(size), g(size)]]
        if bold: font.append([Sym('bold'), Sym('yes')])
        if italic: font.append([Sym('italic'), Sym('yes')])
        self.items.append([Sym('text'), s, [Sym('exclude_from_sim'), Sym('no')], [Sym('at'), g(at[0]), g(at[1]), Sym(str(rot))],
                           [Sym('effects'), font, [Sym('justify'), Sym('left'), Sym('bottom')]], [Sym('uuid'), new_uuid()]])
    def rect(self, a, b):
        self.items.append([Sym('rectangle'), [Sym('start'), g(a[0]), g(a[1])], [Sym('end'), g(b[0]), g(b[1])],
                           [Sym('stroke'), [Sym('width'), Sym('0.2')], [Sym('type'), Sym('dash')]], [Sym('fill'), [Sym('type'), Sym('none')]],
                           [Sym('uuid'), new_uuid()]])
    # pin ucu + kısa tel + etiket / güç sembolü / NC
    def pin_label(self, P, key, text, L=5.08):
        a = P.p(key); b = P.stub(key, L); self.wire(a, b)
        ox, oy = P.out(key)
        rot = 0 if ox > 0.5 else 180 if ox < -0.5 else (90 if oy < -0.5 else 270)
        self.label(text, b, rot)
        return b
    def pin_power(self, P, key, name, L=2.54, rot=None):
        a = P.p(key); b = P.stub(key, L); self.wire(a, b)
        ox, oy = P.out(key)
        if rot is None:
            rot = 0 if oy < 0 else 180 if oy > 0 else (90 if ox > 0.5 else 270)   # gövde tel yönüne doğru
            if name == 'GND': rot = (rot + 180) % 360
        return self.power(name, b, rot)
    def pin_nc(self, P, key): self.nc(P.p(key))

    def emit(self, title):
        out = [Sym('kicad_sch'), [Sym('version'), Sym('20250610')], [Sym('generator'), 'gen_sch'], [Sym('generator_version'), '10.0'],
               [Sym('uuid'), ROOT_UUID], [Sym('paper'), 'A3'],
               [Sym('title_block'), [Sym('title'), title], [Sym('date'), '2026-09-14'], [Sym('rev'), '1'], [Sym('company'), 'Grid Up Hackathon / İZ A'],
                [Sym('comment'), Sym('1'), 'Kavramsal şema — üretim çizimi değildir (karar kaydı §1.4). Pasif değerler tipik başlangıç değerleri.'],
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
                pe.append([Sym('effects'), [Sym('font'), [Sym('size'), Sym('1.27'), Sym('1.27')]], [Sym('justify'), Sym('left')]])
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
    S = Sch()
    S.libsyms['GridUp:MLX90640'] = mlx90640_symbol()
    R = S.use('Device', 'R'); C = S.use('Device', 'C'); CP = S.use('Device', 'C_Polarized')
    DS = S.use('Device', 'D_Schottky'); FU = S.use('Device', 'Fuse'); RV = S.use('Device', 'Varistor')
    ESP = S.use('RF_Module', 'ESP32-S3-WROOM-1'); SHT = S.use('Sensor_Humidity', 'SHT31-DIS')
    MAX = S.use('Interface_UART', 'MAX3485'); RAC = S.use('Converter_ACDC', 'RAC05-05SK')
    LDO = S.use('Regulator_Linear', 'LD1117S33TR_SOT223'); SW = S.use('Switch', 'SW_Push')
    C02 = S.use('Connector_Generic', 'Conn_01x02'); C03 = S.use('Connector_Generic', 'Conn_01x03')
    C04 = S.use('Connector_Generic', 'Conn_01x04'); C25 = S.use('Connector_Generic', 'Conn_02x05_Odd_Even')
    COAX = S.use('Connector', 'Conn_Coaxial')

    # ---------- ESP32-S3 ----------
    U1 = S.part(ESP, 'U1', 'ESP32-S3-WROOM-1U-N8', (185.42, 120.65), ref_at=(195.58, 152.4), val_at=(195.58, 154.94),
                footprint='RF_Module:ESP32-S3-WROOM-1U')
    S.pin_power(U1, '3V3', '+3V3'); S.pin_power(U1, '40', 'GND')      # 3V3 üst, GND alt (1/40/41 aynı nokta)
    left = {'IO8': 'SDA', 'IO9': 'SCL', 'IO4': 'CT_L1', 'IO5': 'CT_L2', 'IO6': 'CT_L3', 'IO7': 'CT_N',
            'IO1': 'VSENSE', 'IO10': 'GPIO10', 'IO11': 'GPIO11'}
    right = {'IO17': 'U1TXD', 'IO18': 'U1RXD', 'IO21': 'DE_RE', 'USB_D-': 'USB_DN', 'USB_D+': 'USB_DP', 'TXD0': 'U0TXD', 'RXD0': 'U0RXD'}
    for k, v in left.items(): S.pin_label(U1, k, v)
    for k, v in right.items(): S.pin_label(U1, k, v)
    for k in ['IO0', 'IO2', 'IO3', 'IO12', 'IO13', 'IO14', 'IO15', 'IO16', 'IO35', 'IO36', 'IO37', 'IO38', 'IO39', 'IO40', 'IO41', 'IO42',
              'IO45', 'IO46', 'IO47', 'IO48']:
        S.pin_nc(U1, k)
    S.text('strapping: IO0 / IO3 / IO45 / IO46 — bağlanmaz; IO35–IO37 flash — kullanılmaz', (129.54, 158.75), 1.0, italic=True)
    S.text('ADC yalnız ADC1 (GPIO1, 4–7, 10) — ADC2 Wi-Fi ile kullanılamaz', (129.54, 156.21), 1.0, italic=True)
    S.text('U.FL harici anten (1U) — sembolde pin yok, bkz. J8', (129.54, 161.29), 1.0, italic=True)
    # EN: 10k → 3V3, 1 µF → GND, reset butonu
    en = U1.p('EN'); n_en = (149.86, en[1]); S.wire(en, n_en)
    Ren = S.part(R, 'R1', '10k', (149.86, en[1] - 3.81), ref_at=(151.13, en[1] - 6.35), val_at=(151.13, en[1] - 3.81))
    S.wire(Ren.p('2'), n_en); S.pin_power(Ren, '1', '+3V3')
    Cen = S.part(C, 'C1', '1 µF', (149.86, en[1] + 3.81), ref_at=(143.51, en[1] + 2.54), val_at=(142.24, en[1] + 5.08))
    S.wire(n_en, Cen.p('1')); S.pin_power(Cen, '2', 'GND')
    SW1 = S.part(SW, 'SW1', 'Reset', (137.16, en[1]), ref_at=(134.62, en[1] - 3.81), val_at=(133.35, en[1] - 6.35))
    S.wire(SW1.p('2'), n_en); S.junction(n_en)
    S.pin_power(SW1, '1', 'GND', L=2.54, rot=0)
    S.text('EN: RC + reset butonu', (129.54, en[1] - 8.89), 1.0, italic=True)

    # ---------- I²C sensörler ----------
    S.text('I²C — tek hat, 400 kHz+, 0x33 ≠ 0x44, 2× 4,7 kΩ pull-up → 3V3', (55.88, 41.91), 1.27, bold=True)
    U2 = S.part('GridUp:MLX90640', 'U2', 'MLX90640ESF-BAA', (78.74, 66.04), ref_at=(57.15, 66.04), val_at=(52.07, 68.58),
                footprint='Package_TO_SOT_THT:TO-39-4')
    S.pin_label(U2, 'SDA', 'SDA'); S.pin_label(U2, 'SCL', 'SCL')
    S.pin_power(U2, 'GND', 'GND')
    vdd = U2.p('VDD'); n_vdd = (78.74, vdd[1] - 3.81); S.wire(vdd, n_vdd); S.power('+3V3', n_vdd)
    S.wire(n_vdd, (66.04, n_vdd[1])); S.junction(n_vdd)
    Cm1 = S.part(C, 'C2', '100 nF', (66.04, n_vdd[1] + 3.81), ref_at=(60.96, n_vdd[1] + 2.54), val_at=(58.42, n_vdd[1] + 5.08))
    S.wire((66.04, n_vdd[1]), Cm1.p('1')); S.pin_power(Cm1, '2', 'GND')
    S.text('termal dizi 32×24, 110°×75°, I²C 0x33', (86.36, 74.93), 1.0, italic=True)
    S.text('≤23 mA, 3,3 V', (86.36, 77.47), 1.0, italic=True)

    U3 = S.part(SHT, 'U3', 'SHT31-DIS-B', (78.74, 109.22), ref_at=(66.04, 97.79), val_at=(66.04, 100.33),
                footprint='Sensor_Humidity:Sensirion_DFN-8-1EP_2.5x2.5mm_P0.5mm_EP1.1x1.7mm')
    S.pin_label(U3, 'SDA', 'SDA'); S.pin_label(U3, 'SCL', 'SCL')
    S.pin_power(U3, 'VDD', '+3V3'); S.pin_power(U3, '8', 'GND')
    S.pin_power(U3, 'ADDR', 'GND', L=7.62, rot=270); S.pin_power(U3, '~{RESET}', '+3V3', L=11.43, rot=90)
    S.pin_nc(U3, 'ALERT'); S.pin_nc(U3, 'R')
    S.text('sıcaklık + nem, I²C 0x44 (ADDR → GND)', (86.36, 118.11), 1.0, italic=True)
    # pull-up'lar
    for i, (x, net) in enumerate([(111.76, 'SDA'), (119.38, 'SCL')]):
        Rp = S.part(R, 'R%d' % (2 + i), '4,7k', (x, 55.88), ref_at=(x + 1.27, 53.34), val_at=(x + 1.27, 55.88))
        S.pin_power(Rp, '1', '+3V3'); S.pin_label(Rp, '2', net, L=3.81)

    # ---------- CT ön ucu ×4 ----------
    S.text('Split-core CT ×4 (analizör yoksa) — L1 / L2 / L3 / nötr, her kanal aynı devre: burden + V_bias, 1 kΩ / 100 nF RC → ADC1', (35.56, 160.02), 1.27, bold=True)
    for k, (nm, net) in enumerate([('CT L1', 'CT_L1'), ('CT L2', 'CT_L2'), ('CT L3', 'CT_L3'), ('CT nötr', 'CT_N')]):
        y0 = 172.72 + k * 15.24
        J = S.part(C02, 'J%d' % (2 + k), nm, (43.18, y0), mirror='y', ref_at=(35.56, y0 - 3.81), val_at=(33.02, y0 - 1.27),
                   footprint='TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-3-2-5.08_1x02_P5.08mm_Horizontal')
        hot = J.p('1'); ret = J.p('2')
        S.pin_label(J, '2', 'V_BIAS', L=3.81)
        nA = (60.96, hot[1]); S.wire(hot, nA)
        Rb = S.part(R, 'R%d' % (10 + k), 'R_burden', (60.96, hot[1] + 3.81), ref_at=(62.23, hot[1] + 1.27), val_at=(62.23, hot[1] + 3.81))
        S.wire(nA, Rb.p('1')); S.pin_label(Rb, '2', 'V_BIAS', L=2.54); S.junction(nA)
        Rr = S.part(R, 'R%d' % (20 + k), '1k', (76.2, hot[1]), rot=90, ref_at=(73.66, hot[1] - 4.45), val_at=(74.93, hot[1] - 1.9))
        S.wire(nA, Rr.p('1'))
        nB = (88.9, hot[1]); S.wire(Rr.p('2'), nB); S.junction(nB)
        Cr = S.part(C, 'C%d' % (10 + k), '100 nF', (88.9, hot[1] + 3.81), ref_at=(90.17, hot[1] + 1.27), val_at=(90.17, hot[1] + 3.81))
        S.wire(nB, Cr.p('1')); S.pin_power(Cr, '2', 'GND')
        S.wire(nB, (96.52, hot[1])); S.label(net, (96.52, hot[1]), 0)
    # V_bias = 3V3/2: 2× 100 kΩ + 10 µF
    Rv1 = S.part(R, 'R30', '100k', (121.92, 176.53), ref_at=(123.19, 173.99), val_at=(123.19, 176.53))
    S.pin_power(Rv1, '1', '+3V3')
    nV = (121.92, 182.88); S.wire(Rv1.p('2'), nV)
    Rv2 = S.part(R, 'R31', '100k', (121.92, 189.23), ref_at=(123.19, 186.69), val_at=(123.19, 189.23))
    S.wire(nV, Rv2.p('1')); S.pin_power(Rv2, '2', 'GND')
    S.wire(nV, (132.08, nV[1])); S.junction(nV)
    Cv = S.part(C, 'C20', '10 µF', (132.08, 189.23), ref_at=(133.35, 186.69), val_at=(133.35, 189.23))
    S.wire((132.08, nV[1]), Cv.p('1')); S.pin_power(Cv, '2', 'GND'); S.junction((132.08, nV[1]))
    S.wire((132.08, nV[1]), (139.7, nV[1])); S.label('V_BIAS', (139.7, nV[1]), 0)
    S.text('V_bias = 3V3/2', (115.57, 170.18), 1.0, italic=True)

    # ---------- RS-485 ----------
    S.text('RS-485 / Modbus RTU — MAX3485 sınıfı, 3,3 V, yarıçift yönlü; 120 Ω sonlandırma; A/B bükümlü çift, ekranlı', (243.84, 88.9), 1.27, bold=True)
    U4 = S.part(MAX, 'U4', 'MAX3485', (274.32, 109.22), ref_at=(264.16, 92.71), val_at=(264.16, 95.25), footprint='Package_SO:SOIC-8_3.9x4.9mm_P1.27mm')
    S.pin_label(U4, 'RO', 'U1RXD'); S.pin_label(U4, 'DI', 'U1TXD')
    re_, de = U4.p('~{RE}'), U4.p('DE'); n_re = (re_[0] - 3.81, re_[1]); n_de = (de[0] - 3.81, de[1])
    S.wire(re_, n_re, n_de, de); S.junction(n_re)
    S.wire(n_re, (n_re[0] - 1.27, n_re[1])); S.label('DE_RE', (n_re[0] - 1.27, n_re[1]), 180)
    S.pin_power(U4, 'VCC', '+3V3'); S.pin_power(U4, 'GND', 'GND')
    A, B = U4.p('A'), U4.p('B')
    J7 = S.part(C03, 'J7', 'RS-485 klemens A / GND / B', (307.34, B[1] - 2.54), ref_at=(304.8, B[1] - 8.89), val_at=(299.72, B[1] + 5.08),
                footprint='TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-3-3-5.08_1x03_P5.08mm_Horizontal')
    pA, pG, pB = J7.p('1'), J7.p('2'), J7.p('3')
    S.wire(A, (pA[0], A[1]), pA); S.wire(B, pB)
    Rt = S.part(R, 'R40', '120 Ω', (292.1, (A[1] + B[1]) / 2), ref_at=(293.37, A[1] - 0.5), val_at=(293.37, B[1] + 0.5))
    S.wire((292.1, A[1]), Rt.p('1')); S.wire((292.1, B[1]), Rt.p('2')); S.junction((292.1, A[1])); S.junction((292.1, B[1]))
    S.pin_power(J7, '2', 'GND', L=5.08, rot=270)
    S.text('→ enerji analizörü (slave 1, akım) / TVOC-2 (slave 2, yalnız trip-diag. kaydı)', (256.54, 132.08), 1.0, italic=True)
    S.text('son cihazda 2. 120 Ω sonlandırma', (256.54, 134.62), 1.0, italic=True)

    # ---------- Anten ----------
    S.text('Anten — U.FL pigtail → SMA panel konnektörü → dış anten (pano dış yüzü, mevcut kablo girişi)', (243.84, 55.88), 1.27, bold=True)
    J8 = S.part(COAX, 'J8', 'SMA panel', (279.4, 66.04), ref_at=(281.94, 60.96), val_at=(281.94, 71.12), footprint='Connector_Coaxial:SMA_Amphenol_132134_Vertical')
    S.pin_nc(J8, '1'); S.pin_power(J8, '2', 'GND')
    S.text('U.FL pigtail (modül konnektörü) — RF, şemada net değil', (256.54, 81.28), 1.0, italic=True)

    # ---------- Servis başlığı ----------
    S.text('Servis başlığı — USB + UART0, sahada bağlı değil', (243.84, 139.7), 1.27, bold=True)
    J9 = S.part(C04, 'J9', 'Servis USB/UART0', (279.4, 147.32), ref_at=(281.94, 141.61), val_at=(281.94, 154.94), footprint='Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical')
    for num, net in [('1', 'USB_DN'), ('2', 'USB_DP'), ('3', 'U0TXD'), ('4', 'U0RXD')]: S.pin_label(J9, num, net)

    # ---------- Genişleme ----------
    S.text('Genişleme başlığı 2×5 (boş) — PD / akustik için ayrılmış, §7.1 şartı; kutuda kör tapa', (243.84, 165.1), 1.27, bold=True)
    J6 = S.part(C25, 'J6', 'Genişleme 2×5', (283.21, 180.34), ref_at=(284.48, 167.64), val_at=(278.13, 190.5), footprint='Connector_PinHeader_2.54mm:PinHeader_2x05_P2.54mm_Vertical')
    for num, name, dx in [('1', '+3V3', -3.81), ('2', '+5V', 3.81)]:      # üst çift: yukarı kırıp dik güç sembolü
        a0 = J6.p(num); b0 = (a0[0] + dx, a0[1]); c0 = (b0[0], b0[1] - 5.08)
        S.wire(a0, b0, c0); S.power(name, c0)
    S.pin_power(J6, '3', 'GND', L=16.51, rot=0); S.pin_power(J6, '4', 'GND', L=11.43, rot=0)
    S.pin_label(J6, '5', 'SDA'); S.pin_label(J6, '6', 'SCL'); S.pin_label(J6, '7', 'GPIO10'); S.pin_label(J6, '8', 'GPIO11')
    S.pin_nc(J6, '9'); S.pin_nc(J6, '10')

    # ---------- Besleme ----------
    S.text('Besleme — 230 V iç ihtiyaç devresi → RAC05 5 V → D1 (OR) → 5 V rayı → LDO 3V3; süperkap R_şarj + D2 yedek; algılama D1 öncesinden (03 §3.4, §7.3)', (35.56, 236.22), 1.27, bold=True)
    yL = 248.92
    J1 = S.part(C03, 'J1', 'İç ihtiyaç L / N / PE', (43.18, yL + 2.54), mirror='y', ref_at=(36.83, yL - 6.35), val_at=(46.99, yL - 3.81),   # mirror: metin sağa yaslı
                footprint='TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-3-3-5.08_1x03_P5.08mm_Horizontal')
    pL, pN, pPE = J1.p('1'), J1.p('2'), J1.p('3')
    F1 = S.part(FU, 'F1', 'sigorta', (58.42, pL[1]), rot=90, ref_at=(55.88, pL[1] - 5.08), val_at=(53.34, pL[1] - 2.54))
    S.wire(pL, F1.p('1'))
    U5 = S.part(RAC, 'U5', 'RAC05-05SK/277', (88.9, pN[1] - 2.54 + 2.54), ref_at=(78.74, pL[1] - 10.16), val_at=(78.74, pL[1] - 7.62),
                footprint='Converter_ACDC:Converter_ACDC_RECOM_RAC05-xxSK_THT')
    # RAC05: AC(L) üstte (+2,54), AC(N) altta (−2,54) → J1 pin1 (üst) L, pin2 N
    ac_l, ac_n = U5.p('AC(L)'), U5.p('AC(N)')
    S.wire(F1.p('2'), (F1.p('2')[0], ac_l[1]), ac_l)
    S.wire(pN, (66.04, pN[1]), (66.04, ac_n[1]), ac_n)
    RV1 = S.part(RV, 'RV1', 'MOV', (71.12, (ac_l[1] + ac_n[1]) / 2), ref_at=(72.39, ac_l[1] - 0.5), val_at=(72.39, ac_n[1] + 0.5))
    S.wire((71.12, ac_l[1]), RV1.p('1')); S.wire((71.12, ac_n[1]), RV1.p('2')); S.junction((71.12, ac_l[1])); S.junction((71.12, ac_n[1]))
    S.wire(pPE, (pPE[0] + 2.54, pPE[1]), (pPE[0] + 2.54, pPE[1] + 5.08)); S.power('Earth_Protective', (pPE[0] + 2.54, pPE[1] + 5.08))
    S.flag((pPE[0] + 2.54, pPE[1] + 2.54)); S.junction((pPE[0] + 2.54, pPE[1] + 2.54))   # PE dış kaynak
    S.flag((F1.p('2')[0] + 2.54, ac_l[1])); S.junction((F1.p('2')[0] + 2.54, ac_l[1]))   # L dış kaynak (ERC)
    S.flag((66.04, ac_n[1]), rot=180); S.junction((66.04, ac_n[1]))                     # N dış kaynak (ERC)
    S.text('PE → panonun koruma iletkeni; kutu metal ise gövde PE', (30.48, pPE[1] + 12.7), 1.0, italic=True)
    S.pin_nc(U5, 'NC')
    vout, gout = U5.p('+Vout'), U5.p('-Vout')
    S.pin_power(U5, '-Vout', 'GND', L=2.54, rot=0)
    # 5V_RAW → D1 → +5V rayı
    nRaw = (vout[0] + 12.7, vout[1]); S.wire(vout, nRaw); S.junction(nRaw)
    S.label('5V_RAW', (vout[0] + 1.27, vout[1]), 0)
    D1 = S.part(DS, 'D1', 'Schottky (OR)', (nRaw[0] + 6.35, vout[1]), mirror='y', ref_at=(nRaw[0] + 2.54, vout[1] - 6.35), val_at=(nRaw[0] + 2.54, vout[1] - 3.81))
    S.wire(nRaw, D1.p('A'))
    rail_y = vout[1]; rail_x0 = D1.p('K')[0]
    U6 = S.part(LDO, 'U6', 'LDO 3,3 V ≥600 mA (LD1117S33)', (182.88, rail_y), ref_at=(177.8, rail_y - 8.89), val_at=(172.72, rail_y - 6.35),
                footprint='Package_TO_SOT_SMD:SOT-223-3_TabPin2')
    vi, vo = U6.p('VI'), U6.p('VO')
    S.wire(D1.p('K'), vi)
    S.pin_power(U6, 'GND', 'GND')
    # rayı besleyen düğümler
    x5 = 156.21; S.power('+5V', (x5, rail_y)); S.junction((x5, rail_y)); S.flag((x5 + 5.08, rail_y)); S.junction((x5 + 5.08, rail_y))
    Ci = S.part(C, 'C30', '10 µF', (166.37, rail_y + 3.81), ref_at=(167.64, rail_y + 1.27), val_at=(167.64, rail_y + 3.81))
    S.wire((166.37, rail_y), Ci.p('1')); S.pin_power(Ci, '2', 'GND'); S.junction((166.37, rail_y))
    # LDO çıkışı → 3V3
    n3 = (vo[0] + 7.62, vo[1]); S.wire(vo, n3); S.junction(n3); S.power('+3V3', (n3[0] + 5.08, rail_y)); S.wire(n3, (n3[0] + 5.08, rail_y))
    Co = S.part(C, 'C31', '10 µF', (n3[0], rail_y + 3.81), ref_at=(n3[0] + 1.27, rail_y + 1.27), val_at=(n3[0] + 1.27, rail_y + 3.81))
    S.wire(n3, Co.p('1')); S.pin_power(Co, '2', 'GND')
    S.text('3V3 rayı → ESP32 / MLX90640 / SHT31 / RS-485 / CT bias / genişleme', (n3[0] + 10.16, rail_y - 6.35), 1.0, italic=True)
    S.text('Bütçe: ESP32 Wi-Fi tepe ~350 mA + MLX 23 mA + SHT31 <2 mA + RS-485 ~10 mA', (n3[0] + 10.16, rail_y - 3.81), 1.0, italic=True)
    S.text('→ 5 V / 1 A modül ve ≥600 mA LDO yeterli', (n3[0] + 10.16, rail_y - 1.27), 1.0, italic=True)
    # besleme algılama bölücü (D1 öncesi)
    xd = nRaw[0]
    Rd1 = S.part(R, 'R50', '100k', (xd, rail_y + 7.62), ref_at=(xd + 1.27, rail_y + 5.08), val_at=(xd + 1.27, rail_y + 7.62))
    S.wire(nRaw, Rd1.p('1'))
    nS = (xd, rail_y + 13.97); S.wire(Rd1.p('2'), nS); S.junction(nS)
    Rd2 = S.part(R, 'R51', '47k', (xd, rail_y + 20.32), ref_at=(xd + 1.27, rail_y + 17.78), val_at=(xd + 1.27, rail_y + 20.32))
    S.wire(nS, Rd2.p('1')); S.pin_power(Rd2, '2', 'GND')
    S.wire(nS, (xd + 7.62, nS[1])); S.label('VSENSE', (xd + 7.62, nS[1]), 0)
    S.text('100k/47k → GPIO1 ADC1_CH0: şebeke var/yok → modul_durum.besleme = sebeke | yedek', (35.56, rail_y + 29.21), 1.0, italic=True)
    # süperkap yedek: ray → R_şarj → C_sc → GND; C_sc → D2 → ray
    xs = 133.35
    S.junction((xs, rail_y))
    Rs = S.part(R, 'R52', 'R_şarj ≈10 Ω', (xs, rail_y + 7.62), ref_at=(xs + 1.27, rail_y + 5.08), val_at=(xs + 1.27, rail_y + 7.62))
    S.wire((xs, rail_y), Rs.p('1'))
    nC = (xs, rail_y + 13.97); S.wire(Rs.p('2'), nC); S.junction(nC)
    Csc = S.part(CP, 'C32', 'C_sc süperkap.', (xs, rail_y + 20.32), ref_at=(xs + 3.81, rail_y + 19.05), val_at=(xs + 3.81, rail_y + 21.59))
    S.wire(nC, Csc.p('1')); S.pin_power(Csc, '2', 'GND')
    D2 = S.part(DS, 'D2', 'D2', (xs + 10.16, nC[1]), mirror='y', ref_at=(xs + 8.89, nC[1] - 1.9), hide_value=True)
    S.wire(nC, D2.p('A')); xk = D2.p('K')[0]; S.wire(D2.p('K'), (xk, rail_y)); S.junction((xk, rail_y))
    S.text('süperkap float şarjlı bekler; kesintide D2 üzerinden birkaç dk besler (02-bom §2.5)', (143.51, rail_y + 29.21), 1.0, italic=True)
    S.text('GND: tek yıldız noktası RAC05 çıkışında', (66.04, rail_y + 21.59), 1.0, italic=True)

    # ---------- notlar ----------
    S.text('Notlar: pin atamaları 03 §3.1 ile aynı; tabloda olmayan tek ekleme GPIO1 besleme algılama. Pasif değerler tipik başlangıç değerleridir.', (35.56, 282.58), 1.0)
    S.text('Analizör varsa CT ön ucu boş kalır (hedef senaryo, 02-bom §2.3). Kavramsal şema — üretim çizimi değildir (§1.4). Üretim: eda/gen_sch.py → kicad-cli (ERC + SVG).', (35.56, 285.12), 1.0)
    return S

if __name__ == '__main__':
    S = build()
    with open(os.path.join(HERE, 'GridUp.kicad_sym'), 'w', encoding='utf-8', newline='') as fh:   # özel sembol kütüphanesi (MLX90640)
        ms = list(mlx90640_symbol()); ms[1] = 'MLX90640'
        fh.write(ser([Sym('kicad_symbol_lib'), [Sym('version'), Sym('20241209')], [Sym('generator'), 'gen_sch'], [Sym('generator_version'), '10.0'], ms]) + '\n')
    libs = ['Device', 'power', 'RF_Module', 'Sensor_Humidity', 'Interface_UART', 'Converter_ACDC', 'Regulator_Linear', 'Switch', 'Connector', 'Connector_Generic']
    with open(os.path.join(HERE, 'sym-lib-table'), 'w', encoding='utf-8', newline='') as fh:
        fh.write('(sym_lib_table\n  (version 7)\n')
        for l in libs: fh.write('  (lib (name "%s")(type "KiCad")(uri "${KICAD10_SYMBOL_DIR}/%s.kicad_sym")(options "")(descr ""))\n' % (l, l))
        fh.write('  (lib (name "GridUp")(type "KiCad")(uri "${KIPRJMOD}/GridUp.kicad_sym")(options "")(descr "proje sembolleri"))\n)\n')
    fps = ['TerminalBlock_Phoenix', 'Connector_Coaxial', 'Connector_PinHeader_2.54mm', 'Converter_ACDC', 'Package_SO', 'Package_TO_SOT_SMD', 'Package_TO_SOT_THT', 'RF_Module', 'Sensor_Humidity']
    with open(os.path.join(HERE, 'fp-lib-table'), 'w', encoding='utf-8', newline='') as fh:
        fh.write('(fp_lib_table\n  (version 7)\n')
        for l in fps: fh.write('  (lib (name "%s")(type "KiCad")(uri "${KICAD10_FOOTPRINT_DIR}/%s.pretty")(options "")(descr ""))\n' % (l, l))
        fh.write(')\n')
    out = os.path.join(HERE, PROJECT + '.kicad_sch')
    with open(out, 'w', encoding='utf-8', newline='') as fh: fh.write(S.emit('GridUp modül bağlantı şeması — ESP32-S3-WROOM-1U'))
    pro = os.path.join(HERE, PROJECT + '.kicad_pro')
    if not os.path.exists(pro):
        with open(pro, 'w', encoding='utf-8', newline='') as fh:
            json.dump({"meta": {"filename": PROJECT + ".kicad_pro", "version": 3},
                       "schematic": {"drawing": {"default_font": "KiCad Font"}, "legacy_lib_dir": "", "legacy_lib_list": []},
                       "sheets": [[ROOT_UUID, "Root"]], "text_variables": {}}, fh, indent=2, ensure_ascii=False)
    print('yazıldı', out, len(S.parts), 'parça', len(S.items), 'öğe')
