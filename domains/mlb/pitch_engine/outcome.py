"""domains.mlb.pitch_engine.outcome -- empirical PITCH-OUTCOME model.

P(outcome | pitch_class, zone_bucket, count, batter_tier) over the 10-way per-pitch
outcome space, an empirical conditional table with backoff:

    (class, zone, count, tier) -> (class, zone, count) -> (class, count) -> global

A cell is used only when it holds >= MIN_CELL pitches.

BATTER TIER = the batter's as-of profile "vs that class" (the replicated PA-v2
idea), reused here as a 3-way skill tercile. It is fit on the PRIOR season from a
wOBA-like value per PA (per (batter, pitch_class), backing off to the batter's
overall tier, then league-average tier 1). Fit on 2023, applied to 2024 -> leak-
free. A richer as-of / bat-tracking profile is a v2 seam (BatterTiers accepts an
optional extra feature but ignores it in v1).

INVARIANTS: domains-only; ASCII; numpy/pandas; <=300 LOC.
Tests: python -m pytest domains/mlb/pitch_engine/test_outcome.py -q
"""
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd

from domains.mlb.pitch_engine.corpus import OUTCOMES, PITCH_CLASSES

N_OUT = len(OUTCOMES)                 # 10
N_CLASS, N_ZONE, N_COUNT, N_TIER = 3, 2, 12, 3
MIN_CELL = 40
_OUT_IX = {o: i for i, o in enumerate(OUTCOMES)}
_CLASS_IX = {c: i for i, c in enumerate(PITCH_CLASSES)}
# wOBA-like linear weights on the 8-way PA event -> batter value per PA
_PA_VALUE = {"OUT": 0.0, "K": 0.0, "BB": 0.69, "HBP": 0.72,
             "1B": 0.89, "2B": 1.27, "3B": 1.62, "HR": 2.10}
_MIN_PA_TIER = 40
ALPHA = 0.5                            # Laplace smoothing over the 10-way outcome


def _norm(v: np.ndarray) -> np.ndarray:
    v = v + ALPHA
    return v / v.sum()


class BatterTiers:
    """Prior-season batter skill tiers (0/1/2), per (batter, pitch_class) with
    backoff to the batter overall then league-average tier 1."""

    def __init__(self, by_class, by_batter, edges):
        self._by_class: Dict[Tuple[int, int], int] = by_class
        self._by_batter: Dict[int, int] = by_batter
        self._edges = edges           # (lo, hi) value terciles

    @classmethod
    def fit(cls, pa_frame: pd.DataFrame) -> "BatterTiers":
        df = pa_frame.copy()
        df["val"] = df["pa_evt"].map(_PA_VALUE).astype(float)
        df["cix"] = df["pclass"].map(_CLASS_IX)
        overall = df.groupby("batter").agg(v=("val", "mean"), n=("val", "size"))
        q = overall[overall["n"] >= _MIN_PA_TIER]["v"]
        lo, hi = (float(q.quantile(1 / 3)), float(q.quantile(2 / 3))) if len(q) >= 3 else (0.30, 0.34)
        by_batter = {int(b): _tier(v, lo, hi)
                     for b, v, n in overall.itertuples() if n >= _MIN_PA_TIER}
        bc = df.groupby(["batter", "cix"]).agg(v=("val", "mean"), n=("val", "size"))
        by_class = {(int(b), int(c)): _tier(v, lo, hi)
                    for (b, c), v, n in bc.itertuples() if n >= _MIN_PA_TIER}
        return cls(by_class, by_batter, (lo, hi))

    def tier(self, batter: int, class_ix: int) -> int:
        t = self._by_class.get((int(batter), int(class_ix)))
        if t is not None:
            return t
        return self._by_batter.get(int(batter), 1)

    def assign(self, batter: np.ndarray, class_ix: np.ndarray) -> np.ndarray:
        return np.array([self.tier(b, c) for b, c in zip(batter, class_ix)], dtype=int)


def _tier(v: float, lo: float, hi: float) -> int:
    return 0 if v < lo else (2 if v >= hi else 1)


class OutcomeModel:
    """Empirical P(outcome | class, zone, count, tier) with 3-rung backoff."""

    def __init__(self, full, by_czc, by_cc, glob):
        self._full = full            # [3,2,12,3,10]
        self._czc = by_czc           # [3,2,12,10]
        self._cc = by_cc             # [3,12,10]
        self._glob = glob            # [10]

    @classmethod
    def fit(cls, pitch_df: pd.DataFrame, tiers: BatterTiers) -> "OutcomeModel":
        cix = pitch_df["pclass"].map(_CLASS_IX).to_numpy()
        zix = (pitch_df["zbucket"].to_numpy() == "OZ").astype(int)
        cidx = pitch_df["cidx"].to_numpy()
        oix = pitch_df["outcome"].map(_OUT_IX).to_numpy()
        tier = tiers.assign(pitch_df["batter"].to_numpy(), cix)

        glob = _norm(np.bincount(oix, minlength=N_OUT).astype(float))
        cc = np.zeros((N_CLASS, N_COUNT, N_OUT))
        np.add.at(cc, (cix, cidx, oix), 1.0)
        czc = np.zeros((N_CLASS, N_ZONE, N_COUNT, N_OUT))
        np.add.at(czc, (cix, zix, cidx, oix), 1.0)
        full = np.zeros((N_CLASS, N_ZONE, N_COUNT, N_TIER, N_OUT))
        np.add.at(full, (cix, zix, cidx, tier, oix), 1.0)

        for k in range(N_CLASS):
            for c in range(N_COUNT):
                cc[k, c] = _norm(cc[k, c]) if cc[k, c].sum() >= MIN_CELL else glob
        for k in range(N_CLASS):
            for z in range(N_ZONE):
                for c in range(N_COUNT):
                    czc[k, z, c] = (_norm(czc[k, z, c])
                                    if czc[k, z, c].sum() >= MIN_CELL else cc[k, c])
        for k in range(N_CLASS):
            for z in range(N_ZONE):
                for c in range(N_COUNT):
                    for t in range(N_TIER):
                        full[k, z, c, t] = (_norm(full[k, z, c, t])
                                            if full[k, z, c, t].sum() >= MIN_CELL
                                            else czc[k, z, c])
        return cls(full, czc, cc, glob)

    def outcome_probs(self, class_ix: int, zone_ix: int, cidx: int, tier: int) -> np.ndarray:
        return self._full[int(class_ix), int(zone_ix), int(cidx), int(tier)]

    def summary(self) -> dict:
        return {"outcomes": list(OUTCOMES), "min_cell": MIN_CELL,
                "shape_full": list(self._full.shape)}


__all__ = ["OutcomeModel", "BatterTiers", "OUTCOMES", "N_OUT", "_OUT_IX"]
