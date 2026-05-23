"""
retrain_win_prob.py — Retrain win probability model with v2 ELO + injury features.

Usage:
    conda activate basketball_ai
    python scripts/retrain_win_prob.py

Produces:
    data/models/win_prob.pkl          — new model
    data/models/win_prob_metrics.json — accuracy + brier + walk-forward slices
    data/models/elo_state.json        — current ELO ratings for all teams
"""

from __future__ import annotations

import json
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_METRICS_PATH = os.path.join(PROJECT_DIR, "data", "models", "win_prob_metrics.json")

SEASONS = ["2022-23", "2023-24", "2024-25"]


def _load_baseline() -> dict:
    if os.path.exists(_METRICS_PATH):
        try:
            return json.load(open(_METRICS_PATH))
        except Exception:
            pass
    return {}


def main():
    baseline = _load_baseline()
    baseline_acc   = baseline.get("accuracy", None)
    baseline_brier = baseline.get("brier", None)

    print("=" * 60)
    print("Win Probability Model Retrain — v2 (ELO + Injury)")
    print("=" * 60)
    if baseline_acc is not None:
        print(f"BASELINE: acc={baseline_acc:.4f}  brier={baseline_brier:.4f}  "
              f"version={baseline.get('version', 'v1')}")
    print()

    from src.prediction.win_probability import train
    model = train(seasons=SEASONS)

    # Load new metrics
    new_metrics = json.load(open(_METRICS_PATH))
    new_acc   = new_metrics["accuracy"]
    new_brier = new_metrics["brier"]

    print()
    print("=" * 60)
    print("BEFORE / AFTER COMPARISON")
    print("=" * 60)
    print(f"{'Metric':<12} {'Before':>10} {'After':>10} {'Delta':>10}")
    print("-" * 44)

    if baseline_acc is not None:
        delta_acc   = new_acc   - baseline_acc
        delta_brier = new_brier - baseline_brier
        print(f"{'Accuracy':<12} {baseline_acc:>10.4f} {new_acc:>10.4f} {delta_acc:>+10.4f}")
        print(f"{'Brier':<12} {baseline_brier:>10.4f} {new_brier:>10.4f} {delta_brier:>+10.4f}")
    else:
        print(f"{'Accuracy':<12} {'N/A':>10} {new_acc:>10.4f} {'N/A':>10}")
        print(f"{'Brier':<12} {'N/A':>10} {new_brier:>10.4f} {'N/A':>10}")

    print()
    print("Walk-forward slices:")
    for name, vals in new_metrics.get("slices", {}).items():
        print(f"  {name:8s}: acc={vals['acc']:.4f}  brier={vals['brier']:.4f}  n={vals['n']}")

    print()
    print(f"Model saved: data/models/win_prob.pkl")
    print(f"Metrics:     data/models/win_prob_metrics.json")
    print(f"Features:    {len(new_metrics.get('features', []))} columns (version={new_metrics.get('version')})")


if __name__ == "__main__":
    main()
