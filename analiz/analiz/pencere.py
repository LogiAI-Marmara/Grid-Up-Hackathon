"""The evaluation window: what a module's recent past looks like to the layers.

Section 3.6 draws the line this module sits on. The *scan period* is how often
the detector visits the database; the *evaluation window* is how far back it
looks when it gets there. They are independent, and the detector never looks at
"the current value" — there is no such thing here, only a window.

Everything the four layers need arrives in one `Pencere`. The layers are then
pure functions of it, which is what makes them testable without a database and
re-runnable over the same history as often as an algorithm change demands
(section 3.4).

Cost: one turn is a fixed number of queries — six — no matter how many modules
it touches. Per-module queries would make a 100-module turn 600 round trips and
section 8's scale target unreachable for reasons that have nothing to do with
detection.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import psycopg

from .ayar import Ayar
from .sozlesme import Kalite, OlcumTipi, Tip


#: Default number of newest samples a representative value is taken over.
#: Mirrors `PencereAyari.temsil_ornek`; the layers pass the configured value
#: explicitly, and this is only the fallback for direct use in tests.
VARSAYILAN_TEMSIL = 5


def _medyan(degerler: "tuple[float, ...] | list[float]") -> float:
    """Local median, so this module does not import the detector package.

    `dedektor.istatistik.medyan` is the same function; `tests/test_istatistik.py`
    asserts they agree. The duplication buys a clean dependency direction —
    the detector reads windows, windows do not reach back into the detector.
    """
    sirali = sorted(degerler)
    n = len(sirali)
    orta = n // 2
    if n % 2:
        return float(sirali[orta])
    return (float(sirali[orta - 1]) + float(sirali[orta])) / 2.0

__all__ = [
    "Nokta",
    "Seri",
    "TermalOzet",
    "TabanCizgisi",
    "Pencere",
    "PencereGetirici",
    "KANAL_TIPLERI",
]


#: Which anomaly types a channel can produce. Used by the baseline poisoning
#: guard: a humidity episode must not blank out the thermal baseline, so only
#: episodes of a type this channel actually feeds are excluded from it.
KANAL_TIPLERI: dict[OlcumTipi, frozenset[Tip]] = {
    OlcumTipi.TERMAL_MAKS: frozenset(
        {Tip.SICAK_NOKTA, Tip.AKIM_SICAKLIK_SAPMASI}
    ),
    OlcumTipi.TERMAL_ORT: frozenset(
        {Tip.SICAK_NOKTA, Tip.AKIM_SICAKLIK_SAPMASI}
    ),
    OlcumTipi.ORTAM_SICAKLIK: frozenset({Tip.ORTAM_SICAKLIK_YUKSEK}),
    OlcumTipi.NEM: frozenset({Tip.NEM_YUKSEK}),
}


@dataclass(frozen=True, slots=True)
class Nokta:
    """One measurement row, as the layers see it."""

    zaman: datetime
    deger: float | None
    kalite: Kalite
    alindi_zaman: datetime

    @property
    def gecerli(self) -> bool:
        """True if this sample may be used for a physical judgement.

        A `supheli` or `yok` sample is not a small number or a large one — it is
        not a number at all, and averaging it in is exactly the mistake the
        `kalite` column exists to prevent. Layer 0 reads these; every other layer
        sees them already filtered out.
        """
        return self.deger is not None and self.kalite is Kalite.IYI

    @property
    def gecikme_sn(self) -> float:
        """Arrival minus measurement time, seconds. Module clock drift shows here."""
        return (self.alindi_zaman - self.zaman).total_seconds()


@dataclass(frozen=True, slots=True)
class Seri:
    """One channel's samples inside one window, oldest first."""

    olcum_tipi: OlcumTipi
    noktalar: tuple[Nokta, ...] = ()

    def __len__(self) -> int:
        return len(self.noktalar)

    @property
    def gecerli_noktalar(self) -> tuple[Nokta, ...]:
        return tuple(n for n in self.noktalar if n.gecerli)

    @property
    def degerler(self) -> tuple[float, ...]:
        return tuple(n.deger for n in self.gecerli_noktalar)  # type: ignore[misc]

    @property
    def bos(self) -> bool:
        return not self.gecerli_noktalar

    @property
    def ilk(self) -> Nokta | None:
        gecerli = self.gecerli_noktalar
        return gecerli[0] if gecerli else None

    @property
    def son(self) -> Nokta | None:
        gecerli = self.gecerli_noktalar
        return gecerli[-1] if gecerli else None

    def temsil(self, ornek: int = VARSAYILAN_TEMSIL) -> float | None:
        """Median of the newest `ornek` valid samples — what the layers judge.

        Section 3.6 is explicit that the detector never looks at "the current
        value", and this method is where that holds or fails. Judging the single
        latest sample would mean one noise spike, one reflection off a passing
        technician's jacket, produces an alarm with a work order attached; and a
        detector that cries wolf at noise is the one section 2.6 says gets turned
        off. A median over the last few samples ignores a lone spike completely
        while following a real move within the same few samples.
        """
        degerler = self.degerler[-max(1, ornek):]
        if not degerler:
            return None
        return _medyan(degerler)

    def baslangic(self, ornek: int = VARSAYILAN_TEMSIL) -> float | None:
        """Median of the oldest `ornek` valid samples. The other end of a delta."""
        degerler = self.degerler[: max(1, ornek)]
        if not degerler:
            return None
        return _medyan(degerler)

    def delta_temsil(self, ornek: int = VARSAYILAN_TEMSIL) -> float:
        """Rise across the window, both ends taken as medians rather than points.

        `son - ilk` on raw samples makes the whole trend hostage to two readings,
        one of which is the noisiest thing in the window (the newest). Both ends
        are medians for the same reason `temsil` is.
        """
        bas, bit = self.baslangic(ornek), self.temsil(ornek)
        if bas is None or bit is None:
            return 0.0
        return bit - bas

    @property
    def delta(self) -> float:
        """Rise across the window, using the default representative sample count."""
        return self.delta_temsil()

    @property
    def sure_saat(self) -> float:
        """Span of the valid samples in hours. 0.0 for fewer than two."""
        ilk, son = self.ilk, self.son
        if ilk is None or son is None or ilk is son:
            return 0.0
        return (son.zaman - ilk.zaman).total_seconds() / 3600.0

    @property
    def azami(self) -> float | None:
        degerler = self.degerler
        return max(degerler) if degerler else None

    def zaman_saat(self, baslangic: datetime) -> tuple[float, ...]:
        """Valid samples' timestamps as hours since `baslangic`, for a slope fit."""
        return tuple(
            (n.zaman - baslangic).total_seconds() / 3600.0 for n in self.gecerli_noktalar
        )


