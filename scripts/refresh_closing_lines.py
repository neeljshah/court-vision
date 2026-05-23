"""
refresh_closing_lines.py — Daily CLI to refresh closing lines + props for a date.

Usage:
    python scripts/refresh_closing_lines.py --date 2026-05-22
    python scripts/refresh_closing_lines.py --date 2026-05-22 --force
    python scripts/refresh_closing_lines.py --date 2026-05-22 --props-only
    python scripts/refresh_closing_lines.py --date 2026-05-22 --lines-only

Output summary:
    Source results, record counts, cache paths.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.data.closing_lines_scraper import scrape_date, load_cached, _cache_path
from src.data.closing_lines_props   import scrape_props, load_cached_props, _cache_path as _props_cache_path

log = logging.getLogger(__name__)


def _print_coverage(date_str: str, lines: list, label: str) -> None:
    """Print a compact coverage summary."""
    n = len(lines)
    has_close  = sum(1 for r in lines if r.get("close_ml_home") or r.get("close_total"))
    has_open   = sum(1 for r in lines if r.get("open_ml_home") or r.get("open_total"))
    books      = sorted({r.get("book", "?") for r in lines})
    print(f"  [{label}] {n} records | {has_open} have open | {has_close} have close | books: {books}")


def _print_props_coverage(date_str: str, lines: list) -> None:
    n = len(lines)
    stats = sorted({r.get("stat", "?") for r in lines})
    players = len({r.get("player", "") for r in lines})
    books   = sorted({r.get("book", "?") for r in lines})
    print(f"  [props] {n} records | {players} players | stats: {stats} | books: {books}")


def run(date_str: str, *, force: bool = False, lines_only: bool = False,
        props_only: bool = False) -> None:
    print(f"\n=== Closing Lines Refresh: {date_str} ===")
    print(f"  API key present: {'yes' if os.environ.get('THE_ODDS_API_KEY') else 'no (set THE_ODDS_API_KEY for paid source)'}")

    # ── Game lines ────────────────────────────────────────────────────────────
    if not props_only:
        print("\n--- Game Lines ---")
        try:
            lines = scrape_date(date_str, force=force)
            cache = _cache_path(date_str)
            _print_coverage(date_str, lines, "game_lines")
            print(f"  Cache: {cache}")
            if lines:
                sample = lines[0]
                print(f"  Sample: {sample.get('away')} @ {sample.get('home')} "
                      f"| total close={sample.get('close_total')} open={sample.get('open_total')} "
                      f"| ml_home close={sample.get('close_ml_home')}")
            else:
                print("  WARNING: 0 records — all sources blocked or returned no data")
        except Exception as exc:
            log.exception("Game lines scrape failed: %s", exc)
            print(f"  ERROR: {exc}")

    # ── Player props ──────────────────────────────────────────────────────────
    if not lines_only:
        print("\n--- Player Props ---")
        try:
            props = scrape_props(date_str, force=force)
            cache = _props_cache_path(date_str)
            _print_props_coverage(date_str, props)
            print(f"  Cache: {cache}")
            if props:
                s = props[0]
                print(f"  Sample: {s.get('player')} {s.get('stat')} {s.get('line')} [{s.get('book')}]")
            else:
                print("  WARNING: 0 prop records")
        except Exception as exc:
            log.exception("Props scrape failed: %s", exc)
            print(f"  ERROR: {exc}")

    print(f"\nDone. Run daily and accumulate history before interpreting CLV metrics.")
    print(f"Next: python scripts/build_clv_backtest.py --verbose\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Refresh NBA closing lines for a date")
    ap.add_argument("--date",       required=True, help="YYYY-MM-DD")
    ap.add_argument("--force",      action="store_true", help="Bypass cache")
    ap.add_argument("--lines-only", action="store_true", help="Skip props")
    ap.add_argument("--props-only", action="store_true", help="Skip game lines")
    ap.add_argument("--verbose",    action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    run(
        args.date,
        force=args.force,
        lines_only=args.lines_only,
        props_only=args.props_only,
    )
