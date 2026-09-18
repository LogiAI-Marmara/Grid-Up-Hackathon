"""The four layers, each exercised on the thing it alone is responsible for.

Section 5: the layers run in order and none replaces another. These tests check
the division of labour as much as the detection — in particular that layer 0's
veto reaches the later layers, which is the single most important behaviour in
the detector for keeping operator trust.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from analiz.dedektor import degerlendir
from analiz.dedektor.istatistik import egim, mad, medyan, robust_z
from analiz.pencere import PencereGetirici
from analiz.sozlesme import Kalite, OlcumTipi, Seviye, Tip


def _pencere(baglanti, ayar, modul_id, an):
    return PencereGetirici(baglanti, ayar).getir({modul_id: an})[modul_id]


def _gecmis(fikstur, modul_id, an, *, gun=15.0, taban=45.0, ortam=30.0, yayilim=1.4):
    """A fortnight of history, so layer 2 has a baseline to work from.

    `yayilim` is the spread of that history. It matters more than it looks: a
    baseline built from a near-constant value has a MAD near zero, and then
    *every* later reading is many robust deviations out and layer 2 fires at
    everything. Real modules have a daily swing, so a test that wants layer 2
    quiet has to give it one.
    """
    fikstur.modul(modul_id)
    adim = timedelta(minutes=10)
    zaman = an - timedelta(days=gun)
    i = 0
    while zaman < an - timedelta(hours=7):
        salinim = (i % 11) * yayilim / 10.0
        fikstur.olcum(modul_id, OlcumTipi.TERMAL_MAKS, zaman, taban + salinim, Kalite.IYI, zaman)
        fikstur.olcum(modul_id, OlcumTipi.ORTAM_SICAKLIK, zaman, ortam + salinim, Kalite.IYI, zaman)
        zaman += adim
        i += 1


def _tespit(fikstur, modul_id, an, uretici, *, saat=6.0, adim_sn=60, titresim=0.05):
    """Fill the detection window from a callable of (progress) -> [(channel, value, quality)].

    `titresim` adds a small deterministic wobble to every value. It is not
    decoration: layer 0 treats a channel that holds a value to six decimal places
    for hours as a frozen sensor and vetoes it, which is correct behaviour and
    exactly what a test writing a perfectly constant 300.0 A would trip over. Real
    sensors dither; a fixture that does not is testing an impossible input.

    Pass `titresim=0` where the test wants a genuinely frozen channel.
    """
    zaman = an - timedelta(hours=saat)
    toplam = (an - zaman).total_seconds()
    adim = 0
    while zaman <= an:
        ilerleme = (an - timedelta(hours=saat) - zaman).total_seconds() / -toplam if toplam else 1.0
        # A repeating, non-monotonic pattern: enough to look alive, too little to
        # move any threshold, and identical on every run.
        wobble = titresim * ((adim % 7) - 3) / 3.0
        for olcum_tipi, deger, kalite in uretici(ilerleme):
            if deger is not None and olcum_tipi is not OlcumTipi.ARK_OLAY:
                deger = deger + wobble
            fikstur.olcum(modul_id, olcum_tipi, zaman, deger, kalite, zaman)
        zaman += timedelta(seconds=adim_sn)
        adim += 1


# --------------------------------------------------------------------------
# Layer 0
# --------------------------------------------------------------------------


def test_katman0_bozuk_kanal_sicaklik_anomalisi_uretmez(baglanti, fikstur, ayar, an):
    """A failed sensor is `sensor_arizasi`, never a temperature anomaly.

    Section 5: "if this distinction is not made the system raises a fire alarm at
    every broken sensor — and that is the fastest way to destroy an operator's
    trust." The readings here are 150 C, far above every absolute limit and far
    outside the module's own baseline. The *only* thing standing between them and
    a critical hot-spot alarm is `kalite`.
    """
    modul_id = "TR063-P01-M1"
    _gecmis(fikstur, modul_id, an)
    _tespit(
        fikstur,
        modul_id,
        an,
        lambda i: [
            (OlcumTipi.TERMAL_MAKS, 150.0, Kalite.SUPHELI),
            (OlcumTipi.ORTAM_SICAKLIK, 30.0, Kalite.IYI),
        ],
    )
    fikstur.yaz()

    sonuc = degerlendir(_pencere(baglanti, ayar, modul_id, an), ayar)

    assert Tip.SENSOR_ARIZASI in sonuc.tipler
    assert Tip.SICAK_NOKTA not in sonuc.tipler, "a broken sensor is not a hot spot"
    assert OlcumTipi.TERMAL_MAKS in sonuc.kanal_durumu.bozuk
    # The veto is per channel: ambient is still readable.
    assert OlcumTipi.ORTAM_SICAKLIK not in sonuc.kanal_durumu.bozuk


def test_katman0_donuk_sensor_yakalanir(baglanti, fikstur, ayar, an):
    """A frozen sensor: no quality flag admits it, only the physics gives it away.

    78.00 C is above layer 1's `izle` limit and far outside this module's
    baseline, so without the frozen-value test this becomes a temperature anomaly
    — a work order sending a crew to look at a joint that is fine.
    """
    modul_id = "TR063-P01-M2"
    _gecmis(fikstur, modul_id, an)
    # titresim=0: this channel really is stuck, which is the whole scenario.
    _tespit(
        fikstur,
        modul_id,
        an,
        lambda i: [(OlcumTipi.TERMAL_MAKS, 78.0, Kalite.IYI)],
        titresim=0.0,
    )
    # Ambient keeps dithering normally, so only the thermal channel is frozen.
    _tespit(fikstur, modul_id, an, lambda i: [(OlcumTipi.ORTAM_SICAKLIK, 30.0, Kalite.IYI)])
    fikstur.yaz()

    sonuc = degerlendir(_pencere(baglanti, ayar, modul_id, an), ayar)

    assert Tip.SENSOR_ARIZASI in sonuc.tipler
    assert Tip.SICAK_NOKTA not in sonuc.tipler
    bulgu = sonuc.bulgu(Tip.SENSOR_ARIZASI)
    assert "donmuş" in bulgu.gerekce or "değişmedi" in bulgu.gerekce


def test_katman0_ark_sayaci_donuk_sayilmaz(baglanti, fikstur, ayar, an):
    """An arc counter reading 0 for months is not a frozen sensor.

    Holding still is what that channel does. Exempting it is configuration
    (`katman0.donuk_muaf`), not a special case in the logic.
    """
    modul_id = "TR052-P02-M1"
    _gecmis(fikstur, modul_id, an)
    _tespit(
        fikstur,
        modul_id,
        an,
        lambda i: [
            (OlcumTipi.ARK_OLAY, 0.0, Kalite.IYI),
            (OlcumTipi.TERMAL_MAKS, 45.0 + (i * 0.01), Kalite.IYI),
        ],
    )
    fikstur.yaz()

    sonuc = degerlendir(_pencere(baglanti, ayar, modul_id, an), ayar)
    assert Tip.SENSOR_ARIZASI not in sonuc.tipler


# --------------------------------------------------------------------------
# Layer 1
# --------------------------------------------------------------------------


def test_katman1_mutlak_sinir_taban_cizgisinden_bagimsizdir(baglanti, fikstur, ayar, an):
    """135 C is critical even on a module whose whole history runs hot.

    The point of layer 1, from section 5: "whatever the module's normal is, 130 C
    is critical". A module baselined at 120 C has a *high* median, and layer 2
    would find 135 C unremarkable. Layer 1 does not consult the baseline at all.
    """
    modul_id = "TR041-P01-M1"
    # A module that has always run hot, with a realistic spread — so 135 C sits
    # comfortably inside its own normal band and layer 2 has nothing to say.
    _gecmis(fikstur, modul_id, an, taban=120.0, yayilim=16.0)
    _tespit(
        fikstur,
        modul_id,
        an,
        lambda i: [
            (OlcumTipi.TERMAL_MAKS, 135.0, Kalite.IYI),
            (OlcumTipi.ORTAM_SICAKLIK, 30.0, Kalite.IYI),
        ],
    )
    fikstur.yaz()

    sonuc = degerlendir(_pencere(baglanti, ayar, modul_id, an), ayar)

    # Layer 2 is silent: against this module's own history, 135 C is unremarkable.
    assert not [b for b in sonuc.ham_bulgular if b.katman == 2], (
        "the baseline must find this module's own 135 C unsurprising"
    )
    # Layer 1 fires anyway. That is the entire point of having it.
    bulgu = sonuc.bulgu(Tip.SICAK_NOKTA)
    assert bulgu is not None
    assert bulgu.katman == 1
    assert bulgu.seviye is Seviye.KRITIK
    assert "135" in bulgu.gerekce and "130" in bulgu.gerekce


def test_katman1_dusuk_yukte_faz_dengesizligi_bildirmez(baglanti, fikstur, ayar, an):
    """2 A against 1 A is 66% imbalance and means nothing.

    Near no load the percentage is arithmetic noise. Reporting it would be a
    false alarm every night, which is when panels are least loaded.
    """
    modul_id = "TR052-P01-M1"
    _gecmis(fikstur, modul_id, an)
    _tespit(
        fikstur,
        modul_id,
        an,
        lambda i: [
            (OlcumTipi.AKIM_L1, 2.0, Kalite.IYI),
            (OlcumTipi.AKIM_L2, 1.0, Kalite.IYI),
            (OlcumTipi.AKIM_L3, 1.5, Kalite.IYI),
            (OlcumTipi.TERMAL_MAKS, 45.0, Kalite.IYI),
        ],
    )
    fikstur.yaz()

    sonuc = degerlendir(_pencere(baglanti, ayar, modul_id, an), ayar)
    assert Tip.FAZ_DENGESIZLIGI not in sonuc.tipler


# --------------------------------------------------------------------------
# Layer 2
# --------------------------------------------------------------------------


def test_katman2_egilim_mutlak_sinir_asilmadan_uyarir(baglanti, fikstur, ayar, an):
    """D2 (post-review): a warning while every absolute limit is still fine, but
    now from the PRESENT magnitude (capped at izle), with the slope as
    information only — not, as before this decision, a finding the slope
    itself was allowed to create or promote.

    Section 2.3's day-10 row. The value ends at 62 C — below layer 1's `izle`
    limit of 70, so nothing absolute has been crossed and nothing is visibly
    wrong. Old assertion changed (see analiz/README.md's change log and the
    final report): this used to assert a SEPARATE trend-only Bulgu existed and
    that its severity came from the slope; D2 removed that Bulgu entirely, so
    this now asserts the single surviving layer-2 finding is capped at `izle`
    (never higher, however large the underlying z gets) and that its
    `gerekce` still carries the trend as a sentence, not as the reason it fired.
    """
    modul_id = "TR041-P01-M1"
    _gecmis(fikstur, modul_id, an, taban=45.0)
    _tespit(
        fikstur,
        modul_id,
        an,
        lambda i: [
            (OlcumTipi.TERMAL_MAKS, 45.0 + 17.0 * i, Kalite.IYI),
            (OlcumTipi.ORTAM_SICAKLIK, 30.0, Kalite.IYI),
        ],
    )
    fikstur.yaz()

    pencere = _pencere(baglanti, ayar, modul_id, an)
    sonuc = degerlendir(pencere, ayar)

    assert Tip.SICAK_NOKTA in sonuc.tipler
    katman2_bulgulari = [b for b in sonuc.ham_bulgular if b.katman == 2]
    assert katman2_bulgulari, "layer 2 must still fire on this module's own history"
    assert all(b.seviye is Seviye.IZLE for b in katman2_bulgulari), (
        "deviation from a module's OWN normal may never exceed izle (D2)"
    )
    egilim_metinli = [b for b in katman2_bulgulari if "saatte" in b.gerekce]
    assert egilim_metinli, "the rise is steep enough that trend text must still be present"
    # Nothing absolute was crossed: layer 1 stayed silent.
    assert not [b for b in sonuc.ham_bulgular if b.katman == 1]


def test_katman2_soguk_baslangicta_tetiklenmez(baglanti, fikstur, ayar, an):
    """A module installed this morning has no normal yet, so layer 2 declines.

    Inventing a baseline from a handful of readings produces confident nonsense,
    and the first hour after an installation is exactly when nobody wants an
    alarm storm.
    """
    modul_id = "TR041-P01-M1"
    fikstur.modul(modul_id)
    _tespit(
        fikstur,
        modul_id,
        an,
        lambda i: [(OlcumTipi.TERMAL_MAKS, 45.0 + 20.0 * i, Kalite.IYI)],
        saat=0.5,
    )
    fikstur.yaz()

    pencere = _pencere(baglanti, ayar, modul_id, an)
    sonuc = degerlendir(pencere, ayar)
    assert not [b for b in sonuc.ham_bulgular if b.katman == 2]


def test_katman2_taban_cizgisi_acik_olayda_dondurulur(baglanti, fikstur, ayar, an):
    """Baseline poisoning: while an episode is open, the baseline stops moving.

    Section 5's design note, and the failure mode that would make layer 2 quietly
    useless. A sliding baseline absorbs a slow fault — each day's hotter reading
    widens the band the next day is judged against — until the detector has
    learned the fault as normal and goes silent exactly when it should not.
    """
    modul_id = "TR041-P01-M1"
    _gecmis(fikstur, modul_id, an)
    _tespit(
        fikstur,
        modul_id,
        an,
        lambda i: [(OlcumTipi.TERMAL_MAKS, 45.0 + 20.0 * i, Kalite.IYI)],
    )
    fikstur.yaz()

    with baglanti.cursor() as imlec:
        imlec.execute(
            """
            INSERT INTO gridup.anomali
                (sira, id, modul_id, tip, seviye, maks_seviye, skor,
                 ilk_gorulme, son_gorulme, durum, gerekce)
            VALUES (1, 'an_00001', %s, 'sicak_nokta', 'uyari', 'uyari', 0.6,
                    %s, %s, 'acik', 'test')
            """,
            (modul_id, an - timedelta(days=3), an),
        )
    baglanti.commit()

    pencere = _pencere(baglanti, ayar, modul_id, an)
    taban = pencere.taban(OlcumTipi.TERMAL_MAKS)
    assert taban is not None
    assert taban.donduruldu, "an open episode must freeze the channel's baseline"
    assert taban.bit <= an - timedelta(days=3), "frozen at the episode's onset"


# --------------------------------------------------------------------------
# Layer 3
# --------------------------------------------------------------------------


def test_katman3_sabit_akimda_isinma_direnc_artisidir(baglanti, fikstur, ayar, an):
    """Scenario 1: the temperature rises and nothing that could explain it does.

    The decision record's worked example in section 5. What makes it a diagnosis
    rather than an observation is the negative half — the current and the ambient
    both stayed put, so the heat has nowhere to come from except resistance.
    """
    modul_id = "TR041-P01-M1"
    _gecmis(fikstur, modul_id, an)
    _tespit(
        fikstur,
        modul_id,
        an,
        lambda i: [
            (OlcumTipi.TERMAL_MAKS, 45.1 + 27.3 * i, Kalite.IYI),
            (OlcumTipi.ORTAM_SICAKLIK, 31.2 + 0.6 * i, Kalite.IYI),
            (OlcumTipi.AKIM_L1, 310.0 - 2.0 * i, Kalite.IYI),
            (OlcumTipi.AKIM_L2, 308.0 - 2.0 * i, Kalite.IYI),
            (OlcumTipi.AKIM_L3, 309.0 - 2.0 * i, Kalite.IYI),
        ],
    )
    fikstur.yaz()

    sonuc = degerlendir(_pencere(baglanti, ayar, modul_id, an), ayar)
    bulgu = sonuc.bulgu(Tip.AKIM_SICAKLIK_SAPMASI)
    assert bulgu is not None, "current-vs-temperature must fire when current is steady"
    assert bulgu.katman == 3
    # The justification has to carry the numbers, not adjectives.
    assert "310" in bulgu.gerekce and "°C" in bulgu.gerekce


def test_katman3_gercek_asiri_yuk_direnc_artisi_sayilmaz(baglanti, fikstur, ayar, an):
    """When the load really did double, the heat is explained and this test stays quiet.

    The other direction of the same comparison, and the reason it is posed as
    I^2 R rather than as "is the current flat". Sending a crew to tighten a screw
    on a panel that is simply overloaded is a false positive with a van attached.
    """
    modul_id = "TR041-P02-M1"
    _gecmis(fikstur, modul_id, an)
    _tespit(
        fikstur,
        modul_id,
        an,
        lambda i: [
            (OlcumTipi.TERMAL_MAKS, 45.0 + 30.0 * i, Kalite.IYI),
            (OlcumTipi.ORTAM_SICAKLIK, 30.0, Kalite.IYI),
            (OlcumTipi.AKIM_L1, 300.0 * (1.0 + 1.0 * i), Kalite.IYI),
            (OlcumTipi.AKIM_L2, 300.0 * (1.0 + 1.0 * i), Kalite.IYI),
            (OlcumTipi.AKIM_L3, 300.0 * (1.0 + 1.0 * i), Kalite.IYI),
        ],
    )
    fikstur.yaz()

    sonuc = degerlendir(_pencere(baglanti, ayar, modul_id, an), ayar)
    assert Tip.AKIM_SICAKLIK_SAPMASI not in sonuc.tipler


def test_katman3_faz_faz_ayrisan_fazi_isimlendirir(baglanti, fikstur, ayar, an):
    """Phase-to-phase names which phase, which layer 1's percentage cannot."""
    modul_id = "TR052-P01-M1"
    _gecmis(fikstur, modul_id, an)
    _tespit(
        fikstur,
        modul_id,
        an,
        lambda i: [
            (OlcumTipi.AKIM_L1, 300.0, Kalite.IYI),
            (OlcumTipi.AKIM_L2, 302.0, Kalite.IYI),
            (OlcumTipi.AKIM_L3, 200.0, Kalite.IYI),
            (OlcumTipi.AKIM_NOTR, 95.0, Kalite.IYI),
            (OlcumTipi.TERMAL_MAKS, 45.0, Kalite.IYI),
        ],
    )
    fikstur.yaz()

    sonuc = degerlendir(_pencere(baglanti, ayar, modul_id, an), ayar)
    bulgu = sonuc.bulgu(Tip.FAZ_DENGESIZLIGI)
    assert bulgu is not None
    katman3 = [b for b in sonuc.ham_bulgular if b.tip is Tip.FAZ_DENGESIZLIGI and b.katman == 3]
    assert katman3, "the phase-to-phase comparison must fire"
    assert "L3" in katman3[0].gerekce


