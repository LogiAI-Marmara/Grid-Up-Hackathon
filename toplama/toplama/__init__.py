"""Grid-Up track A — collection (ingest) service.

Item 10 of the task list: the endpoint that receives module packets, validates
them against the contracts in `/sozlesmeler`, stamps `alindi_zaman`, and writes
them into the schema in `../migrations`.

    uvicorn toplama.uygulama:uygulama --host 0.0.0.0 --port 8000
    python -m toplama                              # same thing

Layout:

* `sozlesme`  — imports the shared vocabularies; nothing is restated here.
* `dogrulama` — JSON Schema validation plus the cross-field contract rules.
* `modeller`  — typed models for contracts ① and ②, derived from the enums.
* `kayit`     — storage backends: `postgres` (the real target) and `dosya`
                (JSONL append, so the service runs and is testable with no DB).
* `uygulama`  — the FastAPI app.
"""

from __future__ import annotations

from .kayit import DosyaKayit, Kayit, KayitAyar, PostgresKayit, Satirlar, kayit_olustur, satirlar
from .modeller import ModulDurum, ModulPaketi, OlcumKaydi, TermalOzet, YazimSonucu
from .uygulama import SURUM, uygulama_olustur

__version__ = SURUM

__all__ = [
    "__version__",
    "SURUM",
    "uygulama_olustur",
    # models
    "ModulPaketi",
    "OlcumKaydi",
    "TermalOzet",
    "ModulDurum",
    "YazimSonucu",
    # storage
    "Kayit",
    "KayitAyar",
    "DosyaKayit",
    "PostgresKayit",
    "Satirlar",
    "satirlar",
    "kayit_olustur",
]
