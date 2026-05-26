"""probe_R21_N1_pts_ast_audit.py — PTS/AST artifact-load audit (R21_N1).

R19_L7 observed the production prediction path returning None for PTS and AST
on every starter while REB/FG3M/STL/BLK/TOV produced values. This probe makes
that observation cheaply reproducible: it iterates over STATS, loads the base
learners, runs `predict_pergame` on a synthetic feature row, and records
per-stat coverage to `data/cache/probe_R21_N1_results.json`.

Re-run any time the prop_pergame load path or model artifacts change.

Usage:
    python scripts/improve_loop/probe_R21_N1_pts_ast_audit.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

OUT_PATH = os.path.join(PROJECT_DIR, "data", "cache", "probe_R21_N1_results.json")


def _build_synthetic_row() -> dict:
    """Plausible mid-season starter feature row — matches the test fixture."""
    from src.prediction.prop_pergame import feature_columns
    row = {c: 0.0 for c in feature_columns()}
    row.update({
        "l5_pts": 25.0, "l10_pts": 23.0, "ewma_pts": 24.0, "prev_pts": 22.0,
        "l5_reb": 5.0,  "l10_reb": 5.0,  "ewma_reb": 5.0,  "prev_reb": 5.0,
        "l5_ast": 4.0,  "l10_ast": 4.0,  "ewma_ast": 4.0,  "prev_ast": 4.0,
        "l5_fg3m": 2.0, "l10_fg3m": 2.0, "ewma_fg3m": 2.0, "prev_fg3m": 2.0,
        "l5_stl": 1.0,  "l10_stl": 1.0,  "ewma_stl": 1.0,  "prev_stl": 1.0,
        "l5_blk": 0.5,  "l10_blk": 0.5,  "ewma_blk": 0.5,  "prev_blk": 0.5,
        "l5_tov": 2.5,  "l10_tov": 2.5,  "ewma_tov": 2.5,  "prev_tov": 2.5,
        "l5_min": 32.0, "l10_min": 32.0, "ewma_min": 32.0, "prev_min": 32.0,
        "is_home": 1, "rest_days": 2.0, "games_played": 20,
    })
    return row


def run_audit() -> dict:
    """Audit the load + predict paths for every stat. Returns the result dict.

    Each per-stat entry captures:
        n_base_learners  — output of load_pergame_model
        q50_present      — whether _load_q50_model returns non-None
        pred             — output of predict_pergame on the synthetic row
        pred_is_none     — boolean shortcut used for coverage stats
        path             — which dispatch path actually ran (q50 vs blend)
    """
    from src.prediction.prop_pergame import (
        STATS,
        _MODEL_DIR,
        _USE_Q50_STATS,
        load_pergame_model,
        _load_q50_model,
        predict_pergame,
    )

    row = _build_synthetic_row()
    per_stat: dict = {}
    for stat in STATS:
        learners = load_pergame_model(stat)
        q50 = _load_q50_model(stat, _MODEL_DIR)
        try:
            pred = predict_pergame(stat, row)
            err = None
        except Exception as exc:  # noqa: BLE001
            pred = None
            err = f"{type(exc).__name__}: {exc}"
        per_stat[stat] = {
            "n_base_learners": len(learners),
            "q50_present": q50 is not None,
            "pred": pred,
            "pred_is_none": pred is None,
            "path": "q50" if stat in _USE_Q50_STATS else "blend",
            "error": err,
        }

    coverage = {
        s: ("NON_NONE" if not v["pred_is_none"] else "NONE")
        for s, v in per_stat.items()
    }
    n_non_none = sum(1 for v in per_stat.values() if not v["pred_is_none"])

    result = {
        "probe": "R21_N1",
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "model_dir": _MODEL_DIR,
        "n_stats_with_pred": n_non_none,
        "n_stats_total": len(STATS),
        "coverage": coverage,
        "per_stat": per_stat,
        "L7_regression_present": (per_stat.get("pts", {}).get("pred_is_none", True)
                                  or per_stat.get("ast", {}).get("pred_is_none", True)),
    }
    return result


def main() -> int:
    result = run_audit()
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"\n  R21_N1 PTS/AST audit  ({result['timestamp']})")
    print(f"  model_dir: {result['model_dir']}")
    print(f"  coverage: {result['n_stats_with_pred']}/{result['n_stats_total']} stats produce non-None\n")
    print(f"  {'stat':<6}{'path':<8}{'learners':<10}{'q50':<6}{'pred':<10}{'status'}")
    print(f"  {'----':<6}{'----':<8}{'--------':<10}{'---':<6}{'----':<10}{'------'}")
    for s, v in result["per_stat"].items():
        status = "OK" if not v["pred_is_none"] else "NONE"
        pred_str = f"{v['pred']:.3f}" if v["pred"] is not None else "None"
        print(f"  {s:<6}{v['path']:<8}{v['n_base_learners']:<10}"
              f"{'Y' if v['q50_present'] else 'N':<6}{pred_str:<10}{status}")

    if result["L7_regression_present"]:
        print("\n  STATUS: L7 REGRESSION PRESENT — PTS or AST is None.")
        print("  Fix: ensure prop_pergame._resolve_model_dir() finds the correct")
        print("       data/models/ directory (with props_pg_pts.json + friends).")
    else:
        print("\n  STATUS: OK — PTS + AST both return non-None.")
    print(f"\n  Wrote {OUT_PATH}\n")
    return 0 if not result["L7_regression_present"] else 1


if __name__ == "__main__":
    sys.exit(main())
