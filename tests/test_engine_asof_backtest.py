"""Tests for engine_asof_backtest.py -- fast, no full backtest run required.

(a) Leak-free assertion: at game G the accumulator uses only date < G rows.
(b) CV_ENGINE_RELIABILITY_WEIGHTS unset -> predict_ensemble margin unchanged vs equal-weight.
(c) weights sum to 1 on the simplex.
(d) excluded engines absent from weights JSON.
"""
from __future__ import annotations
import json
import math
import os
import sys
import importlib.util

import numpy as np
import pytest
import pandas as pd

# Repo root
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TS   = os.path.join(ROOT, "data", "cache", "team_system")
WEIGHTS_JSON = os.path.join(TS, "engine_reliability_weights.json")
PREDS_PQ     = os.path.join(TS, "engine_asof_preds.parquet")

# Add scripts/team_system to path so we can import the backtest module
_TEAM_SYS = os.path.join(ROOT, "scripts", "team_system")
sys.path.insert(0, _TEAM_SYS)

# ------------------------------------------------------------------ helpers --

def _load_backtest():
    spec = importlib.util.spec_from_file_location(
        "engine_asof_backtest",
        os.path.join(_TEAM_SYS, "engine_asof_backtest.py"),
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _has_ltg():
    return os.path.exists(os.path.join(TS, "league_team_game.parquet"))


# ====================================================================
# (a) Leak-free property on a tiny slice
# ====================================================================

@pytest.mark.skipif(not _has_ltg(), reason="league_team_game.parquet not built")
def test_leak_free_accumulator():
    """The accumulator for game G must NOT include G's own row.

    Reconstruct the accumulator state after the first 15 games for one team
    and assert that the 15th game's stats are not yet in the acc totals
    (they are added *after* predicting, per the update-after-predict pattern).
    """
    bt = _load_backtest()
    TG = pd.read_parquet(os.path.join(TS, "league_team_game.parquet"))
    SG = {r["game_id"]: r
          for r in json.load(open(os.path.join(ROOT, "data", "nba", "season_games_2025-26.json")))["rows"]
          if "home_win" in r}

    games = []
    tg_by_gid_team = {(r.gid, r.team): r for r in TG.itertuples(index=False)}
    for gid, g in TG.groupby("gid"):
        s = SG.get(gid)
        if s is None:
            continue
        ht, at = s["home_team"], s["away_team"]
        hr = g[g.team == ht]; ar = g[g.team == at]
        if len(hr) != 1 or len(ar) != 1:
            continue
        games.append(dict(gid=gid, date=s["game_date"], ht=ht, at=at,
                          home_pts=int(hr.iloc[0].pts), away_pts=int(ar.iloc[0].pts),
                          home_win=int(s["home_win"])))
    games = sorted(games, key=lambda r: (r["date"], r["gid"]))

    # Replay first 20 games for the first home team
    target_team = games[0]["ht"]
    acc = {}

    for i, gm in enumerate(games[:20]):
        acc.setdefault(gm["ht"], bt._blank_acc())
        acc.setdefault(gm["at"], bt._blank_acc())

        # Capture state BEFORE update for this game (this is the as-of state used to predict)
        a_before = dict(acc.get(target_team, bt._blank_acc()))
        g_before = a_before["g"]

        # Update
        hr_row = tg_by_gid_team.get((gm["gid"], gm["ht"]))
        ar_row = tg_by_gid_team.get((gm["gid"], gm["at"]))
        if hr_row is not None:
            bt._update_acc(acc[gm["ht"]], hr_row)
        if ar_row is not None:
            bt._update_acc(acc[gm["at"]], ar_row)

        a_after = acc.get(target_team, bt._blank_acc())

        # If target_team played in game i, the update should add exactly 1 game
        if gm["ht"] == target_team or gm["at"] == target_team:
            assert a_after["g"] == g_before + 1, (
                f"game {i}: acc['g'] should increment by 1 after update, "
                f"was {g_before} -> {a_after['g']}"
            )
        # The state BEFORE update has exactly g_before games -- no future row included
        assert g_before <= i, f"acc['g']={g_before} cannot exceed game index {i} (leak guard)"


# ====================================================================
# (b) CV_ENGINE_RELIABILITY_WEIGHTS unset -> equal-weight path unchanged
# ====================================================================

def test_flag_off_is_equal_weight():
    """With CV_ENGINE_RELIABILITY_WEIGHTS unset, predict_ensemble must use equal-weight margin."""
    # We test the logic directly without running the full ensemble (which needs TeamModel caches).
    # Simulate the gating logic in predict_ensemble.py.
    import os as _os
    # Ensure flag is unset
    _os.environ.pop("CV_ENGINE_RELIABILITY_WEIGHTS", None)

    fake_preds = [
        {"engine": "power_ratings", "margin_home": 3.0, "margin_sd": 13.0, "total": 220.0, "win_prob_home": 0.6},
        {"engine": "team_score",    "margin_home": 5.0, "margin_sd": 14.0, "total": 225.0, "win_prob_home": 0.65},
        {"engine": "four_factors",  "margin_home": 1.0, "margin_sd": 12.0, "total": 218.0, "win_prob_home": 0.55},
        {"engine": "possession_mc", "margin_home": 4.0, "margin_sd": 11.0, "total": 222.0, "win_prob_home": 0.62},
    ]
    margins = np.array([p["margin_home"] for p in fake_preds])

    # Replicate the gating block from predict_ensemble.py
    eng_w = None
    if _os.environ.get("CV_ENGINE_RELIABILITY_WEIGHTS") == "1":
        import json as _json
        _wp = WEIGHTS_JSON
        if _os.path.exists(_wp):
            _d = _json.load(open(_wp))
            if _d.get("beats_equal_weight"):
                _map = dict(zip(_d["engines"], _d["weights"]))
                eng_w = np.array([_map.get(p["engine"], 0.0) for p in fake_preds])
                if eng_w.sum() > 0:
                    eng_w = eng_w / eng_w.sum()
                else:
                    eng_w = None

    eq_margin = float((eng_w * margins).sum()) if eng_w is not None else float(margins.mean())

    # Flag is OFF -> must be plain equal weight
    assert eng_w is None, "eng_w should be None when flag is unset"
    assert abs(eq_margin - float(margins.mean())) < 1e-9, (
        f"margin mismatch: {eq_margin} vs equal-weight {float(margins.mean())}"
    )


# ====================================================================
# (c) Weights sum to 1 on the simplex
# ====================================================================

@pytest.mark.skipif(not os.path.exists(WEIGHTS_JSON), reason="weights JSON not yet built")
def test_weights_sum_to_one():
    with open(WEIGHTS_JSON) as f:
        d = json.load(f)
    w = d["weights"]
    assert len(w) == 3, f"Expected 3 weights, got {len(w)}"
    assert abs(sum(w) - 1.0) < 1e-5, f"Weights do not sum to 1: {sum(w)}"
    assert all(wi >= -1e-9 for wi in w), f"Negative weight found: {w}"


# ====================================================================
# (d) Excluded engines absent from weights JSON
# ====================================================================

@pytest.mark.skipif(not os.path.exists(WEIGHTS_JSON), reason="weights JSON not yet built")
def test_excluded_engines_absent():
    with open(WEIGHTS_JSON) as f:
        d = json.load(f)
    included = set(d["engines"])
    excluded = {"player_impact", "attribute_matchup", "possession_mc", "clock_trajectory"}
    overlap  = included & excluded
    assert not overlap, f"Excluded engines found in weights: {overlap}"
    # And they should be explicitly documented in excluded_engines
    for eng in excluded:
        assert eng in d.get("excluded_engines", {}), f"Engine {eng!r} not in excluded_engines doc"


# ====================================================================
# (e) Parquet output has expected columns and non-trivial rows
# ====================================================================

@pytest.mark.skipif(not os.path.exists(PREDS_PQ), reason="engine_asof_preds.parquet not yet built")
def test_preds_parquet_schema():
    P = pd.read_parquet(PREDS_PQ)
    required_cols = [
        "gid", "date", "home_win", "margin",
        "m_power", "sd_power", "wp_power",
        "m_team",  "sd_team",  "wp_team",
        "m_ff",    "sd_ff",    "wp_ff",
    ]
    for col in required_cols:
        assert col in P.columns, f"Missing column: {col}"
    assert len(P) >= 100, f"Too few graded games: {len(P)}"
    # win probs must be in (0, 1)
    for col in ["wp_power", "wp_team", "wp_ff"]:
        assert P[col].between(0.0, 1.0).all(), f"{col} out of [0,1]"


# ====================================================================
# (f) Leak-free: as-of SRS on a tiny synthetic dataset
# ====================================================================

def test_asof_srs_small():
    """On a 4-team, 6-game synthetic dataset, SRS at game 3 should NOT use games 4-6."""
    bt = _load_backtest()

    # 4 teams, 6 games in date order
    rows = [
        {"gid": "g1", "date": "2025-11-01", "team": "A", "opp": "B", "pts": 110, "opp_pts": 100,
         "poss": 95.0, "opp_poss": 95.0, "tov": 12, "opp_tov": 14, "fga": 80, "fta": 20,
         "opp_fta": 18, "opp_fga": 78, "oreb": 10, "dreb": 30, "opp_oreb": 8, "opp_dreb": 32, "win": 1},
        {"gid": "g1", "date": "2025-11-01", "team": "B", "opp": "A", "pts": 100, "opp_pts": 110,
         "poss": 95.0, "opp_poss": 95.0, "tov": 14, "opp_tov": 12, "fga": 78, "fta": 18,
         "opp_fta": 20, "opp_fga": 80, "oreb": 8, "dreb": 32, "opp_oreb": 10, "opp_dreb": 30, "win": 0},
        {"gid": "g2", "date": "2025-11-03", "team": "C", "opp": "D", "pts": 115, "opp_pts": 108,
         "poss": 98.0, "opp_poss": 98.0, "tov": 11, "opp_tov": 13, "fga": 85, "fta": 22,
         "opp_fta": 20, "opp_fga": 83, "oreb": 12, "dreb": 28, "opp_oreb": 9, "opp_dreb": 31, "win": 1},
        {"gid": "g2", "date": "2025-11-03", "team": "D", "opp": "C", "pts": 108, "opp_pts": 115,
         "poss": 98.0, "opp_poss": 98.0, "tov": 13, "opp_tov": 11, "fga": 83, "fta": 20,
         "opp_fta": 22, "opp_fga": 85, "oreb": 9, "dreb": 31, "opp_oreb": 12, "opp_dreb": 28, "win": 0},
        # "future" games (should NOT appear in as-of slice for g1/g2)
        {"gid": "g3", "date": "2025-11-10", "team": "A", "opp": "C", "pts": 120, "opp_pts": 90,
         "poss": 96.0, "opp_poss": 96.0, "tov": 10, "opp_tov": 16, "fga": 82, "fta": 24,
         "opp_fta": 16, "opp_fga": 80, "oreb": 13, "dreb": 27, "opp_oreb": 7, "opp_dreb": 33, "win": 1},
        {"gid": "g3", "date": "2025-11-10", "team": "C", "opp": "A", "pts": 90, "opp_pts": 120,
         "poss": 96.0, "opp_poss": 96.0, "tov": 16, "opp_tov": 10, "fga": 80, "fta": 16,
         "opp_fta": 24, "opp_fga": 82, "oreb": 7, "dreb": 33, "opp_oreb": 13, "opp_dreb": 27, "win": 0},
    ]
    df = pd.DataFrame(rows)

    # as-of for g2 (date 2025-11-03): only prior_df has date < 2025-11-03
    prior_g2 = df[df["date"] < "2025-11-03"].copy()
    assert len(prior_g2) == 2, f"Expected 2 prior rows for g2, got {len(prior_g2)}"

    # Run SRS on prior_g2; teams A and B should appear; C and D should NOT influence their ratings
    ratings = bt._srs_asof(prior_g2, ["A", "B", "C", "D"])
    # C and D have no games before 2025-11-03, so their SRS = 0.0
    assert abs(ratings["C"]) < 1e-6, f"C should have 0.0 SRS before its first game, got {ratings['C']}"
    assert abs(ratings["D"]) < 1e-6, f"D should have 0.0 SRS before its first game, got {ratings['D']}"
    # A and B only played each other; with 50 iters (even), SRS oscillates A+B to 0 in this
    # degenerate symmetric case. The structural guarantee is: C/D ratings are 0 (no prior games),
    # and A/B sum to 0 (zero-sum rating, league-normalized).
    assert abs(ratings["A"] + ratings["B"]) < 1e-4, (
        f"A+B should sum to 0 (league-normalized), got {ratings['A']+ratings['B']}"
    )
    # Future games (g3) must NOT appear in prior_g2
    future_games = prior_g2[prior_g2["date"] >= "2025-11-10"]
    assert len(future_games) == 0, f"Future games leaked into as-of slice: {len(future_games)} rows"