@dataclass(frozen=True, slots=True)
class TermalOzet:
    """One thermal sampling cycle's on-board summary."""

    zaman: datetime
    maks: float
    maks_sutun: int
    maks_satir: int
    bolge_ort: tuple[float, ...]

    @property
    def piksel(self) -> list[int]:
        """Hot pixel as the contract's `[sutun, satir]` — x first."""
        return [self.maks_sutun, self.maks_satir]

    @property
    def bolge_ortalamasi(self) -> float:
        """Mean of the four quadrant means: the frame's overall level."""
        return sum(self.bolge_ort) / len(self.bolge_ort) if self.bolge_ort else 0.0

    @property
    def ayrisma(self) -> float:
        """Hot pixel minus the frame's overall level.

        This one number is the neighbouring-pixel test in section 5: a frame that
        warmed up as a whole has a small ayrisma and is ambient; one pixel pulling
        away from its own frame is a terminal, and no amount of summer heat
        produces it.
        """
        return self.maks - self.bolge_ortalamasi


@dataclass(frozen=True, slots=True)
class TabanCizgisi:
    """Robust baseline for one module-channel: what normal is, numerically."""

    olcum_tipi: OlcumTipi
    medyan: float
    mad: float
    ornek: int
    bas: datetime
    bit: datetime
    donduruldu: bool = False

    @property
    def yeterli(self) -> bool:
        return self.ornek > 0


