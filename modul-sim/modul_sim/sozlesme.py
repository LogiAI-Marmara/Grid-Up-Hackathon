"""Loader for the shared contracts in `/sozlesmeler`.

The simulator must never restate a vocabulary: the enum values are the wire
contract and exist in exactly one file. `/sozlesmeler` is a sibling folder, not
an installed package, so this module puts the repository root on `sys.path`
once and re-exports the names the simulator uses. Everything imported here is
imported, never copied — if an enum changes, this package changes with it.
"""

from __future__ import annotations

import sys
from pathlib import Path

#: Repository root: modul-sim/modul_sim/sozlesme.py -> modul-sim/modul_sim -> modul-sim -> repo
KOK = Path(__file__).resolve().parents[2]

if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from sozlesmeler import enums  # noqa: E402
from sozlesmeler.enums import (  # noqa: E402
    OLCUM_ARALIK,
    OLCUM_BIRIM,
    TERMAL_BOLGE_SAYISI,
    TERMAL_PIKSEL,
    TERMAL_SATIR,
    TERMAL_SUTUN,
    Besleme,
    Birim,
    Kalite,
    ModulId,
    OlcumTipi,
    Seviye,
    Tip,
    indeks_piksel,
    modul_id_ayristir,
    modul_id_gecerli,
    piksel_indeks,
    zaman_oku,
    zaman_yaz,
)

#: Folder holding the JSON Schemas, so tests and the `--dogrula` flag can find them.
SEMA_KLASORU = KOK / "sozlesmeler"

__all__ = [
    "KOK",
    "SEMA_KLASORU",
    "enums",
    "OLCUM_ARALIK",
    "OLCUM_BIRIM",
    "TERMAL_BOLGE_SAYISI",
    "TERMAL_PIKSEL",
    "TERMAL_SATIR",
    "TERMAL_SUTUN",
    "Besleme",
    "Birim",
    "Kalite",
    "ModulId",
    "OlcumTipi",
    "Seviye",
    "Tip",
    "indeks_piksel",
    "modul_id_ayristir",
    "modul_id_gecerli",
    "piksel_indeks",
    "zaman_oku",
    "zaman_yaz",
]
