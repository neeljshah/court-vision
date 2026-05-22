"""
prune_prop_features.py — Feature-importance audit for the prop models (PRED-11).

The prop models carry 100+ features; many are likely noise. This script runs
the model_explainer importance analysis on every trained prop model and
reports which features are low-importance — candidates to prune at the next
retrain, which reduces overfitting and training cost.

It is read-only: it loads models and writes a report; it never edits the
feature list or the models. Pruning is applied deliberately at retrain time.

Usage:
    python scripts/prune_prop_features.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from typing import Callable, Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_OUTPUT_DIR = os.path.join(PROJECT_DIR, "data", "output")
_REPORT_PATH = os.path.join(_OUTPUT_DIR, "prop_feature_importance.json")


def cross_stat_prune_list(per_stat: Dict[str, dict]) -> List[str]:
    """Features flagged as low-importance for EVERY trained stat.

    A feature that no prop model relies on is the safest to drop — pruning it
    cannot hurt any single stat's accuracy.

    Args:
        per_stat: {stat: explain_model report dict with 'prune_candidates'}.

    Returns:
        Sorted list of features that are prune candidates across all stats.
    """
    trained = [r for r in per_stat.values() if r.get("prune_candidates") is not None]
    if not trained:
        return []
    common = set(trained[0]["prune_candidates"])
    for report in trained[1:]:
        common &= set(report["prune_candidates"])
    return sorted(common)


def analyse_prop_features(
    model_dir: Optional[str] = None,
    output_path: Optional[str] = None,
    explain_fn: Optional[Callable] = None,
) -> dict:
    """Audit feature importance across every trained prop model.

    Args:
        model_dir:  Directory holding props_{stat}.json (default data/models).
        output_path: Destination report JSON.
        explain_fn: Injectable importance function (signature matching
                    model_explainer.explain_model); defaults to the real one.

    Returns:
        {"per_stat": {...}, "cross_stat_prune": [...], "n_trained": int}.
    """
    import numpy as np

    from src.prediction.player_props import _ALL_FEATS, _PROP_STATS

    model_dir = model_dir or os.path.join(PROJECT_DIR, "data", "models")
    output_path = output_path or _REPORT_PATH
    if explain_fn is None:
        from src.prediction.model_explainer import explain_model as explain_fn

    per_stat: Dict[str, dict] = {}
    for stat in _PROP_STATS:
        feature_names = [c for c in _ALL_FEATS if c != f"season_{stat}"]
        model_path = os.path.join(model_dir, f"props_{stat}.json")
        if not os.path.exists(model_path):
            per_stat[stat] = {"status": "not_trained", "prune_candidates": None}
            continue
        try:
            import xgboost as xgb
            model = xgb.XGBRegressor()
            model.load_model(model_path)
            # Tree importance ignores X values — a zero matrix of the right
            # width satisfies explain_model's shape contract.
            X = np.zeros((2, len(feature_names)))
            report = explain_fn(model, X, feature_names, f"props_{stat}")
            n_low = len(report.get("prune_candidates", []))
            per_stat[stat] = {
                "status": "analysed",
                "method": report.get("method"),
                "n_features": len(feature_names),
                "n_low_importance": n_low,
                "prune_candidates": report.get("prune_candidates", []),
            }
        except Exception as exc:  # noqa: BLE001
            per_stat[stat] = {"status": f"error: {exc}", "prune_candidates": None}

    cross = cross_stat_prune_list(per_stat)
    n_trained = sum(1 for r in per_stat.values() if r.get("prune_candidates") is not None)
    result = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "n_trained_models": n_trained,
        "cross_stat_prune": cross,
        "per_stat": per_stat,
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return result


def main() -> int:
    result = analyse_prop_features()
    print("\n" + "=" * 64)
    print("Prop Feature-Importance Audit")
    print("=" * 64)
    if result["n_trained_models"] == 0:
        print("  No trained prop models found — train props first.")
        return 0
    for stat, r in result["per_stat"].items():
        if r.get("prune_candidates") is None:
            print(f"  {stat:6s}: {r['status']}")
        else:
            print(f"  {stat:6s}: {r['n_low_importance']}/{r['n_features']} "
                  f"low-importance features  (method={r.get('method')})")
    print("-" * 64)
    cross = result["cross_stat_prune"]
    print(f"  {len(cross)} feature(s) low-importance across ALL trained models "
          f"— safe to prune at next retrain")
    if cross:
        print(f"  prune candidates: {', '.join(cross[:15])}"
              + (" ..." if len(cross) > 15 else ""))
    print(f"\n[prune_prop_features] report -> {_REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
