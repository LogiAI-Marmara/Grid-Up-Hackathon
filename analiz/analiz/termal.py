"""The binary thermal frame: `termal_kare.piksel_verisi` since the integration phase.

Storage (contract 2, integration decision): `bytea`, 768 values as int16
signed, little-endian, unit 0.1 °C (452 -> 45.2 °C), row-major, exactly 1536
bytes. The API's external format does not change — consumers still receive an
array of 768 °C numbers — so this module is the one place the two forms meet.
Anything in track B that reads a frame goes through `kare_coz`; anything that
writes one (fixtures only; track A writes real frames) goes through `kare_kodla`.
"""

from __future__ import annotations

import struct
from collections.abc import Sequence

from .sozlesme import TERMAL_PIKSEL

__all__ = ["KARE_BAYT", "KARE_BICIM", "kare_coz", "kare_kodla", "KareHatasi"]

#: struct format for one frame: 768 little-endian signed 16-bit integers.
KARE_BICIM = f"<{TERMAL_PIKSEL}h"
#: Exact byte length of an encoded frame.
KARE_BAYT = struct.calcsize(KARE_BICIM)  # 1536

_OLCEK = 10.0  # stored unit is 0.1 °C


class KareHatasi(ValueError):
    """A frame that is not 1536 bytes, or a value that does not fit int16."""


def kare_coz(veri: "bytes | bytearray | memoryview") -> list[float]:
    """Decode a stored frame into 768 °C values, row-major.

    Length is checked here as well as by the database CHECK: a frame arriving
    through any other path (a file, a test) must fail the same way.
    """
    ham = bytes(veri)
    if len(ham) != KARE_BAYT:
        raise KareHatasi(f"frame must be exactly {KARE_BAYT} bytes, got {len(ham)}")
    return [v / _OLCEK for v in struct.unpack(KARE_BICIM, ham)]


def kare_kodla(pikseller: Sequence[float]) -> bytes:
    """Encode 768 °C values as the stored form. Rounds to the nearest 0.1 °C."""
    if len(pikseller) != TERMAL_PIKSEL:
        raise KareHatasi(f"frame must have {TERMAL_PIKSEL} values, got {len(pikseller)}")
    tam = [round(float(p) * _OLCEK) for p in pikseller]
    if any(v < -32768 or v > 32767 for v in tam):
        raise KareHatasi("a value does not fit int16 at 0.1 °C resolution")
    return struct.pack(KARE_BICIM, *tam)
