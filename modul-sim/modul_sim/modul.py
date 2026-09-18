"""One simulated module: sampling schedule, threshold logic, packet assembly.

This is the firmware, written as if it ran on the MCU in the box. The flow is
the one in track A's document item 7 — *wake, read, summarise, check threshold,
send* — and the code is organised so the reader can follow that order.

Two things here are firmware decisions rather than simulation details, and both
are visible to the rest of the system:

* **What goes in which packet.** Currents every cycle, thermal summary every
  other cycle, ambient and humidity once a minute, arc only when it happens.
  Section 7.2.
* **When the 768-value frame is attached.** `EsikAyar`, evaluated on board.
  Section 7.4: the module has to recognise the anomaly itself, or it could not
  know when to send the evidence.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from .ayar import ModulAyar
from .fizik import Hava, Kabin, Yuk, YavasKayma, ciy_noktasi, ic_bagil_nem
from .senaryo import Baglam, Senaryo
from .sozlesme import (
    OLCUM_ARALIK,
    OLCUM_BIRIM,
    TERMAL_PIKSEL,
    Besleme,
    Kalite,
    OlcumTipi,
    zaman_yaz,
)
from .termal import TermalDizi, TermalOzet

#: Probability that a healthy environmental reading comes back suspect anyway.
#: Real sensors glitch: a bus read collides, a value arrives out of trend. Data
#: without any of this is data on which any detector looks good.
GLITCH_OLASILIK = 0.0008


def _kirp(deger: float, tip: OlcumTipi) -> float:
    """Clamp to the contract's plausible range for that measurement type.

    Not an alarm threshold — it is the difference between "an implausible
    reading" (which we report with kalite 'supheli') and "a value the collector
    will reject at the door" (which would just lose the packet).
    """
    alt, ust = OLCUM_ARALIK[tip]
    return min(max(deger, alt), ust)


@dataclass
class UretilenPaket:
    """One packet plus the bookkeeping the simulator wants but the wire does not."""

    paket: dict
    gercek_zaman: datetime  # true time, before the module's clock error
    kare_sebebi: str | None  # why the full frame was attached, for the log


class Modul:
    """A single measuring module, driven tick by tick by the fleet runner."""

    def __init__(
        self,
        ayar: ModulAyar,
        hava: Hava,
        baslangic: datetime,
        senaryo: Senaryo | None = None,
        senaryo_baslangic: datetime | None = None,
        senaryo_sure_s: float = 3600.0,
    ) -> None:
        self.ayar = ayar
        self.hava = hava
        self.senaryo = senaryo
        self.senaryo_baslangic = senaryo_baslangic or baslangic
        self.senaryo_sure_s = max(senaryo_sure_s, 1.0)

        self._rng = random.Random(ayar.tohum)
        self._yuk = Yuk(ayar.yuk, random.Random(ayar.tohum ^ 0x5EED1))
        ilk_hava = hava.taban_sicaklik(baslangic)
        self._kabin = Kabin(ayar.kabin, random.Random(ayar.tohum ^ 0x5EED2), ilk_hava + 6.0)
        self._dizi = TermalDizi(ayar.termal, random.Random(ayar.tohum ^ 0x5EED3))

        self._sayac = 0  # packets emitted, drives the sampling schedule
        self._ark_sayaci = 0
        self._son_kare_an: datetime | None = None
        self._son_deger: dict[OlcumTipi, float] = {}
        self._sinyal_kayma = YavasKayma(random.Random(ayar.tohum ^ 0x5EED4), ayar.saglik.sinyal_salinim, 1800.0)
        self._baslangic = baslangic
        self.son_ozet: TermalOzet | None = None
        self.son_kabin_c: float = ilk_hava + 6.0

    # -- helpers ----------------------------------------------------------

    @property
    def modul_id(self) -> str:
        return self.ayar.modul_id

    def _olcum(self, tip: OlcumTipi, deger: float | None, zaman: str, kalite: Kalite) -> dict:
        """One measurement row in contract ① format."""
        return {
            "modul_id": self.ayar.modul_id,
            "zaman": zaman,
            "olcum_tipi": tip.value,
            "deger": None if deger is None else round(deger, 2),
            "birim": OLCUM_BIRIM[tip].value,
            "kalite": kalite.value,
        }

    def _cevre_degeri(self, tip: OlcumTipi, ham: float, b: Baglam) -> tuple[float | None, Kalite]:
        """Apply sensor-failure behaviour to one environmental channel.

        Returns `(deger, kalite)`. Only `kalite = yok` may carry a null value —
        that rule is in the schema, in the database CHECK, and here.
        """
        kalite = b.kalite_zorla.get(tip, Kalite.IYI)
        if tip in b.dusur:
            return None, Kalite.YOK
        if tip in b.dondur:
            # Frozen: the last value the sensor managed to produce, forever.
            deger = self._son_deger.get(tip, ham)
            return _kirp(deger, tip), kalite
        if tip in b.sapit:
            # Nonsense, but inside the contract's plausible range — a value the
            # collector accepts and only `kalite` marks as untrustworthy.
            alt, ust = OLCUM_ARALIK[tip]
            genislik = ust - alt
            deger = alt + genislik * self._rng.choice((0.02, 0.05, 0.88, 0.95)) * self._rng.uniform(0.9, 1.1)
            return _kirp(deger, tip), kalite
        if kalite is Kalite.IYI and self._rng.random() < GLITCH_OLASILIK:
            kalite = Kalite.SUPHELI
            ham += self._rng.choice((-1, 1)) * self._rng.uniform(4.0, 12.0)
        deger = _kirp(ham, tip)
        self._son_deger[tip] = deger
        return deger, kalite

    def _kare_gerekli(self, ozet: TermalOzet, kabin_c: float, an: datetime, ark: bool) -> str | None:
        """On-board threshold logic. Returns the trigger reason, or None.

        Three independent triggers plus the arc override, and a rate limit. See
        `EsikAyar` for why absolute temperature alone is not enough.
        """
        e = self.ayar.esik
        sebepler = []
        if ark and e.ark_kare:
            sebepler.append("ark")
        if ozet.maks >= e.maks_c:
            sebepler.append(f"maks {ozet.maks:.1f}>={e.maks_c:.1f}")
        if ozet.maks - ozet.ortalama >= e.delta_c:
            sebepler.append(f"delta {ozet.maks - ozet.ortalama:.1f}>={e.delta_c:.1f}")
        if ozet.maks - kabin_c >= e.kabin_delta_c:
            sebepler.append(f"kabin_delta {ozet.maks - kabin_c:.1f}>={e.kabin_delta_c:.1f}")
        if not sebepler:
            return None
        # Rate limit: a module stuck in a fault would otherwise spend its whole
        # uplink budget retransmitting 768 values. An arc trip ignores it —
        # that is the one frame the operator will certainly want.
        if "ark" not in sebepler and self._son_kare_an is not None:
            if (an - self._son_kare_an).total_seconds() < e.min_aralik_s:
                return None
        return ", ".join(sebepler)

    # -- the tick ---------------------------------------------------------

    def ilerle(self, an: datetime) -> UretilenPaket:
        """Advance to `an` (true time) and produce exactly one packet."""
        o = self.ayar.ornekleme
        dt_s = float(o.paket_s) if self._sayac else 0.0

        # 1 — the world as it would be with nothing wrong
        hava = self.hava.ilerle(an, dt_s)
        gecen_s = (an - self.senaryo_baslangic).total_seconds()
        oran = 0.0 if gecen_s <= 0 else min(gecen_s / self.senaryo_sure_s, 1.0)
        b = Baglam(
            an=an,
            dt_s=dt_s,
            gecen_s=gecen_s,
            oran=oran,
            dis_sicaklik_c=hava.sicaklik_c,
            dis_nem=hava.bagil_nem,
            klemens_ek_c=[0.0] * self._dizi.klemens_sayisi,
        )

        # 2 — the fault pushes on it
        if self.senaryo is not None:
            self.senaryo.uygula(b, self._rng)

        # 3 — read the currents. Sub-sampled at akim_okuma_s and averaged over
        #     the packet window, which is what "read every 1-5 s, record the
        #     10 s mean" means in practice.
        alt_adim = max(int(o.paket_s / max(o.akim_okuma_s, 1)), 1)
        alt_dt = o.paket_s / alt_adim if self._sayac else 0.0
        toplam = [0.0, 0.0, 0.0]
        notr_toplam = 0.0
        katsayi_toplam = 0.0
        for _ in range(alt_adim):
            durum = self._yuk.ilerle(an, alt_dt, olcek=b.yuk_olcek)
            akimlar = tuple(i * k for i, k in zip(durum.akimlar, b.faz_olcek))
            notr = self._yuk.notr_akimi(*akimlar)
            toplam = [t + i for t, i in zip(toplam, akimlar)]
            notr_toplam += notr
            katsayi_toplam += durum.katsayi
        l1, l2, l3 = (t / alt_adim for t in toplam)
        notr = notr_toplam / alt_adim
        yuk_katsayisi = katsayi_toplam / alt_adim

        # 4 — cabinet air, and the humidity inside it
        kabin_c = self._kabin.ilerle(hava.sicaklik_c, yuk_katsayisi, dt_s, ek_c=b.kabin_ek_c)
        self.son_kabin_c = kabin_c
        ic_nem = min(ic_bagil_nem(hava.sicaklik_c, hava.bagil_nem, kabin_c) + b.nem_ek, 100.0)

        # 5 — arc counter. The TVOC-2 counts; we read. Section 7.1.
        if b.ark_tetik:
            self._ark_sayaci = min(self._ark_sayaci + b.ark_tetik, int(OLCUM_ARALIK[OlcumTipi.ARK_OLAY][1]))

        # 6 — the module's own clock. Free-running, so it drifts even when
        #     healthy; the collector sees the error as alindi_zaman - zaman.
        kayma_s = (an - self._baslangic).total_seconds() * self.ayar.saglik.saat_kayma_ppm * 1e-6
        kayma_s += b.saat_ek_s
        modul_an = an + timedelta(seconds=kayma_s)
        zaman = zaman_yaz(modul_an)

        # 7 — thermal array: unconditional full frame on every sampling instant (integration item 2)
        termal_ozet_veri = None
        termal_kare = None
        kare_sebebi = None
        ozet: TermalOzet | None = None
        if not b.dusuk_guc:
            # Sub-sample averaging: sensor reads faster and averages into one frame
            # to reduce temporal sensor noise (integration item 2).
            alt_termal_adim = max(int(o.paket_s / getattr(o, "termal_okuma_s", 6)), 1)
            kare_toplam = [0.0] * TERMAL_PIKSEL
            for _ in range(alt_termal_adim):
                sub_kare = self._dizi.kare(
                    kabin_c,
                    yuk_katsayisi,
                    klemens_ek_c=b.klemens_ek_c,
                    genel_ek_c=b.termal_genel_ek_c,
                )
                for p in range(TERMAL_PIKSEL):
                    kare_toplam[p] += sub_kare[p]
            ham_kare = [v / alt_termal_adim for v in kare_toplam]

            alt, ust = OLCUM_ARALIK[OlcumTipi.TERMAL_MAKS]
            # Round before summarising, not after: the collector checks that
            # maks_konum really points at the hottest pixel of the frame it
            # received, so the summary has to be derived from the frame as
            # transmitted.
            kare = [round(min(max(v, alt), ust), 2) for v in ham_kare]
            ozet = TermalDizi.ozet(kare)
            self.son_ozet = ozet
            termal_ozet_veri = {
                "maks": round(ozet.maks, 2),
                "maks_konum": [ozet.maks_konum[0], ozet.maks_konum[1]],
                "bolge_ort": [round(v, 2) for v in ozet.bolge_ort],
            }
            termal_kare = kare
            kare_sebebi = "surekli"
            self._son_kare_an = an

        # 8 — assemble the measurement rows
        olcumler: list[dict] = []
        if not b.dusuk_guc:
            for tip, deger in (
                (OlcumTipi.AKIM_L1, l1),
                (OlcumTipi.AKIM_L2, l2),
                (OlcumTipi.AKIM_L3, l3),
                (OlcumTipi.AKIM_NOTR, notr),
            ):
                kalite = b.kalite_zorla.get(tip, Kalite.IYI)
                olcumler.append(self._olcum(tip, _kirp(deger, tip), zaman, kalite))

            if ozet is not None:
                olcumler.append(
                    self._olcum(OlcumTipi.TERMAL_MAKS, _kirp(ozet.maks, OlcumTipi.TERMAL_MAKS), zaman, Kalite.IYI)
                )
                olcumler.append(
                    self._olcum(OlcumTipi.TERMAL_ORT, _kirp(ozet.ortalama, OlcumTipi.TERMAL_ORT), zaman, Kalite.IYI)
                )

            cevre_cevrim = max(int(o.cevre_s / o.paket_s), 1)
            if self._sayac % cevre_cevrim == 0:
                for tip, ham in ((OlcumTipi.ORTAM_SICAKLIK, kabin_c), (OlcumTipi.NEM, ic_nem)):
                    deger, kalite = self._cevre_degeri(tip, ham, b)
                    olcumler.append(self._olcum(tip, deger, zaman, kalite))

        if b.ark_tetik:
            # Event-driven, no sampling period: the row exists because the
            # TVOC-2 tripped. The value is the cumulative trip count, so the
            # detector sees a monotonic counter rather than a lone 1.
            olcumler.append(self._olcum(OlcumTipi.ARK_OLAY, float(self._ark_sayaci), zaman, Kalite.IYI))

        # 9 — module health
        sinyal = self.ayar.saglik.sinyal_dbm + self._sinyal_kayma.ilerle(dt_s) + b.sinyal_ek_dbm
        if b.besleme is Besleme.YEDEK:
            # On the supercapacitor the transmitter runs at reduced power.
            sinyal -= 4.0
        paket = {
            "modul_id": self.ayar.modul_id,
            "zaman": zaman,
            "olcumler": olcumler,
            "termal_ozet": termal_ozet_veri,
            "termal_kare": termal_kare,
            "modul_durum": {
                "besleme": b.besleme.value,
                "sinyal": int(round(min(max(sinyal, -120.0), 0.0))),
                "yazilim_surumu": self.ayar.saglik.yazilim_surumu,
            },
        }

        self._sayac += 1
        return UretilenPaket(paket=paket, gercek_zaman=an, kare_sebebi=kare_sebebi)

    # -- inspection -------------------------------------------------------

    def ciy_noktasi_c(self, ic_nem: float) -> float:
        """Dew point for the current cabinet state — used by scenario 4's test."""
        return ciy_noktasi(self.son_kabin_c, ic_nem)
