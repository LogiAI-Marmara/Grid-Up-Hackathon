"""The contract, asserted rather than assumed.

Track B restates the contract tables in `migrations/000_sozlesme.sql` and the
contract vocabularies in `sozlesme.py`, because it has to run standalone against
a database it creates itself. That restatement is a liability: if track A's
definition moves and track B's does not, nothing crashes — the two produce
quietly different numbers, which section "sozlesmeler/README" names as worse
than a crash.

This file is where that drift becomes a failing test instead of a silent wrong
answer. It pins the column names and types track B reads, the vocabularies it
writes, and the geometry it indexes frames by.
"""

from __future__ import annotations

import pytest

from analiz.sozlesme import (
    OLCUM_ARALIK,
    OLCUM_BIRIM,
    SEVIYE_SIRA,
    TERMAL_PIKSEL,
    TERMAL_SATIR,
    TERMAL_SUTUN,
    Durum,
    Kalite,
    OlcumTipi,
    Seviye,
    Tip,
    indeks_piksel,
    modul_id_ayristir,
    piksel_indeks,
    zaman_yaz,
)

# Verbatim from section 10 of the parent decision record. Adding or renaming a
# value here is a contract change requiring the lead's approval and an
# announcement to all three tracks — so it should be a deliberate edit to this
# list, not a surprise.
BEKLENEN_OLCUM_TIPI = {
    "ortam_sicaklik", "nem", "akim_l1", "akim_l2", "akim_l3",
    "akim_notr", "termal_maks", "termal_ort", "ark_olay",
}
BEKLENEN_SEVIYE = {"normal", "izle", "uyari", "kritik"}
BEKLENEN_TIP = {
    "sicak_nokta", "akim_sicaklik_sapmasi", "faz_dengesizligi", "nem_yuksek",
    "ortam_sicaklik_yuksek", "ark", "sensor_arizasi", "modul_saglik",
}
BEKLENEN_KALITE = {"iyi", "supheli", "yok"}
BEKLENEN_DURUM = {"acik", "onaylandi", "kapandi"}


def test_sozlukler_sozlesmedeki_gibidir():
    assert {e.value for e in OlcumTipi} == BEKLENEN_OLCUM_TIPI
    assert {e.value for e in Seviye} == BEKLENEN_SEVIYE
    assert {e.value for e in Tip} == BEKLENEN_TIP
    assert {e.value for e in Kalite} == BEKLENEN_KALITE
    assert {e.value for e in Durum} == BEKLENEN_DURUM


def test_seviye_siralamasi():
    """normal < izle < uyari < kritik — the order the alarm service sorts by."""
    assert (
        SEVIYE_SIRA[Seviye.NORMAL]
        < SEVIYE_SIRA[Seviye.IZLE]
        < SEVIYE_SIRA[Seviye.UYARI]
        < SEVIYE_SIRA[Seviye.KRITIK]
    )


def test_her_olcum_tipinin_birimi_ve_araligi_vardir():
    for olcum_tipi in OlcumTipi:
        assert olcum_tipi in OLCUM_BIRIM
        assert olcum_tipi in OLCUM_ARALIK
        alt, ust = OLCUM_ARALIK[olcum_tipi]
        assert alt < ust


def test_termal_geometri_ve_piksel_sirasi():
    """32 columns x 24 rows, row-major, and coordinates are [sutun, satir] — x first.

    The decision record's `[14, 9]` example is ambiguous on its own and both
    track B and track C draw from it. This is the reading the contract fixed, and
    getting it backwards would put every evidence marker in the wrong place on
    the dashboard without anything failing.
    """
    assert TERMAL_SUTUN == 32
    assert TERMAL_SATIR == 24
    assert TERMAL_PIKSEL == 768

    assert piksel_indeks(14, 9) == 9 * 32 + 14
    assert indeks_piksel(piksel_indeks(14, 9)) == (14, 9)
    assert piksel_indeks(0, 0) == 0
    assert piksel_indeks(31, 23) == 767

    with pytest.raises(ValueError):
        piksel_indeks(32, 0)
    with pytest.raises(ValueError):
        piksel_indeks(0, 24)


def test_modul_id_hiyerarsiyi_tasir():
    saha, pano, modul = modul_id_ayristir("TR041-P01-M1")
    assert (saha, pano, modul) == ("TR041", "P01", "M1")
    with pytest.raises(ValueError):
        modul_id_ayristir("TR041_P01_M1")


def test_zaman_utc_ve_naif_zaman_reddedilir():
    """UTC with a literal Z, and a naive datetime is an error rather than a guess.

    Guessing a timezone here would be silently wrong in a system that claims to
    detect clock drift.
    """
    from datetime import datetime, timedelta, timezone

    an = datetime(2026, 9, 14, 9, 31, 20, tzinfo=timezone.utc)
    assert zaman_yaz(an) == "2026-09-14T09:31:20Z"
    # A non-UTC offset is converted, not rejected — the contract only fixes the
    # stored form.
    dogu = datetime(2026, 9, 14, 12, 31, 20, tzinfo=timezone(timedelta(hours=3)))
    assert zaman_yaz(dogu) == "2026-09-14T09:31:20Z"
    with pytest.raises(ValueError):
        zaman_yaz(datetime(2026, 9, 14, 9, 31, 20))


