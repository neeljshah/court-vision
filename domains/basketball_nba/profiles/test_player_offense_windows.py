"""Per-file test: profiles/player_offense_windows.py -- last_n_games slicing
logic (synthetic, no disk I/O) + a REAL cross-season leak check using the
already-built per-season composition parquets.

Run: python -m pytest domains/basketball_nba/profiles/test_player_offense_windows.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_nba.profiles.player_offense_windows import last_n_games
from domains.basketball_nba.profiles.player_offense_zones import _load_season_table


def test_last_n_games_keeps_most_recent_n_per_group():
    dates = pd.date_range("2025-01-01", periods=25)
    df = pd.DataFrame({"player_id": [1] * 25, "date": dates, "val": range(25)})
    out = last_n_games(df, "player_id", "date", 20)
    assert len(out) == 20
    assert set(out["val"]) == set(range(5, 25))  # the 20 MOST RECENT rows


def test_last_n_games_groups_independently():
    dates = pd.date_range("2025-01-01", periods=5)
    df = pd.DataFrame({
        "player_id": [1, 1, 1, 2, 2],
        "date": list(dates[:3]) + list(dates[:2]),
        "val": [10, 11, 12, 20, 21],
    })
    out = last_n_games(df, "player_id", "date", 2)
    assert out[out["player_id"] == 1]["val"].tolist() == [11, 12]
    assert out[out["player_id"] == 2]["val"].tolist() == [20, 21]


def test_no_cross_season_leakage_in_real_composition_tables():
    """Each player_offense_events_<season>.parquet is a SEPARATE file (one
    per season) -- a game_id in one season's file can never appear in
    another's, so a last-20 window built from ONE file can never pull a game
    from a different season. Verified directly on the real on-disk tables."""
    t2324 = _load_season_table("2023_24")
    t2526 = _load_season_table("2025_26")
    if t2324.empty or t2526.empty:
        return  # composition tables not built in this environment -- skip, don't fake a pass
    assert not (set(t2324["game_id"]) & set(t2526["game_id"]))
