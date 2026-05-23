"""
build_injury_rampup.py — Fit injury rampup curve from gamelog data.

Usage:
    python scripts/build_injury_rampup.py [--seasons 2022-23 2023-24 2024-25]

Output:
    data/models/injury_rampup.json
    Prints rampup matrix: stats × (days_bucket, games_since_return).
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
    parser = argparse.ArgumentParser(description="Fit injury rampup multipliers")
    parser.add_argument(
        "--seasons", nargs="+",
        default=["2022-23", "2023-24", "2024-25"],
    )
    args = parser.parse_args()

    from src.features.injury_rampup import fit_rampup_curve, _DAYS_BUCKETS, _GAME_BUCKET_LABELS

    print(f"Fitting rampup curve for seasons: {args.seasons}")
    curve = fit_rampup_curve(seasons=args.seasons)

    days_labels  = [b[0] for b in _DAYS_BUCKETS]
    game_labels  = _GAME_BUCKET_LABELS
    focus_stats  = ("pts", "reb", "ast", "stl", "blk")

    print("\n=== Rampup Multiplier Matrix (ratio = actual / season_avg) ===")
    print("Format: ratio (n samples)\n")

    for stat in focus_stats:
        print(f"  -- {stat.upper()} --")
        header = f"{'':12}"
        for gl in game_labels:
            header += f"  game_{gl:>3}"
        print(header)

        for dl in days_labels:
            row = f"  days={dl:6}"
            for gl in game_labels:
                key = f"{dl}_{gl}"
                entry = curve.get(stat, {}).get(key, {})
                ratio = entry.get("ratio", 1.0)
                n     = entry.get("n", 0)
                row += f"  {ratio:.3f}({n:4d})"
            print(row)
        print()

    output_path = os.path.join(PROJECT_DIR, "data", "models", "injury_rampup.json")
    print(f"Wrote: {output_path}")

    # Summary: how many bucket cells have real data (n >= 5)?
    real_cells = sum(
        1 for s in curve for k in curve[s] if curve[s][k].get("n", 0) >= 5
    )
    total_cells = len(focus_stats) * len(days_labels) * len(game_labels)
    print(f"Coverage: {real_cells} / {total_cells} cells have n>=5 games")


if __name__ == "__main__":
    main()
