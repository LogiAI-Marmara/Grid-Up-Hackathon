"""Each of the seven scenarios must produce a signal a detector could act on.

This file is the track A / track B handshake, made executable. A scenario class
declares `belirti` (the discriminating signal) and `beklenen_tip` (the anomaly
type track B should raise); these tests measure the signal in the generated data
and assert that the scenario declares the matching `beklenen_tip`. If someone
weakens a scenario, or renames the type it is supposed to produce, a test fails
here rather than track B silently detecting nothing.

**Every fault is measured against a control run.** The same seed and window with
no scenario is generated alongside, and the assertions are about the *difference*
between the two. That matters because the underlying world moves on its own: the
evening load peak raises currents and cabinet temperature all by itself, so
"currents are higher at the end of the run" proves nothing. Comparing against the
control is what makes "the terminal got hotter while the current did not change"
a statement about the fault instead of a statement about the time of day.

The other claim checked here is conformance: every packet the generator emits
must satisfy `modul_paketi.schema.json`, because track B and track C build
against that file and not against this code.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache

import pytest

from modul_sim import Filo, KosuAyar, TermalAyar
from modul_sim.dogrulama import paket_hatalari
from modul_sim.senaryo import SENARYOLAR, senaryo_olustur
from modul_sim.sozlesme import TERMAL_PIKSEL, Besleme, Kalite, OlcumTipi, Tip, indeks_piksel, zaman_oku

# ---------------------------------------------------------------------------
# One fixed run per scenario, shared by every test
# ---------------------------------------------------------------------------

TOHUM = 4242
MODUL_SAYISI = 2
SURE_DK = 120.0
BASLANGIC = datetime(2026, 9, 14, 6, 0, 0, tzinfo=timezone.utc)
#: Healthy for the first 30 minutes, then a 60-minute ramp to full strength.
SENARYO_BAS_S = 1800.0
SENARYO_SURE_S = 3600.0

#: Windows the assertions compare. `ERKEN` is before the fault exists in either
#: run; `GEC` is after the ramp has finished, so the fault is at full strength.
ERKEN = (BASLANGIC, BASLANGIC + timedelta(minutes=20))
GEC = (BASLANGIC + timedelta(minutes=100), BASLANGIC + timedelta(minutes=120))

TERMAL = TermalAyar()
#: Pixels a hot spot may legitimately sit on: the terminal row.
KLEMENS_PIKSELLERI = {(sutun, TERMAL.klemens_satir) for sutun in TERMAL.klemens_sutunlar}


@lru_cache(maxsize=None)
def kosu(senaryo_ad: str | None) -> tuple[dict, ...]:
    """The reference run for one scenario (or the control, for `None`).

    Cached: eight runs of two modules over two hours is ~11 500 packets, and
    regenerating them per test would dominate the suite's runtime for no gain —
    the generator is deterministic, so the cached tuple is the same data a fresh
    run would produce.
    """
    ayar = KosuAyar(
        modul_sayisi=MODUL_SAYISI,
        sure_dk=SURE_DK,
        tohum=TOHUM,
        senaryo_ad=senaryo_ad,
        baslangic=BASLANGIC,
        senaryo_bas_s=SENARYO_BAS_S,
        senaryo_sure_s=SENARYO_SURE_S,
    )
    return tuple(Filo(ayar).paketler())


# ---------------------------------------------------------------------------
# Small measurement helpers
# ---------------------------------------------------------------------------


def _pencerede(zaman: str, pencere: tuple[datetime, datetime]) -> bool:
    an = zaman_oku(zaman)
    return pencere[0] <= an <= pencere[1]


def satirlar(
    paketler: tuple[dict, ...],
    tip: OlcumTipi,
    pencere: tuple[datetime, datetime] | None = None,
    modul_id: str | None = None,
) -> list[dict]:
    """Every measurement row of one type, optionally restricted to a window."""
    return [
        olcum
        for paket in paketler
        for olcum in paket["olcumler"]
        if olcum["olcum_tipi"] == tip.value
        and (pencere is None or _pencerede(olcum["zaman"], pencere))
        and (modul_id is None or olcum["modul_id"] == modul_id)
    ]


def degerler(paketler, tip, pencere=None, modul_id=None) -> list[float]:
    """The non-null values of one measurement type."""
    return [s["deger"] for s in satirlar(paketler, tip, pencere, modul_id) if s["deger"] is not None]


def ort(sayilar: list[float]) -> float:
    assert sayilar, "no samples in this window — the assertion would be meaningless"
    return sum(sayilar) / len(sayilar)


def faz_ortalamasi(paketler, pencere) -> float:
    """Mean of the three phase currents — the board's total load, per phase."""
    return ort(
        degerler(paketler, OlcumTipi.AKIM_L1, pencere)
        + degerler(paketler, OlcumTipi.AKIM_L2, pencere)
        + degerler(paketler, OlcumTipi.AKIM_L3, pencere)
    )


