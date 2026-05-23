"""sweep_winprob_gamma.py — XGB gamma sweep for WinProb.

Thin driver on top of `sweep_winprob_common.run_sweep`. `gamma` is the
minimum loss reduction required to split a leaf; higher values produce a
more conservative tree. Production default is 0 (XGB default — no extra
prune pressure). Sweep probes {0, 0.1, 0.2, 0.4, 0.8}.

Run:
    python scripts/sweep_winprob_gamma.py
"""
from __future__ import annotations

from sweep_winprob_common import run_sweep


_GRID  = [0.0, 0.1, 0.2, 0.4, 0.8]
_PROD  = 0.0

_FIXED = dict(
    n_estimators=300,
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
        knob="gamma",
        grid=_GRID,
        baseline_value=_PROD,
        fixed_params=_FIXED,
        result_filename="winprob_gamma_sweep_results.json",
        knob_fmt="{:.2f}",
    )
