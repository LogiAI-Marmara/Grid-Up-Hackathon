"""Integration-phase behaviour: items 8–11 of the track B integration task.

Each test names the item it proves. They run against the schema track A's
migrations define (plus, until track A's PR is on main, the stand-in that adds
`modul_durum` and the binary frame column — see conftest).
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from analiz.pencere import PencereGetirici
from analiz.sozlesme import Besleme, Kalite, OlcumTipi, Tip
from analiz.tarama import Tarayici
from analiz.termal import KARE_BAYT, KareHatasi, kare_coz, kare_kodla


def _saglikli(fikstur, modul_id, an, *, saat=2.0, adim_sn=60, deger=45.0, gecikme_sn=2.0):
    """A flat, healthy thermal series ending at `an`, arriving `gecikme_sn` late."""
    fikstur.modul(modul_id)
    zaman = an - timedelta(hours=saat)
    i = 0
    while zaman <= an:
        fikstur.olcum(
            modul_id,
            OlcumTipi.TERMAL_MAKS,
            zaman,
            deger + (i % 3) * 0.1,
            Kalite.IYI,
            zaman + timedelta(seconds=gecikme_sn),
        )
        zaman += timedelta(seconds=adim_sn)
        i += 1


def _durumlar(fikstur, modul_id, an, *, saat=2.0, adim_sn=60, besleme=None, sinyal=None,
              gecikme_sn=2.0):
    """One status row per packet. `besleme(t)` / `sinyal(t)` take progress 0..1."""
    zaman = an - timedelta(hours=saat)
    toplam = saat * 3600.0
    while zaman <= an:
        ilerleme = 1.0 - (an - zaman).total_seconds() / toplam
        fikstur.durum(
            modul_id,
            zaman,
            besleme=besleme(ilerleme) if besleme else Besleme.SEBEKE,
            sinyal=sinyal(ilerleme) if sinyal else -72,
            alindi_zaman=zaman + timedelta(seconds=gecikme_sn),
        )
        zaman += timedelta(seconds=adim_sn)


def _olaylar(baglanti, modul_id):
    with baglanti.cursor() as imlec:
        imlec.execute(
            "SELECT id, tip, seviye, durum, gerekce, kanit FROM gridup.anomali "
            "WHERE modul_id = %s ORDER BY sira",
            (modul_id,),
        )
        return imlec.fetchall()


def _tur(baglanti, ayar, an, geri_saat=3.0):
    # bekleme_sn (D2's delay-on) forced to 0: every test in this file drives
    # exactly ONE scan turn to check what that turn found, which is the
    # single-turn case delay-on exists specifically to hold back — a
    # condition seen on turn one alone never opens on production defaults.
    # That is the correct production behaviour and is covered on its own
    # terms in tests/test_olay.py; these tests are about what item 8/9/10's
    # wiring finds once persistence is not the thing being measured.
    tarayici = Tarayici(baglanti, ayar.ile(olay={"bekleme_sn": 0.0}))
    tarayici.imlecler.geri_al(ayar.tarama.imlec_adi, an - timedelta(hours=geri_saat))
    return tarayici.tur(simdi=an + timedelta(seconds=5))


# --------------------------------------------------------------------------
# Item 8 — module status
# --------------------------------------------------------------------------


def test_8_yedek_beslemeye_dusen_modul_icin_anomali_acilir(baglanti, fikstur, ayar, an):
    """A module that falls back to backup power gets a `modul_saglik` episode.

    The measurements stay perfectly healthy: the only evidence is the status
    rows, which is exactly the signal the old detector could not see.
    """
    modul_id = "TR041-P01-M1"
    _saglikli(fikstur, modul_id, an)
    _durumlar(fikstur, modul_id, an, besleme=lambda p: Besleme.YEDEK if p >= 0.9 else Besleme.SEBEKE)
    fikstur.yaz()

    sonuc = _tur(baglanti, ayar, an)
    assert sonuc.modul == 1

    olaylar = _olaylar(baglanti, modul_id)
    saglik = [o for o in olaylar if o["tip"] == Tip.MODUL_SAGLIK.value]
    assert len(saglik) == 1, f"expected one modul_saglik episode, got {olaylar}"
    assert saglik[0]["kanit"]["neden"] == "besleme"
    assert saglik[0]["kanit"]["besleme"] == "yedek"
    assert "yedek" in saglik[0]["gerekce"]
    assert saglik[0]["seviye"] == ayar.katman0.besleme_seviye.value
    # Nothing else fired on a module whose measurements are fine.
    assert {o["tip"] for o in olaylar} == {Tip.MODUL_SAGLIK.value}


def test_8_sebekede_kalan_modul_icin_anomali_acilmaz(baglanti, fikstur, ayar, an):
    modul_id = "TR041-P01-M1"
    _saglikli(fikstur, modul_id, an)
    _durumlar(fikstur, modul_id, an)
    fikstur.yaz()
    _tur(baglanti, ayar, an)
    assert _olaylar(baglanti, modul_id) == []


def test_8_tek_yedek_paketi_yeterli_degildir(baglanti, fikstur, ayar, an):
    """One packet on backup is below `besleme_yedek_ardisik` (2) — no episode."""
    modul_id = "TR041-P01-M1"
    _saglikli(fikstur, modul_id, an)
    _durumlar(fikstur, modul_id, an, besleme=lambda p: Besleme.YEDEK if p >= 0.999 else Besleme.SEBEKE)
    fikstur.yaz()
    _tur(baglanti, ayar, an)
    assert _olaylar(baglanti, modul_id) == []


def test_8_zayiflayan_sinyal_modul_saglik_uretir(baglanti, fikstur, ayar, an):
    modul_id = "TR041-P01-M1"
    _saglikli(fikstur, modul_id, an)
    _durumlar(fikstur, modul_id, an, sinyal=lambda p: int(-72 - 45 * p))
    fikstur.yaz()

    _tur(baglanti, ayar, an)
    saglik = [o for o in _olaylar(baglanti, modul_id) if o["tip"] == Tip.MODUL_SAGLIK.value]
    assert len(saglik) == 1
    assert saglik[0]["kanit"]["neden"] == "sinyal"
    assert saglik[0]["kanit"]["olculen"] < ayar.katman0.sinyal_zayif_dbm
    assert "dBm" in saglik[0]["gerekce"]


def test_8_esikler_ayardan_gelir(baglanti, fikstur, ayar, an):
    """Thresholds live in configuration: raise the dBm floor and the same data fires."""
    modul_id = "TR041-P01-M1"
    _saglikli(fikstur, modul_id, an)
    _durumlar(fikstur, modul_id, an)  # a steady -72 dBm
    fikstur.yaz()

    _tur(baglanti, ayar, an)
    assert _olaylar(baglanti, modul_id) == []

    sert = ayar.ile(katman0={"sinyal_zayif_dbm": -60.0})
    _tur(baglanti, sert, an)
    saglik = [o for o in _olaylar(baglanti, modul_id) if o["tip"] == Tip.MODUL_SAGLIK.value]
    assert len(saglik) == 1 and saglik[0]["kanit"]["neden"] == "sinyal"


def test_8_yalnizca_durum_gonderen_modul_yeniden_degerlendirilir(baglanti, fikstur, ayar, an):
    """New `modul_durum` rows are a "re-evaluate this module" signal on their own.

    The module's measurements all arrived BEFORE the cursor; only status rows
    arrive inside the turn's range. Before the integration phase that module
    would not be in the turn's set at all.
    """
    modul_id = "TR041-P01-M1"
    # Ten minutes of status-only traffic: long enough for the power finding,
    # short of the 15-minute silence threshold, so the cause is unambiguous.
    eski = an - timedelta(minutes=10)
    _saglikli(fikstur, modul_id, eski, gecikme_sn=2.0)
    # Status rows keep coming for the next ten minutes, on backup power.
    zaman = eski + timedelta(minutes=1)
    while zaman <= an:
        fikstur.durum(modul_id, zaman, besleme=Besleme.YEDEK, alindi_zaman=zaman + timedelta(seconds=2))
        zaman += timedelta(minutes=1)
    fikstur.yaz()

    tarayici = Tarayici(baglanti, ayar.ile(olay={"bekleme_sn": 0.0}))  # single turn; see `_tur`
    # Cursor sits after the last measurement's arrival; only status rows are new.
    tarayici.imlecler.geri_al(ayar.tarama.imlec_adi, eski + timedelta(seconds=30))
    sonuc = tarayici.tur(simdi=an + timedelta(seconds=5))

    assert sonuc.modul == 1, "a status-only arrival must put the module in the turn"
    assert sonuc.satir > 0
    assert [d.modul_id for d in sonuc.degerlendirmeler] == [modul_id]
    saglik = [o for o in _olaylar(baglanti, modul_id) if o["tip"] == Tip.MODUL_SAGLIK.value]
    assert saglik and saglik[0]["kanit"]["neden"] == "besleme"


# --------------------------------------------------------------------------
# Item 9 — clock drift vs late data
# --------------------------------------------------------------------------


def _saat_kaymasi_bulgulari(baglanti, modul_id):
    return [
        o for o in _olaylar(baglanti, modul_id)
        if o["tip"] == Tip.MODUL_SAGLIK.value and o["kanit"].get("neden") == "saat_kaymasi"
    ]


def test_9_geriye_doldurulan_veri_saat_kaymasi_uretmez(baglanti, fikstur, ayar, an):
    """Late (backfilled) data: minimum gap near zero, maximum gap hours. Not drift.

    The uplink was down for two hours and the backlog arrived at once. Every
    measurement time is right; only the arrival times are late. The old rule
    judged the maximum gap and called this a broken clock.
    """
    modul_id = "TR041-P01-M1"
    fikstur.modul(modul_id)
    zaman = an - timedelta(hours=2)
    i = 0
    while zaman <= an:
        # Everything measured before the last five minutes arrives now.
        gec = zaman < an - timedelta(minutes=5)
        fikstur.olcum(
            modul_id, OlcumTipi.TERMAL_MAKS, zaman, 45.0 + (i % 3) * 0.1, Kalite.IYI,
            an if gec else zaman + timedelta(seconds=2),
        )
        zaman += timedelta(seconds=60)
        i += 1
    fikstur.yaz()

    _tur(baglanti, ayar, an)
    assert _saat_kaymasi_bulgulari(baglanti, modul_id) == []
    assert _olaylar(baglanti, modul_id) == []


def test_9_gelecek_tarihli_olcum_saat_kaymasidir(baglanti, fikstur, ayar, an):
    """A measurement stamped after it was received can only be a wrong clock."""
    modul_id = "TR041-P01-M1"
    _saglikli(fikstur, modul_id, an)
    # One reading measured a minute AFTER the collector received it.
    ileri = an - timedelta(minutes=10)
    fikstur.olcum(modul_id, OlcumTipi.TERMAL_MAKS, ileri, 45.05, Kalite.IYI, ileri - timedelta(seconds=60))
    fikstur.yaz()

    _tur(baglanti, ayar, an)
    bulgular = _saat_kaymasi_bulgulari(baglanti, modul_id)
    assert len(bulgular) == 1
    assert bulgular[0]["kanit"]["yon"] == "ileri"
    assert bulgular[0]["kanit"]["olculen"] == pytest.approx(-60.0)
    assert "ileri" in bulgular[0]["gerekce"]


def test_9_kucuk_ileri_sapma_tolerans_icindedir(baglanti, fikstur, ayar, an):
    """A second of NTP scatter is not drift (`ileri_tarih_tolerans_sn`)."""
    modul_id = "TR041-P01-M1"
    _saglikli(fikstur, modul_id, an, gecikme_sn=-1.0)
    fikstur.yaz()
    _tur(baglanti, ayar, an)
    assert _saat_kaymasi_bulgulari(baglanti, modul_id) == []


def test_9_hicbir_olcum_taze_degilse_saat_kaymasidir(baglanti, fikstur, ayar, an):
    """Minimum gap above the threshold: the offset is in the clock, not the network."""
    modul_id = "TR041-P01-M1"
    _saglikli(fikstur, modul_id, an, gecikme_sn=900.0)
    fikstur.yaz()

    _tur(baglanti, ayar, an)
    bulgular = _saat_kaymasi_bulgulari(baglanti, modul_id)
    assert len(bulgular) == 1
    assert bulgular[0]["kanit"]["yon"] == "geri"
    assert bulgular[0]["kanit"]["olculen"] == pytest.approx(900.0)


# --------------------------------------------------------------------------
# Item 10 — the evidence frame belongs to the event's time
# --------------------------------------------------------------------------


def _kare_idler(baglanti, modul_id):
    with baglanti.cursor() as imlec:
        imlec.execute(
            "SELECT kare_id, zaman FROM gridup.termal_kare WHERE modul_id = %s ORDER BY zaman",
            (modul_id,),
        )
        return {r["zaman"]: r["kare_id"] for r in imlec.fetchall()}


def test_10_pencere_degerlendirme_anindan_sonraki_kareyi_baglamaz(baglanti, fikstur, ayar, an):
    modul_id = "TR041-P01-M1"
    fikstur.modul(modul_id)
    zamanlar = [an - timedelta(hours=h) for h in (5, 3, 1, 0)]
    for z in zamanlar:
        fikstur.termal(modul_id, z, 60.0, 18, 11, (40.0, 40.0, 40.0, 40.0), kare=True)
    fikstur.yaz()
    kareler = _kare_idler(baglanti, modul_id)
    assert len(kareler) == 4

    getirici = PencereGetirici(baglanti, ayar)
    # A historical instant: two hours ago. The frames at -1 h and now exist in
    # the table but are later than the instant being judged.
    gecmis = getirici.getir({modul_id: an - timedelta(hours=2)})[modul_id]
    assert gecmis.kare_id == kareler[an - timedelta(hours=3)]
    assert gecmis.kare_zaman == an - timedelta(hours=3)

    simdi = getirici.getir({modul_id: an})[modul_id]
    assert simdi.kare_id == kareler[an]

    # Older than the detection window: no frame, rather than a stale one.
    cok_eski = getirici.getir({modul_id: an - timedelta(hours=5) - timedelta(seconds=1)})[modul_id]
    assert cok_eski.kare_id is None


def test_10_gecmis_yeniden_taramada_olayin_kendi_karesi_baglanir(baglanti, fikstur, ayar, an):
    """A re-scan of history links the frame of the event's time, not the newest.

    The module ran hot all afternoon and sent a frame every half hour. The
    detector is rewound to noon and re-scans; the episode it opens must cite
    the noon frame although the evening frames are already in the table.
    """
    modul_id = "TR041-P01-M1"
    fikstur.modul(modul_id)
    bas = an - timedelta(hours=6)
    zaman = bas
    i = 0
    while zaman <= an:
        # 95 °C: above layer 1's `uyari` limit, so the episode is certain and its
        # `kanit` carries the frame.
        fikstur.olcum(modul_id, OlcumTipi.TERMAL_MAKS, zaman, 95.0 + (i % 3) * 0.1, Kalite.IYI, zaman)
        if i % 30 == 0:
            fikstur.termal(modul_id, zaman, 95.0, 18, 11, (60.0, 60.0, 60.0, 60.0), kare=True,
                           alindi_zaman=zaman)
        zaman += timedelta(seconds=60)
        i += 1
    fikstur.yaz()
    kareler = _kare_idler(baglanti, modul_id)

    # Rewind to noon (three hours in), run ONE turn covering the next half hour.
    ogle = bas + timedelta(hours=3)
    # bekleme_sn forced to 0: this drives one turn to check frame-linking on
    # a historical re-scan, not delay-on persistence.
    yeniden = ayar.ile(tarama={"azami_aralik_sn": 30 * 60.0}, olay={"bekleme_sn": 0.0})
    tarayici = Tarayici(baglanti, yeniden)
    tarayici.imlecler.geri_al(yeniden.tarama.imlec_adi, ogle)
    sonuc = tarayici.tur(simdi=an)
    assert sonuc.modul == 1 and sonuc.acilan

    olay = _olaylar(baglanti, modul_id)[0]
    kare_id = olay["kanit"]["kare_id"]
    kare_zamani = next(z for z, k in kareler.items() if k == kare_id)
    assert kare_zamani <= sonuc.bit, "evidence frame must not be later than the evaluation instant"
    assert kare_zamani >= ogle, "evidence frame must belong to the re-scanned stretch"
    assert kare_id != kareler[max(kareler)], "the newest frame is not the event's frame"


# --------------------------------------------------------------------------
# Item 11 — the binary frame
# --------------------------------------------------------------------------


def test_11_kare_kodlama_sozlesmedeki_gibidir():
    """int16 signed, little-endian, 0.1 °C, row-major, exactly 1536 bytes."""
    assert KARE_BAYT == 1536
    veri = kare_kodla([45.2] * 768)
    assert len(veri) == 1536
    assert veri[:2] == b"\xc4\x01"  # 452 = 0x01C4, little-endian
    assert kare_coz(veri) == [45.2] * 768

    # Negative values and row-major order survive the round trip.
    kare = [(-40.0 + (i % 32) * 0.1 + (i // 32)) for i in range(768)]
    geri = kare_coz(kare_kodla(kare))
    assert geri == pytest.approx(kare, abs=1e-9)
    assert geri[9 * 32 + 14] == pytest.approx(kare[9 * 32 + 14])

    with pytest.raises(KareHatasi):
        kare_coz(b"\x00" * 1535)
    with pytest.raises(KareHatasi):
        kare_kodla([0.0] * 767)
    with pytest.raises(KareHatasi):
        kare_kodla([5000.0] * 768)


def test_11_veritabanindaki_kare_1536_bayttir(baglanti, fikstur, an):
    modul_id = "TR041-P01-M1"
    fikstur.modul(modul_id)
    fikstur.termal(modul_id, an, 72.4, 14, 9, (40.0, 41.0, 39.0, 40.5), kare=True)
    fikstur.yaz()
    with baglanti.cursor() as imlec:
        imlec.execute(
            "SELECT piksel_verisi, octet_length(piksel_verisi) AS n FROM gridup.termal_kare "
            "WHERE modul_id = %s",
            (modul_id,),
        )
        satir = imlec.fetchone()
    assert satir["n"] == 1536
    pikseller = kare_coz(satir["piksel_verisi"])
    assert len(pikseller) == 768
    assert max(pikseller) == pytest.approx(72.4)
    assert pikseller[9 * 32 + 14] == pytest.approx(72.4)
