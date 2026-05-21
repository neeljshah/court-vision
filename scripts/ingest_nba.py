"""
ingest_nba.py — CLI entry point for NBA Stats API ingestion.

Usage:
    python scripts/ingest_nba.py --backfill --season 2024-25 [--limit N]
    python scripts/ingest_nba.py --incremental --season 2024-25
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from src.data.ingest import NBAStatsIngester  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ingest_nba",
        description="Ingest NBA box scores and play-by-play into the data lake.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--backfill",
        action="store_true",
        help="Full backfill for the season (resumable).",
    )
    mode.add_argument(
        "--incremental",
        action="store_true",
        help="Resume from last successful run.",
    )
    parser.add_argument(
        "--season",
        required=True,
        metavar="YYYY-YY",
        help="NBA season string e.g. 2024-25.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Cap games processed (backfill only).",
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=1.5,
        metavar="SECONDS",
        help="Seconds to sleep between games (default 1.5).",
    )
    return parser.parse_args()


def print_summary(result: dict, mode: str) -> None:
    print()
    print("=" * 60)
    print(f"  mode     : {mode}")
    print(f"  run_id   : {result.get('run_id', 'n/a')}")
    print(f"  games    : {result.get('games_processed', 0)}")
    print(f"  box rows : {result.get('box_rows', 0)}")
    print(f"  pbp rows : {result.get('pbp_rows', 0)}")
    print(f"  status   : {result.get('status', 'unknown')}")
    errors = result.get("errors", [])
    if errors:
        print(f"  errors   : {len(errors)}")
        for e in errors[:5]:
            print(f"    - {e}")
    print("=" * 60)
    print()


def main() -> None:
    args = parse_args()
    ingester = NBAStatsIngester(rate_limit_s=args.rate_limit)

    log.info("season=%s mode=%s", args.season, "backfill" if args.backfill else "incremental")

    try:
        if args.backfill:
            result = ingester.backfill(season=args.season, limit=args.limit)
            print_summary(result, "backfill")
        else:
            result = ingester.incremental(season=args.season)
            print_summary(result, "incremental")
    except Exception as exc:
        log.error("fatal: %s", exc)
        sys.exit(1)

    if result.get("status") == "error":
        sys.exit(1)


if __name__ == "__main__":
    main()
