"""weekly_review.py — Weekly model health and calibration review.

Run every Sunday morning or after sufficient residuals accumulate.

Usage:
    python scripts/weekly_review.py [--min-samples N]
"""
from __future__ import annotations

import json
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_RESIDUALS_PATH = os.path.join(PROJECT_DIR, "data", "models", "prop_residuals.json")
STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]


def review_calibration(min_samples: int = 30) -> dict:
    """Run A/B calibration test. Returns results dict."""
    if not os.path.exists(_RESIDUALS_PATH):
        print("[weekly_review] No residuals found — run predictions first.")
        return {}

    with open(_RESIDUALS_PATH, encoding="utf-8") as f:
        residuals = json.load(f)

    # Import ab_test_calibration from fit_prop_calibration
    sys.path.insert(0, os.path.join(PROJECT_DIR, "scripts"))
    from fit_prop_calibration import ab_test_calibration

    results = ab_test_calibration(residuals)
    return results


def main(min_samples: int = 30) -> None:
    print("=" * 60)
    print("Weekly Review — Calibration A/B Test")
    print("=" * 60)

    results = review_calibration(min_samples)
    if not results:
        return

    promoted_count = sum(1 for r in results.values() if r.get("promoted"))
    print(f"\nCalibration results ({promoted_count}/{len(results)} models promoted):")
    for stat, r in results.items():
        if "reason" in r:
            print(f"  {stat}: skipped ({r['reason']})")
            continue
        status = "PROMOTED" if r.get("promoted") else "kept"
        old = f"{r.get('old_brier', 'n/a'):.4f}" if isinstance(r.get("old_brier"), float) else "n/a"
        new = f"{r.get('new_brier', 0):.4f}"
        print(f"  {stat}: old_brier={old}  new_brier={new}  [{status}]")

    print("\nDone.")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Weekly model health review")
    p.add_argument("--min-samples", type=int, default=30)
    args = p.parse_args()
    main(min_samples=args.min_samples)
