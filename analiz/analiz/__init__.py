"""Grid Up — track B, the analysis layer.

Owns one question: how does an anomaly come out of the data? Reads the
measurement and thermal tables track A writes, and produces anomaly episodes the
dashboard and the alarm service read.

The layout follows the decision record (`docs/izb-karar-kaydi.md`):

    sozlesme.py   re-exports sozlesmeler/enums.py; B's own helpers only
    termal.py     the binary thermal frame codec
    ayar.py       every threshold and window — configuration, not constants
    db.py         connection; track A's migrations, then track B's
    depo.py       the scan cursor                              (K1)
    tarama.py     the scan loop                                (K1)
    pencere.py    the evaluation window fetcher
    dedektor/     the four layers, in order                    (K2)
    skor.py       magnitude -> (severity, score)
    gerekce.py    the sentence the operator reads
    olay.py       episode lifecycle and the journal            (K3)
    api.py        contract 5, the read API
    duman.py      smoke-test checks against a live API (track C calls it)
"""

from .ayar import Ayar
from .sozlesme import Durum, Kalite, OlcumTipi, Seviye, Tip

__all__ = ["Ayar", "Durum", "Kalite", "OlcumTipi", "Seviye", "Tip", "__version__"]

__version__ = "0.1.0"
