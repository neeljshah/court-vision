"""domains.soccer.chain_engine.shot_model -- EMPIRICAL P(possession produces a
shot | team, time_bucket, score_bucket) with a declared backoff hierarchy,
mirroring mlb.pitch_engine.selection's pitcher-conditioned design:

    (team, time_bucket, score_bucket)  full cell
      -> team-only                            [team's own overall shot rate]
      -> (time_bucket, score_bucket) league cell
      -> league global shot rate

A cell needs >= MIN_CELL possessions to be used; otherwise the next rung backs
off, so every context returns a proper probability. Laplace smoothing kills
held-out zero/one probabilities.

GOAL CONVERSION (declared, no re-fit): given a shot occurs, this module does
NOT re-model shot quality -- it reuses StatsBomb's own published, externally-
validated per-shot xG (statsbomb_xg) directly as the conversion probability,
via an empirical BOOTSTRAP pool of real xG values observed in the same
(time_bucket, score_bucket) cell (match_sim samples an actual historical xG
value, then flips a coin with that value). This isolates this engine's value-
add to the possession-frequency chain, not shot-quality modelling.

COND SEAM (v2): opponent defensive strength is NOT conditioned on in v1 (team-
offense-only, like MLB's selection model conditions on pitcher not batter). A
future `def_tier` argument slot is the natural v2 extension.

INVARIANTS: domains-only; ASCII; numpy/pandas; <=300 LOC.
Tests: python -m pytest domains/soccer/chain_engine/test_shot_model.py -q
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from domains.soccer.chain_engine.corpus import N_SCORE_BUCKETS, N_TIME_BUCKETS

MIN_CELL = 20
ALPHA = 1.0


def _rate(hits: float, n: float, base: float) -> float:
    return (hits + ALPHA * base) / (n + ALPHA)


class ShotModel:
    """Empirical P(shot | team, time_bucket, score_bucket) + a per-(time,score)
    bootstrap pool of real observed shot xG values for goal conversion."""

    def __init__(self, full: Dict[Tuple, float], team_only: Dict[str, float],
                 league_cell: np.ndarray, glob: float,
                 xg_pool: Dict[Tuple[int, int], np.ndarray], xg_pool_global: np.ndarray):
        self._full = full
        self._team_only = team_only
        self._league = league_cell   # [N_TIME_BUCKETS, N_SCORE_BUCKETS]
        self._glob = glob
        self._xg_pool = xg_pool
        self._xg_pool_global = xg_pool_global

    @classmethod
    def fit(cls, df: pd.DataFrame) -> "ShotModel":
        """df: team, time_bucket, score_bucket, had_shot, xg, goal (possession rows)."""
        hit = df["had_shot"].to_numpy(dtype=float)
        glob = float(hit.mean()) if len(hit) else 0.1

        league = np.full((N_TIME_BUCKETS, N_SCORE_BUCKETS), glob)
        for (tb, sb), g in df.groupby(["time_bucket", "score_bucket"]):
            if len(g) >= MIN_CELL:
                league[tb, sb] = _rate(g["had_shot"].sum(), len(g), glob)

        team_only: Dict[str, float] = {}
        for team, g in df.groupby("team"):
            team_only[team] = _rate(g["had_shot"].sum(), len(g), glob)

        full: Dict[Tuple, float] = {}
        for (team, tb, sb), g in df.groupby(["team", "time_bucket", "score_bucket"]):
            if len(g) >= MIN_CELL:
                full[(team, tb, sb)] = _rate(g["had_shot"].sum(), len(g),
                                             team_only.get(team, glob))

        shots = df[df["had_shot"].astype(bool)]
        xg_pool: Dict[Tuple[int, int], np.ndarray] = {}
        for (tb, sb), g in shots.groupby(["time_bucket", "score_bucket"]):
            xg_pool[(int(tb), int(sb))] = g["xg"].dropna().to_numpy()
        xg_pool_global = shots["xg"].dropna().to_numpy()
        if len(xg_pool_global) == 0:
            xg_pool_global = np.array([0.1])
        return cls(full, team_only, league, glob, xg_pool, xg_pool_global)

    def shot_prob(self, team: str, time_bucket: int, score_bucket: int) -> float:
        v = self._full.get((team, time_bucket, score_bucket))
        if v is not None:
            return v
        v = self._team_only.get(team)
        if v is not None:
            return v
        return float(self._league[time_bucket, score_bucket])

    def sample_xg(self, time_bucket: int, score_bucket: int,
                  rng: np.random.Generator) -> float:
        pool = self._xg_pool.get((int(time_bucket), int(score_bucket)))
        if pool is None or len(pool) == 0:
            pool = self._xg_pool_global
        return float(rng.choice(pool))

    def summary(self) -> dict:
        return {"n_full_cells": len(self._full), "n_teams": len(self._team_only),
                "min_cell": MIN_CELL, "global_shot_rate": round(self._glob, 4),
                "n_xg_pool_cells": len(self._xg_pool)}


def naive_baseline(df: pd.DataFrame) -> Dict[str, float]:
    """Per-team CONSTANT shot rate, no time/score conditioning (the classic
    Poisson-attack-rate assumption)."""
    hit = df["had_shot"].to_numpy(dtype=float)
    glob = float(hit.mean()) if len(hit) else 0.1
    out: Dict[str, float] = {"__global__": glob}
    for team, g in df.groupby("team"):
        out[team] = _rate(g["had_shot"].sum(), len(g), glob)
    return out


__all__ = ["ShotModel", "naive_baseline", "MIN_CELL", "ALPHA"]
