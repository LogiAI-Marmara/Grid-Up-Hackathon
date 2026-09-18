"""Layer 3 — relationships. The project's own technical claim (section 5).

The first three layers all judge a number against something: a quality flag, a
fixed limit, the channel's own history. This one judges a number against
*another number measured at the same time*, and that is what lets it see things
no single channel can:

    current vs temperature   current flat, temperature climbing -> the heat is
                             not coming from the load, so it is coming from
                             resistance. A loose terminal, in one comparison.
    phase vs phase           L1 and L3 steady, L2 heating -> one phase. A change
                             in the ambient or in total load moves all three and
                             cancels out here for free.
    neighbouring pixel       whole frame warmer -> the room. One pixel pulling
                             away from its own frame -> a joint.
    module vs module         the whole site warmed together -> the weather. One
                             module diverging -> that panel.

It is also the layer that *removes* false alarms rather than adding them. On a
hot afternoon every panel on the site warms up, layer 2 sees every module leave
its own band at once, and on its own it would produce an alarm per module — a
downpour, on the one day an operator is least able to check them. The
module-to-module comparison turns that into silence, because the finding is not
"this module is hot", it is "this module is hot *and its neighbours are not*".
That suppression is returned separately from the findings; see `Bastirma`.

NETA / Infraspection (section 9.2) call comparison against a similar component
the primary method, ahead of comparison against ambient. The phase-to-phase and
neighbouring-pixel tests are that method.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..ayar import Ayar
from ..gerekce import akim_sicaklik, faz_faz, komsu_piksel, modul_modul
from ..pencere import Pencere, Seri
from ..skor import esikle
from ..sozlesme import AKIM_FAZLARI, OlcumTipi, Seviye, Tip
from .istatistik import medyan
from .taban import Bulgu, KanalDurumu

__all__ = ["calistir", "Bastirma", "baskin_faz"]


@dataclass(frozen=True, slots=True)
class Bastirma:
    """Layer 2 findings this layer has explained away.

    Kept separate from the findings list, and never applied to layer 1: a fixed
    safety limit is not something a comparison gets to argue with. 130 C is
    critical whether or not the neighbours are hot too.
    """

    tipler: frozenset[Tip] = frozenset()
    sebep: str = ""

    def __bool__(self) -> bool:
        return bool(self.tipler)


def calistir(
    pencere: Pencere, durum: KanalDurumu, ayar: Ayar
) -> tuple[list[Bulgu], Bastirma]:
    """Relationship findings, plus anything they let us take back."""
    bulgular: list[Bulgu] = []

    piksel_bulgusu = _komsu_piksel(pencere, durum, ayar)
    if piksel_bulgusu is not None:
        bulgular.append(piksel_bulgusu)

    akim_bulgusu = _akim_sicaklik(pencere, durum, ayar)
    if akim_bulgusu is not None:
        bulgular.append(akim_bulgusu)

    faz_bulgusu = _faz_faz(pencere, durum, ayar)
    if faz_bulgusu is not None:
        bulgular.append(faz_bulgusu)

    modul_bulgusu, bastirma = _modul_modul(pencere, durum, ayar, yerel=piksel_bulgusu is not None)
    if modul_bulgusu is not None:
        bulgular.append(modul_bulgusu)

    return bulgular, bastirma


def _pencere_kaniti(pencere: Pencere) -> list[str]:
    return [
        pencere.tespit_bas.strftime("%Y-%m-%dT%H:%M:%SZ"),
        pencere.tespit_bit.strftime("%Y-%m-%dT%H:%M:%SZ"),
    ]


def _kare_kaniti(pencere: Pencere, kanit: dict) -> dict:
    if pencere.kare_id is not None:
        kanit["kare_id"] = pencere.kare_id
    if pencere.termal:
        kanit["piksel"] = pencere.termal[-1].piksel
    return kanit


# --------------------------------------------------------------------------
# current vs temperature — scenario 1, the loose terminal
# --------------------------------------------------------------------------


def _akim_sicaklik(pencere: Pencere, durum: KanalDurumu, ayar: Ayar) -> Bulgu | None:
    """Temperature rising by more than the load and the air can account for.

    This is the comparison the decision record works through end to end in
    section 5, and the one that turns a number into a work order. It is posed as
    an accounting rather than as "is the current flat?":

        measured rise  -  ambient's share  -  the load's share  =  unexplained

    WHY NOT "IS THE CURRENT FLAT?". Because over a six-hour window it never is.
    A panel's load follows a daily profile; asking for current steady to within
    10% means the test fires reliably at 4 a.m. and never in the afternoon, which
    is not a detector, it is a clock. The record's own example has the current
    moving 310 -> 308 A, and the real question it is asking is not whether the
    current held still but whether it moved *enough to explain the heat*.

    THE LOAD'S SHARE is computable rather than guessable. A joint dissipates
    I^2 * R, so its rise above ambient scales with the square of the current: at
    the start of the window the joint sat `yukselme_ilk` degrees above ambient at
    current `akim_ilk`, so at `akim_son` the same resistance would put it at
    `yukselme_ilk * (akim_son/akim_ilk)^2`. The difference is what the load
    explains. What is left needs R to have changed, and a connection whose
    resistance is rising is the definition of the fault.

    That makes the test work in both directions, which "flatness" cannot:

      - loose terminal: current barely moves, so it explains almost nothing and
        the whole rise is left unexplained. Fires.
      - genuine overload: current nearly doubles, I^2 explains more than the
        observed rise, the residual goes negative. Correctly silent — and it is
        layer 1's absolute limit that speaks for that panel, which is right,
        because the answer there is "shed load", not "tighten a screw".
    """
    k3 = ayar.katman3
    n = ayar.pencere.temsil_ornek
    if not durum.kullanilabilir(OlcumTipi.TERMAL_MAKS):
        return None

    sicaklik = pencere.seri(OlcumTipi.TERMAL_MAKS)
    ilk, son = sicaklik.ilk, sicaklik.son
    sicaklik_bas = sicaklik.baslangic(n)
    sicaklik_son = sicaklik.temsil(n)
    if ilk is None or son is None or sicaklik.sure_saat <= 0:
        return None
    if sicaklik_bas is None or sicaklik_son is None:
        return None

    artis = sicaklik_son - sicaklik_bas
    if artis < k3.sicaklik_artis_esigi:
        return None

    # The load has to be measured for "the load did not do this" to mean anything.
    faz = baskin_faz(pencere, durum)
    if faz is None:
        return None
    faz_tipi, faz_seri = faz
    akim_ilk = faz_seri.baslangic(n)
    akim_son = faz_seri.temsil(n)
    if akim_ilk is None or akim_son is None:
        return None
    if akim_ilk < k3.akim_asgari or akim_son < k3.akim_asgari:
        # Near no-load the ratio of two small noisy numbers can explain anything,
        # in either direction. Declining is better than a confident wrong answer.
        return None

    # Ambient's share. NOT optional, unlike an earlier version of this check.
    #
    # D3 fix (post-review): crediting the air with 0 C when the ambient channel
    # is simply missing or layer-0-vetoed is not conservative, it is wrong in
    # the dangerous direction. `ortam_farki = 0.0` looks like "assume the room
    # did not warm up", but it silently also removes ambient from
    # `yukselme_ilk` (the joint's rise above ambient at the start of the
    # window), which feeds the I^2 load-explanation term. For an extreme
    # current ratio (e.g. 300 -> 600 A on a pure overload with no ambient
    # sensor) that combination can make `aciklanamayan` swing kritik for a
    # module that is doing nothing but carrying its rated load — exactly the
    # false positive layer 3 exists to prevent, not manufacture. Reproduced in
    # tests/test_katmanlar.py::test_akim_sicaklik_ambient_missing_no_finding
    # (acceptance test A6) before this fix landed.
    #
    # Without ambient there is no accounting to do at all: the comparison is
    # "measured rise minus air's share minus load's share", and one term being
    # an invented zero rather than a measurement makes the whole equation
    # unreliable, not merely approximate. So: no ambient channel, or layer 0
    # vetoed it, and this check does not run — not "runs assuming 0 C".
    if not durum.kullanilabilir(OlcumTipi.ORTAM_SICAKLIK):
        return None
    ortam = pencere.seri(OlcumTipi.ORTAM_SICAKLIK)
    if ortam.bos:
        return None
    ortam_bas = ortam.baslangic(n)
    ortam_son = ortam.temsil(n)
    if ortam_bas is None or ortam_son is None:
        return None
    ortam_farki = ortam_son - ortam_bas

    # The load's share, from I^2 R.
    yukselme_ilk = sicaklik_bas - (ortam_bas if ortam_bas is not None else sicaklik_bas)
    yukselme_ilk = max(yukselme_ilk, 0.0)
    akim_orani = (akim_son / akim_ilk) ** 2
    yuk_aciklamasi = yukselme_ilk * (akim_orani - 1.0)

    aciklanamayan = artis - ortam_farki - yuk_aciklamasi

    seviye, skor = esikle(
        aciklanamayan,
        k3.aciklanamayan_izle,
        k3.aciklanamayan_uyari,
        k3.aciklanamayan_kritik,
    )
    if seviye is Seviye.NORMAL:
        return None

    esik = {
        Seviye.IZLE: k3.aciklanamayan_izle,
        Seviye.UYARI: k3.aciklanamayan_uyari,
        Seviye.KRITIK: k3.aciklanamayan_kritik,
    }[seviye]

    kanit = _kare_kaniti(
        pencere,
        {
            "olcum_tipi": OlcumTipi.TERMAL_MAKS.value,
            "pencere": _pencere_kaniti(pencere),
            "esik": round(esik, 3),
            "olculen": round(aciklanamayan, 3),
            "sicaklik_artisi": round(artis, 3),
            "ortam_farki": round(ortam_farki, 3),
            "yuk_aciklamasi": round(yuk_aciklamasi, 3),
            "akim_tipi": faz_tipi.value,
            "akim_ilk": round(akim_ilk, 2),
            "akim_son": round(akim_son, 2),
            "sure_saat": round(sicaklik.sure_saat, 3),
        },
    )

    return Bulgu(
        tip=Tip.AKIM_SICAKLIK_SAPMASI,
        seviye=seviye,
        skor=skor,
        katman=3,
        gerekce=akim_sicaklik(
            sicaklik_bas,
            sicaklik_son,
            sicaklik.sure_saat,
            _faz_adi(faz_tipi),
            akim_ilk,
            akim_son,
            ortam_farki,
            yuk_aciklamasi,
            aciklanamayan,
        ),
        zaman=son.zaman,
        kanal=OlcumTipi.TERMAL_MAKS,
        kanit=kanit,
    )


def baskin_faz(
    pencere: Pencere, durum: KanalDurumu
) -> tuple[OlcumTipi, Seri] | None:
    """The most heavily loaded usable phase — the one whose heat we would expect.

    The module reports one hot-spot temperature, not one per phase, so there is no
    way to attribute the heat to a specific phase from the data. The heaviest
    phase is the strongest candidate explanation, which makes rejecting it the
    strongest form of the argument: if even the busiest phase did not change, the
    load did not cause this.

    Public (not `_`-prefixed) because it is the fast path's definition of
    "which phase is the load"; kept exported for tests and for any future
    caller outside this module that needs the same notion at the fast path's
    own (6-hour) time scale. The slow path (`katman2_taban._yavas_baskin_faz`,
    decision D1) answers the same question over daily aggregates instead of
    raw samples and so has its own, structurally different, implementation —
    documented there.
    """
    en_iyi: tuple[OlcumTipi, Seri] | None = None
    en_yuksek = -1.0
    for faz in AKIM_FAZLARI:
        if not durum.kullanilabilir(faz):
            continue
        seri = pencere.seri(faz)
        azami = seri.azami
        if azami is None:
            continue
        if azami > en_yuksek:
            en_yuksek = azami
            en_iyi = (faz, seri)
    return en_iyi


def _faz_adi(olcum_tipi: OlcumTipi) -> str:
    return {
        OlcumTipi.AKIM_L1: "L1 akımı",
        OlcumTipi.AKIM_L2: "L2 akımı",
        OlcumTipi.AKIM_L3: "L3 akımı",
    }.get(olcum_tipi, olcum_tipi.value)


# --------------------------------------------------------------------------
# phase vs phase — scenario 3, seen as a comparison rather than a percentage
# --------------------------------------------------------------------------


def _faz_faz(pencere: Pencere, durum: KanalDurumu, ayar: Ayar) -> Bulgu | None:
    """One phase diverging from the median of the three, with the neutral as witness.

    Different from layer 1's imbalance percentage in two ways that matter: it is
    more sensitive, and it names the phase — which is the difference between
    "this panel is unbalanced" and "look at L2". Using the median of the three as
    the reference rather than the mean means the faulty phase does not drag the
    reference towards itself and mask its own deviation.
    """
    k3 = ayar.katman3
    if not durum.hepsi_kullanilabilir(AKIM_FAZLARI):
        return None

    degerler: dict[OlcumTipi, float] = {}
    zamanlar = []
    for faz in AKIM_FAZLARI:
        seri = pencere.seri(faz)
        son = seri.son
        deger = seri.temsil(ayar.pencere.temsil_ornek)
        if son is None or deger is None:
            return None
        degerler[faz] = deger
        zamanlar.append(son.zaman)

    orta = medyan(list(degerler.values()))
    if orta < ayar.katman1.faz_asgari_akim:
        return None

    faz_tipi, deger = max(degerler.items(), key=lambda kv: abs(kv[1] - orta))
    sapma = abs(deger - orta) / orta

    seviye, skor = esikle(sapma, k3.faz_sapma_izle, k3.faz_sapma_uyari, k3.faz_sapma_kritik)
    if seviye is Seviye.NORMAL:
        return None

    notr = None
    if durum.kullanilabilir(OlcumTipi.AKIM_NOTR):
        notr = pencere.seri(OlcumTipi.AKIM_NOTR).temsil(ayar.pencere.temsil_ornek)
        if notr is not None:
            # A genuine imbalance has to go somewhere: the difference returns
            # through the neutral. A neutral current that stayed near zero while
            # one phase "diverged" points at a current sensor, not at the panel.
            if notr < k3.notr_orani * orta:
                notr = None

    esik = {
        Seviye.IZLE: k3.faz_sapma_izle,
        Seviye.UYARI: k3.faz_sapma_uyari,
        Seviye.KRITIK: k3.faz_sapma_kritik,
    }[seviye]

    return Bulgu(
        tip=Tip.FAZ_DENGESIZLIGI,
        seviye=seviye,
        skor=skor,
        katman=3,
        gerekce=faz_faz(_faz_adi(faz_tipi).replace(" akımı", ""), deger, orta, sapma, notr),
        zaman=max(zamanlar),
        kanal=faz_tipi,
        kanit={
            "olcum_tipi": faz_tipi.value,
            "pencere": _pencere_kaniti(pencere),
            "esik": round(esik, 4),
            "olculen": round(sapma, 4),
            "faz_medyan": round(orta, 2),
            "akimlar": {f.value: round(v, 2) for f, v in degerler.items()},
            "akim_notr": round(notr, 2) if notr is not None else None,
        },
    )


# --------------------------------------------------------------------------
# neighbouring pixel — one joint, or the whole room
# --------------------------------------------------------------------------


def _komsu_piksel(pencere: Pencere, durum: KanalDurumu, ayar: Ayar) -> Bulgu | None:
    """How far the hot pixel has pulled away from its own frame.

    The module sends four quadrant means alongside the hot pixel precisely so this
    question can be answered without transmitting 768 values. The hot pixel minus
    the frame's own level is immune to everything that moves the whole frame — the
    weather, the time of day, the season — because those move the quadrants too.

    The stability requirement is the second half: a hot spot that wanders around
    the frame is reflection or a passing person. One that sits on the same pixel
    is bolted to something.
    """
    k3 = ayar.katman3
    if not pencere.termal:
        return None
    if not durum.kullanilabilir(OlcumTipi.TERMAL_MAKS):
        return None

    son = pencere.termal[-1]
    # Median divergence over the newest few frames, not the divergence in the
    # newest one. A single frame catching a reflection, a warm hand, or plain
    # sensor noise shows exactly the signature this test looks for — one pixel
    # far above its own quadrants — and judging one frame would turn every such
    # blip into a work order. Same rule as `Seri.temsil`, applied to frames.
    sonuncular = pencere.termal[-max(1, ayar.pencere.temsil_ornek):]
    ayrisma = medyan([o.ayrisma for o in sonuncular])

    seviye, skor = esikle(
        ayrisma, k3.piksel_ayrisma_izle, k3.piksel_ayrisma_uyari, k3.piksel_ayrisma_kritik
    )
    if seviye is Seviye.NORMAL:
        return None

    ayni = sum(
        1
        for o in pencere.termal
        if o.maks_sutun == son.maks_sutun and o.maks_satir == son.maks_satir
    )
    kararlilik = ayni / len(pencere.termal)
    if kararlilik < k3.piksel_kararlilik_orani:
        return None

    esik = {
        Seviye.IZLE: k3.piksel_ayrisma_izle,
        Seviye.UYARI: k3.piksel_ayrisma_uyari,
        Seviye.KRITIK: k3.piksel_ayrisma_kritik,
    }[seviye]

    kanit: dict = {
        "olcum_tipi": OlcumTipi.TERMAL_MAKS.value,
        "pencere": _pencere_kaniti(pencere),
        "esik": round(esik, 3),
        "olculen": round(ayrisma, 3),
        "kare_sayisi": len(sonuncular),
        "maks": round(son.maks, 2),
        "bolge_ort": [round(b, 2) for b in son.bolge_ort],
        "piksel": son.piksel,
        "kararlilik": round(kararlilik, 3),
    }
    if pencere.kare_id is not None:
        kanit["kare_id"] = pencere.kare_id

    return Bulgu(
        tip=Tip.SICAK_NOKTA,
        seviye=seviye,
        skor=skor,
        katman=3,
        gerekce=komsu_piksel(
            son.bolge_ortalamasi + ayrisma,
            son.bolge_ortalamasi,
            ayrisma,
            son.maks_sutun,
            son.maks_satir,
            kararlilik,
        ),
        zaman=son.zaman,
        kanal=OlcumTipi.TERMAL_MAKS,
        kanit=kanit,
    )


# --------------------------------------------------------------------------
# module vs module — the weather, or this panel
# --------------------------------------------------------------------------


def _modul_modul(
    pencere: Pencere, durum: KanalDurumu, ayar: Ayar, yerel: bool
) -> tuple[Bulgu | None, Bastirma]:
    """Compare this module's rise with its neighbours'.

    Two outcomes, and the second one is the more valuable:

      - this module rose and the others did not -> a finding, and a strong one,
        because the weather cannot be the explanation.
      - this module rose and so did the others -> *suppress* layer 2's thermal
        findings. It is a hot afternoon. Reporting it once per module is how a
        monitoring system teaches its operators to ignore it.

    `yerel` is the neighbouring-pixel verdict. If one pixel has provably pulled
    away from its own frame, no amount of agreement between modules explains it,
    so suppression is withheld. Sensors on different modules see different
    equipment; a frame's own quadrants see the same equipment as its hot pixel.
    """
    k3 = ayar.katman3
    bos = Bastirma()

    if not durum.kullanilabilir(OlcumTipi.TERMAL_MAKS):
        return None, bos

    n = ayar.pencere.temsil_ornek
    kendi = pencere.seri(OlcumTipi.TERMAL_MAKS)
    if kendi.ilk is None or kendi.son is None:
        return None, bos
    kendi_delta = kendi.delta_temsil(n)

    komsu_deltalar: list[float] = []
    for kanallar in pencere.komsular.values():
        komsu_seri = kanallar.get(OlcumTipi.TERMAL_MAKS)
        if komsu_seri is None or komsu_seri.bos or len(komsu_seri.gecerli_noktalar) < 2:
            continue
        komsu_deltalar.append(komsu_seri.delta_temsil(n))

    if len(komsu_deltalar) < k3.asgari_komsu:
        # Not enough peers for the comparison to mean anything. Crucially this
        # returns no suppression either: with nothing to compare against we
        # cannot claim the fleet moved together, so layer 2 keeps its finding.
        return None, bos

    komsu_medyan = medyan(komsu_deltalar)
    fark = kendi_delta - komsu_medyan
    kapsam = "sahada" if k3.komsu_kapsami == "saha" else "panoda"

    # --- the fleet moved together: take layer 2's thermal findings back ------
    if not yerel and kendi_delta > 0:
        birlikte = sum(
            1 for d in komsu_deltalar if abs(d - kendi_delta) <= k3.ortak_hareket_delta
        )
        if birlikte / len(komsu_deltalar) >= k3.ortak_hareket_orani:
            return None, Bastirma(
                tipler=frozenset({Tip.SICAK_NOKTA, Tip.ORTAM_SICAKLIK_YUKSEK}),
                sebep=(
                    f"aynı {kapsam}ki {len(komsu_deltalar)} modülün "
                    f"{birlikte} tanesi benzer şekilde ısındı "
                    f"(medyan {komsu_medyan:+.1f} °C, bu modül {kendi_delta:+.1f} °C); "
                    f"ortak kaynaklı ısınma"
                ),
            )

    # --- this module diverged -----------------------------------------------
    seviye, skor = esikle(
        fark, k3.modul_ayrisma_izle, k3.modul_ayrisma_uyari, k3.modul_ayrisma_kritik
    )
    if seviye is Seviye.NORMAL:
        return None, bos

    esik = {
        Seviye.IZLE: k3.modul_ayrisma_izle,
        Seviye.UYARI: k3.modul_ayrisma_uyari,
        Seviye.KRITIK: k3.modul_ayrisma_kritik,
    }[seviye]

    return (
        Bulgu(
            tip=Tip.SICAK_NOKTA,
            seviye=seviye,
            skor=skor,
            katman=3,
            gerekce=modul_modul(
                kendi_delta,
                komsu_medyan,
                len(komsu_deltalar),
                kapsam.removesuffix("da").removesuffix("de"),
                kendi.sure_saat,
            ),
            zaman=kendi.son.zaman,
            kanal=OlcumTipi.TERMAL_MAKS,
            kanit=_kare_kaniti(
                pencere,
                {
                    "olcum_tipi": OlcumTipi.TERMAL_MAKS.value,
                    "pencere": _pencere_kaniti(pencere),
                    "esik": round(esik, 3),
                    "olculen": round(fark, 3),
                    "kendi_delta": round(kendi_delta, 3),
                    "komsu_medyan": round(komsu_medyan, 3),
                    "komsu_sayisi": len(komsu_deltalar),
                },
            ),
        ),
        bos,
    )