def faz_sapmasi(paketler, pencere) -> float:
    """(L1 - L3) as a fraction of the mean phase current: the imbalance signal."""
    l1 = ort(degerler(paketler, OlcumTipi.AKIM_L1, pencere))
    l3 = ort(degerler(paketler, OlcumTipi.AKIM_L3, pencere))
    return (l1 - l3) / faz_ortalamasi(paketler, pencere)


def notr_orani(paketler, pencere) -> float:
    """Neutral current relative to the phase mean. Non-zero even when healthy."""
    return ort(degerler(paketler, OlcumTipi.AKIM_NOTR, pencere)) / faz_ortalamasi(paketler, pencere)


def ozetler(paketler, pencere=None) -> list[dict]:
    return [
        paket["termal_ozet"]
        for paket in paketler
        if paket.get("termal_ozet") and (pencere is None or _pencerede(paket["zaman"], pencere))
    ]


def kareler(paketler) -> list[dict]:
    return [paket for paket in paketler if paket.get("termal_kare")]


def paketleri(paketler, pencere) -> list[dict]:
    return [paket for paket in paketler if _pencerede(paket["zaman"], pencere)]


def bekleniyor(senaryo_ad: str, *tipler: Tip) -> None:
    """Assert the scenario declares the anomaly type its signal implies.

    This is the actual contract check: the test measures a signal, names the
    `tip` a detector should raise for it, and the scenario must agree.
    """
    senaryo = senaryo_olustur(senaryo_ad)
    for tip in tipler:
        assert tip in senaryo.beklenen_tip, (
            f"{senaryo_ad} produces a {tip.value} signal but declares beklenen_tip="
            f"{[t.value for t in senaryo.beklenen_tip]}"
        )


# ---------------------------------------------------------------------------
# The registry itself
# ---------------------------------------------------------------------------


def test_yedi_senaryo_kayitli():
    """Section 7.6 lists seven scenarios. An eighth needs the lead's approval."""
    assert len(SENARYOLAR) == 7, sorted(SENARYOLAR)


@pytest.mark.parametrize("ad", sorted(SENARYOLAR))
def test_senaryo_kendini_tanitiyor(ad):
    """Every scenario must document its signal and the type it maps to."""
    senaryo = senaryo_olustur(ad)
    assert senaryo.ad == ad
    assert senaryo.baslik and senaryo.belirti
    assert senaryo.beklenen_tip, f"{ad} declares no beklenen_tip"
    for tip in senaryo.beklenen_tip:
        assert isinstance(tip, Tip)


def test_her_tip_bir_senaryodan_gelir():
    """Every anomaly type in the vocabulary must be reachable from some scenario.

    A `tip` no scenario can produce is a detector track B could never test.
    """
    uretilen = {tip for ad in SENARYOLAR for tip in senaryo_olustur(ad).beklenen_tip}
    assert uretilen == set(Tip), f"unreachable types: {sorted(t.value for t in set(Tip) - uretilen)}"


# ---------------------------------------------------------------------------
# Contract conformance
# ---------------------------------------------------------------------------


def _ornek_paketler(paketler: tuple[dict, ...], adim: int = 11) -> list[dict]:
    """A subsample that keeps the interesting packets.

    Full validation of every packet in all eight runs costs about a minute, which
    is a test suite nobody runs. Every packet carrying a full frame or a non-`iyi`
    reading is validated — those are the shapes with conditional rules — plus a
    regular stride through the rest, plus both ends of the run.
    """
    secilen = {id(p): p for p in paketler[:20] + paketler[-20:]}
    for i, paket in enumerate(paketler):
        ilginc = paket.get("termal_kare") or any(o["kalite"] != "iyi" for o in paket["olcumler"])
        if ilginc or i % adim == 0:
            secilen[id(paket)] = paket
    return list(secilen.values())


