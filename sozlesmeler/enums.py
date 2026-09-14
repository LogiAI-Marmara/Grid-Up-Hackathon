"""Grid-Up shared vocabularies — single source of truth.

Every track (A/B/C) imports its enum values from here. The values themselves are
Turkish because they are part of the wire contract (see section 10 of
`gridup-proje-karar-kaydi.md`); code and comments are English.

Nothing outside the standard library is required, so any service can vendor or
import this file without pulling dependencies.

Run `python enums.py` to dump every vocabulary as JSON — that is how non-Python
tracks (the dashboard, the Modbus server) consume the same source of truth.
"""

from __future__ import annotations

import json
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
    "Besleme",
    "Birim",
    "OLCUM_BIRIM",
    "OLCUM_ARALIK",
    "SEVIYE_SIRA",
    "TERMAL_SATIR",
    "TERMAL_SUTUN",
    "TERMAL_PIKSEL",
    "TERMAL_BOLGE_SAYISI",
    "MODUL_ID_DESEN",
    "ZAMAN_DESEN",
    "ModulId",
    "modul_id_ayristir",
    "modul_id_gecerli",
    "zaman_yaz",
    "zaman_oku",
    "piksel_indeks",
    "indeks_piksel",
    "seviye_karsilastir",
    "sozlukler",
]


