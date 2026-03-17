"""
model_pipeline.py — Unified train/evaluate/save pipeline for all Phase 3 models.

Orchestrates: data fetch → feature build → train → evaluate → save → report.

Public API
----------
    run(model_name, seasons, force_retrain)  -> dict
    evaluate_all(seasons)                    -> dict
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from typing import List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)
_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")
_REPORT_DIR = os.path.join(PROJECT_DIR, "data", "model_reports")

SUPPORTED_MODELS = ["win_probability", "player_props"]


def run(
    model_name: str = "win_probability",
    seasons: Optional[List[str]] = None,
    force_retrain: bool = False,
    output_path: Optional[str] = None,
) -> dict:
    """
    Train (or load cached) a named model and return evaluation metrics.

    Args:
        model_name:    One of SUPPORTED_MODELS.
        seasons:       Season list (default: last 3).
        force_retrain: Always retrain even if saved model exists.
        output_path:   Override model save path.

    Returns:
        Dict with model_name, metrics, feature_importance, saved_path.
    """
    if model_name not in SUPPORTED_MODELS:
        raise ValueError(f"Unknown model '{model_name}'. Supported: {SUPPORTED_MODELS}")

    os.makedirs(_MODEL_DIR, exist_ok=True)
    os.makedirs(_REPORT_DIR, exist_ok=True)

    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    if model_name == "win_probability":
        return _run_win_prob(seasons, force_retrain, output_path)
    if model_name == "player_props":
        return _run_player_props(seasons, force_retrain)

    return {"error": f"model {model_name} not implemented yet"}


def evaluate_all(seasons: Optional[List[str]] = None) -> dict:
    """
    Run backtests for all trained models and produce a consolidated report.

    Args:
        seasons: Seasons to evaluate (default: last 3).

    Returns:
        Dict mapping model_name → backtest results.
    """
    results = {}
    for name in SUPPORTED_MODELS:
        print(f"\n── {name} ──")
        try:
            results[name] = _backtest_model(name, seasons)
        except Exception as e:
            results[name] = {"error": str(e)}

    # Save consolidated report
    ts     = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = {"timestamp": ts, "seasons": seasons, "results": results}
    rpath  = os.path.join(_REPORT_DIR, f"eval_{ts}.json")
    with open(rpath, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved → {rpath}")
    return report


# ── Model-specific runners ─────────────────────────────────────────────────────

def _run_win_prob(
    seasons: List[str],
    force_retrain: bool,
    output_path: Optional[str],
) -> dict:
    """Train or load win probability model and return metrics."""
    from src.prediction.win_probability import train, load, backtest

    saved = output_path or os.path.join(_MODEL_DIR, "win_probability.pkl")
    if os.path.exists(saved) and not force_retrain:
        print(f"Loading cached model from {saved}")
        model = load(saved)
    else:
        print("Training win probability model ...")
        model = train(seasons=seasons, output_path=saved)

    print("Running backtest ...")
    bt = backtest(seasons=seasons)

    fi = model.feature_importance(top_n=10)
    report = {
        "model_name":         "win_probability",
        "seasons":            seasons,
        "saved_path":         saved,
        "backtest":           bt,
        "feature_importance": fi,
    }
    rpath = os.path.join(_REPORT_DIR, "win_probability_latest.json")
    with open(rpath, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"Report → {rpath}")
    return report


def _run_player_props(seasons: List[str], force_retrain: bool) -> dict:
    """Train player prop models (pts, reb, ast) and return metrics."""
    from src.prediction.player_props import train_props
    print("Training player prop models ...")
    results = train_props(seasons=seasons, force=force_retrain)
    rpath = os.path.join(_REPORT_DIR, "player_props_latest.json")
    report = {"model_name": "player_props", "seasons": seasons, "metrics": results}
    with open(rpath, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Report → {rpath}")
    return report


def _backtest_model(model_name: str, seasons: Optional[List[str]]) -> dict:
    """Run backtest for the named model."""
    if model_name == "win_probability":
        from src.prediction.win_probability import backtest
        return backtest(seasons=seasons)
    return {"error": "not implemented"}


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="NBA AI Model Pipeline")
    ap.add_argument("--model",   default="win_probability", choices=SUPPORTED_MODELS)
    ap.add_argument("--seasons", nargs="+", default=["2022-23", "2023-24", "2024-25"])
    ap.add_argument("--retrain", action="store_true")
    ap.add_argument("--eval-all", action="store_true")
    args = ap.parse_args()

    if args.eval_all:
        evaluate_all(seasons=args.seasons)
    else:
        result = run(model_name=args.model, seasons=args.seasons,
                     force_retrain=args.retrain)
        print(json.dumps({k: v for k, v in result.items()
                          if k != "feature_importance"}, indent=2, default=str))
