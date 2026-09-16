"""The 32x24 thermal array: field synthesis and the on-board summary.

Frame model, from the outside in:

    frame = cabinet air
          + convection gradient (the top of a cabinet is warmer)
          + busbar band (a horizontal warm band across the terminal row)
          + one Gaussian blob per terminal, scaled by I²
          + fixed pattern noise (per pixel, constant for the life of a sensor)
          + temporal noise (per pixel, per frame)

The two noise terms are separate on purpose. Fixed pattern noise is what makes
one sensor's frame not look like another's, and it does not average out over
time — a detector that learns "pixel 412 reads 0.4 °C high" is learning the
sensor, not the panel. Temporal noise does average out, which is what makes
multi-frame confirmation worth doing. Collapsing them into one number would
hide both effects.

`ozet()` is the on-board reduction from section 7.4: 768 values in, three
numbers plus a coordinate out. Normal traffic carries only that.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .ayar import TermalAyar
from .sozlesme import (
    TERMAL_BOLGE_SAYISI,
    TERMAL_PIKSEL,
    TERMAL_SATIR,
    TERMAL_SUTUN,
    indeks_piksel,
    piksel_indeks,
)


@dataclass(frozen=True)
class TermalOzet:
    """What the module derives on board and sends in normal operation."""

    maks: float
    maks_konum: tuple[int, int]  # [sutun, satir] — x first, per the contract
    bolge_ort: tuple[float, float, float, float]
    ortalama: float  # frame mean, reported as olcum_tipi termal_ort


class TermalDizi:
    """Per-module thermal array model. One instance per simulated sensor."""

    def __init__(self, ayar: TermalAyar, rng: random.Random) -> None:
        self.ayar = ayar
        self._rng = rng

        satir, sutun = ayar.satir, ayar.sutun
        if (satir, sutun) != (TERMAL_SATIR, TERMAL_SUTUN):
            raise ValueError(
                f"frame geometry {sutun}x{satir} does not match the contract's {TERMAL_SUTUN}x{TERMAL_SATIR}"
            )

        # --- static per-pixel terms, computed once -------------------------
        # Convection gradient plus this sensor's fixed pattern noise.
        self._sabit: list[float] = [0.0] * TERMAL_PIKSEL
        # Busbar band: load-scaled, so it is kept as a separate weight map.
        self._bara: list[float] = [0.0] * TERMAL_PIKSEL
        for indeks in range(TERMAL_PIKSEL):
            _, s = indeks_piksel(indeks)
            egim = ayar.egim_c * (1.0 - s / max(satir - 1, 1))
            self._sabit[indeks] = egim + rng.gauss(0.0, ayar.fpn_c)
            self._bara[indeks] = math.exp(-0.5 * ((s - ayar.klemens_satir) / ayar.bara_sigma) ** 2)

        # --- terminal blobs ------------------------------------------------
        # Each terminal is a Gaussian kernel over a small window. Precomputing
        # the (index, weight) pairs keeps a frame at a few thousand float ops,
        # which is what makes a 100-module load test finish in a coffee break.
        self._klemens_cekirdek: list[list[tuple[int, float]]] = []
        self._klemens_kazanc: list[float] = []
        yaricap = max(int(3 * ayar.klemens_sigma), 2)
        for merkez_sutun in ayar.klemens_sutunlar:
            cekirdek: list[tuple[int, float]] = []
            for ds in range(-yaricap, yaricap + 1):
                for dc in range(-yaricap, yaricap + 1):
                    s = ayar.klemens_satir + ds
                    c = merkez_sutun + dc
                    if not (0 <= s < satir and 0 <= c < sutun):
                        continue
                    agirlik = math.exp(-0.5 * (ds * ds + dc * dc) / (ayar.klemens_sigma**2))
                    if agirlik < 0.02:
                        continue
                    cekirdek.append((piksel_indeks(c, s), agirlik))
            self._klemens_cekirdek.append(cekirdek)
            # Terminals are not identical: torque, contact area and ageing all
            # differ, so each one runs a little hotter or cooler than its
            # neighbours even when every one of them is healthy.
            self._klemens_kazanc.append(
                ayar.klemens_tam_yuk_c * (1.0 + rng.uniform(-ayar.klemens_dagilim, ayar.klemens_dagilim))
            )

        # --- temporal noise pool -------------------------------------------
        # Drawing 768 gaussians per frame dominates the runtime and buys
        # nothing: a pre-drawn pool read at a rotating offset is statistically
        # indistinguishable here and about twenty times cheaper. The offset
        # advances by a co-prime stride so the pattern does not repeat frame to
        # frame.
        self._havuz = [rng.gauss(0.0, ayar.gurultu_c) for _ in range(ayar.havuz_boyu)]
        self._havuz_ofset = rng.randrange(ayar.havuz_boyu)

    @property
    def klemens_sayisi(self) -> int:
        return len(self._klemens_kazanc)

    def klemens_konumu(self, sira: int) -> tuple[int, int]:
        """`[sutun, satir]` of terminal `sira` — what a hot spot should land on."""
        return (self.ayar.klemens_sutunlar[sira % self.klemens_sayisi], self.ayar.klemens_satir)

    def kare(
        self,
        kabin_sicaklik_c: float,
        yuk_katsayisi: float,
        klemens_ek_c: list[float] | None = None,
        genel_ek_c: float = 0.0,
    ) -> list[float]:
        """Build one 768-value frame, row-major.

        `klemens_ek_c` adds degrees to individual terminals (scenario 1, the
        loose one), `genel_ek_c` warms the whole frame (scenario 5's flash).
        """
        a = self.ayar
        yuk2 = yuk_katsayisi * yuk_katsayisi
        bara = a.bara_bant_c * yuk2
        taban = kabin_sicaklik_c + genel_ek_c
        kare = [taban + sabit + bara * agirlik for sabit, agirlik in zip(self._sabit, self._bara)]

        for sira, cekirdek in enumerate(self._klemens_cekirdek):
            genlik = self._klemens_kazanc[sira] * yuk2
            if klemens_ek_c:
                genlik += klemens_ek_c[sira]
            if abs(genlik) < 0.01:
                continue
            for indeks, agirlik in cekirdek:
                kare[indeks] += genlik * agirlik

        havuz = self._havuz
        boy = len(havuz)
        ofset = self._havuz_ofset
        for i in range(TERMAL_PIKSEL):
            kare[i] += havuz[(ofset + i) % boy]
        # 769 is prime and larger than the frame, so consecutive frames never
        # reuse the same slice of the pool.
        self._havuz_ofset = (ofset + 769) % boy

        return kare

    @staticmethod
    def ozet(kare: list[float]) -> TermalOzet:
        """Reduce a frame to what goes on the wire in normal operation."""
        if len(kare) != TERMAL_PIKSEL:
            raise ValueError(f"frame must hold {TERMAL_PIKSEL} values, got {len(kare)}")

        maks_indeks = max(range(TERMAL_PIKSEL), key=kare.__getitem__)
        sutun, satir = indeks_piksel(maks_indeks)

        # Four 16x12 quadrants in contract order: top-left, top-right,
        # bottom-left, bottom-right.
        toplamlar = [0.0] * TERMAL_BOLGE_SAYISI
        sayilar = [0] * TERMAL_BOLGE_SAYISI
        for indeks, deger in enumerate(kare):
            c, s = indeks % TERMAL_SUTUN, indeks // TERMAL_SUTUN
            bolge = (0 if s < TERMAL_SATIR // 2 else 2) + (0 if c < TERMAL_SUTUN // 2 else 1)
            toplamlar[bolge] += deger
            sayilar[bolge] += 1

        bolge_ort = tuple(t / max(n, 1) for t, n in zip(toplamlar, sayilar))
        return TermalOzet(
            maks=kare[maks_indeks],
            maks_konum=(sutun, satir),
            bolge_ort=bolge_ort,  # type: ignore[arg-type]
            ortalama=sum(kare) / TERMAL_PIKSEL,
        )
