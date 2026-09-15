"""Turning a deviation into a score and a severity.

Two separate jobs, and the contract keeps them separate on purpose: `seviye` is
what the alarm service and the SCADA register map act on, and `skor` is only for
ranking inside a severity. A score is never allowed to decide a severity —
"the model said 0.87" is exactly the unexplainable output section 4.3 rejects.

Severity means a time horizon (section 2.4): izle is weeks, uyari is days,
kritik is hours or a hard safety limit already crossed. So the thresholds that
produce it are physical quantities in `ayar.py` — degrees, percent, degrees per
hour — and this module only does the arithmetic of comparing against them.
"""

from __future__ import annotations

from .sozlesme import Seviye

__all__ = ["esikle", "skor_birlestir", "SEVIYE_SKOR_TABANI"]

#: Score band each severity starts in. The bands are ordered and do not overlap,
#: so sorting a queue by score never puts an `izle` above a `uyari` — an operator
#: triaging by score sees the same order as one triaging by severity.
SEVIYE_SKOR_TABANI: dict[Seviye, tuple[float, float]] = {
    Seviye.NORMAL: (0.00, 0.30),
    Seviye.IZLE: (0.30, 0.55),
    Seviye.UYARI: (0.55, 0.80),
    Seviye.KRITIK: (0.80, 1.00),
}


def _oranla(deger: float, alt: float, ust: float) -> float:
    """Position of `deger` between `alt` and `ust`, clamped to 0..1."""
    genislik = ust - alt
    if genislik <= 0:
        return 1.0
    return min(1.0, max(0.0, (deger - alt) / genislik))


def esikle(
    deger: float, izle: float, uyari: float, kritik: float
) -> tuple[Seviye, float]:
    """Map a magnitude onto (severity, score) using three ascending thresholds.

    The single place a number becomes a severity. Every layer funnels through it,
    which is what stops each detector from inventing its own idea of what "uyari"
    means and makes the whole set re-tunable from `ayar.py` alone.

    Above `kritik` the score keeps rising but saturates: twice the critical limit
    is not twice as urgent, it is the same "go now" with a higher rank.
    """
    if not izle <= uyari <= kritik:
        raise ValueError(
            f"thresholds must ascend: izle={izle} uyari={uyari} kritik={kritik}"
        )

    if deger >= kritik:
        seviye = Seviye.KRITIK
        # Reference span for the tail is the uyari..kritik band, or the critical
        # limit itself when those coincide.
        span = (kritik - uyari) or abs(kritik) or 1.0
        oran = _oranla(deger, kritik, kritik + span)
    elif deger >= uyari:
        seviye = Seviye.UYARI
        oran = _oranla(deger, uyari, kritik)
    elif deger >= izle:
        seviye = Seviye.IZLE
        oran = _oranla(deger, izle, uyari)
    else:
        seviye = Seviye.NORMAL
        oran = _oranla(deger, min(0.0, izle), izle)

    alt, ust = SEVIYE_SKOR_TABANI[seviye]
    return seviye, round(alt + oran * (ust - alt), 4)


def skor_birlestir(skorlar: "list[float] | tuple[float, ...]") -> float:
    """Combined score when several layers agree on the same anomaly type.

    Agreement is evidence, so the result is at least the strongest single score,
    but corroboration is worth less than the difference between severities —
    hence a small bounded bonus rather than a sum. Two layers saying `uyari`
    never add up to `kritik`: only a threshold in `ayar.py` decides that.
    """
    if not skorlar:
        return 0.0
    en_yuksek = max(skorlar)
    if len(skorlar) == 1:
        return round(en_yuksek, 4)
    ikincil = sorted(skorlar, reverse=True)[1]
    return round(min(1.0, en_yuksek + 0.05 * ikincil), 4)