@dataclass(frozen=True, slots=True)
class Pencere:
    """Everything the four layers get to see about one module at one instant."""

    modul_id: str
    saha_kodu: str
    pano_kodu: str
    simdi: datetime

    tespit_bas: datetime
    tespit_bit: datetime

    #: Detection-window series, keyed by measurement type.
    seriler: dict[OlcumTipi, Seri] = field(default_factory=dict)
    #: Robust baselines, keyed by measurement type. Missing key = cold start.
    tabanlar: dict[OlcumTipi, TabanCizgisi] = field(default_factory=dict)
    #: Thermal summaries in the detection window, oldest first.
    termal: tuple[TermalOzet, ...] = ()
    #: Peer modules' detection-window series, keyed by modul_id.
    komsular: dict[str, dict[OlcumTipi, Seri]] = field(default_factory=dict)

    #: Newest evidence frame for this module, if it sent one.
    kare_id: str | None = None
    kare_zaman: datetime | None = None

    #: Types with an episode already open. Layer 2 reads this for the poisoning
    #: guard; the event lifecycle reads it to decide open-vs-update.
    acik_tipler: frozenset[Tip] = frozenset()

    #: Newest measurement time anywhere for this module, and its arrival time.
    #: Layer 0 needs both: the first detects silence, the pair detects clock drift.
    son_olcum_zaman: datetime | None = None
    son_olcum_alindi: datetime | None = None

    def seri(self, olcum_tipi: OlcumTipi) -> Seri:
        """The channel's series, or an empty one. Never raises: a module that
        does not report humidity is normal, not an error."""
        return self.seriler.get(olcum_tipi, Seri(olcum_tipi))

    def taban(self, olcum_tipi: OlcumTipi) -> TabanCizgisi | None:
        return self.tabanlar.get(olcum_tipi)

    @property
    def bos(self) -> bool:
        """True when no channel has a usable sample in the detection window."""
        return all(s.bos for s in self.seriler.values()) and not self.termal

    @property
    def tetikleyici_zaman(self) -> datetime:
        """Measurement time to stamp a finding with.

        Contract 3 is explicit that this is the time of the measurement that
        triggered the anomaly, not the time the detector ran. Lead time is
        measured from it, so getting it wrong flatters the headline metric.
        """
        adaylar = [s.son.zaman for s in self.seriler.values() if s.son is not None]
        if self.termal:
            adaylar.append(self.termal[-1].zaman)
        return max(adaylar) if adaylar else self.simdi


