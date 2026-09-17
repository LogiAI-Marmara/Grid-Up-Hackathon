"""The postgres write path — counts, retransmission, and the byte column.

These run against a real migrated schema and are skipped when none is reachable.
The environment variable is the same one the service reads, so a developer who
can start the collector can also run these.

What is covered here that the file-backend tests cannot cover:

* the frame really lands in a `bytea` column, read back byte-for-byte;
* `yinelenen` and the written-row counts come from the database, not from the
  backend's in-memory dedup set. The counting bug this file was written for
  (`executemany` + `fetchall` with no `returning=True`) only exists on this path.
"""

from __future__ import annotations

import os
import struct

import pytest

from toplama.kayit import PostgresKayit, kare_kodla

DSN = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
MODUL = "TR041-P01-M9"


def _sema_hazir() -> bool:
    """True when a migration-built schema (4 or later) is reachable."""
    if not DSN:
        return False
    try:
        import psycopg

        with psycopg.connect(DSN, connect_timeout=3) as baglanti, baglanti.cursor() as imlec:
            imlec.execute("SELECT max(surum) FROM gridup.sema_surum")
            satir = imlec.fetchone()
        return bool(satir and satir[0] and satir[0] >= 4)
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _sema_hazir(), reason="no migrated schema reachable (TEST_DATABASE_URL)")


@pytest.fixture()
def depo():
    """A postgres backend, with this test's rows removed before and after."""
    import psycopg

    kayit = PostgresKayit(DSN)
    kayit.baslat()

    def temizle():
        with psycopg.connect(DSN, autocommit=True) as baglanti, baglanti.cursor() as imlec:
            imlec.execute("DELETE FROM gridup.termal_kare WHERE modul_id = %s", (MODUL,))
            imlec.execute("DELETE FROM gridup.termal_ozet WHERE modul_id = %s", (MODUL,))
            imlec.execute("DELETE FROM gridup.olcum WHERE modul_id = %s", (MODUL,))
            imlec.execute("DELETE FROM gridup.modul WHERE modul_id = %s", (MODUL,))

    temizle()
    yield kayit
    temizle()
    kayit.kapat()


def _paket(kare=None, olcum_sayisi: int = 4):
    """A valid packet for this module, with a known frame."""
    from datetime import datetime, timezone

    from toplama.modeller import ModulPaketi

    zaman = datetime(2026, 9, 14, 10, 0, 0, tzinfo=timezone.utc)
    olcumler = []
    for i, (tip, deger, birim) in enumerate(
        [
            ("akim_l1", 310.0, "A"),
            ("akim_l2", 308.0, "A"),
            ("akim_l3", 309.0, "A"),
            ("ortam_sicaklik", 34.7, "C"),
        ][:olcum_sayisi]
    ):
        olcumler.append(
            {"modul_id": MODUL, "zaman": zaman, "olcum_tipi": tip, "deger": deger, "birim": birim, "kalite": "iyi"}
        )

    ozet = None
    if kare is not None:
        # The summary must agree with the frame at maks_konum, or validation
        # rejects the packet before it reaches the backend.
        en_sicak = max(range(len(kare)), key=lambda i: kare[i])
        satir, sutun = divmod(en_sicak, 32)
        ozet = {"maks": kare[en_sicak], "maks_konum": [sutun, satir], "bolge_ort": [30.0, 31.0, 32.0, 33.0]}

    return ModulPaketi(
        modul_id=MODUL,
        zaman=zaman,
        olcumler=olcumler,
        termal_ozet=ozet,
        termal_kare=kare,
        modul_durum={"besleme": "sebeke", "sinyal": -72, "yazilim_surumu": "1.0.3"},
    )


def _kare() -> list[float]:
    """768 values with a known hottest pixel at [14, 9]."""
    kare = [20.0] * 768
    kare[0], kare[1], kare[2] = -40.0, -10.0, 0.0
    kare[9 * 32 + 14] = 45.2
    return kare


# --------------------------------------------------------------------------
# Counting — the regression this file was written for
# --------------------------------------------------------------------------


def test_olcum_sayisi_dogru_raporlanir(depo):
    """`executemany` + RETURNING must report every inserted row, not crash.

    The previous implementation called `fetchall()` after `executemany` without
    `returning=True`, which raises "no result available" — so the postgres
    backend failed on every packet that carried a measurement. The file backend
    hid this, because it never touches psycopg.
    """
    from datetime import datetime, timezone

    sonuc = depo.yaz(_paket(olcum_sayisi=4), datetime.now(timezone.utc))
    assert sonuc.olcum == 4, f"4 measurement rows were sent, {sonuc.olcum} reported"
    assert sonuc.yinelenen is False


def test_yinelenen_paket_sifir_yazar(depo):
    """A retransmitting module is normal; replay must be a no-op, not an error."""
    from datetime import datetime, timezone

    alindi = datetime.now(timezone.utc)
    ilk = depo.yaz(_paket(olcum_sayisi=4), alindi)
    assert ilk.olcum == 4

    ikinci = depo.yaz(_paket(olcum_sayisi=4), alindi)
    assert ikinci.olcum == 0, "replaying the same packet must not insert measurements again"
    assert ikinci.yinelenen is True


def test_kismen_yinelenen_paket_yalniz_yenileri_sayar(depo):
    """Overlap is the interesting case: the count must be of inserted rows.

    Not of submitted rows, and not "all or nothing".
    """
    from datetime import datetime, timezone

    alindi = datetime.now(timezone.utc)
    assert depo.yaz(_paket(olcum_sayisi=2), alindi).olcum == 2
    # Same instant, four rows: two already stored, two new.
    assert depo.yaz(_paket(olcum_sayisi=4), alindi).olcum == 2


# --------------------------------------------------------------------------
# The frame column
# --------------------------------------------------------------------------


def test_kare_bytea_olarak_saklanir_ve_geri_cozulur(depo):
    """End to end: Python floats in, int16 bytes in the column, same values out."""
    from datetime import datetime, timezone

    kare = _kare()
    sonuc = depo.yaz(_paket(kare=kare), datetime.now(timezone.utc))
    assert sonuc.termal_kare == 1
    assert sonuc.kare_id is not None

    import psycopg

    with psycopg.connect(DSN) as baglanti, baglanti.cursor() as imlec:
        imlec.execute(
            "SELECT piksel_verisi, octet_length(piksel_verisi) FROM gridup.termal_kare WHERE kare_id = %s",
            (sonuc.kare_id,),
        )
        ham, bayt = imlec.fetchone()

    assert bayt == 1536
    assert ham == kare_kodla(kare), "the stored bytes must equal the encoder's output"
    geri = struct.unpack("<768h", ham)
    assert geri[0] == -400 and geri[1] == -100 and geri[2] == 0
    assert geri[9 * 32 + 14] == 452


def test_kare_yinelenirse_ayni_id_doner(depo):
    """`anomali.kanit.kare_id` must keep pointing at the frame that exists."""
    from datetime import datetime, timezone

    alindi = datetime.now(timezone.utc)
    ilk = depo.yaz(_paket(kare=_kare()), alindi)
    ikinci = depo.yaz(_paket(kare=_kare()), alindi)

    assert ilk.termal_kare == 1
    assert ikinci.termal_kare == 0
    assert ikinci.kare_id == ilk.kare_id, "a replayed frame must resolve to the stored one"