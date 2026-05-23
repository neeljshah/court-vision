"""sweep_winprob_combined.py — roll-up of all A1 per-knob winners.

Compares the production-default XGB config against several combined-winner
configurations to see whether the per-knob gains compound or interfere.

Per-knob winners (from sweep_winprob_<knob>_sweep_results.json, all clear
the ship gate individually):
    learning_rate    0.05 -> 0.035
    subsample        0.80 -> 0.70   (ships on Brier; acc -0.27pp)
    colsample_bytree 0.80 -> 0.50
    gamma            0.0  -> 0.40
    reg_alpha        0.0  -> 2.0    (ships on Brier; acc +0.41pp)
    reg_lambda       1.0  -> 4.0    (ships on Brier; acc +0.27pp)
    max_depth        4    -> 3      (ships on Brier; acc -0.14pp)

Three combined configs are tested:
    combined_full   — every winner applied
    combined_lean   — only winners that improved BOTH metrics (lr, gamma)
                      plus colsample (large gains on both)
    combined_l2     — full minus reg_alpha (the L1+L2 combination can
                      over-shrink with sparse weights)

Ship gate (workday-loop spec): any non-baseline config must beat baseline
by Brier > 0.001 OR accuracy >= 0.5pp.

Run:
    python scripts/sweep_winprob_combined.py
"""
from __future__ import annotations

from sweep_winprob_common import compare_configs


# Shared XGB plumbing — these never change.
_PLUMBING = dict(
    eval_metric="logloss",
    random_state=42,
    n_jobs=-1,
    early_stopping_rounds=20,
)


def _cfg(**overrides):
    """Build a complete XGB params dict starting from prod defaults."""
    base = dict(
        n_estimators=300,
        learning_rate=0.05,
        max_depth=4,
        subsample=0.8,
        colsample_bytree=0.8,
        **_PLUMBING,
    )
    base.update(overrides)
    return base


CONFIGS = {
    "baseline_prod": _cfg(),
    "combined_full": _cfg(
        learning_rate=0.035,
        max_depth=3,
        subsample=0.70,
        colsample_bytree=0.50,
        gamma=0.40,
        reg_alpha=2.0,
        reg_lambda=4.0,
    ),
    "combined_lean": _cfg(
        learning_rate=0.035,
        colsample_bytree=0.50,
        gamma=0.40,
    ),
    "combined_l2_only": _cfg(
        learning_rate=0.035,
        max_depth=3,
        subsample=0.70,
        colsample_bytree=0.50,
        gamma=0.40,
        reg_lambda=4.0,
    ),
}


if __name__ == "__main__":
    compare_configs(
        configs=CONFIGS,
        baseline_name="baseline_prod",
        result_filename="winprob_combined_sweep_results.json",
    )
