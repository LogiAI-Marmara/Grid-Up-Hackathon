"""Layer 2 — deviation from a robust baseline. The early-warning claim lives here.

Section 5 measures two different things on the same channel, and both are needed:

  - MAGNITUDE: how far outside its own normal band this module's value sits,
    as a robust z against a median/MAD baseline (section 2.2).
  - TREND: whether it has been climbing over the detection window.

The trend half is the one that matters. A point being 60 C is not interesting;
having gone 45 -> 60 over a fortnight is. Section 2.3's table makes the argument
concretely — at day 10 nothing is wrong by any absolute measure, and that is
exactly when the maintenance round should be told to call in. Without the trend
there is no early warning, only a late one.

Why a baseline rather than a fixed threshold at all (section 2.1): every panel's
load is different. An industrial board pulling 400 A in the afternoon and a
residential one pulling 120 A do not share a normal temperature, and a single
threshold picked to suit both either floods one with alarms or misses the other's
real fault.

BASELINE POISONING — section 5's design note, and the thing most likely to make
this layer quietly useless. If the baseline is a sliding window, a fault that
develops slowly enough is simply absorbed: each day's slightly-hotter reading
widens the band that the next day is judged against, and the detector learns the
fault as the new normal. Three defences, all implemented in
`PencereGetirici._tabanlar` where the samples are selected:

  1. the baseline window is far longer than the detection window,
  2. it stops short of the present by `taban_bosluk_sn`, so a value is never
     judged against itself,
  3. it is frozen at onset while an episode is open, and stretches inside past
     episodes are excluded.

This layer consumes the result; the guard lives with the query because that is
where the sample selection happens, and a guard applied after the samples are
chosen would already be too late.
"""

from __future__ import annotations

from ..ayar import Ayar
from ..gerekce import taban_egilimi, taban_sapmasi
from ..pencere import Pencere, Seri, TabanCizgisi
from ..skor import esikle
from ..sozlesme import OlcumTipi, Seviye, Tip
from .istatistik import egim, robust_z
from .taban import Bulgu, KanalDurumu

__all__ = ["calistir", "KANAL_TIP"]


#: Which anomaly type a baseline deviation on this channel becomes. Ambient is
#: its own type: a hot room is a ventilation problem, not a hot spot, and sending
#: a crew to look for a loose terminal that is not there is a false alarm even
#: though the temperature really did rise.
KANAL_TIP: dict[OlcumTipi, Tip] = {
    OlcumTipi.TERMAL_MAKS: Tip.SICAK_NOKTA,
    OlcumTipi.TERMAL_ORT: Tip.SICAK_NOKTA,
    OlcumTipi.ORTAM_SICAKLIK: Tip.ORTAM_SICAKLIK_YUKSEK,
    OlcumTipi.NEM: Tip.NEM_YUKSEK,
}


def calistir(pencere: Pencere, durum: KanalDurumu, ayar: Ayar) -> list[Bulgu]:
    """Baseline findings for every configured channel of this module."""
    k2 = ayar.katman2
    bulgular: list[Bulgu] = []

    for kanal in k2.kanallar:
        if not durum.kullanilabilir(kanal):
            # Layer 0 vetoed this channel. Judging a broken sensor against a
            # baseline is how a loose thermocouple becomes a fire alarm.
            continue
        seri = pencere.seri(kanal)
        if seri.bos:
            continue
        taban = pencere.taban(kanal)
        if taban is None or taban.ornek < ayar.pencere.asgari_taban_ornek:
            # Cold start. Declining to fire is the right answer: a module
            # installed this morning has no normal yet, and inventing one from
            # three readings produces confident nonsense.
            continue

        sapma = _sapma(seri, taban, pencere, ayar)
        if sapma is not None:
            bulgular.append(sapma)

        egilim = _egilim(seri, taban, pencere, ayar)
        if egilim is not None:
            bulgular.append(egilim)

    return bulgular


def _pencere_kaniti(pencere: Pencere) -> list[str]:
    return [
        pencere.tespit_bas.strftime("%Y-%m-%dT%H:%M:%SZ"),
        pencere.tespit_bit.strftime("%Y-%m-%dT%H:%M:%SZ"),
    ]


