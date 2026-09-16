"""T5 — load test and resource report.

The brief's T5 item does not ask for 100 modules on a screen; it asks that the
system be *designed* to handle them and that the resource cost be assessed.
Section 8 fixes what to measure:

    - turn duration as a function of module count (10 / 50 / 100)
    - rows processed per turn
    - CPU and memory
    - database query timings and the effect of indexes
    - WHETHER TURN DURATION EXCEEDS THE SCAN PERIOD

The last one is the answer. Throughput is not the limit here: the detector polls
on a fixed period, so as long as a turn finishes inside that period the system is
keeping up, and the moment it does not the detector falls behind and the lag
grows without bound. That crossing point is the real scaling limit, and it is
what this module reports.

The volume basis, from section 8: 100 modules x 6 measurement types every 10 s
is roughly 60 rows/s, about 5 million rows a day.

    python -m analiz.yuk --dsn postgresql:///gridup_yuk --moduller 10,50,100

Output is the raw measurement table, unsummarised, as section 8 asks for.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import re
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.rows import dict_row

from .ayar import Ayar
from .db import sema_kur
from .fikstur import Fikstur
from .senaryolar import Profil, Uretec, _bozucu_gevsek_klemens, _bozucu_nem
from .tarama import Tarayici

__all__ = ["Donanim", "SorguKaydi", "TurOlcumu", "YukSonucu", "donanim", "olc", "yazdir"]


# --------------------------------------------------------------------------
# Hardware
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Donanim:
    """What the measurement ran on.

    A turn duration without the machine it was measured on is not a result, it
    is a number. "18.9 s at 100 modules" says nothing portable; "2.9 core-seconds
    per turn on a 4-core Xeon at 2.10 GHz" can be carried to other hardware.
    """

    cekirdek_mantiksal: int
    cekirdek_fiziksel: int
    model: str
    ram_gb: float
    cgroup_cpu: str

    @classmethod
    def topla(cls) -> "Donanim":
        import psutil

        model = "bilinmiyor"
        try:
            for satir in open("/proc/cpuinfo", encoding="utf-8"):
                if satir.startswith("model name"):
                    model = satir.split(":", 1)[1].strip()
                    break
        except OSError:  # pragma: no cover - not Linux
            pass

        # A container can be capped below the core count the kernel reports, and
        # then `nproc` is a promise the scheduler will not keep. Read the cgroup
        # quota too, so a capped run cannot be mistaken for an uncapped one.
        cgroup = "sınırsız"
        try:
            ham = open("/sys/fs/cgroup/cpu.max", encoding="utf-8").read().strip()
            if ham and not ham.startswith("max"):
                kota, periyot = ham.split()
                cgroup = f"{int(kota) / int(periyot):.2f} çekirdek"
        except (OSError, ValueError):
            pass

        return cls(
            cekirdek_mantiksal=psutil.cpu_count(logical=True) or 0,
            cekirdek_fiziksel=psutil.cpu_count(logical=False) or 0,
            model=model,
            ram_gb=psutil.virtual_memory().total / 1e9,
            cgroup_cpu=cgroup,
        )

    def __str__(self) -> str:
        return (
            f"{self.cekirdek_fiziksel} fiziksel / {self.cekirdek_mantiksal} mantıksal "
            f"çekirdek, {self.ram_gb:.1f} GB RAM, {self.model}"
            f"{'' if self.cgroup_cpu == 'sınırsız' else f', cgroup {self.cgroup_cpu}'}"
        )


def donanim() -> Donanim:
    return Donanim.topla()


def _sistem_cpu() -> float:
    """System-wide CPU seconds (user + system + friends), across all cores."""
    import psutil

    z = psutil.cpu_times()
    return sum(
        getattr(z, alan, 0.0)
        for alan in ("user", "nice", "system", "irq", "softirq", "steal", "guest")
    )


def _postgres_cpu() -> float:
    """Total CPU seconds burned by every PostgreSQL backend on this machine.

    The detector's own process CPU is only half the bill: the queries run in
    separate server processes, and their cost does not appear in
    `Process.cpu_times()`. Counting only the Python side would understate the
    work per turn by roughly the SQL share and make the per-core capacity figure
    flattering.
    """
    import psutil

    toplam = 0.0
    for surec in psutil.process_iter(["name"]):
        try:
            if "postgres" in (surec.info["name"] or ""):
                zamanlar = surec.cpu_times()
                toplam += zamanlar.user + zamanlar.system
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return toplam


# --------------------------------------------------------------------------
# Query timing
# --------------------------------------------------------------------------


class SorguKaydi:
    """Accumulates per-statement timings for a run.

    Wired in through psycopg's `cursor_factory` rather than by instrumenting the
    scan loop: measurement code inside the thing being measured is how a load
    test ends up reporting its own overhead. The production path is untouched
    and does not know this exists.
    """

    def __init__(self) -> None:
        self.sureler: dict[str, list[float]] = defaultdict(list)
        self.acik = False

    def sifirla(self) -> None:
        self.sureler.clear()

    def ekle(self, etiket: str, sure: float) -> None:
        if self.acik:
            self.sureler[etiket].append(sure)

    def ozet(self) -> dict[str, dict[str, float]]:
        return {
            etiket: {
                "cagri": len(s),
                "toplam_ms": sum(s) * 1000.0,
                "ort_ms": statistics.mean(s) * 1000.0,
                "azami_ms": max(s) * 1000.0,
            }
            for etiket, s in sorted(
                self.sureler.items(), key=lambda kv: -sum(kv[1])
            )
        }


#: Statement signature -> a name a human can read in a report. Ordered: the
#: first match wins, so the more specific patterns come first.
_ETIKETLER: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"percentile_cont", re.I), "taban çizgisi (medyan+MAD)"),
    (re.compile(r"UNION ALL[\s\S]*alindi_zaman", re.I), "tur aralık sorgusu"),
    (re.compile(r"JOIN gridup\.olcum", re.I), "pencere: ölçüm serileri"),
    (re.compile(r"JOIN gridup\.termal_ozet", re.I), "pencere: termal özet"),
    (re.compile(r"JOIN gridup\.modul_durum", re.I), "pencere: modül durumu"),
    (re.compile(r"(FROM|JOIN) gridup\.termal_kare", re.I), "pencere: kanıt karesi"),
    (re.compile(r"DISTINCT ON \(modul_id\)[\s\S]*gridup\.olcum", re.I), "pencere: son ölçüm"),
    (re.compile(r"JOIN LATERAL[\s\S]*gridup\.olcum", re.I), "sessiz modül taraması"),
    (re.compile(r"INSERT INTO gridup\.anomali_gecis", re.I), "olay: journal yazımı"),
    (re.compile(r"INSERT INTO gridup\.anomali\b", re.I), "olay: açılış"),
    (re.compile(r"UPDATE gridup\.anomali\b", re.I), "olay: güncelleme"),
    (re.compile(r"FROM gridup\.anomali\b", re.I), "olay: açık olay okuma"),
    (re.compile(r"gridup\.tarama_imleci", re.I), "imleç"),
    (re.compile(r"FROM gridup\.modul", re.I), "modül meta / komşular"),
    (re.compile(r"nextval\('gridup\.anomali_sira'\)", re.I), "olay: kimlik"),
)


def _etiketle(sorgu: str) -> str:
    for desen, ad in _ETIKETLER:
        if desen.search(sorgu):
            return ad
    return "diğer"


def _olcen_cursor(kayit: SorguKaydi):
    class ZamanliCursor(psycopg.Cursor):
        def execute(self, query, params=None, **kw):  # type: ignore[override]
            bas = time.perf_counter()
            try:
                return super().execute(query, params, **kw)
            finally:
                kayit.ekle(_etiketle(str(query)), time.perf_counter() - bas)

    return ZamanliCursor


# --------------------------------------------------------------------------
# Measurement
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TurOlcumu:
    """One scan turn."""

    sure_sn: float
    satir: int
    modul: int


@dataclass(frozen=True, slots=True)
class YukSonucu:
    """One module count's worth of measurements."""

    modul_sayisi: int
    turlar: tuple[TurOlcumu, ...]
    periyot_sn: float
    cpu_sn: float
    bellek_mb: float
    bellek_artis_mb: float
    veri_satiri: int
    kurulum_sn: float
    #: CPU seconds burned by PostgreSQL backends during the measured turns. The
    #: detector's own process CPU is only half the bill; the queries run in
    #: separate server processes.
    pg_cpu_sn: float = 0.0
    #: System-wide CPU seconds during the measured turns, and the wall-clock time
    #: they spanned. The ratio is how many cores were actually busy — which is
    #: how "is this single-core work?" gets answered rather than assumed.
    sistem_cpu_sn: float = 0.0
    olcum_suresi_sn: float = 0.0
    donanim: Donanim | None = None
    sorgular: dict[str, dict[str, float]] = field(default_factory=dict)

    @property
    def sureler(self) -> tuple[float, ...]:
        return tuple(t.sure_sn for t in self.turlar)

    @property
    def ort_sure(self) -> float:
        return statistics.mean(self.sureler) if self.turlar else 0.0

    @property
    def medyan_sure(self) -> float:
        return statistics.median(self.sureler) if self.turlar else 0.0

    @property
    def azami_sure(self) -> float:
        return max(self.sureler) if self.turlar else 0.0

    @property
    def p95_sure(self) -> float:
        """The number that decides whether the detector keeps up.

        Not the mean: a detector that fits inside its period on average and
        overruns one turn in ten is falling behind one turn in ten, and the lag
        from those turns accumulates rather than averaging out.
        """
        if not self.turlar:
            return 0.0
        sirali = sorted(self.sureler)
        return sirali[min(len(sirali) - 1, int(0.95 * len(sirali)))]

    @property
    def ort_satir(self) -> float:
        return statistics.mean([t.satir for t in self.turlar]) if self.turlar else 0.0

    @property
    def doluluk(self) -> float:
        """Fraction of the scan period a turn consumes. At 1.0 the detector
        stops keeping up and the backlog grows without bound."""
        return self.p95_sure / self.periyot_sn if self.periyot_sn else 0.0

    @property
    def yetisiyor(self) -> bool:
        return self.doluluk < 1.0

    @property
    def modul_basina_ms(self) -> float:
        return (self.ort_sure * 1000.0 / self.modul_sayisi) if self.modul_sayisi else 0.0

    # -- per-core accounting ------------------------------------------------

    @property
    def cekirdek_sn_tur(self) -> float:
        """CPU core-seconds a turn costs: the detector process plus PostgreSQL.

        This, not wall time, is the portable number. Wall time depends on how
        much of the work overlapped; core-seconds is what the turn actually costs
        a machine, and it carries to hardware with a different clock speed by a
        single ratio.
        """
        if not self.turlar:
            return 0.0
        return (self.cpu_sn + self.pg_cpu_sn) / len(self.turlar)

    @property
    def modul_basina_cekirdek_sn(self) -> float:
        """Core-seconds per module per turn — the unit capacity is computed from."""
        return self.cekirdek_sn_tur / self.modul_sayisi if self.modul_sayisi else 0.0

    @property
    def mesgul_cekirdek(self) -> float:
        """Average number of cores busy across the measured window.

        Near 1.0 means the work is serial and adding cores will not help; near
        the core count means it is already spread. Measured system-wide, so it
        includes the PostgreSQL backends the detector is waiting on.
        """
        if self.olcum_suresi_sn <= 0:
            return 0.0
        return self.sistem_cpu_sn / self.olcum_suresi_sn

    @property
    def paralellik(self) -> float:
        """How much of this turn's CPU work overlapped in time.

        `cekirdek_sn_tur / ort_sure`. At 1.0 nothing overlapped — one core's
        worth of work, done one thing at a time. Above 1.0 some of the SQL ran
        in parallel with something else, or PostgreSQL used parallel workers.
        """
        return self.cekirdek_sn_tur / self.ort_sure if self.ort_sure > 0 else 0.0

    @property
    def cekirdek_basina_kapasite(self) -> float:
        """Modules one core can carry at this scan period.

        `periyot / core-seconds per module`. The figure to quote instead of a
        turn duration, because it survives a change of machine: a box with twice
        the clock speed carries roughly twice as many per core.
        """
        birim = self.modul_basina_cekirdek_sn
        return self.periyot_sn / birim if birim > 0 else 0.0


