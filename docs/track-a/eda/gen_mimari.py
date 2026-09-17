#!/usr/bin/env python3
"""08-sistem-mimarisi.svg üreteci — karar kaydı §8'e birebir.

Zincir: PANO (sensörler -> MODÜL -> anten + besleme) -> kablosuz -> SAHA GATEWAY
-> mevcut altyapı -> ON-PREMISE SUNUCU (toplama -> PostgreSQL -> anomali motoru
-> alarm / okuma API'si + monitoring / Modbus TCP -> SCADA).

Kapsam: T3 (yazılım mimarisi) + T4 (monitoring) + T6 (on-prem) + T7 (alarm).
Lider kararıyla tamamı İZ A (İZ B/C katmanları §8'e sadık kalınarak çizilir).

Kural: elle SVG düzenlemesi yok — değiştir, üret, kontrol et:
    python gen_mimari.py [../08-sistem-mimarisi.svg]
    python3 temp/kontrol.py   # XML + metin taşması (Arial metriği) + kırık link

Stil: 09-montaj-adimlari.svg ile aynı sınıflar (t/s/r, zone, box).
Kurallar (cad/README): font Arial/Helvetica, ayraç " / ", LF satır sonu.
"""

import sys

C = dict(
    PANO_X=40, PANO_W=380, GW_X=500, GW_W=280, SRV_X=860, SRV_W=700,
    TOP=100, H=580,
)

STIL = """\
    .card{fill:#fafafa;stroke:#90a4ae;stroke-width:2}
    .t{font-size:14px;font-weight:700;fill:#263238}
    .s{font-size:12px;fill:#37474f}
    .r{font-size:11px;fill:#607d8b}
    .zoneP{fill:#e3f2fd;stroke:#1565c0;stroke-width:2}
    .zoneG{fill:#eceff1;stroke:#546e7a;stroke-width:2}
    .zoneS{fill:#e8f5e9;stroke:#2e7d32;stroke-width:2}
    .boxMcu{fill:#c8e6c9;stroke:#2e7d32;stroke-width:2}
    .boxGuc{fill:#fce4ec;stroke:#ad1457;stroke-width:2}
    .boxIc{fill:#ffffff;stroke:#455a64;stroke-width:2}
    .boxOut{fill:#fff3e0;stroke:#ef6c00;stroke-width:2}
    .actor{fill:none;stroke:#546e7a;stroke-width:1.5;stroke-dasharray:5 4}
    .zh{font-size:16px;font-weight:700;fill:#263238}"""

