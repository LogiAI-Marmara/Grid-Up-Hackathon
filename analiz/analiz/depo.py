"""The scan cursor: where the last turn stopped.

Decision K1's bookkeeping. One row per named cursor, in the database rather than
in memory, so a restart resumes instead of starting over — and so it can be
rewound by hand, which section 3.4 lists as the first reason polling was chosen
over push: when the algorithm changes, the cursor goes back and the last N days
are scanned again. With a push design that is impossible, and during a hackathon
where the algorithm changes several times a day it is the difference between
re-testing in seconds and waiting for fresh data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import psycopg

from .ayar import Ayar

__all__ = ["Imlec", "ImlecDeposu"]

_gunluk = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Imlec:
    """A cursor's persisted state."""

    ad: str
    son_islenen: datetime
    tur_sayisi: int = 0
    son_tur: datetime | None = None
    son_tur_satir: int = 0
    son_tur_modul: int = 0


class ImlecDeposu:
    """Reads and writes `gridup.tarama_imleci`."""

    def __init__(self, baglanti: psycopg.Connection, ayar: Ayar) -> None:
        self._baglanti = baglanti
        self._ayar = ayar

    def oku(self, ad: str | None = None) -> Imlec:
        """The cursor's current position, creating it on first use.

        Cold start does not begin at the beginning of time: a detector started
        against a database with a month of history would spend its first turn
        pulling five million rows and its second one still behind. It begins
        `ilk_imlec_geri_sn` back, and a deliberate re-scan of older history is
        `geri_al`'s job — an explicit act, not an accident of first startup.
        """
        ad = ad or self._ayar.tarama.imlec_adi
        with self._baglanti.cursor() as imlec:
            imlec.execute(
                "SELECT ad, son_islenen, tur_sayisi, son_tur, son_tur_satir, son_tur_modul "
                "FROM gridup.tarama_imleci WHERE ad = %s",
                (ad,),
            )
            satir = imlec.fetchone()
            if satir is not None:
                return Imlec(**satir)

            baslangic = datetime.now(timezone.utc) - timedelta(
                seconds=self._ayar.tarama.ilk_imlec_geri_sn
            )
            imlec.execute(
                "INSERT INTO gridup.tarama_imleci (ad, son_islenen) VALUES (%s, %s) "
                "ON CONFLICT (ad) DO NOTHING",
                (ad, baslangic),
            )
        self._baglanti.commit()
        _gunluk.info("cursor %s created at %s", ad, baslangic.isoformat())
        return self.oku(ad)

    def ilerlet(self, ad: str, yeni: datetime, satir: int, modul: int) -> None:
        """Advance the cursor after a turn's work is committed.

        `greatest` rather than plain assignment: a re-scan started from an older
        position must not be able to drag the live cursor backwards if the two
        ever end up sharing a name by mistake.
        """
        with self._baglanti.cursor() as imlec:
            imlec.execute(
                """
                UPDATE gridup.tarama_imleci
                   SET son_islenen   = greatest(son_islenen, %s),
                       son_tur       = now(),
                       son_tur_satir = %s,
                       son_tur_modul = %s,
                       tur_sayisi    = tur_sayisi + 1,
                       guncelleme    = now()
                 WHERE ad = %s
                """,
                (yeni, satir, modul, ad),
            )

    def geri_al(self, ad: str, zaman: datetime) -> None:
        """Rewind a cursor so the next turns re-scan history.

        The manual operation section 3.4 is built around. Unlike `ilerlet` this
        one assigns unconditionally — going backwards is the entire point.

        Re-scanning is safe because of the episode model: replaying the same
        measurements re-derives the same findings, and the same `modul_id` + `tip`
        is the same episode, so it is updated rather than duplicated. `_guncelle`
        moves `son_gorulme` forward only, so a replay cannot make an episode look
        stale and get it closed by the hysteresis sweep.
        """
        with self._baglanti.cursor() as imlec:
            imlec.execute(
                "UPDATE gridup.tarama_imleci SET son_islenen = %s, guncelleme = now() "
                "WHERE ad = %s",
                (zaman, ad),
            )
        self._baglanti.commit()
        _gunluk.warning("cursor %s rewound to %s", ad, zaman.isoformat())
