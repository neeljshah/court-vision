"""
build_position_priors.py — Build position_priors.json from NBA gamelog data.

Usage:
    python scripts/build_position_priors.py [--seasons 2022-23 2023-24 2024-25]

Output:
    data/models/position_priors.json
    Prints top-line stats: n positions filled, per-stat means by position.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build per-position Bayesian priors")
    parser.add_argument(
        "--seasons", nargs="+",
        default=["2022-23", "2023-24", "2024-25"],
        help="Seasons to include",
    )
    parser.add_argument(
        "--fetch-positions", action="store_true",
        help="Pre-fetch positions from NBA API for all player IDs in gamelogs "
             "(slow — ~0.5s per player, call once to populate data/cache/positions.json)",
    )
    args = parser.parse_args()

    from src.features.position_priors import (
        build_position_priors, _ALL_POSITIONS, get_position, _load_position_cache, _NBA_CACHE,
    )

    if args.fetch_positions:
        # Collect unique player IDs from all gamelogs
        import glob
        player_ids = set()
        for fpath in glob.glob(os.path.join(_NBA_CACHE, "gamelog_full_*.json")):
            try:
                data = json.load(open(fpath))
                rows = data if isinstance(data, list) else []
                for row in rows:
                    pid = row.get("player_id")
                    if pid:
                        player_ids.add(int(pid))
            except Exception:
                continue
        existing = set(int(k) for k in _load_position_cache())
        to_fetch = sorted(player_ids - existing)
        print(f"Fetching positions for {len(to_fetch)} players (already cached: {len(existing)})...")
        import time
        for i, pid in enumerate(to_fetch):
            pos = get_position(pid)
            if (i + 1) % 50 == 0:
                print(f"  {i+1}/{len(to_fetch)} fetched...")
        print(f"Done. Total cached: {len(_load_position_cache())} players")

    print(f"Building position priors for seasons: {args.seasons}")
    priors = build_position_priors(seasons=args.seasons)

    # Show how many positions were actually filled vs fallback
    pos_cache_size = len(_load_position_cache())
    if pos_cache_size < 100:
        print(f"\nNOTE: Only {pos_cache_size} positions cached. Run with --fetch-positions to "
              f"populate data/cache/positions.json (~569 players, ~5 min) for accurate priors.")

    # ── Top-line report ────────────────────────────────────────────────────────
    print("\n=== Position Prior Means ===")
    print(f"{'Stat':<8}", end="")
    for pos in _ALL_POSITIONS:
        print(f"  {pos:>7}", end="")
    print()
    print("-" * (8 + 9 * len(_ALL_POSITIONS)))

    for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
        print(f"{stat:<8}", end="")
        for pos in _ALL_POSITIONS:
            entry = priors.get(stat, {}).get(pos, {})
            mean = entry.get("mean", 0.0)
            n    = entry.get("n", 0)
            src  = "data" if n >= 30 else "fback"
            print(f"  {mean:>5.2f}{src[0]:1}", end="")
        print()

    print("\n=== Sample Sizes (n player-games) ===")
    print(f"{'Stat':<8}", end="")
    for pos in _ALL_POSITIONS:
        print(f"  {pos:>7}", end="")
    print()
    print("-" * (8 + 9 * len(_ALL_POSITIONS)))

    for stat in ("pts", "reb", "ast", "stl", "blk"):
        print(f"{stat:<8}", end="")
        for pos in _ALL_POSITIONS:
            entry = priors.get(stat, {}).get(pos, {})
            n = entry.get("n", 0)
            print(f"  {n:>7}", end="")
        print()

    output_path = os.path.join(PROJECT_DIR, "data", "models", "position_priors.json")
    print(f"\nWrote: {output_path}")


if __name__ == "__main__":
    main()
