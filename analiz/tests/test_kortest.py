"""The label format and the four metrics.

Most of these run on synthetic episodes rather than on a scan: the arithmetic of
the four metrics is what is under test, and it is easier to be sure a lead time
is right when the two timestamps going into it are written three lines above the
assertion. One end-to-end test runs the whole protocol — fixtures, replayed
scan, freeze, open the key, score — because the arithmetic being right and the
pipeline being wired up are different claims.
"""

from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone

import pytest

from analiz import etiket as E
from analiz.kortest import Olay, dondur, rapor, yazdir, yukle
from analiz.senaryolar import etiket_uret
from analiz.sozlesme import Tip

AN = datetime(2026, 9, 15, 9, 40, tzinfo=timezone.utc)


def _senaryo(modul_id, senaryo, baslangic_saat=-7.0, kritik_saat=0.0, **kw):
    return E.EtiketSenaryosu(
        senaryo_id=kw.pop("senaryo_id", f"s_{modul_id}"),
        modul_id=modul_id,
        senaryo=senaryo,
        baslangic=AN + timedelta(hours=baslangic_saat),
        kritik_esik=None if kritik_saat is None else AN + timedelta(hours=kritik_saat),
        **kw,
    )


def _etiket(senaryolar, temiz=("TR099-P01-M1",), gun=15.0):
    return E.EtiketDosyasi(
        surum=E.SURUM,
        senaryolar=tuple(senaryolar),
        temiz_moduller=tuple(temiz),
        kapsam_bas=AN - timedelta(days=gun),
        kapsam_bit=AN,
    )


def _olay(modul_id, tip, saat, olay_id="an_1", seviye="uyari"):
    an = AN + timedelta(hours=saat)
    return Olay(
        id=olay_id,
        modul_id=modul_id,
        tip=tip,
        seviye=seviye,
        skor=0.7,
        ilk_gorulme=an,
        son_gorulme=an,
        durum="acik",
        gerekce="test",
    )


# --------------------------------------------------------------------------
# Label format
# --------------------------------------------------------------------------


def test_etiket_gidip_gelir(tmp_path):
    dosya = _etiket([_senaryo("TR041-P01-M1", "gevsek_klemens")])
    yol = E.yaz(dosya, tmp_path / "e.json")
    geri = E.oku(yol)

    assert len(geri.senaryolar) == 1
    s = geri.senaryolar[0]
    assert s.modul_id == "TR041-P01-M1"
    assert s.senaryo == "gevsek_klemens"
    assert s.baslangic == AN - timedelta(hours=7)
    assert s.kritik_esik == AN
    assert geri.temiz_moduller == ("TR099-P01-M1",)
    assert geri.gozlem_gunu == pytest.approx(15.0)


def test_fikstur_seti_gecerli_etiket_uretir(tmp_path):
    """The set emits the same format track A's blind sets will, so one drops in."""
    yol = E.yaz(etiket_uret(AN), tmp_path / "e.json")
    geri = E.oku(yol)

    assert len(geri.senaryolar) == 9
    assert len(geri.temiz_moduller) == 13
    assert {s.senaryo for s in geri.senaryolar} <= set(E.SENARYO_ADLARI)
    # Every scenario's accepted-tip set is non-empty, or it could never be detected.
    for s in geri.senaryolar:
        assert s.kabul_edilen_tipler


@pytest.mark.parametrize(
    "bozma, beklenen",
    [
        ({"surum": 99}, "surum"),
        ({"senaryolar": "hayir"}, "senaryolar"),
        ({"temiz_moduller": None}, "temiz_moduller"),
    ],
)
def test_bozuk_etiket_sessizce_gecilmez(tmp_path, bozma, beklenen):
    """A malformed label file is an error, never a partial parse.

    A file that half-parses yields a detection rate computed over whatever
    survived parsing. That looks like a result and is not one — and it is wrong
    in the flattering direction, which is the one an evaluation tool must never
    be wrong in.
    """
    yol = tmp_path / "e.json"
    E.yaz(_etiket([_senaryo("TR041-P01-M1", "gevsek_klemens")]), yol)
    govde = json.loads(yol.read_text())
    govde.update(bozma)
    yol.write_text(json.dumps(govde))

    with pytest.raises(E.EtiketHatasi) as hata:
        E.oku(yol)
    assert beklenen in str(hata.value)


