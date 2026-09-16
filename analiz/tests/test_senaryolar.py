"""End to end: the seven fault scenarios, against a real database and the real loop.

These run over the session-scoped `senaryo_vt` — the whole scenario set written
into PostgreSQL, then scanned by the same `Tarayici` that would run in
production. Nothing is stubbed. The success criteria for this delivery are
stated here as assertions:

  - each of the seven scenarios produces an episode of the right `tip`
  - clean modules produce nothing at all
  - sensor failures come out as `sensor_arizasi`, not as temperature anomalies
  - every episode carries a `gerekce` with real numbers in it
"""

from __future__ import annotations

import re

import pytest

from analiz.senaryolar import SENARYOLAR
from analiz.sozlesme import Tip


def _olaylar(baglanti, modul_id):
    with baglanti.cursor() as imlec:
        imlec.execute(
            "SELECT * FROM gridup.anomali WHERE modul_id = %s ORDER BY sira", (modul_id,)
        )
        return imlec.fetchall()


# --------------------------------------------------------------------------
# The seven scenarios
# --------------------------------------------------------------------------

_HEDEFLER = [s for s in SENARYOLAR if s.beklenen]


@pytest.mark.parametrize("senaryo", _HEDEFLER, ids=[s.ad for s in _HEDEFLER])
def test_senaryo_dogru_tipte_olay_uretir(senaryo, senaryo_vt):
    """Every injected fault produces an episode, and of the right type."""
    baglanti, _, _ = senaryo_vt
    uretilen = {Tip(o["tip"]) for o in _olaylar(baglanti, senaryo.modul_id)}

    eksik = senaryo.beklenen - uretilen
    assert not eksik, (
        f"{senaryo.ad} ({senaryo.modul_id}): missing "
        f"{sorted(t.value for t in eksik)}; produced {sorted(t.value for t in uretilen)}"
    )


@pytest.mark.parametrize(
    "senaryo",
    [s for s in _HEDEFLER if s.yasak],
    ids=[s.ad for s in _HEDEFLER if s.yasak],
)
def test_sensor_arizasi_sicaklik_anomalisi_olarak_bildirilmez(senaryo, senaryo_vt):
    """A broken sensor never comes out as a grid fault.

    Section 5's justification for putting layer 0 first, asserted directly. Both
    scenario 6 modules report temperatures that would be alarming if they were
    real — 150 C, and a hot spot stuck at 78 C — and in both cases the correct
    output is a maintenance ticket for the sensor, not a crew sent to a panel
    that is fine.
    """
    baglanti, _, _ = senaryo_vt
    uretilen = {Tip(o["tip"]) for o in _olaylar(baglanti, senaryo.modul_id)}

    ihlal = senaryo.yasak & uretilen
    assert not ihlal, (
        f"{senaryo.ad}: a sensor failure was reported as "
        f"{sorted(t.value for t in ihlal)}"
    )


# --------------------------------------------------------------------------
# The negatives — the half of the set that makes the other half mean something
# --------------------------------------------------------------------------

_TEMIZLER = [s for s in SENARYOLAR if not s.beklenen]


@pytest.mark.parametrize("senaryo", _TEMIZLER, ids=[s.ad for s in _TEMIZLER])
def test_temiz_modul_hicbir_olay_uretmez(senaryo, senaryo_vt):
    """A healthy module produces no episode at all — not even `izle`.

    Section 4.4's first trap: without clean modules in the set, a detector that
    alarms on everything scores a perfect detection rate and the false-alarm rate
    cannot be computed. This covers the genuinely quiet modules, the noisy but
    healthy ones, and the whole site warming up together on a hot afternoon.
    """
    baglanti, _, _ = senaryo_vt
    olaylar = _olaylar(baglanti, senaryo.modul_id)

    assert not olaylar, (
        f"{senaryo.ad} ({senaryo.modul_id}) is healthy but produced "
        + "; ".join(f"{o['tip']}/{o['seviye']}: {o['gerekce'][:90]}" for o in olaylar)
    )