# --------------------------------------------------------------------------
# Fixture generation at scale
# --------------------------------------------------------------------------


def _modul_idleri(sayi: int, pano_basina: int = 4, saha_basina: int = 2) -> list[str]:
    """`sayi` module ids spread over sites and panels.

    Spread rather than piled into one site because layer 3's module-to-module
    comparison queries a module's site-mates, and a flat topology would make that
    query either trivially small or pathologically large — neither of which is
    what a real deployment costs.
    """
    idler: list[str] = []
    saha = pano = modul = 1
    while len(idler) < sayi:
        idler.append(f"TR{saha:03d}-P{pano:02d}-M{modul}")
        modul += 1
        if modul > pano_basina:
            modul = 1
            pano += 1
            if pano > saha_basina:
                pano = 1
                saha += 1
    return idler


def veri_kur(
    baglanti: psycopg.Connection,
    modul_sayisi: int,
    bitis: datetime,
    gecmis_gun: float,
    tespit_saat: float,
    sik_sn: float,
    seyrek_sn: float,
    arizali_oran: float = 0.15,
) -> tuple[int, float]:
    """Write a realistic fleet of `modul_sayisi` modules. Returns (rows, seconds).

    A share of the fleet carries a fault, because a turn that finds nothing is
    cheaper than one that opens and updates episodes, and a load test on an
    entirely healthy fleet would under-report the cost of the case that matters.
    """
    bas = time.perf_counter()
    fikstur = Fikstur(baglanti)
    profil = Profil(sik_sn=sik_sn, seyrek_sn=seyrek_sn)
    uretec = Uretec(fikstur=fikstur, simdi=bitis, profil=profil, tohum=7)

    idler = _modul_idleri(modul_sayisi)
    arizali = max(1, int(modul_sayisi * arizali_oran))
    toplam = 0
    for i, modul_id in enumerate(idler):
        bozucu = None
        if i < arizali:
            bozucu = _bozucu_gevsek_klemens if i % 2 == 0 else _bozucu_nem
        uretec.uret(
            modul_id,
            gecmis_gun=gecmis_gun,
            tespit_saat=tespit_saat,
            bozucu=bozucu,
        )
        # Flush periodically so the buffer never holds the whole fleet at once,
        # and accumulate: each flush returns only what it wrote.
        if (i + 1) % 10 == 0:
            olcum, termal = fikstur.yaz()
            toplam += olcum + termal
    olcum, termal = fikstur.yaz()
    toplam += olcum + termal

    with baglanti.cursor() as imlec:
        imlec.execute("ANALYZE gridup.olcum")
        imlec.execute("ANALYZE gridup.termal_ozet")
        imlec.execute("ANALYZE gridup.modul")
    baglanti.commit()
    return toplam, time.perf_counter() - bas


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------