def test_etiket_tutarsizliklari_reddedilir(tmp_path):
    yol = tmp_path / "e.json"

    # A scenario name outside the seven of section 7.6.
    E.yaz(_etiket([_senaryo("TR041-P01-M1", "gevsek_klemens")]), yol)
    govde = json.loads(yol.read_text())
    govde["senaryolar"][0]["senaryo"] = "uydurma_ariza"
    yol.write_text(json.dumps(govde))
    with pytest.raises(E.EtiketHatasi, match="unknown senaryo"):
        E.oku(yol)

    # Critical before onset.
    govde["senaryolar"][0]["senaryo"] = "gevsek_klemens"
    govde["senaryolar"][0]["kritik_esik"] = "2026-09-01T00:00:00Z"
    yol.write_text(json.dumps(govde))
    with pytest.raises(E.EtiketHatasi, match="precedes baslangic"):
        E.oku(yol)

    # A naive timestamp is refused rather than assumed to be UTC: an unstated
    # timezone shifts every lead time by the offset, silently and by hours.
    govde["senaryolar"][0]["kritik_esik"] = "2026-09-15T09:40:00"
    yol.write_text(json.dumps(govde))
    with pytest.raises(E.EtiketHatasi, match="no timezone"):
        E.oku(yol)

    # A module cannot be both clean and injected.
    govde["senaryolar"][0]["kritik_esik"] = "2026-09-15T09:40:00Z"
    govde["temiz_moduller"] = ["TR041-P01-M1"]
    yol.write_text(json.dumps(govde))
    with pytest.raises(E.EtiketHatasi, match="clean and as carrying"):
        E.oku(yol)


# --------------------------------------------------------------------------
# Metric 1 — detection
# --------------------------------------------------------------------------


def test_tespit_kabul_edilen_tip_kumesine_bakar(tmp_path):
    """A loose terminal counts as detected under either name it can surface as.

    Track A knows it injected a loose terminal; whether that comes out as
    `akim_sicaklik_sapmasi` or `sicak_nokta` is track B's business and both are
    correct. Pinning one would measure naming, not detection.
    """
    etiket = _etiket([_senaryo("M1", "gevsek_klemens")])

    for tip in (Tip.AKIM_SICAKLIK_SAPMASI, Tip.SICAK_NOKTA):
        r = rapor(etiket, [_olay("M1", tip, -3)])
        assert r.tespit_orani == 1.0, f"{tip.value} must count"

    # A humidity episode does not detect a loose terminal.
    r = rapor(etiket, [_olay("M1", Tip.NEM_YUKSEK, -3)])
    assert r.tespit_orani == 0.0
    assert r.sonuclar[0].yabanci_tipler == frozenset({Tip.NEM_YUKSEK})


def test_beklenen_tip_kumesi_etiketten_gecilebilir():
    """A label may pin one classification when the set is testing exactly that."""
    etiket = _etiket(
        [_senaryo("M1", "gevsek_klemens", beklenen_tip=frozenset({Tip.AKIM_SICAKLIK_SAPMASI}))]
    )
    assert rapor(etiket, [_olay("M1", Tip.SICAK_NOKTA, -3)]).tespit_orani == 0.0
    assert rapor(etiket, [_olay("M1", Tip.AKIM_SICAKLIK_SAPMASI, -3)]).tespit_orani == 1.0


# --------------------------------------------------------------------------
# Metric 2 — lead time
# --------------------------------------------------------------------------


def test_kazanilan_sure_kritik_ana_gore_olculur():
    """Lead time is critical-moment minus first matching detection.

    The project's actual product, per section 2.5: not "we detected an anomaly"
    but "we gave six hours' warning".
    """
    etiket = _etiket([_senaryo("M1", "gevsek_klemens", kritik_saat=0.0)])
    r = rapor(etiket, [_olay("M1", Tip.SICAK_NOKTA, -6.0)])
    assert r.sonuclar[0].kazanilan_sure_sn == pytest.approx(6 * 3600)
    assert r.medyan_kazanilan_saat == pytest.approx(6.0)


def test_kazanilan_sure_en_erken_eslesen_olayi_kullanir():
    """Earliest matching episode by measurement time, not by episode id.

    The id is the order the detector happened to write rows in; the claim is
    about when we could first have told someone, which is a measurement time.
    """
    etiket = _etiket([_senaryo("M1", "gevsek_klemens", kritik_saat=0.0)])
    r = rapor(
        etiket,
        [
            _olay("M1", Tip.AKIM_SICAKLIK_SAPMASI, -2.0, olay_id="an_9"),
            _olay("M1", Tip.SICAK_NOKTA, -5.0, olay_id="an_2"),
        ],
    )
    assert r.sonuclar[0].ilk_eslesen.id == "an_2"
    assert r.sonuclar[0].kazanilan_sure_sn == pytest.approx(5 * 3600)


