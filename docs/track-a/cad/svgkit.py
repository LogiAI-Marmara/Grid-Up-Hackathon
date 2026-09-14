# SVG kompozisyon yardımcıları — Fusion projeksiyon JSON'undan teknik kroki
import json

FONT = 'Arial,Helvetica,sans-serif'
INK = '#263238'; DIM = '#455a64'; MUTED = '#78909c'

def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

class Svg:
    def __init__(self, w, h, title):
        self.w, self.h = w, h
        self.parts = []
        self.header = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="100%%" '
                       'style="max-width:1100px;background:#fff;font-family:%s">\n' % (w, h, FONT))
        self.title = title

    def add(self, s): self.parts.append(s)

    def text(self, x, y, s, size=13, fill=INK, anchor='start', weight=None, rotate=None, style=None):
        a = ['x="%g" y="%g"' % (x, y), 'font-size="%g"' % size, 'fill="%s"' % fill]
        if anchor != 'start': a.append('text-anchor="%s"' % anchor)
        if weight: a.append('font-weight="%s"' % weight)
        if style: a.append('font-style="%s"' % style)
        if rotate is not None: a.append('transform="rotate(%g %g %g)"' % (rotate, x, y))
        self.add('<text %s>%s</text>' % (' '.join(a), esc(s)))

    def dim_h(self, x1, x2, y, label, off=0, size=15):
        # yatay ölçü çizgisi; off: uzatma çizgisi başlangıcı (y'den off kadar yukarı/aşağı)
        self.add('<line x1="%g" y1="%g" x2="%g" y2="%g" stroke="%s" stroke-width="1.5" marker-start="url(#dim)" marker-end="url(#dim)"/>' % (x1, y, x2, y, DIM))
        if off:
            for x in (x1, x2):
                self.add('<line x1="%g" y1="%g" x2="%g" y2="%g" stroke="%s" stroke-width="1"/>' % (x, y - off, x, y + (6 if off > 0 else -6), DIM))
        self.text((x1 + x2) / 2, y + (size + 6 if off >= 0 else -8), label, size, DIM, 'middle')

    def dim_v(self, x, y1, y2, label, off=0, size=15):
        self.add('<line x1="%g" y1="%g" x2="%g" y2="%g" stroke="%s" stroke-width="1.5" marker-start="url(#dim)" marker-end="url(#dim)"/>' % (x, y1, x, y2, DIM))
        if off:
            for y in (y1, y2):
                self.add('<line x1="%g" y1="%g" x2="%g" y2="%g" stroke="%s" stroke-width="1"/>' % (x - off, y, x + (6 if off > 0 else -6), y, DIM))
        tx = x - 8 if off >= 0 else x + 18
        self.text(tx, (y1 + y2) / 2, label, size, DIM, 'middle', rotate=-90)

    def leader(self, x1, y1, x2, y2, lines, size=12, fill=INK, anchor='start', dot=True):
        self.add('<line x1="%g" y1="%g" x2="%g" y2="%g" stroke="%s" stroke-width="1"/>' % (x1, y1, x2, y2, fill))
        if dot: self.add('<circle cx="%g" cy="%g" r="2.5" fill="%s"/>' % (x1, y1, fill))
        for i, ln in enumerate(lines):
            self.text(x2 + (4 if anchor == 'start' else -4), y2 + 4 + i * (size + 3), ln, size, fill, anchor, weight='700' if i == 0 else None)

    def view(self, polys, ox, oy, S, origin, stroke=INK, sw=1.5, colors=None, bg=None):
        """polys: JSON listesi (mm, y aşağı). origin: (x_mm, y_mm) → (ox, oy) piksel."""
        colors = colors or {}
        g = ['<g transform="translate(%g,%g)">' % (ox, oy)]
        if bg: g.append(bg)
        for pl in polys:
            col = colors.get(pl['body'], stroke)
            pts = ' '.join('%g,%g' % (round((p[0] - origin[0]) * S, 2), round((p[1] - origin[1]) * S, 2)) for p in pl['pts'])
            g.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="%g" stroke-linejoin="round" stroke-linecap="round"/>' % (pts, col, sw))
        g.append('</g>')
        self.add('\n'.join(g))

    def bbox(self, polys):
        xs = [p[0] for pl in polys for p in pl['pts']]; ys = [p[1] for pl in polys for p in pl['pts']]
        return min(xs), min(ys), max(xs), max(ys)

    def write(self, path, comment):
        defs = ('  <defs>\n'
                '    <marker id="dim" markerWidth="10" markerHeight="10" refX="5" refY="3" orient="auto-start-reverse">\n'
                '      <path d="M0,0 L6,3 L0,6 z" fill="%s"/>\n    </marker>\n'
                '    <marker id="arr" markerWidth="10" markerHeight="10" refX="6" refY="3" orient="auto">\n'
                '      <path d="M0,0 L6,3 L0,6 z" fill="#c62828"/>\n    </marker>\n'
                '  </defs>\n' % DIM)
        body = self.header + '  <!--\n' + comment + '\n  -->\n' + defs + '\n'.join('  ' + p for p in self.parts) + '\n</svg>\n'
        with open(path, 'w', encoding='utf-8', newline='') as fh:
            fh.write(body)
        return len(body)
