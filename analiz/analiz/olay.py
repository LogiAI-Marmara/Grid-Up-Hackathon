"""Decision K3 — the anomaly episode: open, update, close. Plus the journal.

Why an episode instead of a row per detection (section 6.2): a loose-terminal
fault lasts three days, which at a 10 s scan period is 25,920 turns. Writing a
row per turn would mean 25,920 anomaly rows for one loose screw, and the damage
would not stay inside track B — the dashboard's list becomes unusable, the alarm
service has to invent de-duplication for a problem created upstream of it, and
`durum` stops meaning anything because there is no single row for an operator to
acknowledge. Lead time could not be computed at all.

So: the same `modul_id` + the same `tip`, not yet closed, is the *same* episode.
A turn that finds the condition again updates it. A partial unique index makes
that a database guarantee rather than an intention.

The journal is the second half, and it is not a display convenience. ISA-18.2
models an alarm as a state machine, and SCADA products (Ignition, Geo SCADA)
split it into a status table and a permanent journal for the same reason we do:
"when did this alarm come in, who saw it, when did it clear" is a regulatory
question in electricity distribution, and it cannot be answered from a table that
only holds current state.

HYSTERESIS (section 6.5): an episode closes when the condition has been absent
for about 30 minutes, not the moment a single turn fails to see it. Without it a
value sitting on a threshold opens and closes an episode all afternoon —
chattering, in ISA-18.2's vocabulary — and every open is an alarm.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import psycopg
from psycopg import errors
from psycopg.types.json import Json

from .ayar import Ayar
from .dedektor.taban import Bulgu
from .sozlesme import SEVIYE_SIRA, Durum, Seviye, Tip

__all__ = ["OlayDeposu", "OlaySonucu"]

_gunluk = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OlaySonucu:
    """What one turn did to the episode table. Returned for logging and tests."""

    acilan: tuple[str, ...] = ()
    guncellenen: tuple[str, ...] = ()
    kapanan: tuple[str, ...] = ()
    seviye_degisen: tuple[str, ...] = ()

    @property
    def toplam(self) -> int:
        return len(self.acilan) + len(self.guncellenen) + len(self.kapanan)


class OlayDeposu:
    """Reads and writes `gridup.anomali` and `gridup.anomali_gecis`.

    The only place either table is written. Every state or severity change goes
    through a method here, and every one of those methods writes its journal row
    in the same transaction as the change it records — an audit trail that can be
    missing a row is not an audit trail.
    """

    def __init__(self, baglanti: psycopg.Connection, ayar: Ayar) -> None:
        self._baglanti = baglanti
        self._ayar = ayar

    # -- the turn's main entry point ---------------------------------------

    def uygula(
        self, modul_id: str, bulgular: "tuple[Bulgu, ...] | list[Bulgu]", simdi: datetime
    ) -> OlaySonucu:
        """Fold one module's findings into the episode table.

        `simdi` is the TURN's instant, not the window's: it records that the
        detector confirmed these conditions now, which is what the hysteresis
        sweep measures against. A module replaying a backlog is judged over an
        old window but is being confirmed in the present, and closing its episode
        because the measurements are old would be wrong.

        Deliberately does *not* close episodes whose finding is absent this turn.
        That is `kapat_sureli`'s job, and it is separate because absence has to
        persist for the hysteresis window before it means anything — a single turn
        without a finding is not the condition going away, it is one turn.
        """
        acilan: list[str] = []
        guncellenen: list[str] = []
        seviye_degisen: list[str] = []

        for bulgu in bulgular:
            mevcut = self._acik_olay(modul_id, bulgu.tip)
            if mevcut is None:
                acilan.append(self._ac(modul_id, bulgu, simdi))
            else:
                degisti = self._guncelle(mevcut, bulgu, simdi)
                guncellenen.append(mevcut["id"])
                if degisti:
                    seviye_degisen.append(mevcut["id"])

        return OlaySonucu(
            acilan=tuple(acilan),
            guncellenen=tuple(guncellenen),
            seviye_degisen=tuple(seviye_degisen),
        )

    def kapat_sureli(self, simdi: datetime) -> tuple[str, ...]:
        """Close every episode the detector has not confirmed for the hysteresis window.

        Measured on `son_dogrulama` — when the detector last *found* the condition
        — not on `son_gorulme`, which is when the grid last misbehaved. For a
        latched condition the two are far apart: an arc that tripped forty minutes
        ago is still found on every turn, and closing it because the trip itself is
        older than the hysteresis would open and close an episode every turn for as
        long as the event stayed in the evaluation window.

        Runs once per turn over the whole table rather than per module: an episode
        on a module that has gone completely silent still has to close, and that
        module produces no rows, so a per-module sweep would never reach it.
        """
        sinir = simdi - timedelta(seconds=self._ayar.olay.histerezis_sn)
        with self._baglanti.cursor() as imlec:
            imlec.execute(
                "SELECT id, durum FROM gridup.anomali "
                "WHERE durum <> 'kapandi' AND son_dogrulama < %s "
                "ORDER BY sira",
                (sinir,),
            )
            adaylar = imlec.fetchall()

        kapanan: list[str] = []
        for aday in adaylar:
            self.kapat(aday["id"], simdi, onceki_durum=Durum(aday["durum"]))
            kapanan.append(aday["id"])
        return tuple(kapanan)

    # -- individual transitions --------------------------------------------

    def _ac(self, modul_id: str, bulgu: Bulgu, simdi: datetime) -> str:
        """Open a new episode and journal both of its opening transitions."""
        try:
            with self._baglanti.transaction():
                anomali_id = self._yeni_kimlik()
                with self._baglanti.cursor() as imlec:
                    imlec.execute(
                        """
                        INSERT INTO gridup.anomali
                            (sira, id, modul_id, tip, seviye, maks_seviye, skor,
                             ilk_gorulme, son_gorulme, son_dogrulama, durum,
                             gerekce, kanit, katman)
                        VALUES
                            (currval('gridup.anomali_sira'), %s, %s, %s, %s, %s, %s,
                             %s, %s, %s, 'acik', %s, %s, %s)
                        """,
                        (
                            anomali_id,
                            modul_id,
                            bulgu.tip.value,
                            bulgu.seviye.value,
                            bulgu.seviye.value,
                            bulgu.skor,
                            bulgu.zaman,
                            bulgu.zaman,
                            simdi,
                            bulgu.gerekce,
                            Json(bulgu.kanit) if bulgu.kanit else None,
                            bulgu.katman,
                        ),
                    )
                # An opening is two transitions, and both belong in the journal:
                # the episode came into existence, and its severity left normal.
                self._gecis(anomali_id, "durum", None, Durum.ACIK.value, bulgu.zaman)
                self._gecis(
                    anomali_id, "seviye", Seviye.NORMAL.value, bulgu.seviye.value, bulgu.zaman
                )
        except errors.UniqueViolation:
            # Another turn opened the same episode between our check and our
            # insert. The partial unique index is what caught it; the right
            # answer is to treat this turn as an update, which is what would have
            # happened had the two turns been ordered the other way.
            _gunluk.info(
                "episode for %s/%s already open, updating instead", modul_id, bulgu.tip.value
            )
            mevcut = self._acik_olay(modul_id, bulgu.tip)
            if mevcut is None:  # pragma: no cover - only if it closed in between
                raise
            self._guncelle(mevcut, bulgu, simdi)
            return mevcut["id"]

        _gunluk.info(
            "opened %s %s/%s seviye=%s skor=%.2f",
            anomali_id,
            modul_id,
            bulgu.tip.value,
            bulgu.seviye.value,
            bulgu.skor,
        )
        return anomali_id

    def _guncelle(self, mevcut: dict, bulgu: Bulgu, simdi: datetime) -> bool:
        """Update an open episode in place. Returns True if the severity moved.

        `son_gorulme` only ever moves forward. A re-scan of history (section 3.4)
        replays old measurements through the same code, and letting it drag
        `son_gorulme` backwards would close the episode on the next hysteresis
        sweep — re-running the detector would destroy the finding it re-derived.
        """
        onceki_seviye = Seviye(mevcut["seviye"])
        onceki_maks = Seviye(mevcut["maks_seviye"])
        seviye_degisti = bulgu.seviye is not onceki_seviye

        yeni_maks = (
            bulgu.seviye
            if SEVIYE_SIRA[bulgu.seviye] > SEVIYE_SIRA[onceki_maks]
            else onceki_maks
        )

        with self._baglanti.transaction():
            with self._baglanti.cursor() as imlec:
                imlec.execute(
                    """
                    UPDATE gridup.anomali
                       SET seviye      = %s,
                           maks_seviye = %s,
                           skor        = %s,
                           gerekce     = %s,
                           kanit       = %s,
                           katman      = %s,
                           son_gorulme = greatest(son_gorulme, %s),
                           ilk_gorulme = least(ilk_gorulme, %s),
                           son_dogrulama = greatest(son_dogrulama, %s),
                           guncelleme  = now()
                     WHERE id = %s
                    """,
                    (
                        bulgu.seviye.value,
                        yeni_maks.value,
                        bulgu.skor,
                        bulgu.gerekce,
                        Json(bulgu.kanit) if bulgu.kanit else None,
                        bulgu.katman,
                        bulgu.zaman,
                        bulgu.zaman,
                        simdi,
                        mevcut["id"],
                    ),
                )
            if seviye_degisti:
                # Section 6.5: a severity change is something the alarm service
                # must hear about. A score moving 0.81 -> 0.83 inside the same
                # severity is not, and writing a journal row for it would bury
                # the transitions that matter.
                self._gecis(
                    mevcut["id"],
                    "seviye",
                    onceki_seviye.value,
                    bulgu.seviye.value,
                    bulgu.zaman,
                )
        return seviye_degisti

    def kapat(
        self, anomali_id: str, simdi: datetime, onceki_durum: Durum | None = None
    ) -> None:
        """Close an episode: the condition has been gone for the hysteresis window."""
        if onceki_durum is None:
            with self._baglanti.cursor() as imlec:
                imlec.execute("SELECT durum FROM gridup.anomali WHERE id = %s", (anomali_id,))
                satir = imlec.fetchone()
            if satir is None or satir["durum"] == Durum.KAPANDI.value:
                return
            onceki_durum = Durum(satir["durum"])

        with self._baglanti.transaction():
            with self._baglanti.cursor() as imlec:
                imlec.execute(
                    "UPDATE gridup.anomali "
                    "SET durum = 'kapandi', kapanma_zaman = %s, guncelleme = now() "
                    "WHERE id = %s AND durum <> 'kapandi'",
                    (simdi, anomali_id),
                )
                if imlec.rowcount == 0:
                    return
            self._gecis(anomali_id, "durum", onceki_durum.value, Durum.KAPANDI.value, simdi)
        _gunluk.info("closed %s", anomali_id)

    def onayla(self, anomali_id: str, aktor: str, simdi: datetime) -> bool:
        """Operator acknowledgement.

        Not called by the scan loop — it is the write half of contract 5's
        `onayla` endpoint, which is out of scope for this delivery. It lives here
        because an acknowledgement is a state transition like any other and has to
        produce a journal row carrying *who* and *when*; that is half of what the
        audit trail exists for, and a read API that wrote this transition itself
        would be the second place episode state is mutated.
        """
        with self._baglanti.cursor() as imlec:
            imlec.execute("SELECT durum FROM gridup.anomali WHERE id = %s", (anomali_id,))
            satir = imlec.fetchone()
        if satir is None or satir["durum"] != Durum.ACIK.value:
            return False

        with self._baglanti.transaction():
            with self._baglanti.cursor() as imlec:
                imlec.execute(
                    "UPDATE gridup.anomali SET durum = 'onaylandi', guncelleme = now() "
                    "WHERE id = %s AND durum = 'acik'",
                    (anomali_id,),
                )
                if imlec.rowcount == 0:  # pragma: no cover - lost race
                    return False
            self._gecis(
                anomali_id, "durum", Durum.ACIK.value, Durum.ONAYLANDI.value, simdi, aktor=aktor
            )
        return True

    # -- helpers -----------------------------------------------------------

    def _gecis(
        self,
        anomali_id: str,
        alan: str,
        onceki: str | None,
        yeni: str,
        zaman: datetime,
        aktor: str | None = None,
        aciklama: str | None = None,
    ) -> None:
        """Write one journal row. Every state and severity change calls this."""
        with self._baglanti.cursor() as imlec:
            imlec.execute(
                "INSERT INTO gridup.anomali_gecis "
                "(anomali_id, zaman, alan, onceki, yeni, aktor, aciklama) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    anomali_id,
                    zaman,
                    alan,
                    onceki,
                    yeni,
                    aktor or self._ayar.olay.sistem_aktoru,
                    aciklama,
                ),
            )

    def _acik_olay(self, modul_id: str, tip: Tip) -> dict | None:
        with self._baglanti.cursor() as imlec:
            imlec.execute(
                "SELECT id, seviye, maks_seviye, durum, ilk_gorulme, son_gorulme "
                "FROM gridup.anomali "
                "WHERE modul_id = %s AND tip = %s AND durum <> 'kapandi'",
                (modul_id, tip.value),
            )
            return imlec.fetchone()

    def _yeni_kimlik(self) -> str:
        """Next episode id, e.g. `an_00412`.

        Drawn from the same sequence as `sira`, so the id's ordering and the
        monotonic column the alarm service reads can never disagree. The insert
        uses `currval` of this same sequence for `sira` — hence one `nextval`
        here and none there.
        """
        o = self._ayar.olay
        with self._baglanti.cursor() as imlec:
            imlec.execute("SELECT nextval('gridup.anomali_sira') AS n")
            n = int(imlec.fetchone()["n"])  # type: ignore[index]
        return f"{o.kimlik_oneki}{n:0{o.kimlik_basamak}d}"
