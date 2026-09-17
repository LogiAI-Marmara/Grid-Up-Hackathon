"""Typed models for contracts ① and ② — the service's internal representation.

The JSON Schema is the wire contract and `dogrulama.py` enforces it; these models
are what the rest of the service then works with. Both derive from the same
source: every enum, every unit pairing and every plausibility range here is
imported from `/sozlesmeler/enums.py`, never written out again. That is what makes
"the collector agrees with the contract" a structural fact rather than a habit.

Two conversions happen at this boundary and nowhere else:

* `zaman` becomes an aware `datetime`. Strings are what the radio carries;
  `TIMESTAMPTZ` is what the database stores, and a service that passes strings
  around ends up with one place that forgot to parse them.
* `maks_konum` becomes `maks_sutun` / `maks_satir`. The contract's `[14, 9]` is
  x-first; the table has two columns. Splitting it once, here, is the reason no
  query has to remember which way round the pair goes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

from .sozlesme import (
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
    modul_id_ayristir,
    zaman_oku,
    zaman_yaz,
)


def _zaman(deger: Any) -> Any:
    """Parse a contract timestamp, rejecting anything that is not UTC-with-Z.

    `zaman_oku` refuses `+03:00` offsets on purpose (section 11: one timezone
    everywhere). Keeping that strictness at the door means nothing downstream has
    to wonder whether a timestamp was local.
    """
    if isinstance(deger, str):
        return zaman_oku(deger)
    return deger


#: An aware UTC datetime on the inside, the contract's `...Z` string on the wire.
Zaman = Annotated[datetime, BeforeValidator(_zaman)]

#: `{saha}-{pano}-{modul}`, validated with the canonical pattern from enums.py.
ModulIdStr = Annotated[str, Field(pattern=r"^([A-Za-z0-9]{2,16})-([A-Za-z0-9]{2,16})-([A-Za-z0-9]{2,16})$")]


class OlcumKaydi(BaseModel):
    """Contract ① — one measurement row."""

    model_config = ConfigDict(extra="forbid")

    modul_id: ModulIdStr
    zaman: Zaman
    olcum_tipi: OlcumTipi
    deger: float | None
    birim: Birim
    kalite: Kalite

    @model_validator(mode="after")
    def _sozlesme_kurallari(self) -> OlcumKaydi:
        # 1 — the unit is determined by the measurement type. Without this check a
        #     producer that labels amperes as Celsius writes data that is wrong
        #     but still looks valid. Same pairing as the olcum_birim_uyumlu CHECK.
        beklenen = OLCUM_BIRIM[self.olcum_tipi]
        if self.birim is not beklenen:
            raise ValueError(f"birim for {self.olcum_tipi.value} must be {beklenen.value!r}, got {self.birim.value!r}")

        # 2 — a value may only be missing when the quality says there was no
        #     reading. Writing 0.0 for a dead sensor is exactly the confusion
        #     `kalite` exists to prevent.
        if self.deger is None and self.kalite is not Kalite.YOK:
            raise ValueError(f"deger may only be null when kalite is 'yok', got kalite={self.kalite.value!r}")

        # 3 — plausibility bounds, not alarm thresholds. Out of range means a
        #     broken sensor or a broken encoder; the detector should never see it.
        if self.deger is not None:
            alt, ust = OLCUM_ARALIK[self.olcum_tipi]
            if not alt <= self.deger <= ust:
                raise ValueError(f"deger {self.deger} outside the plausible range [{alt}, {ust}] for {self.olcum_tipi.value}")
        return self

    @property
    def zaman_metni(self) -> str:
        return zaman_yaz(self.zaman)


class TermalOzet(BaseModel):
    """The module's on-board reduction of the 32x24 array."""

    model_config = ConfigDict(extra="forbid")

    maks: float = Field(ge=-40, le=300)
    maks_konum: list[int] = Field(min_length=2, max_length=2)
    bolge_ort: list[float] = Field(min_length=TERMAL_BOLGE_SAYISI, max_length=TERMAL_BOLGE_SAYISI)

    @field_validator("maks_konum")
    @classmethod
    def _konum_araligi(cls, deger: list[int]) -> list[int]:
        sutun, satir = deger
        if not 0 <= sutun < TERMAL_SUTUN or not 0 <= satir < TERMAL_SATIR:
            raise ValueError(f"maks_konum {deger} outside the {TERMAL_SUTUN}x{TERMAL_SATIR} frame (order is [sutun, satir])")
        return deger

    @field_validator("bolge_ort")
    @classmethod
    def _bolge_araligi(cls, deger: list[float]) -> list[float]:
        for ort in deger:
            if not -40 <= ort <= 300:
                raise ValueError(f"bolge_ort value {ort} outside [-40, 300]")
        return deger

    @property
    def maks_sutun(self) -> int:
        """Hot-pixel column, 0..31 (x). The contract's pair is x-first."""
        return self.maks_konum[0]

    @property
    def maks_satir(self) -> int:
        """Hot-pixel row, 0..23 (y)."""
        return self.maks_konum[1]


class ModulDurum(BaseModel):
    """The module's own health — the reason we can claim it does not die silently."""

    model_config = ConfigDict(extra="forbid")

    besleme: Besleme
    sinyal: int = Field(ge=-120, le=0)
    yazilim_surumu: str = Field(pattern=r"^\d+\.\d+\.\d+$")


class ModulPaketi(BaseModel):
    """Contract ② — what a module puts on the wire."""

    model_config = ConfigDict(extra="forbid")

    modul_id: ModulIdStr
    zaman: Zaman
    olcumler: list[OlcumKaydi]
    termal_ozet: TermalOzet | None = None
    termal_kare: list[float] | None = None
    modul_durum: ModulDurum

    @field_validator("termal_kare")
    @classmethod
    def _kare_boyu(cls, deger: list[float] | None) -> list[float] | None:
        if deger is not None and len(deger) != TERMAL_PIKSEL:
            raise ValueError(f"termal_kare must hold {TERMAL_PIKSEL} values ({TERMAL_SUTUN}x{TERMAL_SATIR}), got {len(deger)}")
        return deger

    @property
    def kimlik(self) -> ModulId:
        """The module id split into site / panel / module — the reference tree."""
        return modul_id_ayristir(self.modul_id)

    @property
    def zaman_metni(self) -> str:
        return zaman_yaz(self.zaman)


class YazimSonucu(BaseModel):
    """How many rows one packet turned into. The body of a successful POST."""

    modul_id: str
    zaman: str
    alindi_zaman: str
    olcum: int = 0
    termal_ozet: int = 0
    termal_kare: int = 0
    modul_durum: int = 0
    kare_id: str | None = None
    #: True when every row was a duplicate of something already stored. A
    #: retransmitting module is normal (it has a backup store), so this is
    #: information, not an error.
    yinelenen: bool = False
