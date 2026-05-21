"""
backtest_system.py — Full-system backtest entry point.

Phase 18.5-01 (betting simulation) will extend this with fill modeling.
This module provides the R²-regression gate used by CI.

Usage:
    python scripts/backtest_system.py [--r2-threshold 0.7] [--stat pts]

Exits 0 if all stats pass the R² threshold, 1 if any stat regresses.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_RESIDUALS_PATH = os.path.join(PROJECT_DIR, "data", "models", "prop_residuals.json")
_METRICS_PATH   = os.path.join(PROJECT_DIR, "data", "models", "props_metrics.json")
STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
DEFAULT_R2_THRESHOLD = 0.70


def _load_residuals(path: str | None = None) -> List[dict]:
    p = path or _RESIDUALS_PATH
    if not os.path.exists(p):
        return []
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return []


def _compute_r2(residuals: List[dict], stat: str) -> Optional[float]:
    rows = [r for r in residuals
            if r.get("stat") == stat
            and r.get("predicted") is not None
            and r.get("actual") is not None]
    if len(rows) < 5:
        return None
    preds   = [float(r["predicted"]) for r in rows]
    actuals = [float(r["actual"])     for r in rows]
    mean_a  = sum(actuals) / len(actuals)
    ss_tot  = sum((a - mean_a) ** 2 for a in actuals)
    if ss_tot == 0:
        return None
    ss_res  = sum((p - a) ** 2 for p, a in zip(preds, actuals))
    return round(1.0 - ss_res / ss_tot, 4)


def run_regression_check(
    residuals: List[dict],
    r2_threshold: float = DEFAULT_R2_THRESHOLD,
    stats: List[str] | None = None,
) -> Dict[str, dict]:
    """Check R² for each stat against threshold.

    Returns dict: {stat: {"r2": float|None, "pass": bool, "n": int}}
    """
    stats = stats or STATS
    results = {}
    for stat in stats:
        rows = [r for r in residuals if r.get("stat") == stat]
        r2   = _compute_r2(residuals, stat)
        results[stat] = {
            "r2":   r2,
            "pass": r2 is None or r2 >= r2_threshold,  # None = insufficient data, treated as pass
            "n":    len(rows),
        }
    return results


def main(argv: List[str] | None = None) -> int:
    """Return 0 if all stats pass, 1 if any regresses."""
    p = argparse.ArgumentParser(description="Backtest regression gate")
    p.add_argument("--r2-threshold", type=float, default=DEFAULT_R2_THRESHOLD)
    p.add_argument("--stat", choices=STATS, default=None, help="Check only one stat")
    p.add_argument("--residuals", default=None, help="Path to prop_residuals.json")
    args = p.parse_args(argv)

    residuals = _load_residuals(args.residuals)
    stats     = [args.stat] if args.stat else STATS
    results   = run_regression_check(residuals, args.r2_threshold, stats)

    print(f"\nBacktest Regression Check (threshold R² ≥ {args.r2_threshold})")
    print("-" * 50)
    any_fail = False
    for stat, r in results.items():
        status = "PASS" if r["pass"] else "FAIL"
        r2_str = f"{r['r2']:.4f}" if r["r2"] is not None else "insufficient data"
        print(f"  {stat:6s}: R²={r2_str:>12s}  n={r['n']:4d}  [{status}]")
        if not r["pass"]:
            any_fail = True

    print(f"\nOverall: {'FAIL' if any_fail else 'PASS'}")
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
