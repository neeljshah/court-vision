"""Per-file tests for domains.basketball_wnba.adapter.WNBAAdapter (synthetic data,
no network, no real corpus dependency).

  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_adapter.py -q
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from domains.basketball_wnba.adapter import WNBAAdapter, SPORT_ID
from src.loop.signal import Hypothesis


def _hyp(name: str = "wnba_test") -> Hypothesis:
    return Hypothesis(name=name, target="winprob", scope="pregame",
                      statement=f"{name} hypothesis")


def _synthetic_games() -> pd.DataFrame:
    return pd.DataFrame({
        "event_id": ["1", "2", "3", "4"],
        "date": pd.to_datetime(["2024-05-03", "2024-05-05", "2024-05-08", "2025-05-03"]),
        "season": ["2024", "2024", "2024", "2025"],
        "home_team": ["Aces", "Fever", "Aces", "Aces"],
        "away_team": ["Fever", "Aces", "Fever", "Fever"],
        "home_score": [88.0, 75.0, 90.0, 80.0],
        "away_score": [80.0, 70.0, 85.0, 82.0],
        "home_win": [1.0, 1.0, 1.0, 0.0],
        "neutral_site": [False, False, False, False],
        "status_name": ["STATUS_FINAL"] * 4,
    })


def test_sport_id_is_basketball_wnba():
    assert SPORT_ID == "basketball_wnba"


def test_list_events_returns_games_on_date():
    adapter = WNBAAdapter(games_df=_synthetic_games())
    events = adapter.list_events(dt.date(2024, 5, 3))
    assert len(events) == 1
    assert events[0]["sport"] == SPORT_ID
    assert events[0]["event_id"] == "1"
    assert events[0]["meta"]["home_team"] == "Aces"


def test_market_snapshot_always_none():
    adapter = WNBAAdapter(games_df=_synthetic_games())
    assert adapter.market_snapshot({"event_id": "1"}, "open") is None
    assert adapter.market_snapshot({"event_id": "1"}, "close") is None


def test_outcome_winner_a_when_home_wins():
    adapter = WNBAAdapter(games_df=_synthetic_games())
    out = adapter.outcome({"event_id": "1"})
    assert out is not None
    assert out["winner"] == "a"


def test_outcome_winner_b_when_away_wins():
    adapter = WNBAAdapter(games_df=_synthetic_games())
    out = adapter.outcome({"event_id": "4"})
    assert out is not None
    assert out["winner"] == "b"


def test_outcome_none_for_unknown_event():
    adapter = WNBAAdapter(games_df=_synthetic_games())
    assert adapter.outcome({"event_id": "does-not-exist"}) is None


def test_baseline_probability_is_valid_prob():
    adapter = WNBAAdapter(games_df=_synthetic_games())
    event = {"meta": {"home_team": "Aces", "away_team": "Fever"}}
    p = adapter.baseline_probability(event, as_of=dt.datetime(2024, 5, 9))
    assert 0.0 < p < 1.0


def test_feature_bundle_shape_and_contract():
    adapter = WNBAAdapter(games_df=_synthetic_games())
    fb = adapter.feature_bundle(_hyp())
    assert fb.base.shape == (4, 2)  # [elo_home, elo_away]
    assert fb.signal_col.shape == (4,)
    assert fb.target.shape == (4,)
    assert set(fb.target.tolist()) <= {0.0, 1.0}
    assert all(0.0 < p < 1.0 for p in fb.signal_col.tolist())
    assert fb.lines is None
    assert fb.closing is None
    assert list(fb.dates) == sorted(fb.dates)  # ascending


def test_feature_bundle_season_filter():
    adapter = WNBAAdapter(games_df=_synthetic_games())
    fb = adapter.feature_bundle(_hyp(), seasons=["2024"])
    assert fb.base.shape[0] == 3


def test_feature_bundle_raises_on_empty_filter():
    adapter = WNBAAdapter(games_df=_synthetic_games())
    with pytest.raises(ValueError):
        adapter.feature_bundle(_hyp(), seasons=["1999"])


def test_get_games_missing_file_raises():
    adapter = WNBAAdapter(repo_root=None, games_df=None)
    # Point at a repo_root with no data dir at all.
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        a2 = WNBAAdapter(repo_root=Path(td))
        with pytest.raises(FileNotFoundError):
            a2._get_games()
