"""domains.mlb.pitch_engine.outcome_platoon -- platoon-conditioned OUTCOME table
(gate candidate for the OPEN inn4|m2 bucket, sim heatmap sweep 2026-07-10).

Mechanism #1 (platoon (pitcher-hand x batter-stand) x pitch type) is CONFIRMED
REPLICATED across 3+ corpora in domains/mlb/knowledge/mechanisms.md -- the
strongest-evidence single mechanism in the MLB ledger -- but outcome.py's
OutcomeModel table is P(outcome | class, zone, count, tier) and never carries a
platoon term: selection.py already conditions pitch-CLASS choice on platoon
(pidx), but the OUTCOME of a pitch, once thrown, does not. This module adds ONE
extra same_hand={0,1} dimension (same_hand = pitcher-throws == batter-stand,
matching mechanism #1's own "same-hand x pitch-type" test spec) with backoff to
the existing base OutcomeModel table whenever a platoon-specific cell is
thinner than MIN_CELL -- composition over duplication: outcome.py is READ-ONLY
and untouched, its fitted table is the floor every platoon cell backs off to.

INVARIANTS: domains-only; corpus READ-ONLY; ASCII; <=300 LOC.
Tests: python -m pytest domains/mlb/pitch_engine/test_outcome_platoon.py -q
"""
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd

from domains.mlb.pitch_engine.outcome import (
    OutcomeModel, BatterTiers, _OUT_IX, _CLASS_IX, _norm, MIN_CELL, N_OUT,
)
from domains.mlb.pitch_engine.pa_chain import N_COUNT, pa_event_dist


class PlatoonOutcomeModel:
    """P(outcome | class, zone, count, tier, same_hand) with backoff to the base
    (platoon-blind) OutcomeModel table for any cell below MIN_CELL."""

    def __init__(self, base: OutcomeModel,
                 cells: Dict[Tuple[int, int, int, int, int], np.ndarray]):
        self._base = base
        self._cells = cells

    @classmethod
    def fit(cls, pitch_df: pd.DataFrame, tiers: BatterTiers,
            base: OutcomeModel) -> "PlatoonOutcomeModel":
        cix = pitch_df["pclass"].map(_CLASS_IX).to_numpy()
        zix = (pitch_df["zbucket"].to_numpy() == "OZ").astype(int)
        cidx = pitch_df["cidx"].to_numpy()
        oix = pitch_df["outcome"].map(_OUT_IX).to_numpy()
        tier = tiers.assign(pitch_df["batter"].to_numpy(), cix)
        same_hand = pitch_df["pidx"].isin([0, 3]).to_numpy().astype(int)

        counts = np.zeros((3, 2, N_COUNT, 3, 2, N_OUT))
        np.add.at(counts, (cix, zix, cidx, tier, same_hand, oix), 1.0)
        cells: Dict[Tuple[int, int, int, int, int], np.ndarray] = {}
        for k in range(3):
            for z in range(2):
                for c in range(N_COUNT):
                    for t in range(3):
                        for sh in range(2):
                            cell = counts[k, z, c, t, sh]
                            if cell.sum() >= MIN_CELL:
                                cells[(k, z, c, t, sh)] = _norm(cell)
        return cls(base, cells)

    def outcome_probs(self, class_ix: int, zone_ix: int, cidx: int, tier: int,
                       same_hand: int) -> np.ndarray:
        v = self._cells.get((int(class_ix), int(zone_ix), int(cidx), int(tier),
                              int(same_hand)))
        if v is not None:
            return v
        return self._base.outcome_probs(class_ix, zone_ix, cidx, tier)

    def summary(self) -> dict:
        return {"n_platoon_cells": len(self._cells), "min_cell": MIN_CELL,
                "mechanism": "#1 platoon(pitcher-hand x batter-stand) x pitch-type, "
                             "CONFIRMED REPLICATED"}


def context_outcome_matrix_platoon(sel, out_p: PlatoonOutcomeModel, tiers,
                                   pitcher, batter, pidx, bbucket) -> np.ndarray:
    """[12,10] P(outcome | count), same-hand-aware. Identical to
    pa_chain.context_outcome_matrix except the outcome lookup also takes
    same_hand (derived from pidx: 0/3 = same-handed, 1/2 = opposite)."""
    same_hand = 1 if pidx in (0, 3) else 0
    tier_by_class = [tiers.tier(batter, k) for k in range(3)]
    mat = np.zeros((N_COUNT, N_OUT))
    for cidx in range(N_COUNT):
        classp = sel.class_probs(pitcher, cidx, pidx, bbucket)
        row = np.zeros(N_OUT)
        for k in range(3):
            zp = sel.zone_probs(k, cidx)
            for z in range(2):
                row += classp[k] * zp[z] * out_p.outcome_probs(
                    k, z, cidx, tier_by_class[k], same_hand)
        mat[cidx] = row
    return mat


def assemble_platoon(sel, out_p: PlatoonOutcomeModel, tiers, pitcher, batter,
                     pidx, bbucket) -> np.ndarray:
    """Full chain, same-hand-aware outcome table -> PA-event distribution [8]."""
    return pa_event_dist(
        context_outcome_matrix_platoon(sel, out_p, tiers, pitcher, batter, pidx, bbucket))


__all__ = ["PlatoonOutcomeModel", "context_outcome_matrix_platoon", "assemble_platoon"]