@pytest.mark.parametrize("ad", [None, *sorted(SENARYOLAR)])
def test_paketler_semaya_uygun(ad):
    """Generated packets satisfy `modul_paketi.schema.json` — normal and faulted.

    The faulted runs matter more than the healthy one: a scenario that pushed a
    value out of the contract's plausible range, or dropped a required field,
    would be rejected by the collector at the door.
    """
    paketler = kosu(ad)
    assert paketler
    for paket in _ornek_paketler(paketler):
        hatalar = paket_hatalari(paket)
        assert not hatalar, f"{ad}: {paket['modul_id']} {paket['zaman']}: {hatalar[:3]}"


def test_kare_gonderildiginde_ozet_karesiyle_tutarli():
    """`maks_konum` must point at the hottest pixel of the transmitted frame.

    The collector enforces this, and the operator's evidence view depends on it:
    a coordinate that does not match the image points at the wrong terminal.
    """
    paketler = kosu("gevsek_klemens")
    kare_paketleri = kareler(paketler)
    assert kare_paketleri, "the loose-terminal run attached no evidence frame"
    for paket in kare_paketleri:
        kare = paket["termal_kare"]
        ozet = paket["termal_ozet"]
        assert len(kare) == TERMAL_PIKSEL
        en_sicak = max(range(TERMAL_PIKSEL), key=kare.__getitem__)
        assert list(indeks_piksel(en_sicak)) == ozet["maks_konum"]
        assert abs(kare[en_sicak] - ozet["maks"]) <= 0.01


def test_normal_kosu_sakin():
    """The control run must look healthy: all frames present (unconditional policy), nothing suspect.

    Integration item 2: every packet attaches a full thermal frame regardless of health.
    """
    paketler = kosu(None)
    assert all(p.get("termal_kare") is not None for p in paketler), "unconditional policy: every packet must carry a full frame"
    kotu = [o for p in paketler for o in p["olcumler"] if o["kalite"] == Kalite.YOK.value]
    assert not kotu, "the healthy run reported missing values"
    assert all(p["modul_durum"]["besleme"] == Besleme.SEBEKE.value for p in paketler)
    # A few glitches are deliberate (GLITCH_OLASILIK), but they must stay rare.
    supheli = [o for p in paketler for o in p["olcumler"] if o["kalite"] == Kalite.SUPHELI.value]
    toplam = sum(len(p["olcumler"]) for p in paketler)
    assert len(supheli) / toplam < 0.01


def test_ayni_tohum_ayni_veri():
    """Same seed and same start time reproduce a run exactly.

    Without this, a detector that fails on a run cannot be debugged against it.
    """
    ayar = KosuAyar(modul_sayisi=2, sure_dk=5, tohum=99, baslangic=BASLANGIC, senaryo_ad="gevsek_klemens")
    assert list(Filo(ayar).paketler()) == list(Filo(ayar).paketler())


def test_ayni_sahadaki_moduller_ayni_havayi_gorur():
    """Modules in one site share the weather, so a divergence is the cabinet.

    Track B's neighbour comparison rests on this: if each module had its own
    private weather, "this module is warmer than the one next to it" would be
    noise rather than evidence.
    """
    filo = Filo(KosuAyar(modul_sayisi=2, sure_dk=10, tohum=7, baslangic=BASLANGIC))
    assert len({m.ayar.saha_kodu for m in filo.moduller}) == 1, "expected both modules in one site"
    idler = filo.modul_idler
    paketler = tuple(filo.paketler())
    birinci = ort(degerler(paketler, OlcumTipi.ORTAM_SICAKLIK, modul_id=idler[0]))
    ikinci = ort(degerler(paketler, OlcumTipi.ORTAM_SICAKLIK, modul_id=idler[1]))
    assert abs(birinci - ikinci) < 2.0, f"{birinci:.1f} vs {ikinci:.1f} °C in the same site"


# ---------------------------------------------------------------------------
# 1 — loose terminal
# ---------------------------------------------------------------------------