def olc(
    dsn: str,
    modul_sayisi: int,
    ayar: Ayar,
    tur_sayisi: int = 12,
    gecmis_gun: float = 15.0,
    tespit_saat: float = 7.0,
    sik_sn: float = 10.0,
    seyrek_sn: float = 600.0,
) -> YukSonucu:
    """Build a fleet of this size, run turns over it, and measure."""
    import psutil

    simdi = datetime(2026, 9, 15, 9, 40, tzinfo=timezone.utc)
    periyot = ayar.tarama.periyot_sn
    # Data is generated past `simdi` so that every measured turn has a scan
    # period's worth of fresh arrivals to consume, exactly as it would in
    # production. Without the overhang the warm-up turn drains the table and
    # every measured turn afterwards processes nothing — which times the empty
    # case and reports it as the cost of running the fleet.
    bitis = simdi + timedelta(seconds=periyot * (tur_sayisi + 2))
    kayit = SorguKaydi()

    with psycopg.connect(dsn, row_factory=dict_row) as baglanti:
        baglanti.cursor_factory = _olcen_cursor(kayit)
        with baglanti.cursor() as imlec:
            imlec.execute("SET search_path TO gridup, public")
        sema_kur(baglanti)

        veri_satiri, kurulum_sn = veri_kur(
            baglanti, modul_sayisi, bitis, gecmis_gun, tespit_saat, sik_sn, seyrek_sn
        )

        tarayici = Tarayici(baglanti, ayar)
        # Start the cursor one scan period back, so each turn picks up roughly
        # what one period's worth of arrivals would be in production rather than
        # the whole history at once.
        tarayici.imlecler.geri_al(
            ayar.tarama.imlec_adi, simdi - timedelta(seconds=periyot)
        )
        # One warm-up turn, unmeasured: the first turn pays for cold caches and
        # for opening every episode at once, and reporting that as steady state
        # would overstate the cost of every turn after it.
        tarayici.tur(simdi=simdi)

        surec = psutil.Process(os.getpid())
        gc.collect()
        bellek_once = surec.memory_info().rss / 1e6
        cpu_once = sum(surec.cpu_times()[:2])
        pg_once = _postgres_cpu()
        # System-wide CPU, so nothing the turn provokes goes uncounted — including
        # PostgreSQL backends that start and exit inside the measured window.
        sistem_once = _sistem_cpu()
        duvar_once = time.perf_counter()

        kayit.sifirla()
        kayit.acik = True
        turlar: list[TurOlcumu] = []
        for i in range(tur_sayisi):
            an = simdi + timedelta(seconds=periyot * (i + 1))
            bas = time.perf_counter()
            sonuc = tarayici.tur(simdi=an)
            turlar.append(
                TurOlcumu(
                    sure_sn=time.perf_counter() - bas,
                    satir=sonuc.satir,
                    modul=sonuc.modul,
                )
            )
        kayit.acik = False

        duvar_sonra = time.perf_counter()
        cpu_sonra = sum(surec.cpu_times()[:2])
        pg_sonra = _postgres_cpu()
        sistem_sonra = _sistem_cpu()
        bellek_sonra = surec.memory_info().rss / 1e6

    return YukSonucu(
        modul_sayisi=modul_sayisi,
        turlar=tuple(turlar),
        periyot_sn=ayar.tarama.periyot_sn,
        cpu_sn=cpu_sonra - cpu_once,
        bellek_mb=bellek_sonra,
        bellek_artis_mb=bellek_sonra - bellek_once,
        veri_satiri=veri_satiri,
        kurulum_sn=kurulum_sn,
        pg_cpu_sn=max(0.0, pg_sonra - pg_once),
        sistem_cpu_sn=max(0.0, sistem_sonra - sistem_once),
        olcum_suresi_sn=duvar_sonra - duvar_once,
        donanim=donanim(),
        sorgular=kayit.ozet(),
    )


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def sinir_tahmini(sonuclar: "list[YukSonucu]") -> str:
    """Where turn duration crosses the scan period, stated per core.

    Reported as a measurement where one was taken and as an extrapolation
    otherwise, and the difference is stated rather than blurred. Turn cost is
    close to linear in module count — the work is per-module window fetches and
    per-module baselines — so a straight line through the largest measured point
    is a defensible estimate, but it is still an estimate and says so.

    The capacity figure is per core, not an absolute duration, because a turn
    duration is only true of the machine it was measured on. Core-seconds per
    module carries to other hardware by one ratio.
    """
    en_buyuk = max(sonuclar, key=lambda s: s.modul_sayisi)
    kapasite = en_buyuk.cekirdek_basina_kapasite
    birim_ms = en_buyuk.modul_basina_cekirdek_sn * 1000.0

    asan = [s for s in sonuclar if not s.yetisiyor]
    if asan:
        ilk = min(asan, key=lambda s: s.modul_sayisi)
        return (
            f"ÖLÇÜLDÜ: tur süresi {ilk.modul_sayisi} modülde tarama periyodunu "
            f"({ilk.periyot_sn:.0f} sn) aşıyor — p95 {ilk.p95_sure:.2f} sn, "
            f"doluluk %{ilk.doluluk * 100:.0f}. Dedektör bu noktadan sonra geride kalır.\n"
            f"Çekirdek başına kapasite: modül başına {birim_ms:.0f} ms çekirdek "
            f"zamanı ile {ilk.periyot_sn:.0f} sn'lik periyotta ~{kapasite:.0f} modül/çekirdek."
        )

    return (
        f"{en_buyuk.modul_sayisi} modülde sınıra ULAŞILMADI: p95 tur süresi "
        f"{en_buyuk.p95_sure:.2f} sn, tarama periyodunun "
        f"(%{en_buyuk.doluluk * 100:.0f}) altında.\n"
        f"Çekirdek başına kapasite: modül başına {birim_ms:.0f} ms çekirdek zamanı "
        f"ile {en_buyuk.periyot_sn:.0f} sn'lik periyotta ~{kapasite:.0f} modül/çekirdek "
        f"(doğrusal varsayım, ölçüm değil tahmin)."
    )


