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

Plus the module's own health (scenario 7): silence, clock drift, and — since
the integration phase gave `modul_durum` a table — loss of mains supply and a
fading radio link.
"""

from __future__ import annotations

from datetime import datetime

from ..ayar import Ayar
from ..gerekce import (
    aralik_disi,
    besleme_kaybi,
    donuk_sensor,
    ileri_tarihli,
    kalite_bozuk,
    modul_sessiz,
    saat_kaymasi,
    sinyal_zayif,
)
from ..pencere import Pencere, Seri
from ..skor import SEVIYE_SKOR_TABANI
from ..sozlesme import OLCUM_ARALIK, Besleme, Kalite, OlcumTipi, Seviye, Tip
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

    # --- 1. physically impossible values ------------------------------------
    #
    # D3 fix (post-review): this used to run AFTER the minimum-sample early
    # return below, which meant a module with, say, two samples — one of them
    # a value the sensor's own physical range rules out — was waved through as
    # merely "unjudged, too few samples" instead of being caught. The shared DB
    # CHECK constraint (`OLCUM_ARALIK`) already rejects such rows at the
    # PostgreSQL layer for anything that goes through the normal write path, so
    # this in-process check is a second line of defence — for data written by
    # another path, or for a build running against an older schema — and a
    # defence that only engages once six samples have accumulated is not a
    # defence for the case that matters most: catching it immediately.
    # Verified at the unit level (an out-of-range value cannot be inserted into
    # Postgres directly, since the schema already rejects it) in
    # tests/test_katmanlar.py::test_kanal_sagligi_aralik_disi_az_ornekle.
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

    if len(seri.noktalar) < k0.asgari_ornek:
        # Too few samples to judge the remaining, statistical tests. Not
        # "healthy" — unjudged. Returning None lets the later layers see the
        # channel, and they have their own minimum sample guards; declaring a
        # fault here would make every cold start a sensor failure. The range
        # check above is exempt from this guard on purpose — a single
        # impossible value does not need six samples to be impossible.
        return None

    # --- 2. the module's own quality flag -----------------------------------
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
    """Scenario 7 — the module's own health.

    Four signals, all `modul_saglik`: silence, clock drift, loss of mains
    supply, and a weak link. The engine keeps one finding per `tip`, so when
    several fire at once the worst survives and `kanit.neden` says which. Each
    test is independent — a module on backup power with a good clock is a
    power finding and nothing else.
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
                        "neden": "sessizlik",
                        "pencere": _pencere_kaniti(pencere),
                        "esik": k0.sessizlik_sn,
                        "olculen": round(sessizlik, 1),
                    },
                )
            )

    kayma = _saat_kaymasi(pencere, ayar)
    if kayma is not None:
        bulgular.append(kayma)

    bulgular.extend(_durum_sagligi(pencere, ayar))
    return bulgular


def _saat_kaymasi(pencere: Pencere, ayar: Ayar) -> Bulgu | None:
    """Clock drift, per the integration-phase table — distinguished from late data.

    Per sample the gap is `alindi_zaman - zaman`. Three cases:

      gap < -tolerance anywhere    future-dated: measured after it was received.
                                   Certain drift; the module's clock is ahead.
      min(gap) > threshold         nothing in the window was fresh, so the
                                   offset is in the clock, not the network.
      min(gap) ~ 0, max(gap) high  late (backfilled) data — a module that lost
                                   its uplink and then sent the backlog. Not an
                                   anomaly. `/saglik` reports it as data delay.

    The previous rule judged the *maximum* gap and therefore alarmed on every
    backlog, which contradicted section 3.6's promise that late data is caught
    for free. Status rows count too: they ride in the same packet as the
    measurements, so they carry the same clock.
    """
    k0 = ayar.katman0
    en_kucuk: tuple[float, datetime] | None = None
    en_ileri: tuple[float, datetime] | None = None

    def bak(gecikme: float, zaman: datetime) -> None:
        nonlocal en_kucuk, en_ileri
        if en_kucuk is None or gecikme < en_kucuk[0]:
            en_kucuk = (gecikme, zaman)
        if gecikme < -k0.ileri_tarih_tolerans_sn and (
            en_ileri is None or gecikme < en_ileri[0]
        ):
            en_ileri = (gecikme, zaman)

    for seri in pencere.seriler.values():
        for nokta in seri.noktalar:
            bak(nokta.gecikme_sn, nokta.zaman)
    for durum in pencere.durumlar:
        bak(durum.gecikme_sn, durum.zaman)

    if en_ileri is not None:
        kayma_sn, kayma_zaman = en_ileri
        return Bulgu(
            tip=Tip.MODUL_SAGLIK,
            seviye=k0.saat_kaymasi_seviye,
            skor=_skor(k0.saat_kaymasi_seviye),
            katman=0,
            gerekce=ileri_tarihli(kayma_sn, kayma_zaman.strftime("%Y-%m-%dT%H:%M:%SZ")),
            zaman=kayma_zaman,
            kanit={
                "neden": "saat_kaymasi",
                "yon": "ileri",
                "pencere": _pencere_kaniti(pencere),
                "esik": -k0.ileri_tarih_tolerans_sn,
                "olculen": round(kayma_sn, 1),
            },
        )

    if en_kucuk is not None and en_kucuk[0] > k0.saat_kaymasi_sn:
        kayma_sn, kayma_zaman = en_kucuk
        return Bulgu(
            tip=Tip.MODUL_SAGLIK,
            seviye=k0.saat_kaymasi_seviye,
            skor=_skor(k0.saat_kaymasi_seviye),
            katman=0,
            gerekce=saat_kaymasi(kayma_sn, k0.saat_kaymasi_sn),
            zaman=kayma_zaman,
            kanit={
                "neden": "saat_kaymasi",
                "yon": "geri",
                "pencere": _pencere_kaniti(pencere),
                "esik": k0.saat_kaymasi_sn,
                "olculen": round(kayma_sn, 1),
            },
        )
    return None


