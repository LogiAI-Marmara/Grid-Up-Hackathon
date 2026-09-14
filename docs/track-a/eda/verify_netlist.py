# kicad-cli sch export netlist çıktısını 03-pinout.md §3.1–3.6 beklentisiyle karşılaştırır.
# Kullanım: kicad-cli sch export netlist --format kicadsexpr -o netlist.net GridUp-Modul.kicad_sch && python verify_netlist.py netlist.net
import sys, re, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_sch import parse, find, find1

net_file = sys.argv[1] if len(sys.argv) > 1 else 'netlist.net'
tree = parse(open(net_file, encoding='utf-8').read())
nets = {}
for n in find(find1(tree, 'nets'), 'net'):
    name = find1(n, 'name')[1]
    for node in find(n, 'node'):
        nets[(find1(node, 'ref')[1], find1(node, 'pin')[1])] = name.lstrip('/')   # yerel etiket '/AD' → 'AD'

# beklenen: (ref, pin) -> net (03-pinout §3.1, §3.4, §3.6)
EXP = {
    ('U1', '12'): 'SDA', ('U1', '17'): 'SCL',                                  # GPIO8 / GPIO9
    ('U1', '4'): 'CT_L1', ('U1', '5'): 'CT_L2', ('U1', '6'): 'CT_L3', ('U1', '7'): 'CT_N',   # GPIO4–7 ADC1
    ('U1', '39'): 'VSENSE',                                                    # GPIO1 ADC1_CH0
    ('U1', '18'): 'GPIO10', ('U1', '19'): 'GPIO11',                            # genişleme
    ('U1', '10'): 'U1TXD', ('U1', '11'): 'U1RXD', ('U1', '23'): 'DE_RE',       # GPIO17/18/21
    ('U1', '13'): 'USB_DN', ('U1', '14'): 'USB_DP', ('U1', '37'): 'U0TXD', ('U1', '36'): 'U0RXD',
    ('U1', '2'): '+3V3', ('U1', '1'): 'GND', ('U1', '40'): 'GND', ('U1', '41'): 'GND',
    ('U2', '1'): '+3V3', ('U2', '2'): 'GND', ('U2', '3'): 'SDA', ('U2', '4'): 'SCL',          # MLX90640
    ('U3', '1'): 'SDA', ('U3', '4'): 'SCL', ('U3', '5'): '+3V3', ('U3', '8'): 'GND', ('U3', '2'): 'GND', ('U3', '6'): '+3V3',  # SHT31 ADDR→GND, nRESET→3V3
    ('U4', '1'): 'U1RXD', ('U4', '4'): 'U1TXD', ('U4', '2'): 'DE_RE', ('U4', '3'): 'DE_RE', ('U4', '8'): '+3V3', ('U4', '5'): 'GND',  # MAX3485
    ('J7', '1'): None, ('J7', '2'): 'GND', ('J7', '3'): None,                # B / GND / A (A,B adsız net)
    ('J9', '1'): 'U0TXD', ('J9', '2'): 'U0RXD', ('J9', '3'): 'USB_DN', ('J9', '4'): 'USB_DP',
    ('U5', '5'): '5V_RAW', ('U5', '4'): 'GND',                                # RAC05 +Vout / −Vout
    ('D1', '2'): '5V_RAW', ('D1', '1'): '+5V',                                # D1 A → K (OR)
    ('U6', '3'): '+5V', ('U6', '2'): '+3V3', ('U6', '1'): 'GND',              # LDO VI/VO/GND
    ('R50', '1'): '5V_RAW', ('R50', '2'): 'VSENSE', ('R51', '1'): 'VSENSE', ('R51', '2'): 'GND',  # bölücü D1 öncesi
    ('R52', '1'): '+5V', ('D2', '1'): '+5V',                                  # R_şarj rayda, D2 K rayda
    ('J6', '1'): '+3V3', ('J6', '2'): '+5V', ('J6', '3'): 'GND', ('J6', '4'): 'GND',
    ('J6', '5'): 'SDA', ('J6', '6'): 'SCL', ('J6', '7'): 'GPIO10', ('J6', '8'): 'GPIO11',
    ('R1', '1'): '+3V3', ('C1', '2'): 'GND', ('SW1', '1'): 'GND',
    ('R2', '2'): 'SDA', ('R3', '2'): 'SCL', ('R2', '1'): '+3V3', ('R3', '1'): '+3V3',
}
# aynı nete düşmesi gereken adsız gruplar
SAME = [
    [('U4', '6'), ('J7', '3'), ('R40', '2')], [('U4', '7'), ('J7', '1'), ('R40', '1')],       # A → J7.3 (alt), B → J7.1 (üst) + 120 Ω
    [('U1', '3'), ('R1', '2'), ('C1', '1'), ('SW1', '2')],                                   # EN
    [('R52', '2'), ('C32', '1'), ('D2', '2')],                                               # süperkap düğümü
    [('J1', '1'), ('F1', '1')], [('F1', '2'), ('U5', '1'), ('RV1', '1')], [('J1', '2'), ('U5', '2'), ('RV1', '2')],  # L / N
    [('J2', '2'), ('R10', '2'), ('R30', '2'), ('R31', '1'), ('C20', '1')],                   # V_BIAS
]
for k in range(4):
    j, rb, rr, cr = 'J%d' % (2 + k), 'R%d' % (10 + k), 'R%d' % (20 + k), 'C%d' % (10 + k)
    SAME.append([(j, '1'), (rb, '1'), (rr, '1')])
    EXP[(rr, '2')] = ['CT_L1', 'CT_L2', 'CT_L3', 'CT_N'][k]; EXP[(cr, '1')] = EXP[(rr, '2')]; EXP[(cr, '2')] = 'GND'

bad = 0
for (ref, pin), want in EXP.items():
    got = nets.get((ref, pin))
    if want is None: continue
    if got != want: bad += 1; print('HATA %s.%s: %s bekleniyor, %s' % (ref, pin, want, got))
for grp in SAME:
    names = {nets.get(rp) for rp in grp}
    if len(names) != 1 or None in names: bad += 1; print('HATA aynı net değil:', grp, names)
print('netler:', len(set(nets.values())), '| düğümler:', len(nets), '| kontrol:', len(EXP) + len(SAME), '| hata:', bad)
sys.exit(1 if bad else 0)
