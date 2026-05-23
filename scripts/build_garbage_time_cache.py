"""
build_garbage_time_cache.py — Pre-compute per-player garbage minutes for all cached games.

Usage:
    conda run -n basketball_ai python scripts/build_garbage_time_cache.py
    conda run -n basketball_ai python scripts/build_garbage_time_cache.py --seasons 2024-25
    conda run -n basketball_ai python scripts/build_garbage_time_cache.py --dry-run

Output:
    data/cache/garbage_time/{season}.json
    data/models/garbage_time_meta.json

Summary printed to stdout.
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import sys
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.features.garbage_time_filter import (
    estimate_garbage_minutes_per_game,
    load_season_cache,
    save_season_cache,
)

_NBA_CACHE  = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _game_id_season(game_id: str) -> str:
    """Heuristic: derive season from game_id prefix.

    NBA game IDs are like 002YYXXXXX where YY is season year offset from 2000.
    0022200001 → season starting 2022 → '2022-23'
    0022300001 → '2023-24'
    0022400001 → '2024-25'
    """
    try:
        yy = int(game_id[3:5])
        return f"20{yy:02d}-{(yy+1):02d}"
    except (ValueError, IndexError):
        return "unknown"


def _get_final_margin(game_id: str) -> float:
    """Return final absolute margin from boxscore cache."""
    bs_path = os.path.join(_NBA_CACHE, f"boxscore_{game_id}.json")
    if not os.path.exists(bs_path):
        return 0.0
    try:
        with open(bs_path) as f:
            bs = json.load(f)
        return abs(float(bs.get("home_score", 0) or 0) - float(bs.get("away_score", 0) or 0))
    except Exception:
        return 0.0


def build_cache(seasons: list[str], dry_run: bool = False) -> dict:
    """
    Walk all boxscore files, compute garbage minutes per game, save cache.

    Returns summary statistics dict.
    """
    # Discover all boxscore game IDs
    boxscore_files = glob.glob(os.path.join(_NBA_CACHE, "boxscore_*.json"))
    all_game_ids = [
        os.path.basename(f).replace("boxscore_", "").replace(".json", "")
        for f in boxscore_files
    ]

    # Filter to requested seasons
    if seasons:
        filtered = []
        for gid in all_game_ids:
            s = _game_id_season(gid)
            if s in seasons:
                filtered.append(gid)
        game_ids = filtered
    else:
        game_ids = all_game_ids

    if not game_ids:
        print("No matching game IDs found for seasons:", seasons)
        return {}

    print(f"Processing {len(game_ids)} games across seasons {seasons} ...")

    # Group by season
    by_season: dict[str, list[str]] = {}
    for gid in game_ids:
        s = _game_id_season(gid)
        by_season.setdefault(s, []).append(gid)

    total_processed = 0
    total_with_garbage = 0
    total_garbage_min = 0.0
    season_summaries = {}

    for season, gids in sorted(by_season.items()):
        cache = load_season_cache(season) if not dry_run else {}
        new_games = 0
        season_garbage_games = 0
        season_garbage_min = 0.0

        for gid in gids:
            if gid in cache and not dry_run:
                # Already cached — tally it
                gt_map = cache[gid]
                if gt_map:
                    season_garbage_games += 1
                    season_garbage_min += sum(gt_map.values())
                total_processed += 1
                continue

            gt_map = estimate_garbage_minutes_per_game(gid)
            if not dry_run:
                cache[gid] = gt_map

            total_processed += 1
            new_games += 1

            if gt_map:
                season_garbage_games += 1
                total_with_garbage += 1
                gmin = sum(gt_map.values())
                season_garbage_min += gmin
                total_garbage_min += gmin

        if not dry_run and new_games > 0:
            save_season_cache(season, cache)

        pct = 100.0 * season_garbage_games / len(gids) if gids else 0.0
        avg_min = season_garbage_min / len(gids) if gids else 0.0
        season_summaries[season] = {
            "games": len(gids),
            "new_computed": new_games,
            "games_with_garbage": season_garbage_games,
            "pct_with_garbage": round(pct, 1),
            "avg_garbage_min": round(avg_min, 2),
        }
        print(f"  {season}: {len(gids)} games | {season_garbage_games} with garbage "
              f"({pct:.1f}%) | avg {avg_min:.2f} garbage-min/game")

    # Overall
    pct_total = 100.0 * total_with_garbage / total_processed if total_processed else 0.0
    avg_total = total_garbage_min / total_processed if total_processed else 0.0

    summary = {
        "n_games_processed":      total_processed,
        "n_games_with_garbage":   total_with_garbage,
        "pct_games_with_garbage": round(pct_total, 1),
        "avg_garbage_min_per_game": round(avg_total, 2),
        "by_season": season_summaries,
    }

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build garbage-time cache for prop models.")
    parser.add_argument(
        "--seasons", nargs="+",
        default=["2022-23", "2023-24", "2024-25"],
        help="Seasons to process (default: 2022-23 2023-24 2024-25)",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute but do not write cache files")
    args = parser.parse_args()

    summary = build_cache(seasons=args.seasons, dry_run=args.dry_run)
    if not summary:
        return

    print("\n=== SUMMARY ===")
    print(f"Total games processed : {summary['n_games_processed']}")
    print(f"Games with garbage    : {summary['n_games_with_garbage']} "
          f"({summary['pct_games_with_garbage']:.1f}%)")
    print(f"Avg garbage min/game  : {summary['avg_garbage_min_per_game']:.2f}")

    # Write metadata
    if not args.dry_run:
        os.makedirs(_MODEL_DIR, exist_ok=True)
        meta = {
            "version":                  "v1",
            "n_games_processed":        summary["n_games_processed"],
            "pct_games_with_garbage":   summary["pct_games_with_garbage"],
            "avg_garbage_min_per_game": summary["avg_garbage_min_per_game"],
            "computed_at":              datetime.utcnow().isoformat() + "Z",
            "seasons":                  args.seasons,
        }
        meta_path = os.path.join(_MODEL_DIR, "garbage_time_meta.json")
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)
        print(f"\nMeta written → {meta_path}")
        print(f"Cache dir    → data/cache/garbage_time/")


if __name__ == "__main__":
    main()
