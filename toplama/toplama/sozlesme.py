"""Loader for the shared contracts in `/sozlesmeler`.

The collector is the door to the database, so it is the one service that must
agree with the contract exactly. It therefore imports the vocabularies instead
of restating them: `enums.py` is the single source of truth for all three tracks
(section 10 of the decision record), and the JSON Schemas next to it are what
`POST /paket` validates against.

`/sozlesmeler` is a sibling folder rather than an installed package, so this
module puts the repository root on `sys.path` once and re-exports what the
service uses. The Docker image keeps the same layout (`/app/toplama`,
`/app/sozlesmeler`), so the path arithmetic holds inside the container too.
"""

from __future__ import annotations

import sys
from pathlib import Path

#: Repository root: toplama/toplama/sozlesme.py -> toplama/toplama -> toplama -> repo
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
    indeks_piksel,
    modul_id_ayristir,
    modul_id_gecerli,
    piksel_indeks,
    zaman_oku,
    zaman_yaz,
)

#: Folder holding the JSON Schemas that `POST /paket` enforces.
SEMA_KLASORU = KOK / "sozlesmeler"

#: Folder holding the SQL migrations, so the README and the health endpoint can
#: point at the schema this service was built against.
GOC_KLASORU = Path(__file__).resolve().parents[1] / "migrations"

__all__ = [
    "KOK",
    "SEMA_KLASORU",
    "GOC_KLASORU",
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
    "indeks_piksel",
    "modul_id_ayristir",
    "modul_id_gecerli",
    "piksel_indeks",
    "zaman_oku",
    "zaman_yaz",
]