def paralellik_notu(sonuclar: "list[YukSonucu]") -> str:
    """Whether the work is serial, measured rather than assumed.

    CPU time close to wall time is *suggestive* of single-core work but does not
    establish it, because the detector's own process CPU excludes the PostgreSQL
    backends it waits on: a turn could be half Python and half SQL, each using a
    different core, and still show a process CPU/wall ratio near one. So this
    reads system-wide CPU across the measured window and reports how many cores
    were genuinely busy.
    """
    en_buyuk = max(sonuclar, key=lambda s: s.modul_sayisi)
    mesgul = en_buyuk.mesgul_cekirdek
    paralel = en_buyuk.paralellik
    cekirdek = en_buyuk.donanim.cekirdek_mantiksal if en_buyuk.donanim else 0

    if paralel < 1.25:
        hüküm = (
            "TEK ÇEKİRDEK. Tur içindeki iş neredeyse hiç örtüşmüyor: dedektör "
            "tek süreç, tek iş parçacığı ve her modülü sırayla değerlendiriyor; "
            "SQL çalışırken Python bekliyor. Çekirdek eklemek tur süresini "
            "kısaltmaz — ölçeklemek için modülleri süreçlere bölmek gerekir."
        )
    elif paralel < cekirdek * 0.6:
        hüküm = (
            "KISMEN PARALEL. İşin bir kısmı örtüşüyor (muhtemelen PostgreSQL "
            "paralel işçileri), ama mevcut çekirdeklerin tamamı kullanılmıyor."
        )
    else:
        hüküm = "PARALEL. Mevcut çekirdekler büyük ölçüde kullanılıyor."

    return (
        f"Ortalama meşgul çekirdek: {mesgul:.2f} / {cekirdek} "
        f"(sistem geneli CPU ÷ duvar saati).\n"
        f"Tur içi paralellik: {paralel:.2f}× "
        f"(tur başına {en_buyuk.cekirdek_sn_tur:.2f} çekirdek-sn ÷ "
        f"{en_buyuk.ort_sure:.2f} sn duvar saati).\n"
        f"Hüküm: {hüküm}"
    )


