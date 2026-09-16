"""Acceptance tests for decisions D1-D3 (multi-time-scale detection, severity
semantics, and the two fixes) — the track owner's required A1-A6 set, plus the
regression that proves the failure mode D1 fixes was real.

Real PostgreSQL throughout, via `PencereGetirici` and `degerlendir`: these are
not layer unit tests with a hand-built `Pencere`, they run the SQL the slow
path actually depends on (`PencereGetirici._yavas_ozetler`).
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from analiz.ayar import Ayar
from analiz.dedektor import degerlendir
from analiz.dedektor.istatistik import mad, medyan, robust_z
from analiz.pencere import PencereGetirici
from analiz.senaryolar import Profil, Uretec
from analiz.sozlesme import Kalite, OlcumTipi, Seviye, Tip


def _pencere(baglanti, ayar, modul_id, an):
    return PencereGetirici(baglanti, ayar).getir({modul_id: an})[modul_id]


def _en_yuksek_seviye(sonuc):
    if not sonuc.bulgular:
        return None
    from analiz.sozlesme import SEVIYE_SIRA

    return max((b.seviye for b in sonuc.bulgular), key=lambda s: SEVIYE_SIRA[s])


# --------------------------------------------------------------------------
# A1 — the slow drift the fast path (and the OLD sliding baseline) must miss,
# and the slow path (D1) must catch, at izle by day 10 and uyari by day 25.
# --------------------------------------------------------------------------


def test_a1_yavas_isinma_gun10_izle_gun25_uyari(baglanti, fikstur, ayar, an):
    modul_id = "TR041-P09-M1"
    # 30-day write, steady load and ambient, termal_maks drifting toward the
    # module's own early-window level. A concave (t/25)**0.4 ramp rather than
    # a straight line: the slow path's reference is the median of the
    # EARLIEST few daily buckets (see katman2_taban._yavas_isinma's "THE
    # REFERENCE" comment), so a ramp with near-zero early slope keeps that
    # reference clean at ~0 excess, matching a real fault's actual onset
    # rather than the reference itself already being partway up the ramp.
    simdi = an
    gecmis_gun = 30.0

    def yavas_bozucu(nokta_an, ilerleme_g, ortam, akim, termal, rng):
        gun = (nokta_an - (simdi - timedelta(days=gecmis_gun))).total_seconds() / 86400.0
        oran = min(max(gun, 0.0) / 25.0, 1.0)
        return ortam, akim, termal + 50.0 * (oran**0.4)

    uretec = Uretec(fikstur=fikstur, simdi=simdi, profil=Profil(), tohum=1)
    uretec.uret(modul_id, gecmis_gun=gecmis_gun, tespit_saat=7.0, yavas_bozucu=yavas_bozucu)
    fikstur.yaz()

    gecmis_bas = simdi - timedelta(days=gecmis_gun)
    gun10 = gecmis_bas + timedelta(days=10)
    gun25 = gecmis_bas + timedelta(days=25)

    pencere10 = _pencere(baglanti, ayar, modul_id, gun10)
    sonuc10 = degerlendir(pencere10, ayar)
    bulgu10 = sonuc10.bulgu(Tip.AKIM_SICAKLIK_SAPMASI)
    assert bulgu10 is not None, "the slow path must have a finding by day 10"
    assert bulgu10.seviye is Seviye.IZLE, f"day 10 must be izle, got {bulgu10.seviye}"
    assert bulgu10.katman == 2

    pencere25 = _pencere(baglanti, ayar, modul_id, gun25)
    sonuc25 = degerlendir(pencere25, ayar)
    bulgu25 = sonuc25.bulgu(Tip.AKIM_SICAKLIK_SAPMASI)
    assert bulgu25 is not None, "the slow path must still have a finding by day 25"
    assert bulgu25.seviye is Seviye.UYARI, f"day 25 must be uyari, got {bulgu25.seviye}"


def test_yavas_isinma_taban_cizgisi_yutulur(baglanti, fikstur, ayar, an):
    """Regression: the OLD sliding baseline (`Katman2Ayari`'s 14-day median/MAD)
    really does absorb a 10-day linear drift, which is exactly why the slow
    path (D1) cannot use it as its own reference.

    Reproduces the failure mode named in the review: feed the fast baseline a
    10-day drift from 45 to 60 C and its median ends up close to the drifting
    value's own recent level, with a MAD wide enough that the robust z stays
    small — "no finding" from the mechanism that exists to be the early
    warning. This is checked directly against the baseline the fast path
    would compute, not against whether an episode opened, so it keeps failing
    honestly if a future change quietly widens the baseline window instead of
    fixing the reference problem.
    """
    modul_id = "TR041-P09-M2"
    simdi = an
    gecmis_gun = 30.0

    def yavas_bozucu(nokta_an, ilerleme_g, ortam, akim, termal, rng):
        # Same drift as A1, isolated to days 0-10 of the 30-day write so the
        # baseline's own 14-day window (ending ~6h before the checkpoint)
        # sees mostly-drifted data, matching the reviewer's own example.
        gun = ilerleme_g * gecmis_gun
        oran = min(max(gun / 10.0, 0.0), 1.0)
        return ortam, akim, termal + 15.0 * oran

    uretec = Uretec(fikstur=fikstur, simdi=simdi, profil=Profil(), tohum=2)
    uretec.uret(modul_id, gecmis_gun=gecmis_gun, tespit_saat=7.0, yavas_bozucu=yavas_bozucu)
    fikstur.yaz()

    gecmis_bas = simdi - timedelta(days=gecmis_gun)
    gun12 = gecmis_bas + timedelta(days=12)  # just past the drift's own end

    pencere = _pencere(baglanti, ayar, modul_id, gun12)
    taban = pencere.taban(OlcumTipi.TERMAL_MAKS)
    assert taban is not None and taban.yeterli

    deger = pencere.seri(OlcumTipi.TERMAL_MAKS).temsil(ayar.pencere.temsil_ornek)
    assert deger is not None and deger > 55.0, "the drift should have reached ~60 C by day 12"
    # The baseline absorbed the drift: its own median sits close to the
    # drifted value, so the robust z the FAST path's magnitude check sees
    # stays under its (already capped-at-izle) izle threshold.
    z = robust_z(deger, taban.medyan, taban.mad, ayar.katman2.asgari_mad)
    assert taban.medyan > 48.0, "median should have been dragged up by the drift, not stayed at 45"
    assert z < ayar.katman2.z_izle, (
        f"the sliding baseline absorbed the drift (median={taban.medyan:.1f}, "
        f"mad={taban.mad:.1f}, z={z:.2f}) — confirms this reference cannot be reused "
        "for the slow path"
    )


# --------------------------------------------------------------------------
# A2 / A3 — the slow path's own hard negatives
# --------------------------------------------------------------------------


def test_a2_yavas_ortam_yukselisi_bulgu_uretmez(baglanti, fikstur, ayar, an):
    modul_id = "TR041-P09-M3"

    def yavas_bozucu(nokta_an, ilerleme_g, ortam, akim, termal, rng):
        gun = ilerleme_g * 15.0
        oran = min(max(gun / 10.0, 0.0), 1.0)
        yeni_ortam = ortam + 8.0 * oran
        return yeni_ortam, akim, termal + (yeni_ortam - ortam)

    uretec = Uretec(fikstur=fikstur, simdi=an, profil=Profil(), tohum=3)
    uretec.uret(modul_id, gecmis_gun=15.0, tespit_saat=7.0, yavas_bozucu=yavas_bozucu)
    fikstur.yaz()

    sonuc = degerlendir(_pencere(baglanti, ayar, modul_id, an), ayar)
    assert sonuc.bulgular == (), f"ambient-following rise must stay silent, got {sonuc.bulgular}"


def test_a3_yavas_asiri_yuk_bulgu_uretmez(baglanti, fikstur, ayar, an):
    modul_id = "TR041-P09-M4"

    def yavas_bozucu(nokta_an, ilerleme_g, ortam, akim, termal, rng):
        gun = ilerleme_g * 15.0
        oran = min(max(gun / 10.0, 0.0), 1.0)
        carpan = 1.0 + 0.4 * oran
        yukselme = max(termal - ortam, 0.0)
        return ortam, akim * carpan, ortam + yukselme * carpan**2

    uretec = Uretec(fikstur=fikstur, simdi=an, profil=Profil(), tohum=4)
    uretec.uret(modul_id, gecmis_gun=15.0, tespit_saat=7.0, yavas_bozucu=yavas_bozucu)
    fikstur.yaz()

    sonuc = degerlendir(_pencere(baglanti, ayar, modul_id, an), ayar)
    assert Tip.AKIM_SICAKLIK_SAPMASI not in sonuc.tipler, (
        "temperature consistent with I^2 must not be reported as a loose terminal"
    )


# --------------------------------------------------------------------------
# A4 — deviation from a module's own normal, alone, is capped at izle (D2)
# --------------------------------------------------------------------------


def _gecmis_basit(fikstur, modul_id, an, *, gun=15.0, taban=45.0, ortam=30.0, yayilim=1.4):
    fikstur.modul(modul_id)
    adim = timedelta(minutes=10)
    zaman = an - timedelta(days=gun)
    i = 0
    while zaman < an - timedelta(hours=7):
        salinim = (i % 11) * yayilim / 10.0
        fikstur.olcum(modul_id, OlcumTipi.TERMAL_MAKS, zaman, taban + salinim, Kalite.IYI, zaman)
        fikstur.olcum(modul_id, OlcumTipi.ORTAM_SICAKLIK, zaman, ortam + salinim, Kalite.IYI, zaman)
        for faz in (OlcumTipi.AKIM_L1, OlcumTipi.AKIM_L2, OlcumTipi.AKIM_L3):
            fikstur.olcum(modul_id, faz, zaman, 300.0 + salinim, Kalite.IYI, zaman)
        zaman += adim
        i += 1


def _tespit_basit(fikstur, modul_id, an, uretici, *, saat=6.0, adim_sn=60):
    zaman = an - timedelta(hours=saat)
    toplam = (an - zaman).total_seconds()
    while zaman <= an:
        ilerleme = (zaman - (an - timedelta(hours=saat))).total_seconds() / toplam if toplam else 1.0
        for olcum_tipi, deger in uretici(ilerleme):
            fikstur.olcum(modul_id, olcum_tipi, zaman, deger, Kalite.IYI, zaman)
        zaman += timedelta(seconds=adim_sn)


def test_a4_kendi_normalinden_sapma_kritik_olmaz(baglanti, fikstur, ayar, an):
    """Module normally 45 C (ambient 30), steps to a steady 55 C for 6h at
    UNCHANGED load with balanced phases — nothing for layer 3 to explain away
    and nothing for layer 1 to cross (55 < termal_izle=70). The only thing
    that could fire is layer 2's own-history deviation, and D2 caps that at
    izle: the level must not read kritik.
    """
    modul_id = "TR041-P09-M5"
    _gecmis_basit(fikstur, modul_id, an, taban=45.0, ortam=30.0)
    _tespit_basit(
        fikstur,
        modul_id,
        an,
        lambda i: [
            (OlcumTipi.TERMAL_MAKS, 55.0 + 0.05 * ((int(i * 97) % 7) - 3)),
            (OlcumTipi.ORTAM_SICAKLIK, 30.0),
            (OlcumTipi.AKIM_L1, 300.0),
            (OlcumTipi.AKIM_L2, 300.0),
            (OlcumTipi.AKIM_L3, 300.0),
        ],
    )
    fikstur.yaz()

    sonuc = degerlendir(_pencere(baglanti, ayar, modul_id, an), ayar)
    seviye = _en_yuksek_seviye(sonuc)
    assert seviye is not Seviye.KRITIK, f"a steady, load-unchanged step must not read kritik, got {seviye}"


# --------------------------------------------------------------------------
# A5 — one terminal, neighbours untouched: kritik via the FIST divergence band
# --------------------------------------------------------------------------


def test_a5_tek_terminal_komsulardan_ayrisinca_kritik(baglanti, fikstur, ayar, an):
    """One terminal rises to ~128 C within 2h while its own frame's quadrants
    (and, by construction, its neighbours) stay put. 128 C alone is only
    `uyari` on layer 1's absolute scale (termal_izle=70, uyari=90, kritik=130)
    — the kritik verdict has to come from the divergence-vs-a-similar-
    component criterion (D2's corrected FIST 4-13 bands, >15 K -> kritik),
    which a ~80 K pixel-vs-frame gap clears easily.
    """
    modul_id = "TR041-P09-M6"
    _gecmis_basit(fikstur, modul_id, an, taban=45.0, ortam=30.0)

    zaman = an - timedelta(hours=2)
    toplam = (an - zaman).total_seconds()
    while zaman <= an:
        ilerleme = (zaman - (an - timedelta(hours=2))).total_seconds() / toplam
        maks = 45.0 + 83.0 * ilerleme  # -> ~128 C
        for olcum_tipi, deger in (
            (OlcumTipi.TERMAL_MAKS, maks),
            (OlcumTipi.ORTAM_SICAKLIK, 30.0),
            (OlcumTipi.AKIM_L1, 300.0),
            (OlcumTipi.AKIM_L2, 300.0),
            (OlcumTipi.AKIM_L3, 300.0),
        ):
            fikstur.olcum(modul_id, olcum_tipi, zaman, deger, Kalite.IYI, zaman)
        fikstur.termal(
            modul_id,
            zaman,
            maks=maks,
            maks_sutun=14,
            maks_satir=9,
            # Quadrants stay at the healthy level: the frame did not move,
            # only this one pixel did.
            bolge_ort=(44.0, 45.5, 44.5, 45.0),
            # kare=False: this test only needs termal_ozet (the quadrant
            # summary layer 3 actually reads); the full 768-pixel frame is
            # not needed and this sandbox's exported track-A schema has an
            # unrelated, pre-existing piksel_verisi column-type mismatch
            # (jsonb vs the contract's bytea — see test_sozlesme.py's own
            # failing test for it) that has nothing to do with this change.
            kare=False,
            alindi_zaman=zaman,
        )
        zaman += timedelta(seconds=60)
    fikstur.yaz()

    sonuc = degerlendir(_pencere(baglanti, ayar, modul_id, an), ayar)
    seviye = _en_yuksek_seviye(sonuc)
    assert seviye is Seviye.KRITIK, f"an ~80 K pixel-vs-frame gap must read kritik, got {seviye}"


# --------------------------------------------------------------------------
# A6 — D3's fix: no ambient channel must SKIP the check, not assume 0 C
# --------------------------------------------------------------------------


def test_a6_ortam_yokken_akim_sicaklik_sapmasi_uretilmez(baglanti, fikstur, ayar, an):
    """Ambient channel entirely absent, current 300 -> 600 A (a pure overload),
    termal_maks 45 -> 75 C tracking I^2 R at the doubled current. Before the
    D3 fix, crediting the missing ambient with 0 C could make this read
    `kritik akim_sicaklik_sapmasi` for a module carrying nothing but its own
    rated overload with no ambient sensor. After the fix, layer 3's
    current-vs-temperature check must not run at all for this module.
    """
    modul_id = "TR041-P09-M7"
    fikstur.modul(modul_id)
    # Baseline stretch: no ambient channel anywhere, ever.
    adim = timedelta(minutes=10)
    zaman = an - timedelta(days=15)
    while zaman < an - timedelta(hours=6):
        fikstur.olcum(modul_id, OlcumTipi.TERMAL_MAKS, zaman, 45.0, Kalite.IYI, zaman)
        for faz in (OlcumTipi.AKIM_L1, OlcumTipi.AKIM_L2, OlcumTipi.AKIM_L3):
            fikstur.olcum(modul_id, faz, zaman, 300.0, Kalite.IYI, zaman)
        zaman += adim

    zaman = an - timedelta(hours=6)
    toplam = (an - zaman).total_seconds()
    while zaman <= an:
        ilerleme = (zaman - (an - timedelta(hours=6))).total_seconds() / toplam
        akim = 300.0 + 300.0 * ilerleme  # 300 -> 600 A
        maks = 45.0 * (akim / 300.0) ** 2  # tracks I^2 exactly: 45 -> 180...
        # clamp to the stated 45 -> 75 C so this stays a modest, physically
        # plausible overload rather than an implausible 4x thermal rise.
        maks = 45.0 + 30.0 * ilerleme
        for olcum_tipi, deger in (
            (OlcumTipi.TERMAL_MAKS, maks),
            (OlcumTipi.AKIM_L1, akim),
            (OlcumTipi.AKIM_L2, akim),
            (OlcumTipi.AKIM_L3, akim),
        ):
            fikstur.olcum(modul_id, olcum_tipi, zaman, deger, Kalite.IYI, zaman)
        zaman += timedelta(seconds=60)
    fikstur.yaz()

    pencere = _pencere(baglanti, ayar, modul_id, an)
    assert pencere.seri(OlcumTipi.ORTAM_SICAKLIK).bos, "the fixture must genuinely have no ambient data"

    sonuc = degerlendir(pencere, ayar)
    assert Tip.AKIM_SICAKLIK_SAPMASI not in sonuc.tipler, (
        "no ambient channel must skip the check, never substitute 0 C"
    )
