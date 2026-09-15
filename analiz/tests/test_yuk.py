"""T5 — the load test's own correctness.

A load test that measures the wrong thing is worse than none: it produces
numbers, and numbers get quoted. These check the arithmetic and the two mistakes
that made the first version of this harness report nonsense — counting an empty
turn as the cost of running the fleet, and losing rows from the count.

The measurement run itself is not exercised here. Building a hundred modules'
history takes minutes and belongs in `python -m analiz.yuk`, not in a suite that
has to stay fast enough to run on every change.
"""

from __future__ import annotations

import io

import pytest

from analiz.yuk import (
    SorguKaydi,
    TurOlcumu,
    YukSonucu,
    _etiketle,
    _modul_idleri,
    sinir_tahmini,
    yazdir,
)


def _sonuc(modul, sureler, periyot=10.0, satir=600):
    return YukSonucu(
        modul_sayisi=modul,
        turlar=tuple(TurOlcumu(sure_sn=s, satir=satir, modul=modul) for s in sureler),
        periyot_sn=periyot,
        cpu_sn=sum(sureler) * 0.7,
        bellek_mb=150.0,
        bellek_artis_mb=5.0,
        veri_satiri=modul * 30_000,
        kurulum_sn=1.0,
        sorgular={"taban çizgisi (medyan+MAD)": {"cagri": 10, "toplam_ms": 100.0, "ort_ms": 10.0, "azami_ms": 20.0}},
    )


def test_modul_idleri_sahalara_yayilir():
    """Modules spread over sites, because layer 3 compares a module with its site-mates.

    Piling a hundred modules into one site would make that comparison either
    trivially small or pathologically large, and the load test would be measuring
    a topology nobody deploys.
    """
    idler = _modul_idleri(100)
    assert len(idler) == 100
    assert len(set(idler)) == 100
    sahalar = {i.split("-")[0] for i in idler}
    assert len(sahalar) > 5, "modules must span several sites"
    assert all(len(i.split("-")) == 3 for i in idler)


def test_doluluk_tarama_periyoduna_gore_olculur():
    """Duty is p95 turn duration over the scan period; at 1.0 the detector falls behind."""
    hizli = _sonuc(10, [1.0] * 10)
    assert hizli.doluluk == pytest.approx(0.1)
    assert hizli.yetisiyor

    yavas = _sonuc(100, [12.0] * 10)
    assert yavas.doluluk == pytest.approx(1.2)
    assert not yavas.yetisiyor


def test_doluluk_ortalamayi_degil_p95i_kullanir():
    """A detector that overruns one turn in ten is falling behind one turn in ten.

    The lag from those turns accumulates instead of averaging out, so a mean that
    fits inside the period is not evidence of keeping up.
    """
    # Nine fast turns and one slow one: mean is comfortable, p95 is not.
    sonuc = _sonuc(50, [2.0] * 9 + [40.0])
    assert sonuc.ort_sure < 10.0
    assert sonuc.p95_sure == 40.0
    assert not sonuc.yetisiyor, "the p95 overrun must decide the verdict"


def test_sinir_olculdugunde_tahmin_diye_sunulmaz():
    """When a measured point crosses the period, say measured — not estimated."""
    sonuclar = [_sonuc(10, [1.0] * 5), _sonuc(50, [5.0] * 5), _sonuc(100, [14.0] * 5)]
    metin = sinir_tahmini(sonuclar)
    assert "ÖLÇÜLDÜ" in metin
    assert "100 modülde" in metin


def test_sinira_ulasilmadiginda_tahmin_oldugu_soylenir():
    """An extrapolation is labelled as one rather than quoted as a measurement."""
    sonuclar = [_sonuc(10, [0.5] * 5), _sonuc(50, [2.0] * 5), _sonuc(100, [4.0] * 5)]
    metin = sinir_tahmini(sonuclar)
    assert "ULAŞILMADI" in metin
    assert "tahmin" in metin


def test_sorgu_etiketleri_gercek_ifadeleri_ayirir():
    """Query timings are grouped by what the statement does, not by its text."""
    assert "taban" in _etiketle(
        "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY deger) FROM gridup.olcum"
    )
    assert _etiketle("INSERT INTO gridup.anomali_gecis (anomali_id) VALUES (1)") == (
        "olay: journal yazımı"
    )
    assert _etiketle("SELECT 1") == "diğer"


def test_sorgu_kaydi_yalnizca_acikken_toplar():
    """Timing is off during setup and the warm-up turn.

    Building the fleet issues far more statements than a turn does, and folding
    those into the per-turn figures would report the fixture generator's cost as
    the detector's.
    """
    kayit = SorguKaydi()
    kayit.ekle("a", 1.0)
    assert not kayit.sureler

    kayit.acik = True
    kayit.ekle("a", 0.5)
    kayit.ekle("a", 1.5)
    ozet = kayit.ozet()
    assert ozet["a"]["cagri"] == 2
    assert ozet["a"]["ort_ms"] == pytest.approx(1000.0)
    assert ozet["a"]["azami_ms"] == pytest.approx(1500.0)


def test_bos_tur_flotu_calistirmanin_maliyeti_degildir():
    """A turn that processed nothing is not evidence the fleet is cheap.

    The harness generates data past the measurement window so every measured turn
    has arrivals; the first version did not, the warm-up drained the table, and
    every measured turn afterwards timed the empty case at ~1 ms and reported it
    as the cost of running a hundred modules.
    """
    bos = _sonuc(100, [0.001] * 10, satir=0)
    assert bos.ort_satir == 0
    # The figure is honest on its own terms, so the guard is that the report
    # shows the row count alongside the duration and cannot hide a zero.
    akis = io.StringIO()
    yazdir([bos], akis)
    cikti = akis.getvalue()
    assert "satır/tur" in cikti
    assert " 0 " in cikti


def test_rapor_bolum_8in_istedigi_her_seyi_yazdirir():
    """Section 8 fixes the list: duration, rows, CPU, memory, query times, limit."""
    akis = io.StringIO()
    yazdir([_sonuc(10, [1.0] * 5), _sonuc(100, [9.0] * 5)], akis)
    cikti = akis.getvalue()

    for baslik in ("modül", "veri satırı", "tur ort", "satır/tur", "CPU/tur", "bellek", "doluluk"):
        assert baslik in cikti, f"missing column: {baslik}"
    assert "VERİTABANI SORGU SÜRELERİ" in cikti
    assert "ÖLÇEK SINIRI" in cikti
