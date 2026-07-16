"""LANE B -- schedule_context_resolver tests. Synthetic 3-game calendar
(monkeypatched _CALENDAR_PATHS, no real linescores.parquet dependency) --
pins the rest_days/is_b2b boundary convention (game yesterday -> rest_days=0
-> is_b2b=True) and the fail-closed no_data / not_supported paths.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/answers/test_schedule_context_resolver.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.answers import schedule_context_resolver as R

# AAA: games 2025-01-01, 2025-01-03, 2025-01-04 (last two are a real b2b).
_CAL = pd.DataFrame([
    {"home_abbr": "AAA", "away_abbr": "BBB", "date": pd.Timestamp("2025-01-01")},
    {"home_abbr": "BBB", "away_abbr": "AAA", "date": pd.Timestamp("2025-01-03")},
    {"home_abbr": "AAA", "away_abbr": "CCC", "date": pd.Timestamp("2025-01-04")},
])


@pytest.fixture(autouse=True)
def _synthetic_calendar(tmp_path, monkeypatch):
    path = tmp_path / "cal.parquet"
    _CAL.to_parquet(path)
    monkeypatch.setitem(R._CALENDAR_PATHS, "nba", (str(path), "home_abbr", "away_abbr"))
    monkeypatch.setattr(R, "_schedule_claims", lambda sport, team: [])  # isolate from real claims store
    return path


def test_game_yesterday_is_b2b_rest_days_zero():
    # boundary case: prior game 2025-01-01, as_of 2025-01-02 -> delta=1 day -> rest_days=0
    r = R.resolve("nba", "AAA", "2025-01-02")
    assert r["status"] == "ok"
    assert r["rest_days"] == 0
    assert r["is_b2b"] is True
    assert r["prior_game_date"] == "2025-01-01"


def test_two_days_rest_is_not_b2b():
    # prior game 2025-01-04, as_of 2025-01-06 -> delta=2 days -> rest_days=1
    r = R.resolve("nba", "AAA", "2025-01-06")
    assert r["rest_days"] == 1
    assert r["is_b2b"] is False
    assert r["prior_game_date"] == "2025-01-04"


def test_games_in_last_7_excludes_as_of_own_game():
    # as_of=2025-01-08 -> trailing window [2025-01-01, 2025-01-08) catches all 3 games
    r = R.resolve("nba", "AAA", "2025-01-08")
    assert r["games_in_last_7"] == 3


def test_no_prior_game_before_as_of():
    r = R.resolve("nba", "AAA", "2024-12-31")
    assert r["status"] == "ok"
    assert r["rest_days"] is None
    assert r["is_b2b"] is False
    assert r["prior_game_date"] is None


def test_unmatched_team_is_no_data_not_fabricated():
    r = R.resolve("nba", "ZZZ", "2025-01-08")
    assert r["status"] == "no_data"
    assert r["category"] == "schedule_context"


def test_unsupported_sport_is_not_supported():
    r = R.resolve("soccer", "ARS")
    assert r["status"] == "not_supported"


def test_missing_artifact_is_no_data(monkeypatch):
    monkeypatch.setitem(R._CALENDAR_PATHS, "nba", ("data/does/not/exist.parquet", "home_abbr", "away_abbr"))
    r = R.resolve("nba", "AAA")
    assert r["status"] == "no_data"
    assert r["source_artifact"] == "data/does/not/exist.parquet"


def test_nba_claims_code_convention_accepted():
    # GSW (claims convention) must resolve against the calendar's "GS" code
    cal = pd.DataFrame([
        {"home_abbr": "GS", "away_abbr": "BBB", "date": pd.Timestamp("2025-01-01")},
    ])
    path_gs = R._CALENDAR_PATHS["nba"][0]
    cal.to_parquet(path_gs)
    r = R.resolve("nba", "GSW", "2025-01-02")
    assert r["status"] == "ok"
    assert r["team"] == "GSW"  # echoed back in claims convention
    assert r["is_b2b"] is True
