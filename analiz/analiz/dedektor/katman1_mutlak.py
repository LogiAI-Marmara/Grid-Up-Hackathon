"""Layer 1 — absolute limits, independent of any baseline.

Section 5: whatever this module's "normal" happens to be, 130 C is critical.
That is the whole idea, and it is why this layer ignores the baseline entirely —
a module whose terminal has been running hot for a fortnight has a *high* median,
and layer 2 would find the fortnight unremarkable. Layer 1 does not care what is
usual here.

This is the type B (state anomaly) half of section 2.3: nothing is trending,
something is simply wrong right now. No early-warning claim attaches to it.

Thresholds come from the TEDAS specification, material temperature limits and
the NETA / Infraspection delta-T priority classes (section 9.2), and they live in
`ayar.py`. Section 9.2 is also honest about their limit: those criteria were
written for a technician walking round with a camera once, not for continuous
monitoring. They are a reference here; the early warning is layer 2's job.

Covers scenarios 2, 3, 4 and 5.
"""

from __future__ import annotations

from ..ayar import Ayar
from ..gerekce import ark_olayi, mutlak_faz, mutlak_nem, mutlak_ortam, mutlak_sicaklik
from ..pencere import Pencere
from ..skor import esikle
from ..sozlesme import AKIM_FAZLARI, OlcumTipi, Seviye, Tip
from .taban import Bulgu, KanalDurumu

__all__ = ["calistir"]


def calistir(pencere: Pencere, durum: KanalDurumu, ayar: Ayar) -> list[Bulgu]:
    """Every absolute-limit finding for this window."""
    bulgular: list[Bulgu] = []
    for uretici in (_sicaklik, _ortam, _nem, _faz, _ark):
        bulgu = uretici(pencere, durum, ayar)
        if bulgu is not None:
            bulgular.append(bulgu)
    return bulgular


def _pencere_kaniti(pencere: Pencere) -> list[str]:
    return [
        pencere.tespit_bas.strftime("%Y-%m-%dT%H:%M:%SZ"),
        pencere.tespit_bit.strftime("%Y-%m-%dT%H:%M:%SZ"),
    ]


def _ortam_degeri(pencere: Pencere, durum: KanalDurumu, ayar: Ayar) -> float | None:
    """Latest usable ambient reading, or None if there is not one.

    Several justifications quote ambient alongside the value that fired, because
    a surface at 70 C means something different in a 20 C room and a 45 C one —
    that is the second delta-T comparison basis in section 9.2.
    """
    if not durum.kullanilabilir(OlcumTipi.ORTAM_SICAKLIK):
        return None
    return pencere.seri(OlcumTipi.ORTAM_SICAKLIK).temsil(ayar.pencere.temsil_ornek)


def _sicaklik(pencere: Pencere, durum: KanalDurumu, ayar: Ayar) -> Bulgu | None:
    """Absolute hot-spot temperature. Scenario 2 (overload heating) surfaces here."""
    k1 = ayar.katman1
    if not durum.kullanilabilir(OlcumTipi.TERMAL_MAKS):
        return None
    seri = pencere.seri(OlcumTipi.TERMAL_MAKS)
    son = seri.son
    # Judged on the window's representative value, never on the newest sample.
    deger = seri.temsil(ayar.pencere.temsil_ornek)
    if son is None or deger is None:
        return None

    seviye, skor = esikle(deger, k1.termal_izle, k1.termal_uyari, k1.termal_kritik)
    if seviye is Seviye.NORMAL:
        return None

    esik = {
        Seviye.IZLE: k1.termal_izle,
        Seviye.UYARI: k1.termal_uyari,
        Seviye.KRITIK: k1.termal_kritik,
    }[seviye]
    ortam = _ortam_degeri(pencere, durum, ayar)

    kanit: dict = {
        "olcum_tipi": OlcumTipi.TERMAL_MAKS.value,
        "pencere": _pencere_kaniti(pencere),
        "esik": esik,
        "olculen": round(deger, 2),
    }
    if ortam is not None:
        kanit["ortam_sicaklik"] = round(ortam, 2)
    # The evidence frame, when the module sent one. Contract 3's kanit.kare_id /
    # kanit.piksel are what the dashboard renders.
    if pencere.kare_id is not None:
        kanit["kare_id"] = pencere.kare_id
    if pencere.termal:
        kanit["piksel"] = pencere.termal[-1].piksel

    return Bulgu(
        tip=Tip.SICAK_NOKTA,
        seviye=seviye,
        skor=skor,
        katman=1,
        gerekce=mutlak_sicaklik(deger, esik, ortam),
        zaman=son.zaman,
        kanal=OlcumTipi.TERMAL_MAKS,
        kanit=kanit,
    )