def test_gevsek_klemens_akim_sabit_tek_nokta_isiniyor():
    """The project's central claim: heat rises, current does not, one pixel moves.

    Three measurements, and all three are needed. The hot spot alone could be an
    overload; the flat current alone could be a quiet night; the pinned pixel is
    what says it is a joint and not the whole board.
    """
    senaryo, kontrol = kosu("gevsek_klemens"), kosu(None)

    sicaklik_artisi = ort(degerler(senaryo, OlcumTipi.TERMAL_MAKS, GEC)) - ort(
        degerler(kontrol, OlcumTipi.TERMAL_MAKS, GEC)
    )
    assert sicaklik_artisi > 15.0, f"hot spot only {sicaklik_artisi:.1f} °C above the control run"

    akim_orani = faz_ortalamasi(senaryo, GEC) / faz_ortalamasi(kontrol, GEC)
    assert 0.9 < akim_orani < 1.1, f"current moved by {akim_orani:.2f}x — this scenario must not change the load"

    # The cabinet air must barely move: if it followed the joint one-for-one there
    # would be nothing separating this from an overload.
    ortam_artisi = ort(degerler(senaryo, OlcumTipi.ORTAM_SICAKLIK, GEC)) - ort(
        degerler(kontrol, OlcumTipi.ORTAM_SICAKLIK, GEC)
    )
    assert ortam_artisi < 0.35 * sicaklik_artisi

    konumlar = [tuple(o["maks_konum"]) for o in ozetler(senaryo, GEC)]
    baskin = max(set(konumlar), key=konumlar.count)
    assert konumlar.count(baskin) / len(konumlar) > 0.8, f"hot pixel wandered: {set(konumlar)}"
    assert baskin in KLEMENS_PIKSELLERI, f"hot pixel {baskin} is not on the terminal row"

    assert kareler(senaryo), "no evidence frame was attached"
    bekleniyor("gevsek_klemens", Tip.SICAK_NOKTA)


# ---------------------------------------------------------------------------
# 2 — overload heating
# ---------------------------------------------------------------------------


def test_asiri_yuk_her_sey_birlikte_isiniyor():
    """Overload: the current rises, the whole board follows, the spread does not.

    The contrast with scenario 1 is the point — same thermal alarm, opposite
    current behaviour, and that is exactly what `akim_sicaklik_sapmasi` has to
    tell apart.
    """
    senaryo, kontrol = kosu("asiri_yuk"), kosu(None)

    akim_orani = faz_ortalamasi(senaryo, GEC) / faz_ortalamasi(kontrol, GEC)
    assert akim_orani > 1.4, f"load only rose {akim_orani:.2f}x"

    ortam_artisi = ort(degerler(senaryo, OlcumTipi.ORTAM_SICAKLIK, GEC)) - ort(
        degerler(kontrol, OlcumTipi.ORTAM_SICAKLIK, GEC)
    )
    assert ortam_artisi > 5.0, f"cabinet only {ortam_artisi:.1f} °C above control"

    # Everything warms together: the frame mean must move with the maximum, unlike
    # the loose terminal where only one pixel does.
    ort_artisi = ort(degerler(senaryo, OlcumTipi.TERMAL_ORT, GEC)) - ort(degerler(kontrol, OlcumTipi.TERMAL_ORT, GEC))
    maks_artisi = ort(degerler(senaryo, OlcumTipi.TERMAL_MAKS, GEC)) - ort(degerler(kontrol, OlcumTipi.TERMAL_MAKS, GEC))
    assert ort_artisi > 0.5 * maks_artisi, f"frame mean {ort_artisi:.1f} vs maximum {maks_artisi:.1f}"

    # The phases rise together, so the imbalance must stay where it was.
    assert abs(faz_sapmasi(senaryo, GEC) - faz_sapmasi(kontrol, GEC)) < 0.05

    bekleniyor("asiri_yuk", Tip.ASIRI_YUK, Tip.ORTAM_SICAKLIK_YUKSEK)


# ---------------------------------------------------------------------------
# 3 — phase imbalance
# ---------------------------------------------------------------------------


