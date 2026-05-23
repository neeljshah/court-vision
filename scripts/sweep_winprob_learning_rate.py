"""sweep_winprob_learning_rate.py — XGB learning-rate sweep for WinProb.

Thin driver on top of `sweep_winprob_common.run_sweep`. The shared module
handles dataset construction, training, ship-gate evaluation, and results
JSON. This file just declares the swept knob, the grid, the production
default, and the fixed XGB params.

Run:
    python scripts/sweep_winprob_learning_rate.py
"""
from __future__ import annotations

from sweep_winprob_common import run_sweep


# Grid centred on the production default (0.05). 0.025/0.035 probe slower
# fits where early-stopping may exploit more trees, 0.07/0.10 a faster one.
_GRID  = [0.025, 0.035, 0.05, 0.07, 0.10]
_PROD  = 0.05

# Mirrors win_probability.train() with `learning_rate` removed so the
# sweep can vary it.
_FIXED = dict(
    n_estimators=300,
    max_depth=4,
    subsample=0.8,
    colsample_bytree=0.8,
    eval_metric="logloss",
    random_state=42,
    n_jobs=-1,
    early_stopping_rounds=20,
)


if __name__ == "__main__":
    run_sweep(
        knob="learning_rate",
        grid=_GRID,
        baseline_value=_PROD,
        fixed_params=_FIXED,
        result_filename="winprob_lr_sweep_results.json",
        knob_fmt="{:.3f}",
    )
