"""domains.basketball_nba.sim2.pace_model -- EMPIRICAL possession-duration model
for the NBA simulator v2.

Possession duration (seconds, 1..DMAX) is drawn from the empirical distribution
conditioned on (time_b, margin_b) -- the SAME two evolving state dims the point
model uses. This is deliberate and sufficient:

  * Late-game trailing teams play FAST and leading teams get FOULED. Both regimes
    live in the Q4<=3min time bucket crossed with the offense-relative margin
    bucket: a LEADING offense there shows short, foul-truncated possessions; a
    TRAILING offense shows short, hurried ones. The intentional-foul regime is
    therefore captured EMPIRICALLY by the (Q4-late x margin) cells, not by a
    hand-coded foul rule. Stated here rather than special-cased in code.
  * End-of-period effects fall out because the last possession of a period is
    truncated to the remaining clock by the simulator, and the empirical durations
    already reflect shorter end-of-period trips.

42 (time_b x margin_b) cells, each well populated, so no strength-tercile backoff
is needed; a cell with < MIN_DUR observations backs off to the global duration
distribution. `dur_cdf_matrix()` returns the [42, DMAX] inclusive-CDF the simulator
indexes; sampled duration = 1 + count(u >= cdf).

LEAK-FREE: durations are a fit-season empirical table; the held-out season never
touches it.

INVARIANTS: domains-only; <=300 LOC; ASCII; numpy/pandas; no src/kernel imports.
Tests: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/sim2/test_pace_model.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd

from domains.basketball_nba.sim2.possession_model import N_TIME, N_MARGIN

DMAX = 40                 # max possession seconds (clip); durations live in 1..40
MIN_DUR = 30              # per-(time,margin) cell backoff threshold
N_DCELLS = N_TIME * N_MARGIN


class PaceModel:
    """Empirical P(duration | time_b, margin_b), global backoff for thin cells."""

    def __init__(self, cdf: np.ndarray, n_full: int):
        self.cdf = cdf           # [42, DMAX] inclusive CDF over seconds 1..DMAX
        self.n_full = n_full

    @staticmethod
    def _cdf_from(dur: np.ndarray) -> np.ndarray:
        d = np.clip(np.round(dur).astype(int), 1, DMAX)
        c = np.bincount(d, minlength=DMAX + 1).astype(float)[1:]  # index 1..DMAX
        s = c.sum()
        pmf = c / s if s > 0 else np.ones(DMAX) / DMAX
        cdf = np.cumsum(pmf)
        cdf[-1] = 1.0
        return cdf

    @classmethod
    def fit(cls, df: pd.DataFrame) -> "PaceModel":
        dur = df["duration"].to_numpy()
        glob = cls._cdf_from(dur)
        cdf = np.tile(glob, (N_DCELLS, 1))
        tm = (df["time_b"].to_numpy() * N_MARGIN + df["margin_b"].to_numpy())
        n_full = 0
        for k in range(N_DCELLS):
            m = tm == k
            if m.sum() >= MIN_DUR:
                cdf[k] = cls._cdf_from(dur[m]); n_full += 1
        return cls(cdf, n_full)

    def dur_cdf_matrix(self) -> np.ndarray:
        return self.cdf

    def mean_duration(self) -> float:
        vals = np.arange(1, DMAX + 1)
        pmf = np.diff(np.hstack([[0.0], self.cdf.mean(axis=0)]))
        return float((vals * pmf).sum())

    def summary(self) -> Dict[str, Any]:
        return {"n_dcells": N_DCELLS, "n_full": self.n_full, "min_dur": MIN_DUR,
                "dmax": DMAX, "mean_duration_s": round(self.mean_duration(), 3)}

    def save(self, path: Path) -> None:
        np.savez_compressed(path, cdf=self.cdf, n_full=np.array([self.n_full]))


__all__ = ["DMAX", "N_DCELLS", "PaceModel"]
