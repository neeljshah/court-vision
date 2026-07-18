"""Synthetic-parquet test for nba_grid: exact bucket aggregates + can_price reasons.

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/calibration_grid/test_nba_grid.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.calibration_grid import nba_grid as ng

# 6 rows: 3 ticks in one bucket (2 games), 3 ticks in a second bucket (1 game).
# elapsed=28 -> remaining=20 -> rem_12_24; home_lead=7 -> lead_+05_10 (regulation).
# elapsed=44 -> remaining=4 -> rem_02_05; home_lead=0 -> lead_00 (regulation).
_ROWS = [
    # bucket A: lead_+05_10|rem_12_24|reg -- game 1 (home wins), game 2 (home wins)
    {"game_id": "g1", "period": 3, "game_clock_s": 240.0, "score_home": 57, "score_away": 50,
     "market_prob": 0.60, "traded": True, "market_ticker": "nba-bos-lal-2026-01-01",
     "outcome_home_win": 1},
    {"game_id": "g1", "period": 3, "game_clock_s": 235.0, "score_home": 58, "score_away": 51,
     "market_prob": 0.62, "traded": True, "market_ticker": "nba-bos-lal-2026-01-01",
     "outcome_home_win": 1},
    {"game_id": "g2", "period": 3, "game_clock_s": 240.0, "score_home": 60, "score_away": 53,
     "market_prob": 0.58, "traded": True, "market_ticker": "nba-mia-nyk-2026-01-02",
     "outcome_home_win": 1},
    # bucket B: lead_00|rem_02_05|reg -- game 3 (home loses)
    {"game_id": "g3", "period": 4, "game_clock_s": 240.0, "score_home": 90, "score_away": 90,
     "market_prob": 0.50, "traded": True, "market_ticker": "nba-gsw-den-2026-01-03",
     "outcome_home_win": 0},
    {"game_id": "g3", "period": 4, "game_clock_s": 235.0, "score_home": 91, "score_away": 91,
     "market_prob": 0.51, "traded": True, "market_ticker": "nba-gsw-den-2026-01-03",
     "outcome_home_win": 0},
    # an UNTRADED tick that must be dropped
    {"game_id": "g3", "period": 4, "game_clock_s": 230.0, "score_home": 92, "score_away": 91,
     "market_prob": 0.55, "traded": False, "market_ticker": "nba-gsw-den-2026-01-03",
     "outcome_home_win": 0},
]


@pytest.fixture
def parquet_path(tmp_path):
    p = tmp_path / "nba_checkpoints_full.parquet"
    pd.DataFrame(_ROWS).to_parquet(p)
    return p


def test_load_ticks_drops_untraded_and_buckets(parquet_path):
    df = ng.load_ticks(parquet_path)
    assert len(df) == 5  # the untraded 6th row is dropped
    assert set(df["bucket"].unique()) == {
        "lead_+05_10|rem_12_24|reg", "lead_00|rem_02_05|reg"}


def test_market_pass_exact_aggregates(parquet_path):
    df = ng.load_ticks(parquet_path)
    market = ng._market_pass(df)
    a = market["lead_+05_10|rem_12_24|reg"]
    assert a["n_ticks"] == 3 and a["n_games"] == 2
    assert a["outcome_rate"] == 1.0
    assert a["market_mean_prob"] == round((0.60 + 0.62 + 0.58) / 3, 4)
    b = market["lead_00|rem_02_05|reg"]
    assert b["n_ticks"] == 2 and b["n_games"] == 1
    assert b["outcome_rate"] == 0.0
    assert b["market_mean_prob"] == round((0.50 + 0.51) / 2, 4)


def test_missing_corpus_returns_empty_frame(tmp_path):
    df = ng.load_ticks(tmp_path / "does_not_exist.parquet")
    assert df.empty


def test_can_price_insufficient_games():
    row = ng._can_price({"n_games": 2}, None)
    assert row["can_price"] is False
    assert "insufficient games" in row["reason"]


def test_can_price_insufficient_model_samples():
    row = ng._can_price({"n_games": 40}, {"model_n": 3, "model_mean_prob": 0.5})
    assert row["can_price"] is False
    assert "insufficient model samples" in row["reason"]


def test_can_price_miscalibrated():
    row = ng._can_price({"n_games": 40, "outcome_rate": 0.5},
                         {"model_n": 20, "model_mean_prob": 0.7})
    assert row["can_price"] is False
    assert "miscalibrated" in row["reason"]


def test_can_price_ok():
    row = ng._can_price({"n_games": 40, "outcome_rate": 0.55},
                         {"model_n": 20, "model_mean_prob": 0.56})
    assert row["can_price"] is True
    assert row["reason"] == "ok"


def test_build_reliability_map_default_no_model_pass_reason(parquet_path):
    doc = ng.build_reliability_map(parquet_path, model_per_bucket=0)
    assert doc["edge_claimed"] is False
    assert doc["n_ticks_total"] == 5
    for bkt in doc["buckets"].values():
        assert bkt["can_price"] is False
        assert "insufficient" in bkt["reason"]  # too few games AND zero model samples


def test_model_pass_uses_sanctioned_dispatch_and_parses_ticker(parquet_path, monkeypatch):
    calls = []

    def fake_dispatch(sport, home, away, ingame_state=None):
        calls.append((sport, home, away, ingame_state))
        return {"status": "ok", "p_home_win": 0.6}

    monkeypatch.setattr(ng, "dispatch", fake_dispatch)
    df = ng.load_ticks(parquet_path)
    sample = ng._sample_for_model(df, n_per_bucket=10, seed=0)
    model = ng._model_pass(sample)
    assert calls, "dispatch was never called"
    sport, home, away, state = calls[0]
    assert sport == "nba" and home and away
    assert "elapsed" in state and "home_score" in state and "away_score" in state
    assert model  # at least one bucket scored
    for row in model.values():
        assert row["model_n"] > 0
