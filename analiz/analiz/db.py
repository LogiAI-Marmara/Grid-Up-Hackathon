"""Database connection and schema management.

Track B talks to PostgreSQL and to nothing else — decision K1's whole point is
that the only contact surface with track A is a set of tables. There is no HTTP
client here, no queue, and no import of another track's code.

SCHEMA OWNERSHIP. The shared tables (`saha`, `pano`, `modul`, `olcum`,
`termal_ozet`, `termal_kare`, `modul_durum`) are defined once, in track A's
`toplama/migrations/`. Track B never defines them: `sema_kur` applies track A's
files in order and then track B's own `100_analiz.sql`, which holds only
`anomali`, `anomali_gecis`, `tarama_imleci` and the indexes track B needs on the
shared tables. A second copy of the schema in this package was removed in the
integration phase precisely because two copies drift.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import resources
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from .ayar import Ayar, VeritabaniAyari

__all__ = [
    "baglan",
    "sema_kur",
    "sema_surumu",
    "toplama_migrasyon_dizini",
    "toplama_migrasyonlari",
    "MIGRASYONLAR",
]

_gunluk = logging.getLogger(__name__)

#: Track B's own migrations, applied after track A's. Numbered from 100 so
#: track A can keep adding 004, 005 ... without asking what is free.
MIGRASYONLAR: tuple[str, ...] = ("100_analiz.sql",)

#: Environment variable naming the directory that holds track A's migrations.
#: Defaults to `<repo>/toplama/migrations`, resolved relative to this file.
TOPLAMA_MIGRASYON_ORTAM = "GRIDUP_TOPLAMA_MIGRASYON_DIZINI"


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


def toplama_migrasyon_dizini() -> Path:
    """Where track A's migrations live.

    `GRIDUP_TOPLAMA_MIGRASYON_DIZINI` when set; otherwise `toplama/migrations`
    at the repository root, which is two levels above this package. The
    override exists for an installed package (no repository around it) and for
    tests that point at an exported copy of track A's files.
    """
    ortam = os.environ.get(TOPLAMA_MIGRASYON_ORTAM)
    if ortam:
        return Path(ortam)
    return Path(__file__).resolve().parents[2] / "toplama" / "migrations"


def toplama_migrasyonlari(dizin: Path | None = None) -> list[Path]:
    """Track A's migration files, in application order (lexical on file name).

    Raises rather than returning an empty list: a schema with none of the shared
    tables is not a schema track B can run against, and "applied zero files
    successfully" would be a confusing way to find that out.
    """
    dizin = dizin or toplama_migrasyon_dizini()
    if not dizin.is_dir():
        raise FileNotFoundError(
            f"track A's migrations directory not found: {dizin} "
            f"(set {TOPLAMA_MIGRASYON_ORTAM} or run from a checkout containing toplama/migrations)"
        )
    dosyalar = sorted(p for p in dizin.iterdir() if p.suffix == ".sql" and p.is_file())
    if not dosyalar:
        raise FileNotFoundError(f"no .sql files in {dizin}")
    return dosyalar


def _migrasyon_metni(ad: str) -> str:
    """Read one of track B's own migrations, from the installed package or the source tree."""
    try:
        # joinpath() takes a single segment on 3.11's MultiplexedPath, so chain.
        kok = resources.files(__package__).joinpath("migrations")
        return kok.joinpath(ad).read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError):  # pragma: no cover - dev fallback
        return (Path(__file__).parent / "migrations" / ad).read_text(encoding="utf-8")


def sema_kur(baglanti: psycopg.Connection, toplama_dizini: Path | None = None) -> None:
    """Apply track A's migrations in order, then track B's. Idempotent.

    There is no version check before applying: every file is `IF NOT EXISTS`
    throughout, so "have I run this?" stops being a question anyone has to
    answer correctly, including during a demo at 3 a.m.
    """
    for yol in toplama_migrasyonlari(toplama_dizini):
        _gunluk.debug("applying track A migration %s", yol.name)
        with baglanti.cursor() as imlec:
            imlec.execute(yol.read_text(encoding="utf-8"))  # type: ignore[arg-type]
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
