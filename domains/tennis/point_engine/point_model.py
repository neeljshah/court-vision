"""domains.tennis.point_engine.point_model -- EMPIRICAL P(server_wins_point |
server, score_bucket, set_bucket) with a declared backoff hierarchy, mirroring
mlb.pitch_engine.selection's design:

    (server, score_bucket, set_bucket)  full cell
      -> (server, score_bucket)                 [server's own score-state mix]
      -> (score_bucket, set_bucket) league cell
      -> league global server-win rate

A cell is used only when it holds >= MIN_CELL points; otherwise the next rung is
taken, so every context returns a proper probability. Laplace smoothing kills
held-out zero/one probabilities.

NAIVE BASELINE (declared, classic-tennis-model style): a per-server CONSTANT
point-win rate (their own overall serve-win rate, no score-state conditioning at
all -- the textbook i.i.d.-points assumption). This isolates exactly what
score-state conditioning adds, mirroring MLB panel A (context vs no-context).

COND SEAM (v2): returner identity/return-strength is NOT conditioned on in v1
(server-only, like MLB's selection model conditions on pitcher not batter). A
`returner_tier` argument slot is left for attribute conditioning to plug into a
future v2 without a signature break.

INVARIANTS: domains-only; ASCII; numpy/pandas; <=300 LOC.
Tests: python -m pytest domains/tennis/point_engine/test_point_model.py -q
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from domains.tennis.point_engine.corpus import N_SCORE_BUCKETS, N_SET_BUCKETS

MIN_CELL = 25
ALPHA = 1.0   # Laplace smoothing pseudo-count on each side (win/loss)


def _rate(wins: float, n: float, base: float) -> float:
    """Laplace-smoothed rate, shrunk toward `base` via the ALPHA pseudo-counts."""
    return (wins + ALPHA * base) / (n + ALPHA)


class PointModel:
    """Empirical P(server wins point | server, score_bucket, set_bucket)."""

    def __init__(self, full: Dict[Tuple, float], server_only: Dict[str, float],
                 league_cell: np.ndarray, glob: float):
        self._full = full
        self._server_only = server_only
        self._league = league_cell   # [N_SCORE_BUCKETS, N_SET_BUCKETS]
        self._glob = glob

    @classmethod
    def fit(cls, df: pd.DataFrame, cond: Optional[str] = None) -> "PointModel":
        """df: server_id, score_bucket, set_bucket, server_won. `cond` is the v2
        returner-tier seam, ignored in v1."""
        won = df["server_won"].to_numpy(dtype=float)
        glob = float(won.mean()) if len(won) else 0.5

        league = np.full((N_SCORE_BUCKETS, N_SET_BUCKETS), glob)
        for (sb, tb), g in df.groupby(["score_bucket", "set_bucket"]):
            if len(g) >= MIN_CELL:
                league[sb, tb] = _rate(g["server_won"].sum(), len(g), glob)

        server_only: Dict[str, float] = {}
        for sid, g in df.groupby("server_id"):
            server_only[sid] = _rate(g["server_won"].sum(), len(g), glob)

        full: Dict[Tuple, float] = {}
        for (sid, sb, tb), g in df.groupby(["server_id", "score_bucket", "set_bucket"]):
            if len(g) >= MIN_CELL:
                full[(sid, sb, tb)] = _rate(g["server_won"].sum(), len(g),
                                            server_only.get(sid, glob))
        return cls(full, server_only, league, glob)

    def prob(self, server_id: str, score_bucket: int, set_bucket: int) -> float:
        v = self._full.get((server_id, score_bucket, set_bucket))
        if v is not None:
            return v
        v = self._server_only.get(server_id)
        if v is not None:
            return v
        return float(self._league[score_bucket, set_bucket])

    def summary(self) -> dict:
        return {"n_full_cells": len(self._full), "n_servers": len(self._server_only),
                "min_cell": MIN_CELL, "global_serve_win_rate": round(self._glob, 4)}


def naive_baseline(df: pd.DataFrame) -> Dict[str, float]:
    """Per-server CONSTANT point-win rate, no score-state conditioning at all --
    the classic i.i.d.-points tennis model. Backoff to league global."""
    won = df["server_won"].to_numpy(dtype=float)
    glob = float(won.mean()) if len(won) else 0.5
    out: Dict[str, float] = {"__global__": glob}
    for sid, g in df.groupby("server_id"):
        out[sid] = _rate(g["server_won"].sum(), len(g), glob)
    return out


__all__ = ["PointModel", "naive_baseline", "MIN_CELL", "ALPHA"]
