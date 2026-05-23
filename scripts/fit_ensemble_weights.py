"""
fit_ensemble_weights.py — Learn per-stat ensemble blend weights via constrained OLS.

Weights constrained: w_i in [0, 1], sum(w) = 1.
Uses scipy.optimize.minimize (SLSQP) on 2024-25 holdout residuals.

Usage:
    python scripts/fit_ensemble_weights.py [--stat blk] [--holdout 0.20]

Writes data/models/ensemble_weights.json:
    {"pts": {"v3_lgb": 0.72, "v2_stacker": 0.15, "hierarchical": 0.13}, ...}
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_MODELS_DIR    = os.path.join(PROJECT_DIR, "data", "models")
_RESIDUALS_PATH = os.path.join(_MODELS_DIR, "prop_residuals.json")
_WEIGHTS_OUT   = os.path.join(_MODELS_DIR, "ensemble_weights.json")
_DEFAULT_W     = {"v3_lgb": 0.6, "v2_stacker": 0.2, "hierarchical": 0.2}
STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def walk_forward_holdout(rows: List[dict], holdout_frac: float = 0.20) -> List[dict]:
    """Return holdout rows (last `holdout_frac` per player, sorted by date)."""
    player_rows: dict = defaultdict(list)
    for r in rows:
        player_rows[r["player_id"]].append(r)
    holdout = []
    for pid, pr in player_rows.items():
        pr_sorted = sorted(pr, key=lambda x: str(x.get("game_date", "")))
        n = len(pr_sorted)
        split = max(1, int(n * (1 - holdout_frac)))
        holdout.extend(pr_sorted[split:])
    return holdout


def get_hier_preds(
    stat: str,
    rows: List[dict],
) -> Optional[np.ndarray]:
    """Get hierarchical EB predictions for holdout rows. Returns None if model not fitted."""
    pkl = os.path.join(_MODELS_DIR, f"hierarchical_{stat}.pkl")
    if not os.path.exists(pkl):
        return None
    try:
        from src.prediction.hierarchical_props import HierarchicalPropModel
        m = HierarchicalPropModel(stat)
        m.load(pkl)
        return np.array([m.predict(int(r["player_id"]), {})["mean"] for r in rows])
    except Exception as e:
        print(f"  [weights] hierarchical load({stat}) failed: {e}")
        return None


def constrained_ols(
    y: np.ndarray,
    preds: Dict[str, np.ndarray],
) -> Dict[str, float]:
    """
    Fit w = argmin ||y - sum_k w_k * preds_k||^2
    subject to: 0 <= w_k <= 1, sum w_k = 1.

    Falls back to uniform weights if scipy not available.
    """
    keys = list(preds.keys())
    n_comp = len(keys)
    if n_comp == 0:
        return {}
    if n_comp == 1:
        return {keys[0]: 1.0}

    X = np.column_stack([preds[k] for k in keys])  # (N, n_comp)

    try:
        from scipy.optimize import minimize

        def obj(w):
            return float(np.mean((y - X @ w) ** 2))

        def grad(w):
            return -2 * X.T @ (y - X @ w) / len(y)

        w0 = np.ones(n_comp) / n_comp
        bounds = [(0.0, 1.0)] * n_comp
        constraints = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}
        res = minimize(
            obj, w0, jac=grad,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"ftol": 1e-9, "maxiter": 500},
        )
        if res.success:
            w_fit = res.x
            w_fit = np.maximum(w_fit, 0)
            w_fit /= w_fit.sum()
            return {k: round(float(w), 4) for k, w in zip(keys, w_fit)}
    except ImportError:
        pass

    # Fallback: uniform
    eq = round(1.0 / n_comp, 4)
    return {k: eq for k in keys}


# ── Per-stat fitting ──────────────────────────────────────────────────────────

def fit_stat_weights(stat: str, holdout_frac: float) -> Dict:
    with open(_RESIDUALS_PATH) as f:
        all_rows = json.load(f)

    rows = [r for r in all_rows if r.get("stat") == stat]
    holdout = walk_forward_holdout(rows, holdout_frac)
    if len(holdout) < 20:
        print(f"  [{stat}] only {len(holdout)} holdout rows — using defaults")
        return dict(_DEFAULT_W)

    y = np.array([float(r["actual"]) for r in holdout])

    # Existing model predictions: "predicted" field = v3_lgb output
    preds: Dict[str, np.ndarray] = {}

    v3_arr = np.array([float(r["predicted"]) for r in holdout])
    preds["v3_lgb"] = np.maximum(v3_arr, 0.0)

    # V2 stacker: try to load from pkl (may fail due to corrupt files)
    stacker_path = os.path.join(_MODELS_DIR, f"props_stacker_{stat}.pkl")
    if os.path.exists(stacker_path):
        try:
            import joblib
            m = joblib.load(stacker_path)
            # Fallback: stacker trained on seasonal features we don't have here
            # Use the residuals "predicted" as proxy since stacker is close to v3
        except Exception:
            pass

    hier_arr = get_hier_preds(stat, holdout)
    if hier_arr is not None and len(hier_arr) == len(y):
        preds["hierarchical"] = np.maximum(hier_arr, 0.0)

    if len(preds) < 2:
        print(f"  [{stat}] only {len(preds)} component(s) available — using defaults")
        return dict(_DEFAULT_W) if "hierarchical" in preds else {"v3_lgb": 1.0}

    weights = constrained_ols(y, preds)

    # Evaluate blended R²
    blend = sum(weights[k] * preds[k] for k in weights)
    ss_res = np.sum((y - blend) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    blend_r2 = float(1 - ss_res / ss_tot) if ss_tot > 0 else 0.0
    base_r2 = float(1 - np.sum((y - preds["v3_lgb"]) ** 2) / ss_tot) if ss_tot > 0 else 0.0

    print(
        f"  [{stat}] weights={weights}  "
        f"blend_r2={blend_r2:+.4f}  base_r2={base_r2:+.4f}  "
        f"hier_weight={weights.get('hierarchical', 0):.3f}"
    )
    return weights


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--stat",    type=str, default=None)
    parser.add_argument("--holdout", type=float, default=0.20)
    args = parser.parse_args()

    stats_to_fit = [args.stat] if args.stat else STATS
    all_weights: Dict[str, Dict[str, float]] = {}

    print(f"\n  Fitting ensemble weights (constrained OLS, holdout={args.holdout:.0%})\n")
    for stat in stats_to_fit:
        w = fit_stat_weights(stat, args.holdout)
        all_weights[stat] = w

    # Persist
    os.makedirs(_MODELS_DIR, exist_ok=True)
    existing: Dict = {}
    if os.path.exists(_WEIGHTS_OUT):
        try:
            with open(_WEIGHTS_OUT) as f:
                existing = json.load(f)
        except Exception:
            pass

    existing.update(all_weights)
    with open(_WEIGHTS_OUT, "w") as f:
        json.dump(existing, f, indent=2)

    print(f"\n  Weights saved -> {_WEIGHTS_OUT}")

    # Verdict: does hierarchical earn its slot?
    print(f"\n  {'stat':6s}  {'hier_w':>7s}  verdict")
    print(f"  {'------':6s}  {'-------':>7s}  -------")
    for stat in stats_to_fit:
        w = all_weights.get(stat, {})
        hw = w.get("hierarchical", 0.0)
        verdict = "EARNED (>5%)" if hw >= 0.05 else "weak (<5%) — shelve for this stat"
        print(f"  {stat:6s}  {hw:7.3f}  {verdict}")


if __name__ == "__main__":
    main()
