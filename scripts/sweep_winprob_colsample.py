"""sweep_winprob_colsample.py — XGB colsample_bytree sweep for WinProb.

Thin driver on top of `sweep_winprob_common.run_sweep`. Varies the
fraction of features each tree samples. Production default is 0.8;
sweep probes {0.5, 0.6, 0.7, 0.8, 0.9, 1.0}. With 67 effective features
in the cache, dropping below 0.5 starves the model.

Run:
    python scripts/sweep_winprob_colsample.py
"""
from __future__ import annotations

from sweep_winprob_common import run_sweep


_GRID  = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
_PROD  = 0.8

_FIXED = dict(
    n_estimators=300,
    learning_rate=0.05,
    max_depth=4,
    subsample=0.8,
    eval_metric="logloss",
    random_state=42,
    n_jobs=-1,
    early_stopping_rounds=20,
)


if __name__ == "__main__":
    run_sweep(
        knob="colsample_bytree",
        grid=_GRID,
        baseline_value=_PROD,
        fixed_params=_FIXED,
        result_filename="winprob_colsample_sweep_results.json",
        knob_fmt="{:.2f}",
    )
