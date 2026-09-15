"""Layer 0 — sensor health. Runs before everything else and can veto a channel.

Section 5: this layer exists because a broken sensor does not report "broken",
it reports 0 or it reports 500, and both look exactly like the anomaly the other
three layers are built to find. Without the separation the system raises a fire
alarm every time a thermocouple comes loose — and nothing destroys an operator's
trust faster, which makes this the layer that protects the false-alarm metric
(section 2.6) more than any other.

The veto is per *channel*, not per module. A dead humidity sensor must not blind
the thermal detector on the same module.

Three independent tests, because the three failure modes look different:

  - `kalite`      the module itself said the reading is untrustworthy
  - frozen value  the module does not know, but physics does: real quantities
                  do not hold still to six decimal places
  - out of range  the value is not a measurement at all

Plus the module's own health (scenario 7): silence, and clock drift.
"""

from __future__ import annotations

from datetime import timedelta

from ..ayar import Ayar
from ..gerekce import aralik_disi, donuk_sensor, kalite_bozuk, modul_sessiz, saat_kaymasi
from ..pencere import Pencere, Seri
from ..skor import SEVIYE_SKOR_TABANI
from ..sozlesme import OLCUM_ARALIK, Kalite, OlcumTipi, Seviye, Tip
from .taban import Bulgu, KanalDurumu

__all__ = ["calistir"]


def _skor(seviye: Seviye) -> float:
    """Mid-band score for a layer-0 finding.

    Sensor faults are graded by *which* fault, not by magnitude — a frozen sensor
    is not "more frozen" than another one — so they take the middle of their
    severity band and rank below a genuine deviation of the same severity.
    """
    alt, ust = SEVIYE_SKOR_TABANI[seviye]
    return round((alt + ust) / 2.0, 4)


def calistir(pencere: Pencere, ayar: Ayar) -> tuple[list[Bulgu], KanalDurumu]:
    """Return layer 0's findings and the set of channels the later layers may use."""
    k0 = ayar.katman0
    bulgular: list[Bulgu] = []
    bozuk: set[OlcumTipi] = set()

    for olcum_tipi, seri in sorted(pencere.seriler.items(), key=lambda kv: kv[0].value):
        bulgu = _kanal_sagligi(seri, pencere, ayar)
        if bulgu is not None:
            bulgular.append(bulgu)
            bozuk.add(olcum_tipi)

    bulgular.extend(_modul_sagligi(pencere, ayar))
    return bulgular, KanalDurumu(bozuk=frozenset(bozuk))


def _kanal_sagligi(seri: Seri, pencere: Pencere, ayar: Ayar) -> Bulgu | None:
    """Judge one channel. Returns the first fault found, or None if it is healthy.

    The order of the three tests matters. Quality comes first because it is the
    module's own verdict and outranks anything we infer; out-of-range comes before
    the frozen test because a sensor stuck at an impossible value is better
    described as impossible than as stuck.
    """
    k0 = ayar.katman0
    zaman = seri.son.zaman if seri.son is not None else pencere.tetikleyici_zaman
    if seri.noktalar:
        zaman = seri.noktalar[-1].zaman

    if len(seri.noktalar) < k0.asgari_ornek:
        # Too few samples to judge. Not "healthy" — unjudged. Returning None
        # lets the later layers see the channel, and they have their own minimum
        # sample guards; declaring a fault here would make every cold start a
        # sensor failure.
        return None

    # --- 1. the module's own quality flag ---------------------------------
    toplam = len(seri.noktalar)
    bozuk_sayisi = sum(1 for n in seri.noktalar if n.kalite is not Kalite.IYI)
    if bozuk_sayisi / toplam >= k0.kalite_orani:
        baskin = _baskin_kalite(seri)
        return Bulgu(
            tip=Tip.SENSOR_ARIZASI,
            seviye=k0.kalite_seviye,
            skor=_skor(k0.kalite_seviye),
            katman=0,
            gerekce=kalite_bozuk(seri.olcum_tipi, bozuk_sayisi, toplam, baskin.value),
            zaman=zaman,
            kanal=seri.olcum_tipi,
            kanit={
                "olcum_tipi": seri.olcum_tipi.value,
                "pencere": _pencere_kaniti(pencere),
                "esik": round(k0.kalite_orani, 4),
                "olculen": round(bozuk_sayisi / toplam, 4),
                "kalite": baskin.value,
            },
        )

    # --- 2. physically impossible values ----------------------------------
    alt, ust = OLCUM_ARALIK[seri.olcum_tipi]
    for nokta in reversed(seri.noktalar):
        if nokta.deger is None:
            continue
        if nokta.deger < alt or nokta.deger > ust:
            return Bulgu(
                tip=Tip.SENSOR_ARIZASI,
                seviye=k0.aralik_disi_seviye,
                skor=_skor(k0.aralik_disi_seviye),
                katman=0,
                gerekce=aralik_disi(seri.olcum_tipi, nokta.deger, alt, ust),
                zaman=nokta.zaman,
                kanal=seri.olcum_tipi,
                kanit={
                    "olcum_tipi": seri.olcum_tipi.value,
                    "pencere": _pencere_kaniti(pencere),
                    "esik": ust if nokta.deger > ust else alt,
                    "olculen": round(float(nokta.deger), 3),
                },
            )

    # --- 3. frozen value ---------------------------------------------------
    if seri.olcum_tipi not in k0.donuk_muaf:
        donuk = _donuk_kuyruk(seri, k0.donuk_tolerans)
        if donuk is not None and donuk[0] >= k0.donuk_ardisik:
            ardisik, deger, dakika = donuk
            return Bulgu(
                tip=Tip.SENSOR_ARIZASI,
                seviye=k0.donuk_seviye,
                skor=_skor(k0.donuk_seviye),
                katman=0,
                gerekce=donuk_sensor(seri.olcum_tipi, ardisik, deger, dakika),
                zaman=zaman,
                kanal=seri.olcum_tipi,
                kanit={
                    "olcum_tipi": seri.olcum_tipi.value,
                    "pencere": _pencere_kaniti(pencere),
                    "esik": k0.donuk_ardisik,
                    "olculen": ardisik,
                    "donuk_deger": round(float(deger), 3),
                },
            )

    return None


