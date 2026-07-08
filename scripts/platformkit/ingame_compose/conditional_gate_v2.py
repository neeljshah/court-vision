"""conditional_gate_v2 -- does LIVE-STATE (who is on the floor, foul trouble,
in-game shooting luck, bench usage) improve checkpoint win probability BEYOND
score+Elo? v1 (conditional_gate.py) showed the box-derived PREGAME prior adds
nothing once you condition on score+Elo -- Elo already knows team strength on
average. v2 tests what Elo definitionally CANNOT carry: which specific players
are out there right now, in THIS game.

Same base and gate discipline as v1 (base = intercept + score_diff_z on the
Elo offset; walk-forward; DM p; truncation-80) -- see conditional_gate.py's
docstring for the score_diff*sqrt(trf) collinearity note, unchanged here.
v2's only difference is the candidate ladder: 4 preregistered feature diffs
(livestate_ingame.compute_v2_features), added ONE AT A TIME, cumulative:

  rung0 base
  rung1 base + floor_quality_now
  rung2 rung1 + star_minutes_load
  rung3 rung2 + shooting_luck_so_far
  rung4 rung3 + bench_depth_used

All 4 features (or none) are required per game/checkpoint -- a game missing
any one is dropped from EVERY rung so all 5 rungs score the identical sample
(deltas are attributable to the added feature, not a changed test set).

Ledger method 'ingame_livestate_v2_walkforward'.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.compose.challenger import _base_logit_nba
from scripts.platformkit.compose.team_form import team_id_to_abbr
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.ingame_compose.checkpoints import (
    CHECKPOINTS,
    extract_checkpoints,
    final_home_margin,
)
from scripts.platformkit.ingame_compose.livestate_ingame import (
    FEATURE_NAMES,
    add_global_times,
    compute_v2_features,
)
from scripts.platformkit.ingame_compose.livestate_priors import (
    build_league_shot_rate_table,
    build_player_net48_asof,
    build_top3_fga_table,
    league_shot_rates_asof,
    top3_fga_by_team,
)
from scripts.platformkit.intel_weighting.relevance_gate import (
    _DM_ALPHA,
    _MIN_TEST,
    _TRAIN_FRAC,
    _brier,
    _fit,
    _sigmoid,
)

METHOD = "ingame_livestate_v2_walkforward"
_RUNGS = ["base"] + FEATURE_NAMES   # base, +floor_quality_now, +star_minutes_load, ...
_REPO = Path(__file__).resolve().parents[3]
_STINTS = _REPO / "data" / "cache" / "team_system" / "lineups" / "stints_2025_26.parquet"
_BOX = _REPO / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
_GAMES = _REPO / "data" / "domains" / "basketball_nba" / "games.parquet"
_PBP = _REPO / "data" / "cache" / "team_system" / "pbp"


@dataclass
class RungResult:
    checkpoint: str
    rung: str                        # cumulative feature set label
    n_games: int
    n_test: int
    brier_base: float
    brier_cond: float
    delta: float
    delta_trunc80: float
    dm_p: float
    verdict: str
    betas: Dict[str, float] = field(default_factory=dict)
    caveats: List[str] = field(default_factory=list)


def _standardize_cols(df: pd.DataFrame, cols: List[str], tr: slice) -> Dict[str, np.ndarray]:
    """z-score each column on the TRAIN prefix only (mirrors compose._standardize
    but for an arbitrary column list rather than the fixed 4-col prior schema)."""
    out = {}
    for c in cols:
        v = df[c].to_numpy(dtype=float)
        mu, sd = v[tr].mean(), v[tr].std()
        out[c] = (v - mu) / sd if sd > 1e-12 else v - mu
    return out


def score_rung(rung: str, feat_cols: List[str], elo_logit: np.ndarray,
              score_diff: np.ndarray, feats: pd.DataFrame,
              y: np.ndarray, gid: np.ndarray, checkpoint: str) -> RungResult:
    """base = intercept + score_diff_z; candidate = base + feat_cols (cumulative
    prefix of FEATURE_NAMES). Identical fit/score/DM machinery as v1's
    score_checkpoint, generalized to an arbitrary feature-column list."""
    n = len(y)
    n_tr, n_te = int(n * _TRAIN_FRAC), n - int(n * _TRAIN_FRAC)
    if n_te < _MIN_TEST:
        return RungResult(checkpoint, rung, n, n_te, 0.0, 0.0, 0.0, 0.0, 1.0,
                          "UNTESTABLE", {}, [f"only {n_te} OOS games"])
    tr, te = slice(0, n_tr), slice(n_tr, n)

    z_score = _standardize_cols(pd.DataFrame({"score": score_diff}), ["score"], tr)["score"]
    ones_tr, ones_te = np.ones((n_tr, 1)), np.ones((n_te, 1))
    yb = y[te]

    base_tr = np.column_stack([ones_tr, z_score[tr]])
    base_te = np.column_stack([ones_te, z_score[te]])
    th_base = _fit(elo_logit[tr], base_tr, y[tr])
    p_base = _sigmoid(elo_logit[te] + base_te @ th_base)

    if feat_cols:
        z_feats = _standardize_cols(feats, feat_cols, tr)
        cand_tr = np.column_stack([base_tr] + [z_feats[c][tr] for c in feat_cols])
        cand_te = np.column_stack([base_te] + [z_feats[c][te] for c in feat_cols])
    else:
        cand_tr, cand_te = base_tr, base_te
    th_cand = _fit(elo_logit[tr], cand_tr, y[tr])
    p_cond = _sigmoid(elo_logit[te] + cand_te @ th_cand)

    brier_base, brier_cond = _brier(p_base, yb), _brier(p_cond, yb)
    delta = brier_base - brier_cond
    d = (p_base - yb) ** 2 - (p_cond - yb) ** 2
    dm_p = diebold_mariano(d, gid[te]).p_value
    cut = int(n_te * 0.8)
    delta_t80 = _brier(p_base[:cut], yb[:cut]) - _brier(p_cond[:cut], yb[:cut])

    betas = {c: round(float(b), 4) for c, b in zip(feat_cols, th_cand[2:])}
    if delta > 0 and dm_p < _DM_ALPHA and delta_t80 > 0:
        verdict = "MATTERS_PROVISIONAL"
        caveats = ["single-fold, one season, 4 checkpoints x a 4-rung ladder: "
                   "expected chance hits are non-trivial; stays PROVISIONAL "
                   "until replicated on an independent season/corpus"]
    else:
        verdict = "NULL"
        caveats = []
    return RungResult(checkpoint, rung, n, n_te, round(brier_base, 6), round(brier_cond, 6),
                      round(delta, 6), round(delta_t80, 6), round(dm_p, 4), verdict,
                      betas, caveats)


def _load_v2_states(season: str = "2025-26"):
    """(games, states_by_game, elo_by_game, skips) where states_by_game[gid][cid]
    is the (score_diff, floor_quality, star_minutes, luck, bench) tuple or None."""
    games = pd.read_parquet(_GAMES)
    games["date"] = pd.to_datetime(games["date"])
    ev = games[games["season"].astype(str) == season].sort_values(["date", "game_id"]).reset_index(drop=True)
    abbr = team_id_to_abbr()
    id_by_abbr = {v: k for k, v in abbr.items()}

    stints_all = add_global_times(pd.read_parquet(_STINTS))
    # net48 is as-of PER GAME (a player's rolling rating moves game to game) --
    # index is (game_id, player_id); group into one {player_id: net48} dict per
    # game_id so compute_v2_features gets a plain player_id-keyed lookup for
    # the specific game it is scoring, not one global (stale) snapshot.
    net_df = build_player_net48_asof().reset_index()
    net_df.columns = ["game_id", "player_id", "net48"]
    net48_by_game: Dict[str, Dict[int, float]] = {
        g: dict(zip(d["player_id"], d["net48"])) for g, d in net_df.groupby("game_id")}
    top3_table = build_top3_fga_table()
    rate_table = build_league_shot_rate_table()

    games_all, base_logit_all = _base_logit_nba()
    idx = games_all.reset_index().set_index("game_id")["index"]

    states: Dict[str, Dict[str, object]] = {}
    elo_by_game: Dict[str, float] = {}
    skips = {"no_pbp": 0, "orientation_flip": 0, "no_elo": 0, "no_stints": 0}

    for r in ev.itertuples(index=False):
        gid = str(r.game_id)
        fp = _PBP / f"{gid}.json"
        if not fp.exists():
            skips["no_pbp"] += 1
            continue
        if gid not in idx.index:
            skips["no_elo"] += 1
            continue
        elo_by_game[gid] = float(base_logit_all[int(idx[gid])])

        gj = json.loads(fp.read_text(encoding="utf-8"))
        fm = final_home_margin(gj)
        if fm is not None and fm != 0 and (fm > 0) != (r.home_win > 0.5):
            skips["orientation_flip"] += 1
            continue

        gstints = stints_all[stints_all["game_id"] == gid]
        if gstints.empty:
            skips["no_stints"] += 1
            continue
        home_id, away_id = id_by_abbr.get(r.home_team), id_by_abbr.get(r.away_team)
        top3_h = top3_fga_by_team(top3_table, r.home_team, r.date)
        top3_a = top3_fga_by_team(top3_table, r.away_team, r.date)
        rates = league_shot_rates_asof(rate_table, r.date)
        net48_this_game = net48_by_game.get(gid, {})

        cps = extract_checkpoints(gj)
        row: Dict[str, object] = {}
        for cid, t, _trf in CHECKPOINTS:
            cp = cps.get(cid)
            if cp is None:
                row[cid] = None
                continue
            feats = compute_v2_features(gj, gstints, t, home_id, away_id, net48_this_game,
                                        top3_h, top3_a, rates)
            row[cid] = None if feats is None else (cp.score_diff, *feats)
        states[gid] = row
    return ev, states, elo_by_game, skips


def run_all_rungs(season: str = "2025-26"
                  ) -> Tuple[List[RungResult], Dict[str, int], Dict[str, int]]:
    ev, states, elo, glob_skips = _load_v2_states(season)
    gids = ev["game_id"].astype(str).to_numpy()

    results: List[RungResult] = []
    cp_skips: Dict[str, int] = {}
    for cid, _t, _trf in CHECKPOINTS:
        rows = []
        skipped = 0
        for i, g in enumerate(gids):
            st = states.get(g, {}).get(cid) if g in states else None
            if st is None:
                skipped += 1
                continue
            rows.append((ev.iloc[i]["date"], g, float(ev.iloc[i]["home_win"]), elo[g], *st))
        cp_skips[cid] = skipped
        if not rows:
            for rung in _RUNGS:
                results.append(RungResult(cid, rung, 0, 0, 0.0, 0.0, 0.0, 0.0, 1.0,
                                          "UNTESTABLE", {}, ["no games"]))
            continue
        rows.sort(key=lambda x: x[0])
        y = np.array([r[2] for r in rows], dtype=float)
        gid_arr = np.array([r[1] for r in rows])
        elo_l = np.array([r[3] for r in rows], dtype=float)
        sdiff = np.array([r[4] for r in rows], dtype=float)
        feats = pd.DataFrame([r[5:] for r in rows], columns=FEATURE_NAMES)

        cum_cols: List[str] = []
        for rung, fname in zip(_RUNGS, [None] + FEATURE_NAMES):
            if fname is not None:
                cum_cols = cum_cols + [fname]
            results.append(score_rung(rung, cum_cols, elo_l, sdiff, feats, y, gid_arr, cid))
    return results, cp_skips, glob_skips


if __name__ == "__main__":  # pragma: no cover - smoke
    res, cps, gs = run_all_rungs()
    for r in res:
        print(f"{r.checkpoint:8s} {r.rung:22s} n={r.n_games:4d} te={r.n_test:4d} "
              f"base {r.brier_base:.5f} cond {r.brier_cond:.5f} d {r.delta:+.5f} "
              f"dm {r.dm_p:.4f} {r.verdict}")
    print("checkpoint skips", cps, "global skips", gs)
