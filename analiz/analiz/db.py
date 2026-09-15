"""Database connection and schema management.

Track B talks to PostgreSQL and to nothing else — decision K1's whole point is
that the only contact surface with track A is a set of tables. There is no HTTP
client here, no queue, and no import of another track's code.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import resources
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from .ayar import Ayar, VeritabaniAyari

__all__ = ["baglan", "sema_kur", "sema_surumu", "MIGRASYONLAR"]

_gunluk = logging.getLogger(__name__)

#: Applied in order. 000 restates the contract tables so track B can run
#: standalone; 100 creates track B's own. See the header of each file.
MIGRASYONLAR: tuple[str, ...] = ("000_sozlesme.sql", "100_analiz.sql")


@contextmanager
def baglan(ayar: Ayar | VeritabaniAyari) -> Iterator[psycopg.Connection]:
    """Open a connection with the session settings every caller needs.

    `search_path` is set once here rather than schema-qualifying several hundred
    identifiers across the query modules. The statement timeout is configuration
    (`sorgu_zaman_asimi_ms`) because a turn that outgrows it is the scale limit
    section 8 asks us to measure, and it should announce itself as an error
    instead of as a turn that quietly takes longer than the scan period.
    """
    vt = ayar.veritabani if isinstance(ayar, Ayar) else ayar
    with psycopg.connect(vt.dsn, row_factory=dict_row) as baglanti:
        with baglanti.cursor() as imlec:
            imlec.execute(f"SET search_path TO {vt.sema}, public")
            imlec.execute(f"SET statement_timeout = {int(vt.sorgu_zaman_asimi_ms)}")
        yield baglanti


def _migrasyon_metni(ad: str) -> str:
    """Read one migration, from the installed package or the source tree."""
    try:
        # joinpath() takes a single segment on 3.11's MultiplexedPath, so chain.
        kok = resources.files(__package__).joinpath("migrations")
        return kok.joinpath(ad).read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError):  # pragma: no cover - dev fallback
        return (Path(__file__).parent / "migrations" / ad).read_text(encoding="utf-8")


def sema_kur(baglanti: psycopg.Connection) -> None:
    """Apply every migration. Idempotent — each file is `IF NOT EXISTS` throughout.

    There is no version check before applying: the point of making the files
    idempotent is that "have I run this?" stops being a question anyone has to
    answer correctly, including during a demo at 3 a.m.
    """
    for ad in MIGRASYONLAR:
        _gunluk.debug("applying migration %s", ad)
        with baglanti.cursor() as imlec:
            imlec.execute(_migrasyon_metni(ad))  # type: ignore[arg-type]
    baglanti.commit()


def sema_surumu(baglanti: psycopg.Connection) -> int:
    """Highest applied migration number, or 0 on an empty database."""
    with baglanti.cursor() as imlec:
        imlec.execute(
            "SELECT coalesce(max(surum), 0) AS surum FROM gridup.sema_surum"
        )
        satir = imlec.fetchone()
    return int(satir["surum"]) if satir else 0