def _durum_sagligi(pencere: Pencere, ayar: Ayar) -> list[Bulgu]:
    """Power loss and weak signal, from the module's own status rows.

    `besleme = yedek` on the newest `besleme_yedek_ardisik` rows is a power
    finding; the median `sinyal` over the newest `sinyal_ornek` rows below the
    dBm threshold is a link finding. Both take a few rows rather than one, for
    the same reason no layer judges a single sample — but a run of packets
    saying "I am on the capacitor" is the module's own statement, and it is
    reported without waiting for the silence that would otherwise follow.
    """
    k0 = ayar.katman0
    durumlar = pencere.durumlar
    bulgular: list[Bulgu] = []
    if len(durumlar) < k0.asgari_durum_ornek:
        return bulgular

    # --- supply ------------------------------------------------------------
    ardisik = 0
    for durum in reversed(durumlar):
        if durum.besleme is not Besleme.YEDEK:
            break
        ardisik += 1
    if ardisik >= max(1, k0.besleme_yedek_ardisik):
        ilk_yedek = durumlar[len(durumlar) - ardisik]
        dakika = (durumlar[-1].zaman - ilk_yedek.zaman).total_seconds() / 60.0
        bulgular.append(
            Bulgu(
                tip=Tip.MODUL_SAGLIK,
                seviye=k0.besleme_seviye,
                skor=_skor(k0.besleme_seviye),
                katman=0,
                gerekce=besleme_kaybi(
                    ardisik, dakika, ilk_yedek.zaman.strftime("%Y-%m-%dT%H:%M:%SZ")
                ),
                zaman=durumlar[-1].zaman,
                kanit={
                    "neden": "besleme",
                    "pencere": _pencere_kaniti(pencere),
                    "esik": k0.besleme_yedek_ardisik,
                    "olculen": ardisik,
                    "besleme": Besleme.YEDEK.value,
                    "ilk_yedek": ilk_yedek.zaman.strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            )
        )

    # --- link --------------------------------------------------------------
    sonuncular = durumlar[-max(1, k0.sinyal_ornek):]
    sinyaller = sorted(d.sinyal for d in sonuncular)
    n = len(sinyaller)
    medyan = (
        float(sinyaller[n // 2])
        if n % 2
        else (sinyaller[n // 2 - 1] + sinyaller[n // 2]) / 2.0
    )
    if medyan < k0.sinyal_zayif_dbm:
        bulgular.append(
            Bulgu(
                tip=Tip.MODUL_SAGLIK,
                seviye=k0.sinyal_seviye,
                skor=_skor(k0.sinyal_seviye),
                katman=0,
                gerekce=sinyal_zayif(medyan, k0.sinyal_zayif_dbm, n),
                zaman=durumlar[-1].zaman,
                kanit={
                    "neden": "sinyal",
                    "pencere": _pencere_kaniti(pencere),
                    "esik": k0.sinyal_zayif_dbm,
                    "olculen": round(medyan, 1),
                    "ornek": n,
                },
            )
        )
    return bulgular


def _pencere_kaniti(pencere: Pencere) -> list[str]:
    """`kanit.pencere` — the window the detector looked at, as [bas, bit]."""
    return [
        pencere.tespit_bas.strftime("%Y-%m-%dT%H:%M:%SZ"),
        pencere.tespit_bit.strftime("%Y-%m-%dT%H:%M:%SZ"),
    ]
