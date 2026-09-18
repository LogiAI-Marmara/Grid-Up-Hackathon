"""Layer 2 — deviation from a robust baseline. The early-warning claim lives here.

Section 5 measures two different things on the same channel, and both still
matter, but D2 (post-review) changed what each one is allowed to DO:

  - MAGNITUDE: how far outside its own normal band this module's value sits,
    as a robust z against a median/MAD baseline (section 2.2). Produces a
    finding, capped at `izle` — see `_sapma` and `Katman2Ayari.z_uyari`'s
    docstring for why a module being unusual for ITSELF is not, on its own,
    grounds for more than "keep watching".
  - TREND: whether it has been climbing over the detection window. No longer
    produces a finding or a severity of its own (`_egilim` is gone). Severity
    is meant to be an action taken on the PRESENT condition, and a slope
    describes the future — so trend now only ever appears as informational
    text inside a magnitude-triggered finding's `gerekce` (`_egilim_bilgisi`).

Section 2.3's table is still the argument for WHY trend information matters —
at day 10 of a slow fault nothing is wrong by any absolute measure, and that is
exactly when the maintenance round should be told to call in — it is just no
longer the trend ALONE that gets to say "call the round in now" by promoting a
severity. That job now belongs to the MAGNITUDE criteria (this layer's capped
z, layer 3's unexplained-heat check, and the slow path below), each mapped onto
the same FIST 4-13 bands the review specified.

THE SLOW PATH (decision D1, `_yavas_isinma`) is the other half of the same
argument taken further: even the trend-as-information version of this layer
only sees six hours, so a fault developing over ten days never accumulates
enough rise inside any given six-hour window to be worth mentioning, no matter
how far it has actually come by day 10. See `Katman2YavasAyari`'s docstring —
including why its reference for severity is NOT a sliding baseline, which is
the crux of why this half of the layer exists as a separate mechanism rather
than as a longer `PencereAyari.tespit_sn`.

Why a baseline rather than a fixed threshold at all, for the fast path's own
magnitude check (section 2.1): every panel's load is different. An industrial
board pulling 400 A in the afternoon and a residential one pulling 120 A do not
share a normal temperature, and a single threshold picked to suit both either
floods one with alarms or misses the other's real fault.

BASELINE POISONING — section 5's design note, and the thing most likely to make
the fast path's magnitude check quietly useless. If the baseline is a sliding
window, a fault that develops slowly enough is simply absorbed: each day's
slightly-hotter reading widens the band that the next day is judged against,
and the detector learns the fault as the new normal. Three defences, all
implemented in `PencereGetirici._tabanlar` where the samples are selected:

  1. the baseline window is far longer than the detection window,
  2. it stops short of the present by `taban_bosluk_sn`, so a value is never
     judged against itself,
  3. it is frozen at onset while an episode is open, and stretches inside past
     episodes are excluded.

This layer consumes the result; the guard lives with the query because that is
where the sample selection happens, and a guard applied after the samples are
chosen would already be too late. It is exactly this mechanism the slow path
below cannot reuse for ITS OWN reference, because a fault growing over weeks
poisons even a 14-day sliding window before the window's own defences can
outrun it — see the verified failure mode in
`tests/test_zaman_olcekleri.py::test_yavas_isinma_taban_cizgisi_yutulur`.
"""

from __future__ import annotations

from ..ayar import Ayar, Katman2YavasAyari
from ..gerekce import taban_egilimi, taban_sapmasi, yavas_isinma
from ..pencere import GunlukOzet, Pencere, Seri, TabanCizgisi
from ..skor import esikle, esikle_tavanli
from ..sozlesme import AKIM_FAZLARI, OlcumTipi, Seviye, Tip
from .istatistik import egim, medyan, robust_z, theil_sen
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
    """Baseline findings for every configured channel of this module, both the
    fast path (per channel, this module's own 14-day sliding baseline) and the
    slow path (module-level, decision D1's days-to-weeks normalized heating).
    """
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

    # The slow path is module-level (it needs the hot spot, the ambient AND
    # the dominant current phase together, not one channel at a time), so it
    # runs once per module rather than inside the per-channel loop above.
    yavas = _yavas_isinma(pencere, durum, ayar)
    if yavas is not None:
        bulgular.append(yavas)

    return bulgular