# (x, y, metin, sınıf, anchor) — tüm metinler burada, koordinat hesabı test edilebilir.
METINLER = [
    # başlık
    (800, 36, "Sistem mimarisi / uçtan uca veri akışı", "baslik", "middle"),
    (800, 62, "Karar kaydı §8'e birebir · T3 + T4 + T6 + T7 · public cloud yok, sunucu on-premise", "r", "middle"),
    # pano
    (230, 128, "PANO İÇİ", "zh", "middle"),
    (230, 168, "Sensörler", "t", "middle"),
    (230, 190, "Ortam sıcaklık + nem (SHT31)", "s", "middle"),
    (230, 208, "Termal dizi MLX90640 (32×24)", "s", "middle"),
    (230, 226, "Akım: analizör (Modbus) veya CT ×4", "s", "middle"),
    (230, 244, "Ark kaydı: TVOC-2 (okuma)", "s", "middle"),
    (230, 262, "Genişleme arayüzü (boş, kesikli)", "s", "middle"),
    (230, 293, "PD / akustik için ayrılmış I2C-UART", "r", "middle"),
    (230, 348, "MODÜL (ESP32-S3-N8)", "t", "middle"),
    (230, 370, "Oku → özetle → eşik → paketle", "s", "middle"),
    (230, 388, "Normalde özet, anomalide tam kare", "s", "middle"),
    (230, 406, "Modül hüküm VERMEZ (seviye/tip yok)", "s", "middle"),
    (230, 428, "Detay: 01 blok şema · akış: 07", "r", "middle"),
    (230, 448, "Paket (sözleşme 2): modul_id, zaman", "r", "middle"),
    (230, 513, "Besleme", "t", "middle"),
    (230, 535, "230 V iç ihtiyaç → 5 V → LDO 3,3 V", "s", "middle"),
    (230, 553, "Süperkap yedek (kesintide bildirir)", "s", "middle"),
    (108, 488, "3,3 V güç", "r", "start"),
    (230, 622, "Dış anten (U.FL → SMA)", "t", "middle"),
    (230, 642, "Metal pano içi anten çalışmaz (§7.4)", "r", "middle"),
    (373, 540, "RF", "r", "start"),
    (460, 600, "kablosuz", "s", "middle"),
    (460, 616, "2,4 GHz", "r", "middle"),
    (460, 650, "birkaç m", "r", "middle"),
    # gateway
    (640, 128, "SAHA GATEWAY", "zh", "middle"),
    (640, 152, "Trafo binası içi · 230 V", "r", "middle"),
    (640, 196, "Gateway", "t", "middle"),
    (640, 220, "Modüllerden kablosuz toplar", "s", "middle"),
    (640, 238, "Mevcut altyapıyla", "s", "middle"),
    (640, 256, "merkeze iletir", "s", "middle"),
    (640, 286, "Boyut kısıtı yok (§7.4)", "r", "middle"),
    (640, 304, "Kendi gateway'imiz önerilir;", "r", "middle"),
    (640, 320, "mevcut modem/RTU alternatif", "r", "middle"),
    (640, 344, "Detay İZ C kapsamı", "r", "middle"),
    (640, 440, "~3 saha × 2 pano × 1–2 modül", "s", "middle"),
    (640, 458, "Demo 8–10 · yük 100 (§7.7)", "s", "middle"),
    (820, 170, "mevcut", "s", "middle"),
    (820, 186, "altyapı", "s", "middle"),
    # sunucu
    (1210, 128, "ON-PREMISE SUNUCU (public cloud yok)", "zh", "middle"),
    (1210, 168, "Toplama servisi (İZ A)", "t", "middle"),
    (1210, 190, "Paketi al → doğrula → alindi_zaman ekle → PostgreSQL'e yaz", "s", "middle"),
    (1210, 208, "Kod: /toplama · şema: ölçüm (uzun format) + termal kare + modül", "r", "middle"),
    (1210, 263, "PostgreSQL", "t", "middle"),
    (1210, 285, "Ölçüm satırları (modul_id, zaman, olcum_tipi, deger, kalite)", "s", "middle"),
    (1210, 303, "Termal tam kare ayrı tabloda (768 değer) · sözleşme 1", "r", "middle"),
    (1210, 358, "Anomali motoru (İZ B)", "t", "middle"),
    (1210, 380, "Taban çizgisi (medyan + MAD) → skor + seviye + tip + gerekce", "s", "middle"),
    (1210, 398, "Çıktı: sözleşme 3 (id, skor, seviye, tip, gerekce, kanit)", "r", "middle"),
    (985, 458, "Alarm servisi", "t", "middle"),
    (985, 480, "Seviye → kanal", "s", "middle"),
    (985, 498, "SMS / WhatsApp", "s", "middle"),
    (985, 520, "Tekrar önleme (T7)", "r", "middle"),
    (985, 538, "GSM modem / on-prem", "r", "middle"),
    (1215, 458, "Okuma API'si", "t", "middle"),
    (1215, 480, "REST + JSON", "s", "middle"),
    (1215, 498, "Sözleşme 5 (İZ B)", "s", "middle"),
    (1215, 520, "/sahalar /moduller", "r", "middle"),
    (1215, 538, "/anomaliler /saglik", "r", "middle"),
    (1440, 458, "Modbus TCP", "t", "middle"),
    (1440, 480, "Register haritası", "s", "middle"),
    (1440, 498, "Sözleşme 4 (İZ C)", "s", "middle"),
    (1440, 520, "Modül başına 20 reg.", "r", "middle"),
    (1440, 538, "→ SCADA", "r", "middle"),
    (1215, 603, "Monitoring (İZ C)", "t", "middle"),
    (1215, 625, "Saha/pano/modül ağacı", "s", "middle"),
    (1215, 643, "Isı haritası + alarm listesi", "s", "middle"),
    (985, 597, "operasyon ekibi", "s", "middle"),
    (1440, 597, "SCADA", "s", "middle"),
    # alt notlar
    (800, 712, "Veri politikası (§7.4): normalde özet (maks, konum, bölge ort.) · anomali anında tam kare (768) kanıt olarak · eşik merkezden güncellenir (100 saha gezilmez, T5)", "r", "middle"),
    (800, 732, "Sınır: modül anomali hükmü vermez (§7.4 satır 304) · ark tespiti yok, TVOC-2 kaydı okunur (§7.1 satır 230) · WhatsApp bulutu yerine yerel GSM/on-prem gateway (İZ C)", "r", "middle"),
    (800, 762, "İz sahipleri: saha + toplama İZ A · anomali + okuma API İZ B · arayüz + Modbus + alarm + kurulum İZ C · sözleşme değişimi lidere sorulur (§9)", "r", "middle"),
]

