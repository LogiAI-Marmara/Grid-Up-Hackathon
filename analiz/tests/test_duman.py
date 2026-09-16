"""Item 14 — the smoke-test checks, run against the fixture set.

The runner is track C's; the checks are track B's. These tests prove the
checks pass on data where the answer is known (the labelled set, replayed turn
by turn so severity transitions exist), fail when the answer is wrong, and that
the entry point works over real HTTP with the documented exit codes.
"""

from __future__ import annotations

import json
import socket
import threading
import time

import pytest
from fastapi.testclient import TestClient

from analiz import duman
from analiz.api import olustur
from analiz.duman import DumanHatasi, kontrol_et, senaryolari_oku

#: The fixture set's answer, in the smoke-test input format. One clean module,
#: one loose terminal (which also escalates), one power loss, one severity
#: transition — the required coverage — plus the other health causes.
FIKSTUR_SENARYOLARI = {
    "surum": 1,
    "moduller": {
        "TR041-P01-M2": "temiz",
        "TR074-P01-M1": "temiz",
        "TR041-P01-M1": ["gevsek_klemens", "seviye_gecisi"],
        "TR041-P02-M1": ["asiri_yuk", "seviye_gecisi"],
        "TR063-P02-M3": "besleme_kaybi",
        "TR063-P02-M4": "sinyal_zayif",
        "TR063-P02-M2": "saat_kaymasi",
        "TR063-P02-M1": "sessiz",
        "TR052-P02-M1": "ark_olayi",
    },
}


@pytest.fixture(scope="module")
def istemci(kortest_vt):
    _, _, ayar = kortest_vt
    with TestClient(olustur(ayar)) as c:
        yield c


def _getir(istemci):
    def getir(yol, params):
        cevap = istemci.get(yol, params=params)
        try:
            return cevap.status_code, cevap.json()
        except ValueError:
            return cevap.status_code, None

    return getir


# --------------------------------------------------------------------------
# Input format
# --------------------------------------------------------------------------


def test_senaryo_dosyasi_siki_ayristirilir(tmp_path):
    iyi = senaryolari_oku(FIKSTUR_SENARYOLARI)
    assert iyi.moduller["TR041-P01-M1"] == ("gevsek_klemens", "seviye_gecisi")
    assert iyi.moduller["TR041-P01-M2"] == ("temiz",)
    assert iyi.bas is None

    tarihli = senaryolari_oku({**FIKSTUR_SENARYOLARI, "bas": "2026-09-15T00:00:00Z"})
    assert tarihli.bas is not None and tarihli.bas.tzinfo is not None

    with pytest.raises(DumanHatasi):
        senaryolari_oku({"surum": 2, "moduller": {"TR041-P01-M1": "temiz"}})
    with pytest.raises(DumanHatasi):
        senaryolari_oku({"surum": 1, "moduller": {}})
    with pytest.raises(DumanHatasi):
        senaryolari_oku({"surum": 1, "moduller": {"TR041-P01-M1": "uydurma"}})
    with pytest.raises(DumanHatasi):
        senaryolari_oku({"surum": 1, "moduller": {"TR041-P01-M1": ["temiz", "ark_olayi"]}})
    with pytest.raises(DumanHatasi):
        senaryolari_oku({"surum": 1, "bas": "2026-09-15T00:00:00", "moduller": {"X-Y-Z": "temiz"}})

    yol = tmp_path / "duman.json"
    yol.write_text(json.dumps(FIKSTUR_SENARYOLARI), encoding="utf-8")
    assert senaryolari_oku(yol).moduller == iyi.moduller
    with pytest.raises(DumanHatasi):
        senaryolari_oku(tmp_path / "yok.json")


# --------------------------------------------------------------------------
# The checks, against the replayed fixture set
# --------------------------------------------------------------------------


def test_14_duman_kontrolleri_fikstur_setinde_gecer(istemci):
    """Every documented scenario passes on the data it describes.

    The cursor-lag bound is lifted because the fixture set lives at a fixed
    instant in the past; a live run keeps the default.
    """
    rapor = kontrol_et(_getir(istemci), senaryolari_oku(FIKSTUR_SENARYOLARI), azami_imlec_gecikme_sn=1e12)
    assert rapor.basarili, "\n".join(k.satir for k in rapor.basarisizlar)

    adlar = {(k.ad, k.modul_id) for k in rapor.kontroller}
    assert ("temiz", "TR041-P01-M2") in adlar
    assert ("gevsek_klemens", "TR041-P01-M1") in adlar
    assert ("besleme_kaybi", "TR063-P02-M3") in adlar
    assert ("seviye_gecisi", "TR041-P01-M1") in adlar
    # The loose terminal carries a frame, so the frame decoded end to end.
    assert ("kanit_karesi", "TR041-P01-M1") in adlar
    assert {"saglik", "tarama_imleci", "veri_gecikmesi", "gecisler_akisi"} <= {k.ad for k in rapor.kontroller}


