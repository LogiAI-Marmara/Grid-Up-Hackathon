"""Command-line entry point for the module simulator.

    python -m modul_sim --senaryo gevsek_klemens --modul 9 --sure 120 --cikti ndjson

The tool is a *source*: packets go to stdout and nothing else does, so it
composes with the rest of the system without either side knowing about the
other:

    python -m modul_sim --modul 100 --sure 60 > filo.ndjson
    python -m modul_sim --senaryo ark_olay | while read -r p; do
        curl -s -XPOST localhost:8000/paket -H 'content-type: application/json' -d "$p"
    done

Run statistics go to stderr, so redirecting stdout never mixes the two. Output is
streamed, not buffered: a 100-module multi-day run is millions of packets and
must not have to fit in memory.

`--dogrula` validates every packet against `modul_paketi.schema.json` on the way
out and exits non-zero if anything failed, which is what makes "the generator
emits contract-shaped data" a checked claim rather than an assertion.

A blind set for track B is a run where only some modules carry the fault, plus
the label file that says which (`analiz/README.md`, "Etiket dosyası formatı"):

    python -m modul_sim --senaryo gevsek_klemens --modul 20 --sure 720         --senaryo-oran 0.3 --etiket etiket.json > kor.ndjson

The data goes to the database; `etiket.json` stays with the producer until the
detector's output is frozen.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from .runner import VARSAYILAN_TOHUM, Filo, KosuAyar, KosuOzeti
from .senaryo import SENARYOLAR, senaryo_olustur

VARSAYILAN_MODUL = 9
VARSAYILAN_SURE_DK = 60.0


def _zaman(metin: str) -> datetime:
    """Parse `--baslangic`. Accepts the contract form and plain ISO 8601."""
    try:
        an = datetime.fromisoformat(metin.replace("Z", "+00:00"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid timestamp {metin!r}; expected e.g. 2026-09-14T06:00:00Z") from None
    return an if an.tzinfo else an.replace(tzinfo=timezone.utc)


def ayristir(argv: list[str] | None = None) -> argparse.Namespace:
    ayristirici = argparse.ArgumentParser(
        prog="python -m modul_sim",
        description="Grid-Up track A synthetic module data generator.",
        epilog="Scenarios: " + ", ".join(sorted(SENARYOLAR)),
    )
    ayristirici.add_argument(
        "--senaryo",
        choices=sorted(SENARYOLAR),
        default=None,
        help="fault scenario to inject into every module; omit for normal operation only",
    )
    ayristirici.add_argument(
        "--modul", type=int, default=VARSAYILAN_MODUL, metavar="N", help=f"number of modules (default {VARSAYILAN_MODUL})"
    )
    ayristirici.add_argument(
        "--sure",
        type=float,
        default=VARSAYILAN_SURE_DK,
        metavar="DK",
        help=f"simulated run length in minutes (default {VARSAYILAN_SURE_DK:g})",
    )
    ayristirici.add_argument(
        "--tohum", type=int, default=VARSAYILAN_TOHUM, metavar="N", help="root seed; same seed and start time reproduce a run"
    )
    ayristirici.add_argument(
        "--cikti", choices=("ndjson", "json"), default="ndjson", help="one packet per line, or a single JSON array"
    )
    ayristirici.add_argument(
        "--baslangic",
        type=_zaman,
        default=None,
        metavar="ZAMAN",
        help="UTC run start, e.g. 2026-09-14T06:00:00Z (default: so the run ends now)",
    )
    ayristirici.add_argument(
        "--senaryo-bas",
        type=float,
        default=None,
        metavar="DK",
        help="minutes of healthy operation before the fault starts (default: 35%% of the run)",
    )
    ayristirici.add_argument(
        "--senaryo-sure",
        type=float,
        default=None,
        metavar="DK",
        help="minutes the fault takes to reach full strength (default: 55%% of the run)",
    )
    ayristirici.add_argument(
        "--senaryo-modul",
        default=None,
        metavar="ID[,ID...]",
        help="inject the scenario only into these module ids (e.g. TR041-P01-M1,TR042-P02-M2); the rest stay clean",
    )
    ayristirici.add_argument(
        "--senaryo-oran",
        type=float,
        default=None,
        metavar="0-1",
        help="inject the scenario into this fraction of the fleet, chosen deterministically from the seed; the rest stay clean",
    )
    ayristirici.add_argument(
        "--etiket",
        default=None,
        metavar="PATH",
        help="write the blind-test label file (track B format: senaryolar, kritik_esik, temiz_moduller) here when the run ends",
    )
    ayristirici.add_argument(
        "--dogrula", action="store_true", help="validate every packet against modul_paketi.schema.json"
    )
    ayristirici.add_argument("--sessiz", action="store_true", help="do not print the run summary to stderr")
    ayristirici.add_argument("--liste", action="store_true", help="list the scenarios with their expected anomaly types and exit")
    return ayristirici.parse_args(argv)


def senaryolari_listele(akis) -> None:
    """Print the scenario registry: the track A / track B contract, in one table."""
    for ad in sorted(SENARYOLAR):
        senaryo = senaryo_olustur(ad)
        print(f"{ad}\n  {senaryo.baslik}", file=akis)
        print(f"  beklenen_tip: {', '.join(t.value for t in senaryo.beklenen_tip)}", file=akis)
        print(f"  belirti: {senaryo.belirti}", file=akis)


def ozet_yaz(ozet: KosuOzeti, filo: Filo, akis) -> None:
    """Human-readable run summary. stderr, so stdout stays machine-readable."""
    ayar = filo.ayar
    print(
        f"modul_sim: {ozet.modul_sayisi} module(s), {len(filo.sahalar)} site(s), "
        f"{ozet.paket} packet(s), {ozet.olcum} measurement(s)",
        file=akis,
    )
    print(f"  window:  {ozet.ilk_zaman} .. {ozet.son_zaman}  (every {ayar.ornekleme.paket_s} s)", file=akis)
    print(f"  thermal: {ozet.termal_ozet} summary, {ozet.termal_kare} full frame(s)", file=akis)
    if ozet.kare_sebepleri:
        sebepler = ", ".join(f"{k}={v}" for k, v in sorted(ozet.kare_sebepleri.items()))
        print(f"  frame triggers: {sebepler}", file=akis)
    if ayar.senaryo_ad:
        print(
            f"  scenario: {ayar.senaryo_ad} from {filo.senaryo_baslangic:%Y-%m-%dT%H:%M:%SZ} "
            f"ramping over {filo.senaryo_sure_s / 60:.0f} min, "
            f"in {len(filo.senaryo_moduller)} of {len(filo.moduller)} module(s)",
            file=akis,
        )
    if ozet.kalite_supheli or ozet.kalite_yok:
        print(f"  quality: {ozet.kalite_supheli} supheli, {ozet.kalite_yok} yok", file=akis)
    if ozet.ark_olay:
        print(f"  arc rows: {ozet.ark_olay}", file=akis)
    if ozet.yedek_besleme:
        print(f"  packets on backup supply: {ozet.yedek_besleme}", file=akis)


def main(argv: list[str] | None = None) -> int:
    secenek = ayristir(argv)
    if secenek.liste:
        senaryolari_listele(sys.stdout)
        return 0

    if (secenek.senaryo_modul or secenek.senaryo_oran is not None) and not secenek.senaryo:
        print("modul_sim: --senaryo-modul / --senaryo-oran need --senaryo", file=sys.stderr)
        return 2
    try:
        ayar = KosuAyar(
            modul_sayisi=secenek.modul,
            sure_dk=secenek.sure,
            tohum=secenek.tohum,
            senaryo_ad=secenek.senaryo,
            baslangic=secenek.baslangic,
            senaryo_bas_s=None if secenek.senaryo_bas is None else secenek.senaryo_bas * 60.0,
            senaryo_sure_s=None if secenek.senaryo_sure is None else secenek.senaryo_sure * 60.0,
            senaryo_moduller=(
                tuple(p.strip() for p in secenek.senaryo_modul.split(",") if p.strip())
                if secenek.senaryo_modul
                else None
            ),
            senaryo_oran=secenek.senaryo_oran,
        )
    except ValueError as hata:
        print(f"modul_sim: {hata}", file=sys.stderr)
        return 2

    hatalari_bul = None
    if secenek.dogrula:
        from .dogrulama import paket_hatalari  # optional dependency, imported only if asked for

        hatalari_bul = paket_hatalari

    try:
        filo = Filo(ayar)
    except ValueError as hata:
        print(f"modul_sim: {hata}", file=sys.stderr)
        return 2
    ozet = KosuOzeti()
    gecersiz = 0
    cikti = sys.stdout

    try:
        if secenek.cikti == "json":
            cikti.write("[\n")
        for i, paket in enumerate(filo.paketler(ozet)):
            if hatalari_bul is not None:
                hatalar = hatalari_bul(paket)
                if hatalar:
                    gecersiz += 1
                    for hata in hatalar[:4]:
                        print(f"INVALID {paket['modul_id']} {paket['zaman']}: {hata}", file=sys.stderr)
            satir = json.dumps(paket, ensure_ascii=False, separators=(",", ":"))
            if secenek.cikti == "json":
                cikti.write(("," if i else "") + satir + "\n")
            else:
                cikti.write(satir + "\n")
        if secenek.cikti == "json":
            cikti.write("]\n")
        cikti.flush()
    except BrokenPipeError:
        # `... | head` closes the pipe early; that is a normal way to use this
        # tool, not an error. Redirect stdout to devnull so the interpreter's
        # final flush does not raise again on the way out.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
    except KeyboardInterrupt:  # pragma: no cover - interactive
        print("modul_sim: interrupted", file=sys.stderr)
        return 130

    if secenek.etiket:
        with open(secenek.etiket, "w", encoding="utf-8", newline="\n") as dosya:
            json.dump(filo.etiket(), dosya, ensure_ascii=False, indent=2)
            dosya.write("\n")
        if not secenek.sessiz:
            print(f"modul_sim: label file written to {secenek.etiket}", file=sys.stderr)

    if not secenek.sessiz:
        ozet_yaz(ozet, filo, sys.stderr)
    if gecersiz:
        print(f"modul_sim: {gecersiz} of {ozet.paket} packet(s) failed schema validation", file=sys.stderr)
        return 1
    if secenek.dogrula and not secenek.sessiz:
        print(f"modul_sim: all {ozet.paket} packet(s) valid against modul_paketi.schema.json", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
