"""Blind-test support: partial injection and the label file.

Track B's `analiz/README.md` ("Etiket dosyası formatı") is the spec. The label
file is what turns a run into a blind set: which modules were injected, when the
fault became critical (lead time is measured from it), and which modules were
left clean (the false-alarm denominator). These tests hold the generator to that
spec without importing track B's code, so they run on a checkout of this folder
alone; the vocabulary below is copied from the spec verbatim.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

import pytest

from modul_sim import Filo, KosuAyar
from modul_sim.__main__ import main
from modul_sim.senaryo import SENARYOLAR
from modul_sim.sozlesme import zaman_oku

BASLANGIC = datetime(2026, 9, 14, 6, 0, 0, tzinfo=timezone.utc)

#: Section 7.6's seven, as track B's label parser spells them.
ETIKET_SOZLUGU = {
    "gevsek_klemens",
    "asiri_yuk",
    "faz_dengesizligi",
    "nem_yukselmesi",
    "ark_olayi",
    "sensor_arizasi",
    "modul_saglik",
}

ZAMAN_BICIMI = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _ayar(**ek) -> KosuAyar:
    return KosuAyar(**{"modul_sayisi": 6, "sure_dk": 10, "tohum": 11, "baslangic": BASLANGIC, **ek})


def test_her_senaryonun_etiket_adi_sozlukte():
    """The CLI names differ from the label names for four scenarios; every one
    must map onto the spec's vocabulary, or the label file is rejected."""
    assert {s.etiket_adi for s in SENARYOLAR.values()} == ETIKET_SOZLUGU


def test_varsayilan_hala_tum_modullere_uygular():
    filo = Filo(_ayar(senaryo_ad="gevsek_klemens"))
    assert len(filo.senaryo_moduller) == 6
    assert filo.temiz_moduller == ()


def test_senaryo_modul_listesi_kalanlari_temiz_birakir():
    filo = Filo(_ayar(senaryo_ad="gevsek_klemens", senaryo_moduller=("TR041-P01-M1", "TR042-P01-M2")))
    assert filo.senaryo_moduller == {"TR041-P01-M1", "TR042-P01-M2"}
    assert len(filo.temiz_moduller) == 4
    # Clean modules really are clean: their scenario slot is None, so nothing
    # can push on their world.
    for modul, senaryo in zip(filo.moduller, filo.senaryolar):
        assert (senaryo is None) == (modul.modul_id in filo.temiz_moduller)


def test_senaryo_orani_deterministik():
    a = Filo(_ayar(senaryo_ad="asiri_yuk", senaryo_oran=0.5))
    b = Filo(_ayar(senaryo_ad="asiri_yuk", senaryo_oran=0.5))
    assert a.senaryo_moduller == b.senaryo_moduller
    assert len(a.senaryo_moduller) == 3
    c = Filo(_ayar(senaryo_ad="asiri_yuk", senaryo_oran=0.5, tohum=12))
    assert c.senaryo_moduller != a.senaryo_moduller, "a different seed should pick a different subset"


def test_bilinmeyen_modul_hata():
    with pytest.raises(ValueError, match="not in this fleet"):
        Filo(_ayar(senaryo_ad="asiri_yuk", senaryo_moduller=("TR999-P01-M1",)))


def test_oran_ve_liste_birlikte_hata():
    with pytest.raises(ValueError):
        _ayar(senaryo_ad="asiri_yuk", senaryo_moduller=("TR041-P01-M1",), senaryo_oran=0.5)


def test_etiket_dosyasi_spec_ile_uyumlu():
    filo = Filo(
        _ayar(
            senaryo_ad="faz_dengesizlik",
            senaryo_moduller=("TR041-P01-M1",),
            senaryo_bas_s=120.0,
            senaryo_sure_s=300.0,
        )
    )
    etiket = filo.etiket(uretim_zamani=BASLANGIC + timedelta(days=1))

    assert etiket["surum"] == 1
    assert etiket["tohum"] == 11
    assert ZAMAN_BICIMI.match(etiket["uretim_zamani"])
    assert etiket["kapsam"] == {"bas": "2026-09-14T06:00:00Z", "bit": "2026-09-14T06:10:00Z"}

    assert len(etiket["senaryolar"]) == 1
    s = etiket["senaryolar"][0]
    assert s["senaryo_id"] == "senaryo_01"
    assert s["modul_id"] == "TR041-P01-M1"
    assert s["senaryo"] == "faz_dengesizligi", "label name, not the CLI name"
    assert s["baslangic"] == "2026-09-14T06:02:00Z"
    assert s["kritik_esik"] == "2026-09-14T06:07:00Z", "end of the ramp"
    assert "beklenen_tip" not in s, "the scenario-to-tip mapping is track B's, not ours"

    assert etiket["temiz_moduller"] == list(filo.temiz_moduller)
    assert len(etiket["temiz_moduller"]) == 5
    assert not set(etiket["temiz_moduller"]) & {x["modul_id"] for x in etiket["senaryolar"]}
    # Strict parser rule: every timestamp is UTC with a literal Z.
    for alan in ("baslangic", "kritik_esik"):
        assert ZAMAN_BICIMI.match(s[alan])
        zaman_oku(s[alan])


def test_ark_kritik_esigi_ilk_trip():
    """An arc does not ramp: it is critical at the first trip, not at the end."""
    filo = Filo(_ayar(senaryo_ad="ark_olay", senaryo_bas_s=0.0, senaryo_sure_s=200.0))
    s = filo.etiket()["senaryolar"][0]
    assert zaman_oku(s["kritik_esik"]) == BASLANGIC + timedelta(seconds=200.0 * 0.45)


def test_senaryosuz_kosu_etiketi_bos_senaryo_hepsi_temiz():
    etiket = Filo(_ayar()).etiket()
    assert etiket["senaryolar"] == []
    assert len(etiket["temiz_moduller"]) == 6


def test_cli_etiket_yazar(tmp_path, capsys):
    yol = tmp_path / "etiket.json"
    kod = main(
        [
            "--senaryo", "nem_yuksek",
            "--modul", "4",
            "--sure", "2",
            "--senaryo-oran", "0.5",
            "--baslangic", "2026-09-14T06:00:00Z",
            "--etiket", str(yol),
            "--sessiz",
        ]
    )
    assert kod == 0
    etiket = json.loads(yol.read_text(encoding="utf-8"))
    assert {s["senaryo"] for s in etiket["senaryolar"]} == {"nem_yukselmesi"}
    assert len(etiket["senaryolar"]) == 2
    assert len(etiket["temiz_moduller"]) == 2
    cikti = capsys.readouterr().out
    assert cikti.count("\n") == 4 * 5, "2 min at 30 s = 5 ticks x 4 modules of packets on stdout"


def test_cli_alt_kume_senaryo_ister(capsys):
    assert main(["--senaryo-oran", "0.5", "--sure", "1", "--sessiz"]) == 2
    assert "need --senaryo" in capsys.readouterr().err
