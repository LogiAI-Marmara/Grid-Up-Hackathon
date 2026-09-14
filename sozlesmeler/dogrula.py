#!/usr/bin/env python3
"""Check that the JSON Schemas and `enums.py` still agree.

"Single source of truth" is a claim, not a property — nothing stops someone
editing a vocabulary in one file and not the other, and a mismatched enum fails
silently at 3 a.m. rather than loudly at build time. This script is the thing
that makes the claim true. Run it before pushing a contract change:

    python dogrula.py

Exit code 0 = contracts consistent. Standard library only; if `jsonschema` is
installed the embedded examples are validated too, otherwise that step is
skipped with a note.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import enums

KLASOR = Path(__file__).resolve().parent
SEMALAR = ["olcum_kaydi.schema.json", "modul_paketi.schema.json", "anomali.schema.json"]

# Every enum literal that may legally appear in a schema, keyed by vocabulary name.
SOZLUKLER = {
    "olcum_tipi": [e.value for e in enums.OlcumTipi],
    "seviye": [e.value for e in enums.Seviye],
    "tip": [e.value for e in enums.Tip],
    "kalite": [e.value for e in enums.Kalite],
    "durum": [e.value for e in enums.Durum],
    "besleme": [e.value for e in enums.Besleme],
    "birim": [e.value for e in enums.Birim],
}

DESENLER = {
    enums.MODUL_ID_DESEN.pattern: "modul_id",
    enums.ZAMAN_DESEN.pattern: "zaman",
}


def _dolas(dugum, yol="$"):
    """Yield (json_pointer, node) for every dict in the document."""
    if isinstance(dugum, dict):
        yield yol, dugum
        for anahtar, deger in dugum.items():
            yield from _dolas(deger, f"{yol}.{anahtar}")
    elif isinstance(dugum, list):
        for i, deger in enumerate(dugum):
            yield from _dolas(deger, f"{yol}[{i}]")


def enum_denetle(ad: str, belge: dict) -> list[str]:
    """Every `enum` array in the schema must come from a vocabulary in enums.py.

    A field declaration must list the vocabulary in full. Inside an `if` branch a
    partial list is legitimate (that is how "these three types are measured in
    Celsius" is expressed), so there only the "no unknown values" rule applies.
    """
    hatalar = []
    bulunan = set()
    for yol, dugum in _dolas(belge):
        secenekler = dugum.get("enum")
        if not isinstance(secenekler, list):
            continue
        degerler = set(map(str, secenekler))
        kosul_ici = ".if." in yol
        kapsayan = [k for k, v in SOZLUKLER.items() if degerler <= set(v)]
        if kapsayan:
            ad_sozluk = kapsayan[0]
            bulunan.add(ad_sozluk)
            if not kosul_ici and degerler != set(SOZLUKLER[ad_sozluk]):
                eksik = sorted(set(SOZLUKLER[ad_sozluk]) - degerler)
                hatalar.append(f"{ad} {yol}: '{ad_sozluk}' incomplete, missing {eksik}")
            continue
        # Contains values no vocabulary knows about — name the closest one.
        yakin = max(SOZLUKLER, key=lambda k: len(set(SOZLUKLER[k]) & degerler))
        fazla = sorted(degerler - set(SOZLUKLER[yakin]))
        if set(SOZLUKLER[yakin]) & degerler:
            hatalar.append(f"{ad} {yol}: values unknown to '{yakin}': {fazla}")
        else:
            hatalar.append(f"{ad} {yol}: enum {secenekler} matches no vocabulary in enums.py")
    if bulunan:
        print(f"  {ad}: vocabularies {', '.join(sorted(bulunan))}")
    return hatalar


def desen_denetle(ad: str, belge: dict) -> list[str]:
    """Any property named modul_id / zaman must carry the canonical regex."""
    hatalar = []
    for yol, dugum in _dolas(belge):
        if not yol.endswith((".modul_id", ".zaman")) or "pattern" not in dugum:
            continue
        alan = yol.rsplit(".", 1)[1]
        beklenen = enums.MODUL_ID_DESEN.pattern if alan == "modul_id" else enums.ZAMAN_DESEN.pattern
        if dugum["pattern"] != beklenen:
            hatalar.append(
                f"{ad} {yol}: pattern differs from enums.py\n"
                f"      schema:  {dugum['pattern']}\n"
                f"      enums.py:{beklenen}"
            )
    return hatalar


def termal_denetle(ad: str, belge: dict) -> list[str]:
    """The frame length and quadrant count must match the geometry constants."""
    hatalar = []
    for yol, dugum in _dolas(belge):
        if yol.endswith(".termal_kare"):
            for anahtar in ("minItems", "maxItems"):
                if dugum.get(anahtar) != enums.TERMAL_PIKSEL:
                    hatalar.append(
                        f"{ad} {yol}.{anahtar}: {dugum.get(anahtar)} != {enums.TERMAL_PIKSEL}"
                    )
        if yol.endswith(".bolge_ort"):
            for anahtar in ("minItems", "maxItems"):
                if dugum.get(anahtar) != enums.TERMAL_BOLGE_SAYISI:
                    hatalar.append(
                        f"{ad} {yol}.{anahtar}: {dugum.get(anahtar)} != {enums.TERMAL_BOLGE_SAYISI}"
                    )
    return hatalar


def ornek_denetle(belgeler: dict[str, dict]) -> list[str]:
    """Validate each schema's own `examples` against the schema, if jsonschema exists."""
    try:
        import jsonschema
        from referencing import Registry, Resource
    except ImportError:
        print("  (jsonschema not installed — example validation skipped)")
        return []

    kayit = Registry().with_resources(
        [(ad, Resource.from_contents(belge)) for ad, belge in belgeler.items()]
    )
    hatalar = []
    for ad, belge in belgeler.items():
        dogrulayici = jsonschema.Draft202012Validator(belge, registry=kayit)
        for i, ornek in enumerate(belge.get("examples", [])):
            for hata in dogrulayici.iter_errors(ornek):
                hatalar.append(f"{ad} examples[{i}]: {hata.message} at {list(hata.path)}")
        print(f"  {ad}: {len(belge.get('examples', []))} example(s) validated")
    return hatalar


def main() -> int:
    belgeler = {}
    for ad in SEMALAR:
        yol = KLASOR / ad
        if not yol.exists():
            print(f"MISSING: {ad}", file=sys.stderr)
            return 1
        belgeler[ad] = json.loads(yol.read_text(encoding="utf-8"))

    hatalar: list[str] = []

    print("vocabularies")
    for ad, belge in belgeler.items():
        hatalar += enum_denetle(ad, belge)

    print("patterns and geometry")
    for ad, belge in belgeler.items():
        hatalar += desen_denetle(ad, belge)
        hatalar += termal_denetle(ad, belge)
    if not hatalar:
        print(f"  modul_id / zaman patterns and 32x{enums.TERMAL_SATIR}={enums.TERMAL_PIKSEL} geometry consistent")

    print("examples")
    hatalar += ornek_denetle(belgeler)

    if hatalar:
        print("\nFAIL")
        for hata in hatalar:
            print(f"  - {hata}")
        return 1
    print("\nOK — schemas and enums.py agree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