def _pencere_kaniti(pencere: Pencere) -> list[str]:
    return [
        pencere.tespit_bas.strftime("%Y-%m-%dT%H:%M:%SZ"),
        pencere.tespit_bit.strftime("%Y-%m-%dT%H:%M:%SZ"),
    ]


def _sapma(
    seri: Seri, taban: TabanCizgisi, pencere: Pencere, ayar: Ayar
) -> Bulgu | None:
    """Magnitude: how far outside its own band the latest value sits.

    D2 (post-review): capped at `izle`. A module's own history is not the
    normalized physical condition severity is meant to read off — see
    `Katman2Ayari.z_uyari`'s docstring — so `esikle_tavanli` is used here
    instead of `esikle`, with the cap pinned at `Seviye.IZLE`. The trend that
    used to be a second, independently-firing Bulgu (`_egilim`, removed) is
    folded in here as informational text only, via `_egilim_bilgisi`: it can
    make this sentence more informative, and it can never by itself create a
    finding, raise this severity, or fire when the magnitude check below did
    not.
    """
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

    seviye, skor = esikle_tavanli(z, k2.z_izle, k2.z_uyari, k2.z_kritik, Seviye.IZLE)
    if seviye is Seviye.NORMAL:
        return None

    esik = k2.z_izle
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

    egilim_bilgisi = _egilim_bilgisi(seri, taban, pencere, ayar)
    if egilim_bilgisi is not None:
        kanit["egilim_saatlik"] = egilim_bilgisi[1]

    return Bulgu(
        tip=KANAL_TIP[seri.olcum_tipi],
        seviye=seviye,
        skor=skor,
        katman=2,
        gerekce=taban_sapmasi(
            seri.olcum_tipi,
            deger,
            taban.medyan,
            taban.mad,
            z,
            taban.ornek,
            gun,
            egilim_bilgisi=egilim_bilgisi[0] if egilim_bilgisi is not None else None,
        ),
        zaman=son.zaman,
        kanal=seri.olcum_tipi,
        kanit=kanit,
    )


def _egilim_bilgisi(
    seri: Seri, taban: TabanCizgisi, pencere: Pencere, ayar: Ayar
) -> tuple[str, float] | None:
    """The fast-path trend, as TEXT only — never a Bulgu, never a severity.

    D2 (post-review): this used to be `_egilim`, an independently-firing
    finding whose severity came from the slope (`egilim_izle/uyari/kritik`).
    That is exactly the "a forecast set the severity" pattern D2 forbids —
    severity is an action taken on the PRESENT condition, and "it is
    climbing" describes the future, not the present. The computation is
    unchanged (same OLS fit via `istatistik.egim`, same `asgari_delta` /
    `asgari_egilim_ornek` gates so a slope fitted through a few noisy minutes
    stays silent); only what happens with the number changed: it returns text
    to append to a magnitude-triggered finding's `gerekce`, and the hourly
    rate for `kanit`, and nothing else. Returns None when there is nothing
    worth mentioning, exactly as before.
    """
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
    if delta < k2.asgari_delta:
        return None
    if saatlik < k2.egilim_izle:
        # Below the "worth mentioning" floor. Still purely a wording gate now,
        # not a severity gate — see the field's docstring in ayar.py.
        return None

    bas_deger = seri.baslangic(ayar.pencere.temsil_ornek)
    son_deger = seri.temsil(ayar.pencere.temsil_ornek)
    if bas_deger is None or son_deger is None:
        return None

    return (
        taban_egilimi(
            seri.olcum_tipi, bas_deger, son_deger, seri.sure_saat, saatlik, taban.medyan
        ),
        round(saatlik, 4),
    )


# --------------------------------------------------------------------------
# the slow path — decision D1
# --------------------------------------------------------------------------