def _baskin_kalite(seri: Seri) -> Kalite:
    """The more serious of the non-`iyi` qualities present. `yok` outranks `supheli`."""
    kaliteler = {n.kalite for n in seri.noktalar}
    if Kalite.YOK in kaliteler:
        return Kalite.YOK
    if Kalite.SUPHELI in kaliteler:
        return Kalite.SUPHELI
    return Kalite.IYI


def _donuk_kuyruk(seri: Seri, tolerans: float) -> tuple[int, float, float] | None:
    """Length of the run of identical values ending at the newest sample.

    Measured from the end backwards rather than as "the longest run anywhere",
    because a sensor that froze and recovered is a different, milder story than
    one that is frozen right now, and only the second should stop the later
    layers from reading the channel.

    Returns (run length, the repeated value, the run's duration in minutes).
    """
    gecerli = seri.gecerli_noktalar
    if len(gecerli) < 2:
        return None
    son = gecerli[-1]
    referans = float(son.deger)  # type: ignore[arg-type]
    ardisik = 1
    en_eski = son
    for nokta in reversed(gecerli[:-1]):
        if abs(float(nokta.deger) - referans) > tolerans:  # type: ignore[arg-type]
            break
        ardisik += 1
        en_eski = nokta
    dakika = (son.zaman - en_eski.zaman).total_seconds() / 60.0
    return ardisik, referans, dakika


def _modul_sagligi(pencere: Pencere, ayar: Ayar) -> list[Bulgu]:
    """Scenario 7 — the module's own health, as far as the database can show it.

    Two signals are available: silence, and the gap between `zaman` and
    `alindi_zaman`. The contract's `modul_durum` also carries `besleme` and
    `sinyal`, which would make this layer considerably stronger — but the
    collector on track A's branch drops both on the floor (it persists only
    `yazilim_surumu` and `son_gorulme` into `gridup.modul`), so there is nowhere
    to read them from. Recorded in the README under "Contract mismatches";
    wiring them up here is a few lines once a table exists.
    """
    k0 = ayar.katman0
    bulgular: list[Bulgu] = []

    if pencere.son_olcum_zaman is not None:
        sessizlik = (pencere.simdi - pencere.son_olcum_zaman).total_seconds()
        if sessizlik > k0.sessizlik_sn:
            bulgular.append(
                Bulgu(
                    tip=Tip.MODUL_SAGLIK,
                    seviye=k0.sessizlik_seviye,
                    skor=_skor(k0.sessizlik_seviye),
                    katman=0,
                    gerekce=modul_sessiz(
                        sessizlik / 60.0,
                        pencere.son_olcum_zaman.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    ),
                    zaman=pencere.son_olcum_zaman,
                    kanit={
                        "pencere": _pencere_kaniti(pencere),
                        "esik": k0.sessizlik_sn,
                        "olculen": round(sessizlik, 1),
                    },
                )
            )

    kayma = _azami_saat_kaymasi(pencere)
    if kayma is not None and abs(kayma[0]) > k0.saat_kaymasi_sn:
        kayma_sn, kayma_zaman = kayma
        bulgular.append(
            Bulgu(
                tip=Tip.MODUL_SAGLIK,
                seviye=k0.saat_kaymasi_seviye,
                skor=_skor(k0.saat_kaymasi_seviye),
                katman=0,
                gerekce=saat_kaymasi(kayma_sn, k0.saat_kaymasi_sn),
                zaman=kayma_zaman,
                kanit={
                    "pencere": _pencere_kaniti(pencere),
                    "esik": k0.saat_kaymasi_sn,
                    "olculen": round(kayma_sn, 1),
                },
            )
        )

    return bulgular


def _azami_saat_kaymasi(pencere: Pencere):
    """Largest |arrival - measurement| gap in the window, with its timestamp.

    A positive gap is ordinary network latency; the threshold in `ayar.py` is
    what separates "the radio was slow" from "the module's clock is wrong". A
    *negative* gap — measured in the future relative to its own arrival — can
    only be a wrong clock.
    """
    en_buyuk = None
    for seri in pencere.seriler.values():
        for nokta in seri.noktalar:
            gecikme = nokta.gecikme_sn
            if en_buyuk is None or abs(gecikme) > abs(en_buyuk[0]):
                en_buyuk = (gecikme, nokta.zaman)
    return en_buyuk


def _pencere_kaniti(pencere: Pencere) -> list[str]:
    """`kanit.pencere` — the window the detector looked at, as [bas, bit]."""
    return [
        pencere.tespit_bas.strftime("%Y-%m-%dT%H:%M:%SZ"),
        pencere.tespit_bit.strftime("%Y-%m-%dT%H:%M:%SZ"),
    ]