def _ortam(pencere: Pencere, durum: KanalDurumu, ayar: Ayar) -> Bulgu | None:
    """Absolute ambient temperature inside the enclosure."""
    k1 = ayar.katman1
    if not durum.kullanilabilir(OlcumTipi.ORTAM_SICAKLIK):
        return None
    seri = pencere.seri(OlcumTipi.ORTAM_SICAKLIK)
    son = seri.son
    deger = seri.temsil(ayar.pencere.temsil_ornek)
    if son is None or deger is None:
        return None

    seviye, skor = esikle(deger, k1.ortam_izle, k1.ortam_uyari, k1.ortam_kritik)
    if seviye is Seviye.NORMAL:
        return None

    esik = {
        Seviye.IZLE: k1.ortam_izle,
        Seviye.UYARI: k1.ortam_uyari,
        Seviye.KRITIK: k1.ortam_kritik,
    }[seviye]
    return Bulgu(
        tip=Tip.ORTAM_SICAKLIK_YUKSEK,
        seviye=seviye,
        skor=skor,
        katman=1,
        gerekce=mutlak_ortam(deger, esik),
        zaman=son.zaman,
        kanal=OlcumTipi.ORTAM_SICAKLIK,
        kanit={
            "olcum_tipi": OlcumTipi.ORTAM_SICAKLIK.value,
            "pencere": _pencere_kaniti(pencere),
            "esik": esik,
            "olculen": round(deger, 2),
        },
    )


def _nem(pencere: Pencere, durum: KanalDurumu, ayar: Ayar) -> Bulgu | None:
    """Scenario 4 — humidity threshold and condensation risk."""
    k1 = ayar.katman1
    if not durum.kullanilabilir(OlcumTipi.NEM):
        return None
    seri = pencere.seri(OlcumTipi.NEM)
    son = seri.son
    deger = seri.temsil(ayar.pencere.temsil_ornek)
    if son is None or deger is None:
        return None

    seviye, skor = esikle(deger, k1.nem_izle, k1.nem_uyari, k1.nem_kritik)
    if seviye is Seviye.NORMAL:
        return None

    esik = {Seviye.IZLE: k1.nem_izle, Seviye.UYARI: k1.nem_uyari, Seviye.KRITIK: k1.nem_kritik}[
        seviye
    ]
    return Bulgu(
        tip=Tip.NEM_YUKSEK,
        seviye=seviye,
        skor=skor,
        katman=1,
        gerekce=mutlak_nem(deger, esik, _ortam_degeri(pencere, durum, ayar)),
        zaman=son.zaman,
        kanal=OlcumTipi.NEM,
        kanit={
            "olcum_tipi": OlcumTipi.NEM.value,
            "pencere": _pencere_kaniti(pencere),
            "esik": esik,
            "olculen": round(deger, 2),
        },
    )


