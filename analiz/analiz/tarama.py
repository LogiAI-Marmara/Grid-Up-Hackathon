"""Decision K1 — the scan loop.

The detector is a background job. Every scan period it asks the database what
has arrived since it last looked, works out which modules those rows belong to,
evaluates each of those modules once, writes what it found, and moves its cursor.
It never touches track A's code; the only contact surface is a set of tables.

The turn, from section 3.6:

    1. which rows have arrived since the cursor?      -> RANGE query
    2. which modules do they belong to?
    3. for each of those modules: fetch the window, evaluate
    4. advance the cursor

Step 1 being a range query is what makes the guarantee in section 3.6 hold: no
measurement is ever missed, whatever the arrival pattern.

    1 measurement/s, 10 s turn      -> 10 rows arrive, 10 are taken
    1 per 20 s, 10 s turn           -> 1 row one turn, 0 the next. Nothing lost
    module silent 5 min, 300 at once -> all 300 are taken

And step 2 being a *set* of modules is the other half: one evaluation per module
per turn, however many rows arrived. Rows are a signal to re-evaluate a module,
not something evaluated one by one — 300 backlogged rows are one evaluation of
one module, not 300 findings.
"""

from __future__ import annotations

import logging
import signal
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import psycopg

from .ayar import Ayar
from .dedektor import Degerlendirme, degerlendir
from .depo import ImlecDeposu
from .olay import OlayDeposu
from .pencere import PencereGetirici

__all__ = ["TurSonucu", "Tarayici"]

_gunluk = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TurSonucu:
    """What one turn did. The unit of measurement for section 8's load test."""

    bas: datetime
    bit: datetime
    satir: int = 0
    modul: int = 0
    acilan: tuple[str, ...] = ()
    guncellenen: tuple[str, ...] = ()
    kapanan: tuple[str, ...] = ()
    seviye_degisen: tuple[str, ...] = ()
    sure_sn: float = 0.0
    degerlendirmeler: tuple[Degerlendirme, ...] = ()

    @property
    def bos(self) -> bool:
        return self.modul == 0


