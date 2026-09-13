"""The collection service: `POST /paket`, and the health endpoint next to it.

Item 10 of track A's task list: the endpoint that receives packets, validates
them, adds `alindi_zaman`, and writes them to the database. Everything else in
this package exists to serve those four verbs.

Three design points that are visible from the outside:

* **The endpoint parses the body itself** instead of declaring a Pydantic
  parameter. FastAPI would answer a malformed packet with its own 422 and its own
  error shape; the contract owner is `/sozlesmeler/modul_paketi.schema.json`, so
  the schema validates first and a rejection is a 400 whose `gerekce` quotes the
  schema. The producer then reads one explanation, not two.
* **`alindi_zaman` is stamped here.** Section 11: the module owns `zaman`, the
  collector owns `alindi_zaman`, and the difference between them is the module
  clock drift scenario 7 claims to expose. Trusting the module's clock for both
  would delete that signal.
* **Storage runs in the thread pool.** Both backends do blocking I/O, so the
  handler awaits them through `run_in_threadpool`: one slow database write cannot
  stall the event loop and with it every other module's uplink.
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .dogrulama import paket_hatalari
from .kayit import Kayit, kayit_olustur
from .modeller import ModulPaketi, YazimSonucu
from .sozlesme import zaman_yaz

SURUM = "1.0.0"

kutuk = logging.getLogger("toplama")

#: Rejections are logged at most this often per module, so a producer stuck in a
#: loop cannot fill the disk with identical lines during a demo.
KUTUK_ARALIK_S = 5.0


def _simdi() -> datetime:
    """Collector clock. UTC, second precision — the contract's resolution."""
    return datetime.now(timezone.utc).replace(microsecond=0)


def uygulama_olustur(kayit: Kayit | None = None) -> FastAPI:
    """Build the app. Pass `kayit` to inject a backend; otherwise read the env.

    Injection is what lets the test suite run the real endpoint against a
    temporary directory: the service under test is the shipped one, not a
    lookalike with the storage stubbed out.
    """
    depo = kayit or kayit_olustur()
    son_kutuk: dict[str, float] = {}

    @asynccontextmanager
    async def yasam(_: FastAPI):
        depo.baslat()
        kutuk.info("toplama %s ready, kayit=%s", SURUM, depo.ad)
        try:
            yield
        finally:
            depo.kapat()

    uygulama = FastAPI(
        title="Grid-Up toplama servisi",
        version=SURUM,
        description=(
            "Collects module packets (contract 2), validates them against "
            "/sozlesmeler, stamps alindi_zaman and writes olcum / termal_ozet / "
            "termal_kare. On-premise only; no cloud dependency in the path."
        ),
        lifespan=yasam,
    )
    uygulama.state.kayit = depo

    @uygulama.post(
        "/paket",
        status_code=201,
        response_model=YazimSonucu,
        summary="Receive one module packet",
        responses={400: {"description": "Packet rejected; body carries the reasons in `gerekce`."}},
    )
    async def paket_al(istek: Request, yanit: Response) -> Any:
        ham = _govde(await istek.body())
        if isinstance(ham, JSONResponse):
            return ham

        hatalar = paket_hatalari(ham)
        if hatalar:
            return _reddet(ham, hatalar, son_kutuk)

        # The schema has already accepted the packet, so this cannot normally
        # fail — but the models carry the enum-derived rules (unit pairing,
        # plausibility range) and a disagreement between the two layers must
        # surface as a rejection rather than as a corrupt row.
        try:
            paket = ModulPaketi.model_validate(ham)
        except Exception as hata:
            return _reddet(ham, [f"model: {hata}"], son_kutuk)

        alindi_zaman = _simdi()
        sonuc = await run_in_threadpool(depo.yaz, paket, alindi_zaman)
        if sonuc.yinelenen:
            # Nothing new was stored, so this is not a creation. A retransmitting
            # module gets a 200 and can stop retrying.
            yanit.status_code = 200
        return sonuc

    @uygulama.get("/saglik", summary="Service and storage health")
    async def saglik() -> dict[str, Any]:
        # The postgres backend's health check is a round trip to the database, so
        # it goes to the thread pool like any other blocking call.
        depo_saglik = await run_in_threadpool(depo.saglik)
        return {
            "servis": "toplama",
            "surum": SURUM,
            "durum": "ayakta",
            "zaman": zaman_yaz(_simdi()),
            "depo": depo_saglik,
            "yazilan": depo.sayac.sozluk(),
        }

    return uygulama


def _govde(veri: bytes) -> Any:
    """Body bytes -> parsed JSON, with a contract-shaped 400 on failure."""
    if not veri:
        return JSONResponse(status_code=400, content={"hata": "bos_govde", "gerekce": ["request body is empty"]})
    try:
        return json.loads(veri)
    except json.JSONDecodeError as hata:
        return JSONResponse(
            status_code=400,
            content={"hata": "gecersiz_json", "gerekce": [f"line {hata.lineno} column {hata.colno}: {hata.msg}"]},
        )


def _reddet(ham: Any, hatalar: list[str], son_kutuk: dict[str, float]) -> JSONResponse:
    """Build the 400 and log it, rate-limited per module.

    The response names the contract it failed, because the producer's next
    question is always "against what?".
    """
    modul_id = ham.get("modul_id") if isinstance(ham, dict) else None
    anahtar = str(modul_id)
    simdi = datetime.now(timezone.utc).timestamp()
    if simdi - son_kutuk.get(anahtar, 0.0) > KUTUK_ARALIK_S:
        son_kutuk[anahtar] = simdi
        kutuk.warning("paket reddedildi modul_id=%s: %s", modul_id, hatalar[0])
    return JSONResponse(
        status_code=400,
        content={
            "hata": "gecersiz_paket",
            "sozlesme": "modul_paketi.schema.json",
            "modul_id": modul_id,
            # Capped: a packet that is wrong in fifty ways is wrong in one way
            # fifty times, and the producer only needs the first few.
            "gerekce": hatalar[:10],
            "hata_sayisi": len(hatalar),
        },
    )


#: Module-level app for `uvicorn toplama.uygulama:uygulama`. Built from the
#: environment (TOPLAMA_KAYIT, DATABASE_URL, TOPLAMA_DOSYA_DIZIN); no connection
#: is opened until start-up, so importing this module is always cheap.
uygulama = uygulama_olustur()


def main() -> None:  # pragma: no cover - process entry point
    """`python -m toplama` — run the service with uvicorn."""
    import uvicorn

    uvicorn.run(
        "toplama.uygulama:uygulama",
        host=os.environ.get("TOPLAMA_HOST", "0.0.0.0"),
        port=int(os.environ.get("TOPLAMA_PORT", "8000")),
        log_level=os.environ.get("TOPLAMA_KUTUK", "info"),
    )
