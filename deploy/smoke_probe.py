"""Send one real Track A simulator packet through the collector in a smoke run."""

import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone

sys.path.insert(0, "/app/modul-sim")
from modul_sim.runner import Filo, KosuAyar  # noqa: E402


def main() -> int:
    if os.getenv("GRIDUP_SMOKE") != "1":
        raise RuntimeError("smoke probe requires GRIDUP_SMOKE=1")
    filo = Filo(KosuAyar(modul_sayisi=15, sure_dk=0.5))
    fixture_ids = {
        "TR041-P01-M1", "TR041-P01-M2", "TR063-P02-M3",
        "TR074-P01-M1", "TR041-P02-M1", "TR063-P02-M4",
        "TR063-P02-M2", "TR063-P02-M1", "TR052-P02-M1",
    }
    modul = next(m for m in reversed(filo.moduller) if m.modul_id not in fixture_ids)
    paket = modul.ilerle(datetime.now(timezone.utc).replace(microsecond=0)).paket
    istek = urllib.request.Request(
        os.environ["TOPLAMA_URL"],
        data=json.dumps(paket).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(istek, timeout=20) as cevap:
        if cevap.status not in (200, 201):
            raise RuntimeError(f"collector HTTP {cevap.status}")
    detay_url = "http://analiz_api:8080/moduller/" + urllib.parse.quote(modul.modul_id)
    with urllib.request.urlopen(detay_url, timeout=20) as cevap:
        detay = json.load(cevap)
    if detay.get("modul_id") != modul.modul_id:
        raise RuntimeError(f"read API did not return simulator module {modul.modul_id}")
    print(f"Simulator -> collector -> read API: {modul.modul_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
