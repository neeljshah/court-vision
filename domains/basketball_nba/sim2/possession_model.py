"""domains.basketball_nba.sim2.possession_model -- EMPIRICAL possession-outcome
model for the NBA possession-level simulator v2 (validated DISTRIBUTIONALLY, not
a betting-edge product; markets are efficient).

WHAT THIS IS
------------
A transparent, empirical conditional model of points-per-possession. NO neural
nets, NO fitted parameters beyond counted frequencies. For each declared game
STATE bucket it holds the empirical PMF over the points the team on offense scores
in one possession (0,1,2,3,4,5,6; 6 = "6 or more", rare OREB/and-1 chains).

POSSESSION UNIT (declared)
--------------------------
A possession is the TEAM-CONTINUITY unit produced by the corpus segmenter
(composition.shot_clock_proxy.resolve_segments): a maximal run of consecutive PBP
actions with the same possessing team. Offensive rebounds STAY within the same
possession (the ball did not change teams), so a possession can yield 0..6+ points
and last longer than one shot. Possessions therefore strictly ALTERNATE between
the two teams -- exactly what the simulator needs. Turnovers fold into the
"0 points" outcome; ORB-extension folds into the point total + a longer duration
(modelled by pace_model). This is the deliberate v2 simplification: points + a
duration fully determine the margin random walk, which is all a win-prob simulator
needs. It is stated here rather than modelled as separate turnover/ORB categories.

STATE BUCKET (5 declared dims; see bucket helpers)
--------------------------------------------------
  time_b   : 6 buckets  Q1,Q2,Q3, Q4>3min, Q4<=3min, OT
  margin_b : 7 buckets  OFFENSE-relative margin (off_score-def_score), symmetric,
             so home/away possessions share cells and late-game asymmetry (a
             LEADING offense late gets fouled -> FT points) is captured empirically.
  off_t    : 3 offense as-of offensive-strength terciles (assigned by caller)
  def_t    : 3 defense as-of defensive-strength terciles (assigned by caller)
  pace_t   : 3 game as-of pace terciles (assigned by caller)
Cell index = ((((time_b*7+margin_b)*3+off_t)*3+def_t)*3+pace_t), n_cells=3402.

BACKOFF (sparsity, declared): a cell with < MIN_CELL possessions falls back to the
(time_b,margin_b) marginal PMF (42 always-dense cells); that in turn backs off to
the global PMF. So every cell has a proper, normalized PMF.

LEAK-FREENESS: nothing here reads a game's own future. The as-of strength terciles
are computed by the caller from strictly-prior games. The point PMFs are fitted on
the fit seasons only; the held-out season never touches the fit.

Conditioning HOOK (v3 seam): fit() accepts an optional `cond` column name; if given
it is ignored by v2 (kept 0) but the API slot exists so lineup/attribute
conditioning can enter without a signature change.

INVARIANTS: domains-only; <=300 LOC; ASCII; numpy/pandas; no src/kernel imports.
Tests: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/sim2/test_possession_model.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from domains.basketball_nba.composition.shot_clock_proxy import resolve_segments, _detect_mode
from domains.basketball_nba.lineups.pbp_lineups import _period_length_s

PMAX = 6                    # point-value cap (6 == "6 or more")
N_TIME, N_MARGIN = 6, 7
N_CELLS = N_TIME * N_MARGIN * 3 * 3 * 3
MIN_CELL = 40              # backoff threshold: cells thinner than this use the marginal
_MARGIN_EDGES = (-15.0, -8.0, -3.0, 3.0, 8.0, 15.0)   # 7 off-relative margin buckets


def time_bucket(period: int, clock_remaining_s: float) -> int:
    """0..5 : Q1,Q2,Q3, Q4>3min, Q4<=3min, OT. clock_remaining_s = seconds left in
    the CURRENT period (period-relative, matching _period_length_s semantics)."""
    if period <= 3:
        return int(period) - 1
    if period == 4:
        return 3 if clock_remaining_s > 180.0 else 4
    return 5


def margin_bucket(off_margin: float) -> int:
    """0..6 over the OFFENSE-relative margin (off_score - def_score). Symmetric edges."""
    b = 0
    for e in _MARGIN_EDGES:
        if off_margin >= e:
            b += 1
    return b


def cell_index(time_b, margin_b, off_t, def_t, pace_t):
    """Vectorized-safe flat cell index from the 5 bucket dims (ints or int arrays)."""
    return ((((time_b * N_MARGIN + margin_b) * 3 + off_t) * 3 + def_t) * 3 + pace_t)


# ---------------------------------------------------------------------------
# Possession extraction from a single game's PBP actions (pure, testable)
# ---------------------------------------------------------------------------


def _infer_home_team(actions: List[Dict[str, Any]]) -> Optional[int]:
    """Home team_id = the team whose made baskets increment scoreHome. Score-based,
    so it needs no tricode crosswalk. None if undeterminable."""
    prev_h = prev_a = 0
    votes: Dict[int, int] = {}
    for a in sorted(actions, key=lambda x: x["actionNumber"]):
        h, a_ = a.get("scoreHome"), a.get("scoreAway")
        tid = a.get("teamId")
        if h is None or a_ is None or tid is None:
            continue
        h, a_ = int(h), int(a_)
        if h > prev_h and a_ == prev_a:
            votes[tid] = votes.get(tid, 0) + 1
        prev_h, prev_a = h, a_
    return max(votes, key=votes.get) if votes else None


def extract_possessions(actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """PURE: one game's PBP actions -> list of possession rows. Each row:
    period, clock_start (sec remaining in period), off_is_home, points (0..6),
    duration (s, 1..40), off_margin, home_margin. [] if unusable. Leak-free per game.
    """
    if not actions:
        return []
    home = _infer_home_team(actions)
    if home is None:
        return []
    mode = _detect_mode(actions)
    seg = {r["action_number"]: r for r in resolve_segments(actions, mode=mode)}
    acts = sorted(actions, key=lambda x: x["actionNumber"])
    # running scores keyed to each action (cumulative AFTER that action)
    poss: List[Dict[str, Any]] = []
    cur_key = None
    start_h = start_a = 0
    start_elapsed = 0.0
    cur_period = None
    prev_h = prev_a = 0
    for a in acts:
        r = seg.get(a["actionNumber"])
        if r is None or r["seg_team"] is None:
            prev_h = int(a.get("scoreHome") or prev_h)
            prev_a = int(a.get("scoreAway") or prev_a)
            continue
        key = (r["period"], r["seg_team"], r["seg_start_s"])
        if key != cur_key:
            if cur_key is not None:
                _emit(poss, cur_key, home, start_h, start_a, prev_h, prev_a,
                      start_elapsed, r["elapsed_s"], cur_period)
            cur_key = key
            cur_period = r["period"]
            start_h, start_a = prev_h, prev_a
            start_elapsed = r["seg_start_s"]
        prev_h = int(a.get("scoreHome") or prev_h)
        prev_a = int(a.get("scoreAway") or prev_a)
    if cur_key is not None:  # last possession: closes at period end
        _emit(poss, cur_key, home, start_h, start_a, prev_h, prev_a,
              start_elapsed, _period_length_s(cur_period), cur_period)
    return poss


def _emit(out, key, home, sh0, sa0, sh1, sa1, start_elapsed, end_elapsed, period):
    off_team = key[1]
    off_is_home = off_team == home
    pts_off = (sh1 - sh0) if off_is_home else (sa1 - sa0)
    if pts_off < 0:
        return
    dur = end_elapsed - start_elapsed
    if dur < 1.0 or dur > 40.0:
        dur = min(max(dur, 1.0), 40.0)
    home_margin = sh0 - sa0
    off_margin = home_margin if off_is_home else -home_margin
    clock_start = _period_length_s(period) - start_elapsed
    out.append({
        "period": int(period), "clock_start": float(clock_start),
        "off_is_home": bool(off_is_home), "points": int(min(pts_off, PMAX)),
        "duration": float(dur), "off_margin": float(off_margin),
        "home_margin": float(home_margin),
        "home_score_start": int(sh0), "away_score_start": int(sa0),
    })


def add_state_buckets(df: pd.DataFrame) -> pd.DataFrame:
    """Attach time_b, margin_b to a possession frame (needs period, clock_start,
    off_margin). off_t/def_t/pace_t are added by the caller from as-of terciles."""
    df = df.copy()
    df["time_b"] = [time_bucket(int(p), float(c))
                    for p, c in zip(df["period"], df["clock_start"])]
    df["margin_b"] = [margin_bucket(float(m)) for m in df["off_margin"]]
    return df


# ---------------------------------------------------------------------------
# The empirical point-outcome model
# ---------------------------------------------------------------------------


class PossessionModel:
    """Empirical P(points | state) with (time,margin) -> global backoff.

    Fit input columns: time_b, margin_b, off_t, def_t, pace_t, points.
    `point_cdf_matrix()` returns the [N_CELLS, PMAX+1] inclusive-CDF matrix the
    simulator indexes by cell_index(); every row is a normalized CDF ending at 1.
    """

    def __init__(self, cdf: np.ndarray, n_full: int, n_backoff: int, n_global: int):
        self.cdf = cdf
        self.n_full = n_full
        self.n_backoff = n_backoff
        self.n_global = n_global

    @staticmethod
    def _pmf(points: np.ndarray) -> np.ndarray:
        c = np.bincount(np.clip(points, 0, PMAX), minlength=PMAX + 1).astype(float)
        s = c.sum()
        return c / s if s > 0 else np.ones(PMAX + 1) / (PMAX + 1)

    @classmethod
    def fit(cls, df: pd.DataFrame, cond: Optional[str] = None) -> "PossessionModel":
        pts = df["points"].to_numpy()
        glob = cls._pmf(pts)
        # (time,margin) marginal table [42, PMAX+1]
        marg = np.tile(glob, (N_TIME * N_MARGIN, 1))
        tm = (df["time_b"].to_numpy() * N_MARGIN + df["margin_b"].to_numpy())
        for k in range(N_TIME * N_MARGIN):
            m = tm == k
            if m.sum() > 0:
                marg[k] = cls._pmf(pts[m])
        # full cells with backoff
        pmf = np.zeros((N_CELLS, PMAX + 1))
        cell = cell_index(df["time_b"].to_numpy(), df["margin_b"].to_numpy(),
                          df["off_t"].to_numpy(), df["def_t"].to_numpy(),
                          df["pace_t"].to_numpy())
        order = np.argsort(cell)
        cell_s, pts_s = cell[order], pts[order]
        bounds = np.searchsorted(cell_s, np.arange(N_CELLS + 1))
        n_full = n_back = n_glob = 0
        for c in range(N_CELLS):
            lo, hi = bounds[c], bounds[c + 1]
            n = hi - lo
            tmk = c // 27  # (time*7+margin) recovered: cell = tmk*27 + rest
            if n >= MIN_CELL:
                pmf[c] = cls._pmf(pts_s[lo:hi]); n_full += 1
            elif marg[tmk].sum() > 0:
                pmf[c] = marg[tmk]; n_back += 1
            else:
                pmf[c] = glob; n_glob += 1
        cdf = np.cumsum(pmf, axis=1)
        cdf[:, -1] = 1.0
        return cls(cdf, n_full, n_back, n_glob)

    def point_cdf_matrix(self) -> np.ndarray:
        return self.cdf

    def summary(self) -> Dict[str, Any]:
        return {"n_cells": N_CELLS, "n_full": self.n_full,
                "n_backoff_marginal": self.n_backoff, "n_global": self.n_global,
                "min_cell": MIN_CELL, "pmax": PMAX}

    def save(self, path: Path) -> None:
        np.savez_compressed(path, cdf=self.cdf,
                            meta=np.array([self.n_full, self.n_backoff, self.n_global]))


__all__ = ["PMAX", "N_TIME", "N_MARGIN", "N_CELLS", "time_bucket", "margin_bucket",
           "cell_index", "extract_possessions", "add_state_buckets", "PossessionModel"]
