"""sweep_winprob_n_estimators.py — XGB n_estimators sweep for WinProb.

Thin driver on top of `sweep_winprob_common.run_sweep`. Number of boosting
rounds. Early stopping (20 rounds, fixed) makes the cap somewhat soft;
this sweep ensures the cap isn't hit before convergence. Production
default is 300; sweep probes {200, 300, 500, 800, 1200}.

Run:
    python scripts/sweep_winprob_n_estimators.py
"""
from __future__ import annotations

from sweep_winprob_common import run_sweep


_GRID  = [200, 300, 500, 800, 1200]
_PROD  = 300

_FIXED = dict(
    learning_rate=0.05,
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
        knob="n_estimators",
        grid=_GRID,
        baseline_value=_PROD,
        fixed_params=_FIXED,
        result_filename="winprob_n_estimators_sweep_results.json",
        knob_fmt="{:d}",
    )
