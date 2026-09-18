"""Integration item 1 — module health (modul_durum) is recorded per packet.

Requirements from integration document:
- Table `gridup.modul_durum` with columns:
  modul_id, zaman, besleme, sinyal, yazilim_surumu, alindi_zaman
- Primary key: (modul_id, zaman)
- Constraints:
  - besleme IN ('sebeke', 'yedek')
  - sinyal BETWEEN -120 AND 0
  - yazilim_surumu regex semver
- Recorded per packet so that:
  - exact power outage transition time is preserved (sebeke -> yedek)
  - radio signal strength degradation trend is traceable (scenario 7)
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from toplama.kayit import DosyaKayit, PostgresKayit
from toplama.modeller import ModulDurum, ModulPaketi

DSN = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
MODUL = "TR041-P01-M3"


def _sema_hazir() -> bool:
    """True when a migration-built schema (5 or later) is reachable."""
    if not DSN:
        return False
    try:
        import psycopg

        with psycopg.connect(DSN, connect_timeout=3) as baglanti, baglanti.cursor() as imlec:
            imlec.execute("SELECT max(surum) FROM gridup.sema_surum")
            satir = imlec.fetchone()
        return bool(satir and satir[0] and satir[0] >= 5)
    except Exception:
        return False


pytestmark_db = pytest.mark.skipif(not _sema_hazir(), reason="no migrated schema (>=5) reachable (TEST_DATABASE_URL)")


def _ornek_paket(
    *,
    zaman: datetime | None = None,
    besleme: str = "sebeke",
    sinyal: int = -72,
    surum: str = "1.0.3",
) -> ModulPaketi:
    zaman_ = zaman or datetime(2026, 9, 14, 10, 0, 0, tzinfo=timezone.utc)
    return ModulPaketi(
        modul_id=MODUL,
        zaman=zaman_,
        olcumler=[
            {
                "modul_id": MODUL,
                "zaman": zaman_,
                "olcum_tipi": "ortam_sicaklik",
                "deger": 32.5,
                "birim": "C",
                "kalite": "iyi",
            }
        ],
        modul_durum={"besleme": besleme, "sinyal": sinyal, "yazilim_surumu": surum},
    )


# --------------------------------------------------------------------------
# Dosya backend tests
# --------------------------------------------------------------------------


def test_dosya_backendi_modul_durum_yazar_ve_yinelenen_engeller(tmp_path):
    depo = DosyaKayit(tmp_path)
    depo.baslat()
    alindi = datetime.now(timezone.utc)

    paket = _ornek_paket()
    sonuc = depo.yaz(paket, alindi)
    assert sonuc.modul_durum == 1
    assert sonuc.yinelenen is False

    satirlar = depo.oku("modul_durum")
    assert len(satirlar) == 1
    d = satirlar[0]
    assert d["modul_id"] == MODUL
    assert d["besleme"] == "sebeke"
    assert d["sinyal"] == -72
    assert d["yazilim_surumu"] == "1.0.3"
    assert "alindi_zaman" in d

    # Replay same packet
    sonuc2 = depo.yaz(paket, alindi)
    assert sonuc2.modul_durum == 0
    assert sonuc2.yinelenen is True
    assert len(depo.oku("modul_durum")) == 1


# --------------------------------------------------------------------------
# Postgres backend tests
# --------------------------------------------------------------------------


@pytest.fixture()
def depo_pg():
    import psycopg

    kayit = PostgresKayit(DSN)
    kayit.baslat()

    def temizle():
        with psycopg.connect(DSN, autocommit=True) as baglanti, baglanti.cursor() as imlec:
            imlec.execute("DELETE FROM gridup.modul_durum WHERE modul_id = %s", (MODUL,))
            imlec.execute("DELETE FROM gridup.olcum WHERE modul_id = %s", (MODUL,))
            imlec.execute("DELETE FROM gridup.modul WHERE modul_id = %s", (MODUL,))

    temizle()
    yield kayit
    temizle()
    kayit.kapat()


@pytestmark_db
def test_postgres_modul_durum_yazar(depo_pg):
    import psycopg

    alindi = datetime.now(timezone.utc)
    t = datetime(2026, 9, 14, 10, 0, 0, tzinfo=timezone.utc)
    paket = _ornek_paket(zaman=t, besleme="sebeke", sinyal=-68, surum="1.0.4")
    sonuc = depo_pg.yaz(paket, alindi)

    assert sonuc.modul_durum == 1
    assert sonuc.yinelenen is False

    with psycopg.connect(DSN) as baglanti, baglanti.cursor() as imlec:
        imlec.execute(
            "SELECT modul_id, zaman, besleme, sinyal, yazilim_surumu, alindi_zaman "
            "FROM gridup.modul_durum WHERE modul_id = %s AND zaman = %s",
            (MODUL, t),
        )
        satir = imlec.fetchone()
        assert satir is not None
        assert satir[0] == MODUL
        assert satir[1] == t
        assert satir[2] == "sebeke"
        assert satir[3] == -68
        assert satir[4] == "1.0.4"
        assert satir[5] is not None


@pytestmark_db
def test_postgres_modul_durum_yinelenen_paket_yazmaz(depo_pg):
    import psycopg

    alindi = datetime.now(timezone.utc)
    t = datetime(2026, 9, 14, 10, 0, 0, tzinfo=timezone.utc)
    paket = _ornek_paket(zaman=t)

    ilk = depo_pg.yaz(paket, alindi)
    assert ilk.modul_durum == 1

    ikinci = depo_pg.yaz(paket, alindi)
    assert ikinci.modul_durum == 0
    assert ikinci.yinelenen is True

    with psycopg.connect(DSN) as baglanti, baglanti.cursor() as imlec:
        imlec.execute("SELECT count(*) FROM gridup.modul_durum WHERE modul_id = %s", (MODUL,))
        assert imlec.fetchone()[0] == 1


@pytestmark_db
def test_postgres_modul_durum_zaman_serisi_ve_besleme_kaybi(depo_pg):
    """Scenario 7 evidence: power failure and signal degradation over consecutive packets."""
    import psycopg

    t0 = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 9, 14, 12, 0, 30, tzinfo=timezone.utc)
    t2 = datetime(2026, 9, 14, 12, 1, 0, tzinfo=timezone.utc)

    # 1. Normal mains operation
    depo_pg.yaz(_ornek_paket(zaman=t0, besleme="sebeke", sinyal=-65), t0)
    # 2. Power loss occurs: module switches to backup supercap
    depo_pg.yaz(_ornek_paket(zaman=t1, besleme="yedek", sinyal=-80), t1)
    # 3. Running on backup, signal further degrades
    depo_pg.yaz(_ornek_paket(zaman=t2, besleme="yedek", sinyal=-95), t2)

    with psycopg.connect(DSN) as baglanti, baglanti.cursor() as imlec:
        imlec.execute(
            "SELECT zaman, besleme, sinyal FROM gridup.modul_durum "
            "WHERE modul_id = %s ORDER BY zaman ASC",
            (MODUL,),
        )
        satirlar = imlec.fetchall()
        assert len(satirlar) == 3
        # Exact transition time from sebeke to yedek is preserved
        assert satirlar[0] == (t0, "sebeke", -65)
        assert satirlar[1] == (t1, "yedek", -80)
        assert satirlar[2] == (t2, "yedek", -95)


@pytestmark_db
def test_postgres_modul_durum_check_kisitlari():
    import psycopg

    with psycopg.connect(DSN, autocommit=True) as baglanti, baglanti.cursor() as imlec:
        imlec.execute(
            "INSERT INTO gridup.modul (modul_id, saha_kodu, pano_kodu, modul_kodu) "
            "VALUES (%s, 'TR041', 'P01', 'M3') ON CONFLICT DO NOTHING",
            (MODUL,),
        )
        t = datetime(2026, 9, 14, 15, 0, 0, tzinfo=timezone.utc)

        # Invalid besleme
        with pytest.raises(psycopg.errors.CheckViolation):
            imlec.execute(
                "INSERT INTO gridup.modul_durum (modul_id, zaman, besleme, sinyal, yazilim_surumu) "
                "VALUES (%s, %s, 'aku', -70, '1.0.0')",
                (MODUL, t),
            )

        # Signal > 0
        with pytest.raises(psycopg.errors.CheckViolation):
            imlec.execute(
                "INSERT INTO gridup.modul_durum (modul_id, zaman, besleme, sinyal, yazilim_surumu) "
                "VALUES (%s, %s, 'sebeke', 5, '1.0.0')",
                (MODUL, t),
            )

        # Signal < -120
        with pytest.raises(psycopg.errors.CheckViolation):
            imlec.execute(
                "INSERT INTO gridup.modul_durum (modul_id, zaman, besleme, sinyal, yazilim_surumu) "
                "VALUES (%s, %s, 'sebeke', -125, '1.0.0')",
                (MODUL, t),
            )

        # Invalid version string
        with pytest.raises(psycopg.errors.CheckViolation):
            imlec.execute(
                "INSERT INTO gridup.modul_durum (modul_id, zaman, besleme, sinyal, yazilim_surumu) "
                "VALUES (%s, %s, 'sebeke', -70, 'v1.0')",
                (MODUL, t),
            )
