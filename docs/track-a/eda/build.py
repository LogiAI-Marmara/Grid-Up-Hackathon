# Üretim zinciri: gen_sch.py → kicad-cli sch erc → export netlist + verify_netlist.py → export svg (çerçevesiz)
#                 → svg_min.py → ../03-baglanti-semasi.svg (dokümandaki şema doğrudan buradan üretilir)
# Kullanım: python build.py [--kicad-cli=PATH] [--out=SVG]
import os, sys, subprocess, shutil, tempfile, re

HERE = os.path.dirname(os.path.abspath(__file__))
CLI = None; OUT = os.path.normpath(os.path.join(HERE, '..', '03-baglanti-semasi.svg'))
for a in sys.argv[1:]:
    if a.startswith('--kicad-cli='): CLI = a.split('=', 1)[1]
    if a.startswith('--out='): OUT = os.path.abspath(a.split('=', 1)[1])
if CLI is None:
    for c in [os.path.expandvars(r'%LOCALAPPDATA%\Programs\KiCad\10.0\bin\kicad-cli.exe'),
              r'C:\Program Files\KiCad\10.0\bin\kicad-cli.exe', r'C:\Program Files\KiCad\9.0\bin\kicad-cli.exe', shutil.which('kicad-cli')]:
        if c and os.path.exists(c): CLI = c; break
assert CLI, 'kicad-cli bulunamadı (--kicad-cli=PATH)'
SCH = os.path.join(HERE, 'GridUp-Modul.kicad_sch')
PY = sys.executable

def run(*args, ok=(0,)):
    print('>', ' '.join(os.path.basename(a) if os.path.isabs(a) else a for a in args))
    r = subprocess.run(args, cwd=HERE)
    if r.returncode not in ok: sys.exit('HATA: %s → %d' % (args[0], r.returncode))
    return r.returncode

run(PY, os.path.join(HERE, 'gen_sch.py'))
rc = run(CLI, 'sch', 'erc', '--format', 'report', '--severity-all', '--exit-code-violations', '-o', 'erc-raporu.txt', SCH, ok=(0, 5))
print('ERC:', 'temiz' if rc == 0 else 'İHLAL VAR (erc-raporu.txt)')
rep = os.path.join(HERE, 'erc-raporu.txt')   # kicad-cli CRLF yazar → LF; zaman damgası → deterministik
data = open(rep, 'rb').read().replace(b'\r\n', b'\n')
data = re.sub(rb'\(\d{4}-\d\d-\d\dT[^,]*, ', b'(', data)
open(rep, 'wb').write(data)
net = os.path.join(HERE, 'GridUp-Modul.net')   # commit'li: verify_netlist.py tekrar üretilebilir
run(CLI, 'sch', 'export', 'netlist', '--format', 'kicadsexpr', '-o', net, SCH)
txt = open(net, encoding='utf-8').read().replace('\r\n', '\n')
txt = re.sub(r'\(source "[^"]*GridUp-Modul\.kicad_sch"\)', '(source "GridUp-Modul.kicad_sch")', txt)   # mutlak yol → dosya adı
txt = re.sub(r'\(date "\d{4}-\d\d-\d\dT[^"]*"\)', '(date "")', txt)                                     # zaman damgası → deterministik
open(net, 'w', encoding='utf-8', newline='').write(txt)
run(PY, os.path.join(HERE, 'verify_netlist.py'), net)
tmp = tempfile.mkdtemp()
run(CLI, 'sch', 'export', 'svg', '--no-background-color', '--exclude-drawing-sheet', '--draw-hop-over', '-o', tmp, SCH)
run(PY, os.path.join(HERE, 'svg_min.py'), os.path.join(tmp, 'GridUp-Modul.svg'), OUT)
shutil.rmtree(tmp, ignore_errors=True)
if rc != 0: sys.exit(1)
print('TAMAM →', OUT)
