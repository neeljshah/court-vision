"""Synthetic-parquet test for mlb_grid: exact bucket aggregates + can_price reasons.

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/calibration_grid/test_mlb_grid.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.calibration_grid import mlb_grid as mg

_ROWS = [
    # game 1: reg inning 7, run_diff +3 -> home wins 5-2 final
    {"game_pk": 1, "home_team": "NYY", "away_team": "BOS", "inning": 7,
     "inning_topbot": "Bot", "post_home_score": 5, "post_away_score": 2},
    {"game_pk": 1, "home_team": "NYY", "away_team": "BOS", "inning": 7,
     "inning_topbot": "Top", "post_home_score": 5, "post_away_score": 2},
    # game 2: reg inning 7, run_diff +3 -> home wins 3-0 final
    {"game_pk": 2, "home_team": "LAD", "away_team": "SF", "inning": 7,
     "inning_topbot": "Bot", "post_home_score": 3, "post_away_score": 0},
    # game 3: extras inning 11, run_diff -9 -> home loses 1-9 final (clip to -6)
    {"game_pk": 3, "home_team": "CHC", "away_team": "STL", "inning": 11,
     "inning_topbot": "Top", "post_home_score": 1, "post_away_score": 9},
]


@pytest.fixture
def data_dir(tmp_path):
    pd.DataFrame(_ROWS).to_parquet(tmp_path / "savant_full__2026.parquet")
    return tmp_path


def test_load_ticks_buckets_and_outcome(data_dir):
    df = mg.load_ticks(data_dir)
    assert len(df) == 4
    assert set(df["bucket"].unique()) == {"inn_07|diff_+03|reg", "extras|diff_-06|extras"}
    g3 = df[df["game_pk"] == 3].iloc[0]
    assert g3["home_win"] == 0  # 1 < 9
    g1 = df[df["game_pk"] == 1].iloc[0]
    assert g1["home_win"] == 1  # final 5 > 2 (max post_home_score/post_away_score)


def test_market_pass_always_null_v1(data_dir):
    df = mg.load_ticks(data_dir)
    market = mg._market_pass(df)
    a = market["inn_07|diff_+03|reg"]
    assert a["n_ticks"] == 3 and a["n_games"] == 2
    assert a["outcome_rate"] == 1.0
    assert a["market_mean_prob"] is None and a["market_brier"] is None
    b = market["extras|diff_-06|extras"]
    assert b["n_ticks"] == 1 and b["n_games"] == 1
    assert b["outcome_rate"] == 0.0


def test_missing_data_dir_returns_empty_frame(tmp_path):
    df = mg.load_ticks(tmp_path / "does_not_exist")
    assert df.empty


def test_can_price_reasons_match_nba_grid_thresholds():
    assert mg._can_price({"n_games": 2}, None)["can_price"] is False
    assert mg._can_price({"n_games": 40}, {"model_n": 1, "model_mean_prob": 0.5}
                         )["can_price"] is False
    assert mg._can_price({"n_games": 40, "outcome_rate": 0.5},
                         {"model_n": 20, "model_mean_prob": 0.9})["can_price"] is False
    assert mg._can_price({"n_games": 40, "outcome_rate": 0.5},
                         {"model_n": 20, "model_mean_prob": 0.52})["can_price"] is True


def test_build_reliability_map_honest_note_and_no_edge(data_dir):
    doc = mg.build_reliability_map(data_dir, model_per_bucket=0)
    assert doc["edge_claimed"] is False
    assert "MARKET JOIN NOT BUILT v1" in doc["honest_note"]
    assert "BASES-OCCUPIED" in doc["honest_note"]
    for bkt in doc["buckets"].values():
        assert bkt["can_price"] is False  # too few games in this synthetic fixture


def test_model_pass_maps_half_and_uses_sanctioned_dispatch(data_dir, monkeypatch):
    calls = []

    def fake_dispatch(sport, home, away, ingame_state=None):
        calls.append((sport, home, away, ingame_state))
        return {"status": "ok", "p_home_win": 0.55}

    monkeypatch.setattr(mg, "dispatch", fake_dispatch)
    df = mg.load_ticks(data_dir)
    sample = mg._sample_for_model(df, n_per_bucket=10, seed=0)
    model = mg._model_pass(sample)
    assert calls
    sport, home, away, state = calls[0]
    assert sport == "mlb"
    assert state["half"] in ("top", "bottom")
    assert model
