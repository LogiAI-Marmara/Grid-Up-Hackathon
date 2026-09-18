#!/usr/bin/env python3
"""08-sistem-mimarisi.svg üreteci — karar kaydı §8 (mimari) + §9 (sözleşmeler) + üç izin main/PR'daki gerçek kodu.

Zincir: PANO İÇİ (sensörler → modül → anten, besleme) → kablosuz → SAHA GATEWAY → mevcut altyapı
→ ON-PREMISE SUNUCU (toplama → PostgreSQL → anomali motoru → okuma API'si → alarm / monitoring / Modbus TCP → SCADA).

Kaynaklar (metinler buradan, uydurma yok):
  gridup-proje-karar-kaydi.md §8–§11 · sozlesmeler/README.md · toplama/toplama/uygulama.py (İZ A)
  analiz/README.md (İZ B, K1–K3, 4 katman, olay modeli, API :8080) · PR #2 docs/operasyon-yuzu-dokumantasyonu.md
  (İZ C: arayüz :80, Modbus :5020, alarm Telegram, docker-compose) · modul-sim (sentetik üreteç, 7 senaryo).

Kural: elle SVG düzenlemesi yok — bu dosyayı değiştir, üret, tarayıcıda kontrol et:
    python gen_mimari.py [../08-sistem-mimarisi.svg]
Üreteç metin genişliklerini Arial metriğiyle (PIL) ölçer; kutudan taşan metin varsa hata verir.

Stil: 09-montaj-adimlari.svg ile aynı aile (Arial, ayraç " / ", LF).
"""
import sys, os

W, H = 1600, 912
try:
    from PIL import ImageFont
    _F = ImageFont.truetype('arial.ttf', 100); _FB = ImageFont.truetype('arialbd.ttf', 100)
    def tw(s, size, bold=False): return (_FB if bold else _F).getlength(s) / 100 * size
except Exception:   # PIL yoksa ölçüm atlanır
    def tw(s, size, bold=False): return 0

SZ = dict(t=14, s=12, r=11, zh=16, baslik=24)
CSS = """\
    text{font-family:Arial,Helvetica,sans-serif}
    .baslik{font-size:24px;font-weight:700;fill:#263238}
    .alt{font-size:13px;fill:#607d8b}
    .zh{font-size:16px;font-weight:700;fill:#263238}
    .t{font-size:14px;font-weight:700;fill:#263238}
    .s{font-size:12px;fill:#37474f}
    .r{font-size:11px;fill:#607d8b}
    .w{font-size:11px;font-weight:700;fill:#c62828}
    .zoneP{fill:#e3f2fd;stroke:#1565c0;stroke-width:2}
    .zoneG{fill:#eceff1;stroke:#546e7a;stroke-width:2}
    .zoneS{fill:#e8f5e9;stroke:#2e7d32;stroke-width:2}
    .boxIc{fill:#ffffff;stroke:#455a64;stroke-width:2}
    .boxMcu{fill:#c8e6c9;stroke:#2e7d32;stroke-width:2}
    .boxGuc{fill:#fce4ec;stroke:#ad1457;stroke-width:2}
    .boxOut{fill:#fff3e0;stroke:#ef6c00;stroke-width:2}
    .boxSim{fill:#ffffff;stroke:#1565c0;stroke-width:1.5;stroke-dasharray:6 4}
    .boxSoz{fill:#fffde7;stroke:#f9a825;stroke-width:1.5}
    .actor{fill:none;stroke:#546e7a;stroke-width:1.5;stroke-dasharray:5 4}
    .lbl{font-size:11px;fill:#455a64}"""

L = []          # svg parçaları
HATA = []       # taşma raporu


def esc(s): return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def text(x, y, s, cls='s', anchor='start', maxw=None):
    L.append(f'  <text x="{x}" y="{y}" text-anchor="{anchor}" class="{cls}">{esc(s)}</text>')
    if maxw:
        w = tw(s, SZ.get(cls, 12), cls in ('t', 'zh', 'baslik', 'w'))
        if w > maxw: HATA.append(f'{s[:40]!r}: {w:.0f} > {maxw} px')