def test_gec_kalan_tespit_negatif_kazanilan_sure_verir():
    """Detecting after the fault went critical is a detection, not a warning.

    The sign carries that distinction. An absolute value would let a detector
    that is consistently an hour late look identical to one an hour early.
    """
    etiket = _etiket([_senaryo("M1", "ark_olayi", kritik_saat=-2.0)])
    r = rapor(etiket, [_olay("M1", Tip.ARK, -1.0)])
    assert r.sonuclar[0].kazanilan_sure_sn == pytest.approx(-3600)
    assert r.medyan_kazanilan_saat == pytest.approx(-1.0)


def test_kritik_esigi_olmayan_senaryo_ortalamayi_bozmaz():
    """A scenario with no critical moment has no lead time, and is not a zero.

    A frozen sensor does not escalate. Averaging in a zero for it would drag the
    median towards nothing and understate the warning the other scenarios gave.
    """
    etiket = _etiket(
        [
            _senaryo("M1", "gevsek_klemens", kritik_saat=0.0),
            _senaryo("M2", "sensor_arizasi", kritik_saat=None),
        ]
    )
    r = rapor(
        etiket,
        [_olay("M1", Tip.SICAK_NOKTA, -6.0), _olay("M2", Tip.SENSOR_ARIZASI, -6.0)],
    )
    assert len(r.kazanilan_sureler) == 1
    assert r.medyan_kazanilan_saat == pytest.approx(6.0)


def test_kacirilan_senaryonun_kazanilan_suresi_yoktur():
    etiket = _etiket([_senaryo("M1", "gevsek_klemens", kritik_saat=0.0)])
    r = rapor(etiket, [])
    assert r.sonuclar[0].kazanilan_sure_sn is None
    assert r.medyan_kazanilan_saat is None
    assert r.tespit_orani == 0.0


# --------------------------------------------------------------------------
# Metric 3 — false alarms
# --------------------------------------------------------------------------


def test_yanlis_alarm_modul_gun_basina_sayilir():
    etiket = _etiket(
        [_senaryo("M1", "gevsek_klemens")], temiz=("T1", "T2", "T3", "T4"), gun=10.0
    )
    r = rapor(
        etiket,
        [
            _olay("M1", Tip.SICAK_NOKTA, -3),
            _olay("T1", Tip.SICAK_NOKTA, -3, olay_id="an_2"),
            _olay("T3", Tip.NEM_YUKSEK, -2, olay_id="an_3"),
        ],
    )
    assert r.modul_gun == pytest.approx(40.0)
    assert r.yanlis_alarm_orani == pytest.approx(2 / 40.0)
    assert not r.basarili


def test_arizali_moduldeki_ikinci_belirti_yanlis_alarm_degildir():
    """An extra episode on a genuinely faulty module is a second true symptom.

    Overload heats the cabinet as well as the busbar, so `ortam_sicaklik_yuksek`
    beside `sicak_nokta` is the physics being right. Counting it against the
    false-alarm rate would penalise the detector for being thorough — section
    4.4 measures false alarms on the clean modules, and only there.
    """
    etiket = _etiket([_senaryo("M1", "gevsek_klemens")], temiz=("T1",))
    r = rapor(
        etiket,
        [
            _olay("M1", Tip.SICAK_NOKTA, -3),
            _olay("M1", Tip.NEM_YUKSEK, -2, olay_id="an_2"),
        ],
    )
    assert r.yanlis_alarm_orani == 0.0
    assert r.sonuclar[0].yabanci_tipler == frozenset({Tip.NEM_YUKSEK})


def test_temiz_modulu_olmayan_set_oran_veremez():
    """Without clean modules the false-alarm rate is undefined, not perfect.

    Section 4.4's first trap. A set where every module is faulty is passed
    flawlessly by a detector that alarms on everything, and reporting 0.000 for
    it would dress that up as a result.
    """
    etiket = _etiket([_senaryo("M1", "gevsek_klemens")], temiz=())
    r = rapor(etiket, [_olay("M1", Tip.SICAK_NOKTA, -3)])
    assert r.modul_gun == 0
    assert r.yanlis_alarm_orani is None


# --------------------------------------------------------------------------
# Metric 4 — sensor separation
# --------------------------------------------------------------------------


def test_sensor_ayrimi_kirlenmeyi_yakalar():
    """A grid-fault episode on a broken-sensor module is the miscount layer 0 prevents."""
    etiket = _etiket([_senaryo("M1", "sensor_arizasi", kritik_saat=None)], temiz=("T1",))

    temiz_rapor = rapor(etiket, [_olay("M1", Tip.SENSOR_ARIZASI, -3)])
    assert temiz_rapor.ayrim_orani == 1.0
    assert not temiz_rapor.kirlenen_senaryolar

    kirli = rapor(
        etiket,
        [
            _olay("M1", Tip.SENSOR_ARIZASI, -3),
            _olay("M1", Tip.SICAK_NOKTA, -3, olay_id="an_2"),
        ],
    )
    assert kirli.ayrim_orani == 0.0
    assert kirli.kirlenen_senaryolar
    assert kirli.kirlenen_senaryolar[0].sebeke_kirlenmesi == frozenset({Tip.SICAK_NOKTA})
    assert not kirli.basarili


