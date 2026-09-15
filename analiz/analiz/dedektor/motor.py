"""Runs the four layers in order and merges what they found.

Section 5: "the layers run in sequence. Each looks at a different fault class;
none replaces another." The order is not cosmetic —

  layer 0 first, because everything after it assumes the numbers are real. A
          channel it vetoes is invisible to layers 1-3, which is how a broken
          thermocouple becomes a maintenance ticket instead of a fire alarm.
  layer 1 next, baseline-free, so a hard safety limit is reported even when the
          module has no history to compare against.
  layer 2 then, needing the baseline layer 1 does not.
  layer 3 last, because it is the only layer allowed to take something back:
          it sees the other modules and can say "that was the weather".

Merging: several layers can produce the same `tip` — a terminal at 95 C trips
layer 1's absolute limit, layer 2's baseline, and layer 3's pixel comparison, all
truthfully. Three anomaly rows for one loose screw would be three work orders, so
per `tip` exactly one finding survives: worst severity first, then highest score,
then the later layer (its justification names a cause rather than a threshold).
Corroboration is not thrown away — it raises the score, bounded, in `skor_birlestir`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace

from ..ayar import Ayar
from ..pencere import Pencere
from ..skor import skor_birlestir
from ..sozlesme import SEVIYE_SIRA, Seviye, Tip
from . import katman0_sensor, katman1_mutlak, katman2_taban, katman3_iliski
from .katman3_iliski import Bastirma
from .taban import Bulgu, KanalDurumu

__all__ = ["Degerlendirme", "degerlendir"]

_gunluk = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Degerlendirme:
    """One module's verdict for one turn.

    Carries more than the surviving findings because the extras are what make a
    false positive diagnosable after the fact: which layer fired, what was
    suppressed and why, which channels layer 0 vetoed.
    """

    modul_id: str
    bulgular: tuple[Bulgu, ...] = ()
    kanal_durumu: KanalDurumu = field(default_factory=KanalDurumu)
    bastirma: Bastirma = field(default_factory=Bastirma)
    #: Every finding before merging and suppression, for diagnostics and tests.
    ham_bulgular: tuple[Bulgu, ...] = ()

    @property
    def tipler(self) -> frozenset[Tip]:
        return frozenset(b.tip for b in self.bulgular)

    def bulgu(self, tip: Tip) -> Bulgu | None:
        for b in self.bulgular:
            if b.tip is tip:
                return b
        return None


def degerlendir(pencere: Pencere, ayar: Ayar) -> Degerlendirme:
    """Run all four layers over one window and merge the result."""
    # --- layer 0: can veto channels for everyone downstream ------------------
    k0_bulgular, kanal_durumu = katman0_sensor.calistir(pencere, ayar)

    ham: list[Bulgu] = list(k0_bulgular)

    # --- layers 1-3 ----------------------------------------------------------
    k1_bulgular = katman1_mutlak.calistir(pencere, kanal_durumu, ayar)
    k2_bulgular = katman2_taban.calistir(pencere, kanal_durumu, ayar)
    k3_bulgular, bastirma = katman3_iliski.calistir(pencere, kanal_durumu, ayar)

    ham.extend(k1_bulgular)
    ham.extend(k2_bulgular)
    ham.extend(k3_bulgular)

    # --- suppression: layer 3 explaining away layer 2 ------------------------
    hayatta: list[Bulgu] = list(k0_bulgular) + list(k1_bulgular)
    for bulgu in k2_bulgular:
        if bulgu.tip in bastirma.tipler:
            _gunluk.debug(
                "suppressed layer-2 %s on %s: %s",
                bulgu.tip.value,
                pencere.modul_id,
                bastirma.sebep,
            )
            continue
        hayatta.append(bulgu)
    hayatta.extend(k3_bulgular)

    return Degerlendirme(
        modul_id=pencere.modul_id,
        bulgular=tuple(_ozgulluk(_birlestir(hayatta))),
        kanal_durumu=kanal_durumu,
        bastirma=bastirma,
        ham_bulgular=tuple(ham),
    )


def _birlestir(bulgular: list[Bulgu]) -> list[Bulgu]:
    """One surviving finding per `tip`, with corroboration folded into the score."""
    gruplar: dict[Tip, list[Bulgu]] = {}
    for bulgu in bulgular:
        gruplar.setdefault(bulgu.tip, []).append(bulgu)

    sonuc: list[Bulgu] = []
    for tip, grup in gruplar.items():
        kazanan = max(
            grup,
            key=lambda b: (SEVIYE_SIRA[b.seviye], b.skor, b.katman),
        )
        if len(grup) > 1:
            # Agreement between layers is evidence, so the score rises — but
            # bounded, and never across a severity boundary. Only a threshold in
            # ayar.py promotes a finding to kritik.
            birlesik = skor_birlestir([b.skor for b in grup])
            tavan = _seviye_tavani(kazanan.seviye)
            kazanan = replace(kazanan, skor=min(birlesik, tavan))
        sonuc.append(kazanan)

    # Worst first, so a caller that only looks at the head of the list sees the
    # thing that matters most.
    sonuc.sort(key=lambda b: (-SEVIYE_SIRA[b.seviye], -b.skor, b.tip.value))
    return sonuc


#: A diagnosed cause and the generic finding it explains. When layer 3 has
#: worked out *why* a terminal is hot, the bare "this is hot" finding is the same
#: fault described less usefully — and two episodes for one loose screw is two
#: work orders, which is the failure mode section 6.2 is about.
OZGUL_KAPSAM: dict[Tip, frozenset[Tip]] = {
    Tip.AKIM_SICAKLIK_SAPMASI: frozenset({Tip.SICAK_NOKTA}),
}


def _ozgulluk(bulgular: list[Bulgu]) -> list[Bulgu]:
    """Fold a generic finding into the more specific one that explains it.

    One loose terminal legitimately trips several tests: the hot spot is above a
    limit, it is outside the module's own band, and one pixel has pulled away
    from its frame. All true, all the same screw — and as separate episodes they
    are separate rows in the operator's list, separate acknowledgements, and
    separate work orders for one repair. That is the failure section 6.2 is about,
    arriving by a different route than duplicate rows per turn.

    Absorbing is not discarding. The surviving episode takes:

      - the *worse* of the two severities, so a hot spot that has also crossed an
        absolute safety limit stays critical. A diagnosis must never be able to
        quietly downgrade a limit that has already been passed.
      - the higher score,
      - the specific finding's justification, because "the load and the air do
        not account for this heat" tells a crew what to do and "it is hot" does
        not — and, when the absorbed finding is the more severe of the two, its
        sentence as well, since that is where the severity came from and the
        operator needs to see the reason for it.
    """
    mevcut = {b.tip: b for b in bulgular}
    dusur: set[Tip] = set()
    yerine: dict[Tip, Bulgu] = {}

    for ozgul, kapsanan in OZGUL_KAPSAM.items():
        ozgul_bulgu = mevcut.get(ozgul)
        if ozgul_bulgu is None:
            continue
        for tip in kapsanan:
            genel = mevcut.get(tip)
            if genel is None:
                continue
            dusur.add(tip)
            daha_agir = SEVIYE_SIRA[genel.seviye] > SEVIYE_SIRA[ozgul_bulgu.seviye]
            gerekce = ozgul_bulgu.gerekce
            if daha_agir:
                gerekce = f"{gerekce} Ayrıca: {genel.gerekce}"
            ozgul_bulgu = replace(
                ozgul_bulgu,
                seviye=genel.seviye if daha_agir else ozgul_bulgu.seviye,
                skor=max(ozgul_bulgu.skor, genel.skor),
                gerekce=gerekce[:1000],
                kanit={**ozgul_bulgu.kanit, "kapsanan": _kapsanan_kaniti(genel)},
            )
            _gunluk.debug("%s absorbed by the more specific %s", tip.value, ozgul.value)
        yerine[ozgul] = ozgul_bulgu

    sonuc = [yerine.get(b.tip, b) for b in bulgular if b.tip not in dusur]
    sonuc.sort(key=lambda b: (-SEVIYE_SIRA[b.seviye], -b.skor, b.tip.value))
    return sonuc


def _kapsanan_kaniti(bulgu: Bulgu) -> dict:
    """What the absorbed finding contributed, kept in the survivor's evidence."""
    return {
        "tip": bulgu.tip.value,
        "seviye": bulgu.seviye.value,
        "katman": bulgu.katman,
        "skor": bulgu.skor,
        "esik": bulgu.kanit.get("esik"),
        "olculen": bulgu.kanit.get("olculen"),
    }


def _seviye_tavani(seviye: Seviye) -> float:
    """Top of a severity's score band — the corroboration bonus may not cross it."""
    from ..skor import SEVIYE_SKOR_TABANI

    return SEVIYE_SKOR_TABANI[seviye][1]
