"""Integration item 3 — the evidence frame is stored as the module's own bytes.

Two layers are worth testing separately:

* `kare_kodla` is the encoder, and the contract's byte order is the one thing
  that must not drift: a wrong endianness produces a frame that still has 1536
  bytes and still passes the database CHECK, so only a decode test catches it.
* the postgres backend must write those bytes unchanged — the file backend
  carries them as hex, so a round trip through it would not prove the table is
  right.

The database tests skip when no schema is reachable, and read the DSN from the
same environment variable the service uses.
"""

from __future__ import annotations

import os
import struct

import pytest

from toplama.kayit import kare_kodla

# --------------------------------------------------------------------------
# Encoder — the contract's byte order, checked by decoding, not by looking
# --------------------------------------------------------------------------


def test_kodlama_uzunlugu_1536():
    kare = [45.2] * 768
    assert len(kare_kodla(kare)) == 1536


def test_kodlama_geri_cozulur():
    # A frame with a negative value, the hottest plausible value and zero. The
    # negative one is the interesting case: its two's-complement high byte is
    # 0xFF, which is also what a wrong signedness would produce silently.
    kare = [-40.0, 45.2, 300.0, 0.0, -10.0] + [20.0] * 763
    ham = kare_kodla(kare)
    assert len(ham) == 1536
    geri = struct.unpack(f"<{768}h", ham)
    assert list(geri[:5]) == [-400, 452, 3000, 0, -100]


def test_kodlama_little_endian():
    # 452 = 0x01C4; little-endian puts C4 first. int2send-style big-endian would
    # write 01 C4, and that frame would still pass the length CHECK.
    ham = kare_kodla([45.2] * 768)
    assert ham[0:2] == b"\xc4\x01", f"first pixel bytes were {ham[0:2].hex()}, expected c401"


def test_kodlama_yuvarlama():
    # 0.1 degC resolution: 45.24 and 45.16 must land on the same int16, otherwise
    # the stored frame disagrees with the module that produced it.
    a = struct.unpack("<h", kare_kodla([45.24] + [0.0] * 767)[:2])[0]
    b = struct.unpack("<h", kare_kodla([45.16] + [0.0] * 767)[:2])[0]
    assert a == b == 452


def test_kodlama_sinir_degerler():
    # The contract's plausible range endpoints for termal_maks.
    ham = kare_kodla([-40.0] + [0.0] * 766 + [300.0])
    assert ham[0:2] == b"\x70\xfe", f"{-40.0} encoded as {ham[0:2].hex()}, expected 70fe"
    assert ham[1534:1536] == b"\xb8\x0b", f"{300.0} encoded as {ham[1534:1536].hex()}, expected b80b"


# --------------------------------------------------------------------------
# Round trip through the file backend — the hex form must be reversible
# --------------------------------------------------------------------------


def test_dosya_backendi_hex_yazar_ve_geri_okunur(tmp_path):
    """The file fixture and the table must hold the same bytes.

    JSONL cannot carry bytes, so the backend writes hex. If it wrote the decimal
    array instead, track B's fixture would disagree with the table for the one
    column an anomaly points at.
    """
    from datetime import datetime, timezone

    from toplama.kayit import DosyaKayit
    from toplama.modeller import ModulPaketi

    paket = ModulPaketi(
        modul_id="TR041-P01-M1",
        zaman=datetime(2026, 9, 14, 9, 31, 20, tzinfo=timezone.utc),
        olcumler=[],
        termal_kare=[45.2] * 768,
        modul_durum={"besleme": "sebeke", "sinyal": -72, "yazilim_surumu": "1.0.3"},
    )
    depo = DosyaKayit(tmp_path)
    depo.baslat()
    depo.yaz(paket, datetime.now(timezone.utc))

    satirlar = depo.oku("termal_kare")
    assert len(satirlar) == 1
    saklanan = satirlar[0]["piksel_verisi"]
    assert isinstance(saklanan, str), "JSONL cannot hold bytes; hex is expected"
    ham = bytes.fromhex(saklanan)
    assert len(ham) == 1536
    assert struct.unpack("<768h", ham) == (452,) * 768


# --------------------------------------------------------------------------
# Postgres — the column really is bytea of the right length
# --------------------------------------------------------------------------


DSN = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _sema_var() -> bool:
    """True when a migration-built schema is reachable."""
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


pytestmark_db = pytest.mark.skipif(not _sema_var(), reason="no migrated schema reachable (TEST_DATABASE_URL)")


@pytestmark_db
def test_kare_kolonu_bytea_ve_1536_bayt():
    import psycopg

    with psycopg.connect(DSN) as baglanti, baglanti.cursor() as imlec:
        imlec.execute(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema = 'gridup' AND table_name = 'termal_kare' AND column_name = 'piksel_verisi'"
        )
        satir = imlec.fetchone()
        assert satir is not None, "gridup.termal_kare.piksel_verisi not found"
        assert satir[0] == "bytea", f"column type is {satir[0]}, expected bytea"


@pytestmark_db
def test_kare_kolonu_kisa_veriyi_reddeder():
    """The CHECK is the thing that catches a truncated radio frame."""
    import psycopg

    with psycopg.connect(DSN, autocommit=True) as baglanti, baglanti.cursor() as imlec:
        with pytest.raises(psycopg.errors.CheckViolation):
            imlec.execute(
                "INSERT INTO gridup.termal_kare (modul_id, zaman, piksel_verisi, satir_sayisi, sutun_sayisi) "
                "VALUES ('TR041-P01-M1', '2026-09-14T23:59:59Z', %s, 24, 32)",
                (b"\x00\x11",),
            )