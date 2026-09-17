"""The shared vocabularies, imported — and track B's own helpers on top of them.

`sozlesmeler/enums.py` at the repository root is the single source of every
contract vocabulary (`OlcumTipi`, `Seviye`, `Tip`, `Kalite`, `Durum`, `Besleme`,
`Birim`), the derived tables (`OLCUM_BIRIM`, `OLCUM_ARALIK`, `SEVIYE_SIRA`), the
frame geometry and the id/time helpers. This module re-exports them so the rest
of `/analiz` keeps importing from one place, and defines only what is specific
to the detector: which channels are currents, which are temperatures, and the
"worst of these severities" helper. No contract value is restated here.

HOW THE SHARED MODULE IS FOUND. `sozlesmeler` is a plain directory at the
repository root, importable whenever that root is on `sys.path` — which is the
case when track C composes the services from a checkout. When it is not (the
package installed on its own, or the test suite pointed at an exported copy of
track A's files), `GRIDUP_SOZLESMELER_KOK` names the directory that *contains*
`sozlesmeler/`; failing that, the repository root is derived from this file's
location. Nothing is vendored: an unfindable contract is an error, not a
fallback to a private copy.

Identifiers that mirror the contract are Turkish because they are on the wire
(`olcum_tipi`, `seviye`, `tip`, `kalite`, `durum`). Comments are English.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import ModuleType

__all__ = [
    "OlcumTipi",
    "Seviye",
    "Tip",
    "Kalite",
    "Durum",
    "Besleme",
    "Birim",
    "OLCUM_BIRIM",
    "OLCUM_ARALIK",
    "SEVIYE_SIRA",
    "TERMAL_SATIR",
    "TERMAL_SUTUN",
    "TERMAL_PIKSEL",
    "TERMAL_BOLGE_SAYISI",
    "AKIM_FAZLARI",
    "SICAKLIK_KANALLARI",
    "MODUL_ID_DESEN",
    "ModulId",
    "modul_id_ayristir",
    "zaman_yaz",
    "zaman_oku",
    "piksel_indeks",
    "indeks_piksel",
    "seviye_karsilastir",
    "en_yuksek_seviye",
    "SOZLESMELER_KOK_ORTAM",
]

#: Environment variable naming the directory that contains `sozlesmeler/`.
SOZLESMELER_KOK_ORTAM = "GRIDUP_SOZLESMELER_KOK"


def _sozlesmeleri_yukle() -> ModuleType:
    """Import `sozlesmeler.enums`, adding the repository root to the path if needed."""
    try:
        from sozlesmeler import enums  # type: ignore[import-not-found]

        return enums
    except ImportError:
        pass

    kok = os.environ.get(SOZLESMELER_KOK_ORTAM) or str(Path(__file__).resolve().parents[2])
    if kok not in sys.path:
        sys.path.insert(0, kok)
    try:
        from sozlesmeler import enums  # type: ignore[import-not-found]
    except ImportError as hata:
        raise ImportError(
            f"sozlesmeler/enums.py not found under {kok!r}; set {SOZLESMELER_KOK_ORTAM} "
            "to the directory containing sozlesmeler/ (track A's PR puts it at the "
            "repository root)"
        ) from hata
    return enums


_enums = _sozlesmeleri_yukle()

OlcumTipi = _enums.OlcumTipi
Seviye = _enums.Seviye
Tip = _enums.Tip
Kalite = _enums.Kalite
Durum = _enums.Durum
Besleme = _enums.Besleme
Birim = _enums.Birim
OLCUM_BIRIM = _enums.OLCUM_BIRIM
OLCUM_ARALIK = _enums.OLCUM_ARALIK
SEVIYE_SIRA = _enums.SEVIYE_SIRA
TERMAL_SATIR = _enums.TERMAL_SATIR
TERMAL_SUTUN = _enums.TERMAL_SUTUN
TERMAL_PIKSEL = _enums.TERMAL_PIKSEL
TERMAL_BOLGE_SAYISI = _enums.TERMAL_BOLGE_SAYISI
MODUL_ID_DESEN = _enums.MODUL_ID_DESEN
ModulId = _enums.ModulId
modul_id_ayristir = _enums.modul_id_ayristir
zaman_yaz = _enums.zaman_yaz
zaman_oku = _enums.zaman_oku
piksel_indeks = _enums.piksel_indeks
indeks_piksel = _enums.indeks_piksel
seviye_karsilastir = _enums.seviye_karsilastir


# Values track B writes must exist in the shared vocabulary, or a consumer
# validating against it will reject rows this detector produced. Checked at
# import so the mismatch is one clear message and not a CHECK violation at 3 a.m.
_GEREKLI_TIPLER = ("asiri_yuk",)
_eksik = [t for t in _GEREKLI_TIPLER if t not in {e.value for e in Tip}]
if _eksik:
    raise ImportError(
        f"sozlesmeler.enums.Tip lacks {_eksik}; apply the integration follow-up "
        "(add `ASIRI_YUK = \"asiri_yuk\"` to Tip in sozlesmeler/enums.py)"
    )


# --------------------------------------------------------------------------
# Track B's own helpers. Nothing below restates a contract value.
# --------------------------------------------------------------------------

#: The three line currents, in the order a phase-to-phase comparison reports them.
AKIM_FAZLARI: tuple[OlcumTipi, ...] = (
    OlcumTipi.AKIM_L1,
    OlcumTipi.AKIM_L2,
    OlcumTipi.AKIM_L3,
)

#: Channels measured in Celsius. Layer 2's baseline and layer 3's comparisons
#: both need to know which channels are temperatures and which are not.
SICAKLIK_KANALLARI: tuple[OlcumTipi, ...] = (
    OlcumTipi.TERMAL_MAKS,
    OlcumTipi.TERMAL_ORT,
    OlcumTipi.ORTAM_SICAKLIK,
)


def en_yuksek_seviye(seviyeler: "list[Seviye] | tuple[Seviye, ...]") -> Seviye:
    """Worst severity in the collection; `normal` for an empty one."""
    if not seviyeler:
        return Seviye.NORMAL
    return max(seviyeler, key=lambda s: SEVIYE_SIRA[Seviye(s)])
