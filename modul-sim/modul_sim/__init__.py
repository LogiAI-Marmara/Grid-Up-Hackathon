"""Grid-Up track A — synthetic module simulator.

The package models the field side of the system: the world a cabinet sits in
(`fizik`), the 32x24 thermal array (`termal`), the firmware that samples them and
decides what to transmit (`modul`), the seven fault scenarios of section 7.6
(`senaryo`), every tunable number with the reason it has that value (`ayar`), and
the fleet loop that drives the whole thing tick by tick (`runner`).

Two rules hold across the package:

* The wire vocabulary is never restated here. `sozlesme` re-exports it from
  `/sozlesmeler/enums.py`, which is the single source of truth for all three
  tracks.
* Nothing outside the standard library is required to *generate* data. The
  optional `jsonschema` dependency is only used by `--dogrula` and the tests, so
  the generator still runs on a bare on-prem Python.

Typical use:

    python -m modul_sim --senaryo gevsek_klemens --modul 9 --sure 120 --cikti ndjson

or from Python:

    from modul_sim import KosuAyar, Filo

    for uretilen in Filo(KosuAyar(modul_sayisi=3, sure_dk=10)).kosu():
        print(uretilen.paket["modul_id"], uretilen.paket["zaman"])
"""

from __future__ import annotations

from .ayar import (
    EsikAyar,
    HavaAyar,
    KabinAyar,
    ModulAyar,
    OrneklemeAyar,
    SaglikAyar,
    SahaAyar,
    TermalAyar,
    YukAyar,
    modul_ayarlari,
    topoloji,
)
from .fizik import Hava, Kabin, Yuk, ciy_noktasi, ic_bagil_nem
from .modul import Modul, UretilenPaket
from .runner import VARSAYILAN_TOHUM, Filo, KosuAyar, KosuOzeti, PaylasilanHava
from .senaryo import SENARYOLAR, Baglam, Senaryo, senaryo_olustur
from .sozlesme import SEMA_KLASORU, Besleme, Birim, Kalite, OlcumTipi, Seviye, Tip
from .termal import TermalDizi, TermalOzet

__version__ = "1.0.0"

__all__ = [
    "__version__",
    # fleet
    "Filo",
    "KosuAyar",
    "KosuOzeti",
    "PaylasilanHava",
    "VARSAYILAN_TOHUM",
    # one module
    "Modul",
    "UretilenPaket",
    # world
    "Hava",
    "Kabin",
    "Yuk",
    "TermalDizi",
    "TermalOzet",
    "ciy_noktasi",
    "ic_bagil_nem",
    # scenarios
    "Senaryo",
    "SENARYOLAR",
    "Baglam",
    "senaryo_olustur",
    # settings
    "topoloji",
    "modul_ayarlari",
    "ModulAyar",
    "SahaAyar",
    "EsikAyar",
    "OrneklemeAyar",
    "HavaAyar",
    "YukAyar",
    "KabinAyar",
    "TermalAyar",
    "SaglikAyar",
    # contract re-exports, so a consumer never has to guess where they live
    "SEMA_KLASORU",
    "OlcumTipi",
    "Seviye",
    "Tip",
    "Kalite",
    "Besleme",
    "Birim",
]
