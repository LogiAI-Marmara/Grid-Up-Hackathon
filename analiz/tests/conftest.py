"""Shared test fixtures.

Two databases, on purpose:

  `baglanti`        function-scoped, truncated between tests. Small, explicit
                    fixtures written by the test itself, so a failure points at
                    one behaviour.
  `senaryo_vt`      session-scoped, built once from the full scenario set and
                    then left alone. It is the end-to-end article: real rows,
                    real scan turns, real episodes — and it is deliberately NOT
                    dropped at the end of the run, so the episode and journal
                    tables can be inspected with psql after the suite finishes.

Both are real PostgreSQL. There is no mocked database anywhere in this suite:
the scan loop's range semantics, the partial unique index that enforces episode
identity, and the SQL that computes the baseline are the things most likely to
be wrong, and a fake database would test none of them.
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from analiz.ayar import Ayar
from analiz.db import baglan, sema_kur
from analiz.dogrulama import dogrulama_ayari, kos, oynat
from analiz.fikstur import Fikstur

#: Override with GRIDUP_TEST_DSN / GRIDUP_SENARYO_DSN to point at another server.
TEST_DSN = os.environ.get("GRIDUP_TEST_DSN", "postgresql:///gridup_analiz_test")
SENARYO_DSN = os.environ.get("GRIDUP_SENARYO_DSN", "postgresql:///gridup_analiz_senaryo")
KORTEST_DSN = os.environ.get("GRIDUP_KORTEST_DSN", "postgresql:///gridup_analiz_kortest")

#: A fixed instant, so every run of the suite produces the same numbers. Not
#: `now()`: the fixtures contain daily load and temperature cycles, and a suite
#: whose result depends on the hour it is run at is a suite that fails at 3 a.m.
SABIT_AN = datetime(2026, 9, 15, 9, 40, 0, tzinfo=timezone.utc)


def _veritabani_kur(dsn: str) -> None:
    """Drop and recreate a database from scratch."""
    ad = dsn.rsplit("/", 1)[-1]
    subprocess.run(["dropdb", "--if-exists", ad], check=True, capture_output=True)
    subprocess.run(["createdb", ad], check=True, capture_output=True)


@pytest.fixture(scope="session")
def test_dsn() -> str:
    _veritabani_kur(TEST_DSN)
    with psycopg.connect(TEST_DSN) as baglanti:
        sema_kur(baglanti)
    return TEST_DSN


@pytest.fixture
def ayar(test_dsn: str) -> Ayar:
    """Test configuration.

    Only the three knobs a test has to control differ from production defaults:
    the safety margin and the range cap (see `dogrulama_ayari` for why), and a
    cold-start lookback long enough to reach fixtures written weeks back.
    """
    return dogrulama_ayari(test_dsn)


@pytest.fixture
def baglanti(ayar: Ayar):
    """A clean connection: every table emptied, sequences reset."""
    with baglan(ayar) as b:
        with b.cursor() as imlec:
            imlec.execute(
                "TRUNCATE gridup.anomali_gecis, gridup.anomali, gridup.tarama_imleci, "
                "gridup.olcum, gridup.termal_kare, gridup.termal_ozet, "
                "gridup.modul, gridup.pano, gridup.saha RESTART IDENTITY CASCADE"
            )
            imlec.execute("ALTER SEQUENCE gridup.anomali_sira RESTART WITH 1")
        b.commit()
        yield b


@pytest.fixture
def fikstur(baglanti) -> Fikstur:
    return Fikstur(baglanti)


@pytest.fixture
def an() -> datetime:
    """The fixed evaluation instant every test builds its timeline around."""
    return SABIT_AN


# --------------------------------------------------------------------------
# The end-to-end scenario database
# --------------------------------------------------------------------------


@pytest.fixture(scope="session")
def senaryo_vt():
    """Build the whole scenario set once and run the scan loop over it.

    Session-scoped because it writes about a quarter of a million rows and runs
    the real loop; doing that per test would make the suite unusable. Left in
    place afterwards so `psql -d gridup_analiz_senaryo` can be used to inspect
    what the run produced.
    """
    _veritabani_kur(SENARYO_DSN)
    ayar = dogrulama_ayari(SENARYO_DSN)
    with baglan(ayar) as baglanti:
        rapor = kos(baglanti, ayar, simdi=SABIT_AN, tur_sayisi=2)
        yield baglanti, rapor, ayar


@pytest.fixture(scope="session")
def kortest_vt():
    """The scenario set with the scan loop REPLAYED across it, turn by turn.

    Separate from `senaryo_vt`, and the difference is the whole point of having
    both. `senaryo_vt` runs a couple of turns at the end of the window: enough to
    prove each scenario is found, useless for saying *when*. Every episode there
    opens at the last measurement, so lead time comes out at roughly zero for
    everything — and lead time is the project's headline claim.

    This one steps the clock through the data the way it passes in the field, so
    an episode opens on the turn where the evidence first crossed a threshold.
    That costs about half a minute, which is why it is session-scoped and why the
    cheap fixture still exists for everything that does not need it.
    """
    from datetime import timedelta

    from analiz.db import sema_kur
    from analiz.fikstur import Fikstur
    from analiz.senaryolar import TESPIT_SAAT, etiket_uret, kur

    _veritabani_kur(KORTEST_DSN)
    ayar = dogrulama_ayari(KORTEST_DSN)
    with baglan(ayar) as baglanti:
        sema_kur(baglanti)
        kur(Fikstur(baglanti), SABIT_AN, gecmis_gun=15.0)
        oynat(
            baglanti,
            ayar,
            simdi=SABIT_AN,
            bas=SABIT_AN - timedelta(hours=TESPIT_SAAT),
            adim_dk=15.0,
        )
        yield baglanti, etiket_uret(SABIT_AN), ayar
