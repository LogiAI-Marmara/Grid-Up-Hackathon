"""Command-line entry point: `python -m analiz` or `gridup-analiz`.

Four subcommands, which between them are the whole operational surface of the
scan loop:

    sema        apply the migrations
    tara        run the scan loop
    geri-al     rewind a cursor so history is scanned again   (section 3.4)
    durum       show cursor and episode state
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone

from .ayar import Ayar
from .db import baglan, sema_kur, sema_surumu
from .depo import ImlecDeposu
from .tarama import Tarayici


def _ayar(args: argparse.Namespace) -> Ayar:
    """Environment first, then anything given explicitly on the command line."""
    ayar = Ayar.ortamdan()
    if args.dsn:
        ayar = ayar.ile(veritabani={"dsn": args.dsn})
    if getattr(args, "periyot", None):
        ayar = ayar.ile(tarama={"periyot_sn": args.periyot})
    return ayar


def _zaman(metin: str) -> datetime:
    """Parse a timestamp, or `-6h` style relative offsets, into aware UTC."""
    metin = metin.strip()
    if metin.startswith("-") and metin[-1] in "smhd":
        carpan = {"s": 1, "m": 60, "h": 3600, "d": 86400}[metin[-1]]
        return datetime.now(timezone.utc) - timedelta(seconds=float(metin[1:-1]) * carpan)
    an = datetime.fromisoformat(metin.replace("Z", "+00:00"))
    return an if an.tzinfo else an.replace(tzinfo=timezone.utc)


def main(argv: list[str] | None = None) -> int:
    ayristirici = argparse.ArgumentParser(prog="gridup-analiz", description=__doc__)
    ayristirici.add_argument("--dsn", help="PostgreSQL DSN (default: GRIDUP_ANALIZ_VERITABANI_DSN)")
    ayristirici.add_argument("--ayrinti", action="store_true", help="debug logging")
    alt = ayristirici.add_subparsers(dest="komut", required=True)

    alt.add_parser("sema", help="apply migrations and exit")

    p_tara = alt.add_parser("tara", help="run the scan loop")
    p_tara.add_argument("--periyot", type=float, help="scan period, seconds")
    p_tara.add_argument("--tur", type=int, help="stop after N turns (default: run forever)")
    p_tara.add_argument("--imlec", help="cursor name")

    p_geri = alt.add_parser("geri-al", help="rewind a cursor to re-scan history")
    p_geri.add_argument("zaman", type=_zaman, help="ISO timestamp, or a relative offset like -24h")
    p_geri.add_argument("--imlec", help="cursor name")

    alt.add_parser("durum", help="show cursor and episode state")

    p_sunucu = alt.add_parser("sunucu", help="run the read API (contract 5)")
    p_sunucu.add_argument("--adres", help="bind address")
    p_sunucu.add_argument("--port", type=int, help="bind port")

    args = ayristirici.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.ayrinti else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    ayar = _ayar(args)

    if args.komut == "sunucu":
        # Runs its own process and opens its own pool, so it does not borrow the
        # connection the other subcommands share.
        from .api import main as api_main

        arg_listesi: list[str] = []
        if args.dsn:
            arg_listesi += ["--dsn", args.dsn]
        if args.adres:
            arg_listesi += ["--adres", args.adres]
        if args.port:
            arg_listesi += ["--port", str(args.port)]
        if args.ayrinti:
            arg_listesi.append("--ayrinti")
        return api_main(arg_listesi)

    with baglan(ayar) as baglanti:
        if args.komut == "sema":
            sema_kur(baglanti)
            print(f"schema version {sema_surumu(baglanti)}")
            return 0

        if args.komut == "geri-al":
            ad = args.imlec or ayar.tarama.imlec_adi
            ImlecDeposu(baglanti, ayar).geri_al(ad, args.zaman)
            print(f"cursor {ad} rewound to {args.zaman.isoformat()}")
            return 0

        if args.komut == "durum":
            return _durum(baglanti, ayar)

        tarayici = Tarayici(baglanti, ayar)
        if args.imlec:
            ayar = ayar.ile(tarama={"imlec_adi": args.imlec})
            tarayici = Tarayici(baglanti, ayar)
        sayac = tarayici.calis(azami_tur=args.tur)
        print(f"{sayac} turns")
        return 0


def _durum(baglanti, ayar: Ayar) -> int:
    with baglanti.cursor() as imlec:
        imlec.execute(
            "SELECT ad, son_islenen, tur_sayisi, son_tur_satir, son_tur_modul "
            "FROM gridup.tarama_imleci ORDER BY ad"
        )
        for satir in imlec.fetchall():
            print(
                f"cursor {satir['ad']}: at {satir['son_islenen'].isoformat()}, "
                f"{satir['tur_sayisi']} turns, last turn {satir['son_tur_satir']} rows / "
                f"{satir['son_tur_modul']} modules"
            )
        imlec.execute(
            "SELECT durum, seviye, count(*) AS n FROM gridup.anomali "
            "GROUP BY durum, seviye ORDER BY durum, seviye"
        )
        for satir in imlec.fetchall():
            print(f"anomali {satir['durum']}/{satir['seviye']}: {satir['n']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
