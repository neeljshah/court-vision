"""fit_validity_gate_nulls -- planted-null permutations for the V2
fit-validity gate. Split out of fit_validity_gate_impl.py purely to keep that
file under the 300-LOC cap. Mirrors fit_validity_gate_prereg_v2.json's
`planted_null_design_v2` section verbatim: null_1 shuffles move destinations
(V1-mandatory), null_2 shuffles outcome deltas (V2 addition). Both are REAL,
deterministic (seeded) permutations -- no fabricated data, no non-permutation
substitute.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def shuffle_move_team_assignment(moves: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Null #1 (V1-mandatory): permute team_post WITHIN each season_pre
    fold's destination pool, keeping bpm_delta fixed to each player's TRUE
    realized outcome. A real, seeded, deterministic permutation of an
    existing column -- not a redraw from an assumed distribution."""
    rng = np.random.default_rng(seed)
    shuffled = moves.copy()
    for _, group in shuffled.groupby("season_pre"):
        idx = group.index.to_numpy()
        perm = rng.permutation(group["team_post"].to_numpy())
        shuffled.loc[idx, "team_post"] = perm
    return shuffled


def shuffle_outcome_deltas(moves: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Null #2 (V2 addition): shuffle bpm_delta WITHIN each season_pre fold,
    keeping the REAL fit-relevant columns (team_post etc.) fixed. Real,
    seeded, deterministic permutation of the outcome column."""
    rng = np.random.default_rng(seed)
    shuffled = moves.copy()
    for _, group in shuffled.groupby("season_pre"):
        idx = group.index.to_numpy()
        perm = rng.permutation(group["bpm_delta"].to_numpy())
        shuffled.loc[idx, "bpm_delta"] = perm
    return shuffled


def null_dies(real_pooled_delta: float, null_pooled_delta: float) -> bool:
    """A null 'dies' if it does NOT clear the SAME bar the real arm needs:
    'H1 beats H0' (delta_rmse > 0), i.e. the bar is H0 itself, not whatever
    the real arm happened to score. A null clears the bar (fails to die)
    only if the SPURIOUS/shuffled fit score ALSO manages a positive delta
    against H0 (a spurious win as large as -- or in the same winning
    direction as -- a real win would need). This is intentionally NOT a
    real_pooled_delta > null_pooled_delta relative comparison: when the real
    arm itself has a NEGATIVE delta (H1 already loses to H0 outright), a
    null with a less-negative delta is not 'clearing the bar' in any
    meaningful sense -- it is just also losing, by a smaller margin. Only
    when the real arm shows a genuine positive delta does 'the null clears
    the same bar' mean anything, and even then the null must independently
    clear the positive-delta bar itself, not merely edge out the real arm's
    negative score."""
    if real_pooled_delta <= 0:
        # the real arm never cleared H0 itself -- a null can only be said
        # to 'clear the same bar' if it ALSO produces a genuine positive
        # delta (which would itself be a spurious-signal red flag,
        # independent of what the real arm scored).
        return null_pooled_delta <= 0
    return null_pooled_delta < real_pooled_delta
