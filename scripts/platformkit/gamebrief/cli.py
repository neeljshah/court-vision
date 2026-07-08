"""CLI: python -m scripts.platformkit.gamebrief.cli --home OKC --away DEN --date 2026-02-27

Any historical 2025-26 (or earlier) date with a real game in games.parquet
works. Unknown team/date prints a one-line error (exit code 1) instead of a
traceback.
"""
from __future__ import annotations

import argparse
import json
import sys

from scripts.platformkit.gamebrief.assemble import assemble
from scripts.platformkit.gamebrief.render import render


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--home", required=True, help="home team abbreviation, e.g. OKC")
    ap.add_argument("--away", required=True, help="away team abbreviation, e.g. DEN")
    ap.add_argument("--date", required=True, help="game date, YYYY-MM-DD")
    ap.add_argument("--json", action="store_true", help="print JSON instead of the ASCII brief")
    args = ap.parse_args(argv)

    brief = assemble(args.home, args.away, args.date)
    if args.json:
        print(json.dumps(brief, indent=2, default=str))
    else:
        print(render(brief))
    return 1 if "error" in brief else 0


if __name__ == "__main__":
    sys.exit(main())
