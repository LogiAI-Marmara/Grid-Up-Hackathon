"""Packet validation at the door: JSON Schema first, then the cross-field rules.

The collector rejects rather than repairs. A packet that is wrong in a way the
schema can see is a producer bug, and storing it would push the cost of that bug
onto the detector and the dashboard, where it is much harder to find. Every
rejection carries a `gerekce` — the same principle as the anomaly contract's
`gerekce` field: whoever is on the other end has to be able to see *why*.

Two layers, in this order:

1. `modul_paketi.schema.json` — the wire contract, enforced verbatim. It owns
   structure, vocabularies, ranges and unit pairings. It is loaded from
   `/sozlesmeler`, never copied into this service.
2. `sozlesme_kurallari` — the rules a JSON Schema cannot express, all of which
   are stated in the contract or in the DB constraints: the id echo, the
   packet-internal primary key, and the agreement between the thermal summary and
   the frame it was derived from.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from .sozlesme import SEMA_KLASORU, TERMAL_PIKSEL, piksel_indeks

#: Schema documents this service needs. `modul_paketi` `$ref`s `olcum_kaydi`, so
#: both have to be in the registry for validation to resolve.
SEMA_DOSYALARI = ("olcum_kaydi.schema.json", "modul_paketi.schema.json")

PAKET_SEMASI = "modul_paketi.schema.json"

#: Tolerance when comparing two numbers that came from the same frame. The wire
#: carries two decimals, so anything tighter would reject correct packets.
TOLERANS = 0.05


@lru_cache(maxsize=None)
def semalar() -> dict[str, dict[str, Any]]:
    """The schema documents, read once."""
    return {ad: json.loads((SEMA_KLASORU / ad).read_text(encoding="utf-8")) for ad in SEMA_DOSYALARI}


@lru_cache(maxsize=None)
def dogrulayici():
    """Cached validator for contract ②, with the referenced row schema registered."""
    import jsonschema
    from referencing import Registry, Resource

    belgeler = semalar()
    # Registered under the file name, which is how the relative $ref inside
    # modul_paketi.schema.json is written.
    kayit = Registry().with_resources(
        [(ad, Resource.from_contents(belge)) for ad, belge in belgeler.items()]
    )
    return jsonschema.Draft202012Validator(belgeler[PAKET_SEMASI], registry=kayit)


def _yol(hata) -> str:
    """A JSON path a producer can act on, e.g. `$['olcumler'][3]['birim']`."""
    return "$" + "".join(f"[{p!r}]" if isinstance(p, str) else f"[{p}]" for p in hata.absolute_path)


def sema_hatalari(paket: Any) -> list[str]:
    """Every `modul_paketi.schema.json` violation, as readable one-liners."""
    if not isinstance(paket, dict):
        return [f"$: packet must be a JSON object, got {type(paket).__name__}"]
    return [f"{_yol(hata)}: {hata.message}" for hata in dogrulayici().iter_errors(paket)]


def sozlesme_kurallari(paket: dict[str, Any]) -> list[str]:
    """Cross-field rules that live outside the schema's expressive power.

    Assumes the packet already passed `sema_hatalari`, so the shapes are known
    good and this function only has to compare values.
    """
    hatalar: list[str] = []
    modul_id = paket["modul_id"]
    paket_zaman = paket["zaman"]
    olcumler = paket.get("olcumler") or []

    # 1 — every row repeats the packet's module id. Stated in the schema's own
    #     description; a row that names a different module would otherwise be
    #     filed under that module, which is a silent data mix-up.
    for i, olcum in enumerate(olcumler):
        if olcum["modul_id"] != modul_id:
            hatalar.append(f"$['olcumler'][{i}]['modul_id']: {olcum['modul_id']!r} does not match the packet's {modul_id!r}")

    # 2 — (modul_id, olcum_tipi, zaman) is the measurement table's primary key.
    #     Two rows with the same key inside one packet means one of them would be
    #     dropped by the dedup path, so the producer must be told instead.
    gorulen: set[tuple[str, str]] = set()
    for i, olcum in enumerate(olcumler):
        anahtar = (olcum["olcum_tipi"], olcum["zaman"])
        if anahtar in gorulen:
            hatalar.append(f"$['olcumler'][{i}]: duplicate ({anahtar[0]}, {anahtar[1]}) inside one packet")
        gorulen.add(anahtar)

    ozet = paket.get("termal_ozet")
    kare = paket.get("termal_kare")

    # 3 — a frame without its summary is incoherent: the summary is derived from
    #     the frame, so if the sensor produced nothing there is no frame either.
    if kare is not None and ozet is None:
        hatalar.append("$['termal_ozet']: a packet carrying termal_kare must carry the summary derived from it")

    if kare is not None and ozet is not None and len(kare) == TERMAL_PIKSEL:
        # 4 — the summary must describe the frame that was actually transmitted.
        #     This is the check that keeps `kanit.piksel` meaningful: the operator
        #     is shown a pixel coordinate on top of an image, and if the two
        #     disagree the evidence points at the wrong terminal.
        sutun, satir = ozet["maks_konum"]
        indeks = piksel_indeks(sutun, satir)
        if abs(kare[indeks] - ozet["maks"]) > TOLERANS:
            hatalar.append(
                f"$['termal_ozet']['maks']: {ozet['maks']} does not match the frame at maks_konum "
                f"[{sutun}, {satir}] ({kare[indeks]})"
            )
        elif abs(max(kare) - ozet["maks"]) > TOLERANS:
            hatalar.append(
                f"$['termal_ozet']['maks_konum']: [{sutun}, {satir}] is not the hottest pixel; "
                f"frame maximum is {max(kare)}"
            )

    # 5 — termal_maks / termal_ort are projections of the summary into the generic
    #     time-series path (migration 003). If the two disagree, one of them is
    #     wrong and the detector would see a contradiction. Only rows stamped with
    #     the packet's own time are compared: a module with a backup store may
    #     legally replay older rows in the same packet.
    if ozet is not None:
        for i, olcum in enumerate(olcumler):
            if olcum["olcum_tipi"] != "termal_maks" or olcum["zaman"] != paket_zaman:
                continue
            if olcum["deger"] is None:
                continue
            if abs(olcum["deger"] - ozet["maks"]) > TOLERANS:
                hatalar.append(
                    f"$['olcumler'][{i}]['deger']: termal_maks {olcum['deger']} contradicts "
                    f"termal_ozet.maks {ozet['maks']}"
                )

    return hatalar


def paket_hatalari(paket: Any) -> list[str]:
    """All reasons this packet is unacceptable. Empty list means "store it".

    Schema errors short-circuit the cross-field pass: comparing values in a
    packet whose shape is already wrong produces noise, not help.
    """
    hatalar = sema_hatalari(paket)
    if hatalar:
        return hatalar
    return sozlesme_kurallari(paket)
