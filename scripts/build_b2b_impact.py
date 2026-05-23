"""
build_b2b_impact.py — Fit B2B multiplier curve from gamelog data.

Usage:
    python scripts/build_b2b_impact.py [--seasons 2022-23 2023-24 2024-25]

Output:
    data/models/b2b_curve.json
    Prints B2B multiplier matrix: top affected stats × age buckets.
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
    parser = argparse.ArgumentParser(description="Fit B2B impact multipliers")
    parser.add_argument(
        "--seasons", nargs="+",
        default=["2022-23", "2023-24", "2024-25"],
    )
    args = parser.parse_args()

    from src.features.back_to_back_impact import fit_b2b_curve, _AGE_LABELS

    print(f"Fitting B2B curve for seasons: {args.seasons}")
    curve = fit_b2b_curve(seasons=args.seasons)

    focus_stats = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "fg_pct")

    print("\n=== B2B Multiplier Matrix (ratio = b2b_avg / reg_avg) ===")
    print("Values below 1.0 = performance decline on second night\n")

    header = f"{'Stat':<8}"
    for al in _AGE_LABELS:
        header += f"  {al:>8}"
    print(header)
    print("-" * (8 + 11 * len(_AGE_LABELS)))

    for stat in focus_stats:
        row = f"{stat:<8}"
        for al in _AGE_LABELS:
            entry = curve.get(stat, {}).get(al, {})
            ratio  = entry.get("ratio", 1.0)
            n_b2b  = entry.get("n_b2b", 0)
            row += f"  {ratio:.4f}({n_b2b:4d})"
        print(row)

    print()
    print("=== Most Impacted Stat × Age Bucket Pairs ===")

    impacts = []
    for stat in focus_stats:
        for al in _AGE_LABELS:
            entry = curve.get(stat, {}).get(al, {})
            ratio = entry.get("ratio", 1.0)
            n     = entry.get("n_b2b", 0)
            if n > 0:
                impacts.append((1.0 - ratio, stat, al, ratio, n))

    impacts.sort(reverse=True)
    for impact, stat, al, ratio, n in impacts[:8]:
        print(f"  {stat:<8} age={al:<6}  ratio={ratio:.4f}  delta={impact:+.4f}  n_b2b={n}")

    output_path = os.path.join(PROJECT_DIR, "data", "models", "b2b_curve.json")
    print(f"\nWrote: {output_path}")


if __name__ == "__main__":
    main()
