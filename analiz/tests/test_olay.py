"""Decision K3: one episode per fault, hysteresis, and a journal row per transition.

Section 6.2's arithmetic is the reason all of this exists: a three-day fault at a
10 s scan period is 25,920 turns, and a row per turn would be 25,920 anomaly rows
for one loose screw. These tests are what keep that from happening.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from analiz.dedektor.taban import Bulgu
from analiz.olay import OlayDeposu
from analiz.sozlesme import Durum, Seviye, Tip


def _bulgu(zaman, seviye=Seviye.UYARI, skor=0.6, tip=Tip.SICAK_NOKTA, gerekce=None):
    return Bulgu(
        tip=tip,
        seviye=seviye,
        skor=skor,
        katman=2,
        gerekce=gerekce or f"Sıcak nokta {60.0:.1f} °C ölçüldü, taban çizgisi 45.0 °C.",
        zaman=zaman,
        kanit={"esik": 50.0, "olculen": 60.0},
    )


def _olaylar(baglanti, modul_id=None):
    with baglanti.cursor() as imlec:
        if modul_id:
            imlec.execute(
                "SELECT * FROM gridup.anomali WHERE modul_id = %s ORDER BY sira", (modul_id,)
            )
        else:
            imlec.execute("SELECT * FROM gridup.anomali ORDER BY sira")
        return imlec.fetchall()


def _gecisler(baglanti, anomali_id=None):
    with baglanti.cursor() as imlec:
        if anomali_id:
            imlec.execute(
                "SELECT * FROM gridup.anomali_gecis WHERE anomali_id = %s ORDER BY id",
                (anomali_id,),
            )
        else:
            imlec.execute("SELECT * FROM gridup.anomali_gecis ORDER BY id")
        return imlec.fetchall()


def test_olay_bir_kez_acilir_sonra_guncellenir(baglanti, fikstur, ayar, an):
    """Fifty turns finding the same condition produce one row, not fifty.

    The core of K3. `son_gorulme` moves, `ilk_gorulme` does not — lead time
    (section 2.5) is measured from the first sighting, so an `ilk_gorulme` that
    crept forward would flatter the headline metric of the whole project.
    """
    modul_id = fikstur.modul("TR041-P01-M1")
    fikstur.yaz()
    depo = OlayDeposu(baglanti, ayar)

    for i in range(50):
        zaman = an + timedelta(seconds=10 * i)
        depo.uygula(modul_id, [_bulgu(zaman)], zaman)
    baglanti.commit()

    olaylar = _olaylar(baglanti, modul_id)
    assert len(olaylar) == 1, "the same condition must not open a second episode"
    olay = olaylar[0]
    assert olay["ilk_gorulme"] == an
    assert olay["son_gorulme"] == an + timedelta(seconds=490)
    assert olay["durum"] == Durum.ACIK.value


def test_her_gecis_icin_journal_satiri_vardir(baglanti, fikstur, ayar, an):
    """Every state and severity change leaves a journal row; nothing else does.

    Section 6.4: the journal is an audit trail, and an audit trail with a missing
    row is not one. Section 6.5 draws the other edge: a score moving inside the
    same severity is not a transition and must not be recorded as one.
    """
    modul_id = fikstur.modul("TR041-P01-M1")
    fikstur.yaz()
    depo = OlayDeposu(baglanti, ayar)

    # open at izle
    depo.uygula(modul_id, [_bulgu(an, Seviye.IZLE, 0.35)], an)
    # score moves inside izle — not a transition
    depo.uygula(modul_id, [_bulgu(an + timedelta(minutes=1), Seviye.IZLE, 0.41)], an)
    # izle -> uyari — a transition
    depo.uygula(modul_id, [_bulgu(an + timedelta(minutes=2), Seviye.UYARI, 0.6)], an)
    # uyari -> kritik — a transition
    depo.uygula(modul_id, [_bulgu(an + timedelta(minutes=3), Seviye.KRITIK, 0.9)], an)
    baglanti.commit()

    olay = _olaylar(baglanti, modul_id)[0]
    gecisler = _gecisler(baglanti, olay["id"])

    durum_gecisleri = [g for g in gecisler if g["alan"] == "durum"]
    seviye_gecisleri = [g for g in gecisler if g["alan"] == "seviye"]

    assert [(g["onceki"], g["yeni"]) for g in durum_gecisleri] == [(None, "acik")]
    assert [(g["onceki"], g["yeni"]) for g in seviye_gecisleri] == [
        ("normal", "izle"),
        ("izle", "uyari"),
        ("uyari", "kritik"),
    ], "a score change inside one severity is not a transition"
    assert all(g["aktor"] == "sistem" for g in gecisler)

    # maks_seviye records the worst reached, and does not fall back.
    depo.uygula(modul_id, [_bulgu(an + timedelta(minutes=4), Seviye.IZLE, 0.3)], an)
    baglanti.commit()
    olay = _olaylar(baglanti, modul_id)[0]
    assert olay["seviye"] == "izle"
    assert olay["maks_seviye"] == "kritik"


def test_histerezis_olayin_acilip_kapanmasini_onler(baglanti, fikstur, ayar, an):
    """A condition that flickers does not open and close an episode each time.

    Section 6.5's chattering. Without hysteresis a value sitting on a threshold
    produces an alarm every time it crosses, and an operator watching that learns
    within an afternoon to ignore the system.
    """
    modul_id = fikstur.modul("TR041-P01-M1")
    fikstur.yaz()
    depo = OlayDeposu(baglanti, ayar)
    histerezis = timedelta(seconds=ayar.olay.histerezis_sn)

    depo.uygula(modul_id, [_bulgu(an)], an)
    baglanti.commit()

    # Gone for a few minutes — well inside the hysteresis window. Stays open.
    depo.kapat_sureli(an + timedelta(minutes=5))
    baglanti.commit()
    assert _olaylar(baglanti, modul_id)[0]["durum"] == Durum.ACIK.value

    # It comes back. Still the same episode, not a second one.
    geri_gelis = an + timedelta(minutes=8)
    depo.uygula(modul_id, [_bulgu(geri_gelis)], geri_gelis)
    baglanti.commit()
    assert len(_olaylar(baglanti, modul_id)) == 1

    # Now genuinely gone: past the hysteresis window since the last sighting.
    kapanma = geri_gelis + histerezis + timedelta(minutes=1)
    kapandi = depo.kapat_sureli(kapanma)
    baglanti.commit()
    assert len(kapandi) == 1

    olay = _olaylar(baglanti, modul_id)[0]
    assert olay["durum"] == Durum.KAPANDI.value
    assert olay["kapanma_zaman"] == kapanma

    gecisler = [g for g in _gecisler(baglanti, olay["id"]) if g["alan"] == "durum"]
    assert [(g["onceki"], g["yeni"]) for g in gecisler] == [
        (None, "acik"),
        ("acik", "kapandi"),
    ]


def test_kapanan_olaydan_sonra_yeni_olay_acilir(baglanti, fikstur, ayar, an):
    """Once closed, the same fault recurring is a genuinely new episode.

    The partial unique index only constrains *open* episodes, which is what makes
    "the same fault last month" and "the same fault today" two rows rather than
    one row with a misleading span.
    """
    modul_id = fikstur.modul("TR041-P01-M1")
    fikstur.yaz()
    depo = OlayDeposu(baglanti, ayar)

    depo.uygula(modul_id, [_bulgu(an)], an)
    depo.kapat_sureli(an + timedelta(seconds=ayar.olay.histerezis_sn + 60))
    baglanti.commit()

    yeniden = an + timedelta(days=1)
    depo.uygula(modul_id, [_bulgu(yeniden)], yeniden)
    baglanti.commit()

    olaylar = _olaylar(baglanti, modul_id)
    assert len(olaylar) == 2
    assert olaylar[0]["durum"] == Durum.KAPANDI.value
    assert olaylar[1]["durum"] == Durum.ACIK.value
    assert olaylar[0]["sira"] < olaylar[1]["sira"]


def test_farkli_tipler_ayri_olaylardir(baglanti, fikstur, ayar, an):
    """Episode identity is (modul_id, tip): two fault types are two episodes."""
    modul_id = fikstur.modul("TR041-P01-M1")
    fikstur.yaz()
    depo = OlayDeposu(baglanti, ayar)

    depo.uygula(
        modul_id,
        [
            _bulgu(an, tip=Tip.SICAK_NOKTA),
            _bulgu(an, tip=Tip.NEM_YUKSEK, gerekce="Bağıl nem %92.0, eşik %85."),
        ],
        an,
    )
    baglanti.commit()

    olaylar = _olaylar(baglanti, modul_id)
    assert {o["tip"] for o in olaylar} == {"sicak_nokta", "nem_yuksek"}


def test_operator_onayi_journala_kim_ve_ne_zaman_yazar(baglanti, fikstur, ayar, an):
    """An acknowledgement is a transition, and it records who made it.

    Section 6.4: "when did this alarm arrive, who saw it, when did it close" is a
    regulatory question, so the actor is not optional. The read API is out of
    scope for this delivery, but the transition it will call is here and tested.
    """
    modul_id = fikstur.modul("TR041-P01-M1")
    fikstur.yaz()
    depo = OlayDeposu(baglanti, ayar)
    depo.uygula(modul_id, [_bulgu(an)], an)
    baglanti.commit()

    olay_id = _olaylar(baglanti, modul_id)[0]["id"]
    assert depo.onayla(olay_id, "operator:efe", an + timedelta(minutes=2))
    baglanti.commit()

    assert _olaylar(baglanti, modul_id)[0]["durum"] == Durum.ONAYLANDI.value
    onay = [
        g for g in _gecisler(baglanti, olay_id) if g["yeni"] == Durum.ONAYLANDI.value
    ]
    assert len(onay) == 1
    assert onay[0]["aktor"] == "operator:efe"
    assert onay[0]["onceki"] == Durum.ACIK.value

    # An acknowledged episode still closes when the condition goes away.
    depo.kapat_sureli(an + timedelta(seconds=ayar.olay.histerezis_sn + 60))
    baglanti.commit()
    assert _olaylar(baglanti, modul_id)[0]["durum"] == Durum.KAPANDI.value


def test_kimlik_ve_sira_birlikte_artar(baglanti, fikstur, ayar, an):
    """`id` and `sira` come from one sequence, so their orderings cannot disagree.

    Section 7.2 asks for a monotonic sequence so the alarm service can read
    "everything after the last one I handled" without missing an episode. Two
    independent counters would eventually disagree under concurrency.
    """
    fikstur.modul("TR041-P01-M1")
    fikstur.modul("TR041-P01-M2")
    fikstur.yaz()
    depo = OlayDeposu(baglanti, ayar)
    depo.uygula("TR041-P01-M1", [_bulgu(an)], an)
    depo.uygula("TR041-P01-M2", [_bulgu(an)], an)
    baglanti.commit()

    olaylar = _olaylar(baglanti)
    assert [o["id"] for o in olaylar] == ["an_00001", "an_00002"]
    assert [o["sira"] for o in olaylar] == sorted(o["sira"] for o in olaylar)


def test_gecmiste_kalan_kosul_her_turda_yeni_olay_acmaz(baglanti, fikstur, ayar, an):
    """A latched condition stays one episode, however old the event itself is.

    Regression test for a real bug. Hysteresis used to be measured on
    `son_gorulme`, which is a *measurement* time — so an arc that tripped forty
    minutes ago, still sitting in the six-hour evaluation window and still found
    on every turn, was already "older than the 30-minute hysteresis" the moment
    it opened. It closed on the same turn that opened it, re-opened on the next,
    and would have produced one anomaly row per turn for as long as the event
    stayed in the window: ~2,000 rows for a single arc at a 10 s period, which is
    exactly the failure section 6.2 describes.

    The fix is `son_dogrulama`: hysteresis measures when the *detector* last
    confirmed the condition, not when the grid misbehaved.
    """
    modul_id = fikstur.modul("TR052-P02-M1")
    fikstur.yaz()
    depo = OlayDeposu(baglanti, ayar)

    # The event itself is well outside the hysteresis window...
    olay_zamani = an - timedelta(minutes=40)
    assert (an - olay_zamani).total_seconds() > ayar.olay.histerezis_sn

    # ...but the detector keeps finding it, turn after turn.
    for i in range(20):
        tur_ani = an + timedelta(seconds=10 * i)
        depo.uygula(
            modul_id,
            [_bulgu(olay_zamani, Seviye.KRITIK, 1.0, tip=Tip.ARK,
                    gerekce="Ark koruma cihazı 1 olay kaydetti.")],
            tur_ani,
        )
        depo.kapat_sureli(tur_ani)
    baglanti.commit()

    olaylar = _olaylar(baglanti, modul_id)
    assert len(olaylar) == 1, (
        "a condition still being found must stay one open episode, not one per turn"
    )
    assert olaylar[0]["durum"] == Durum.ACIK.value
    assert olaylar[0]["ilk_gorulme"] == olay_zamani, "the measurement time is unchanged"

    # Once the detector stops finding it, the hysteresis runs from that moment.
    son_tur = an + timedelta(seconds=190)
    depo.kapat_sureli(son_tur + timedelta(seconds=ayar.olay.histerezis_sn - 60))
    baglanti.commit()
    assert _olaylar(baglanti, modul_id)[0]["durum"] == Durum.ACIK.value

    depo.kapat_sureli(son_tur + timedelta(seconds=ayar.olay.histerezis_sn + 60))
    baglanti.commit()
    assert _olaylar(baglanti, modul_id)[0]["durum"] == Durum.KAPANDI.value