class PencereGetirici:
    """Builds `Pencere` objects for a set of modules in a fixed number of queries."""

    def __init__(self, baglanti: psycopg.Connection, ayar: Ayar) -> None:
        self._baglanti = baglanti
        self._ayar = ayar

    # -- public ------------------------------------------------------------

    def getir(self, zamanlar: dict[str, datetime]) -> dict[str, Pencere]:
        """Build one window per module, each at its own evaluation instant.

        The instant is per module and not per turn, which matters in exactly the
        two cases decision K1 was chosen for (section 3.4):

          - a module that lost its uplink for five minutes and then delivers 300
            rows at once. Those rows carry *old* measurement times. Anchoring its
            window at "now" would put the batch that triggered the evaluation
            outside the window being evaluated.
          - a historical re-scan. The cursor is rewound and last week is replayed;
            every window must land on last week, or the re-scan evaluates empty
            windows and silently finds nothing.

        So the caller passes the instant it wants each module judged at, and the
        scan loop derives it from the rows that actually arrived.
        """
        if not zamanlar:
            return {}

        p = self._ayar.pencere
        hedefler = list(zamanlar)

        meta = self._modul_meta(hedefler)
        komsu_haritasi = self._komsulari_bul(hedefler, meta)

        # Peers need their own detection-window series for the module-vs-module
        # comparison. A peer serving several targets is fetched once, at the
        # latest instant any of them asked for.
        komsu_zamanlari: dict[str, datetime] = {}
        for hedef, komsular in komsu_haritasi.items():
            an = zamanlar[hedef]
            for komsu in komsular:
                if komsu not in zamanlar and komsu_zamanlari.get(komsu, an) <= an:
                    komsu_zamanlari[komsu] = an

        tum_zamanlar = {**komsu_zamanlari, **zamanlar}
        araliklar = [
            (modul_id, an - timedelta(seconds=p.tespit_sn), an)
            for modul_id, an in tum_zamanlar.items()
        ]
        hedef_araliklari = [a for a in araliklar if a[0] in zamanlar]

        seriler = self._seriler(araliklar)
        termaller = self._termal_ozetler(hedef_araliklari)
        acik = self._acik_tipler(hedefler)
        kareler = self._son_kareler(hedefler)
        sonlar = self._son_olcumler(hedefler)
        tabanlar = self._tabanlar(zamanlar, acik)

        pencereler: dict[str, Pencere] = {}
        for modul_id, an in zamanlar.items():
            saha, pano = meta.get(modul_id, ("", ""))
            son_zaman, son_alindi = sonlar.get(modul_id, (None, None))
            pencereler[modul_id] = Pencere(
                modul_id=modul_id,
                saha_kodu=saha,
                pano_kodu=pano,
                simdi=an,
                tespit_bas=an - timedelta(seconds=p.tespit_sn),
                tespit_bit=an,
                seriler=seriler.get(modul_id, {}),
                tabanlar=tabanlar.get(modul_id, {}),
                termal=termaller.get(modul_id, ()),
                komsular={
                    komsu: seriler.get(komsu, {})
                    for komsu in komsu_haritasi.get(modul_id, ())
                },
                kare_id=kareler.get(modul_id, (None, None))[0],
                kare_zaman=kareler.get(modul_id, (None, None))[1],
                acik_tipler=acik.get(modul_id, frozenset()),
                son_olcum_zaman=son_zaman,
                son_olcum_alindi=son_alindi,
            )
        return pencereler

    # -- queries -----------------------------------------------------------

    def _modul_meta(self, modul_idler: Sequence[str]) -> dict[str, tuple[str, str]]:
        with self._baglanti.cursor() as imlec:
            imlec.execute(
                "SELECT modul_id, saha_kodu, pano_kodu FROM gridup.modul "
                "WHERE modul_id = ANY(%s)",
                (list(modul_idler),),
            )
            return {r["modul_id"]: (r["saha_kodu"], r["pano_kodu"]) for r in imlec.fetchall()}

    def _komsulari_bul(
        self, modul_idler: Sequence[str], meta: dict[str, tuple[str, str]]
    ) -> dict[str, list[str]]:
        """Peer modules for the module-vs-module comparison.

        Scope is configuration: `pano` compares a module with the others in its
        own switchboard, `saha` with everything on the site. Panel scope is the
        tighter comparison and site scope finds more peers; which is right depends
        on how densely a site is instrumented, so it is not hardcoded.
        """
        kapsam = self._ayar.katman3.komsu_kapsami
        if kapsam not in {"saha", "pano"}:
            raise ValueError(f"katman3.komsu_kapsami must be 'saha' or 'pano', got {kapsam!r}")

        sahalar = {meta[m][0] for m in modul_idler if m in meta}
        if not sahalar:
            return {}

        with self._baglanti.cursor() as imlec:
            imlec.execute(
                "SELECT modul_id, saha_kodu, pano_kodu FROM gridup.modul "
                "WHERE saha_kodu = ANY(%s) AND aktif",
                (list(sahalar),),
            )
            adaylar = imlec.fetchall()

        harita: dict[str, list[str]] = {}
        for modul_id in modul_idler:
            if modul_id not in meta:
                harita[modul_id] = []
                continue
            saha, pano = meta[modul_id]
            harita[modul_id] = [
                a["modul_id"]
                for a in adaylar
                if a["modul_id"] != modul_id
                and a["saha_kodu"] == saha
                and (kapsam == "saha" or a["pano_kodu"] == pano)
            ]
        return harita

    def _seriler(
        self, araliklar: "list[tuple[str, datetime, datetime]]"
    ) -> dict[str, dict[OlcumTipi, Seri]]:
        """Detection-window samples for every module of interest, in one query.

        Each module brings its own range, joined in as a values list. One query
        per turn rather than one per module: at the 100-module scale of section 8
        the difference is 1 round trip against 100, and that is the difference
        between a turn that fits inside the scan period and one that does not.
        """
        if not araliklar:
            return {}
        with self._baglanti.cursor() as imlec:
            imlec.execute(
                """
                WITH istek(modul_id, bas, bit) AS (
                    SELECT * FROM unnest(%s::text[], %s::timestamptz[], %s::timestamptz[])
                )
                SELECT o.modul_id, o.olcum_tipi, o.zaman, o.deger, o.kalite, o.alindi_zaman
                FROM istek i
                JOIN gridup.olcum o
                  ON o.modul_id = i.modul_id
                 AND o.zaman > i.bas
                 AND o.zaman <= i.bit
                ORDER BY o.modul_id, o.olcum_tipi, o.zaman
                """,
                (
                    [a[0] for a in araliklar],
                    [a[1] for a in araliklar],
                    [a[2] for a in araliklar],
                ),
            )
            satirlar = imlec.fetchall()

        biriken: dict[str, dict[OlcumTipi, list[Nokta]]] = {}
        azami = self._ayar.pencere.azami_satir
        for satir in satirlar:
            try:
                tip = OlcumTipi(satir["olcum_tipi"])
            except ValueError:
                # A measurement type this build of track B does not know about.
                # Skipping is correct: the long/narrow format exists so a new type
                # is a new row, and an old detector must not crash on one.
                continue
            kanal = biriken.setdefault(satir["modul_id"], {}).setdefault(tip, [])
            if len(kanal) >= azami:
                continue
            kanal.append(
                Nokta(
                    zaman=satir["zaman"],
                    deger=satir["deger"],
                    kalite=Kalite(satir["kalite"]),
                    alindi_zaman=satir["alindi_zaman"],
                )
            )
        return {
            modul_id: {tip: Seri(tip, tuple(noktalar)) for tip, noktalar in kanallar.items()}
            for modul_id, kanallar in biriken.items()
        }

    def _termal_ozetler(
        self, araliklar: "list[tuple[str, datetime, datetime]]"
    ) -> dict[str, tuple[TermalOzet, ...]]:
        if not araliklar:
            return {}
        with self._baglanti.cursor() as imlec:
            imlec.execute(
                """
                WITH istek(modul_id, bas, bit) AS (
                    SELECT * FROM unnest(%s::text[], %s::timestamptz[], %s::timestamptz[])
                )
                SELECT t.modul_id, t.zaman, t.maks, t.maks_sutun, t.maks_satir, t.bolge_ort
                FROM istek i
                JOIN gridup.termal_ozet t
                  ON t.modul_id = i.modul_id
                 AND t.zaman > i.bas
                 AND t.zaman <= i.bit
                ORDER BY t.modul_id, t.zaman
                """,
                (
                    [a[0] for a in araliklar],
                    [a[1] for a in araliklar],
                    [a[2] for a in araliklar],
                ),
            )
            satirlar = imlec.fetchall()

        biriken: dict[str, list[TermalOzet]] = {}
        for satir in satirlar:
            biriken.setdefault(satir["modul_id"], []).append(
                TermalOzet(
                    zaman=satir["zaman"],
                    maks=float(satir["maks"]),
                    maks_sutun=int(satir["maks_sutun"]),
                    maks_satir=int(satir["maks_satir"]),
                    bolge_ort=tuple(float(b) for b in satir["bolge_ort"]),
                )
            )
        return {m: tuple(v) for m, v in biriken.items()}

    def _acik_tipler(self, modul_idler: Sequence[str]) -> dict[str, frozenset[Tip]]:
        with self._baglanti.cursor() as imlec:
            imlec.execute(
                "SELECT modul_id, tip FROM gridup.anomali "
                "WHERE modul_id = ANY(%s) AND durum <> 'kapandi'",
                (list(modul_idler),),
            )
            satirlar = imlec.fetchall()
        biriken: dict[str, set[Tip]] = {}
        for satir in satirlar:
            biriken.setdefault(satir["modul_id"], set()).add(Tip(satir["tip"]))
        return {m: frozenset(v) for m, v in biriken.items()}

    def _son_kareler(
        self, modul_idler: Sequence[str]
    ) -> dict[str, tuple[str | None, datetime | None]]:
        """Newest evidence frame per module — what `kanit.kare_id` points at."""
        with self._baglanti.cursor() as imlec:
            imlec.execute(
                """
                SELECT DISTINCT ON (modul_id) modul_id, kare_id, zaman
                FROM gridup.termal_kare
                WHERE modul_id = ANY(%s)
                ORDER BY modul_id, zaman DESC
                """,
                (list(modul_idler),),
            )
            return {r["modul_id"]: (r["kare_id"], r["zaman"]) for r in imlec.fetchall()}

    def _son_olcumler(
        self, modul_idler: Sequence[str]
    ) -> dict[str, tuple[datetime | None, datetime | None]]:
        """Newest measurement time per module, with the arrival time of that row.

        Read from `olcum` rather than from `modul.son_gorulme`, which the contract
        offers for exactly this question. `son_gorulme` is a denormalised cache
        that only exists if track A's collector wrote it, and track B has to work
        against a database it filled itself.
        """
        with self._baglanti.cursor() as imlec:
            imlec.execute(
                """
                SELECT DISTINCT ON (modul_id) modul_id, zaman, alindi_zaman
                FROM gridup.olcum
                WHERE modul_id = ANY(%s)
                ORDER BY modul_id, zaman DESC
                """,
                (list(modul_idler),),
            )
            return {r["modul_id"]: (r["zaman"], r["alindi_zaman"]) for r in imlec.fetchall()}

    def _tabanlar(
        self,
        zamanlar: dict[str, datetime],
        acik: dict[str, frozenset[Tip]],
    ) -> dict[str, dict[OlcumTipi, TabanCizgisi]]:
        """Robust baseline per module-channel, computed in SQL.

        Median and MAD are computed with `percentile_cont(0.5)` rather than by
        pulling the samples into Python. A fortnight of one channel at the
        contract's cadence is ~120k rows, and six channels across 100 modules
        would be 70 million rows crossing the wire every turn — the statistics are
        not the expensive part, the transfer is. `percentile_cont(0.5)`
        interpolates the middle two values for an even count, which is the same
        definition `istatistik.medyan` uses; `tests/test_istatistik.py` asserts
        the two agree on the same data, so there is one definition and two
        implementations of it rather than two definitions.

        THE POISONING GUARD (section 5's design note) is the three exclusions
        below, and it is the reason this query is not a plain aggregate:

        1. The baseline window stops `taban_bosluk_sn` short of now, so the
           samples being judged are never among the samples they are judged
           against.
        2. If an episode of a type this channel feeds is already open, the window
           is frozen at that episode's `ilk_gorulme` — "the baseline is not
           updated while an anomaly is open", verbatim. Without this a fault that
           develops over a fortnight is simply learned, and the detector goes
           quiet exactly when it should not.
        3. Samples that fall inside any *past* episode of such a type are dropped,
           so last month's fault does not widen this month's normal band.
        """
        k2 = self._ayar.katman2
        p = self._ayar.pencere
        if not zamanlar or not k2.kanallar:
            return {}

        # Exclusion 2: freeze at the onset of an open episode for this channel.
        dondurma = self._dondurma_zamanlari(list(zamanlar), acik)

        sonuc: dict[str, dict[OlcumTipi, TabanCizgisi]] = {}
        istekler: list[tuple[str, str, datetime, datetime]] = []
        for modul_id, simdi in zamanlar.items():
            bit_varsayilan = simdi - timedelta(seconds=p.taban_bosluk_sn)
            for kanal in k2.kanallar:
                bit = bit_varsayilan
                donmus = dondurma.get((modul_id, kanal))
                if donmus is not None and donmus < bit:
                    bit = donmus
                bas = bit - timedelta(seconds=p.taban_sn)
                istekler.append((modul_id, kanal.value, bas, bit))

        with self._baglanti.cursor() as imlec:
            imlec.execute(
                """
                WITH istek(modul_id, olcum_tipi, bas, bit) AS (
                    SELECT * FROM unnest(
                        %s::text[], %s::text[], %s::timestamptz[], %s::timestamptz[]
                    )
                ),
                ornek AS (
                    SELECT i.modul_id, i.olcum_tipi, i.bas, i.bit, o.deger
                    FROM istek i
                    JOIN gridup.olcum o
                      ON o.modul_id = i.modul_id
                     AND o.olcum_tipi = i.olcum_tipi
                     AND o.zaman > i.bas
                     AND o.zaman <= i.bit
                    WHERE o.kalite = 'iyi'
                      AND o.deger IS NOT NULL
                      -- Exclusion 3: never learn from a stretch that was already
                      -- known to be anomalous for this channel.
                      AND NOT EXISTS (
                          SELECT 1 FROM gridup.anomali a
                          WHERE a.modul_id = o.modul_id
                            AND a.tip = ANY(
                                CASE i.olcum_tipi
                                    WHEN 'termal_maks'    THEN ARRAY['sicak_nokta','akim_sicaklik_sapmasi']
                                    WHEN 'termal_ort'     THEN ARRAY['sicak_nokta','akim_sicaklik_sapmasi']
                                    WHEN 'ortam_sicaklik' THEN ARRAY['ortam_sicaklik_yuksek']
                                    WHEN 'nem'            THEN ARRAY['nem_yuksek']
                                    ELSE ARRAY[]::text[]
                                END)
                            AND o.zaman >= a.ilk_gorulme
                            AND o.zaman <= coalesce(a.kapanma_zaman, a.son_gorulme)
                      )
                ),
                orta AS (
                    SELECT modul_id, olcum_tipi, min(bas) AS bas, min(bit) AS bit,
                           percentile_cont(0.5) WITHIN GROUP (ORDER BY deger) AS medyan,
                           count(*) AS ornek
                    FROM ornek GROUP BY modul_id, olcum_tipi
                )
                SELECT m.modul_id, m.olcum_tipi, m.medyan, m.ornek, m.bas, m.bit,
                       percentile_cont(0.5) WITHIN GROUP (ORDER BY abs(o.deger - m.medyan)) AS mad
                FROM orta m
                JOIN ornek o ON o.modul_id = m.modul_id AND o.olcum_tipi = m.olcum_tipi
                GROUP BY m.modul_id, m.olcum_tipi, m.medyan, m.ornek, m.bas, m.bit
                """,
                (
                    [i[0] for i in istekler],
                    [i[1] for i in istekler],
                    [i[2] for i in istekler],
                    [i[3] for i in istekler],
                ),
            )
            satirlar = imlec.fetchall()

        for satir in satirlar:
            kanal = OlcumTipi(satir["olcum_tipi"])
            sonuc.setdefault(satir["modul_id"], {})[kanal] = TabanCizgisi(
                olcum_tipi=kanal,
                medyan=float(satir["medyan"]),
                mad=float(satir["mad"]),
                ornek=int(satir["ornek"]),
                bas=satir["bas"],
                bit=satir["bit"],
                donduruldu=(satir["modul_id"], kanal) in dondurma,
            )
        return sonuc

    def _dondurma_zamanlari(
        self, modul_idler: Sequence[str], acik: dict[str, frozenset[Tip]]
    ) -> dict[tuple[str, OlcumTipi], datetime]:
        """Per module-channel, the onset of the open episode that freezes its baseline."""
        ilgili = [m for m in modul_idler if acik.get(m)]
        if not ilgili:
            return {}
        with self._baglanti.cursor() as imlec:
            imlec.execute(
                "SELECT modul_id, tip, ilk_gorulme FROM gridup.anomali "
                "WHERE modul_id = ANY(%s) AND durum <> 'kapandi'",
                (ilgili,),
            )
            satirlar = imlec.fetchall()

        dondurma: dict[tuple[str, OlcumTipi], datetime] = {}
        for satir in satirlar:
            tip = Tip(satir["tip"])
            for kanal, tipler in KANAL_TIPLERI.items():
                if tip not in tipler:
                    continue
                anahtar = (satir["modul_id"], kanal)
                mevcut = dondurma.get(anahtar)
                if mevcut is None or satir["ilk_gorulme"] < mevcut:
                    dondurma[anahtar] = satir["ilk_gorulme"]
        return dondurma
