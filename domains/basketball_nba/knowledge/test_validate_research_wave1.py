"""Tests for domains.basketball_nba.knowledge.validate_research_wave1."""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.basketball_nba.knowledge.validate_research_wave1 import (
    _defender_predictive_r, _partial_corr, _switch_efficiency_frame,
    ast_persistence_and_margin, defender_matchup_skill_predictive_validity,
    switch_rate_defensive_efficiency,
)


def _toy_defender_frame() -> pd.DataFrame:
    # 5 defenders at 5 distinct, stable skill levels -- real, monotone
    # within-half predictive signal in BOTH halves, same sign (n=5 clears
    # p<0.01 at r~0.99; n=3 does not, too few degrees of freedom).
    levels = {1: (0.35, 0.36), 2: (0.42, 0.43), 3: (0.48, 0.47), 4: (0.55, 0.54), 5: (0.60, 0.61)}
    rows = []
    for i, d in enumerate(pd.date_range("2024-10-01", periods=8, freq="15D")):
        for pid, (asof, realized) in levels.items():
            rows.append({
                "def_player_id": pid, "game_date": d,
                "def_priorN_fg_pct_allowed_asof": asof + 0.01 * (i % 2),
                "realized_fg_pct_allowed": realized + 0.01 * (i % 2),
                "def_n_prior": 10,
            })
    return pd.DataFrame(rows)


def test_defender_predictive_confirms_real_split_half_signal():
    from domains.basketball_nba.knowledge.validate_research_wave1 import _defender_half_frame
    d = _defender_half_frame(_toy_defender_frame())
    r = defender_matchup_skill_predictive_validity(d)
    assert r["verdict"] == "CONFIRMED_LOCAL"
    assert r["n_h1_defenders"] == 5 and r["n_h2_defenders"] == 5


def test_defender_floor_excludes_low_support_rows():
    d = _toy_defender_frame()
    d["def_n_prior"] = 1  # below MIN_PRIOR_POSSESSIONS floor
    from domains.basketball_nba.knowledge.validate_research_wave1 import _defender_half_frame
    dd = _defender_half_frame(d)
    out = _defender_predictive_r(dd, "h1")
    assert out["n"] == 0  # every row filtered out by the floor


def test_switch_efficiency_constant_column_is_not_testable():
    df = pd.DataFrame({
        "home_def_switches_per_game_asof": [0.0] * 10,
        "away_def_switches_per_game_asof": [0.0] * 10,
        "home_def_pts_allowed_per36_asof": np.linspace(20, 30, 10),
        "away_def_pts_allowed_per36_asof": np.linspace(20, 30, 10),
        "home_def_blocks_per_game_asof": np.linspace(0.2, 0.4, 10),
        "away_def_blocks_per_game_asof": np.linspace(0.2, 0.4, 10),
    })
    frame = _switch_efficiency_frame(df)
    r = switch_rate_defensive_efficiency(frame)
    assert r["verdict"] == "NOT_TESTABLE"
    assert "constant" in r["note"]


def test_switch_efficiency_detects_real_partial_correlation():
    rng = np.random.default_rng(0)
    n = 200
    blocks = rng.uniform(0.1, 0.5, n)
    switches = rng.uniform(0.0, 1.0, n)
    pts = 20 + 5 * switches - 3 * blocks + rng.normal(0, 0.05, n)
    df = pd.DataFrame({
        "home_def_switches_per_game_asof": switches,
        "away_def_switches_per_game_asof": switches,
        "home_def_pts_allowed_per36_asof": pts,
        "away_def_pts_allowed_per36_asof": pts,
        "home_def_blocks_per_game_asof": blocks,
        "away_def_blocks_per_game_asof": blocks,
    })
    frame = _switch_efficiency_frame(df)
    r = switch_rate_defensive_efficiency(frame)
    assert r["verdict"] == "CONFIRMED_LOCAL"
    assert r["r"] > 0.1


def test_partial_corr_degenerate_inputs_return_nan():
    out = _partial_corr(pd.Series([1.0] * 5), pd.Series([1.0, 2, 3, 4, 5]), pd.Series([1.0, 2, 3, 4, 5]))
    assert out["p"] is None or (isinstance(out["p"], float) and np.isnan(out["p"]))


def _toy_espn_box_ast() -> pd.DataFrame:
    rows = []
    for i, d in enumerate(pd.date_range("2026-01-01", periods=8, freq="10D")):
        rows.append({
            "date": d, "home_abbr": "A", "away_abbr": "B",
            "home_score": 120.0, "away_score": 95.0,
            "home_ast": 28.0 + i * 0.1, "away_ast": 12.0,
        })
        rows.append({
            "date": d, "home_abbr": "C", "away_abbr": "B",
            "home_score": 108.0, "away_score": 95.0,
            "home_ast": 20.0, "away_ast": 12.0,
        })
    return pd.DataFrame(rows)


def test_ast_persistence_and_margin_detects_real_signal():
    from domains.basketball_nba.knowledge.validate_research_wave1 import _load_team_games_ast
    tg = _load_team_games_ast(_toy_espn_box_ast())
    r = ast_persistence_and_margin(tg)
    assert r["hypothesis"] == "boxdetail_ast_persistence_and_margin"
    assert r["verdict"] == "CONFIRMED_LOCAL"


if __name__ == "__main__":
    test_defender_predictive_confirms_real_split_half_signal()
    test_defender_floor_excludes_low_support_rows()
    test_switch_efficiency_constant_column_is_not_testable()
    test_switch_efficiency_detects_real_partial_correlation()
    test_partial_corr_degenerate_inputs_return_nan()
    test_ast_persistence_and_margin_detects_real_signal()
    print("OK: validate_research_wave1 self-checks pass.")
