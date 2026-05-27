"""settle_day.py — CLI wrapper for the shadow-log settlement engine.

Usage
-----
    python scripts/settle_day.py --date YYYY-MM-DD [--base-dir <path>]

Scores every shadow-logged bet (passed + blocked) captured on <date>
against the final NBA box score from cdn.nba.com.

Writes: data/shadow/settled_<date>.csv
Prints: N games found, M games finalized, K rows settled, hit-rate X% (passed only)
"""
from __future__ import annotations

import argparse
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.settlement import settle_day  # noqa: E402


def _parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Settle shadow-log bets against final NBA box scores."
    )
    ap.add_argument(
        "--date",
        required=True,
        metavar="YYYY-MM-DD",
        help="Date to settle (e.g. 2026-05-25).",
    )
    ap.add_argument(
        "--base-dir",
        default=None,
        metavar="PATH",
        help="Override data/shadow directory (default: <project>/data/shadow).",
    )
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    settle_day(date_str=args.date, base_dir=args.base_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
