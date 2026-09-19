"""Seed Track B's known scenarios into a fresh, isolated smoke database."""

import os
from datetime import datetime, timedelta, timezone

from psycopg.conninfo import conninfo_to_dict

from analiz.ayar import Ayar
from analiz.db import baglan
from analiz.dogrulama import oynat
from analiz.fikstur import Fikstur
from analiz.senaryolar import TESPIT_SAAT, kur
from analiz.tarama import Tarayici


def main() -> int:
    dsn = os.environ["GRIDUP_ANALIZ_VERITABANI_DSN"]
    if os.getenv("GRIDUP_SMOKE") != "1" or conninfo_to_dict(dsn).get("dbname") != "gridup_smoke":
        raise RuntimeError("smoke seeding requires isolated gridup_smoke database")
    ayar = Ayar.ortamdan().ile(tarama={"emniyet_payi_sn": 0.0, "azami_aralik_sn": 0.0})
    simdi = datetime.now(timezone.utc)
    with baglan(ayar) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM gridup.anomali")
            if cur.fetchone()["count"]:
                raise RuntimeError("smoke database is not empty")
        satir, _ = kur(Fikstur(conn), simdi, gecmis_gun=2)
        print(f"Seeded {satir} known measurement rows")
        oynat(conn, ayar, simdi=simdi, bas=simdi - timedelta(hours=TESPIT_SAAT), adim_dk=15.0)
        Tarayici(conn, ayar).tur(simdi=simdi)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