# --------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------


def test_medyan_ve_mad_tek_uc_degerden_bozulmaz(baglanti):
    """The property section 2.2 buys robust statistics for."""
    normal = [45.0, 46.0, 45.5, 46.2, 45.8]
    bozuk = normal + [500.0]

    assert medyan(bozuk) == pytest.approx(45.9, abs=0.2)
    assert mad(bozuk) == pytest.approx(mad(normal), abs=0.4)
    # The mean, for contrast, is destroyed by the same sample.
    assert sum(bozuk) / len(bozuk) > 120


def test_sql_medyani_python_medyani_ile_ayni(baglanti, fikstur, ayar, an):
    """`percentile_cont(0.5)` and `istatistik.medyan` must agree.

    The baseline is computed in SQL for volume reasons (a fortnight of one
    channel is ~120k rows and the statistics are not the expensive part, the
    transfer is). That leaves two implementations of one definition, so this test
    pins them together — otherwise they drift and the layer 2 thresholds quietly
    stop meaning what the unit tests say they mean.
    """
    modul_id = "TR041-P01-M1"
    fikstur.modul(modul_id)
    degerler = [40.0, 41.5, 39.0, 44.25, 42.0, 43.5, 41.0, 40.5]
    zaman = an - timedelta(days=10)
    for i, deger in enumerate(degerler):
        fikstur.olcum(
            modul_id,
            OlcumTipi.TERMAL_MAKS,
            zaman + timedelta(minutes=10 * i),
            deger,
            Kalite.IYI,
            zaman + timedelta(minutes=10 * i),
        )
    fikstur.yaz()

    taban = _pencere(baglanti, ayar, modul_id, an).taban(OlcumTipi.TERMAL_MAKS)
    assert taban is not None
    assert taban.ornek == len(degerler)
    assert taban.medyan == pytest.approx(medyan(degerler), abs=1e-9)
    assert taban.mad == pytest.approx(mad(degerler), abs=1e-9)