def rect(x, y, w, h, cls, rx=8):
    L.append(f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" class="{cls}"/>')


LH = {'t': 20, 's': 17, 'r': 15, 'w': 16}
def bh(lines, pad=10): return 22 + sum(LH[c] for _, c in lines) + pad


def box(x, y, w, cls, title, lines, pad=10, h=None):
    """Başlık + satırlar; satır = (metin, sınıf). Yükseklik içerikten. Döner: (x, y, w, h)."""
    lh = LH
    hh = bh(lines, pad)
    if h is None: h = hh
    rect(x, y, w, h, cls)
    cx = x + w / 2
    text(cx, y + 20, title, 't', 'middle', w - 12)
    yy = y + 22
    for s, c in lines:
        yy += lh[c]
        text(cx, yy, s, c, 'middle', w - 12)
    return x, y, w, h


def arrow(x1, y1, x2, y2, col='#546e7a', sw=2, dash=None, mk='arr'):
    d = f' stroke-dasharray="{dash}"' if dash else ''
    L.append(f'  <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{col}" stroke-width="{sw}"{d} marker-end="url(#{mk})"/>')


def line(x1, y1, x2, y2, col='#546e7a', sw=2, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ''
    L.append(f'  <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{col}" stroke-width="{sw}"{d}/>')


def uret():
    del L[:]; del HATA[:]
    L.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%"'
             ' style="max-width:1200px;background:#fff;font-family:Arial,Helvetica,sans-serif">')
    L.append('  <!-- 08-sistem-mimarisi / eda/gen_mimari.py üretir; ELLE DÜZENLEME (yeniden üretimde kaybolur). Karar kaydı §8–§11. -->')
    L.append('  <defs>')
    for mid, col in (('arr', '#546e7a'), ('arrB', '#1565c0'), ('arrG', '#2e7d32'), ('arrO', '#ef6c00')):
        L.append(f'    <marker id="{mid}" markerWidth="10" markerHeight="10" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="{col}"/></marker>')
    L.append('  </defs>')
    L.append('  <style>'); L.append(CSS); L.append('  </style>')

    # ---------- başlık ----------
    text(800, 36, 'Sistem mimarisi / uçtan uca veri akışı', 'baslik', 'middle')
    text(800, 58, 'Karar kaydı §8 mimari + §9 sözleşmeler; kutular üç izin repodaki gerçek servisleri (main + PR #2) / public cloud yok, sunucu on-premise', 'alt', 'middle', 1500)

    # ---------- bölge çerçeveleri ----------
    ZP = (30, 80, 420, 560); ZG = (470, 80, 250, 560); ZS = (740, 80, 830, 560)
    rect(*ZP, 'zoneP', 10); rect(*ZG, 'zoneG', 10); rect(*ZS, 'zoneS', 10)
    text(240, 104, 'PANO İÇİ / donanım (İZ A)', 'zh', 'middle')
    text(595, 104, 'SAHA GATEWAY', 'zh', 'middle')
    text(1155, 104, 'ON-PREMISE SUNUCU / docker-compose (deploy, İZ C)', 'zh', 'middle')

    # ---------- PANO ---------- (kutular bölge yüksekliğine eşit aralıkla dağıtılır)
    px, pw = 50, 380
    P_S = [('Ortam sıcaklık + nem / SHT31 (I²C 0x44)', 's'),
           ('Termal dizi 32×24 / MLX90640 (I²C 0x33)', 's'),
           ('Akım L1 L2 L3 N / analizör (RS-485 Modbus) veya CT ×4', 's'),
           ('Ark kaydı / TVOC-2 trip-diag. (RS-485, yalnız okuma)', 's'),
           ('Genişleme 2×5: I²C / UART / ADC, PD-akustik için boş', 'r')]
    P_M = [('Oku → özetle → eşik → paketle (sözleşme ②)', 's'),
           ('Akım 1–5 s (10 s ort.) / termal özet 10–30 s / ortam 30–60 s', 's'),
           ('Normalde termal özet; anomali anında tam kare (768)', 's'),
           ('Hüküm vermez (seviye/tip yok); basit eşik, merkezden güncellenir', 's'),
           ('modul_durum: besleme sebeke/yedek, sinyal dBm, sürüm', 'r'),
           ('Ayrıntı: 01 blok şema / 03 bağlantı / 07 yazılım akışı', 'r')]
    P_G = [('230 V iç ihtiyaç → RAC05 5 V → LDO 3,3 V (03 §3.4)', 's'),
           ('Yedek: 2× süperkap 10 F seri + boost, ~5 dk @ 50 mA', 's'),
           ('Kesintide "besleme: yedek" paketi gider (senaryo 7)', 'r')]
    P_A = [('Wi-Fi 2,4 GHz → gateway; metal pano içinde anten çalışmaz (§7.4)', 's')]
    P_X = [('Donanım üretimi yok → aynı ② paketini üretir, 7 arıza senaryosu', 's'),
           ('toplama servisine doğrudan POST /paket (gateway yolu atlanır)', 'r')]
    hs = [bh(P_S), bh(P_M), bh(P_G), bh(P_A), bh(P_X)]
    top, bot = 118, ZP[1] + ZP[3] - 14
    gap = (bot - top - sum(hs)) / 4
    assert gap >= 14, 'PANO bölgesi taştı'
    y = top
    bS = box(px, y, pw, 'boxIc', 'Sensörler', P_S); y += hs[0] + gap
    arrow(240, y - gap + 4, 240, y - 4, '#546e7a')
    bM = box(px, y, pw, 'boxMcu', 'MODÜL / ESP32-S3-WROOM-1U', P_M); y += hs[1] + gap
    bG = box(px, y, pw, 'boxGuc', 'Besleme', P_G); y += hs[2] + gap
    bA = box(px, y, pw, 'boxIc', 'Dış anten / U.FL → SMA panel', P_A); y += hs[3] + gap
    bSim = box(px, y, pw, 'boxSim', 'Hackathon: modul-sim (İZ A, sentetik üreteç)', P_X)
    # besleme → modül (güç, pembe)
    line(px + 30, bG[1], px + 30, bM[1] + bM[3] + 4); arrow(px + 30, bM[1] + bM[3] + 4, px + 30, bM[1] + bM[3] + 4 - 0.1, '#ad1457', 1)
    text(px + 36, bG[1] - 5, '3,3 V', 'lbl', 'start')

    # ---------- GATEWAY ----------
    gx, gw = 485, 220
    bGW = box(gx, 150, gw, 'boxIc', 'Gateway', [
        ('Trafo binası içi, 230 V', 's'),
        ('Modüllerden Wi-Fi ile toplar', 's'),
        ('Mevcut altyapı üzerinden', 's'),
        ('merkeze HTTP ile iletir', 's'),
        ('Boyut kısıtı yok (§7.4)', 'r'),
        ('Kendi gateway; mevcut', 'r'),
        ('modem/RTU alternatif', 'r')])
    text(595, 350, 'Ölçek (§7.7)', 't', 'middle')
    text(595, 370, '~3 saha × 2 pano × 1–2 modül', 's', 'middle', 230)
    text(595, 387, 'demo 8–10 modül / yük testi 100', 's', 'middle', 230)
    text(595, 404, '(analiz.yuk: 10 / 50 / 100)', 'r', 'middle')
    # kablosuz ok: anten → gateway
    ay = bA[1] + bA[3] / 2
    arrow(px + pw + 2, ay, gx - 4, ay, '#1565c0', 2.5, mk='arrB')
    # gateway → sunucu
    gy = 160   # toplama kutusunun ortası
    arrow(gx + gw + 2, gy, 758, gy, '#546e7a', 2.5)
    # simülatör → toplama (kesikli, gateway'i atlar)
    sy = bSim[1] + bSim[3] / 2
    line(px + pw + 2, sy, 730, sy, '#1565c0', 1.5, '6 4'); line(730, sy, 730, 180, '#1565c0', 1.5, '6 4'); arrow(730, 180, 758, 180, '#1565c0', 1.5, '6 4', 'arrB')
    text(gx + gw / 2, sy - 6, 'POST /paket', 'lbl', 'middle')   # gateway sütununun ortasında, dikey kesikli çizgiye girmesin

    # ---------- SUNUCU ----------
    sx, sw_ = 758, 795
    bT = box(sx, 118, sw_, 'boxIc', 'Toplama servisi / FastAPI (İZ A, /toplama)', [
        ('POST /paket: sözleşme ② şemasıyla doğrula (hata → 400 + gerekçe) → alindi_zaman damgala → PostgreSQL', 's'),
        ('GET /saglik / modül saati ile alindi_zaman farkı = saat kayması sinyali (senaryo 7)', 'r')])
    y = bT[1] + bT[3] + 8; arrow(1155, y, 1155, y + 12)
    bP = box(sx, y + 16, sw_, 'boxIc', 'PostgreSQL / şema: toplama/migrations + analiz/100', [
        ('olcum (uzun-dar, ① modul_id zaman olcum_tipi deger kalite) / termal_kare (768 × int16, 0,1 °C) / modul_durum', 's'),
        ('anomali + anomali_gecis (olay günlüğü) / tarama_imleci / hacim ~60 satır/sn @ 100 modül', 'r')])
    y = bP[1] + bP[3] + 8
    # motor (sol) ve okuma API (sağ)
    mx, mw = sx, 470; ax, aw = sx + 490, sw_ - 490
    arrow(mx + mw / 2, y, mx + mw / 2, y + 12); arrow(ax + aw / 2, y, ax + aw / 2, y + 12)
    bAn = box(mx, y + 16, mw, 'boxMcu', 'Anomali motoru (İZ B, python -m analiz tara)', [
        ('Periyodik tarama 30 s, imleç alindi_zaman (geri sarılabilir, K1)', 's'),
        ('4 katman: 0 sensör sağlığı → 1 mutlak sınır → 2 taban (medyan+MAD, 14 g)', 's'),
        ('→ 3 ilişki (I²R artığı, faz, modül↔modül bastırma); ML yok', 's'),
        ('Çıktı ③: skor, seviye, tip, gerekce, kanit; olay + histerezis 30 dk (K3)', 'r')])
    bAp = box(ax, y + 16, aw, 'boxIc', 'Okuma API / FastAPI :8080 (İZ B)', [
        ('Sözleşme ⑤ REST+JSON: /sahalar /moduller', 's'),
        ('/moduller/{id}/seri /termal/kare/{id}', 's'),
        ('/anomaliler (+onayla) /gecisler /saglik', 's'),
        ('İZ C tüketir; OpenAPI /docs', 'r')], h=bAn[3])
    # motor → PostgreSQL geri yazım (anomali)
    line(mx + 40, bAn[1], mx + 40, bAn[1] - 8); arrow(mx + 40, bAn[1] - 8, mx + 40, bP[1] + bP[3] + 2, '#2e7d32', 1.5, mk='arrG')
    text(mx + 46, bAn[1] - 6, 'anomali yaz', 'lbl', 'start')
    y = bAn[1] + bAn[3] + 8
    # tüketiciler
    cw = 250; cx1, cx2, cx3 = sx, sx + 272, sx + 544
    for cx in (cx1 + cw / 2, cx2 + cw / 2, cx3 + cw / 2):
        line(ax + aw / 2, bAp[1] + bAp[3], ax + aw / 2, y - 2); line(cx1 + cw / 2, y - 2, cx3 + cw / 2, y - 2); arrow(cx, y - 2, cx, y + 12)
    bAl = box(cx1, y + 16, cw, 'boxOut', 'Alarm servisi (İZ C, /alarm)', [
        ('/anomaliler dinler; uyarı, kritik →', 's'),
        ('Telegram Bot mesajı (gerekçe dahil)', 's'),
        ('Anti-flapping 300 s (T7)', 'r'),
        ('Kayıt: SMS/WhatsApp; uygulama Telegram', 'r')])
    bMo = box(cx2, y + 16, cw, 'boxIc', 'Monitoring / nginx :80 (İZ C)', [
        ('Saha → pano → modül ağacı, 6 metrik', 's'),
        ('32×24 ısı haritası, sıcak nokta', 's'),
        ('Alarm kartı + operatör onayı (T4)', 'r'),
        ('POST /anomaliler/{id}/onayla, günlük', 'r')], h=bAl[3])
    bMb = box(cx3, y + 16, cw, 'boxIc', 'Modbus TCP :5020 (İZ C, /modbus)', [
        ('Sözleşme ④: modül başına 20 reg.', 's'),
        ('100 + (N−1)×20; çarpan 0,1', 's'),
        ('sıc. nem L1-3 N termal seviye', 'r'),
        ('besleme RSSI ark; API\'den senkron', 'r')], h=bAl[3])
    y = bAl[1] + bAl[3] + 6
    for bx, lbl in ((bAl, 'operasyon ekibi (Telegram)'), (bMo, 'operatör tarayıcısı'), (bMb, 'SCADA / RTU')):
        cx = bx[0] + bx[2] / 2
        arrow(cx, y, cx, y + 10)
        rect(bx[0] + 25, y + 12, bx[2] - 50, 24, 'actor', 6); text(cx, y + 28, lbl, 's', 'middle', bx[2] - 60)
    assert y + 40 <= ZS[1] + ZS[3] - 4, 'SUNUCU bölgesi taştı: %d' % (y + 40)

    # ---------- sözleşmeler şeridi ----------
    yb = 664
    text(30, yb, 'Sözleşmeler (§9, /sozlesmeler): izler arası sınır, değişimi lidere sorulur', 't', 'start')
    soz = [('① Ölçüm kaydı', 'A → B', 'modul_id, zaman, olcum_tipi, deger, birim, kalite', 'olcum_kaydi.schema.json'),
           ('② Modül paketi', 'A → A (toplama)', 'olcumler[], termal_ozet, termal_kare, modul_durum', 'modul_paketi.schema.json'),
           ('③ Anomali çıktısı', 'B → C', 'id, skor, seviye, tip, gerekce, kanit, durum', 'anomali.schema.json'),
           ('④ Modbus haritası', 'C → SCADA', 'modül başına 20 register, çarpanlı tam sayı', 'sozlesme_4_modbus.json (PR #2)'),
           ('⑤ Okuma API\'si', 'B → C', 'REST+JSON, 10 uç + /gecisler (İZ B ekledi)', 'sozlesme_5_api.json (PR #2)')]
    bw = 300
    for i, (t, yon, ic, dosya) in enumerate(soz):
        x = 30 + i * (bw + 10)
        rect(x, yb + 10, bw, 74, 'boxSoz', 6)
        text(x + 10, yb + 30, t, 't', 'start', bw - 90); text(x + bw - 10, yb + 30, yon, 'r', 'end')
        text(x + 10, yb + 50, ic, 's', 'start', bw - 20); text(x + 10, yb + 68, dosya, 'r', 'start', bw - 20)
    # ortak sözlük
    text(30, yb + 108, 'Ortak sözlük (§10, enums.py): olcum_tipi 9 değer / seviye normal-izle-uyari-kritik / tip 8 değer / kalite iyi-supheli-yok / durum acik-onaylandi-kapandi / modul_id {saha}-{pano}-{modul} / zaman UTC ISO 8601', 'r', 'start', 1540)
    # alt notlar
    text(30, yb + 132, 'Veri politikası (§7.4): normalde özet (maks, konum, bölge ort.) / anomali anında tam kare kanıt olarak / modülde basit eşik, hüküm merkezde (§7.4 satır 304) / ark tespiti yok, TVOC-2 kaydı okunur (§7.1 satır 230)', 'r', 'start', 1540)
    text(30, yb + 150, 'Sahipler: saha + modul-sim + toplama İZ A / anomali motoru + okuma API İZ B / arayüz + Modbus + alarm + deploy İZ C / on-prem: tüm servisler docker-compose ile tek sunucuda, public cloud yok (T6)', 'r', 'start', 1540)
    text(30, yb + 168, 'Durum (18 Eyl): gerçek zincir modul-sim → toplama → PostgreSQL → analiz → :8080 (main). Hedef, henüz bağlı değil: İZ C servisleri mock API :8000/api okuyor (:8080 değil); PR #2 compose yalnız arayüz+modbus+alarm+mock', 'r', 'start', 1540)
    text(30, yb + 186, '(toplama/analiz/PostgreSQL yok); gateway ve pano donanımı yok. Kaynak: karar kaydı §8–§11, sozlesmeler/README, analiz/README, PR #2 docs/operasyon-yuzu-dokumantasyonu.md. Üretim: eda/gen_mimari.py', 'r', 'start', 1540)

    L.append('</svg>')
    return '\n'.join(L) + '\n'


if __name__ == '__main__':
    cikti = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '08-sistem-mimarisi.svg')
    svg = uret()
    if HATA:
        print('TAŞMA:'); [print('  ', h) for h in HATA]; sys.exit(1)
    with open(cikti, 'w', encoding='utf-8', newline='\n') as f: f.write(svg)
    print('yazıldı:', cikti, len(svg), 'bayt')