def yazdir(sonuclar: "list[YukSonucu]", akis=None) -> None:
    yaz = (akis or sys.stdout).write
    if not sonuclar:
        return
    periyot = sonuclar[0].periyot_sn
    dnm = next((s.donanim for s in sonuclar if s.donanim), None)

    yaz("\nT5 — YÜK TESTİ VE KAYNAK RAPORU\n")
    if dnm is not None:
        yaz(f"donanım: {dnm}\n")
    yaz(f"tarama periyodu {periyot:.0f} sn | tur başına ölçüm {len(sonuclar[0].turlar)}\n")
    yaz("=" * 122 + "\n")
    yaz(
        f"{'modül':>6} {'veri satırı':>12} {'tur ort':>9} {'p95':>8} "
        f"{'satır/tur':>10} {'çekirdek-sn':>12} {'ms/modül':>9} {'bellek':>9} "
        f"{'doluluk':>8} {'mod/çekirdek':>13} {'yetişiyor':>10}\n"
    )
    yaz("-" * 122 + "\n")
    for s in sorted(sonuclar, key=lambda x: x.modul_sayisi):
        yaz(
            f"{s.modul_sayisi:>6} {s.veri_satiri:>12,} "
            f"{s.ort_sure:>8.3f}s {s.p95_sure:>7.3f}s "
            f"{s.ort_satir:>10.0f} {s.cekirdek_sn_tur:>12.2f} "
            f"{s.modul_basina_cekirdek_sn * 1000:>9.0f} {s.bellek_mb:>8.1f}M "
            f"{s.doluluk * 100:>7.0f}% {s.cekirdek_basina_kapasite:>13.0f} "
            f"{('evet' if s.yetisiyor else 'HAYIR'):>10}\n"
        )
    yaz("=" * 122 + "\n")
    yaz(
        "çekirdek-sn = tur başına CPU çekirdek saniyesi (dedektör süreci + "
        "PostgreSQL arka uçları)\n"
        "mod/çekirdek = bu periyotta bir çekirdeğin taşıyabileceği modül sayısı\n"
    )

    yaz("\nÇEKİRDEK KULLANIMI\n")
    yaz("-" * 122 + "\n")
    yaz(paralellik_notu(sonuclar) + "\n")

    yaz("\nVERİTABANI SORGU SÜRELERİ (tur başına, en pahalıdan)\n")
    yaz("-" * 122 + "\n")
    en_buyuk = max(sonuclar, key=lambda s: s.modul_sayisi)
    tur = len(en_buyuk.turlar)
    yaz(f"{en_buyuk.modul_sayisi} modül:\n")
    yaz(f"  {'sorgu':<34} {'çağrı/tur':>10} {'toplam/tur':>12} {'ort':>9} {'azami':>9}\n")
    for ad, olcum in list(en_buyuk.sorgular.items())[:10]:
        yaz(
            f"  {ad:<34} {olcum['cagri'] / tur:>10.1f} "
            f"{olcum['toplam_ms'] / tur:>11.1f}ms {olcum['ort_ms']:>8.1f}ms "
            f"{olcum['azami_ms']:>8.1f}ms\n"
        )
    yaz("-" * 122 + "\n")

    yaz("\nÖLÇEK SINIRI\n")
    yaz(sinir_tahmini(sonuclar) + "\n")


