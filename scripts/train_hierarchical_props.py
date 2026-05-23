"""
train_hierarchical_props.py — Fit HierarchicalPropModel for all 7 stats.

Walk-forward holdout: last 20% of games (by date) per player held out for eval.
Persists posterior to data/models/hierarchical_{stat}.pkl.
Prints before/after table vs v2 stacker baseline R² from prop_stacker_metrics.json.

Usage:
    python scripts/train_hierarchical_props.py [--stat blk] [--holdout 0.20]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.hierarchical_props import HierarchicalPropModel

_MODELS_DIR    = os.path.join(PROJECT_DIR, "data", "models")
_RESIDUALS_PATH = os.path.join(_MODELS_DIR, "prop_residuals.json")
_METRICS_OUT   = os.path.join(_MODELS_DIR, "hierarchical_props_metrics.json")
STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]


# ── Data loading ──────────────────────────────────────────────────────────────

def load_residuals(stat: str) -> List[dict]:
    """Load prop_residuals.json filtered to `stat`."""
    with open(_RESIDUALS_PATH) as f:
        data = json.load(f)
    return [r for r in data if r.get("stat") == stat]


def walk_forward_split(
    rows: List[dict],
    holdout_frac: float = 0.20,
) -> Tuple[List[dict], List[dict]]:
    """
    Walk-forward split: for each player, last `holdout_frac` of their games
    (sorted by date) goes to holdout.  No future leakage.
    """
    from collections import defaultdict

    player_rows: dict = defaultdict(list)
    for r in rows:
        player_rows[r["player_id"]].append(r)

    train, test = [], []
    for pid, pr in player_rows.items():
        pr_sorted = sorted(pr, key=lambda x: str(x.get("game_date", "")))
        n = len(pr_sorted)
        split = max(1, int(n * (1 - holdout_frac)))
        train.extend(pr_sorted[:split])
        test.extend(pr_sorted[split:])

    return train, test


# ── Metrics ───────────────────────────────────────────────────────────────────

def compute_metrics(
    model: HierarchicalPropModel,
    test_rows: List[dict],
) -> Dict:
    """Compute MAE, R², and 80% interval coverage on holdout."""
    y_true, y_pred, lo80, hi80 = [], [], [], []

    for r in test_rows:
        pid  = int(r["player_id"])
        true = float(r["actual"])
        out  = model.predict(pid, {})
        y_true.append(true)
        y_pred.append(out["mean"])
        lo80.append(out["lo_80"])
        hi80.append(out["hi_80"])

    y_true = np.array(y_true)
    y_pred = np.array(y_pred)
    lo80   = np.array(lo80)
    hi80   = np.array(hi80)

    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    r2     = float(1 - ss_res / ss_tot) if ss_tot > 0 else 0.0
    mae    = float(np.mean(np.abs(y_true - y_pred)))
    cov80  = float(np.mean((y_true >= lo80) & (y_true <= hi80)))

    return {
        "mae":   round(mae, 4),
        "r2":    round(r2, 4),
        "cov80": round(cov80, 4),
        "n":     len(y_true),
    }


def baseline_r2_from_residuals(rows: List[dict]) -> Tuple[float, float]:
    """Compute R² of the existing model (predicted vs actual) on given rows."""
    y_true = np.array([float(r["actual"]) for r in rows])
    y_pred = np.array([float(r["predicted"]) for r in rows])
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    r2   = float(1 - ss_res / ss_tot) if ss_tot > 0 else 0.0
    mae  = float(np.mean(np.abs(y_true - y_pred)))
    return round(r2, 4), round(mae, 4)


# ── Per-stat training ─────────────────────────────────────────────────────────

def train_stat(stat: str, holdout_frac: float) -> Dict:
    rows = load_residuals(stat)
    if len(rows) < 30:
        print(f"  {stat}: only {len(rows)} rows — skipping")
        return {}

    train_rows, test_rows = walk_forward_split(rows, holdout_frac)

    # Rename fields for model input
    train_df = [{"player_id": r["player_id"], "actual": r["actual"]} for r in train_rows]

    model = HierarchicalPropModel(stat)
    fit_info = model.fit(train_df)

    test_metrics = compute_metrics(model, test_rows)
    base_r2, base_mae = baseline_r2_from_residuals(test_rows)

    model.save()

    return {
        "stat":          stat,
        "n_train":       len(train_rows),
        "n_test":        len(test_rows),
        "n_players":     fit_info["n_players"],
        "league_mean":   fit_info["league_mean"],
        "hier_mae":      test_metrics["mae"],
        "hier_r2":       test_metrics["r2"],
        "hier_cov80":    test_metrics["cov80"],
        "base_mae":      base_mae,
        "base_r2":       base_r2,
        "r2_delta":      round(test_metrics["r2"] - base_r2, 4),
        "mae_delta":     round(test_metrics["mae"] - base_mae, 4),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stat",    type=str, default=None,
                        help="Single stat to train (default: all 7)")
    parser.add_argument("--holdout", type=float, default=0.20,
                        help="Holdout fraction for walk-forward split (default 0.20)")
    args = parser.parse_args()

    stats_to_train = [args.stat] if args.stat else STATS
    all_results: Dict[str, Dict] = {}

    print(f"\n{'':=<72}")
    print(f"  Hierarchical Prop Model Training  (empirical Bayes, no MCMC)")
    print(f"  Holdout: {args.holdout:.0%} walk-forward split")
    print(f"{'':=<72}\n")

    for stat in stats_to_train:
        print(f"  [{stat}] fitting …", end=" ", flush=True)
        result = train_stat(stat, args.holdout)
        if result:
            all_results[stat] = result
            print(
                f"n_players={result['n_players']}  "
                f"hier_r2={result['hier_r2']:+.4f}  "
                f"base_r2={result['base_r2']:+.4f}  "
                f"delta={result['r2_delta']:+.4f}  "
                f"cov80={result['hier_cov80']:.3f}"
            )

    # ── Summary table ─────────────────────────────────────────────────────────
    if all_results:
        print(f"\n{'':=<72}")
        print(f"  {'stat':6s}  {'base_r2':>8s}  {'hier_r2':>8s}  {'delta':>7s}  "
              f"{'base_mae':>9s}  {'hier_mae':>9s}  {'cov80':>7s}")
        print(f"  {'-'*6}  {'-'*8}  {'-'*8}  {'-'*7}  {'-'*9}  {'-'*9}  {'-'*7}")
        for stat in STATS:
            if stat not in all_results:
                continue
            r = all_results[stat]
            sign = "+" if r["r2_delta"] > 0 else ""
            print(
                f"  {stat:6s}  {r['base_r2']:>8.4f}  {r['hier_r2']:>8.4f}  "
                f"{sign}{r['r2_delta']:>6.4f}  "
                f"{r['base_mae']:>9.4f}  {r['hier_mae']:>9.4f}  "
                f"{r['hier_cov80']:>7.3f}"
            )
        print(f"{'':=<72}\n")

    # Persist JSON metrics
    os.makedirs(_MODELS_DIR, exist_ok=True)
    with open(_METRICS_OUT, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"  Metrics saved -> {_METRICS_OUT}")


if __name__ == "__main__":
    main()
