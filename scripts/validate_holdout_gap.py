#!/usr/bin/env python3
"""
validate_holdout_gap.py — CLI: check train-holdout R² gap across all 7 prop stats.

Usage:
    python scripts/validate_holdout_gap.py --threshold 0.08 [--registry data/models/model_registry.json]

Exit 0 if all stats pass, exit 1 if any stat exceeds threshold or registry missing.
"""
import argparse
import json
import sys
from pathlib import Path

STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate train-holdout R² gap for all 7 prop stats."
    )
    parser.add_argument("--threshold", type=float, default=0.08)
    parser.add_argument("--registry", default="data/models/model_registry.json")
    args = parser.parse_args()

    reg_path = Path(args.registry)
    if not reg_path.exists():
        print(f"[ERROR] Registry not found: {reg_path}", file=sys.stderr)
        sys.exit(1)

    registry = json.loads(reg_path.read_text())
    failures = []
    for stat in STATS:
        key = f"props_{stat}"
        entry = registry.get(key)
        if entry is None:
            failures.append(f"{stat}: MISSING from registry")
            continue
        train_r2 = entry.get("train_r2", float("nan"))
        holdout_r2 = entry.get("holdout_r2", float("nan"))
        gap = abs(train_r2 - holdout_r2)
        status = "PASS" if gap <= args.threshold else "FAIL"
        print(
            f"  {stat:5s}  train_r2={train_r2:.3f}  holdout_r2={holdout_r2:.3f}"
            f"  gap={gap:.3f}  [{status}]"
        )
        if status == "FAIL":
            failures.append(f"{stat}: gap={gap:.3f} > threshold={args.threshold}")

    if failures:
        print("\n[FAIL] Gap threshold exceeded:")
        for f in failures:
            print(f"  {f}")
        sys.exit(1)
    print(f"\n[PASS] All {len(STATS)} stats within gap threshold ({args.threshold})")


if __name__ == "__main__":
    main()
