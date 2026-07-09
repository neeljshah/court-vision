"""domains.mlb.pitch_engine.game_sim -- base-out transition + inning/game Monte-Carlo.

Two pieces:

BaseOutTransition -- an EMPIRICAL base-out advancement model. From the prior-season
PA frame it records, for each (base_out_state 0..23, PA event), the observed joint
(runs scored on the play, resulting base-out state). The resulting state is the NEXT
PA's base-out state within the same half-inning; a 3rd out is the sentinel 24
(inning over). Sampling from this reproduces real baserunning, GIDPs, sac flies,
and inning-ending outs empirically -- the base-out analogue of sim2's empirical
possession PMFs. Backoff for a thin (state,event) cell: the event's pooled samples.

simulate_game -- fully vectorized over N sims (numpy, no per-sim Python loop; each
iteration advances one PA for every still-live sim). Standard MLB end rules incl.
walk-offs and extra innings. Deterministic under `seed`.

Declared simplifications (v1): the PA-event distribution per lineup slot is taken at
a single base context (the caller supplies pa_away[9,8]/pa_home[9,8]); base state
enters through the transition (where it matters most for runs). Reliever modeling
and within-inning slot tracking across mid-game snapshots are v2 seams.

INVARIANTS: domains-only; ASCII; numpy only; <=300 LOC.
Tests: python -m pytest domains/mlb/pitch_engine/test_game_sim.py -q
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from domains.mlb.pitch_engine.pa_chain import _PA_IX

N_BOS = 24
INNING_OVER = 24
_MAX_STEPS = 400
_EXTRA_CAP = 30


class BaseOutTransition:
    """Empirical (runs, next_base_out_state) sampler keyed by (bos, pa_event)."""

    def __init__(self, cell: Dict[int, Tuple[np.ndarray, np.ndarray]],
                 by_evt: Dict[int, Tuple[np.ndarray, np.ndarray]], min_cell: int):
        self._cell = cell            # key = bos*8+evt -> (runs[], next[])
        self._by_evt = by_evt        # evt -> pooled (runs[], next[])
        self.min_cell = min_cell

    @classmethod
    def fit(cls, pa_frame: pd.DataFrame, min_cell: int = 25) -> "BaseOutTransition":
        df = pa_frame.copy()
        df["evix"] = df["pa_evt"].map(_PA_IX).astype(int)
        df = df.sort_values(["game_pk", "inning", "inning_topbot", "at_bat_number"])
        g = df.groupby(["game_pk", "inning", "inning_topbot"], sort=False)
        nxt_mask = g["base_mask"].shift(-1)
        nxt_outs = g["outs_start"].shift(-1)
        last = nxt_mask.isna()
        next_state = np.where(last, INNING_OVER,
                              (nxt_mask.fillna(0).astype(int) * 3
                               + nxt_outs.fillna(0).astype(int))).astype(int)
        runs = df["runs"].to_numpy().astype(int)
        bos = df["base_out_state"].to_numpy().astype(int)
        evt = df["evix"].to_numpy()
        key = bos * 8 + evt
        cell: Dict[int, Tuple[np.ndarray, np.ndarray]] = {}
        for k in np.unique(key):
            m = key == k
            if m.sum() >= min_cell:
                cell[int(k)] = (runs[m].astype(np.int16), next_state[m].astype(np.int16))
        by_evt: Dict[int, Tuple[np.ndarray, np.ndarray]] = {}
        for e in np.unique(evt):
            m = evt == e
            by_evt[int(e)] = (runs[m].astype(np.int16), next_state[m].astype(np.int16))
        return cls(cell, by_evt, min_cell)

    def sample(self, key: np.ndarray, evt: np.ndarray, rng) -> Tuple[np.ndarray, np.ndarray]:
        """Vectorized: for per-sim key=bos*8+evt draw (runs, next_state)."""
        n = len(key)
        out_r = np.zeros(n, dtype=int)
        out_n = np.full(n, INNING_OVER, dtype=int)
        for k in np.unique(key):
            idx = np.nonzero(key == k)[0]
            pool = self._cell.get(int(k))
            if pool is None:
                pool = self._by_evt.get(int(k % 8))
            if pool is None:
                continue
            r, nx = pool
            pick = rng.integers(0, len(r), size=len(idx))
            out_r[idx] = r[pick]
            out_n[idx] = nx[pick]
        return out_r, out_n

    def summary(self) -> dict:
        return {"n_cells": len(self._cell), "min_cell": self.min_cell,
                "n_evt_pools": len(self._by_evt)}


@dataclass
class GameStart:
    inning: int = 1
    half: int = 0          # 0 = top (away bats), 1 = bottom (home bats)
    outs: int = 0
    base_mask: int = 0
    home_score: int = 0
    away_score: int = 0
    away_slot: int = 0
    home_slot: int = 0


def simulate_game(pa_away: np.ndarray, pa_home: np.ndarray, trans: BaseOutTransition,
                  n: int = 2000, seed: int = 0,
                  start: Optional[GameStart] = None) -> Tuple[np.ndarray, np.ndarray]:
    """Return (home_final[n], away_final[n]) run totals. pa_away/pa_home: [9,8] PA-
    event dists per lineup slot for the team when batting."""
    rng = np.random.default_rng(seed)
    s = start or GameStart()
    inn = np.full(n, s.inning); half = np.full(n, s.half)
    outs = np.full(n, s.outs); mask = np.full(n, s.base_mask)
    sh = np.full(n, s.home_score, dtype=int); sa = np.full(n, s.away_score, dtype=int)
    aslot = np.full(n, s.away_slot); hslot = np.full(n, s.home_slot)
    done = np.zeros(n, dtype=bool)
    cdf_a = np.cumsum(pa_away, axis=1); cdf_h = np.cumsum(pa_home, axis=1)

    for _ in range(_MAX_STEPS):
        act = ~done
        if not act.any():
            break
        bat_home = half == 1
        slot = np.where(bat_home, hslot, aslot)
        cdf = np.where(bat_home[:, None], cdf_h[slot], cdf_a[slot])   # [n,8]
        u = rng.random(n)
        evt = np.clip((u[:, None] >= cdf).sum(axis=1), 0, 7)
        bos = mask * 3 + outs
        key = bos * 8 + evt
        runs, nxt = trans.sample(key, evt, rng)
        runs = np.where(act, runs, 0)
        sh = sh + np.where(act & bat_home, runs, 0)
        sa = sa + np.where(act & ~bat_home, runs, 0)
        aslot = np.where(act & ~bat_home, (aslot + 1) % 9, aslot)
        hslot = np.where(act & bat_home, (hslot + 1) % 9, hslot)
        prev_half = half.copy()
        over = act & (nxt >= INNING_OVER)
        cont = act & (nxt < INNING_OVER)
        outs = np.where(cont, nxt % 3, np.where(over, 0, outs))
        mask = np.where(cont, nxt // 3, np.where(over, 0, mask))
        inc_inn = over & (prev_half == 1)
        half = np.where(over, 1 - prev_half, half)
        inn = np.where(inc_inn, inn + 1, inn)
        # end-of-game rules
        done |= act & bat_home & (inn >= 9) & (sh > sa)                  # walk-off
        done |= over & (prev_half == 0) & (inn >= 9) & (sh > sa)         # home leads after top 9+
        done |= inc_inn & ((inn - 1) >= 9) & (sh != sa)                  # full inning, decided
        done |= inn > _EXTRA_CAP                                         # guard
    # resolve any unfinished (guard): leave scores as-is (ties broken by rng)
    tie = (~done) & (sh == sa)
    if tie.any():
        sh = sh + (rng.random(n) < 0.5) * tie
    return sh, sa


__all__ = ["BaseOutTransition", "GameStart", "simulate_game", "INNING_OVER", "N_BOS"]