def test_faz_dengesizligi_notr_akimi_yukseliyor():
    """Load migrates between phases; the neutral carries the difference.

    The healthy board already has a standing imbalance and a third-harmonic
    neutral current, so both assertions are relative to the control: the
    interesting quantity is how far past normal the spread has gone.
    """
    senaryo, kontrol = kosu("faz_dengesizlik"), kosu(None)

    sapma, kontrol_sapma = faz_sapmasi(senaryo, GEC), faz_sapmasi(kontrol, GEC)
    assert kontrol_sapma < 0.10, f"the healthy board is already {kontrol_sapma:.2f} unbalanced"
    assert sapma > 0.25, f"L1-L3 spread only {sapma:.2f}"

    notr, kontrol_notr = notr_orani(senaryo, GEC), notr_orani(kontrol, GEC)
    assert notr > 2 * kontrol_notr, f"neutral {notr:.2f} vs healthy {kontrol_notr:.2f}"

    # Total load barely changes: current moved between phases, it was not added.
    toplam_orani = faz_ortalamasi(senaryo, GEC) / faz_ortalamasi(kontrol, GEC)
    assert 0.8 < toplam_orani < 1.2, f"total load moved {toplam_orani:.2f}x — that would be an overload"

    bekleniyor("faz_dengesizlik", Tip.FAZ_DENGESIZLIGI)


# ---------------------------------------------------------------------------
# 4 — humidity rise
# ---------------------------------------------------------------------------


def test_nem_yuksek_kabin_ciy_noktasina_yaklasiyor():
    """Humidity climbs and stays there, while the cabinet cools — not a dead sensor.

    `kalite` staying `iyi` is half the test: the same numbers with
    `kalite: supheli` would be scenario 6, and the two must not be confusable.
    """
    senaryo, kontrol = kosu("nem_yuksek"), kosu(None)

    nem_gec = degerler(senaryo, OlcumTipi.NEM, GEC)
    assert ort(nem_gec) > 70.0, f"humidity only reached {ort(nem_gec):.0f} %"
    assert max(nem_gec) > 85.0, f"humidity peaked at {max(nem_gec):.0f} %"
    assert ort(nem_gec) - ort(degerler(kontrol, OlcumTipi.NEM, GEC)) > 15.0

    # A wet cabinet is an open one, so it also runs colder than its neighbour
    # would — cooling toward the dew point is the condensation risk itself.
    assert ort(degerler(senaryo, OlcumTipi.ORTAM_SICAKLIK, GEC)) < ort(
        degerler(kontrol, OlcumTipi.ORTAM_SICAKLIK, GEC)
    )

    assert all(s["kalite"] == Kalite.IYI.value for s in satirlar(senaryo, OlcumTipi.NEM, GEC)), (
        "a humidity sensor failure would be scenario 6, not scenario 4"
    )
    bekleniyor("nem_yuksek", Tip.NEM_YUKSEK)


# ---------------------------------------------------------------------------
# 5 — arc event
# ---------------------------------------------------------------------------


def test_ark_olay_sayac_artiyor_ve_akim_cokuyor():
    """A TVOC-2 trip: a counter row, an evidence frame, and the breaker opening.

    The aftermath is as diagnostic as the trip. A lone `ark_olay` row could be a
    glitch; a trip followed by the load collapsing is a breaker that operated.
    """
    senaryo, kontrol = kosu("ark_olay"), kosu(None)

    ark_satirlari = satirlar(senaryo, OlcumTipi.ARK_OLAY)
    assert ark_satirlari, "no ark_olay row was ever emitted"

    for modul_id in {s["modul_id"] for s in ark_satirlari}:
        sayimlar = [s["deger"] for s in ark_satirlari if s["modul_id"] == modul_id]
        assert sayimlar == sorted(sayimlar), f"{modul_id}: trip counter went backwards: {sayimlar}"
        assert max(sayimlar) >= 2, f"{modul_id}: expected both trips, saw {sayimlar}"

    # The breaker opened, so the load is gone. This is the check that separates a
    # real arc from a noisy TVOC reading.
    assert faz_ortalamasi(senaryo, GEC) / faz_ortalamasi(kontrol, GEC) < 0.3

    # Evidence: a full frame must arrive with, or immediately after, the trip —
    # the thermal array is only sampled every other cycle, so "immediately" is
    # one sampling period, not the same instant.
    ilk_ark = zaman_oku(ark_satirlari[0]["zaman"])
    kare_zamanlari = [zaman_oku(p["zaman"]) for p in kareler(senaryo)]
    assert any(ilk_ark <= z <= ilk_ark + timedelta(seconds=60) for z in kare_zamanlari), (
        f"no evidence frame near the first trip at {ilk_ark:%H:%M:%S}; frames at "
        f"{[f'{z:%H:%M:%S}' for z in kare_zamanlari[:5]]}"
    )
    bekleniyor("ark_olay", Tip.ARK)


