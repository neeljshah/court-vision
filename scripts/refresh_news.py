"""
refresh_news.py — CLI to refresh all news/injury caches for a given date.

Usage:
    python scripts/refresh_news.py --date 2026-05-22
    python scripts/refresh_news.py            # defaults to today

Prints a one-line summary:
    [news] 47 injury records, 12 OUT, 8 QUESTIONABLE

Exit codes:
    0 — success (at least one source returned data)
    1 — all sources failed
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone

# Ensure project root is on the path
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s %(name)s: %(message)s",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="refresh_news",
        description="Refresh NBA injury / lineup news caches.",
    )
    parser.add_argument(
        "--date",
        default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        help="Game date (YYYY-MM-DD).  Defaults to today.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass 1-hour cache and re-fetch all sources.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable detailed logging output.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)
        logging.getLogger("src.data.news_ingest").setLevel(logging.DEBUG)
        logging.getLogger("src.data.lineup_news").setLevel(logging.DEBUG)

    game_date = args.date
    print(f"[news] Refreshing news for {game_date} ...")

    # ── Step 1: Injury news ────────────────────────────────────────────────
    from src.data.news_ingest import fetch_all_injury_news

    records = fetch_all_injury_news(game_date=game_date, force=args.force)

    total   = len(records)
    n_out   = sum(1 for r in records if r.get("status", "").upper() == "OUT")
    n_doubt = sum(1 for r in records if r.get("status", "").upper() == "DOUBTFUL")
    n_quest = sum(1 for r in records if r.get("status", "").upper() == "QUESTIONABLE")
    n_prob  = sum(1 for r in records if r.get("status", "").upper() == "PROBABLE")

    # Source breakdown
    sources: dict[str, int] = {}
    for r in records:
        src = r.get("source", "unknown")
        sources[src] = sources.get(src, 0) + 1

    source_str = ", ".join(f"{src}:{cnt}" for src, cnt in sorted(sources.items()))

    print(
        f"[news] {total} injury records, "
        f"{n_out} OUT, {n_doubt} DOUBTFUL, {n_quest} QUESTIONABLE, {n_prob} PROBABLE"
        + (f" | sources: {source_str}" if source_str else "")
    )

    # ── Step 2: Lineup refresh for teams with OUT/DOUBTFUL players ────────
    from src.data.lineup_news import get_projected_starters_by_abbrev

    affected_teams = {
        r.get("team", "").upper()
        for r in records
        if r.get("status", "").upper() in ("OUT", "DOUBTFUL")
        and r.get("team", "")
    }

    if affected_teams:
        print(f"[news] Refreshing projected lineups for {len(affected_teams)} affected teams ...")
        refreshed_lineups = 0
        for team in sorted(affected_teams):
            try:
                starters = get_projected_starters_by_abbrev(team, game_date, force=args.force)
                if starters:
                    refreshed_lineups += 1
                    if args.verbose:
                        print(f"  {team}: {starters}")
            except Exception as exc:
                print(f"  [warn] {team} lineup refresh failed: {exc}", file=sys.stderr)
        print(f"[news] {refreshed_lineups}/{len(affected_teams)} team lineups refreshed.")

    if total == 0:
        print("[news] WARNING: No injury records returned — all sources may be blocked.",
              file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