def test_14_temiz_modulde_anomali_varsa_basarisiz(istemci):
    """Calling a faulty module clean must fail — the clean check is not decorative."""
    rapor = kontrol_et(
        _getir(istemci),
        senaryolari_oku({"surum": 1, "moduller": {"TR041-P01-M1": "temiz"}}),
        azami_imlec_gecikme_sn=1e12,
    )
    assert not rapor.basarili
    assert [k.ad for k in rapor.basarisizlar] == ["temiz"]


def test_14_beklenen_senaryo_yoksa_basarisiz(istemci):
    rapor = kontrol_et(
        _getir(istemci),
        senaryolari_oku({"surum": 1, "moduller": {"TR041-P01-M2": ["gevsek_klemens", "besleme_kaybi"]}}),
        azami_imlec_gecikme_sn=1e12,
    )
    assert {k.ad for k in rapor.basarisizlar} == {"gevsek_klemens", "besleme_kaybi"}


def test_14_geride_kalan_imlec_basarisiz(istemci):
    """With the default bound the fixture set's cursor is a day behind: reported, not hidden."""
    rapor = kontrol_et(_getir(istemci), senaryolari_oku({"surum": 1, "moduller": {"TR041-P01-M2": "temiz"}}))
    assert [k.ad for k in rapor.basarisizlar] == ["tarama_imleci"]


def test_14_bas_sinirindan_onceki_olaylar_sayilmaz(istemci):
    """`bas` scopes the check to this run: the same faulty module is 'clean' after it."""
    rapor = kontrol_et(
        _getir(istemci),
        senaryolari_oku({"surum": 1, "bas": "2030-01-01T00:00:00Z", "moduller": {"TR041-P01-M1": "temiz"}}),
        azami_imlec_gecikme_sn=1e12,
    )
    assert rapor.basarili


def test_14_bilinmeyen_modul_basarisiz(istemci):
    rapor = kontrol_et(
        _getir(istemci),
        senaryolari_oku({"surum": 1, "moduller": {"TR099-P09-M9": "temiz"}}),
        azami_imlec_gecikme_sn=1e12,
    )
    assert [k.ad for k in rapor.basarisizlar] == ["modul"]


# --------------------------------------------------------------------------
# The entry point, over real HTTP
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def canli_api(kortest_vt):
    """The API served by uvicorn on a free port, as track C would run it."""
    import uvicorn

    _, _, ayar = kortest_vt
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    sunucu = uvicorn.Server(
        uvicorn.Config(olustur(ayar), host="127.0.0.1", port=port, log_level="warning")
    )
    is_parcacigi = threading.Thread(target=sunucu.run, daemon=True)
    is_parcacigi.start()
    for _ in range(100):
        if sunucu.started:
            break
        time.sleep(0.1)
    assert sunucu.started, "uvicorn did not start"
    yield f"http://127.0.0.1:{port}"
    sunucu.should_exit = True
    is_parcacigi.join(timeout=10)


def test_14_giris_noktasi_cikis_kodlari(canli_api, tmp_path, capsys):
    """0 on success, 1 on a failed check, 2 on a bad input or an unreachable API."""
    iyi = tmp_path / "iyi.json"
    iyi.write_text(json.dumps(FIKSTUR_SENARYOLARI), encoding="utf-8")
    rapor = tmp_path / "rapor.json"
    kod = duman.main(
        ["--api", canli_api, "--senaryolar", str(iyi), "--azami-imlec-gecikme-sn", "1e12", "--json", str(rapor)]
    )
    cikti = capsys.readouterr().out
    assert kod == 0, cikti
    assert "BAŞARILI" in cikti and "[HATA]" not in cikti
    assert json.loads(rapor.read_text(encoding="utf-8"))["basarili"] is True

    kotu = tmp_path / "kotu.json"
    kotu.write_text(json.dumps({"surum": 1, "moduller": {"TR041-P01-M1": "temiz"}}), encoding="utf-8")
    assert duman.main(["--api", canli_api, "--senaryolar", str(kotu), "--azami-imlec-gecikme-sn", "1e12"]) == 1
    assert "[HATA] temiz TR041-P01-M1" in capsys.readouterr().out

    bozuk = tmp_path / "bozuk.json"
    bozuk.write_text("{", encoding="utf-8")
    assert duman.main(["--api", canli_api, "--senaryolar", str(bozuk)]) == 2

    assert duman.main(["--api", "http://127.0.0.1:9", "--senaryolar", str(iyi), "--zaman-asimi-sn", "2"]) == 2
