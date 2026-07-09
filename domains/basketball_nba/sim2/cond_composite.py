"""domains.basketball_nba.sim2.cond_composite -- v3 conditioning seam: feed the
REPLICATED 12-attribute lineup-quality composite (be9715a9) into the sim2
possession-outcome model as a 6th cell dimension.

HYPOTHESIS (distributional, not $): the composite adds ~nothing at the game
margin AGGREGATE (its own gate stayed SCOUTING), but MIGHT sharpen the
possession-level point distribution for lineup-quality MISMATCHES -- i.e. when a
strong-composite offense faces a weak-composite defense, the empirical PMF over
points-per-possession shifts beyond what the off/def/pace terciles already carry.

DESIGN (minimal, architecture-matched):
  * Per game, compute comp_home_minus_away = the minutes-weighted home lineup
    composite minus the away lineup composite, using STRICT PRIOR-SEASON
    profiles (2025-26<-2024-25, 2024-25<-2023-24; 2023-24 EXCLUDED -> neutral).
    Reuses the validated composition (load_player_composite / build_segments);
    it is NOT reimplemented here.
  * Enter it OFFENSE-RELATIVE per possession exactly like off_margin/terciles:
    a home-offense possession sees +D, an away-offense possession -D. Bin into 3
    (comp_b) by fit-season terciles of the offense-relative value.
  * Conditioned cell = base_5dim_cell * 3 + comp_b (N_CELLS*3 cells). BACKOFF:
    a conditioned cell with < MIN_CELL possessions falls back to the UNCONDITIONED
    v2 cell PMF -> worst case v3 == v2 (an honest null, never worse).

LEAK-FREE: composite uses prior-season profiles only; 2023-24 (no prior) -> comp_b=1
neutral, documented (not a silent fill). Terciles fit on 2024-25 (the only
conditioned fit season), applied unchanged to the test season.

INVARIANTS: domains-only; <=300 LOC; ASCII; reuses possession_model + conditioner;
no src/kernel imports. edge_claimed:false.
Tests: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/sim2/test_cond_composite.py -q
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from domains.basketball_nba.sim2.possession_model import (
    N_CELLS, PMAX, MIN_CELL, cell_index, PossessionModel)
from domains.basketball_nba.composition.lineup_quality_conditioner import (
    load_player_composite, build_segments, _lineup_comp, PRIOR_WINDOW, _LINEUPS_DIR)

N_COMP = 3
# season_tag (composition convention) <-> sim2 season string (corpus convention)
_SEASON_TAG = {"2023-24": "2023_24", "2024-25": "2024_25", "2025-26": "2025_26"}


def _home_team_ids(game_ids) -> Dict[str, int]:
    """game_id -> home team_id (numeric). Uses the offline nba_api static tricode
    crosswalk + games.parquet home tricode. No network."""
    from nba_api.stats.static import teams as _t
    from domains.basketball_nba.sim2.corpus import GAMES
    tri2id = {v["abbreviation"]: v["id"] for v in _t.get_teams()}
    g = pd.read_parquet(GAMES)[["game_id", "home_team"]]
    g["game_id"] = g["game_id"].astype(str)
    home = dict(zip(g["game_id"], g["home_team"]))
    out: Dict[str, int] = {}
    for gid in set(str(x) for x in game_ids):
        tid = tri2id.get(home.get(gid))
        if tid is not None:
            out[gid] = int(tid)
    return out


def game_comp_diff(season_tag: str) -> Dict[str, float]:
    """{game_id: comp_home_minus_away} for one season, minutes-weighted per team,
    prior-season profiles. {} for an excluded season (no prior window)."""
    prior = PRIOR_WINDOW.get(season_tag)
    if prior is None:
        return {}
    comp, _cov = load_player_composite(prior)
    if not comp:
        return {}
    st = pd.read_parquet(_LINEUPS_DIR / f"stints_{season_tag}.parquet")
    st["game_id"] = st["game_id"].astype(str)
    seg = build_segments(st)
    if seg.empty:
        return {}
    seg["ca"] = seg["lineup_key_a"].map(lambda k: _lineup_comp(k, comp))
    seg["cb"] = seg["lineup_key_b"].map(lambda k: _lineup_comp(k, comp))
    home_id = _home_team_ids(seg["game_id"].unique())
    from nba_api.stats.static import teams as _t
    id_ok = {v["id"] for v in _t.get_teams()}
    out: Dict[str, float] = {}
    for gid, gg in seg.groupby("game_id"):
        hid = home_id.get(str(gid))
        if hid is None:
            continue
        w = gg["overlap_s"].to_numpy()
        if w.sum() <= 0:
            continue
        ca = float((gg["ca"] * gg["overlap_s"]).sum() / w.sum())
        cb = float((gg["cb"] * gg["overlap_s"]).sum() / w.sum())
        ta = int(gg["team_id_a"].iloc[0])
        a_is_home = (ta == hid)
        comp_home, comp_away = (ca, cb) if a_is_home else (cb, ca)
        # sanity: home id must be one of the two real team ids in the game
        if hid not in (int(gg["team_id_a"].iloc[0]), int(gg["team_id_b"].iloc[0])):
            if hid in id_ok:  # crosswalk fine but game pairing odd -> skip
                continue
        out[str(gid)] = comp_home - comp_away
    return out


def all_game_comp_diff(seasons) -> Dict[str, float]:
    """Merge per-season game_comp_diff over the given sim2 season strings."""
    merged: Dict[str, float] = {}
    for s in seasons:
        merged.update(game_comp_diff(_SEASON_TAG.get(s, s)))
    return merged


def offrel_values(poss: pd.DataFrame, gcd: Dict[str, float]) -> np.ndarray:
    """Offense-relative composite value per possession: +D if home on offense,
    -D if away; 0.0 (neutral) if the game has no composite (e.g. 2023-24)."""
    d = poss["game_id"].astype(str).map(gcd).fillna(0.0).to_numpy(dtype=float)
    sign = np.where(poss["off_is_home"].to_numpy(), 1.0, -1.0)
    return d * sign


def build_comp_thresholds(fit_poss: pd.DataFrame, gcd: Dict[str, float]) -> List[float]:
    """Terciles of the offense-relative composite over fit possessions that HAVE a
    composite (games in gcd only) -> [lo, hi]. Falls back to symmetric zeros if
    too few, which collapses v3 to the neutral bin (==v2)."""
    have = fit_poss["game_id"].astype(str).isin(gcd.keys()).to_numpy()
    v = offrel_values(fit_poss, gcd)[have]
    if len(v) < 100:
        return [0.0, 0.0]
    return [float(np.quantile(v, 1 / 3)), float(np.quantile(v, 2 / 3))]


def comp_bin(offrel: np.ndarray, thr: List[float]) -> np.ndarray:
    """0/1/2 by the two tercile edges (side='right' matches searchsorted convention)."""
    return np.searchsorted(np.asarray(thr), offrel, side="right").astype(np.intp)


def attach_comp_bin(poss: pd.DataFrame, gcd: Dict[str, float], thr: List[float]) -> pd.DataFrame:
    """Add integer 'comp_b' (0..2) to a possession frame."""
    poss = poss.copy()
    poss["comp_b"] = comp_bin(offrel_values(poss, gcd), thr)
    return poss


class ConditionedPointModel:
    """Empirical P(points | state, comp_b) with BACKOFF to the unconditioned v2
    cell PMF for thin conditioned cells. cdf is [N_CELLS*N_COMP, PMAX+1]."""

    def __init__(self, cdf: np.ndarray, thr: List[float], n_full6: int, n_backoff_v2: int):
        self.cdf = cdf
        self.thr = list(thr)
        self.n_full6 = n_full6
        self.n_backoff_v2 = n_backoff_v2

    @classmethod
    def fit(cls, fit_poss: pd.DataFrame, v2: PossessionModel, gcd: Dict[str, float],
            thr: List[float]) -> "ConditionedPointModel":
        df = attach_comp_bin(fit_poss, gcd, thr)
        pts = df["points"].to_numpy()
        base = cell_index(df["time_b"].to_numpy(), df["margin_b"].to_numpy(),
                          df["off_t"].to_numpy(), df["def_t"].to_numpy(),
                          df["pace_t"].to_numpy())
        comb = base * N_COMP + df["comp_b"].to_numpy()
        order = np.argsort(comb)
        comb_s, pts_s = comb[order], pts[order]
        bounds = np.searchsorted(comb_s, np.arange(N_CELLS * N_COMP + 1))
        v2_pmf = np.diff(v2.cdf, axis=1, prepend=0.0)      # inclusive CDF -> PMF
        pmf = np.zeros((N_CELLS * N_COMP, PMAX + 1))
        n_full = n_back = 0
        for c in range(N_CELLS * N_COMP):
            lo, hi = bounds[c], bounds[c + 1]
            if hi - lo >= MIN_CELL:
                pmf[c] = PossessionModel._pmf(pts_s[lo:hi]); n_full += 1
            else:
                pmf[c] = v2_pmf[c // N_COMP]; n_back += 1     # backoff to unconditioned cell
        cdf = np.cumsum(pmf, axis=1)
        cdf[:, -1] = 1.0
        return cls(cdf, thr, n_full, n_back)

    def point_cdf_matrix(self) -> np.ndarray:
        return self.cdf

    def summary(self) -> Dict[str, Any]:
        return {"n_cells": N_CELLS * N_COMP, "n_comp": N_COMP,
                "n_full_conditioned": self.n_full6, "n_backoff_v2": self.n_backoff_v2,
                "comp_thresholds": [round(t, 4) for t in self.thr], "min_cell": MIN_CELL}


__all__ = ["N_COMP", "game_comp_diff", "all_game_comp_diff", "offrel_values",
           "build_comp_thresholds", "comp_bin", "attach_comp_bin", "ConditionedPointModel"]
