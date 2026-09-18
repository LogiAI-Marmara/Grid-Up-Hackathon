"""Ingest service tests, run against the `dosya` backend with no database.

The endpoint under test is the shipped one (``uygulama_olustur``), injected with a
file backend pointed at a temporary directory. Two behaviours matter:

* an invalid packet is rejected with a 400 whose body quotes the contract and a
  reason (`gerekce`), because the producer's next question is always "why";
* a valid packet is stored — the ``dosya`` backend appends JSONL per table, so a
  test can read the rows back and assert on them directly instead of trusting a
  success code.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from toplama.kayit import DosyaKayit
from toplama.uygulama import uygulama_olustur


def paket_yap(**ustler) -> dict:
    """A minimal valid packet, shaped like the module simulator's output.

    One measurement row plus the required health block. ``ustler`` overrides
    top-level keys (and merges ``olcumler`` / ``modul_durum`` when passed).
    """
    paket = {
        "modul_id": "TR041-P01-M1",
        "zaman": "2026-09-14T09:31:20Z",
        "olcumler": [
            {
                "modul_id": "TR041-P01-M1",
                "zaman": "2026-09-14T09:31:20Z",
                "olcum_tipi": "ortam_sicaklik",
                "deger": 34.7,
                "birim": "C",
                "kalite": "iyi",
            },
            {
                "modul_id": "TR041-P01-M1",
                "zaman": "2026-09-14T09:31:20Z",
                "olcum_tipi": "nem",
                "deger": 61.2,
                "birim": "%",
                "kalite": "iyi",
            },
        ],
        "termal_ozet": None,
        "termal_kare": None,
        "modul_durum": {
            "besleme": "sebeke",
            "sinyal": -72,
            "yazilim_surumu": "1.0.3",
        },
    }
    for anahtar, deger in ustler.items():
        if anahtar in ("olcumler", "modul_durum") and isinstance(deger, dict):
            paket[anahtar].update(deger)
        else:
            paket[anahtar] = deger
    return paket


@pytest.fixture()
def istemci(tmp_path):
    depo = DosyaKayit(tmp_path)
    uygulama = uygulama_olustur(depo)
    with TestClient(uygulama) as istemci:
        istemci.depo = depo  # type: ignore[attr-defined]
        yield istemci


def _gonder(istemci, paket):
    return istemci.post("/paket", json=paket)


def test_gecerli_paket_yazilir(istemci):
    yanit = _gonder(istemci, paket_yap())
    assert yanit.status_code == 201, yanit.text
    govde = yanit.json()
    assert govde["modul_id"] == "TR041-P01-M1"
    assert govde["olcum"] == 2
    assert govde["yinelenen"] is False

    # The two measurement rows really landed on disk, with alindi_zaman stamped.
    olcumler = istemci.depo.oku("olcum")
    assert len(olcumler) == 2
    tipler = sorted(s["olcum_tipi"] for s in olcumler)
    assert tipler == ["nem", "ortam_sicaklik"]
    for satir in olcumler:
        assert satir["modul_id"] == "TR041-P01-M1"
        assert "alindi_zaman" in satir

    # Integration item 1: modul_durum (power source and signal strength) is recorded.
    durumlar = istemci.depo.oku("modul_durum")
    assert len(durumlar) == 1
    assert durumlar[0]["modul_id"] == "TR041-P01-M1"
    assert durumlar[0]["besleme"] == "sebeke"
    assert durumlar[0]["sinyal"] == -72
    assert durumlar[0]["yazilim_surumu"] == "1.0.3"
    assert "alindi_zaman" in durumlar[0]


def test_gecersiz_paket_reddedilir(istemci):
    # Missing the health block entirely.
    ham = paket_yap()
    del ham["modul_durum"]
    yanit = _gonder(istemci, ham)
    assert yanit.status_code == 400, yanit.text
    govde = yanit.json()
    assert govde["hata"] == "gecersiz_paket"
    assert govde["sozlesme"] == "modul_paketi.schema.json"
    assert govde["gerekce"], "a rejection must explain itself"

    # Nothing was stored.
    assert istemci.depo.oku("olcum") == []


def test_birim_uyusmazligi_reddedilir(istemci):
    # A current row labelled with Celsius fails the unit-pairing rule in the model
    # layer (past the schema), because the unit is determined by olcum_tipi.
    paket = paket_yap(
        olcumler=[
            {
                "modul_id": "TR041-P01-M1",
                "zaman": "2026-09-14T09:31:20Z",
                "olcum_tipi": "akim_l1",
                "deger": 318.0,
                "birim": "C",  # wrong: currents are amperes
                "kalite": "iyi",
            }
        ]
    )
    yanit = _gonder(istemci, paket)
    assert yanit.status_code == 400, yanit.text
    assert "birim" in yanit.json()["gerekce"][0]


def test_bos_govde_400_dondurur(istemci):
    yanit = istemci.post("/paket", content=b"", headers={"content-type": "application/json"})
    assert yanit.status_code == 400
    assert yanit.json()["hata"] == "bos_govde"


def test_saglik_uc_noktasi(istemci):
    yanit = istemci.get("/saglik")
    assert yanit.status_code == 200
    govde = yanit.json()
    assert govde["servis"] == "toplama"
    assert govde["durum"] == "ayakta"
    assert govde["depo"]["kayit"] == "dosya"