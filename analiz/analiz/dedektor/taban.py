"""What a detector layer returns.

A layer is a pure function from a `Pencere` to a list of `Bulgu`. It touches no
database, opens no episode and decides nothing about lifecycle — that is
`olay.py`'s job. Keeping the layers pure is what lets the same history be
re-evaluated as many times as an algorithm change requires (section 3.4) and
what lets them be tested without PostgreSQL running.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..sozlesme import OlcumTipi, Seviye, Tip

__all__ = ["Bulgu", "KanalDurumu"]


@dataclass(frozen=True, slots=True)
class Bulgu:
    """One layer's verdict about one thing, at one instant.

    Not yet an anomaly record: several findings can carry the same `tip`, and the
    engine merges them before anything is written. `gerekce` is built here rather
    than later because only the layer that fired still has the numbers that
    explain why — reconstructing the sentence downstream means guessing.
    """

    tip: Tip
    seviye: Seviye
    skor: float
    #: 0, 1, 2 or 3 — which layer produced this. Kept because "which layer fired"
    #: is the first question asked of any false positive.
    katman: int
    gerekce: str
    zaman: datetime
    kanit: dict[str, Any] = field(default_factory=dict)
    #: Channel this is about, when it is about one. `None` for module-level
    #: findings such as silence.
    kanal: OlcumTipi | None = None

    def __post_init__(self) -> None:
        if self.seviye is Seviye.NORMAL:
            # A normal reading produces no row at all (section 2.4). A Bulgu with
            # seviye 'normal' would become an anomaly row asserting nothing is
            # wrong, so it is a programming error rather than a quiet no-op.
            raise ValueError("a Bulgu is never 'normal'; return no finding instead")
        if not self.gerekce.strip():
            raise ValueError("gerekce is mandatory and non-empty (contract 3)")
        if not 0.0 <= self.skor <= 1.0:
            raise ValueError(f"skor out of range: {self.skor}")


@dataclass(frozen=True, slots=True)
class KanalDurumu:
    """Layer 0's verdict on the channels, passed to layers 1-3.

    The whole reason layer 0 runs first: a broken sensor reads 0 or reads 500,
    and both look like anomalies to any layer that judges values. `bozuk` is the
    set of channels the later layers must not read. Section 5: "a broken sensor
    produces a sensor_arizasi record and the remaining layers are skipped *for
    that channel*" — for that channel, not for the module, so a dead humidity
    sensor does not blind the thermal detector.
    """

    bozuk: frozenset[OlcumTipi] = frozenset()

    def kullanilabilir(self, kanal: OlcumTipi) -> bool:
        return kanal not in self.bozuk

    def hepsi_kullanilabilir(self, kanallar: "tuple[OlcumTipi, ...]") -> bool:
        return all(k not in self.bozuk for k in kanallar)
