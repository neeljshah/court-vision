"""
scripts/cv_lift_report.py — CV-feature lift measurement report.

Loads prop residuals, splits records by presence of CV-feature columns
(defender_distance / spacing / fatigue), computes R² and MAE per stat for
each group, then prints a delta table and saves JSON to data/output/.

Exits 0 in all cases, including when no CV data exists.
"""

from __future__ import annotations

import json
import math
import os
import sys
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_RESIDUALS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "models", "prop_residuals.json",
)
_OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "output",
)
_OUTPUT_PATH = os.path.join(_OUTPUT_DIR, "cv_lift_report.json")

# CV-feature column names used to detect enriched records
_CV_COLUMNS = ("defender_distance", "spacing", "fatigue")

# Stats to evaluate
_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_cv_features(record: Dict[str, Any]) -> bool:
    """Return True when at least one CV column is present and not None/NaN."""
    for col in _CV_COLUMNS:
        val = record.get(col)
        if val is not None:
            try:
                if not math.isnan(float(val)):
                    return True
            except (TypeError, ValueError):
                pass
    return False


def _r2(actuals: List[float], predicted: List[float]) -> Optional[float]:
    """Return R² for two parallel lists; None when fewer than 2 samples."""
    n = len(actuals)
    if n < 2:
        return None
    mean_a = sum(actuals) / n
    ss_tot = sum((a - mean_a) ** 2 for a in actuals)
    if ss_tot == 0.0:
        return None
    ss_res = sum((a - p) ** 2 for a, p in zip(actuals, predicted))
    return 1.0 - ss_res / ss_tot


def _mae(actuals: List[float], predicted: List[float]) -> Optional[float]:
    """Return MAE for two parallel lists; None when empty."""
    n = len(actuals)
    if n == 0:
        return None
    return sum(abs(a - p) for a, p in zip(actuals, predicted)) / n


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def compute_lift(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute per-stat R² and MAE for CV vs non-CV groups.

    Parameters
    ----------
    records:
        List of residual dicts.  Must contain at minimum ``stat``,
        ``actual``, and ``predicted`` keys.

    Returns
    -------
    dict
        Nested result: ``{stat: {cv: {...}, no_cv: {...}, delta: {...}}}``
        plus a ``"has_cv_data"`` top-level boolean.
    """
    # Bucket records into cv / no-cv per stat
    buckets: Dict[str, Dict[str, tuple[list, list]]] = {
        s: {"cv": ([], []), "no_cv": ([], [])} for s in _STATS
    }

    cv_count = 0
    for rec in records:
        stat = rec.get("stat")
        if stat not in _STATS:
            continue
        actual = rec.get("actual")
        predicted = rec.get("predicted")
        if actual is None or predicted is None:
            continue
        try:
            a, p = float(actual), float(predicted)
        except (TypeError, ValueError):
            continue

        if _has_cv_features(rec):
            cv_count += 1
            buckets[stat]["cv"][0].append(a)
            buckets[stat]["cv"][1].append(p)
        else:
            buckets[stat]["no_cv"][0].append(a)
            buckets[stat]["no_cv"][1].append(p)

    has_cv_data = cv_count > 0

    result: Dict[str, Any] = {"has_cv_data": has_cv_data, "stats": {}}

    for stat in _STATS:
        cv_a, cv_p = buckets[stat]["cv"]
        ncv_a, ncv_p = buckets[stat]["no_cv"]

        if not has_cv_data:
            result["stats"][stat] = "no CV data"
            continue

        cv_r2 = _r2(cv_a, cv_p)
        cv_mae = _mae(cv_a, cv_p)
        ncv_r2 = _r2(ncv_a, ncv_p)
        ncv_mae = _mae(ncv_a, ncv_p)

        delta_r2: Optional[float] = None
        delta_mae: Optional[float] = None
        if cv_r2 is not None and ncv_r2 is not None:
            delta_r2 = round(cv_r2 - ncv_r2, 6)
        if cv_mae is not None and ncv_mae is not None:
            delta_mae = round(cv_mae - ncv_mae, 6)

        result["stats"][stat] = {
            "cv": {
                "n": len(cv_a),
                "r2": round(cv_r2, 6) if cv_r2 is not None else None,
                "mae": round(cv_mae, 6) if cv_mae is not None else None,
            },
            "no_cv": {
                "n": len(ncv_a),
                "r2": round(ncv_r2, 6) if ncv_r2 is not None else None,
                "mae": round(ncv_mae, 6) if ncv_mae is not None else None,
            },
            "delta": {
                "r2": delta_r2,
                "mae": delta_mae,
            },
        }

    return result


def _print_table(report: Dict[str, Any]) -> None:
    """Print a human-readable delta table to stdout."""
    has_cv = report.get("has_cv_data", False)

    print("\n=== CV Lift Report ===")
    if not has_cv:
        print("No CV-feature data found in residuals — delta table unavailable.")
        print(f"{'Stat':<8}  {'Status'}")
        print("-" * 30)
        for stat in _STATS:
            print(f"{stat:<8}  no CV data")
        return

    header = f"{'Stat':<8}  {'Δ R²':>10}  {'Δ MAE':>10}  {'N(cv)':>8}  {'N(no-cv)':>10}"
    print(header)
    print("-" * len(header))
    for stat in _STATS:
        entry = report["stats"].get(stat)
        if entry == "no CV data" or not isinstance(entry, dict):
            print(f"{stat:<8}  {'no CV data':>10}")
            continue
        delta = entry.get("delta", {})
        dr2 = entry["delta"].get("r2")
        dmae = entry["delta"].get("mae")
        n_cv = entry["cv"].get("n", 0)
        n_ncv = entry["no_cv"].get("n", 0)
        dr2_s = f"{dr2:+.4f}" if dr2 is not None else "    N/A"
        dmae_s = f"{dmae:+.4f}" if dmae is not None else "    N/A"
        print(f"{stat:<8}  {dr2_s:>10}  {dmae_s:>10}  {n_cv:>8}  {n_ncv:>10}")


def run(residuals_path: str = _RESIDUALS_PATH, output_path: str = _OUTPUT_PATH) -> int:
    """Load residuals, compute lift, print table, save JSON.

    Returns
    -------
    int
        Exit code — always 0.
    """
    # Load residuals
    if not os.path.exists(residuals_path):
        print(f"[cv_lift_report] Residuals file not found: {residuals_path}")
        print("[cv_lift_report] Writing empty report.")
        report: Dict[str, Any] = {
            "has_cv_data": False,
            "stats": {s: "no CV data" for s in _STATS},
        }
    else:
        with open(residuals_path, "r", encoding="utf-8") as fh:
            records: List[Dict[str, Any]] = json.load(fh)
        report = compute_lift(records)

    _print_table(report)

    # Save JSON
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"\n[cv_lift_report] Saved to {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