class Tarayici:
    """The scan loop. One `tur()` is one pass; `calis()` repeats it forever."""

    def __init__(self, baglanti: psycopg.Connection, ayar: Ayar) -> None:
        self._baglanti = baglanti
        self._ayar = ayar
        self.imlecler = ImlecDeposu(baglanti, ayar)
        self.olaylar = OlayDeposu(baglanti, ayar)
        self.pencereler = PencereGetirici(baglanti, ayar)
        self._durdur = False

    # -- one turn ----------------------------------------------------------

    def tur(self, simdi: datetime | None = None, imlec_adi: str | None = None) -> TurSonucu:
        """Run one scan turn end to end.

        `simdi` is injectable so tests and a historical re-scan can drive the loop
        without waiting for wall-clock time to pass. In production it is left
        None and the turn uses the real clock.
        """
        baslangic = time.monotonic()
        t = self._ayar.tarama
        ad = imlec_adi or t.imlec_adi
        simdi = simdi or datetime.now(timezone.utc)

        imlec = self.imlecler.oku(ad)
        bas = imlec.son_islenen
        bit = self._aralik_sonu(bas, simdi)

        if bit <= bas:
            # The safety margin has swallowed the whole range: nothing can have
            # settled yet. Advancing anyway would step over rows still in flight.
            return TurSonucu(bas=bas, bit=bas, sure_sn=time.monotonic() - baslangic)

        # --- 1 & 2: the range query, reduced to "which modules, and how recent"
        dokunulan, satir_sayisi = self._dokunulan_moduller(bas, bit)

        # A module that has gone quiet produces no rows, so the row-driven set
        # above can never contain it — and silence is precisely scenario 7. The
        # sweep adds those modules explicitly, judged at the turn's own instant
        # rather than at their last measurement, because the finding is about how
        # long ago that was.
        for modul_id in self._sessiz_moduller(bit):
            # Assignment, not setdefault: a silent module's rows are usually also
            # in the range above (that is how they arrived before it went quiet),
            # and the instant derived from them is the moment it stopped talking.
            # Judging silence at that instant would measure zero silence. Only
            # genuinely silent modules reach here, so this cannot disturb a
            # module that is merely delivering a backlog.
            dokunulan[modul_id] = bit

        # --- 3: one evaluation per module, whatever the row count -------------
        degerlendirmeler: list[Degerlendirme] = []
        acilan: list[str] = []
        guncellenen: list[str] = []
        seviye_degisen: list[str] = []

        if dokunulan:
            pencereler = self.pencereler.getir(dokunulan)
            for modul_id in dokunulan:
                pencere = pencereler.get(modul_id)
                if pencere is None:
                    # Rows for a module not in gridup.modul. Track A's foreign key
                    # should make this impossible; if it happens the row is the
                    # problem, and dropping the module from this turn is better
                    # than failing the turn for every other module.
                    _gunluk.warning("no window for %s; skipping", modul_id)
                    continue
                sonuc = degerlendir(pencere, self._ayar)
                degerlendirmeler.append(sonuc)

                # The turn's instant, not the window's: this records that the
                # detector confirmed the condition now. A module replaying a
                # backlog is judged over an old window but confirmed in the
                # present, and the hysteresis sweep must see the present.
                olay = self.olaylar.uygula(modul_id, sonuc.bulgular, simdi)
                acilan.extend(olay.acilan)
                guncellenen.extend(olay.guncellenen)
                seviye_degisen.extend(olay.seviye_degisen)

        # --- the hysteresis sweep ---------------------------------------------
        kapanan = self.olaylar.kapat_sureli(simdi)

        # --- 4: advance the cursor --------------------------------------------
        self.imlecler.ilerlet(ad, bit, satir_sayisi, len(dokunulan))
        self._baglanti.commit()

        sonuc = TurSonucu(
            bas=bas,
            bit=bit,
            satir=satir_sayisi,
            modul=len(dokunulan),
            acilan=tuple(acilan),
            guncellenen=tuple(guncellenen),
            kapanan=tuple(kapanan),
            seviye_degisen=tuple(seviye_degisen),
            sure_sn=time.monotonic() - baslangic,
            degerlendirmeler=tuple(degerlendirmeler),
        )
        if not sonuc.bos or kapanan:
            _gunluk.info(
                "turn %s..%s: %d rows, %d modules, +%d ~%d -%d in %.3fs",
                bas.isoformat(),
                bit.isoformat(),
                sonuc.satir,
                sonuc.modul,
                len(acilan),
                len(guncellenen),
                len(kapanan),
                sonuc.sure_sn,
            )
        return sonuc

    # -- the loop ----------------------------------------------------------

    def calis(self, azami_tur: int | None = None) -> int:
        """Repeat turns until stopped. Returns the number of turns run.

        The sleep is period *minus elapsed*, not a flat period, so the scan rate
        stays at the configured period instead of drifting to period + turn
        duration. When a turn overruns the period the detector is falling behind,
        which section 8 names as the real scale limit — so it is logged as a
        warning rather than absorbed silently.
        """
        periyot = self._ayar.tarama.periyot_sn
        self._sinyalleri_bagla()
        sayac = 0
        while not self._durdur and (azami_tur is None or sayac < azami_tur):
            try:
                sonuc = self.tur()
            except psycopg.Error:
                # One bad turn must not kill the detector. The cursor was not
                # advanced, so the next turn re-reads the same range.
                _gunluk.exception("turn failed; retrying next period")
                self._baglanti.rollback()
                sonuc = None
            sayac += 1

            gecen = sonuc.sure_sn if sonuc else 0.0
            if gecen > periyot:
                _gunluk.warning(
                    "turn took %.2fs, longer than the %.2fs scan period — falling behind",
                    gecen,
                    periyot,
                )
            if self._durdur:
                break
            time.sleep(max(0.0, periyot - gecen))
        return sayac

    def durdur(self, *_: object) -> None:
        """Ask the loop to stop after the turn in flight."""
        self._durdur = True

    def _sinyalleri_bagla(self) -> None:
        """Stop cleanly on SIGTERM/SIGINT, so a turn is never cut in half.

        Only in the main thread — `signal.signal` raises anywhere else, and tests
        drive `tur()` directly rather than through `calis()`.
        """
        try:
            signal.signal(signal.SIGTERM, self.durdur)
            signal.signal(signal.SIGINT, self.durdur)
        except ValueError:  # pragma: no cover - not the main thread
            pass

    # -- steps -------------------------------------------------------------

    def _aralik_sonu(self, bas: datetime, simdi: datetime) -> datetime:
        """Where this turn's range ends.

        Two adjustments to "now", both of which exist to stop rows being skipped:

        `emniyet_payi_sn` ends the range slightly in the past. `alindi_zaman`
        defaults to `now()`, which in PostgreSQL is *transaction start* time, so a
        collector transaction that began before this turn and commits after it
        would otherwise land a row behind an already-advanced cursor, invisible
        forever.

        `azami_aralik_sn` caps how much time one turn may cover. A detector
        restarted after a day off would otherwise try to evaluate the whole day in
        one query; instead it catches up in bounded steps.
        """
        t = self._ayar.tarama
        bit = simdi - timedelta(seconds=t.emniyet_payi_sn)
        if t.azami_aralik_sn > 0:
            bit = min(bit, bas + timedelta(seconds=t.azami_aralik_sn))
        return bit

    def _dokunulan_moduller(
        self, bas: datetime, bit: datetime
    ) -> tuple[dict[str, datetime], int]:
        """Which modules had rows arrive in `(bas, bit]`, and when they were measured.

        Returns a *set* of modules — step 2 of section 3.6 — mapped to the newest
        measurement time that arrived for each. That timestamp becomes the
        module's evaluation instant, which is what makes a backlog and a
        historical re-scan land their windows on the right stretch of time rather
        than on the present.

        The bound is on `alindi_zaman`, not on `zaman`; see `TaramaAyari.imlec_alani`.
        Measurement, thermal-summary and module-status arrivals all count: a
        thermal summary alone is enough to change what the detector would
        conclude, and a module that has fallen back to backup power may be
        sending nothing but its status — that is precisely when it must be
        looked at.
        """
        with self._baglanti.cursor() as imlec:
            imlec.execute(
                """
                SELECT modul_id, max(zaman) AS son_zaman, sum(sayi) AS sayi
                FROM (
                    SELECT modul_id, zaman, 1 AS sayi
                    FROM gridup.olcum
                    WHERE alindi_zaman > %(bas)s AND alindi_zaman <= %(bit)s
                    UNION ALL
                    SELECT modul_id, zaman, 1 AS sayi
                    FROM gridup.termal_ozet
                    WHERE alindi_zaman > %(bas)s AND alindi_zaman <= %(bit)s
                    UNION ALL
                    SELECT modul_id, zaman, 1 AS sayi
                    FROM gridup.modul_durum
                    WHERE alindi_zaman > %(bas)s AND alindi_zaman <= %(bit)s
                ) g
                GROUP BY modul_id
                ORDER BY modul_id
                """,
                {"bas": bas, "bit": bit},
            )
            satirlar = imlec.fetchall()

        dokunulan = {s["modul_id"]: s["son_zaman"] for s in satirlar}
        toplam = sum(int(s["sayi"]) for s in satirlar)
        return dokunulan, toplam

    def _sessiz_moduller(self, simdi: datetime) -> list[str]:
        """Active modules that have not reported for longer than the silence threshold.

        Bounded by the threshold itself rather than unbounded: a module that went
        dark a month ago already has an open `modul_saglik` episode and does not
        need re-reporting every turn for the rest of time. Once the episode closes
        the module drops out of this window and stays quiet.
        """
        k0 = self._ayar.katman0
        alt = simdi - timedelta(seconds=k0.sessizlik_sn * 20)
        ust = simdi - timedelta(seconds=k0.sessizlik_sn)
        with self._baglanti.cursor() as imlec:
            imlec.execute(
                """
                SELECT m.modul_id
                FROM gridup.modul m
                JOIN LATERAL (
                    SELECT max(o.zaman) AS son FROM gridup.olcum o WHERE o.modul_id = m.modul_id
                ) s ON TRUE
                WHERE m.aktif AND s.son IS NOT NULL AND s.son < %s AND s.son > %s
                ORDER BY m.modul_id
                """,
                (ust, alt),
            )
            return [r["modul_id"] for r in imlec.fetchall()]
