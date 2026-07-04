"""LANE 4 -- PROPS BASELINE SHOOTOUT #2 (queue item 4): the leak-free
walk-forward opportunity builder producing all 4 family lam candidates per
identified SP start. Split out from props_eval_shootout2_mlb.py to respect the
300 LOC cap (mirrors the props_eval_gate_mlb.py / _dist.py split from LANE 3).

Family (d) prev_season's state machine (_PrevSeasonState) lives here rather
than in props_eval_shootout2_mlb_families.py because it depends on
MIN_PRIOR_STARTS + shrink_rate + season-boundary bookkeeping that is specific
to the opportunity-building walk-forward, not the family-definition module.

PURE pandas/numpy/stdlib; no src/kernel/api imports. ASCII only.
Per-file test only: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_props_eval_shootout2_mlb.py -q
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import pandas as pd

from domains.mlb.props_eval_gate_mlb_constants import CORPORA, PROPS
from domains.mlb.props_eval_gate_mlb_dist import (
    MIN_PRIOR_STARTS,
    _corpus_label,
    _expected_bf_snapshot,
    _identify_start_opportunities,
)
from domains.mlb.props_eval_shootout2_mlb_families import (
    EW_ALPHA,
    _LeagueRateState,
    _RateState,
    shrink_rate,
)


class _PrevSeasonState:
    """Family (d): season-anchored rate tracker. On the FIRST start of a new
    season for this pitcher, if a prior-season snapshot exists, the state is
    re-anchored to that prior season's rate shrunk toward league (same k as
    family b) instead of starting blank; then updates cumulatively
    (alpha=0-style) through the season exactly like season_mean. Cross-season
    reset happens strictly BEFORE the new season's first snapshot is read, so
    it is leak-free (only ever uses the pitcher's OWN season(s) strictly prior
    to the opportunity being scored)."""

    __slots__ = ("_k", "_season", "_season_rate", "_season_n", "_prior_season_rate")

    def __init__(self, k: float) -> None:
        self._k = k
        self._season: Optional[int] = None
        self._season_rate: Optional[float] = None
        self._season_n = 0
        self._prior_season_rate: Optional[float] = None

    def _maybe_roll_season(self, year: int) -> None:
        if self._season is None:
            self._season = year
            return
        if year != self._season:
            # season boundary crossed: bank the just-finished season's rate as
            # the prior-season anchor, then reset counters for the new season.
            if self._season_n > 0:
                self._prior_season_rate = self._season_rate
            self._season = year
            self._season_n = 0
            self._season_rate = None

    def snapshot(self, year: int, league_rate: Optional[float]) -> Tuple[Optional[float], int]:
        self._maybe_roll_season(year)
        if self._season_n >= MIN_PRIOR_STARTS and self._season_rate is not None:
            return self._season_rate, self._season_n
        if self._season_n == 0 and self._prior_season_rate is not None:
            # no starts yet THIS season -> anchor on last season's shrunk rate.
            anchored = shrink_rate(self._prior_season_rate, 1, league_rate, self._k)
            return anchored, 0
        return None, self._season_n

    def update(self, per_bf_rate: float) -> None:
        if self._season_rate is None:
            self._season_rate = per_bf_rate
        else:
            total = self._season_rate * self._season_n + per_bf_rate
            self._season_rate = total / (self._season_n + 1)
        self._season_n += 1


def build_shootout_opportunities(gamelogs_df: pd.DataFrame, probables_df: pd.DataFrame,
                                   stat_key: str, k: float,
                                   corpora: Dict[str, Tuple[int, int]] = CORPORA
                                   ) -> List[Dict[str, object]]:
    """Leak-free walk-forward pass producing all 4 family lam candidates per
    identified SP start, plus realized y and corpus label. Shares exposure
    (_expected_bf_snapshot) and corpus labelling (_corpus_label) with LANE 3
    exactly; only the rate projections differ."""
    col = PROPS.get(stat_key)
    if col is None:
        raise KeyError(f"unknown stat_key {stat_key!r}, expected one of {list(PROPS)}")
    opp = _identify_start_opportunities(gamelogs_df, probables_df)
    if len(opp) == 0:
        return []
    opp = opp.copy()
    opp["_d"] = pd.to_datetime(opp["date"])
    opp = opp.sort_values(["_d", "game_pk", "player_id"], kind="mergesort").reset_index(drop=True)

    season_states: Dict[int, _RateState] = {}
    ew_states: Dict[int, _RateState] = {}
    prev_states: Dict[int, _PrevSeasonState] = {}
    league_state = _LeagueRateState()
    bf_hist: Dict[int, List[float]] = {}

    out: List[Dict[str, object]] = []
    for _, row in opp.iterrows():
        pid = int(row["player_id"])
        bf = float(row["battersFaced"])
        y_raw = row.get(col)
        y = float(y_raw) if y_raw is not None and not (isinstance(y_raw, float) and math.isnan(y_raw)) else None
        if y is None:
            continue
        corpus = _corpus_label(row["_d"], corpora)
        if corpus is None:
            continue
        year = int(row["_d"].year)

        sm_state = season_states.setdefault(pid, _RateState(0.0))
        ew_state = ew_states.setdefault(pid, _RateState(EW_ALPHA))
        pv_state = prev_states.setdefault(pid, _PrevSeasonState(k))

        sm_rate, n_prior = sm_state.snapshot()
        ew_rate, _ = ew_state.snapshot()
        l_rate = league_state.snapshot()
        pv_rate, _ = pv_state.snapshot(year, l_rate)
        sh_rate = shrink_rate(sm_rate, n_prior, l_rate, k)
        e_bf = _expected_bf_snapshot(bf_hist.get(pid, []))

        def _lam(rate: Optional[float]) -> float:
            return rate * e_bf if rate is not None else float("nan")

        out.append({
            "game_pk": int(row["game_pk"]), "player_id": pid, "date": str(row["date"]),
            "corpus": corpus, "y": y, "n_prior_starts": n_prior,
            "lam_season_mean": _lam(sm_rate),
            "lam_league_shrunk": _lam(sh_rate),
            "lam_ew_alpha": _lam(ew_rate),
            "lam_prev_season": _lam(pv_rate),
        })

        per_bf_rate = y / bf if bf > 1e-9 else 0.0
        sm_state.update(per_bf_rate)
        ew_state.update(per_bf_rate)
        pv_state.update(per_bf_rate)
        league_state.update(y, bf)
        bf_hist.setdefault(pid, []).append(bf)
    return out
