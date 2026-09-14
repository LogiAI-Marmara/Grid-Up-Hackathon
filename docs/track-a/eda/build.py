# Üretim zinciri: gen_sch.py → kicad-cli sch erc → export netlist + verify_netlist.py → export svg → svg_min.py
# Kullanım: python build.py [--kicad-cli PATH]
import os, sys, subprocess, shutil, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CLI = None
for a in sys.argv[1:]:
    if a.startswith('--kicad-cli='): CLI = a.split('=', 1)[1]
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
rep = os.path.join(HERE, 'erc-raporu.txt')   # kicad-cli CRLF yazar → LF
data = open(rep, 'rb').read().replace(b'\r\n', b'\n')
open(rep, 'wb').write(data)
tmp = tempfile.mkdtemp()
net = os.path.join(tmp, 'netlist.net')
run(CLI, 'sch', 'export', 'netlist', '--format', 'kicadsexpr', '-o', net, SCH)
run(PY, os.path.join(HERE, 'verify_netlist.py'), net)
run(CLI, 'sch', 'export', 'svg', '--no-background-color', '-o', tmp, SCH)
run(PY, os.path.join(HERE, 'svg_min.py'), os.path.join(tmp, 'GridUp-Modul.svg'), os.path.join(HERE, '03-baglanti-semasi-kicad.svg'))
shutil.rmtree(tmp, ignore_errors=True)
if rc != 0: sys.exit(1)
print('TAMAM')