class _MetinEnum(str, Enum):
    """String enum: `OlcumTipi.NEM == "nem"` is true, so JSON/SQL use is direct."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


# --------------------------------------------------------------------------
# Contract vocabularies — section 10 of the decision record, verbatim.
# Adding or renaming a value here is a contract change and requires the lead's
# approval plus an announcement to all three tracks.
# --------------------------------------------------------------------------


class OlcumTipi(_MetinEnum):
    """What a measurement row measures."""

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
    """Severity of an anomaly. Ordered: normal < izle < uyari < kritik."""

    NORMAL = "normal"
    IZLE = "izle"
    UYARI = "uyari"
    KRITIK = "kritik"


class Tip(_MetinEnum):
    """Anomaly class. One value per fault scenario in section 7.6."""

    SICAK_NOKTA = "sicak_nokta"
    AKIM_SICAKLIK_SAPMASI = "akim_sicaklik_sapmasi"
    FAZ_DENGESIZLIGI = "faz_dengesizligi"
    NEM_YUKSEK = "nem_yuksek"
    ORTAM_SICAKLIK_YUKSEK = "ortam_sicaklik_yuksek"
    ARK = "ark"
    SENSOR_ARIZASI = "sensor_arizasi"
    MODUL_SAGLIK = "modul_saglik"


class Kalite(_MetinEnum):
    """Trustworthiness of a measurement.

    This field is what separates "the sensor broke and reports 0" from "the
    value really is 0" — scenario 6 depends entirely on it.
    """

    IYI = "iyi"
    SUPHELI = "supheli"
    YOK = "yok"


class Durum(_MetinEnum):
    """Anomaly lifecycle state, driven by the operator."""

    ACIK = "acik"
    ONAYLANDI = "onaylandi"
    KAPANDI = "kapandi"


class Besleme(_MetinEnum):
    """Module power source. `yedek` means the supercapacitor is carrying it."""

    SEBEKE = "sebeke"
    YEDEK = "yedek"


# --------------------------------------------------------------------------
# Derived vocabularies — not in the decision record, but fully determined by it.
# `birim` is a contract field whose value set follows from the measurement type
# ("gerçek birimde ondalıklı: °C, A, %", section 11). Enumerating it here keeps
# the three tracks from inventing "degC" / "Celsius" / "amper" independently.
# --------------------------------------------------------------------------


class Birim(_MetinEnum):
    """Unit stored in the database. Modbus scaling happens at the edge, not here."""

    C = "C"
    YUZDE = "%"
    A = "A"
    OLAY = "olay"


#: Canonical unit for every measurement type. The ingest service and the DB
#: CHECK constraint both enforce this mapping.
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
#: These are *sanity* bounds, not alarm thresholds. A value outside this range is
#: a broken sensor or a broken encoder, not an anomaly — the detector never sees
#: it because ingest rejects it. Alarm thresholds live in track B.
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

#: Severity ordering, so "is this worse than what we already showed?" is one
#: comparison instead of a hand-written if-chain in three repositories.
SEVIYE_SIRA: dict[Seviye, int] = {
    Seviye.NORMAL: 0,
    Seviye.IZLE: 1,
    Seviye.UYARI: 2,
    Seviye.KRITIK: 3,
}


# --------------------------------------------------------------------------
# Thermal frame geometry (section 11)
# --------------------------------------------------------------------------

TERMAL_SATIR = 24  # rows, y axis
TERMAL_SUTUN = 32  # columns, x axis
TERMAL_PIKSEL = TERMAL_SATIR * TERMAL_SUTUN  # 768, row-major flat array
TERMAL_BOLGE_SAYISI = 4  # bolge_ort quadrants: top-left, top-right, bottom-left, bottom-right


def piksel_indeks(sutun: int, satir: int) -> int:
    """Map a (column, row) pixel to its index in the flat 768-element array.

    `maks_konum` and `kanit.piksel` are both `[sutun, satir]` — x first, as in
    the decision record's `[14, 9]` example. Row-major means index = row*32 + col.
    """
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


# --------------------------------------------------------------------------
# Identity and time (section 11)
# --------------------------------------------------------------------------

#: `{saha}-{pano}-{modul}` e.g. TR041-P01-M1. The hierarchy lives inside the id,
#: which is why the dashboard tree and the load-test grouping come for free.
MODUL_ID_DESEN = re.compile(r"^([A-Za-z0-9]{2,16})-([A-Za-z0-9]{2,16})-([A-Za-z0-9]{2,16})$")

#: UTC ISO 8601 with a literal Z. Offsets like +03:00 are rejected on purpose:
#: one timezone everywhere means no "was this local or UTC?" during the demo.
ZAMAN_DESEN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$")


class ModulId(NamedTuple):
    """Parsed module identifier."""

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


def modul_id_gecerli(modul_id: str) -> bool:
    """True if `modul_id` matches the contract format."""
    return MODUL_ID_DESEN.match(modul_id) is not None


def zaman_yaz(an: datetime | None = None) -> str:
    """Format an aware datetime as the contract timestamp (UTC, second precision).

    With no argument, returns "now". Naive datetimes are rejected rather than
    silently assumed to be UTC — a wrong timestamp is worse than a loud failure,
    because clock drift is one of the things we claim to detect (scenario 7).
    """
    if an is None:
        an = datetime.now(timezone.utc)
    if an.tzinfo is None:
        raise ValueError("naive datetime rejected; attach a timezone")
    return an.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def zaman_oku(metin: str) -> datetime:
    """Parse a contract timestamp into an aware UTC datetime."""
    if ZAMAN_DESEN.match(metin) is None:
        raise ValueError(f"invalid zaman: {metin!r} (expected YYYY-MM-DDTHH:MM:SSZ)")
    return datetime.fromisoformat(metin.replace("Z", "+00:00"))


def seviye_karsilastir(a: Seviye, b: Seviye) -> int:
    """-1 / 0 / +1 depending on whether `a` is milder, equal to, or worse than `b`."""
    fark = SEVIYE_SIRA[Seviye(a)] - SEVIYE_SIRA[Seviye(b)]
    return (fark > 0) - (fark < 0)


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------


def sozlukler() -> dict[str, object]:
    """Every vocabulary as plain data — consumed by `dogrula.py` and other languages."""
    return {
        "olcum_tipi": [e.value for e in OlcumTipi],
        "seviye": [e.value for e in Seviye],
        "tip": [e.value for e in Tip],
        "kalite": [e.value for e in Kalite],
        "durum": [e.value for e in Durum],
        "besleme": [e.value for e in Besleme],
        "birim": [e.value for e in Birim],
        "olcum_birim": {k.value: v.value for k, v in OLCUM_BIRIM.items()},
        "olcum_aralik": {k.value: list(v) for k, v in OLCUM_ARALIK.items()},
        "seviye_sira": {k.value: v for k, v in SEVIYE_SIRA.items()},
        "termal": {
            "satir": TERMAL_SATIR,
            "sutun": TERMAL_SUTUN,
            "piksel": TERMAL_PIKSEL,
            "bolge_sayisi": TERMAL_BOLGE_SAYISI,
            "duzen": "satir_oncelikli",
            "konum_sirasi": "[sutun, satir]",
        },
        "desen": {
            "modul_id": MODUL_ID_DESEN.pattern,
            "zaman": ZAMAN_DESEN.pattern,
        },
    }


if __name__ == "__main__":
    print(json.dumps(sozlukler(), indent=2, ensure_ascii=False))
