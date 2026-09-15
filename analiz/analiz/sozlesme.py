"""Shared vocabularies, as track B needs them.

This is a deliberate, standalone restatement of the contract vocabularies that
live in `/sozlesmeler` on track A's branch. Track B does not import that module:
the two tracks are developed in parallel, track A's branch is not merged, and a
build-time dependency on an unmerged branch would make this package untestable
on its own. The values below are the contract and are kept byte-identical to it;
if the contract changes, this file changes with it and `tests/test_sozlesme.py`
is where the mismatch shows up.

Identifiers that mirror the contract are Turkish because they are on the wire
(`olcum_tipi`, `seviye`, `tip`, `kalite`, `durum`). Comments are English.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import NamedTuple

__all__ = [
    "OlcumTipi",
    "Seviye",
    "Tip",
    "Kalite",
    "Durum",
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
    "piksel_indeks",
    "indeks_piksel",
    "seviye_karsilastir",
    "en_yuksek_seviye",
]


class _MetinEnum(str, Enum):
    """String enum, so `OlcumTipi.NEM == "nem"` holds and SQL/JSON use is direct."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class OlcumTipi(_MetinEnum):
    """What a measurement row measures. Contract 1."""

    ORTAM_SICAKLIK = "ortam_sicaklik"
    NEM = "nem"
    AKIM_L1 = "akim_l1"
    AKIM_L2 = "akim_l2"
    AKIM_L3 = "akim_l3"
    AKIM_NOTR = "akim_notr"
    TERMAL_MAKS = "termal_maks"
    TERMAL_ORT = "termal_ort"
    ARK_OLAY = "ark_olay"


class Seviye(_MetinEnum):
    """Severity. Ordered normal < izle < uyari < kritik.

    Section 2.4 of the track B decision record: this is a *time horizon*, not an
    urgency label. izle = weeks, uyari = days, kritik = hours or a hard safety
    limit already crossed.
    """

    NORMAL = "normal"
    IZLE = "izle"
    UYARI = "uyari"
    KRITIK = "kritik"


class Tip(_MetinEnum):
    """Anomaly class — one value per fault scenario in section 7.6 of the parent record."""

    SICAK_NOKTA = "sicak_nokta"
    AKIM_SICAKLIK_SAPMASI = "akim_sicaklik_sapmasi"
    FAZ_DENGESIZLIGI = "faz_dengesizligi"
    NEM_YUKSEK = "nem_yuksek"
    ORTAM_SICAKLIK_YUKSEK = "ortam_sicaklik_yuksek"
    ARK = "ark"
    SENSOR_ARIZASI = "sensor_arizasi"
    MODUL_SAGLIK = "modul_saglik"


class Kalite(_MetinEnum):
    """Trustworthiness of a measurement. Scenario 6 rests entirely on this."""

    IYI = "iyi"
    SUPHELI = "supheli"
    YOK = "yok"


class Durum(_MetinEnum):
    """Anomaly lifecycle state."""

    ACIK = "acik"
    ONAYLANDI = "onaylandi"
    KAPANDI = "kapandi"


class Birim(_MetinEnum):
    """Unit as stored. Modbus integer scaling happens at the edge, never here."""

    C = "C"
    YUZDE = "%"
    A = "A"
    OLAY = "olay"


#: Canonical unit per measurement type. The database CHECK constraint enforces
#: the same pairing, so writing amperes labelled as Celsius fails at the door.
OLCUM_BIRIM: dict[OlcumTipi, Birim] = {
    OlcumTipi.ORTAM_SICAKLIK: Birim.C,
    OlcumTipi.NEM: Birim.YUZDE,
    OlcumTipi.AKIM_L1: Birim.A,
    OlcumTipi.AKIM_L2: Birim.A,
    OlcumTipi.AKIM_L3: Birim.A,
    OlcumTipi.AKIM_NOTR: Birim.A,
    OlcumTipi.TERMAL_MAKS: Birim.C,
    OlcumTipi.TERMAL_ORT: Birim.C,
    OlcumTipi.ARK_OLAY: Birim.OLAY,
}