def _faz(pencere: Pencere, durum: KanalDurumu, ayar: Ayar) -> Bulgu | None:
    """Scenario 3 — phase imbalance as a percentage of the mean line current.

    NEMA's definition: the largest deviation from the mean, over the mean. Layer 3
    looks at the same three currents differently — it asks which phase diverged
    and whether the neutral corroborates. This one is the blunt absolute check.
    """
    k1 = ayar.katman1
    if not durum.hepsi_kullanilabilir(AKIM_FAZLARI):
        return None

    akimlar: dict[OlcumTipi, float] = {}
    zamanlar = []
    for faz in AKIM_FAZLARI:
        seri = pencere.seri(faz)
        son = seri.son
        deger = seri.temsil(ayar.pencere.temsil_ornek)
        if son is None or deger is None:
            return None
        akimlar[faz] = deger
        zamanlar.append(son.zaman)

    ortalama = sum(akimlar.values()) / len(akimlar)
    if ortalama < k1.faz_asgari_akim:
        # Below this load, the percentage is arithmetic noise: 2 A against 1 A is
        # 66% imbalance and means nothing about the panel. Guard, do not report.
        return None

    sapma = max(abs(a - ortalama) for a in akimlar.values())
    dengesizlik = 100.0 * sapma / ortalama

    seviye, skor = esikle(dengesizlik, k1.faz_izle, k1.faz_uyari, k1.faz_kritik)
    if seviye is Seviye.NORMAL:
        return None

    esik = {Seviye.IZLE: k1.faz_izle, Seviye.UYARI: k1.faz_uyari, Seviye.KRITIK: k1.faz_kritik}[
        seviye
    ]
    notr = None
    if durum.kullanilabilir(OlcumTipi.AKIM_NOTR):
        notr = pencere.seri(OlcumTipi.AKIM_NOTR).temsil(ayar.pencere.temsil_ornek)

    return Bulgu(
        tip=Tip.FAZ_DENGESIZLIGI,
        seviye=seviye,
        skor=skor,
        katman=1,
        gerekce=mutlak_faz(
            dengesizlik,
            esik,
            {f.value.upper().replace("AKIM_", ""): v for f, v in akimlar.items()},
            notr,
        ),
        zaman=max(zamanlar),
        kanit={
            "olcum_tipi": OlcumTipi.AKIM_L1.value,
            "pencere": _pencere_kaniti(pencere),
            "esik": esik,
            "olculen": round(dengesizlik, 2),
            "akimlar": {f.value: round(v, 2) for f, v in akimlar.items()},
            "akim_notr": round(notr, 2) if notr is not None else None,
        },
    )


def _ark(pencere: Pencere, durum: KanalDurumu, ayar: Ayar) -> Bulgu | None:
    """Scenario 5 — an arc event.

    Always critical, and deliberately not analysed. Section 3.5: the arc is the
    one event that needs an instant response, and it is the TVOC-2's job — SIL-2
    certified, sub-millisecond. By the time a row reaches this table the protection
    device has already tripped. Re-deciding whether it was really an arc would be
    second-guessing a certified device with a 10-second scan loop.
    """
    k1 = ayar.katman1
    if not durum.kullanilabilir(OlcumTipi.ARK_OLAY):
        return None

    seri = pencere.seri(OlcumTipi.ARK_OLAY)
    tetikleyen = [n for n in seri.gecerli_noktalar if float(n.deger) >= k1.ark_esik]  # type: ignore[arg-type]
    if not tetikleyen:
        return None

    son = tetikleyen[-1]
    toplam = sum(float(n.deger) for n in tetikleyen)  # type: ignore[arg-type]
    return Bulgu(
        tip=Tip.ARK,
        seviye=Seviye.KRITIK,
        skor=1.0,
        katman=1,
        gerekce=ark_olayi(toplam, son.zaman.strftime("%Y-%m-%dT%H:%M:%SZ")),
        zaman=son.zaman,
        kanal=OlcumTipi.ARK_OLAY,
        kanit={
            "olcum_tipi": OlcumTipi.ARK_OLAY.value,
            "pencere": _pencere_kaniti(pencere),
            "esik": k1.ark_esik,
            "olculen": round(toplam, 2),
        },
    )
