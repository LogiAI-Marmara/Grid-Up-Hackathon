# kicad-cli SVG çıktısını küçültür ve metni sistem fontuna çevirir:
#   - KiCad her metni hem gizli <text> (opacity 0) hem <g class="stroked-text"> çizgi-font yolu olarak yazar;
#     çizgi-font gruplarını atar, <text>'i görünür yapar (Arial/Helvetica), textLength'i kaldırır (glif esnemesin).
#   - Koordinatlar 3 ondalığa yuvarlanır, path içi satır sonları tek boşluğa, tarih damgası silinir (deterministik).
# Kullanım: python svg_min.py in.svg out.svg
import sys, re
src = open(sys.argv[1], encoding='utf-8').read()
def num(m):
    v = round(float(m.group(0)), 3)
    return ('%.3f' % v).rstrip('0').rstrip('.') if v != int(v) else str(int(v))
def fix_path(m):
    d = re.sub(r'\s+', ' ', m.group(1)).strip()
    return 'd="' + re.sub(r'-?\d+\.\d+', num, d) + '"'
out = re.sub(r'<g class="stroked-text">.*?</g>', '', src, flags=re.S)
def fix_text(m):
    a = m.group(1)
    a = re.sub(r'\s*textLength="[^"]*"', '', a); a = re.sub(r'\s*lengthAdjust="[^"]*"', '', a)
    a = re.sub(r'\s*stroke-opacity="0"', '', a); a = re.sub(r'(^|\s)opacity="0"', '', a)
    a = re.sub(r'\s+', ' ', a).strip()
    return '<text ' + a + ' font-family="Arial,Helvetica,sans-serif" stroke="none">'
def fix_group(m):   # metin rengi = grubun stroke rengi (KiCad grubu fill:none yazar)
    col = re.search(r'stroke:(#[0-9A-Fa-f]{6})', m.group(1))
    body = re.sub(r'<text\s+([^>]*)>', fix_text, m.group(2))
    if col: body = body.replace('<text ', '<text fill="%s" ' % col.group(1))
    return '<g style="' + m.group(1) + '">' + body + '</g>'
out = re.sub(r'<g style="([^"]*)">(.*?)</g>', fix_group, out, flags=re.S)
out = re.sub(r'd="([^"]*)"', fix_path, out)
out = re.sub(r'<title>.*?</title>\s*', '', out, flags=re.S)
out = re.sub(r'\n\s*\n', '\n', out)
with open(sys.argv[2], 'w', encoding='utf-8', newline='') as fh: fh.write(out)
print('%s: %d → %d bayt' % (sys.argv[2], len(src), len(out)))
