"""LANE 4 -- PROPS BASELINE SHOOTOUT #2 (queue item 4): the 4 PRE-DECLARED rate
families scored in props_eval_shootout2_mlb.py. Split out to respect the 300 LOC
cap (mirrors the props_eval_gate_mlb.py / _dist.py split from LANE 3).

FAMILIES (pre-declared, no open-ended search):
  (a) season_mean   : pitcher's own cumulative per-BF rate, walk-forward,
                       leak-free (EW_ALPHA=0 special case -- identical to
                       props_eval_gate_mlb_dist._RateState(alpha=0), the wave-5
                       WINNER and the family every other candidate must beat).
  (b) league_shrunk  : player_rate_shrunk = (n*player_rate + k*league_rate) / (n+k)
                       -- k is a SINGLE fixed constant fit ONCE on the
                       2022-2023 fit window ONLY (see fit_shrinkage_k below), not
                       re-fit per corpus and not fit per opportunity.
  (c) ew_alpha       : exponential-weighted rate, EW_ALPHA=0.35 (the wave-5
                       LOSER, kept here as the shootout's control arm).
  (d) prev_season    : previous-season-anchored -- a pitcher's PRESEASON prior is
                       last season's own per-BF rate shrunk to league (same k as
                       (b)), then walk-forward UPDATED by season-to-date starts
                       as the current season progresses (so it converges to
                       cumulative mean within a season, same as (a), but starts
                       each season from an informed prior instead of a blank one).

All 4 reuse the SAME expected-BF exposure projection (props_eval_gate_mlb_dist.
_expected_bf_snapshot) and the SAME NB dispersion (props_eval_gate_mlb_constants.
dispersion_for) -- only the RATE projection differs between families, exactly
the discipline LANE 3 used for model vs season_mean vs league_avg.

LEAK CONTRACT: every family is snapshot-before-update, walk-forward, identical
discipline to props_eval_gate_mlb_dist._RateState / _LeagueRateState. k (the
shrinkage constant) is fit ONCE on the fit_2022_2023 corpus only and then held
FIXED across both holdout corpora -- fitting k per-holdout would leak holdout
information into the family definition itself.

PURE pandas/numpy/stdlib; no src/kernel/api imports. ASCII only.
Per-file test only: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_props_eval_shootout2_mlb.py -q
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd

from domains.mlb.props_eval_gate_mlb_constants import CORPORA, PROPS, dispersion_for
from domains.mlb.props_eval_gate_mlb_dist import (
    MIN_PRIOR_STARTS,
    _corpus_label,
    _expected_bf_snapshot,
    _identify_start_opportunities,
    crps_discrete,
)

EW_ALPHA = 0.35  # control arm, matches props_eval_gate_mlb_dist.EW_ALPHA exactly
_K_GRID = [5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0, 75.0, 100.0, 150.0, 200.0]
FIT_CORPUS_LABEL = "fit_2022_2023"

FAMILIES = ("season_mean", "league_shrunk", "ew_alpha", "prev_season")


# ---------------------------------------------------------------------------
# Family (a) + (c): plain walk-forward per-pitcher rate, alpha in {0, EW_ALPHA}.
# Identical math to props_eval_gate_mlb_dist._RateState; a private local copy
# is kept here (not imported) so this module can be understood standalone and
# so a future edit to LANE 3's _RateState cannot silently change this
# shootout's families underneath it.
# ---------------------------------------------------------------------------


class _RateState:
    __slots__ = ("_alpha", "_mean", "_n")

    def __init__(self, alpha: float) -> None:
        self._alpha = alpha
        self._mean: Optional[float] = None
        self._n = 0

    def snapshot(self) -> Tuple[Optional[float], int]:
        if self._n < MIN_PRIOR_STARTS or self._mean is None:
            return None, self._n
        return self._mean, self._n

    def update(self, per_bf_rate: float, weight_n: int = 1) -> None:
        if self._mean is None:
            self._mean = per_bf_rate
        elif self._alpha > 0.0:
            self._mean = (1.0 - self._alpha) * self._mean + self._alpha * per_bf_rate
        else:
            total = self._mean * self._n + per_bf_rate * weight_n
            self._mean = total / (self._n + weight_n)
        self._n += 1


class _LeagueRateState:
    __slots__ = ("_stat_total", "_bf_total")

    def __init__(self) -> None:
        self._stat_total = 0.0
        self._bf_total = 0.0

    def snapshot(self) -> Optional[float]:
        if self._bf_total <= 1e-9:
            return None
        return self._stat_total / self._bf_total

    def update(self, stat_count: float, bf: float) -> None:
        self._stat_total += stat_count
        self._bf_total += bf


# ---------------------------------------------------------------------------
# Family (b): league-mean shrinkage. player_rate_shrunk = (n*rate + k*league)/(n+k)
# n = the pitcher's own PRIOR start count (BF-weighted cumulative n, i.e. the
# same _n a _RateState(alpha=0) tracks); rate = that pitcher's cumulative mean;
# league = the pooled league rate snapshot at that same point in time.
# ---------------------------------------------------------------------------


def shrink_rate(player_rate: Optional[float], n: int, league_rate: Optional[float],
                 k: float) -> Optional[float]:
    """(n*player_rate + k*league_rate) / (n+k). Falls back to league_rate when
    the pitcher has zero prior starts, and to player_rate when league is
    unresolvable yet (mirrors the other families' None-propagation contract)."""
    if player_rate is None and league_rate is None:
        return None
    if player_rate is None:
        return league_rate
    if league_rate is None:
        return player_rate
    return (n * player_rate + k * league_rate) / (n + k)


@dataclass
class _FitOpportunity:
    """One fit_2022_2023-window opportunity's ingredients for the k grid
    search -- captured once via a walk-forward pass, then reused across every
    k in the grid (only the shrinkage arithmetic changes per k, not the
    walk-forward state machine itself)."""
    player_rate: Optional[float]
    n_prior: int
    league_rate: Optional[float]
    e_bf: float
    y: float


def _collect_fit_opportunities(gamelogs_df: pd.DataFrame, probables_df: pd.DataFrame,
                                 stat_key: str) -> List[_FitOpportunity]:
    """Walk-forward pass restricted to fit_2022_2023, recording the raw
    ingredients (player rate/n, league rate, expected BF, realized y) needed to
    evaluate ANY k after the fact. This is NOT a leak: it still only uses
    strictly-prior information at each step; it just avoids re-running the
    walk-forward once per grid point."""
    col = PROPS[stat_key]
    opp = _identify_start_opportunities(gamelogs_df, probables_df)
    if len(opp) == 0:
        return []
    opp = opp.copy()
    opp["_d"] = pd.to_datetime(opp["date"])
    opp = opp.sort_values(["_d", "game_pk", "player_id"], kind="mergesort").reset_index(drop=True)

    player_states: Dict[int, _RateState] = {}
    league_state = _LeagueRateState()
    bf_hist: Dict[int, List[float]] = {}
    out: List[_FitOpportunity] = []
    for _, row in opp.iterrows():
        corpus = _corpus_label(row["_d"], {FIT_CORPUS_LABEL: CORPORA[FIT_CORPUS_LABEL]})
        pid = int(row["player_id"])
        bf = float(row["battersFaced"])
        y_raw = row.get(col)
        y = float(y_raw) if y_raw is not None and not pd.isna(y_raw) else None
        p_state = player_states.setdefault(pid, _RateState(0.0))
        p_rate, n_prior = p_state.snapshot()
        l_rate = league_state.snapshot()
        e_bf = _expected_bf_snapshot(bf_hist.get(pid, []))
        if corpus == FIT_CORPUS_LABEL and y is not None:
            out.append(_FitOpportunity(p_rate, n_prior, l_rate, e_bf, y))
        if y is not None:
            per_bf_rate = y / bf if bf > 1e-9 else 0.0
            p_state.update(per_bf_rate)
            league_state.update(y, bf)
            bf_hist.setdefault(pid, []).append(bf)
    return out


def fit_shrinkage_k(gamelogs_df: pd.DataFrame, probables_df: pd.DataFrame,
                     stat_key: str, k_grid: Optional[List[float]] = None
                     ) -> Dict[str, object]:
    """Single 1-D grid search for k, fit on fit_2022_2023 ONLY (never touches a
    holdout corpus). Selects the k minimizing mean CRPS of the shrunk-rate
    projection on the fit window; ties broken by the smallest k (more player
    signal, less shrinkage -- the more parsimonious tie-break). Returns
    {'k': float, 'grid_crps': {k: crps}, 'n_fit': int} and NEVER raises --
    degrades to a conservative mid-grid default when the fit window has no
    scorable opportunities."""
    grid = k_grid or _K_GRID
    try:
        fit_opps = _collect_fit_opportunities(gamelogs_df, probables_df, stat_key)
    except Exception as exc:  # noqa: BLE001
        return {"k": grid[len(grid) // 2], "grid_crps": {}, "n_fit": 0, "error": str(exc)}
    scorable = [o for o in fit_opps if o.n_prior >= MIN_PRIOR_STARTS]
    if not scorable:
        return {"k": grid[len(grid) // 2], "grid_crps": {}, "n_fit": 0}
    disp = dispersion_for(stat_key)
    grid_crps: Dict[float, float] = {}
    for k in grid:
        total = 0.0
        for o in scorable:
            lam = max(shrink_rate(o.player_rate, o.n_prior, o.league_rate, k) * o.e_bf, 0.0)
            total += crps_discrete(lam, disp, o.y)
        grid_crps[k] = total / len(scorable)
    best_k = min(grid_crps, key=lambda kk: (round(grid_crps[kk], 6), kk))
    return {"k": best_k, "grid_crps": {str(k): round(v, 5) for k, v in grid_crps.items()},
            "n_fit": len(scorable)}
