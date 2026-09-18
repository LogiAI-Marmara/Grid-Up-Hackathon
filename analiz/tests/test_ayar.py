"""Configuration is configuration.

The brief for this layer is explicit that the scan period, every window length
and every threshold must be configuration rather than constants buried in logic.
That is not tidiness: a threshold that cannot be moved without editing detector
code cannot be re-tuned after a blind test, cannot be varied across the 10/50/100
module load test, and cannot be defended to a jury asking where the number came
from.

These tests assert the property directly — that changing a value in `ayar.py`
changes what the detector does, and that no threshold is hardcoded past it.
"""

from __future__ import annotations

import ast
import pathlib
from dataclasses import fields
from datetime import timedelta

import pytest

from analiz.ayar import Ayar
from analiz.dedektor import degerlendir
from analiz.pencere import PencereGetirici
from analiz.skor import esikle
from analiz.sozlesme import Kalite, OlcumTipi, Seviye, Tip


def test_bolum_bazinda_degistirme_digerlerine_dokunmaz():
    temel = Ayar()
    degisik = temel.ile(katman1={"termal_kritik": 120.0})

    assert degisik.katman1.termal_kritik == 120.0
    assert degisik.katman1.termal_uyari == temel.katman1.termal_uyari
    assert degisik.tarama.periyot_sn == temel.tarama.periyot_sn
    assert temel.katman1.termal_kritik == 130.0, "Ayar is frozen; the original is untouched"


def test_bilinmeyen_bolum_hata_verir():
    with pytest.raises(KeyError):
        Ayar().ile(katman9={"x": 1})


def test_ortam_degiskeni_tiplere_gore_donusturulur():
    ayar = Ayar.ortamdan(
        {
            "GRIDUP_ANALIZ_TARAMA_PERIYOT_SN": "2.5",
            "GRIDUP_ANALIZ_KATMAN0_DONUK_ARDISIK": "20",
            "GRIDUP_ANALIZ_KATMAN0_SAAT_KAYMASI_SEVIYE": "uyari",
            "GRIDUP_ANALIZ_VERITABANI_DSN": "postgresql:///baska",
        }
    )
    assert ayar.tarama.periyot_sn == 2.5
    assert ayar.katman0.donuk_ardisik == 20
    assert ayar.katman0.saat_kaymasi_seviye is Seviye.UYARI
    assert ayar.veritabani.dsn == "postgresql:///baska"


def test_esik_degistirince_dedektorun_karari_degisir(baglanti, fikstur, an):
    """The end-to-end property: move a threshold, get a different verdict.

    A test that only checked the dataclass would pass even if the layer ignored
    it and used a literal. This one runs the real detector twice over identical
    data with one number changed.
    """
    modul_id = "TR041-P01-M1"
    fikstur.modul(modul_id)
    zaman = an - timedelta(hours=6)
    adim = 0
    while zaman <= an:
        wobble = 0.05 * ((adim % 7) - 3) / 3.0
        fikstur.olcum(modul_id, OlcumTipi.NEM, zaman, 80.0 + wobble, Kalite.IYI, zaman)
        zaman += timedelta(minutes=1)
        adim += 1
    fikstur.yaz()

    from analiz.dogrulama import dogrulama_ayari

    temel = dogrulama_ayari(baglanti.info.dsn or "postgresql:///gridup_analiz_test")

    def seviye_ile(ayar):
        pencere = PencereGetirici(baglanti, ayar).getir({modul_id: an})[modul_id]
        bulgu = degerlendir(pencere, ayar).bulgu(Tip.NEM_YUKSEK)
        return bulgu.seviye if bulgu else None

    # 80% humidity: above the default izle (75), below uyari (85).
    assert seviye_ile(temel) is Seviye.IZLE
    # Raise the thresholds past it and the finding disappears entirely.
    assert seviye_ile(temel.ile(katman1={"nem_izle": 90.0, "nem_uyari": 95.0, "nem_kritik": 99.0})) is None
    # Lower them under it and the same data becomes critical.
    assert seviye_ile(temel.ile(katman1={"nem_izle": 50.0, "nem_uyari": 60.0, "nem_kritik": 70.0})) is Seviye.KRITIK


def test_pencere_uzunlugu_ayardan_gelir(baglanti, fikstur, ayar, an):
    """The detection window is configuration, and the fetcher honours it."""
    modul_id = "TR041-P01-M1"
    fikstur.modul(modul_id)
    zaman = an - timedelta(hours=10)
    while zaman <= an:
        fikstur.olcum(modul_id, OlcumTipi.TERMAL_MAKS, zaman, 45.0, Kalite.IYI, zaman)
        zaman += timedelta(minutes=10)
    fikstur.yaz()

    dar = ayar.ile(pencere={"tespit_sn": 3600.0})
    genis = ayar.ile(pencere={"tespit_sn": 6 * 3600.0})

    dar_seri = PencereGetirici(baglanti, dar).getir({modul_id: an})[modul_id].seri(
        OlcumTipi.TERMAL_MAKS
    )
    genis_seri = PencereGetirici(baglanti, genis).getir({modul_id: an})[modul_id].seri(
        OlcumTipi.TERMAL_MAKS
    )

    assert len(dar_seri) == 6      # one hour at 10-minute spacing
    assert len(genis_seri) == 36   # six hours