def test_ortak_isinma_katman3_tarafindan_elenir(senaryo_vt):
    """The summer-afternoon case: every module on the site warms, nobody is alarmed.

    Section 5 names this as the layer-3 claim — "in summer heat every panel warms
    and layer 2 alone produces an alarm downpour; the comparison removes it". All
    four TR085 modules leave their own baselines at once, so layer 2 does fire on
    each; what makes the site quiet is the comparison between them.
    """
    baglanti, _, _ = senaryo_vt
    ortak = [s.modul_id for s in SENARYOLAR if s.ad.startswith("ortak_isinma")]
    assert len(ortak) >= 3

    for modul_id in ortak:
        assert not _olaylar(baglanti, modul_id), (
            f"{modul_id}: fleet-wide warming must not raise an alarm per module"
        )


# --------------------------------------------------------------------------
# Contract 3's mandatory field
# --------------------------------------------------------------------------


def test_her_olayin_gerekcesi_gercek_sayilar_icerir(senaryo_vt):
    """`gerekce` is mandatory, non-empty, and quotes the numbers that produced it.

    Contract 3 makes the field mandatory, and section 4.2 explains why that one
    requirement decides the detection method: an operator who cannot see why an
    alarm fired stops trusting the system. "Model said 0.87" cannot be written
    here — which is most of the argument against putting a model in the core.

    So the assertion is not merely that the field is populated: it has to contain
    actual measured quantities, because that is what makes it checkable by the
    person reading it.
    """
    baglanti, _, _ = senaryo_vt
    with baglanti.cursor() as imlec:
        imlec.execute("SELECT id, modul_id, tip, gerekce FROM gridup.anomali ORDER BY sira")
        olaylar = imlec.fetchall()

    assert olaylar, "the scenario set must produce episodes"

    for olay in olaylar:
        gerekce = olay["gerekce"]
        assert gerekce and gerekce.strip(), f"{olay['id']}: gerekce is mandatory"
        assert len(gerekce) <= 1000, f"{olay['id']}: contract 3 caps gerekce at 1000 chars"

        sayilar = re.findall(r"\d+[.,]?\d*", gerekce)
        assert len(sayilar) >= 2, (
            f"{olay['id']} ({olay['tip']}): gerekce must quote real numbers, got {gerekce!r}"
        )
        # A unit or a physical quantity, not just bare digits.
        assert re.search(r"(°C|%|\bA\b|dBm|olay|saat|dakika|ölçüm)", gerekce), (
            f"{olay['id']} ({olay['tip']}): gerekce must name units — {gerekce!r}"
        )


def test_kanit_alani_sozlesmenin_ayirdigi_anahtarlari_korur(senaryo_vt):
    """`kanit` is open-ended, but the reserved keys keep their declared shapes.

    The contract leaves the object open because different detector types point at
    different evidence, but `kare_id`, `piksel`, `olcum_tipi`, `pencere`, `esik`
    and `olculen` are reserved and the dashboard may rely on them.
    """
    baglanti, _, _ = senaryo_vt
    with baglanti.cursor() as imlec:
        imlec.execute("SELECT id, tip, kanit FROM gridup.anomali WHERE kanit IS NOT NULL")
        olaylar = imlec.fetchall()
        imlec.execute("SELECT kare_id FROM gridup.termal_kare")
        kareler = {r["kare_id"] for r in imlec.fetchall()}

    assert olaylar
    for olay in olaylar:
        kanit = olay["kanit"]
        if "piksel" in kanit:
            sutun, satir = kanit["piksel"]
            # [sutun, satir] — x first, 32 columns by 24 rows.
            assert 0 <= sutun <= 31, f"{olay['id']}: sutun out of range"
            assert 0 <= satir <= 23, f"{olay['id']}: satir out of range"
        if "pencere" in kanit:
            bas, bit = kanit["pencere"]
            assert bas.endswith("Z") and bit.endswith("Z"), "UTC with a literal Z"
            assert bas < bit
        if "kare_id" in kanit:
            assert kanit["kare_id"] in kareler, (
                f"{olay['id']}: kanit.kare_id must point at a real frame"
            )


def test_dogrulama_raporu_dort_metrigi_verir(senaryo_vt):
    """The run as a whole: full detection, no false alarms, sensors separated."""
    _, rapor, _ = senaryo_vt

    assert rapor.tespit_orani == 1.0, "every injected scenario must be detected"
    assert rapor.yanlis_alarm == 0, "no episode may be raised on a healthy module"
    assert rapor.sensor_ayrimi, "no sensor failure may be reported as a grid fault"
    assert rapor.olay > 0 and rapor.gecis > 0
