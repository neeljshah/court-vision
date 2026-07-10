"""domains.basketball_nba.sim2.cond_clutch -- v4 conditioning seam: a strictly
PRIOR-GAMES clutch-lineup-shortening propensity, scoped to Q4 only, for the sim2
possession model. Built because the full-game 12-attr composite (cond_composite,
"v3") REGRESSED the named P4|m2 bucket (0.1292->0.1403, nba_sim2_v3_validation.json)
while helping the two unrelated buckets (P3|m3, P2|m1). Mechanisms behind this:

  #24 "Clutch lineup shortening" (CONFIRMED, mechanisms.md): clutch distinct-player
      count 3.05 vs full-game (>=5min) rotation size 9.39, n=1052 team-games.
  #18 "Clutch usage compression" (CONFIRMED, REVERSED to amplification): remaining
      players see a LARGER shot-usage share late (hero-ball, slope=1.673), not less.

SIGNAL (new, not the composite, not player-identity-based): per (team, season), the
as-of (strictly-PRIOR-GAMES, leak-free) expanding mean of a team's own
(full-game distinct-rotation-size MINUS Q4<=3min-window distinct-rotation-size),
shrunk toward the prior-season/league mean with the SAME k=5 recipe as
corpus.asof_series. Data source: the team_system stints_{season}.parquet files
cond_composite already reads -- no new corpus, no player-composite dependency.
"Clutch window" reuses possession_model.time_bucket's own Q4<=3min boundary
(bucket 4) rather than inventing a new cutoff.

SCOPE (the one new mechanic vs cond_composite.ConditionedPointModel): the fitted
point-CDF matrix is IDENTICAL to v2 for every cell outside time_b in TIME_SCOPE
(Q4>3min, Q4<=3min) -- built once at fit time, so the UNCHANGED
simulator.simulate() (same comp_home/comp_thr protocol as v3) reproduces v2
exactly there; only Q4 cells can differ.

LEAK-FREE: shortening index skips (does not fill with 0) team-games that never
reached the Q4<=3min window when updating history -- an undefined observation,
not "no shortening". Thresholds for the offense-relative bin are fit on FIT
seasons only (reuses cond_composite.build_comp_thresholds unchanged).

INVARIANTS: domains-only; <=300 LOC; ASCII; reuses possession_model + cond_composite
generic helpers; no src/kernel imports. edge_claimed:false.
Tests: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/sim2/test_cond_clutch.py -q
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from domains.basketball_nba.composition.lineup_quality_conditioner import _LINEUPS_DIR
from domains.basketball_nba.lineups.pbp_lineups import _period_length_s
from domains.basketball_nba.sim2.cond_composite import (
    N_COMP, _SEASON_TAG, _home_team_ids, offrel_values, build_comp_thresholds,
    comp_bin, attach_comp_bin)
from domains.basketball_nba.sim2.corpus import GAMES, SHRINK_K
from domains.basketball_nba.sim2.possession_model import (
    N_CELLS, N_MARGIN, PMAX, MIN_CELL, cell_index, time_bucket, PossessionModel)

TIME_SCOPE = (3, 4)          # Q4>3min, Q4<=3min -- the P4|m2 hypothesis's own scope
_TIME_DIVISOR = N_MARGIN * 3 * 3 * 3    # recovers time_b from a flat base cell index


def _ids(lineup_key: str) -> set:
    return set(int(x) for x in str(lineup_key).split(","))


def _team_game_rotation(st: pd.DataFrame) -> pd.DataFrame:
    """One row per (game_id,team_id): full_size (distinct players, whole game) and
    clutch_size (distinct players, Q4<=3min window only; NaN if never reached)."""
    st = st[st["n_on_court"] == 5].copy()
    full = st.groupby(["game_id", "team_id"])["lineup_key"].apply(
        lambda ks: len(set().union(*(_ids(k) for k in ks)))).rename("full_size")
    clock_rem = st["period"].map(_period_length_s) - st["start_s"]
    tb = [time_bucket(int(p), float(c)) for p, c in zip(st["period"], clock_rem)]
    clutch = st[np.array(tb) == 4].groupby(["game_id", "team_id"])["lineup_key"].apply(
        lambda ks: len(set().union(*(_ids(k) for k in ks)))).rename("clutch_size")
    return pd.concat([full, clutch], axis=1).reset_index()


def _asof_skipnan(vals: List[Optional[float]], base: float, k: float) -> List[float]:
    """Leak-free expanding as-of shrink toward `base` (corpus.asof_series recipe),
    SKIPPING undefined (NaN) games when updating history -- a blowout that never
    reached the clutch window tells us nothing about the tendency -- while still
    emitting a value for every game (as-of the games seen so far)."""
    out: List[float] = []
    hist: List[float] = []
    for v in vals:
        n = len(hist)
        emean = float(np.mean(hist)) if n else base
        out.append(emean if (n + k) == 0 else (n * emean + k * base) / (n + k))
        if v is not None and not (isinstance(v, float) and np.isnan(v)):
            hist.append(float(v))
    return out


def all_game_shortening_diff(seasons=("2023-24", "2024-25", "2025-26")) -> Dict[str, float]:
    """{game_id: home_asof_shortening - away_asof_shortening}, offense-relative-
    ready (sign applied later by offrel_values, same as the composite). A team
    with zero games so far this season falls back to its prior-season mean, else
    the league mean -- never NaN, never the current game's own outcome."""
    rows = []
    for s in seasons:
        fp = _LINEUPS_DIR / f"stints_{_SEASON_TAG.get(s, s)}.parquet"
        if not fp.exists():
            continue
        tg = _team_game_rotation(pd.read_parquet(fp))
        tg["season"] = s
        rows.append(tg)
    if not rows:
        return {}
    tg = pd.concat(rows, ignore_index=True)
    tg["game_id"] = tg["game_id"].astype(str)
    tg["shortening"] = tg["full_size"] - tg["clutch_size"]
    games = pd.read_parquet(GAMES)[["game_id", "date"]]
    games["game_id"] = games["game_id"].astype(str)
    date_by = dict(zip(games["game_id"], pd.to_datetime(games["date"])))
    tg["date"] = tg["game_id"].map(date_by)
    tg = tg.dropna(subset=["date"]).sort_values("date")
    league_mean = float(tg["shortening"].mean())
    seas_order = sorted(seasons)
    prev_season = {s: (seas_order[i - 1] if i > 0 else None) for i, s in enumerate(seas_order)}
    prior_mean = tg.groupby(["season", "team_id"])["shortening"].mean().to_dict()
    asof: Dict[Tuple[str, int], float] = {}
    for (team_id, season), grp in tg.groupby(["team_id", "season"]):
        grp = grp.sort_values("date")
        ps = prev_season.get(season)
        base = prior_mean.get((ps, team_id), league_mean) if ps else league_mean
        if base is None or (isinstance(base, float) and np.isnan(base)):
            base = league_mean
        for gid, v in zip(grp["game_id"], _asof_skipnan(list(grp["shortening"]), base, SHRINK_K)):
            asof[(gid, team_id)] = v
    home_ids = _home_team_ids(tg["game_id"].unique())
    diff: Dict[str, float] = {}
    for gid, gg in tg.groupby("game_id"):
        hid = home_ids.get(str(gid))
        team_ids = list(gg["team_id"].unique())
        if hid is None or hid not in team_ids or len(team_ids) != 2:
            continue
        aid = [t for t in team_ids if t != hid][0]
        hv, av = asof.get((gid, hid)), asof.get((gid, aid))
        if hv is None or av is None:
            continue
        diff[str(gid)] = hv - av
    return diff


