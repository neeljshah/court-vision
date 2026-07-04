"""Per-file tests for domains.baseball_kbo.adapter.KBOAdapter (synthetic data,
no network, no real corpus dependency).

  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/baseball_kbo/test_adapter.py -q
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from domains.baseball_kbo.adapter import KBOAdapter, SPORT_ID
from src.loop.signal import Hypothesis


def _hyp(name: str = "kbo_test") -> Hypothesis:
    return Hypothesis(name=name, target="winprob", scope="pregame",
                      statement=f"{name} hypothesis")


def _synthetic_games() -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.to_datetime(["2023-04-01", "2023-04-03", "2023-04-06", "2024-04-01"]),
        "season": ["2023", "2023", "2023", "2024"],
        "home_team": ["DOOSAN", "KIA", "DOOSAN", "DOOSAN"],
        "away_team": ["KIA", "DOOSAN", "KIA", "KIA"],
        "home_score": [4.0, 2.0, 3.0, 5.0],
        "away_score": [2.0, 5.0, 3.0, 6.0],
        "home_win": [1.0, 0.0, np.nan, 0.0],  # third row is a tie
        "tied": [False, False, True, False],
    })


def test_sport_id_is_baseball_kbo():
    assert SPORT_ID == "baseball_kbo"


def test_list_events_returns_games_on_date_including_tied():
    adapter = KBOAdapter(games_df=_synthetic_games())
    events = adapter.list_events(dt.date(2023, 4, 6))
    assert len(events) == 1
    assert events[0]["sport"] == SPORT_ID
    assert events[0]["meta"]["tied"] is True


def test_market_snapshot_always_none():
    adapter = KBOAdapter(games_df=_synthetic_games())
    events = adapter.list_events(dt.date(2023, 4, 1))
    assert adapter.market_snapshot(events[0], "open") is None
    assert adapter.market_snapshot(events[0], "close") is None


def test_outcome_winner_a_when_home_wins():
    adapter = KBOAdapter(games_df=_synthetic_games())
    events = adapter.list_events(dt.date(2023, 4, 1))
    out = adapter.outcome(events[0])
    assert out is not None
    assert out["winner"] == "a"


def test_outcome_winner_b_when_away_wins():
    adapter = KBOAdapter(games_df=_synthetic_games())
    events = adapter.list_events(dt.date(2023, 4, 3))
    out = adapter.outcome(events[0])
    assert out is not None
    assert out["winner"] == "b"


def test_outcome_none_for_tied_game():
    adapter = KBOAdapter(games_df=_synthetic_games())
    events = adapter.list_events(dt.date(2023, 4, 6))
    assert adapter.outcome(events[0]) is None


def test_outcome_none_for_unknown_event():
    adapter = KBOAdapter(games_df=_synthetic_games())
    assert adapter.outcome({"event_id": "does-not-exist"}) is None


def test_baseline_probability_is_valid_prob():
    adapter = KBOAdapter(games_df=_synthetic_games())
    event = {"meta": {"home_team": "DOOSAN", "away_team": "KIA"}}
    p = adapter.baseline_probability(event, as_of=dt.datetime(2023, 4, 10))
    assert 0.0 < p < 1.0


def test_feature_bundle_excludes_tied_row():
    adapter = KBOAdapter(games_df=_synthetic_games())
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
    adapter = KBOAdapter(games_df=_synthetic_games())
    fb = adapter.feature_bundle(_hyp(), seasons=["2023"])
    assert fb.base.shape[0] == 2  # 3 games in 2023, 1 tied -> 2 decisive


def test_feature_bundle_raises_on_empty_filter():
    adapter = KBOAdapter(games_df=_synthetic_games())
    with pytest.raises(ValueError):
        adapter.feature_bundle(_hyp(), seasons=["1999"])


def test_get_games_missing_file_raises():
    adapter = KBOAdapter(repo_root=None, games_df=None)
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        a2 = KBOAdapter(repo_root=Path(td))
        with pytest.raises(FileNotFoundError):
            a2._get_games()


def test_event_id_is_stable_natural_key():
    adapter = KBOAdapter(games_df=_synthetic_games())
    events = adapter.list_events(dt.date(2023, 4, 1))
    assert "2023-04-01" in events[0]["event_id"]
    assert "DOOSAN" in events[0]["event_id"]
    assert "KIA" in events[0]["event_id"]
