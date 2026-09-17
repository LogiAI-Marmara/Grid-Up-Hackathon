"""Decision K1's guarantees: nothing dropped, nothing evaluated twice, restart-safe.

Section 3.6 makes three promises about the scan loop, and they are the promises
the whole design rests on — if any of them is false, the detector silently misses
faults and no amount of good detection logic matters. Each has a test here.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from analiz.depo import ImlecDeposu
from analiz.sozlesme import Kalite, OlcumTipi
from analiz.tarama import Tarayici


def _duz_seri(fikstur, modul_id, an, sayi, aralik_sn=10, deger=45.0):
    """A flat, healthy thermal series ending at `an`."""
    fikstur.modul(modul_id)
    for i in range(sayi):
        zaman = an - timedelta(seconds=aralik_sn * (sayi - 1 - i))
        fikstur.olcum(
            modul_id,
            OlcumTipi.TERMAL_MAKS,
            zaman,
            deger + (i % 3) * 0.1,
            Kalite.IYI,
            zaman,
        )


def test_tek_turda_gelen_hicbir_satir_dusmez(baglanti, fikstur, ayar, an):
    """A module that goes quiet and then delivers a backlog loses nothing.

    Section 3.6's third row: "module silent 5 min, sends 300 rows at once -> all
    300 are taken". This is the case a cursor on measurement time would drop
    entirely, because the backlog carries *old* timestamps and a `zaman` cursor
    has already moved past them. The cursor is on `alindi_zaman` for this reason,
    and this test is what proves it.
    """
    modul_id = "TR041-P01-M1"
    fikstur.modul(modul_id)
    # 300 rows measured across the five silent minutes, all arriving now.
    for i in range(300):
        zaman = an - timedelta(seconds=300 - i)
        fikstur.olcum(modul_id, OlcumTipi.TERMAL_MAKS, zaman, 45.0, Kalite.IYI, an)
    fikstur.yaz()

    tarayici = Tarayici(baglanti, ayar)
    tarayici.imlecler.geri_al(ayar.tarama.imlec_adi, an - timedelta(hours=1))

    sonuc = tarayici.tur(simdi=an + timedelta(seconds=1))

    assert sonuc.satir == 300, "every arrived row must be counted in the turn"
    assert sonuc.modul == 1


def test_bir_turda_modul_basina_tek_degerlendirme(baglanti, fikstur, ayar, an):
    """300 rows for one module is one evaluation, not 300.

    Section 3.6: "one evaluation is done per module per turn; how many rows
    arrived does not change the number of evaluations. Arrived rows are only a
    signal to re-evaluate this module." Without this a backlog would produce a
    burst of identical findings.
    """
    _duz_seri(fikstur, "TR041-P01-M1", an, 300, aralik_sn=1)
    _duz_seri(fikstur, "TR041-P01-M2", an, 50, aralik_sn=1)
    fikstur.yaz()

    tarayici = Tarayici(baglanti, ayar)
    tarayici.imlecler.geri_al(ayar.tarama.imlec_adi, an - timedelta(hours=1))
    sonuc = tarayici.tur(simdi=an + timedelta(seconds=1))

    assert sonuc.modul == 2
    assert len(sonuc.degerlendirmeler) == 2
    modul_idler = [d.modul_id for d in sonuc.degerlendirmeler]
    assert sorted(modul_idler) == ["TR041-P01-M1", "TR041-P01-M2"]
    assert len(set(modul_idler)) == len(modul_idler), "a module must not be evaluated twice"


def test_imlec_yeniden_baslatmadan_sonra_kaldigi_yerden_devam_eder(
    baglanti, fikstur, ayar, an
):
    """A restarted detector resumes, and does not re-read what it already read.

    The cursor lives in the database rather than in memory precisely so this
    holds. The second `Tarayici` here stands in for a restarted process: same
    database, no shared state.
    """
    modul_id = "TR041-P01-M1"
    _duz_seri(fikstur, modul_id, an, 20, aralik_sn=10)
    fikstur.yaz()

    birinci = Tarayici(baglanti, ayar)
    birinci.imlecler.geri_al(ayar.tarama.imlec_adi, an - timedelta(hours=1))
    ilk_sonuc = birinci.tur(simdi=an + timedelta(seconds=1))
    assert ilk_sonuc.satir == 20

    kaydedilen = birinci.imlecler.oku(ayar.tarama.imlec_adi).son_islenen

    # "Restart": a fresh scanner reading the persisted cursor.
    ikinci = Tarayici(baglanti, ayar)
    assert ikinci.imlecler.oku(ayar.tarama.imlec_adi).son_islenen == kaydedilen

    bos_tur = ikinci.tur(simdi=an + timedelta(seconds=2))
    assert bos_tur.satir == 0, "already-processed rows must not be read again"

    # New data arriving after the restart is picked up, and only that data.
    yeni_an = an + timedelta(seconds=30)
    for i in range(5):
        zaman = yeni_an + timedelta(seconds=i)
        fikstur.olcum(modul_id, OlcumTipi.TERMAL_MAKS, zaman, 45.0, Kalite.IYI, zaman)
    fikstur.yaz()

    ucuncu_tur = ikinci.tur(simdi=yeni_an + timedelta(seconds=10))
    assert ucuncu_tur.satir == 5


def test_imlec_geri_alinca_gecmis_yeniden_taranir(baglanti, fikstur, ayar, an):
    """Rewinding the cursor re-scans history — section 3.4's first argument for polling.

    When the algorithm changes, the last N days have to be re-evaluated against
    the new logic. A push design cannot do this at all; here it is one UPDATE.
    """
    modul_id = "TR041-P01-M1"
    _duz_seri(fikstur, modul_id, an, 20, aralik_sn=10)
    fikstur.yaz()

    tarayici = Tarayici(baglanti, ayar)
    tarayici.imlecler.geri_al(ayar.tarama.imlec_adi, an - timedelta(hours=1))
    ilk = tarayici.tur(simdi=an + timedelta(seconds=1))
    assert ilk.satir == 20

    assert tarayici.tur(simdi=an + timedelta(seconds=2)).satir == 0

    tarayici.imlecler.geri_al(ayar.tarama.imlec_adi, an - timedelta(hours=1))
    tekrar = tarayici.tur(simdi=an + timedelta(seconds=3))
    assert tekrar.satir == 20, "a rewound cursor must re-read the same rows"


def test_seyrek_olcum_turlar_arasinda_kaybolmaz(baglanti, fikstur, ayar, an):
    """One measurement every 20 s against a 10 s turn: some turns see nothing, none lose anything.

    Section 3.6's second row. The failure this guards against is an off-by-one in
    the range bounds — `>=` instead of `>` double-counts, `>` on the wrong end
    drops — and it only shows up as a slow leak of missing rows.
    """
    modul_id = "TR041-P01-M1"
    fikstur.modul(modul_id)
    zamanlar = [an + timedelta(seconds=20 * i) for i in range(6)]
    for zaman in zamanlar:
        fikstur.olcum(modul_id, OlcumTipi.TERMAL_MAKS, zaman, 45.0, Kalite.IYI, zaman)
    fikstur.yaz()

    tarayici = Tarayici(baglanti, ayar)
    tarayici.imlecler.geri_al(ayar.tarama.imlec_adi, an - timedelta(seconds=1))

    toplam = 0
    bos_tur = 0
    for i in range(13):  # 13 turns x 10 s covers the whole 100 s span
        sonuc = tarayici.tur(simdi=an + timedelta(seconds=10 * i))
        toplam += sonuc.satir
        if sonuc.satir == 0:
            bos_tur += 1

    assert toplam == len(zamanlar), "no measurement may be lost between turns"
    assert bos_tur > 0, "with this cadence some turns legitimately see nothing"


def test_emniyet_payi_araligi_simdinin_gerisinde_bitirir(baglanti, fikstur, ayar, an):
    """The range stops short of now, so a row still in flight is not stepped over.

    `alindi_zaman` defaults to `now()`, which is *transaction start* time in
    PostgreSQL. A collector transaction that began before this turn and commits
    after it would land behind an advanced cursor and never be seen again.
    """
    gecikmeli = ayar.ile(tarama={"emniyet_payi_sn": 5.0})
    modul_id = "TR041-P01-M1"
    fikstur.modul(modul_id)
    # Arrives 2 s ago — inside the 5 s margin, so this turn must not claim it.
    zaman = an - timedelta(seconds=2)
    fikstur.olcum(modul_id, OlcumTipi.TERMAL_MAKS, zaman, 45.0, Kalite.IYI, zaman)
    fikstur.yaz()

    tarayici = Tarayici(baglanti, gecikmeli)
    tarayici.imlecler.geri_al(gecikmeli.tarama.imlec_adi, an - timedelta(hours=1))

    assert tarayici.tur(simdi=an).satir == 0, "a row inside the safety margin waits"
    # Once the margin has passed, the same row is picked up.
    assert tarayici.tur(simdi=an + timedelta(seconds=10)).satir == 1


def test_imlec_hic_okunmamisken_de_geri_alinabilir(baglanti, fikstur, ayar, an):
    """Rewinding a cursor that does not exist yet must create it, not do nothing.

    Regression test. `geri_al` was a plain UPDATE, which affects no rows before
    the cursor has ever been read — so on a fresh deployment `analiz geri-al`
    reported success, changed nothing, and the next turn created the cursor at
    its cold-start position instead. The history the operator asked to re-scan
    was skipped silently, which is the worst way for a rewind to fail: section
    3.4 makes re-scanning the first argument for polling over push, and an
    operator has no way to tell it did not happen.

    The failure only appears when the cold-start position lands *after* the data,
    which is why the suite missed it: the test configuration's cold start reaches
    thirty days back and covered the rows by accident.
    """
    modul_id = "TR041-P01-M1"
    _duz_seri(fikstur, modul_id, an, 20, aralik_sn=10)
    fikstur.yaz()

    with baglanti.cursor() as imlec:
        imlec.execute("SELECT count(*) AS n FROM gridup.tarama_imleci")
        assert imlec.fetchone()["n"] == 0, "no cursor row exists yet"

    # A cold start that would land well past the fixture data.
    ileri = ayar.ile(tarama={"ilk_imlec_geri_sn": 1.0})
    tarayici = Tarayici(baglanti, ileri)
    tarayici.imlecler.geri_al(ileri.tarama.imlec_adi, an - timedelta(hours=1))

    imlec_durumu = tarayici.imlecler.oku(ileri.tarama.imlec_adi)
    assert imlec_durumu.son_islenen == an - timedelta(hours=1), (
        "the rewind must have created the cursor at the requested position"
    )

    sonuc = tarayici.tur(simdi=an + timedelta(seconds=1))
    assert sonuc.satir == 20, "the rewound history must actually be re-scanned"