class ScopedConditionedModel:
    """Empirical P(points | state, comp_b) IDENTICAL to v2 outside `time_buckets`;
    conditioned (with backoff to the unconditioned v2 cell) inside. Same
    [N_CELLS*N_COMP, PMAX+1] shape/protocol as cond_composite.ConditionedPointModel
    so the UNCHANGED simulator.simulate(comp_home=, comp_thr=) reuses it verbatim."""

    def __init__(self, cdf: np.ndarray, thr: List[float], time_buckets: Tuple[int, ...],
                 n_full: int, n_backoff: int, n_out_of_scope: int):
        self.cdf = cdf
        self.thr = list(thr)
        self.time_buckets = tuple(time_buckets)
        self.n_full6 = n_full
        self.n_backoff_v2 = n_backoff
        self.n_out_of_scope = n_out_of_scope

    @classmethod
    def fit(cls, fit_poss: pd.DataFrame, v2: PossessionModel, gcd: Dict[str, float],
            thr: List[float], time_buckets: Tuple[int, ...] = TIME_SCOPE) -> "ScopedConditionedModel":
        df = attach_comp_bin(fit_poss, gcd, thr)
        in_scope = df["time_b"].isin(time_buckets).to_numpy()
        pts = df["points"].to_numpy()
        base = cell_index(df["time_b"].to_numpy(), df["margin_b"].to_numpy(),
                          df["off_t"].to_numpy(), df["def_t"].to_numpy(), df["pace_t"].to_numpy())
        comp_b = np.where(in_scope, df["comp_b"].to_numpy(), 1)   # neutral bin outside scope
        comb = base * N_COMP + comp_b
        order = np.argsort(comb)
        comb_s, pts_s = comb[order], pts[order]
        bounds = np.searchsorted(comb_s, np.arange(N_CELLS * N_COMP + 1))
        v2_pmf = np.diff(v2.cdf, axis=1, prepend=0.0)
        pmf = np.zeros((N_CELLS * N_COMP, PMAX + 1))
        n_full = n_back = n_out = 0
        for c in range(N_CELLS * N_COMP):
            base_c = c // N_COMP
            if (base_c // _TIME_DIVISOR) not in time_buckets:
                pmf[c] = v2_pmf[base_c]; n_out += 1
                continue
            lo, hi = bounds[c], bounds[c + 1]
            if hi - lo >= MIN_CELL:
                pmf[c] = PossessionModel._pmf(pts_s[lo:hi]); n_full += 1
            else:
                pmf[c] = v2_pmf[base_c]; n_back += 1
        cdf = np.cumsum(pmf, axis=1)
        cdf[:, -1] = 1.0
        return cls(cdf, thr, time_buckets, n_full, n_back, n_out)

    def point_cdf_matrix(self) -> np.ndarray:
        return self.cdf

    def summary(self) -> Dict[str, Any]:
        return {"n_cells": N_CELLS * N_COMP, "n_comp": N_COMP,
                "time_scope": list(self.time_buckets),
                "n_full_conditioned": self.n_full6, "n_backoff_v2": self.n_backoff_v2,
                "n_out_of_scope_passthrough": self.n_out_of_scope,
                "comp_thresholds": [round(t, 4) for t in self.thr], "min_cell": MIN_CELL}


__all__ = ["TIME_SCOPE", "all_game_shortening_diff", "ScopedConditionedModel",
           "offrel_values", "build_comp_thresholds", "comp_bin"]
