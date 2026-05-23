"""sweep_winprob_max_depth.py — XGB max_depth sweep for WinProb.

Thin driver on top of `sweep_winprob_common.run_sweep`. Tree depth caps
how deep each booster can split. Production default is 4; sweep probes
{3, 4, 5, 6, 7, 8}. Deeper trees risk overfitting on the 3.7k-row dataset.

Run:
    python scripts/sweep_winprob_max_depth.py
"""
from __future__ import annotations

from sweep_winprob_common import run_sweep


_GRID  = [3, 4, 5, 6, 7, 8]
_PROD  = 4

_FIXED = dict(
    n_estimators=300,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    eval_metric="logloss",
    random_state=42,
    n_jobs=-1,
    early_stopping_rounds=20,
)


if __name__ == "__main__":
    run_sweep(
        knob="max_depth",
        grid=_GRID,
        baseline_value=_PROD,
        fixed_params=_FIXED,
        result_filename="winprob_max_depth_sweep_results.json",
        knob_fmt="{:d}",
    )
