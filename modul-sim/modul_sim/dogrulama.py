"""Validate generated packets against the JSON Schemas in `/sozlesmeler`.

The generator does not need this to run — that is why `jsonschema` is optional
and this module is imported lazily. It exists because "the simulator emits
contract-shaped packets" is a claim track B and track C depend on, and a claim
nobody checks is a claim that quietly stops being true. `--dogrula` on the CLI
and the test suite both go through here, so there is one implementation of
"conforms to contract ②" rather than two that can disagree.

`modul_paketi.schema.json` references `olcum_kaydi.schema.json` by a relative
`$ref`, so validation needs both documents in a registry; that wiring is the
only real content of this file.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from .sozlesme import SEMA_KLASORU

#: Schema file names, in the order `dogrula.py` lists them.
SEMA_DOSYALARI = ("olcum_kaydi.schema.json", "modul_paketi.schema.json", "anomali.schema.json")

PAKET_SEMASI = "modul_paketi.schema.json"


def sema_oku(ad: str) -> dict[str, Any]:
    """Read one schema document from `/sozlesmeler`."""
    return json.loads((SEMA_KLASORU / ad).read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def dogrulayici(ad: str = PAKET_SEMASI):
    """A cached `jsonschema` validator for one of the contract schemas.

    Raises `ImportError` with an actionable message if `jsonschema` is missing —
    better than a bare ModuleNotFoundError from inside a generator loop.
    """
    try:
        import jsonschema
        from referencing import Registry, Resource
    except ImportError as hata:  # pragma: no cover - depends on the environment
        raise ImportError(
            "packet validation needs the optional dependencies: pip install jsonschema referencing"
        ) from hata

    belgeler = {dosya: sema_oku(dosya) for dosya in SEMA_DOSYALARI}
    # Registered under the file name, which is how the relative $ref in
    # modul_paketi.schema.json is written.
    kayit = Registry().with_resources(
        [(dosya, Resource.from_contents(belge)) for dosya, belge in belgeler.items()]
    )
    return jsonschema.Draft202012Validator(belgeler[ad], registry=kayit)


def paket_hatalari(paket: dict, ad: str = PAKET_SEMASI) -> list[str]:
    """Every schema violation in one packet, as readable one-liners.

    Empty list means the packet is contract-valid.
    """
    hatalar = []
    for hata in dogrulayici(ad).iter_errors(paket):
        yol = "$" + "".join(f"[{p!r}]" if isinstance(p, str) else f"[{p}]" for p in hata.absolute_path)
        hatalar.append(f"{yol}: {hata.message}")
    return hatalar


def paket_gecerli(paket: dict, ad: str = PAKET_SEMASI) -> bool:
    """True if the packet satisfies the schema."""
    return not paket_hatalari(paket, ad)