def test_taban_penceresi_tespit_penceresinden_belirgin_uzundur():
    """The first half of the poisoning defence, as an invariant.

    Section 5: if the baseline window is not much longer than the detection
    window, a slowly developing fault is absorbed into the baseline as fast as it
    grows and the detector learns it as normal. A configuration that violated
    this would look fine and detect nothing.
    """
    ayar = Ayar()
    assert ayar.pencere.taban_sn >= 10 * ayar.pencere.tespit_sn
    assert ayar.pencere.taban_bosluk_sn > 0, "the baseline must not touch the present"


def test_seviye_esikleri_her_katmanda_artan_sirada():
    """Ascending thresholds, checked for every triple in the configuration.

    `esikle` raises on a non-ascending triple, so a typo that swapped two numbers
    would be an exception at runtime — during a demo — rather than here.
    """
    a = Ayar()
    ucluler = [
        (a.katman1.termal_izle, a.katman1.termal_uyari, a.katman1.termal_kritik),
        (a.katman1.ortam_izle, a.katman1.ortam_uyari, a.katman1.ortam_kritik),
        (a.katman1.nem_izle, a.katman1.nem_uyari, a.katman1.nem_kritik),
        (a.katman1.faz_izle, a.katman1.faz_uyari, a.katman1.faz_kritik),
        (a.katman2.z_izle, a.katman2.z_uyari, a.katman2.z_kritik),
        (a.katman2.egilim_izle, a.katman2.egilim_uyari, a.katman2.egilim_kritik),
        (a.katman3.faz_sapma_izle, a.katman3.faz_sapma_uyari, a.katman3.faz_sapma_kritik),
        (
            a.katman3.piksel_ayrisma_izle,
            a.katman3.piksel_ayrisma_uyari,
            a.katman3.piksel_ayrisma_kritik,
        ),
        (
            a.katman3.modul_ayrisma_izle,
            a.katman3.modul_ayrisma_uyari,
            a.katman3.modul_ayrisma_kritik,
        ),
        (
            a.katman3.aciklanamayan_izle,
            a.katman3.aciklanamayan_uyari,
            a.katman3.aciklanamayan_kritik,
        ),
        (
            a.katman2_yavas.asiri_isinma_izle,
            a.katman2_yavas.asiri_isinma_uyari,
            a.katman2_yavas.asiri_isinma_kritik,
        ),
    ]
    for izle, uyari, kritik in ucluler:
        assert izle <= uyari <= kritik
        esikle(kritik, izle, uyari, kritik)  # must not raise


def test_skor_bantlari_seviye_sirasini_bozmaz():
    """Sorting a queue by score gives the same order as sorting by severity.

    An operator triaging by score must not find an `izle` sitting above a
    `uyari`, or the score becomes something to distrust rather than to sort by.
    """
    ornekler = [
        esikle(v, 70.0, 90.0, 130.0) for v in (0, 50, 70, 80, 89, 90, 110, 129, 130, 200)
    ]
    from analiz.sozlesme import SEVIYE_SIRA

    for (seviye_a, skor_a), (seviye_b, skor_b) in zip(ornekler, ornekler[1:]):
        assert skor_a <= skor_b, "score must be monotonic in the measured value"
        if SEVIYE_SIRA[seviye_a] < SEVIYE_SIRA[seviye_b]:
            assert skor_a <= skor_b


def test_katman_kodunda_ciplak_esik_sabiti_yok():
    """No detector layer carries a bare numeric threshold.

    A guard against the slow failure this whole module exists to prevent:
    somebody adds a rule in a hurry with a literal in it, the value stops being
    visible in `ayar.py`, and from then on the configuration is a partial
    description of what the detector actually does.

    Only the layer modules are checked, and only comparisons — arithmetic
    constants (unit conversions, a squared ratio) are legitimate.
    """
    kok = pathlib.Path(__file__).resolve().parent.parent / "analiz" / "dedektor"
    izinli = {0, 0.0, 1, 1.0, 2, 3, 100.0, 1e-6}
    ihlaller = []

    for yol in sorted(kok.glob("katman*.py")):
        agac = ast.parse(yol.read_text(encoding="utf-8"))
        for dugum in ast.walk(agac):
            if not isinstance(dugum, ast.Compare):
                continue
            for taraf in [dugum.left, *dugum.comparators]:
                if isinstance(taraf, ast.Constant) and isinstance(taraf.value, (int, float)):
                    if taraf.value not in izinli:
                        ihlaller.append(f"{yol.name}:{taraf.lineno}: compares against {taraf.value}")

    assert not ihlaller, "thresholds must live in ayar.py:\n" + "\n".join(ihlaller)
