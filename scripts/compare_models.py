"""
compare_models.py — Validate new model metrics vs previous before committing to git.

Usage:
    python scripts/compare_models.py --stat pts --threshold 0.02
    python scripts/compare_models.py --stat all --threshold 0.02

Exit codes: 0 = all pass, 1 = any fail
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

_METRICS_PATH = "data/models/model_metrics_history.json"
_PROP_STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]


def _load_history() -> dict[str, list[dict[str, Any]]]:
    """Load the metrics history file, returning empty dict on missing file."""
    if not os.path.exists(_METRICS_PATH):
        return {}
    with open(_METRICS_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _save_history(history: dict[str, list[dict[str, Any]]]) -> None:
    """Persist metrics history, creating parent directories as needed."""
    os.makedirs(os.path.dirname(_METRICS_PATH), exist_ok=True)
    with open(_METRICS_PATH, "w", encoding="utf-8") as fh:
        json.dump(history, fh, indent=2)


def _load_new_metrics(stat: str) -> dict[str, Any] | None:
    """Read new metrics from props_{stat}.json if it has an r2 key.

    Returns None if no metrics file exists for this stat.
    """
    model_json = os.path.join("data", "models", f"props_{stat}.json")
    if not os.path.exists(model_json):
        return None
    with open(model_json, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if "r2" in data:
        return {
            "r2": float(data["r2"]),
            "mae": float(data.get("mae", 0.0)),
            "trained_at": data.get("trained_at", datetime.utcnow().isoformat()),
        }
    return None


def compare_models(stat: str, threshold: float = 0.02) -> dict[str, Any]:
    """Compare new vs previous model R2 for a given prop stat.

    Parameters
    ----------
    stat:
        One of the 7 prop stats (pts, reb, ast, fg3m, stl, blk, tov).
    threshold:
        Maximum allowed R2 regression (positive float). Default 0.02.

    Returns
    -------
    dict with keys: status ("PASS" | "FAIL" | "SKIP"), stat, delta,
    new_r2, prev_r2, reason.
    """
    history = _load_history()
    new_metrics = _load_new_metrics(stat)

    if new_metrics is None:
        # No new model artifact — nothing to compare
        return {
            "status": "SKIP",
            "stat": stat,
            "delta": 0.0,
            "new_r2": None,
            "prev_r2": None,
            "reason": f"No props_{stat}.json found; skipping",
        }

    new_r2 = new_metrics["r2"]
    stat_history = history.get(stat, [])

    # Append new metrics to history regardless of outcome
    stat_history.append(new_metrics)
    history[stat] = stat_history
    _save_history(history)

    if len(stat_history) < 2:
        # First run — no previous version to compare against
        print(f"[FIRST RUN] {stat}: R2={new_r2:.4f} (no previous version)")
        return {
            "status": "PASS",
            "stat": stat,
            "delta": 0.0,
            "new_r2": new_r2,
            "prev_r2": None,
            "reason": "First run — no prior history to compare against",
        }

    prev_r2 = stat_history[-2]["r2"]
    delta = new_r2 - prev_r2
    passed = delta >= -threshold

    status = "PASS" if passed else "FAIL"
    sign = "+" if delta >= 0 else ""
    print(f"[{status}] {stat}: R2={new_r2:.4f} (prev={prev_r2:.4f}, delta={sign}{delta:.4f})")

    return {
        "status": status,
        "stat": stat,
        "delta": round(delta, 6),
        "new_r2": new_r2,
        "prev_r2": prev_r2,
        "reason": f"delta={sign}{delta:.4f}, threshold=-{threshold}",
    }


def main() -> None:
    """CLI entry point for model validation gate."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Validate new model R2 vs previous version before git commit."
    )
    parser.add_argument(
        "--stat",
        default="all",
        help="Prop stat to check, or 'all' (default: all)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.02,
        help="Max allowed R2 regression (default: 0.02)",
    )
    args = parser.parse_args()

    stats = _PROP_STATS if args.stat == "all" else [args.stat]
    results = [compare_models(s, args.threshold) for s in stats]

    failed = [r for r in results if r["status"] == "FAIL"]
    for r in failed:
        print(
            f"GATE FAIL: {r['stat']} delta={r['delta']:.4f} "
            f"(threshold=-{args.threshold})"
        )

    if not failed:
        skipped = [r for r in results if r["status"] == "SKIP"]
        if len(skipped) == len(results):
            print("No model artifacts found — first-run gate passed.")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