def main(argv: "list[str] | None" = None) -> int:
    ayristirici = argparse.ArgumentParser(prog="analiz.yuk", description=__doc__)
    ayristirici.add_argument("--dsn", default="postgresql:///gridup_yuk")
    ayristirici.add_argument("--moduller", default="10,50,100", help="comma-separated counts")
    ayristirici.add_argument("--tur", type=int, default=12, help="measured turns per count")
    ayristirici.add_argument(
        "--periyot",
        type=float,
        default=Ayar().tarama.periyot_sn,
        help="scan period, seconds (default: the configured default)",
    )
    ayristirici.add_argument("--gun", type=float, default=15.0, help="days of baseline history")
    ayristirici.add_argument(
        "--sik-sn", type=float, default=10.0, help="detection-window sampling interval"
    )
    ayristirici.add_argument("--json", action="store_true")
    args = ayristirici.parse_args(argv)

    sayilar = [int(x) for x in args.moduller.split(",") if x.strip()]
    ayar = Ayar().ile(
        veritabani={"dsn": args.dsn, "sorgu_zaman_asimi_ms": 300_000},
        tarama={
            "periyot_sn": args.periyot,
            "emniyet_payi_sn": 0.0,
            "azami_aralik_sn": 0.0,
        },
    )

    sonuclar: list[YukSonucu] = []
    for sayi in sayilar:
        print(f"[{sayi} modül] veri üretiliyor ve ölçülüyor...", file=sys.stderr)
        # Each module count gets its own database: leftover rows from a smaller
        # run would inflate the next one's query costs and the numbers would be
        # measuring the test harness rather than the detector.
        veritabani = f"{args.dsn}_{sayi}"
        ad = veritabani.rsplit("/", 1)[-1]
        os.system(f"dropdb --if-exists {ad} >/dev/null 2>&1")
        os.system(f"createdb {ad}")
        sonuclar.append(
            olc(
                veritabani,
                sayi,
                ayar.ile(veritabani={"dsn": veritabani}),
                tur_sayisi=args.tur,
                gecmis_gun=args.gun,
                sik_sn=args.sik_sn,
            )
        )

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "modul": s.modul_sayisi,
                        "veri_satiri": s.veri_satiri,
                        "tur_ort_sn": s.ort_sure,
                        "tur_p95_sn": s.p95_sure,
                        "satir_tur": s.ort_satir,
                        "cpu_tur_sn": s.cpu_sn / len(s.turlar),
                        "bellek_mb": s.bellek_mb,
                        "doluluk": s.doluluk,
                        "yetisiyor": s.yetisiyor,
                        "cekirdek_sn_tur": s.cekirdek_sn_tur,
                        "modul_basina_cekirdek_sn": s.modul_basina_cekirdek_sn,
                        "cekirdek_basina_kapasite": s.cekirdek_basina_kapasite,
                        "mesgul_cekirdek": s.mesgul_cekirdek,
                        "paralellik": s.paralellik,
                        "donanim": str(s.donanim) if s.donanim else None,
                    }
                    for s in sonuclar
                ],
                indent=2,
            )
        )
    else:
        yazdir(sonuclar)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
