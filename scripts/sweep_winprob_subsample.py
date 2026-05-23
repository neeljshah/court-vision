"""sweep_winprob_subsample.py — XGB row-subsample sweep for WinProb.

Thin driver on top of `sweep_winprob_common.run_sweep`. With 3.7k training
rows the model can plausibly tolerate more or less bagging than the
production default of 0.8 — this sweep measures whether the gain exceeds
the ship gate.

Run:
    python scripts/sweep_winprob_subsample.py
"""
from __future__ import annotations

from sweep_winprob_common import run_sweep


# Grid centred on the production default (0.8).
_GRID  = [0.6, 0.7, 0.8, 0.9, 1.0]
_PROD  = 0.8

_FIXED = dict(
    n_estimators=300,
    learning_rate=0.05,
    max_depth=4,
    colsample_bytree=0.8,
    eval_metric="logloss",
    random_state=42,
    n_jobs=-1,
    early_stopping_rounds=20,
)


if __name__ == "__main__":
    run_sweep(
        knob="subsample",
        grid=_GRID,
        baseline_value=_PROD,
        fixed_params=_FIXED,
        result_filename="winprob_subsample_sweep_results.json",
        knob_fmt="{:.2f}",
    )