# ---------------------------------------------------------------------------
# 6 — sensor failure
# ---------------------------------------------------------------------------


def test_sensor_arizasi_kalite_alaniyla_gorunur():
    """Freeze, then nonsense, then nothing — and `kalite` says so at every stage.

    This is the scenario that justifies the `kalite` field existing. Without it,
    the frozen stage is indistinguishable from a stable cabinet and the final
    stage from a cabinet at 0 °C.
    """
    senaryo = kosu("sensor_ariza")
    bekleniyor("sensor_ariza", Tip.SENSOR_ARIZASI)

    for tip in (OlcumTipi.ORTAM_SICAKLIK, OlcumTipi.NEM):
        satir_listesi = satirlar(senaryo, tip)
        erken = [s for s in satir_listesi if _pencerede(s["zaman"], ERKEN)]
        assert all(s["kalite"] == Kalite.IYI.value for s in erken), f"{tip.value} was already suspect before the fault"

        supheli = [s for s in satir_listesi if s["kalite"] == Kalite.SUPHELI.value]
        assert supheli, f"{tip.value} never went suspect"
        assert all(s["deger"] is not None for s in supheli), "a suspect reading still carries a value"

        # Frozen stage: the same value repeated. A sensor that is merely stable
        # does not repeat to the last decimal for minutes on end.
        degerleri = [s["deger"] for s in supheli]
        assert max(degerleri.count(d) for d in set(degerleri)) >= 3, f"{tip.value} never froze"

        gec = [s for s in satir_listesi if _pencerede(s["zaman"], GEC)]
        assert gec, f"{tip.value} rows disappeared from the packet entirely"
        assert all(s["kalite"] == Kalite.YOK.value and s["deger"] is None for s in gec), (
            f"{tip.value} should end as kalite 'yok' with a null value"
        )

    # The failure is one chip on one bus: the currents and the thermal array are
    # unaffected, which is how a detector tells this from a real cabinet problem.
    for tip in (OlcumTipi.AKIM_L1, OlcumTipi.AKIM_L2, OlcumTipi.AKIM_L3, OlcumTipi.TERMAL_MAKS):
        assert all(s["kalite"] == Kalite.IYI.value for s in satirlar(senaryo, tip)), f"{tip.value} should stay healthy"


# ---------------------------------------------------------------------------
# 7 — module health
# ---------------------------------------------------------------------------


def test_modul_saglik_sessizce_olmuyor():
    """Mains lost, radio fading, clock drifting — and the module says so.

    The "we do not die silently" claim: the last thing the module does with its
    backup store is transmit the packet that explains why it is about to stop.
    """
    senaryo, kontrol = kosu("modul_saglik"), kosu(None)
    bekleniyor("modul_saglik", Tip.MODUL_SAGLIK)

    gec_paketler = paketleri(senaryo, GEC)
    assert all(p["modul_durum"]["besleme"] == Besleme.YEDEK.value for p in gec_paketler), (
        "supply never flipped to the supercapacitor"
    )
    assert all(p["modul_durum"]["besleme"] == Besleme.SEBEKE.value for p in paketleri(senaryo, ERKEN))

    erken_sinyal = ort([float(p["modul_durum"]["sinyal"]) for p in paketleri(senaryo, ERKEN)])
    gec_sinyal = ort([float(p["modul_durum"]["sinyal"]) for p in gec_paketler])
    assert erken_sinyal - gec_sinyal > 15.0, f"signal only faded {erken_sinyal - gec_sinyal:.0f} dBm"

    # Load shedding: heartbeat packets with no measurements at all. The schema
    # allows an empty `olcumler` precisely for this.
    assert any(not p["olcumler"] for p in gec_paketler), "the module never shed its measurement load"

    # Clock drift. The collector sees it as alindi_zaman - zaman; here the true
    # time is known, so it is measured directly against the control run.
    son_gercek = zaman_oku(kontrol[-1]["zaman"])
    son_modul = zaman_oku(senaryo[-1]["zaman"])
    kayma_s = (son_modul - son_gercek).total_seconds()
    assert kayma_s > 20.0, f"module clock only drifted {kayma_s:.0f} s"