#: Physically plausible inclusive range per measurement type.
#:
#: These are *sanity* bounds, not alarm thresholds — alarm thresholds are
#: configuration and live in `ayar.py`. A value outside this range means a broken
#: sensor or a broken encoder, which is why layer 0 (and not layer 1) is the
#: layer that reads this table.
OLCUM_ARALIK: dict[OlcumTipi, tuple[float, float]] = {
    OlcumTipi.ORTAM_SICAKLIK: (-40.0, 150.0),
    OlcumTipi.NEM: (0.0, 100.0),
    OlcumTipi.AKIM_L1: (0.0, 10000.0),
    OlcumTipi.AKIM_L2: (0.0, 10000.0),
    OlcumTipi.AKIM_L3: (0.0, 10000.0),
    OlcumTipi.AKIM_NOTR: (0.0, 10000.0),
    OlcumTipi.TERMAL_MAKS: (-40.0, 300.0),
    OlcumTipi.TERMAL_ORT: (-40.0, 300.0),
    OlcumTipi.ARK_OLAY: (0.0, 1000.0),
}

SEVIYE_SIRA: dict[Seviye, int] = {
    Seviye.NORMAL: 0,
    Seviye.IZLE: 1,
    Seviye.UYARI: 2,
    Seviye.KRITIK: 3,
}

# Thermal frame geometry. 32 columns x 24 rows, row-major, [sutun, satir] order.
TERMAL_SATIR = 24
TERMAL_SUTUN = 32
TERMAL_PIKSEL = TERMAL_SATIR * TERMAL_SUTUN
TERMAL_BOLGE_SAYISI = 4

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

MODUL_ID_DESEN = re.compile(r"^([A-Za-z0-9]{2,16})-([A-Za-z0-9]{2,16})-([A-Za-z0-9]{2,16})$")


class ModulId(NamedTuple):
    """Parsed module identifier: the hierarchy lives inside the id."""

    saha: str
    pano: str
    modul: str

    def __str__(self) -> str:
        return f"{self.saha}-{self.pano}-{self.modul}"


def modul_id_ayristir(modul_id: str) -> ModulId:
    """Split `TR041-P01-M1` into its site / panel / module parts."""
    eslesme = MODUL_ID_DESEN.match(modul_id)
    if eslesme is None:
        raise ValueError(f"invalid modul_id: {modul_id!r} (expected {{saha}}-{{pano}}-{{modul}})")
    return ModulId(*eslesme.groups())


def zaman_yaz(an: datetime) -> str:
    """Format an aware datetime as the contract timestamp (UTC, second precision).

    Naive datetimes are rejected rather than silently assumed to be UTC: clock
    drift is one of the things this detector claims to find, so guessing about
    timezones here would undermine the claim.
    """
    if an.tzinfo is None:
        raise ValueError("naive datetime rejected; attach a timezone")
    return an.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def piksel_indeks(sutun: int, satir: int) -> int:
    """Index of pixel (column, row) in the flat 768-element row-major array."""
    if not 0 <= sutun < TERMAL_SUTUN:
        raise ValueError(f"sutun out of range: {sutun}")
    if not 0 <= satir < TERMAL_SATIR:
        raise ValueError(f"satir out of range: {satir}")
    return satir * TERMAL_SUTUN + sutun


def indeks_piksel(indeks: int) -> tuple[int, int]:
    """Inverse of `piksel_indeks`. Returns `(sutun, satir)`."""
    if not 0 <= indeks < TERMAL_PIKSEL:
        raise ValueError(f"indeks out of range: {indeks}")
    return indeks % TERMAL_SUTUN, indeks // TERMAL_SUTUN


def seviye_karsilastir(a: Seviye, b: Seviye) -> int:
    """-1 / 0 / +1 as `a` is milder than, equal to, or worse than `b`."""
    fark = SEVIYE_SIRA[Seviye(a)] - SEVIYE_SIRA[Seviye(b)]
    return (fark > 0) - (fark < 0)


def en_yuksek_seviye(seviyeler: "list[Seviye] | tuple[Seviye, ...]") -> Seviye:
    """Worst severity in the collection; `normal` for an empty one."""
    if not seviyeler:
        return Seviye.NORMAL
    return max(seviyeler, key=lambda s: SEVIYE_SIRA[Seviye(s)])
