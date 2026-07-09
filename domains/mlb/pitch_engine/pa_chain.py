"""domains.mlb.pitch_engine.pa_chain -- the PA ASSEMBLER.

Chains the selection model (P(class|count,...)) and the outcome model
(P(outcome|class,zone,count,tier)) through the 12 ball/strike count states to an
absorbing PLATE-APPEARANCE outcome distribution over the 8 PA events
{OUT,K,BB,HBP,1B,2B,3B,HR}.

The count chain is a small absorbing Markov chain (12 transient count states, 8
absorbing PA events). Given the per-count outcome distribution it is solved
EXACTLY -- pa = e00 . (I - M)^-1 . A -- no Monte-Carlo needed for the PA level
(the game MC samples PA events from this exact vector). Count transitions:
  ball -> balls+1 (4 balls = BB);  called/swinging strike -> strikes+1 (3 = K);
  foul -> strikes+1 but never past 2 (self-loop at 2 strikes);  in_play_out/hit/
  hbp -> absorbed immediately.

DirectPAModel is the "direct PA prediction" twin used by validate.py panel (b): an
empirical P(pa_evt | batter_tier, platoon, base_bucket) fit on the SAME prior-
season context but WITHOUT the pitch chain -- so the comparison isolates exactly
what the pitch-by-pitch assembly adds (or fails to add).

INVARIANTS: domains-only; ASCII; numpy/pandas; <=300 LOC.
Tests: python -m pytest domains/mlb/pitch_engine/test_pa_chain.py -q
"""
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd

from domains.mlb.pitch_engine.corpus import PA_EVENTS
from domains.mlb.pitch_engine.outcome import _OUT_IX

N_COUNT = 12
_PA_IX = {e: i for i, e in enumerate(PA_EVENTS)}   # OUT,K,BB,HBP,1B,2B,3B,HR
# per-outcome routing constants (outcome index -> PA event index for absorbers)
_ABS = {_OUT_IX["in_play_out"]: _PA_IX["OUT"], _OUT_IX["single"]: _PA_IX["1B"],
        _OUT_IX["double"]: _PA_IX["2B"], _OUT_IX["triple"]: _PA_IX["3B"],
        _OUT_IX["hr"]: _PA_IX["HR"], _OUT_IX["hbp"]: _PA_IX["HBP"]}
_BALL, _CS, _SS, _FOUL = (_OUT_IX["ball"], _OUT_IX["called_strike"],
                          _OUT_IX["swinging_strike"], _OUT_IX["foul"])


def context_outcome_matrix(sel, out, tiers, pitcher, batter, pidx, bbucket) -> np.ndarray:
    """[12,10] P(outcome | count) for this pitcher/batter/platoon/base context,
    marginalizing class and zone."""
    tier_by_class = [tiers.tier(batter, k) for k in range(3)]
    mat = np.zeros((N_COUNT, 10))
    for cidx in range(N_COUNT):
        classp = sel.class_probs(pitcher, cidx, pidx, bbucket)   # [3]
        row = np.zeros(10)
        for k in range(3):
            zp = sel.zone_probs(k, cidx)                          # [2]
            for z in range(2):
                row += classp[k] * zp[z] * out.outcome_probs(k, z, cidx, tier_by_class[k])
        mat[cidx] = row
    return mat


def _count_matrices(omat: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """From the [12,10] outcome matrix build the transient [12,12] M and absorbing
    [12,8] A of the count chain (row = current count b*3+s)."""
    M = np.zeros((N_COUNT, N_COUNT))
    A = np.zeros((N_COUNT, len(PA_EVENTS)))
    for c in range(N_COUNT):
        b, s = c // 3, c % 3
        p = omat[c]
        # ball
        if b == 3:
            A[c, _PA_IX["BB"]] += p[_BALL]
        else:
            M[c, (b + 1) * 3 + s] += p[_BALL]
        # strike (called or swinging)
        pstr = p[_CS] + p[_SS]
        if s == 2:
            A[c, _PA_IX["K"]] += pstr
        else:
            M[c, b * 3 + (s + 1)] += pstr
        # foul
        if s < 2:
            M[c, b * 3 + (s + 1)] += p[_FOUL]
        else:
            M[c, c] += p[_FOUL]
        # immediate absorbers
        for oix, paix in _ABS.items():
            A[c, paix] += p[oix]
    return M, A


def pa_event_dist(omat: np.ndarray, max_pitches: int = 60) -> np.ndarray:
    """Absorbing-chain propagation from count 0-0 -> normalized [8] PA-event dist.
    Iterative (foul-at-2-strikes self-loops decay geometrically once any escape
    probability is positive), so no singular-matrix risk from a pathological cell."""
    M, A = _count_matrices(omat)
    v = np.zeros(N_COUNT)
    v[0] = 1.0                                    # count 0-0
    pa = np.zeros(len(PA_EVENTS))
    for _ in range(max_pitches):
        pa += v @ A
        v = v @ M
        if v.sum() < 1e-9:
            break
    s = pa.sum()
    return pa / s if s > 0 else np.ones(len(PA_EVENTS)) / len(PA_EVENTS)


def assemble(sel, out, tiers, pitcher, batter, pidx, bbucket) -> np.ndarray:
    """Full chain: context -> PA-event distribution [8]."""
    return pa_event_dist(context_outcome_matrix(sel, out, tiers, pitcher, batter, pidx, bbucket))


class DirectPAModel:
    """Direct empirical P(pa_evt | tier, platoon, base_bucket) -- the no-chain twin.
    Backoff: (tier,pidx,bbucket) -> (tier) -> global."""

    def __init__(self, full: Dict[Tuple, np.ndarray], by_tier, glob):
        self._full = full
        self._by_tier = by_tier
        self._glob = glob

    @classmethod
    def fit(cls, pa_frame: pd.DataFrame, tiers, min_cell: int = 40) -> "DirectPAModel":
        df = pa_frame.copy()
        df["evix"] = df["pa_evt"].map(_PA_IX)
        df["tier"] = [tiers.tier(b, -1) for b in df["batter"].to_numpy()]  # overall tier
        glob = _norm(np.bincount(df["evix"], minlength=len(PA_EVENTS)).astype(float))
        by_tier: Dict[int, np.ndarray] = {}
        for t, g in df.groupby("tier"):
            by_tier[int(t)] = _norm(np.bincount(g["evix"], minlength=len(PA_EVENTS)).astype(float))
        full: Dict[Tuple, np.ndarray] = {}
        for key, g in df.groupby(["tier", "pidx", "bbucket"]):
            if len(g) < min_cell:
                continue
            full[tuple(int(x) for x in key)] = _norm(
                np.bincount(g["evix"], minlength=len(PA_EVENTS)).astype(float))
        return cls(full, by_tier, glob)

    def probs(self, batter_tier: int, pidx: int, bbucket: int) -> np.ndarray:
        v = self._full.get((int(batter_tier), int(pidx), int(bbucket)))
        if v is not None:
            return v
        return self._by_tier.get(int(batter_tier), self._glob)


def _norm(v: np.ndarray) -> np.ndarray:
    s = v.sum()
    return v / s if s > 0 else np.ones_like(v) / len(v)


__all__ = ["context_outcome_matrix", "pa_event_dist", "assemble", "DirectPAModel",
           "PA_EVENTS", "_PA_IX"]
