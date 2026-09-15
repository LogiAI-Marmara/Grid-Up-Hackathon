"""Robust statistics. No dependencies, no machine learning — section 4.1.

Why not mean and standard deviation, which the standard library already has:
section 2.2. One broken sensor reporting 500 C moves a mean and inflates a
standard deviation, and the module's baseline then stays wrong for as long as
that reading sits in the window. The median does not move and the MAD does not
inflate, so a single absurd sample costs nothing.

Everything here is a pure function over a sequence of floats. That is deliberate:
these are the pieces a jury is most likely to ask to see, and they are readable
on their own.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

__all__ = [
    "medyan",
    "mad",
    "robust_z",
    "egim",
    "NORMAL_TUTARLILIK",
]

#: 0.6745 is the 0.75 quantile of the standard normal. Dividing the MAD by it
#: makes the MAD an estimate of sigma for normally distributed data, so a robust
#: z is on the same scale as an ordinary z-score and thresholds like "3.5" keep
#: their usual meaning. Without it the two scales differ by ~1.48 and every
#: threshold in ayar.py would have to be silently rescaled.
NORMAL_TUTARLILIK = 0.6745


def medyan(degerler: Sequence[float]) -> float:
    """Middle value of the sorted sequence; mean of the middle two if even."""
    if not degerler:
        raise ValueError("medyan of an empty sequence")
    sirali = sorted(degerler)
    n = len(sirali)
    orta = n // 2
    if n % 2:
        return float(sirali[orta])
    return (float(sirali[orta - 1]) + float(sirali[orta])) / 2.0


def mad(degerler: Sequence[float], merkez: float | None = None) -> float:
    """Median absolute deviation: the median of |x - median(x)|.

    `merkez` lets a caller reuse a median it has already computed, which the
    baseline path does — it needs both numbers and computing the median twice
    over a fortnight of samples is pure waste.
    """
    if not degerler:
        raise ValueError("mad of an empty sequence")
    orta = medyan(degerler) if merkez is None else merkez
    return medyan([abs(float(d) - orta) for d in degerler])


def robust_z(deger: float, merkez: float, yayilim: float, asgari_yayilim: float) -> float:
    """Signed robust z-score of `deger` against a median/MAD baseline.

    `asgari_yayilim` is a floor on the MAD and it is not optional. A channel that
    sat at exactly 31.2 C for a fortnight has MAD 0, and every subsequent reading
    would then divide by zero — or, worse, produce an enormous z from a 0.1 C
    move and bury the operator in alarms. The floor is roughly one sensor
    quantisation step, and it is configuration (`katman2.asgari_mad`).
    """
    olcek = max(float(yayilim), float(asgari_yayilim))
    if olcek <= 0.0:
        return 0.0
    return NORMAL_TUTARLILIK * (float(deger) - float(merkez)) / olcek


def egim(x: Sequence[float], y: Sequence[float]) -> float:
    """Least-squares slope of y against x, in y-units per x-unit.

    Ordinary least squares, not a robust fit. The trend is computed over the
    *detection* window, which is short and has already been filtered by layer 0,
    so the outliers a robust regression would protect against have been removed
    upstream; and a plain slope is a number that can be explained to an operator
    in one sentence, which the `gerekce` requirement makes a real constraint.

    Returns 0.0 when the fit is undefined (fewer than two points, or every x
    identical) rather than raising: a channel with one sample has no trend, and
    that is a normal state at cold start, not an error.
    """
    n = len(x)
    if n < 2 or n != len(y):
        return 0.0
    x_ort = sum(x) / n
    y_ort = sum(y) / n
    pay = sum((xi - x_ort) * (yi - y_ort) for xi, yi in zip(x, y))
    payda = sum((xi - x_ort) ** 2 for xi in x)
    if payda <= 0.0 or math.isclose(payda, 0.0, abs_tol=1e-12):
        return 0.0
    return pay / payda