def _sapma(
    seri: Seri, taban: TabanCizgisi, pencere: Pencere, ayar: Ayar
) -> Bulgu | None:
    """Magnitude: how far outside its own band the latest value sits."""
    k2 = ayar.katman2
    son = seri.son
    # The median of the newest few samples, not the newest one: a baseline is a
    # robust statistic, and comparing a raw sample against it would throw that
    # robustness away on the one end of the comparison that is noisiest.
    deger = seri.temsil(ayar.pencere.temsil_ornek)
    if son is None or deger is None:
        return None

    z = robust_z(deger, taban.medyan, taban.mad, k2.asgari_mad)

    # One-sided on purpose. A terminal that cooled below its own median is not a
    # fault, and reporting it as one is a false alarm with no work order attached.
    if z <= 0:
        return None

    seviye, skor = esikle(z, k2.z_izle, k2.z_uyari, k2.z_kritik)
    if seviye is Seviye.NORMAL:
        return None

    esik = {Seviye.IZLE: k2.z_izle, Seviye.UYARI: k2.z_uyari, Seviye.KRITIK: k2.z_kritik}[seviye]
    gun = (taban.bit - taban.bas).total_seconds() / 86400.0

    kanit: dict = {
        "olcum_tipi": seri.olcum_tipi.value,
        "pencere": _pencere_kaniti(pencere),
        "esik": round(esik, 3),
        "olculen": round(z, 3),
        "taban_medyan": round(taban.medyan, 3),
        "taban_mad": round(taban.mad, 3),
        "taban_ornek": taban.ornek,
        "taban_donduruldu": taban.donduruldu,
        "deger": round(deger, 3),
    }
    if seri.olcum_tipi is OlcumTipi.TERMAL_MAKS:
        if pencere.kare_id is not None:
            kanit["kare_id"] = pencere.kare_id
        if pencere.termal:
            kanit["piksel"] = pencere.termal[-1].piksel

    return Bulgu(
        tip=KANAL_TIP[seri.olcum_tipi],
        seviye=seviye,
        skor=skor,
        katman=2,
        gerekce=taban_sapmasi(
            seri.olcum_tipi, deger, taban.medyan, taban.mad, z, taban.ornek, gun
        ),
        zaman=son.zaman,
        kanal=seri.olcum_tipi,
        kanit=kanit,
    )


def _egilim(
    seri: Seri, taban: TabanCizgisi, pencere: Pencere, ayar: Ayar
) -> Bulgu | None:
    """Trend: the half of this layer that fires while the value is still harmless."""
    k2 = ayar.katman2
    gecerli = seri.gecerli_noktalar
    if len(gecerli) < k2.asgari_egilim_ornek:
        return None

    saatler = seri.zaman_saat(pencere.tespit_bas)
    degerler = seri.degerler
    saatlik = egim(saatler, degerler)
    if saatlik <= 0:
        return None

    delta = seri.delta_temsil(ayar.pencere.temsil_ornek)
    # Two conditions, not one. The slope says "it is climbing"; the total rise
    # says "it has actually got somewhere". A steep slope fitted through ten
    # minutes of noise passes the first and fails the second, and that is the
    # whole difference between an early warning and a nuisance.
    if delta < k2.asgari_delta:
        return None

    seviye, skor = esikle(saatlik, k2.egilim_izle, k2.egilim_uyari, k2.egilim_kritik)
    if seviye is Seviye.NORMAL:
        return None

    esik = {
        Seviye.IZLE: k2.egilim_izle,
        Seviye.UYARI: k2.egilim_uyari,
        Seviye.KRITIK: k2.egilim_kritik,
    }[seviye]

    ilk, son = seri.ilk, seri.son
    bas_deger = seri.baslangic(ayar.pencere.temsil_ornek)
    son_deger = seri.temsil(ayar.pencere.temsil_ornek)
    if ilk is None or son is None or bas_deger is None or son_deger is None:
        return None

    kanit: dict = {
        "olcum_tipi": seri.olcum_tipi.value,
        "pencere": _pencere_kaniti(pencere),
        "esik": round(esik, 3),
        "olculen": round(saatlik, 4),
        "delta": round(delta, 3),
        "sure_saat": round(seri.sure_saat, 3),
        "taban_medyan": round(taban.medyan, 3),
        "taban_donduruldu": taban.donduruldu,
    }
    if seri.olcum_tipi is OlcumTipi.TERMAL_MAKS:
        if pencere.kare_id is not None:
            kanit["kare_id"] = pencere.kare_id
        if pencere.termal:
            kanit["piksel"] = pencere.termal[-1].piksel

    return Bulgu(
        tip=KANAL_TIP[seri.olcum_tipi],
        seviye=seviye,
        skor=skor,
        katman=2,
        gerekce=taban_egilimi(
            seri.olcum_tipi,
            bas_deger,
            son_deger,
            seri.sure_saat,
            saatlik,
            taban.medyan,
        ),
        zaman=son.zaman,
        kanal=seri.olcum_tipi,
        kanit=kanit,
    )