def _yavas_baskin_faz(
    pencere: Pencere, durum: KanalDurumu, k2y: Katman2YavasAyari
) -> tuple[OlcumTipi, tuple[GunlukOzet, ...]] | None:
    """Same idea as `katman3_iliski.baskin_faz` — the most heavily loaded usable
    phase — but over the slow path's own daily aggregates rather than the fast
    path's raw detection-window samples, so it has its own implementation
    instead of reusing that one on data it was not written for.
    """
    en_iyi: tuple[OlcumTipi, tuple[GunlukOzet, ...]] | None = None
    en_yuksek = -1.0
    for faz in AKIM_FAZLARI:
        if not durum.kullanilabilir(faz):
            continue
        gunler = pencere.yavas_seri(faz)
        if not gunler:
            continue
        ort = medyan([g.ortalama for g in gunler])
        if ort > en_yuksek:
            en_yuksek = ort
            en_iyi = (faz, gunler)
    return en_iyi


def _yavas_isinma(pencere: Pencere, durum: KanalDurumu, ayar: Ayar) -> Bulgu | None:
    """Decision D1's slow path: days-to-weeks normalized heating.

    Severity comes from how far the module's CURRENT normalized-heating level
    sits above its OWN early-in-window reference, mapped onto the FIST 4-13
    bands (see the "THE REFERENCE" comment below for why it is a delta against
    an early-anchored reference and not a raw absolute value, and
    `Katman2YavasAyari`'s docstring for why that reference is not a sliding
    baseline). The Theil-Sen trend across the window is informational only,
    exactly like the fast path's own trend — see `_egilim_bilgisi`.

    D1 is explicit that missing data is not silently substituted: no ambient,
    no usable current phase, or layer 0 having vetoed either, and this check
    does not run for this module this turn — it does not fall back to a
    default the way an earlier version of layer 3's `_akim_sicaklik` did
    (D3's fix).
    """
    k2y = ayar.katman2_yavas
    if not durum.kullanilabilir(OlcumTipi.TERMAL_MAKS):
        return None
    if not durum.kullanilabilir(OlcumTipi.ORTAM_SICAKLIK):
        return None

    termal_gunler = pencere.yavas_seri(OlcumTipi.TERMAL_MAKS)
    ortam_gunler = pencere.yavas_seri(OlcumTipi.ORTAM_SICAKLIK)
    if not termal_gunler or not ortam_gunler:
        return None

    faz = _yavas_baskin_faz(pencere, durum, k2y)
    if faz is None:
        return None
    faz_tipi, akim_gunler = faz

    ortam_gune_gore = {g.gun: g.ortalama for g in ortam_gunler}
    akim_gune_gore = {g.gun: g.ortalama for g in akim_gunler}

    # Normalized-heating series: one point per day-bucket where the day also
    # has an ambient reading and a load above the noise floor. Built once here
    # in Python from the already-aggregated (tens of rows, not tens of
    # thousands) daily buckets — the aggregation itself happened in SQL.
    ilk_gun = termal_gunler[0].gun
    noktalar: list[tuple[float, float]] = []  # (saat-since-ilk_gun, h)
    for g in termal_gunler:
        ortam = ortam_gune_gore.get(g.gun)
        akim = akim_gune_gore.get(g.gun)
        if ortam is None or akim is None or akim < k2y.asgari_akim:
            continue
        h = (g.maksimum - ortam) / (akim**k2y.yuk_ustel)
        saat = (g.gun - ilk_gun).total_seconds() / 3600.0
        noktalar.append((saat, h))

    if len(noktalar) < k2y.asgari_kova:
        # Cold start for the slow path: not enough qualifying days yet to tell
        # a real multi-week trend from bucket-to-bucket noise.
        return None

    saatler = [n[0] for n in noktalar]
    h_degerleri = [n[1] for n in noktalar]
    # Theil-Sen slope is in h-units per hour; the informational sentence wants
    # a per-day rate, which is the scale a multi-week trend is actually read at.
    egilim_saatlik = theil_sen(saatler, h_degerleri)
    egilim_gunluk = egilim_saatlik * 24.0

    son_kova = [n[1] for n in noktalar[-max(1, k2y.temsil_kova) :]]
    h_guncel = medyan(son_kova)

    # THE REFERENCE, per D2: NOT raw (T-ambient)/I^n — the reviewer's own
    # warning is explicit that raw T-ambient "would flag every healthy loaded
    # terminal", because a healthy bolted connection legitimately runs some
    # fixed number of degrees above ambient at rated current; that fixed rise
    # is the "load-expected heating" D2 names, and it is not a fault.
    #
    # So the severity input is EXCESS over this module's OWN early-window
    # normalized-heating level: the median h over the OLDEST `temsil_kova`
    # qualifying buckets in the (up to `pencere_sn`-long) window. This is the
    # "earlier-anchored reference period" D1 offers as an alternative to a
    # sliding baseline — it is computed fresh from each evaluation's own
    # window rather than carried/updated turn to turn, but critically it is
    # anchored to the window's EARLIEST data and never slides forward to
    # re-absorb a fault that develops WITHIN the window, which is exactly the
    # poisoning failure mode a sliding baseline has. A fault already fully
    # established before the window even opens is a real, documented
    # limitation of any window-based reference — not unique to this one — and
    # is why `pencere_sn` defaults to 21 days rather than the 14-day minimum:
    # more runway for the early reference to predate the fault's onset.
    ilk_kova = [n[1] for n in noktalar[: max(1, k2y.temsil_kova)]]
    h_taban = medyan(ilk_kova)

    # Median of the newest few buckets, not the single newest one: the
    # window's very last daily bucket is usually partial (it ends wherever
    # the evaluation instant falls inside that calendar day, not at midnight),
    # and a partial day's average current is noisier than a full one's. Same
    # "representative value" principle as `Seri.temsil` and `h_guncel` above,
    # applied to the load figure the excess gets scaled by.
    akim_son_kova = [g.ortalama for g in akim_gunler[-max(1, k2y.temsil_kova) :]]
    akim_guncel = medyan(akim_son_kova)
    if akim_guncel < k2y.asgari_akim:
        return None

    asiri_isinma = max(h_guncel - h_taban, 0.0) * (akim_guncel**k2y.yuk_ustel)

    seviye, skor = esikle(
        asiri_isinma, k2y.asiri_isinma_izle, k2y.asiri_isinma_uyari, k2y.asiri_isinma_kritik
    )
    if seviye is Seviye.NORMAL:
        return None

    esik = {
        Seviye.IZLE: k2y.asiri_isinma_izle,
        Seviye.UYARI: k2y.asiri_isinma_uyari,
        Seviye.KRITIK: k2y.asiri_isinma_kritik,
    }[seviye]

    # Informational only, per D2: how long at this rate, at today's load,
    # before the EXCESS above the early reference alone would reach the
    # kritik band. Assumes today's load holds, which is exactly why this is a
    # sentence and not a severity input — a forecast is allowed to be wrong
    # about the future.
    gun_tahmini: float | None = None
    if egilim_gunluk > 0:
        hedef_h = h_taban + k2y.asiri_isinma_kritik / (akim_guncel**k2y.yuk_ustel)
        if hedef_h > h_guncel:
            gun_tahmini = (hedef_h - h_guncel) / egilim_gunluk

    son_gun = termal_gunler[-1].gun
    kanit: dict = {
        "olcum_tipi": OlcumTipi.TERMAL_MAKS.value,
        "pencere_gun": round(k2y.pencere_sn / 86400.0, 1),
        "kova_sayisi": len(noktalar),
        "esik": round(esik, 3),
        "olculen": round(asiri_isinma, 3),
        "h_guncel": round(h_guncel, 6),
        "h_taban": round(h_taban, 6),
        "akim_tipi": faz_tipi.value,
        "akim_guncel": round(akim_guncel, 2),
        "yuk_ustel": k2y.yuk_ustel,
        "egilim_gunluk": round(egilim_gunluk, 6),
    }
    if pencere.kare_id is not None:
        kanit["kare_id"] = pencere.kare_id

    return Bulgu(
        tip=Tip.AKIM_SICAKLIK_SAPMASI,
        seviye=seviye,
        skor=skor,
        katman=2,
        gerekce=yavas_isinma(
            len(noktalar),
            akim_guncel,
            k2y.yuk_ustel,
            asiri_isinma,
            esik,
            egilim_gunluk,
            gun_tahmini,
        ),
        zaman=son_gun,
        kanal=OlcumTipi.TERMAL_MAKS,
        kanit=kanit,
    )
