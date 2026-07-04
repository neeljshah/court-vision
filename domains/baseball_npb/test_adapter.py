"""Per-file tests for domains.baseball_npb.adapter.NPBAdapter (synthetic data,
no network, no real corpus dependency).

  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/baseball_npb/test_adapter.py -q
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from domains.baseball_npb.adapter import NPBAdapter, SPORT_ID
from src.loop.signal import Hypothesis


def _hyp(name: str = "npb_test") -> Hypothesis:
    return Hypothesis(name=name, target="winprob", scope="pregame",
                      statement=f"{name} hypothesis")


def _synthetic_games() -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.to_datetime(["2023-04-01", "2023-04-03", "2023-04-06", "2024-04-01"]),
        "season": ["2023", "2023", "2023", "2024"],
        "home_team": ["Giants", "Tigers", "Giants", "Giants"],
        "away_team": ["Tigers", "Giants", "Tigers", "Tigers"],
        "home_score": [4.0, 2.0, 3.0, 5.0],
        "away_score": [2.0, 5.0, 3.0, 6.0],
        "home_win": [1.0, 0.0, np.nan, 0.0],  # third row is a tie
        "tied": [False, False, True, False],
    })


def test_sport_id_is_baseball_npb():
    assert SPORT_ID == "baseball_npb"


def test_list_events_returns_games_on_date_including_tied():
    adapter = NPBAdapter(games_df=_synthetic_games())
    events = adapter.list_events(dt.date(2023, 4, 6))
    assert len(events) == 1
    assert events[0]["sport"] == SPORT_ID
    assert events[0]["meta"]["tied"] is True


def test_market_snapshot_always_none():
    adapter = NPBAdapter(games_df=_synthetic_games())
    events = adapter.list_events(dt.date(2023, 4, 1))
    assert adapter.market_snapshot(events[0], "open") is None
    assert adapter.market_snapshot(events[0], "close") is None


def test_outcome_winner_a_when_home_wins():
    adapter = NPBAdapter(games_df=_synthetic_games())
    events = adapter.list_events(dt.date(2023, 4, 1))
    out = adapter.outcome(events[0])
    assert out is not None
    assert out["winner"] == "a"


def test_outcome_winner_b_when_away_wins():
    adapter = NPBAdapter(games_df=_synthetic_games())
    events = adapter.list_events(dt.date(2023, 4, 3))
    out = adapter.outcome(events[0])
    assert out is not None
    assert out["winner"] == "b"


def test_outcome_none_for_tied_game():
    adapter = NPBAdapter(games_df=_synthetic_games())
    events = adapter.list_events(dt.date(2023, 4, 6))
    assert adapter.outcome(events[0]) is None


def test_outcome_none_for_unknown_event():
    adapter = NPBAdapter(games_df=_synthetic_games())
    assert adapter.outcome({"event_id": "does-not-exist"}) is None


def test_baseline_probability_is_valid_prob():
    adapter = NPBAdapter(games_df=_synthetic_games())
    event = {"meta": {"home_team": "Giants", "away_team": "Tigers"}}
    p = adapter.baseline_probability(event, as_of=dt.datetime(2023, 4, 10))
    assert 0.0 < p < 1.0


def test_feature_bundle_excludes_tied_row():
    adapter = NPBAdapter(games_df=_synthetic_games())
    fb = adapter.feature_bundle(_hyp())
    # 4 total rows, 1 tied -> 3 rows in the bundle
    assert fb.base.shape == (3, 2)
    assert fb.signal_col.shape == (3,)
    assert fb.target.shape == (3,)
    assert set(fb.target.tolist()) <= {0.0, 1.0}
    assert all(0.0 < p < 1.0 for p in fb.signal_col.tolist())
    assert fb.lines is None
    assert fb.closing is None
    assert list(fb.dates) == sorted(fb.dates)


def test_feature_bundle_season_filter():
    adapter = NPBAdapter(games_df=_synthetic_games())
    fb = adapter.feature_bundle(_hyp(), seasons=["2023"])
    assert fb.base.shape[0] == 2  # 3 games in 2023, 1 tied -> 2 decisive


def test_feature_bundle_raises_on_empty_filter():
    adapter = NPBAdapter(games_df=_synthetic_games())
    with pytest.raises(ValueError):
        adapter.feature_bundle(_hyp(), seasons=["1999"])


def test_get_games_missing_file_raises():
    adapter = NPBAdapter(repo_root=None, games_df=None)
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        a2 = NPBAdapter(repo_root=Path(td))
        with pytest.raises(FileNotFoundError):
            a2._get_games()


def test_event_id_is_stable_natural_key():
    adapter = NPBAdapter(games_df=_synthetic_games())
    events = adapter.list_events(dt.date(2023, 4, 1))
    assert "2023-04-01" in events[0]["event_id"]
    assert "Giants" in events[0]["event_id"]
    assert "Tigers" in events[0]["event_id"]


def test_predict_moneyline_pregame_view():
    adapter = NPBAdapter(games_df=_synthetic_games())
    events = adapter.list_events(dt.date(2023, 4, 1))
    home, away = events[0]["meta"]["home_team"], events[0]["meta"]["away_team"]
    out = adapter.predict(home, away)
    assert out["sport"] == SPORT_ID
    assert out["home"] == home and out["away"] == away
    assert 0.0 <= out["p_home_win"] <= 1.0
    assert abs(out["p_home_win"] + out["p_away_win"] - 1.0) < 1e-9
    assert "Elo" in out["honest_note"]
    assert "no $ edge" in out["honest_note"].lower()
