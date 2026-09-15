"""Contract ⑤ — every endpoint, against a real populated database.

The surface track C builds against, so these tests are as much about the shape
of the responses as about the status codes: a field renamed here is a breakage
there, and the contract's paths and field names are fixed.

Runs against the session-scoped scenario database, which holds real fixture
rows and real episodes produced by the real scan loop.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from analiz.api import olustur
from analiz.sozlesme import Durum, OlcumTipi, Seviye, Tip

#: Every path in section 7.3 of the parent record, plus the İZ B addition.
#: Listed here so a dropped endpoint fails a test rather than being noticed by
#: track C during integration.
SOZLESME_UCLARI = {
    ("GET", "/sahalar"),
    ("GET", "/moduller"),
    ("GET", "/moduller/{modul_id}"),
    ("GET", "/moduller/{modul_id}/seri"),
    ("GET", "/moduller/{modul_id}/termal/son"),
    ("GET", "/termal/kare/{kare_id}"),
    ("GET", "/anomaliler"),
    ("GET", "/anomaliler/{anomali_id}"),
    ("GET", "/anomaliler/{anomali_id}/gecisler"),
    ("POST", "/anomaliler/{anomali_id}/onayla"),
    ("GET", "/saglik"),
}

ZAMAN_DESENI = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"


@pytest.fixture(scope="module")
def istemci(senaryo_vt):
    _, _, ayar = senaryo_vt
    with TestClient(olustur(ayar)) as c:
        yield c


@pytest.fixture(scope="module")
def bir_anomali(istemci):
    cevap = istemci.get("/anomaliler", params={"limit": 500})
    assert cevap.status_code == 200
    veriler = cevap.json()["veriler"]
    assert veriler, "the scenario database must contain episodes"
    return veriler[0]


# --------------------------------------------------------------------------
# The contract surface
# --------------------------------------------------------------------------


def test_sozlesmenin_her_uc_noktasi_sunuluyor(istemci):
    """Every path section 7.3 lists exists, with the method it lists."""
    sunulan = {
        (yontem, rota.path)
        for rota in istemci.app.routes
        if hasattr(rota, "methods")
        for yontem in rota.methods
        if yontem in {"GET", "POST"}
    }
    eksik = SOZLESME_UCLARI - sunulan
    assert not eksik, f"contract endpoints not served: {sorted(eksik)}"


def test_saglik_gecikmeyi_bildirir(istemci):
    """Health reports how far behind the scan loop is, not just 'up'.

    Section 8 names a detector falling behind its scan period as the real
    scaling limit, so a health endpoint that returns 200 while the anomaly table
    is an hour stale is telling an operator something false.
    """
    govde = istemci.get("/saglik").json()
    assert govde["durum"] == "calisiyor"
    assert govde["sema_surumu"] >= 100
    assert govde["acik_anomali"] >= 1
    assert govde["imlecler"], "the scan loop's cursor must be visible"
    for imlec in govde["imlecler"]:
        assert "gecikme_sn" in imlec
        assert imlec["son_islenen"] is not None


def test_sahalar_agaci_hiyerarsiyi_ve_seviyeyi_tasir(istemci):
    govde = istemci.get("/sahalar").json()
    sahalar = govde["sahalar"]
    assert sahalar

    modul_sayisi = 0
    for saha in sahalar:
        assert saha["saha_kodu"]
        for pano in saha["panolar"]:
            assert pano["pano_kodu"]
            for modul in pano["moduller"]:
                modul_sayisi += 1
                # The hierarchy is inside the id; the tree must agree with it.
                assert modul["modul_id"].startswith(
                    f"{saha['saha_kodu']}-{pano['pano_kodu']}-"
                )
                assert modul["seviye"] in {e.value for e in Seviye}
    assert modul_sayisi >= 20


def test_moduller_listesi_ve_filtreleri(istemci):
    govde = istemci.get("/moduller", params={"limit": 500}).json()
    veriler = govde["veriler"]
    assert veriler
    assert govde["toplam"] >= len(veriler)

    for m in veriler:
        # `durum` here is the MODULE's state, not the anomaly lifecycle's.
        assert m["durum"] in {"aktif", "sessiz", "pasif"}
        assert m["seviye"] in {e.value for e in Seviye}

    # The silent module of scenario 7 must show as silent.
    sessiz = [m for m in veriler if m["modul_id"] == "TR063-P02-M1"]
    assert sessiz and sessiz[0]["durum"] == "sessiz"

    # Filtering by site narrows, and by severity returns only matching modules.
    tr041 = istemci.get("/moduller", params={"saha": "TR041"}).json()["veriler"]
    assert tr041 and all(m["saha_kodu"] == "TR041" for m in tr041)

    kritik = istemci.get("/moduller", params={"seviye": "kritik"}).json()["veriler"]
    assert all(m["seviye"] == "kritik" for m in kritik)
    assert kritik, "the scenario set contains critical episodes"


def test_modul_detayi_her_kanalin_son_degerini_verir(istemci):
    govde = istemci.get("/moduller/TR041-P01-M1").json()
    assert govde["modul_id"] == "TR041-P01-M1"
    assert govde["saha_kodu"] == "TR041"

    tipler = {o["olcum_tipi"] for o in govde["son_olcumler"]}
    assert {OlcumTipi.TERMAL_MAKS.value, OlcumTipi.ORTAM_SICAKLIK.value} <= tipler
    for o in govde["son_olcumler"]:
        assert o["kalite"] in {"iyi", "supheli", "yok"}
        assert o["birim"]

    # This module carries the loose-terminal scenario, so it has an open episode.
    assert govde["acik_anomaliler"]
    assert govde["acik_anomaliler"][0]["gerekce"]


def test_bilinmeyen_modul_404(istemci):
    cevap = istemci.get("/moduller/TR999-P99-M9")
    assert cevap.status_code == 404
    assert cevap.json()["hata"]["kod"] == "bulunamadi"


# --------------------------------------------------------------------------
# Series
# --------------------------------------------------------------------------


def test_seri_ham_noktalari_dondurur(istemci):
    govde = istemci.get(
        "/moduller/TR041-P01-M1/seri",
        params={"tip": "termal_maks", "bas": "2026-09-15T06:00:00Z", "bit": "2026-09-15T09:40:00Z"},
    ).json()
    assert govde["olcum_tipi"] == "termal_maks"
    assert govde["aralik"] is None
    noktalar = govde["noktalar"]
    assert len(noktalar) > 50
    zamanlar = [n["zaman"] for n in noktalar]
    assert zamanlar == sorted(zamanlar), "series must be chronological"


def test_seri_kovalarken_asgari_ve_azamiyi_da_verir(istemci):
    """A bucketed series carries min and max, not only the mean.

    A mean alone hides the spikes an operator is looking for: a bucket averaging
    46 °C may have touched 130, and a chart drawn from means would never show it.
    """
    govde = istemci.get(
        "/moduller/TR041-P01-M1/seri",
        params={"tip": "termal_maks", "aralik": "15m", "bas": "2026-09-15T03:00:00Z"},
    ).json()
    assert govde["aralik"] == "15m"
    noktalar = govde["noktalar"]
    assert noktalar
    for n in noktalar:
        assert n["asgari"] <= n["ort"] <= n["azami"]
        assert n["sayi"] >= 1


def test_seri_cok_fazla_nokta_isteginde_susmak_yerine_reddeder(istemci):
    """Too many points is refused, not silently truncated.

    A chart quietly missing its last three days looks fine and is wrong, and the
    caller has no way to tell. The error names the remedy.
    """
    dar = olustur(istemci.app.state.ayar.ile(api={"azami_seri_noktasi": 10}))
    with TestClient(dar) as c:
        cevap = c.get("/moduller/TR041-P01-M1/seri", params={"tip": "termal_maks"})
    assert cevap.status_code == 400
    hata = cevap.json()["hata"]
    assert hata["kod"] == "cok_fazla_nokta"
    assert hata["azami"] == 10
    assert hata["kabul_edilen_araliklar"]


def test_seri_gecersiz_parametreleri_reddeder(istemci):
    bozuk_zaman = istemci.get(
        "/moduller/TR041-P01-M1/seri", params={"tip": "termal_maks", "bas": "dun"}
    )
    assert bozuk_zaman.status_code == 400
    assert bozuk_zaman.json()["hata"]["kod"] == "gecersiz_zaman"

    ters = istemci.get(
        "/moduller/TR041-P01-M1/seri",
        params={"tip": "termal_maks", "bas": "2026-09-15T09:00:00Z", "bit": "2026-09-15T08:00:00Z"},
    )
    assert ters.status_code == 400
    assert ters.json()["hata"]["kod"] == "gecersiz_aralik"

    bozuk_kova = istemci.get(
        "/moduller/TR041-P01-M1/seri", params={"tip": "termal_maks", "aralik": "3 hafta"}
    )
    assert bozuk_kova.status_code == 400
    assert bozuk_kova.json()["hata"]["kod"] == "gecersiz_aralik_adi"

    # An olcum_tipi outside the enum is rejected by validation.
    assert istemci.get(
        "/moduller/TR041-P01-M1/seri", params={"tip": "voltaj"}
    ).status_code == 422


# --------------------------------------------------------------------------
# Thermal
# --------------------------------------------------------------------------


def test_termal_son_ve_tam_kare(istemci):
    ozet = istemci.get("/moduller/TR041-P01-M1/termal/son").json()
    # [sutun, satir] — x first, as everywhere else in the contract.
    sutun, satir = ozet["maks_konum"]
    assert 0 <= sutun <= 31 and 0 <= satir <= 23
    assert len(ozet["bolge_ort"]) == 4

    kareler = istemci.get("/anomaliler", params={"modul": "TR041-P01-M1"}).json()["veriler"]
    kare_id = next(
        (a["kanit"]["kare_id"] for a in kareler if a["kanit"] and "kare_id" in a["kanit"]),
        None,
    )
    assert kare_id, "the loose-terminal scenario attaches an evidence frame"

    kare = istemci.get(f"/termal/kare/{kare_id}").json()
    assert kare["satir_sayisi"] == 24
    assert kare["sutun_sayisi"] == 32
    assert kare["duzen"] == "satir_oncelikli"
    assert len(kare["piksel_verisi"]) == 768

    assert istemci.get("/termal/kare/kr_999999").status_code == 404


# --------------------------------------------------------------------------
# Anomalies
# --------------------------------------------------------------------------


def test_anomali_govdesi_sozlesme_alanlarini_tasir(bir_anomali):
    import re

    for alan in (
        "id", "modul_id", "tip", "seviye", "maks_seviye", "skor",
        "ilk_gorulme", "son_gorulme", "durum", "gerekce", "kanit",
    ):
        assert alan in bir_anomali, f"contract field {alan} missing"

    assert bir_anomali["tip"] in {e.value for e in Tip}
    assert bir_anomali["seviye"] in {e.value for e in Seviye}
    assert bir_anomali["durum"] in {e.value for e in Durum}
    assert 0.0 <= bir_anomali["skor"] <= 1.0
    assert bir_anomali["gerekce"].strip()
    assert re.match(ZAMAN_DESENI, bir_anomali["ilk_gorulme"])
    assert re.match(ZAMAN_DESENI, bir_anomali["son_gorulme"])
    # Compatibility alias for the un-amended schema on track A's branch.
    assert bir_anomali["zaman"] == bir_anomali["ilk_gorulme"]


def test_anomali_listesi_filtreleri(istemci):
    hepsi = istemci.get("/anomaliler", params={"limit": 500}).json()["veriler"]
    assert hepsi

    kritik = istemci.get("/anomaliler", params={"seviye": "kritik", "limit": 500}).json()
    assert all(a["seviye"] == "kritik" for a in kritik["veriler"])

    sensor = istemci.get("/anomaliler", params={"tip": "sensor_arizasi"}).json()["veriler"]
    assert sensor and all(a["tip"] == "sensor_arizasi" for a in sensor)

    tek_modul = istemci.get("/anomaliler", params={"modul": "TR041-P01-M1"}).json()["veriler"]
    assert tek_modul and all(a["modul_id"] == "TR041-P01-M1" for a in tek_modul)

    acik = istemci.get("/anomaliler", params={"durum": "acik", "limit": 500}).json()["veriler"]
    assert all(a["durum"] == "acik" for a in acik)


def test_anomali_sayfalama_keyset_ve_hicbir_olayi_atlamaz(istemci):
    """Keyset paging on `sira`, so the alarm service cannot miss an episode.

    Section 7.2 puts a monotonic sequence on the table precisely for this. Offset
    paging cannot make the promise: an episode opening between two requests
    shifts every later row by one and the caller silently skips an alarm.
    """
    hepsi = istemci.get("/anomaliler", params={"limit": 500}).json()["veriler"]
    toplanan: list[dict] = []
    sonra = None
    for _ in range(50):
        params = {"limit": 2}
        if sonra is not None:
            params["sonra"] = sonra
        sayfa = istemci.get("/anomaliler", params=params).json()
        toplanan.extend(sayfa["veriler"])
        sonra = sayfa["sonraki"]
        if sonra is None:
            break

    assert [a["id"] for a in toplanan] == [a["id"] for a in hepsi]
    siralar = [a["sira"] for a in toplanan]
    assert siralar == sorted(siralar), "sira must be monotonic"
    assert len(set(siralar)) == len(siralar), "paging must not repeat an episode"


def test_anomali_detayi_ve_bilinmeyen_kimlik(istemci, bir_anomali):
    govde = istemci.get(f"/anomaliler/{bir_anomali['id']}").json()
    assert govde["id"] == bir_anomali["id"]
    assert govde["gerekce"] == bir_anomali["gerekce"]

    cevap = istemci.get("/anomaliler/an_yok")
    assert cevap.status_code == 404
    assert cevap.json()["hata"]["kod"] == "bulunamadi"


def test_gecisler_journali_sirayla_verir(istemci, bir_anomali):
    """The journal: every transition, in order, with who and when."""
    govde = istemci.get(f"/anomaliler/{bir_anomali['id']}/gecisler").json()
    gecisler = govde["gecisler"]
    assert gecisler, "every episode has at least its opening transitions"

    siralar = [g["sira"] for g in gecisler]
    assert siralar == sorted(siralar)

    acilis = [g for g in gecisler if g["alan"] == "durum" and g["yeni"] == "acik"]
    assert len(acilis) == 1, "an episode opens exactly once"
    assert acilis[0]["onceki"] is None
    assert all(g["aktor"] for g in gecisler)
    assert all(g["alan"] in {"durum", "seviye"} for g in gecisler)

    assert istemci.get("/anomaliler/an_yok/gecisler").status_code == 404


def test_onay_journala_kim_ve_ne_zaman_yazar(istemci):
    """Acknowledgement is the API's only write, and it is auditable.

    It goes through OlayDeposu rather than issuing its own UPDATE, so the episode
    tables keep one writer and the transition lands in the journal with an actor.
    """
    acik = istemci.get("/anomaliler", params={"durum": "acik", "limit": 500}).json()["veriler"]
    assert acik
    hedef = acik[-1]["id"]

    cevap = istemci.post(f"/anomaliler/{hedef}/onayla", params={"aktor": "operator:efe"})
    assert cevap.status_code == 200
    assert cevap.json()["durum"] == "onaylandi"

    gecisler = istemci.get(f"/anomaliler/{hedef}/gecisler").json()["gecisler"]
    onay = [g for g in gecisler if g["yeni"] == "onaylandi"]
    assert len(onay) == 1
    assert onay[0]["aktor"] == "operator:efe"
    assert onay[0]["onceki"] == "acik"

    # Acknowledging twice is a conflict, not a silent success.
    tekrar = istemci.post(f"/anomaliler/{hedef}/onayla", params={"aktor": "operator:efe"})
    assert tekrar.status_code == 409
    assert tekrar.json()["hata"]["kod"] == "onaylanamaz"

    # The actor is mandatory: an audit trail with an optional actor answers
    # "who saw it" with a shrug.
    assert istemci.post(f"/anomaliler/{hedef}/onayla").status_code == 422


def test_hata_govdesi_tek_bicimde(istemci):
    """One error shape everywhere, so track C writes one handler."""
    for yol in ("/moduller/TR999-P99-M9", "/anomaliler/an_yok", "/termal/kare/kr_999999"):
        govde = istemci.get(yol).json()
        assert set(govde) == {"hata"}
        assert "kod" in govde["hata"] and "mesaj" in govde["hata"]
        assert govde["hata"]["mesaj"].strip()
