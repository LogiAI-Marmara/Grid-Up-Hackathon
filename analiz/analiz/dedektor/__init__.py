"""The four-layer detector.

Section 4.1: four layers, and no machine learning in the core. Section 4.3 gives
the reasons — synthetic training data would teach a model our own simulation
assumptions, `gerekce` could not be produced from a model score, and validating
a model against the distribution we generated ourselves proves nothing. A
difference layer could be added later without touching this structure; the core
detection is never wired to a model.
"""

from .motor import Degerlendirme, degerlendir
from .taban import Bulgu, KanalDurumu

__all__ = ["Bulgu", "KanalDurumu", "Degerlendirme", "degerlendir"]
