"""Fix prop model underprediction bias.

Steps:
1. Patch prop_residuals.json: set line=actual for all records (fixes broken proxy)
2. Train Ridge meta-model for all 7 stats (creates prop_stack_meta.json)
3. Retrain win-prob calibration with corrected lines
4. Print before/after bias report
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from typing import List

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_RESIDUALS_PATH = os.path.join(PROJECT_DIR, "data", "models", "prop_residuals.json")
STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]


def _load_residuals() -> List[dict]:
    if not os.path.exists(_RESIDUALS_PATH):
        return []
    with open(_RESIDUALS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _print_bias_report(records: List[dict], label: str) -> None:
    print(f"\n=== {label} bias (predicted - actual) ===")
    for stat in STATS:
        rows = [r for r in records if r.get("stat") == stat
                and r.get("predicted") is not None and r.get("actual") is not None]
        if not rows:
            print(f"  {stat}: no data")
            continue
        mean_bias = sum(r["predicted"] - r["actual"] for r in rows) / len(rows)
        print(f"  {stat}: mean_bias={mean_bias:+.4f}  n={len(rows)}")


def _patch_residuals(records: List[dict]) -> List[dict]:
    patched = []
    for r in records:
        rec = dict(r)
        actual = rec.get("actual")
        if actual is not None:
            rec["line"] = actual
            # Recalculate edge_pct and direction relative to the (now-corrected) line
            predicted = rec.get("predicted")
            if predicted is not None and actual > 0:
                rec["edge_pct"] = round((predicted - actual) / actual, 6)
                rec["direction"] = "over" if predicted >= actual else "under"
            else:
                rec["edge_pct"] = 0.0
                rec["direction"] = "under"
        patched.append(rec)
    return patched


def _save_residuals(records: List[dict]) -> None:
    os.makedirs(os.path.dirname(_RESIDUALS_PATH), exist_ok=True)
    # Atomic write: temp file then rename
    dir_ = os.path.dirname(_RESIDUALS_PATH)
    fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)
        os.replace(tmp_path, _RESIDUALS_PATH)
    except Exception:
        os.unlink(tmp_path)
        raise


def main() -> None:
    records = _load_residuals()
    if not records:
        print(f"[fix_prop_bias] {_RESIDUALS_PATH} not found or empty — nothing to patch.")
        print("  Ridge meta and calibration will train with no data (no-op).")
    else:
        _print_bias_report(records, "BEFORE")
        patched = _patch_residuals(records)
        _save_residuals(patched)
        print(f"\n[fix_prop_bias] Patched {len(patched)} records — line set to actual.")

    # Train Ridge meta for all 7 stats
    print("\n[fix_prop_bias] Training Ridge meta-models...")
    from src.prediction.prop_model_stack import train_all_meta, train_calibration
    meta_results = train_all_meta()
    for stat, r in meta_results.items():
        print(f"  {stat}: coef={r['coef']:.4f} intercept={r['intercept']:.4f} "
              f"n={r['n']} r2={r['r2']:.3f}")

    # Retrain win-prob isotonic calibration
    print("\n[fix_prop_bias] Retraining win-prob calibration...")
    calib_results = train_calibration()
    for stat, r in calib_results.items():
        status = "fitted" if r.get("fitted") else "skipped"
        print(f"  {stat}: n={r.get('n', 0)}  over_rate={r.get('over_rate', 'n/a')}  {status}")

    # After summary
    print("\n=== AFTER — Ridge corrections that will be applied ===")
    for stat, r in meta_results.items():
        if r["n"] >= 10:
            print(f"  {stat}: pred * {r['coef']:.4f} + {r['intercept']:.4f}  (n={r['n']})")
        else:
            print(f"  {stat}: no correction (n={r['n']} < 10)")


if __name__ == "__main__":
    main()