KUTULAR = [  # (x, y, w, h, sınıf) — bölge + kutu + aktör çerçeveleri
    (40, 100, 380, 580, "zoneP"), (60, 145, 340, 165, "boxIc"),
    (60, 280, 340, 18, "kesikli"), (60, 325, 340, 150, "boxMcu"),
    (60, 490, 340, 95, "boxGuc"), (60, 600, 340, 60, "boxIc"),
    (500, 100, 280, 580, "zoneG"), (520, 170, 240, 220, "boxIc"),
    (860, 100, 700, 580, "zoneS"), (880, 145, 660, 80, "boxIc"),
    (880, 240, 660, 80, "boxIc"), (880, 335, 660, 80, "boxMcu"),
    (880, 435, 210, 130, "boxOut"), (1110, 435, 210, 130, "boxIc"),
    (1340, 435, 200, 130, "boxIc"), (1110, 580, 210, 80, "boxIc"),
    (900, 578, 170, 28, "actor"), (1370, 578, 140, 28, "actor"),
]

OKLAR = [  # (x1, y1, x2, y2, renk) — renk: g=gri, m=mavi, p=pembe(güç)
    (230, 310, 230, 322, "g"), (95, 490, 95, 478, "p"),
    (365, 478, 365, 596, "g"), (402, 630, 496, 630, "m"),
    (760, 200, 876, 200, "g"), (1210, 225, 1210, 237, "g"),
    (1210, 320, 1210, 332, "g"), (985, 415, 985, 432, "g"),
    (1215, 415, 1215, 432, "g"), (1440, 415, 1440, 432, "g"),
    (1215, 565, 1215, 577, "g"), (985, 565, 985, 576, "g"),
    (1440, 565, 1440, 576, "g"),
]

RENK = {"g": "#546e7a", "m": "#1565c0", "p": "#ad1457"}
OK = {"g": "arr", "m": "arrB", "p": "arr"}


def uret() -> str:
    L = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 800" width="100%"'
         ' style="max-width:1200px;background:#fff;font-family:Arial,Helvetica,sans-serif;font-size:13px">']
    L.append("  <!-- 08-sistem-mimarisi — gen_mimari.py üretir; ELLE DÜZENLEME (yeniden üretimde kaybolur). §8. -->")
    L.append('  <defs>')
    L.append('    <marker id="arr" markerWidth="10" markerHeight="10" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#546e7a"/></marker>')
    L.append('    <marker id="arrB" markerWidth="10" markerHeight="10" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#1565c0"/></marker>')
    L.append('  </defs>')
    L.append('  <style>')
    L.append(STIL)
    L.append('  </style>')
    for x, y, w, h, sn in KUTULAR:
        if sn == "kesikli":
            L.append(f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="0" fill="none"'
                     f' stroke="#1565c0" stroke-width="1.5" stroke-dasharray="5 4"/>')
        else:
            L.append(f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{10 if sn.startswith("zone") else 8 if sn != "actor" else 6}" class="{sn}"/>')
    for x1, y1, x2, y2, r in OKLAR:
        L.append(f'  <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{RENK[r]}"'
                 f' stroke-width="{2.5 if ((x2 - x1) > 50 or r == "m") else 2}" marker-end="url(#{OK[r]})"/>')
    for x, y, m, sn, an in METINLER:
        if sn == "baslik":
            L.append(f'  <text x="{x}" y="{y}" text-anchor="{an}" font-size="24" font-weight="700" fill="#263238">{m}</text>')
        elif sn == "zh":
            L.append(f'  <text x="{x}" y="{y}" text-anchor="{an}" class="zh">{m}</text>')
        else:
            L.append(f'  <text x="{x}" y="{y}" text-anchor="{an}" class="{sn}">{m}</text>')
    L.append('</svg>')
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    cikti = sys.argv[1] if len(sys.argv) > 1 else "../08-sistem-mimarisi.svg"
    with open(cikti, "w", encoding="utf-8", newline="") as f:
        f.write(uret())
    print(f"yazıldı: {cikti} ({len(METINLER)} metin, {len(KUTULAR)} kutu, {len(OKLAR)} ok)")