def test_modul_saglik_da_sistem_senaryosudur():
    """Scenarios 6 and 7 are both the system reporting on itself, not on the grid."""
    etiket = _etiket(
        [
            _senaryo("M1", "sensor_arizasi", kritik_saat=None),
            _senaryo("M2", "modul_saglik", kritik_saat=None),
        ],
        temiz=("T1",),
    )
    r = rapor(
        etiket,
        [_olay("M1", Tip.SENSOR_ARIZASI, -3), _olay("M2", Tip.MODUL_SAGLIK, -3, olay_id="an_2")],
    )
    assert len(r.sistem_senaryolari) == 2
    assert r.ayrim_orani == 1.0


# --------------------------------------------------------------------------
# Freeze / load, and the whole protocol
# --------------------------------------------------------------------------


def test_dondurma_ve_yukleme_olaylari_korur(kortest_vt, tmp_path):
    """Freezing writes what the detector said; loading reads back the same thing."""
    baglanti, _, _ = kortest_vt
    yol = tmp_path / "cikti.json"
    govde = dondur(baglanti, yol, kaynak="test")

    assert govde["olay_sayisi"] > 0
    assert govde["dondurma_zamani"].endswith("Z")

    olaylar, bilgi = yukle(yol)
    assert len(olaylar) == govde["olay_sayisi"]
    assert bilgi["kaynak"] == "test"
    assert all(isinstance(o.tip, Tip) for o in olaylar)
    assert all(o.ilk_gorulme.tzinfo is not None for o in olaylar)


def test_bozuk_cikti_dosyasi_reddedilir(tmp_path):
    yol = tmp_path / "c.json"
    yol.write_text('{"baska": []}')
    with pytest.raises(E.EtiketHatasi, match="olaylar"):
        yukle(yol)


def test_protokol_uctan_uca_dort_metrigi_verir(kortest_vt, tmp_path):
    """The whole of section 4.4: fixtures, replayed scan, freeze, open key, score.

    The replay is what makes lead time mean anything — without it every episode
    opens at the last measurement and the metric reads zero for everything.
    """
    baglanti, etiket, _ = kortest_vt
    yol = tmp_path / "cikti.json"
    dondur(baglanti, yol)
    olaylar, bilgi = yukle(yol)

    r = rapor(etiket, olaylar, bilgi)

    assert r.tespit_orani == 1.0, "every injected scenario must be found"
    assert r.yanlis_alarm_orani == 0.0, "no episode on a clean module"
    assert r.ayrim_orani == 1.0, "no sensor failure reported as a grid fault"

    # Lead time is a real, positive number for the progressive faults — which is
    # the claim the whole project rests on.
    assert r.medyan_kazanilan_saat is not None
    assert r.medyan_kazanilan_saat > 1.0, (
        f"median lead time {r.medyan_kazanilan_saat} is too small to be an early warning"
    )

    gevsek = next(s for s in r.sonuclar if s.senaryo.senaryo == "gevsek_klemens")
    assert gevsek.kazanilan_sure_sn > 3600, "the loose terminal must be caught hours early"

    # The arc gives no warning by nature — it is instantaneous, and the metric
    # says so rather than pretending otherwise.
    ark = next(s for s in r.sonuclar if s.senaryo.senaryo == "ark_olayi")
    assert ark.tespit
    assert ark.kazanilan_sure_sn <= 0

    assert r.basarili


def test_rapor_dort_metrigi_de_yazdirir(kortest_vt, tmp_path):
    """All four are printed together, always.

    Any one of them alone is misleading: alarm at everything and the detection
    rate is perfect; never fire and the false-alarm rate is. Section 4.4 requires
    the four to be reported together, so the printer cannot omit one.
    """
    baglanti, etiket, _ = kortest_vt
    yol = tmp_path / "c.json"
    dondur(baglanti, yol)
    olaylar, _ = yukle(yol)

    akis = io.StringIO()
    yazdir(rapor(etiket, olaylar), akis)
    cikti = akis.getvalue()

    assert "tespit oranı" in cikti
    assert "kazanılan süre" in cikti
    assert "yanlış alarm" in cikti
    assert "sensör arızası ayrımı" in cikti
    assert "DÖRT METRİK" in cikti
