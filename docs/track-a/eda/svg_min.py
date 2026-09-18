# kicad-cli SVG çıktısını dokümana gömülebilir hâle getirir:
#   - KiCad her metni hem gizli <text> (opacity 0) hem <g class="stroked-text"> çizgi-font yolu olarak yazar;
#     çizgi-font gruplarını atar, <text>'i görünür yapar (Arial/Helvetica, rengi grubun stroke rengi), textLength'i kaldırır.
#   - viewBox içeriğin sınır kutusuna kırpılır (çizim çerçevesi build.py'de zaten dışlanır), kenar payı 4 mm.
#   - Koordinatlar 3 ondalığa yuvarlanır, tarih damgası silinir (deterministik çıktı).
# Kullanım: python svg_min.py in.svg out.svg
import sys, re
src = open(sys.argv[1], encoding='utf-8').read()
MARGIN = 4.0
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
# içeriğe kırp
xs, ys = [], []
for d in re.findall(r'd="([^"]*)"', out):
    for cmd, args in re.findall(r'([MLA])([^MLAZz]*)', d):          # M/L: nokta; A: rx ry rot lf sf x y → son iki sayı
        nums = [float(v) for v in re.findall(r'-?\d+(?:\.\d+)?', args)]
        pts = [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)] if cmd != 'A' else [(nums[-2], nums[-1])]
        for x, y in pts: xs.append(x); ys.append(y)
for x, y in re.findall(r'<text[^>]*\sx="([-\d.]+)"\s+y="([-\d.]+)"', out): xs.append(float(x)); ys.append(float(y))
for x, y, w, h in re.findall(r'<rect[^>]*\sx="([-\d.]+)"[^>]*\sy="([-\d.]+)"[^>]*\swidth="([-\d.]+)"[^>]*\sheight="([-\d.]+)"', out):
    xs += [float(x), float(x) + float(w)]; ys += [float(y), float(y) + float(h)]
w = h = 0
if xs:
    x0, y0, x1, y1 = min(xs) - MARGIN, min(ys) - MARGIN, max(xs) + MARGIN, max(ys) + MARGIN
    w, h = round(x1 - x0, 3), round(y1 - y0, 3)
    out = re.sub(r'width="[^"]*mm" height="[^"]*mm" viewBox="[^"]*"',
                 'width="%gmm" height="%gmm" viewBox="%g %g %g %g"' % (w, h, round(x0, 3), round(y0, 3), w, h), out, count=1)
    out = out.replace('<svg\n', '<svg\n  style="max-width:1200px;width:100%;height:auto;background:#fff"\n', 1)
with open(sys.argv[2], 'w', encoding='utf-8', newline='') as fh: fh.write(out)
print('%s: %d → %d bayt%s' % (sys.argv[2], len(src), len(out), (', içerik %g × %g mm' % (w, h)) if xs else ''))
