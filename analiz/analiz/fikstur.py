"""Test fixtures: contract-shaped rows, written without track A.

Section 4.4's protocol has track A generating blind test sets, and that is the
evidence that counts. This module is the other half — the labelled development
set (section 2.7), which exists so the detector can be built and regression-
tested at all, and so track B is testable on a day when nothing of track A's is
running.

Everything written here goes through the same tables and the same constraints
that track A's collector writes through, so "it works against the fixtures" and
"it works against real data" differ only in who produced the rows.

The two traps from section 4.4 are respected here as well, even though this set
is labelled:

  - there are CLEAN modules. A fixture set where every module is faulty is
    passed by a detector that alarms on everything, and measures nothing.
  - there are modules that are NOISY BUT NORMAL, and sensor failures that look
    like faults. Without them the detector is only ever asked the easy question.

`analiz.senaryolar` builds the scenarios on top of this.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import psycopg

from .sozlesme import (
    OLCUM_BIRIM,
    TERMAL_PIKSEL,
    TERMAL_SUTUN,
    Besleme,
    Kalite,
    OlcumTipi,
    modul_id_ayristir,
)
from .termal import kare_kodla

__all__ = ["OlcumSatiri", "TermalSatiri", "DurumSatiri", "Fikstur"]


@dataclass(frozen=True, slots=True)
class OlcumSatiri:
    """One row of contract 1, before it is written."""

    modul_id: str
    olcum_tipi: OlcumTipi
    zaman: datetime
    deger: float | None
    kalite: Kalite = Kalite.IYI
    alindi_zaman: datetime | None = None

    @property
    def varis(self) -> datetime:
        """Arrival time. Defaults to the measurement time plus a plausible latency.

        The two are kept distinct rather than equal because the gap between them
        is what makes clock drift visible (scenario 7), and a fixture set where
        they are always identical cannot exercise that at all.
        """
        return self.alindi_zaman or (self.zaman + timedelta(seconds=2))


@dataclass(frozen=True, slots=True)
class TermalSatiri:
    """One row of `termal_ozet`, with an optional full frame alongside."""

    modul_id: str
    zaman: datetime
    maks: float
    maks_sutun: int
    maks_satir: int
    bolge_ort: tuple[float, float, float, float]
    kare: bool = False
    alindi_zaman: datetime | None = None

    @property
    def varis(self) -> datetime:
        return self.alindi_zaman or (self.zaman + timedelta(seconds=2))


@dataclass(frozen=True, slots=True)
class DurumSatiri:
    """One row of `modul_durum` — the status half of contract 2, one per packet."""

    modul_id: str
    zaman: datetime
    besleme: Besleme = Besleme.SEBEKE
    sinyal: int = -72
    yazilim_surumu: str = "1.0.3"
    alindi_zaman: datetime | None = None

    @property
    def varis(self) -> datetime:
        return self.alindi_zaman or (self.zaman + timedelta(seconds=2))


class Fikstur:
    """Writes contract-shaped rows into a database.

    Buffers and writes with COPY rather than row-by-row inserts: a fortnight of
    baseline for a dozen modules is ~10^5 rows, and at one INSERT each the test
    suite would be slower than the thing it tests.
    """

    def __init__(self, baglanti: psycopg.Connection) -> None:
        self._baglanti = baglanti
        self._olcumler: list[OlcumSatiri] = []
        self._termaller: list[TermalSatiri] = []
        self._durumlar: list[DurumSatiri] = []
        self._moduller: set[str] = set()

    # -- reference tree ----------------------------------------------------

    def modul(self, modul_id: str, aktif: bool = True) -> str:
        """Register a module, creating its site and panel rows as needed.

        The hierarchy is parsed out of the id rather than passed separately —
        that is the property the contract's `modul_id_bicim` CHECK enforces, so
        deriving it here means the fixtures cannot create a module the real
        schema would reject.
        """
        parcalar = modul_id_ayristir(modul_id)
        with self._baglanti.cursor() as imlec:
            imlec.execute(
                "INSERT INTO gridup.saha (saha_kodu, ad) VALUES (%s, %s) "
                "ON CONFLICT (saha_kodu) DO NOTHING",
                (parcalar.saha, f"{parcalar.saha} trafo merkezi"),
            )
            imlec.execute(
                "INSERT INTO gridup.pano (saha_kodu, pano_kodu, ad) VALUES (%s, %s, %s) "
                "ON CONFLICT (saha_kodu, pano_kodu) DO NOTHING",
                (parcalar.saha, parcalar.pano, f"{parcalar.pano} AG panosu"),
            )
            imlec.execute(
                """
                INSERT INTO gridup.modul
                    (modul_id, saha_kodu, pano_kodu, modul_kodu, aktif, yazilim_surumu)
                VALUES (%s, %s, %s, %s, %s, '1.0.3')
                ON CONFLICT (modul_id) DO UPDATE SET aktif = EXCLUDED.aktif
                """,
                (modul_id, parcalar.saha, parcalar.pano, parcalar.modul, aktif),
            )
        self._moduller.add(modul_id)
        return modul_id

    # -- buffering ---------------------------------------------------------

    def olcum(
        self,
        modul_id: str,
        olcum_tipi: OlcumTipi,
        zaman: datetime,
        deger: float | None,
        kalite: Kalite = Kalite.IYI,
        alindi_zaman: datetime | None = None,
    ) -> None:
        self._olcumler.append(
            OlcumSatiri(modul_id, olcum_tipi, zaman, deger, kalite, alindi_zaman)
        )

    def termal(
        self,
        modul_id: str,
        zaman: datetime,
        maks: float,
        maks_sutun: int,
        maks_satir: int,
        bolge_ort: tuple[float, float, float, float],
        kare: bool = False,
        alindi_zaman: datetime | None = None,
    ) -> None:
        self._termaller.append(
            TermalSatiri(
                modul_id, zaman, maks, maks_sutun, maks_satir, bolge_ort, kare, alindi_zaman
            )
        )

    def durum(
        self,
        modul_id: str,
        zaman: datetime,
        besleme: Besleme = Besleme.SEBEKE,
        sinyal: int = -72,
        yazilim_surumu: str = "1.0.3",
        alindi_zaman: datetime | None = None,
    ) -> None:
        self._durumlar.append(
            DurumSatiri(modul_id, zaman, besleme, sinyal, yazilim_surumu, alindi_zaman)
        )

    # -- writing -----------------------------------------------------------

    def yaz(self) -> tuple[int, int]:
        """Flush everything buffered. Returns (measurement rows, thermal rows).

        Status rows are written too; they are not in the return value so the
        many callers counting the two contract-1/2 halves need not change.
        """
        olcum_sayisi = self._olcumleri_yaz()
        termal_sayisi = self._termalleri_yaz()
        self._durumlari_yaz()
        self._baglanti.commit()
        self._olcumler.clear()
        self._termaller.clear()
        self._durumlar.clear()
        return olcum_sayisi, termal_sayisi

    def _durumlari_yaz(self) -> int:
        if not self._durumlar:
            return 0
        benzersiz: dict[tuple[str, datetime], DurumSatiri] = {}
        for satir in self._durumlar:
            benzersiz[(satir.modul_id, satir.zaman)] = satir
        with self._baglanti.cursor() as imlec:
            with imlec.copy(
                "COPY gridup.modul_durum "
                "(modul_id, zaman, besleme, sinyal, yazilim_surumu, alindi_zaman) FROM STDIN"
            ) as kopya:
                for satir in benzersiz.values():
                    kopya.write_row(
                        (
                            satir.modul_id,
                            satir.zaman,
                            satir.besleme.value,
                            satir.sinyal,
                            satir.yazilim_surumu,
                            satir.varis,
                        )
                    )
        return len(benzersiz)

    def _olcumleri_yaz(self) -> int:
        if not self._olcumler:
            return 0
        # De-duplicate on the natural key first. COPY does not honour ON CONFLICT,
        # and a scenario that overwrites part of a baseline it already wrote would
        # otherwise fail on the primary key.
        benzersiz: dict[tuple[str, str, datetime], OlcumSatiri] = {}
        for satir in self._olcumler:
            benzersiz[(satir.modul_id, satir.olcum_tipi.value, satir.zaman)] = satir

        with self._baglanti.cursor() as imlec:
            with imlec.copy(
                "COPY gridup.olcum (modul_id, olcum_tipi, zaman, deger, birim, kalite, alindi_zaman) "
                "FROM STDIN"
            ) as kopya:
                for satir in benzersiz.values():
                    kopya.write_row(
                        (
                            satir.modul_id,
                            satir.olcum_tipi.value,
                            satir.zaman,
                            satir.deger,
                            OLCUM_BIRIM[satir.olcum_tipi].value,
                            satir.kalite.value,
                            satir.varis,
                        )
                    )
        return len(benzersiz)

    def _termalleri_yaz(self) -> int:
        if not self._termaller:
            return 0
        benzersiz: dict[tuple[str, datetime], TermalSatiri] = {}
        for satir in self._termaller:
            benzersiz[(satir.modul_id, satir.zaman)] = satir

        with self._baglanti.cursor() as imlec:
            with imlec.copy(
                "COPY gridup.termal_ozet "
                "(modul_id, zaman, maks, maks_sutun, maks_satir, bolge_ort, alindi_zaman) "
                "FROM STDIN"
            ) as kopya:
                for satir in benzersiz.values():
                    kopya.write_row(
                        (
                            satir.modul_id,
                            satir.zaman,
                            satir.maks,
                            satir.maks_sutun,
                            satir.maks_satir,
                            list(satir.bolge_ort),
                            satir.varis,
                        )
                    )
            # A full frame arrives at every measurement instant (integration
            # decision), stored binary — int16 LE, 0.1 °C, 1536 bytes. COPY,
            # because there can be one per summary now.
            kareli = [s for s in benzersiz.values() if s.kare]
            if kareli:
                with imlec.copy(
                    "COPY gridup.termal_kare (modul_id, zaman, piksel_verisi, alindi_zaman) "
                    "FROM STDIN"
                ) as kopya:
                    for satir in kareli:
                        kopya.write_row(
                            (
                                satir.modul_id,
                                satir.zaman,
                                kare_kodla(
                                    _kare_uret(
                                        satir.maks,
                                        satir.bolge_ort,
                                        satir.maks_sutun,
                                        satir.maks_satir,
                                    )
                                ),
                                satir.varis,
                            )
                        )
        return len(benzersiz)


def _kare_uret(
    maks: float, bolge_ort: tuple[float, ...], sutun: int, satir: int
) -> list[float]:
    """A 768-value frame consistent with the summary that describes it.

    The frame is evidence the dashboard renders, so it has to agree with the
    summary beside it: the hot pixel really is the hottest, and the quadrant
    means really are the means of their quadrants. A frame that contradicted its
    own summary would be a fixture bug that looks like a detector bug.
    """
    pikseller: list[float] = []
    for s in range(TERMAL_PIKSEL // TERMAL_SUTUN):
        for c in range(TERMAL_SUTUN):
            ceyrek = (0 if s < 12 else 2) + (0 if c < 16 else 1)
            taban = bolge_ort[ceyrek]
            uzaklik = math.hypot(c - sutun, s - satir)
            # Gaussian bump on the hot pixel, so neighbouring pixels are warm too
            # and the spot has a physical shape rather than one hot cell.
            pikseller.append(round(taban + (maks - taban) * math.exp(-(uzaklik**2) / 4.0), 2))
    return pikseller
