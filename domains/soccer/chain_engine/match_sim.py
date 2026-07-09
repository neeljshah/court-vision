"""domains.soccer.chain_engine.match_sim -- MC chain from the POSSESSION atomic
unit to MATCH: for each (time_bucket, home/away) slot, draw a Poisson possession
COUNT from the empirical per-slot rate; for each possession draw a shot via
ShotModel.shot_prob(team, time_bucket, score_bucket) (state re-evaluated every
possession since the score can move mid-bucket); if a shot occurs, sample a
REAL historical xG value for that state (ShotModel.sample_xg) and convert to a
goal with that probability. Score accumulates across all 6 time buckets.

POSSESSION-RATE MODEL (declared, simple by design): a per-(time_bucket,
is_home) empirical average possession-count -- no team-specific pace model in
v1 (mirrors the shot model's own scope decision: team identity enters at the
SHOT stage, not the possession-count stage). The v2 seam is a team-specific
pace multiplier analogous to sim2's pace_model.py.

INVARIANTS: domains-only; ASCII; numpy/pandas; <=300 LOC.
Tests: python -m pytest domains/soccer/chain_engine/test_match_sim.py -q
"""
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd

from domains.soccer.chain_engine.corpus import N_TIME_BUCKETS, score_bucket
from domains.soccer.chain_engine.shot_model import ShotModel


class PossessionRate:
    """Empirical mean possession-count per (time_bucket, is_home) slot."""

    def __init__(self, rate: np.ndarray):
        self._rate = rate   # [N_TIME_BUCKETS, 2] (0=away, 1=home)

    @classmethod
    def fit(cls, df: pd.DataFrame) -> "PossessionRate":
        counts = (df.groupby(["match_id", "team", "is_home", "time_bucket"])
                  .size().reset_index(name="n"))
        rate = np.full((N_TIME_BUCKETS, 2), counts["n"].mean() if len(counts) else 20.0)
        for (tb, ih), g in counts.groupby(["time_bucket", "is_home"]):
            rate[int(tb), int(bool(ih))] = float(g["n"].mean())
        return cls(rate)

    def mean(self, time_bucket: int, is_home: bool) -> float:
        return float(self._rate[int(time_bucket), int(bool(is_home))])


def simulate_match(home_team: str, away_team: str, shot_model: ShotModel,
                    poss_rate: PossessionRate, rng: np.random.Generator) -> Tuple[int, int]:
    """One MC replicate -> (home_goals, away_goals)."""
    hg = ag = 0
    for tb in range(N_TIME_BUCKETS):
        for team, is_home in ((home_team, True), (away_team, False)):
            lam = poss_rate.mean(tb, is_home)
            n_poss = rng.poisson(lam) if lam > 0 else 0
            for _ in range(n_poss):
                diff = (hg - ag) if is_home else (ag - hg)
                sb = score_bucket(diff)
                if rng.random() < shot_model.shot_prob(team, tb, sb):
                    xg = shot_model.sample_xg(tb, sb, rng)
                    if rng.random() < xg:
                        if is_home:
                            hg += 1
                        else:
                            ag += 1
    return hg, ag


def simulate_match_ensemble(home_team: str, away_team: str, shot_model: ShotModel,
                            poss_rate: PossessionRate, n: int,
                            seed: int) -> Tuple[np.ndarray, np.ndarray]:
    """n MC replicates -> (home_goals array, away_goals array)."""
    rng = np.random.default_rng(seed)
    hg = np.empty(n, dtype=int); ag = np.empty(n, dtype=int)
    for i in range(n):
        hg[i], ag[i] = simulate_match(home_team, away_team, shot_model, poss_rate, rng)
    return hg, ag


__all__ = ["PossessionRate", "simulate_match", "simulate_match_ensemble"]
