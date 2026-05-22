"""
run_walk_forward.py — Honest train-vs-holdout report across all models (PRED-02).

Headline R² numbers mix training and holdout. This script produces one
report that, per model, states the training R²/MAE, the holdout R²/MAE, and
the gap between them — the gap being the overfit signal.

Two honest holdout sources are used:
  * Prop models — holdout R²/MAE recomputed from data/models/prop_residuals.json
    (recorded predictions vs realised box scores — inherently out-of-sample),
    compared against the training R² in data/models/model_registry.json.
  * Win probability — holdout accuracy/Brier from data/models/win_prob_metrics.json.

When a feature matrix is available, run_walk_forward_for_model() drives the
walk_forward_backtester for a true expanding-window CV.

Usage:
    python scripts/run_walk_forward.py [--gate]

--gate makes the script exit 1 when any model's train−holdout R² gap exceeds
the overfit threshold (used as a CI guard — task PRED-07).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Callable, List, Optional, Sequence

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_MODELS_DIR    = os.path.join(PROJECT_DIR, "data", "models")
_OUTPUT_DIR    = os.path.join(PROJECT_DIR, "data", "output")
_RESIDUALS     = os.path.join(_MODELS_DIR, "prop_residuals.json")
_REGISTRY      = os.path.join(_MODELS_DIR, "model_registry.json")
_WIN_PROB      = os.path.join(_MODELS_DIR, "win_prob_metrics.json")
_REPORT_PATH   = os.path.join(_OUTPUT_DIR, "walk_forward_report.json")

PROP_STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
_MIN_HOLDOUT_ROWS = 30          # below this, holdout R² is not meaningful
OVERFIT_GAP_THRESHOLD = 0.15    # train−holdout R² gap that flags overfit


def _load_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


# ── holdout from recorded residuals ──────────────────────────────────────────

def holdout_from_residuals(residuals: list, stat: str) -> dict:
    """Recompute holdout R²/MAE for a prop stat from recorded (pred, actual) pairs.

    prop_residuals.json rows are predictions logged against realised box
    scores — genuinely out-of-sample, so this is a real holdout estimate.
    """
    from sklearn.metrics import mean_absolute_error, r2_score

    rows = [r for r in residuals
            if r.get("stat") == stat
            and r.get("predicted") is not None
            and r.get("actual") is not None]
    if len(rows) < _MIN_HOLDOUT_ROWS:
        return {"holdout_r2": None, "holdout_mae": None, "n": len(rows)}

    preds   = [float(r["predicted"]) for r in rows]
    actuals = [float(r["actual"]) for r in rows]
    return {
        "holdout_r2": round(float(r2_score(actuals, preds)), 4),
        "holdout_mae": round(float(mean_absolute_error(actuals, preds)), 4),
        "n": len(rows),
    }


# ── walk-forward CV for a model with a real feature matrix ───────────────────

def run_walk_forward_for_model(
    model_factory: Callable[[], Any],
    X,
    y,
    dates: Sequence,
    n_folds: int = 5,
) -> dict:
    """Walk-forward holdout vs in-sample train metrics for one model.

    Returns train_r2/train_mae (in-sample fit on all rows), holdout_r2/holdout_mae
    (expanding-window CV aggregate), and the train−holdout gap.
    """
    import numpy as np
    from sklearn.metrics import mean_absolute_error, r2_score

    from src.prediction.walk_forward_backtester import run_walk_forward

    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)

    wf = run_walk_forward(model_factory, X, y, dates, n_folds=n_folds)
    holdout_r2 = wf["aggregate"]["r2"]
    holdout_mae = wf["aggregate"]["mae"]

    in_sample = model_factory()
    in_sample.fit(X, y)
    train_pred = in_sample.predict(X)
    train_r2 = float(r2_score(y, train_pred))
    train_mae = float(mean_absolute_error(y, train_pred))

    return {
        "train_r2": round(train_r2, 4),
        "train_mae": round(train_mae, 4),
        "holdout_r2": round(holdout_r2, 4),
        "holdout_mae": round(holdout_mae, 4),
        "gap": round(train_r2 - holdout_r2, 4),
        "n_folds": n_folds,
    }


# ── full report ──────────────────────────────────────────────────────────────

def _gap(train_r2, holdout_r2) -> Optional[float]:
    if train_r2 is None or holdout_r2 is None:
        return None
    return round(float(train_r2) - float(holdout_r2), 4)


def build_model_report(
    residuals_path: Optional[str] = None,
    registry_path: Optional[str] = None,
    win_prob_path: Optional[str] = None,
    output_path: Optional[str] = None,
) -> dict:
    """Assemble the per-model train-vs-holdout report and write it to disk."""
    residuals = _load_json(residuals_path or _RESIDUALS, [])
    registry  = _load_json(registry_path or _REGISTRY, {})
    win_prob  = _load_json(win_prob_path or _WIN_PROB, {})
    output_path = output_path or _REPORT_PATH

    models: List[dict] = []
    for stat in PROP_STATS:
        reg = registry.get(f"props_{stat}", {})
        holdout = holdout_from_residuals(residuals, stat)
        train_r2 = reg.get("train_r2")
        models.append({
            "model": f"props_{stat}",
            "type": "regression",
            "train_r2": train_r2,
            "train_mae": reg.get("train_mae"),
            "holdout_r2": holdout["holdout_r2"],
            "holdout_mae": holdout["holdout_mae"],
            "holdout_n": holdout["n"],
            "gap": _gap(train_r2, holdout["holdout_r2"]),
            "holdout_source": "prop_residuals" if holdout["holdout_r2"] is not None
                              else "registry_only",
        })

    # Win probability is a classifier — report accuracy/Brier, no R².
    if win_prob:
        models.append({
            "model": "win_probability",
            "type": "classification",
            "holdout_accuracy": win_prob.get("accuracy"),
            "holdout_brier": win_prob.get("brier"),
            "holdout_n": win_prob.get("n_games"),
            "gap": None,
        })

    overfit = [m["model"] for m in models
               if m.get("gap") is not None and m["gap"] > OVERFIT_GAP_THRESHOLD]
    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "overfit_threshold": OVERFIT_GAP_THRESHOLD,
        "models": models,
        "overfit_models": overfit,
        "n_models": len(models),
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return report


def print_report(report: dict) -> None:
    """Print the train-vs-holdout report as a table."""
    print("\n" + "=" * 72)
    print("Walk-Forward Train-vs-Holdout Report")
    print("=" * 72)
    print(f"  {'model':<18} {'train R²':>9} {'holdout R²':>11} {'gap':>8}  {'n':>6}")
    print("  " + "-" * 60)
    for m in report["models"]:
        if m["type"] == "classification":
            acc = m.get("holdout_accuracy")
            print(f"  {m['model']:<18} {'(clf)':>9} "
                  f"{('acc ' + format(acc, '.3f')) if acc else 'n/a':>11} "
                  f"{'—':>8}  {str(m.get('holdout_n','?')):>6}")
            continue
        tr = m["train_r2"]; ho = m["holdout_r2"]; gap = m["gap"]
        print(f"  {m['model']:<18} {tr if tr is not None else 'n/a':>9} "
              f"{ho if ho is not None else 'n/a':>11} "
              f"{gap if gap is not None else 'n/a':>8}  {m.get('holdout_n','?'):>6}")
    print("  " + "-" * 60)
    if report["overfit_models"]:
        print(f"  ⚠ OVERFIT (gap > {report['overfit_threshold']}): "
              f"{', '.join(report['overfit_models'])}")
    else:
        print(f"  ✓ no model exceeds the {report['overfit_threshold']} overfit gap")
    print("=" * 72)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Walk-forward train-vs-holdout report")
    ap.add_argument("--gate", action="store_true",
                    help="Exit 1 if any model's train−holdout gap exceeds the threshold")
    args = ap.parse_args(argv)

    report = build_model_report()
    print_report(report)
    print(f"\n[run_walk_forward] report written -> {_REPORT_PATH}")

    if args.gate and report["overfit_models"]:
        print(f"[run_walk_forward] GATE FAILED — overfit models: {report['overfit_models']}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