def test_egim_bozuk_girdide_patlamaz():
    """A channel with one sample has no trend; that is normal, not an error."""
    assert egim([], []) == 0.0
    assert egim([1.0], [2.0]) == 0.0
    assert egim([1.0, 1.0], [2.0, 3.0]) == 0.0
    assert egim([0.0, 1.0, 2.0], [10.0, 12.0, 14.0]) == pytest.approx(2.0)


def test_robust_z_sifir_mad_ile_patlamaz():
    """A channel that never moved has MAD 0; the floor keeps it finite."""
    assert robust_z(50.0, 45.0, 0.0, 0.3) == pytest.approx(0.6745 * 5.0 / 0.3)
    assert robust_z(45.0, 45.0, 0.0, 0.3) == 0.0


def test_kanal_sagligi_aralik_disi_az_ornekle():
    """D3 fix: the physical-range check must catch an impossible value even
    with fewer samples than `asgari_ornek` — it used to run AFTER that
    early-return and so waved a two-sample channel through as merely
    "unjudged". Pure in-memory `Seri`/`Nokta`, per the reviewer's own note:
    the shared DB CHECK constraint already rejects an out-of-range value at
    the PostgreSQL layer, so this can only be exercised as a unit test.
    """
    from datetime import datetime, timezone

    from analiz.ayar import Ayar
    from analiz.dedektor.katman0_sensor import calistir
    from analiz.pencere import Nokta, Pencere, Seri
    from analiz.sozlesme import OLCUM_ARALIK

    ayar = Ayar()
    assert ayar.katman0.asgari_ornek > 2, "the test needs fewer samples than the minimum"

    alt, ust = OLCUM_ARALIK[OlcumTipi.TERMAL_MAKS]
    zaman0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    imkansiz = ust + 1000.0  # far outside the physical range, on purpose

    noktalar = (
        Nokta(zaman0, 40.0, Kalite.IYI, zaman0),
        Nokta(zaman0 + timedelta(seconds=30), imkansiz, Kalite.IYI, zaman0 + timedelta(seconds=30)),
    )
    seri = Seri(OlcumTipi.TERMAL_MAKS, noktalar)
    assert len(seri.noktalar) < ayar.katman0.asgari_ornek

    pencere = Pencere(
        modul_id="TEST",
        saha_kodu="TEST",
        pano_kodu="TEST",
        simdi=noktalar[-1].zaman,
        tespit_bas=zaman0,
        tespit_bit=noktalar[-1].zaman,
        seriler={OlcumTipi.TERMAL_MAKS: seri},
    )

    bulgular, durum = calistir(pencere, ayar)
    tipler_ve_kanallar = [(b.tip, b.kanal) for b in bulgular]
    assert (Tip.SENSOR_ARIZASI, OlcumTipi.TERMAL_MAKS) in tipler_ve_kanallar, (
        "an out-of-range value must be caught even with too few samples for the "
        "other, statistical tests"
    )
    assert OlcumTipi.TERMAL_MAKS in durum.bozuk
