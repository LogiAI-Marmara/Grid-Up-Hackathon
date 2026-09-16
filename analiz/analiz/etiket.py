"""The label file: the answer key for a blind test.

Section 2.7 calls this the *cevap anahtarı* — the answer key that sits beside a
data set and never enters the database. Section 4.4 gives the protocol it serves:

    1. track A runs the generator: N days, M modules. It injects scenarios into
       randomly chosen modules and LEAVES SOME UNTOUCHED.
    2. track B is given only the data. The label file stays with the producer.
    3. the detector runs. Its output is frozen.
    4. the key is opened and the four metrics are computed.

Blind means step 2, not step 4. The labels are withheld while the detector runs
and opened once its output is frozen — which is exactly why every metric here,
lead time included, is computable at evaluation time.

WHY A DEFINED FORMAT AND NOT AN AD-HOC FILE. Lead time is the project's headline
claim (section 2.5): not "we detected an anomaly" but "we gave fourteen hours'
warning". That number is a subtraction between two timestamps, and only one of
them lives in our database. The other — when the injected fault actually became
critical — is known solely to the generator. If track A does not write it down,
the metric cannot exist at all, however good the detector is.

This module defines the format, parses it, and validates it loudly. The format
is documented for track A in `analiz/README.md` under "Etiket dosyası formatı".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .sozlesme import Tip

__all__ = [
    "Senaryo",
    "SENARYO_ADLARI",
    "SENARYO_TIPLERI",
    "EtiketSenaryosu",
    "EtiketDosyasi",
    "oku",
    "yaz",
    "EtiketHatasi",
]

#: Current format version. Bumped only for a breaking change; the reader
#: refuses a version it was not built for rather than guessing at the shape.
SURUM = 1


class EtiketHatasi(ValueError):
    """A label file that cannot be trusted.

    Raised loudly rather than skipped. A silently-dropped scenario makes the
    detection rate look better than it is, which is the one direction an
    evaluation tool must never be wrong in.
    """


#: The seven fault scenarios of section 7.6, as the label file names them.
#: Track A injects one of these; a track owner may not add to the list on their
#: own, so this vocabulary is fixed and a label naming anything else is an error.
SENARYO_ADLARI: tuple[str, ...] = (
    "gevsek_klemens",
    "asiri_yuk",
    "faz_dengesizligi",
    "nem_yukselmesi",
    "ark_olayi",
    "sensor_arizasi",
    "modul_saglik",
)


#: Which anomaly `tip` values count as correctly detecting each scenario.
#:
#: THIS MAPPING IS TRACK B'S, NOT TRACK A'S, and the split matters. Track A knows
#: what it injected — a loose terminal. Track B's detector emits a contract `tip`
#: — and a loose terminal can legitimately surface as `akim_sicaklik_sapmasi`
#: (the diagnosis: heat the load does not explain) or as `sicak_nokta` (the
#: observation: one pixel far above its frame). Both are correct detections of
#: the same screw.
#:
#: If track A were made to write a single expected `tip` into the label file, the
#: evaluation would be measuring whether track B's naming matched track A's guess
#: about track B's naming, which is not a property of the detector. So the label
#: carries what was injected and this table says what counts — and a label may
#: still override it per scenario with `beklenen_tip` when a set is deliberately
#: testing one specific classification.
SENARYO_TIPLERI: dict[str, frozenset[Tip]] = {
    "gevsek_klemens": frozenset({Tip.AKIM_SICAKLIK_SAPMASI, Tip.SICAK_NOKTA}),
    # `asiri_yuk` is the diagnosis (integration phase); the two observations it
    # surfaces as today remain accepted, for the same reason a loose terminal
    # accepts both its diagnosis and its observation.
    "asiri_yuk": frozenset({Tip.ASIRI_YUK, Tip.SICAK_NOKTA, Tip.ORTAM_SICAKLIK_YUKSEK}),
    "faz_dengesizligi": frozenset({Tip.FAZ_DENGESIZLIGI}),
    "nem_yukselmesi": frozenset({Tip.NEM_YUKSEK}),
    "ark_olayi": frozenset({Tip.ARK}),
    "sensor_arizasi": frozenset({Tip.SENSOR_ARIZASI}),
    "modul_saglik": frozenset({Tip.MODUL_SAGLIK}),
}

#: Anomaly types that are the system reporting on itself rather than on the grid
#: (section 7.6: "the last two are not faults, they are the system's own health").
#: The sensor-separation metric is about not confusing the two groups.
SISTEM_TIPLERI: frozenset[Tip] = frozenset({Tip.SENSOR_ARIZASI, Tip.MODUL_SAGLIK})


def _zaman_oku(metin: str, nerede: str) -> datetime:
    """Parse a contract timestamp. UTC, ISO 8601, literal Z."""
    if not isinstance(metin, str):
        raise EtiketHatasi(f"{nerede}: expected an ISO 8601 timestamp, got {metin!r}")
    ham = metin.strip()
    try:
        an = datetime.fromisoformat(ham.replace("Z", "+00:00"))
    except ValueError as hata:
        raise EtiketHatasi(f"{nerede}: invalid timestamp {metin!r}") from hata
    if an.tzinfo is None:
        # Never assumed to be UTC. A label set in an unstated timezone would
        # shift every lead time by the offset, silently and by hours.
        raise EtiketHatasi(f"{nerede}: timestamp {metin!r} has no timezone")
    return an.astimezone(timezone.utc)


def _zaman_yaz(an: datetime) -> str:
    return an.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True, slots=True)
class EtiketSenaryosu:
    """One injected fault, as the generator recorded it."""

    senaryo_id: str
    modul_id: str
    senaryo: str
    #: When the fault was injected — the first moment anything was wrong.
    baslangic: datetime
    #: When it reached its critical state. `None` for a fault still developing at
    #: the end of the set: that is a legitimate scenario, and it simply has no
    #: lead time rather than a lead time of zero.
    kritik_esik: datetime | None = None
    #: Overrides `SENARYO_TIPLERI` for this scenario when a set is deliberately
    #: testing one specific classification.
    beklenen_tip: frozenset[Tip] | None = None
    aciklama: str = ""

    @property
    def kabul_edilen_tipler(self) -> frozenset[Tip]:
        """Anomaly types that count as detecting this scenario."""
        if self.beklenen_tip:
            return self.beklenen_tip
        return SENARYO_TIPLERI[self.senaryo]

    @property
    def sistem_sagligi(self) -> bool:
        """True for scenarios 6 and 7 — the system reporting on itself."""
        return bool(self.kabul_edilen_tipler & SISTEM_TIPLERI)


@dataclass(frozen=True, slots=True)
class EtiketDosyasi:
    """A parsed label file."""

    surum: int
    senaryolar: tuple[EtiketSenaryosu, ...]
    temiz_moduller: tuple[str, ...]
    tohum: int | None = None
    uretim_zamani: datetime | None = None
    kapsam_bas: datetime | None = None
    kapsam_bit: datetime | None = None
    aciklama: str = ""

    @property
    def etiketli_moduller(self) -> frozenset[str]:
        return frozenset(s.modul_id for s in self.senaryolar)

    @property
    def gozlem_gunu(self) -> float:
        """Length of the observation window in days.

        The denominator of the false-alarm rate, which is per module-day. Falls
        back to the span of the scenarios themselves when the file declares no
        `kapsam`, and to 1.0 when even that is unavailable — a fallback that
        makes the rate *worse*, never flattering.
        """
        if self.kapsam_bas is not None and self.kapsam_bit is not None:
            gun = (self.kapsam_bit - self.kapsam_bas).total_seconds() / 86400.0
            if gun > 0:
                return gun
        zamanlar = [s.baslangic for s in self.senaryolar]
        zamanlar += [s.kritik_esik for s in self.senaryolar if s.kritik_esik]
        if len(zamanlar) >= 2:
            gun = (max(zamanlar) - min(zamanlar)).total_seconds() / 86400.0
            if gun > 0:
                return gun
        return 1.0

    def senaryo(self, modul_id: str) -> EtiketSenaryosu | None:
        for s in self.senaryolar:
            if s.modul_id == modul_id:
                return s
        return None


def _senaryo_oku(ham: Any, sira: int) -> EtiketSenaryosu:
    nerede = f"senaryolar[{sira}]"
    if not isinstance(ham, dict):
        raise EtiketHatasi(f"{nerede}: expected an object")

    for alan in ("modul_id", "senaryo", "baslangic"):
        if alan not in ham:
            raise EtiketHatasi(f"{nerede}: missing required field {alan!r}")

    senaryo = ham["senaryo"]
    if senaryo not in SENARYO_ADLARI:
        raise EtiketHatasi(
            f"{nerede}: unknown senaryo {senaryo!r}; "
            f"section 7.6 fixes the list to {', '.join(SENARYO_ADLARI)}"
        )

    beklenen = ham.get("beklenen_tip")
    if beklenen is not None:
        if isinstance(beklenen, str):
            beklenen = [beklenen]
        try:
            beklenen = frozenset(Tip(t) for t in beklenen)
        except ValueError as hata:
            raise EtiketHatasi(f"{nerede}: beklenen_tip has a value outside the tip enum") from hata

    baslangic = _zaman_oku(ham["baslangic"], f"{nerede}.baslangic")
    kritik = ham.get("kritik_esik")
    kritik_zaman = _zaman_oku(kritik, f"{nerede}.kritik_esik") if kritik else None
    if kritik_zaman is not None and kritik_zaman < baslangic:
        raise EtiketHatasi(
            f"{nerede}: kritik_esik precedes baslangic; a fault cannot become "
            f"critical before it starts"
        )

    return EtiketSenaryosu(
        senaryo_id=str(ham.get("senaryo_id") or f"senaryo_{sira + 1:02d}"),
        modul_id=str(ham["modul_id"]),
        senaryo=senaryo,
        baslangic=baslangic,
        kritik_esik=kritik_zaman,
        beklenen_tip=beklenen,
        aciklama=str(ham.get("aciklama") or ""),
    )


def oku(yol: "str | Path") -> EtiketDosyasi:
    """Read and validate a label file.

    Every structural problem is an error rather than a skipped row. A label file
    that half-parses produces a detection rate computed over the scenarios that
    happened to survive parsing, which looks like a result and is not one.
    """
    yol = Path(yol)
    try:
        ham = json.loads(yol.read_text(encoding="utf-8"))
    except FileNotFoundError as hata:
        raise EtiketHatasi(f"label file not found: {yol}") from hata
    except json.JSONDecodeError as hata:
        raise EtiketHatasi(f"{yol}: not valid JSON — {hata}") from hata

    if not isinstance(ham, dict):
        raise EtiketHatasi(f"{yol}: top level must be an object")

    surum = ham.get("surum")
    if surum != SURUM:
        raise EtiketHatasi(
            f"{yol}: surum is {surum!r}, this build reads version {SURUM}. "
            f"Refusing to guess at the shape of another version."
        )

    senaryolar_ham = ham.get("senaryolar")
    if not isinstance(senaryolar_ham, list):
        raise EtiketHatasi(f"{yol}: 'senaryolar' must be a list")

    senaryolar = tuple(_senaryo_oku(s, i) for i, s in enumerate(senaryolar_ham))

    temiz = ham.get("temiz_moduller")
    if not isinstance(temiz, list):
        raise EtiketHatasi(
            f"{yol}: 'temiz_moduller' must be a list. It may be empty only if the "
            f"set genuinely has no clean modules — but then the false-alarm rate "
            f"cannot be measured, and section 4.4 calls such a set worthless."
        )
    temiz = tuple(str(m) for m in temiz)

    cakisan = set(temiz) & {s.modul_id for s in senaryolar}
    if cakisan:
        raise EtiketHatasi(
            f"{yol}: {sorted(cakisan)} listed as clean and as carrying a scenario"
        )

    kapsam = ham.get("kapsam") or {}
    return EtiketDosyasi(
        surum=surum,
        senaryolar=senaryolar,
        temiz_moduller=temiz,
        tohum=ham.get("tohum"),
        uretim_zamani=(
            _zaman_oku(ham["uretim_zamani"], "uretim_zamani")
            if ham.get("uretim_zamani")
            else None
        ),
        kapsam_bas=_zaman_oku(kapsam["bas"], "kapsam.bas") if kapsam.get("bas") else None,
        kapsam_bit=_zaman_oku(kapsam["bit"], "kapsam.bit") if kapsam.get("bit") else None,
        aciklama=str(ham.get("aciklama") or ""),
    )


def yaz(dosya: EtiketDosyasi, yol: "str | Path") -> Path:
    """Write a label file. Used by the fixture set; track A writes its own."""
    yol = Path(yol)
    govde: dict[str, Any] = {
        "surum": dosya.surum,
        "senaryolar": [
            {
                "senaryo_id": s.senaryo_id,
                "modul_id": s.modul_id,
                "senaryo": s.senaryo,
                "baslangic": _zaman_yaz(s.baslangic),
                **({"kritik_esik": _zaman_yaz(s.kritik_esik)} if s.kritik_esik else {}),
                **(
                    {"beklenen_tip": sorted(t.value for t in s.beklenen_tip)}
                    if s.beklenen_tip
                    else {}
                ),
                **({"aciklama": s.aciklama} if s.aciklama else {}),
            }
            for s in dosya.senaryolar
        ],
        "temiz_moduller": list(dosya.temiz_moduller),
    }
    if dosya.tohum is not None:
        govde["tohum"] = dosya.tohum
    if dosya.uretim_zamani is not None:
        govde["uretim_zamani"] = _zaman_yaz(dosya.uretim_zamani)
    if dosya.kapsam_bas and dosya.kapsam_bit:
        govde["kapsam"] = {
            "bas": _zaman_yaz(dosya.kapsam_bas),
            "bit": _zaman_yaz(dosya.kapsam_bit),
        }
    if dosya.aciklama:
        govde["aciklama"] = dosya.aciklama

    yol.write_text(json.dumps(govde, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return yol