# --------------------------------------------------------------------------
# The schema track B reads from
# --------------------------------------------------------------------------

#: Column -> type, for the tables track B consumes. These are track A's tables;
#: this is the shape track B was built against.
BEKLENEN_SUTUNLAR = {
    "olcum": {
        "modul_id": "text",
        "olcum_tipi": "text",
        "zaman": "timestamp with time zone",
        "deger": "double precision",
        "birim": "text",
        "kalite": "text",
        "alindi_zaman": "timestamp with time zone",
    },
    "termal_ozet": {
        "modul_id": "text",
        "zaman": "timestamp with time zone",
        "maks": "double precision",
        "maks_sutun": "smallint",
        "maks_satir": "smallint",
        "bolge_ort": "ARRAY",
        "alindi_zaman": "timestamp with time zone",
    },
    "termal_kare": {
        "kare_id": "text",
        "modul_id": "text",
        "zaman": "timestamp with time zone",
        "piksel_verisi": "jsonb",
        "satir_sayisi": "smallint",
        "sutun_sayisi": "smallint",
        "alindi_zaman": "timestamp with time zone",
    },
    "modul": {
        "modul_id": "text",
        "saha_kodu": "text",
        "pano_kodu": "text",
        "modul_kodu": "text",
        "aktif": "boolean",
        "son_gorulme": "timestamp with time zone",
    },
}


@pytest.mark.parametrize("tablo", sorted(BEKLENEN_SUTUNLAR))
def test_okunan_tablolar_sozlesmedeki_sutunlara_sahiptir(tablo, baglanti):
    with baglanti.cursor() as imlec:
        imlec.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'gridup' AND table_name = %s",
            (tablo,),
        )
        gercek = {r["column_name"]: r["data_type"] for r in imlec.fetchall()}

    for sutun, tur in BEKLENEN_SUTUNLAR[tablo].items():
        assert sutun in gercek, f"gridup.{tablo}.{sutun} is missing"
        assert gercek[sutun] == tur, (
            f"gridup.{tablo}.{sutun} is {gercek[sutun]}, contract says {tur}"
        )


def test_yazilan_tablolar_karar_kaydinin_7_2_alanlarina_sahiptir(baglanti):
    """Section 7.2's amendment to contract 3: the fields track B adds."""
    with baglanti.cursor() as imlec:
        imlec.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'gridup' AND table_name = 'anomali'"
        )
        anomali = {r["column_name"] for r in imlec.fetchall()}
        imlec.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'gridup' AND table_name = 'anomali_gecis'"
        )
        gecis = {r["column_name"] for r in imlec.fetchall()}

    assert {
        "id", "modul_id", "tip", "seviye", "maks_seviye", "skor",
        "ilk_gorulme", "son_gorulme", "durum", "gerekce", "kanit", "sira",
    } <= anomali
    assert {"anomali_id", "zaman", "onceki", "yeni", "aktor"} <= gecis


def test_acik_olay_tekilligi_veritabani_tarafindan_garantidir(baglanti):
    """Episode identity is enforced by an index, not by convention.

    Two turns running concurrently must not be able to open the same episode
    twice. Application-level checking cannot guarantee that; a partial unique
    index can.
    """
    from psycopg import errors

    with baglanti.cursor() as imlec:
        imlec.execute(
            "INSERT INTO gridup.saha (saha_kodu, ad) VALUES ('TR041', 'x');"
            "INSERT INTO gridup.pano (saha_kodu, pano_kodu) VALUES ('TR041', 'P01');"
            "INSERT INTO gridup.modul (modul_id, saha_kodu, pano_kodu, modul_kodu) "
            "VALUES ('TR041-P01-M1', 'TR041', 'P01', 'M1')"
        )
        ekle = (
            "INSERT INTO gridup.anomali (id, modul_id, tip, seviye, maks_seviye, skor, "
            "ilk_gorulme, son_gorulme, durum, gerekce) VALUES "
            "(%s, 'TR041-P01-M1', 'sicak_nokta', 'uyari', 'uyari', 0.6, now(), now(), %s, 'x')"
        )
        imlec.execute(ekle, ("an_00001", "acik"))
        with pytest.raises(errors.UniqueViolation):
            imlec.execute(ekle, ("an_00002", "acik"))
    baglanti.rollback()

    # Once the first is closed, the same (modul_id, tip) may open again.
    with baglanti.cursor() as imlec:
        imlec.execute(
            "INSERT INTO gridup.saha (saha_kodu, ad) VALUES ('TR041', 'x');"
            "INSERT INTO gridup.pano (saha_kodu, pano_kodu) VALUES ('TR041', 'P01');"
            "INSERT INTO gridup.modul (modul_id, saha_kodu, pano_kodu, modul_kodu) "
            "VALUES ('TR041-P01-M1', 'TR041', 'P01', 'M1')"
        )
        imlec.execute(
            "INSERT INTO gridup.anomali (id, modul_id, tip, seviye, maks_seviye, skor, "
            "ilk_gorulme, son_gorulme, durum, gerekce, kapanma_zaman) VALUES "
            "('an_00001', 'TR041-P01-M1', 'sicak_nokta', 'uyari', 'uyari', 0.6, "
            "now(), now(), 'kapandi', 'x', now())"
        )
        imlec.execute(ekle, ("an_00002", "acik"))
    baglanti.rollback()
