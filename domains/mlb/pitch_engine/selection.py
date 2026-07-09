"""domains.mlb.pitch_engine.selection -- empirical PITCH-SELECTION model.

P(pitch_class | pitcher, count, platoon, base-out leverage) as an empirical
conditional table with the declared backoff hierarchy:

    pitcher-specific cell  (pitcher, count, platoon, base_bucket)
      -> pitcher-count      (pitcher, count)            [pitcher's own mix]
      -> league cell        (count, platoon, base_bucket)
      -> league global      marginal class mix

A cell is used only when it holds >= MIN_CELL pitches; otherwise the next rung is
taken, so every context yields a proper normalized 3-vector over (FB, BR, OS).

A companion ZONE sub-model P(zone_bucket | pitch_class, count) (league-level) lets
the PA chain draw a zone bucket after the class -- the outcome model conditions on
it. Zone is league-level on purpose (pitcher x class x count x zone would be
sparse); pitcher-specific zone is a v2 seam.

AS-OF (leak-free): fit on the prior full season, applied forward. The optional
`asof_within_season` v2 seam is documented but NOT fitted in v1.

INVARIANTS: domains-only; ASCII; numpy/pandas; <=300 LOC.
Tests: python -m pytest domains/mlb/pitch_engine/test_selection.py -q
"""
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd

from domains.mlb.pitch_engine.corpus import PITCH_CLASSES

N_CLASS = len(PITCH_CLASSES)          # 3
N_COUNT, N_PLAT, N_BASE, N_ZONE = 12, 4, 3, 2
MIN_CELL = 30
ALPHA = 1.0                            # Laplace smoothing (kills held-out zeros)
_CLASS_IX = {c: i for i, c in enumerate(PITCH_CLASSES)}
_ZONE_IX = {"IZ": 0, "OZ": 1}


def _norm(v: np.ndarray) -> np.ndarray:
    """Laplace-smoothed normalize -- a class never seen in a 2023 cell keeps a small
    probability so a 2024 pitch there is not a log-loss catastrophe."""
    v = v + ALPHA
    return v / v.sum()


class SelectionModel:
    """Empirical P(class | pitcher, count, platoon, base) with backoff + a
    league P(zone | class, count) sub-model."""

    def __init__(self, pitcher_full, pitcher_count, league_cell, glob, zone):
        self._full: Dict[Tuple, np.ndarray] = pitcher_full
        self._pcount: Dict[Tuple, np.ndarray] = pitcher_count
        self._league = league_cell          # [12,4,3,3]
        self._glob = glob                    # [3]
        self._zone = zone                    # [3,12,2]

    @classmethod
    def fit(cls, df: pd.DataFrame, asof_within_season: bool = False) -> "SelectionModel":
        """df: pitch frame with columns pitcher, cidx, pidx, bbucket, pclass,
        zbucket. asof_within_season is the v2 seam (ignored in v1)."""
        cix = df["pclass"].map(_CLASS_IX).to_numpy()
        cidx = df["cidx"].to_numpy()
        pidx = df["pidx"].to_numpy()
        bb = df["bbucket"].to_numpy()
        pid = df["pitcher"].to_numpy()

        glob = _norm(np.bincount(cix, minlength=N_CLASS).astype(float))
        league = np.zeros((N_COUNT, N_PLAT, N_BASE, N_CLASS))
        np.add.at(league, (cidx, pidx, bb, cix), 1.0)
        for c in range(N_COUNT):
            for p in range(N_PLAT):
                for b in range(N_BASE):
                    league[c, p, b] = (_norm(league[c, p, b])
                                       if league[c, p, b].sum() >= MIN_CELL else glob)

        full = cls._table(np.stack([pid, cidx, pidx, bb], 1), cix)
        pcount = cls._table(np.stack([pid, cidx], 1), cix)

        # zone: P(zone | class, count), league level
        zix = df["zbucket"].map(_ZONE_IX).to_numpy()
        zone = np.zeros((N_CLASS, N_COUNT, N_ZONE))
        np.add.at(zone, (cix, cidx, zix), 1.0)
        for k in range(N_CLASS):
            for c in range(N_COUNT):
                zone[k, c] = _norm(zone[k, c]) if zone[k, c].sum() > 0 else np.ones(N_ZONE) / N_ZONE
        return cls(full, pcount, league, glob, zone)

    @staticmethod
    def _table(keys: np.ndarray, cix: np.ndarray) -> Dict[Tuple, np.ndarray]:
        """Group rows by the composite key, keep normalized class vectors for cells
        with >= MIN_CELL pitches."""
        out: Dict[Tuple, np.ndarray] = {}
        df = pd.DataFrame(keys)
        df["cix"] = cix
        keycols = list(range(keys.shape[1]))
        for key, g in df.groupby(keycols):
            if len(g) < MIN_CELL:
                continue
            v = np.bincount(g["cix"].to_numpy(), minlength=N_CLASS).astype(float)
            out[tuple(int(x) for x in (key if isinstance(key, tuple) else (key,)))] = _norm(v)
        return out

    def class_probs(self, pitcher: int, cidx: int, pidx: int, bbucket: int) -> np.ndarray:
        """Backoff lookup -> normalized [3] over (FB,BR,OS)."""
        v = self._full.get((int(pitcher), int(cidx), int(pidx), int(bbucket)))
        if v is not None:
            return v
        v = self._pcount.get((int(pitcher), int(cidx)))
        if v is not None:
            return v
        return self._league[int(cidx), int(pidx), int(bbucket)]

    def zone_probs(self, class_ix: int, cidx: int) -> np.ndarray:
        return self._zone[int(class_ix), int(cidx)]

    def summary(self) -> dict:
        return {"n_pitcher_full_cells": len(self._full),
                "n_pitcher_count_cells": len(self._pcount),
                "min_cell": MIN_CELL, "classes": list(PITCH_CLASSES)}


def no_context_baseline(df: pd.DataFrame) -> np.ndarray:
    """League marginal class mix [3] -- the no-context selection baseline."""
    cix = df["pclass"].map(_CLASS_IX).to_numpy()
    return _norm(np.bincount(cix, minlength=N_CLASS).astype(float))


__all__ = ["SelectionModel", "no_context_baseline", "N_CLASS", "PITCH_CLASSES",
           "_CLASS_IX", "MIN_CELL"]
