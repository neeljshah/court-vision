"""
tests/test_schedule_pressure.py — Unit tests for src/features/schedule_pressure.py

Uses a fully synthetic schedule (no NBA API calls) to verify every feature.
"""
import json
import os
import sys
import pytest
from datetime import datetime, timedelta

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.features.schedule_pressure import (
    get_team_schedule_features,
    _miles_between,
    _ARENA_GEO,
    _default_features,
)


# ── Helper: build a synthetic schedule ────────────────────────────────────────

def _make_schedule(games: list) -> list:
    """
    games: list of (date_str, is_home, opponent_abbrev, wl)
    Returns schedule format matching schedule_context.get_season_schedule output.
    """
    result = []
    for i, (date_str, is_home, opp, wl) in enumerate(games):
        result.append({
            "game_id":   f"TEST{i:05d}",
            "date":      date_str,
            "home":      is_home,
            "opponent":  opp,
            "wl":        wl,
            "rest_days": 1,
            "travel_miles": 0.0,
        })
    return result


# ── Arena geometry tests ───────────────────────────────────────────────────────

def test_all_30_arenas_have_coords():
    assert len(_ARENA_GEO) == 30


def test_miles_between_known_cities():
    """LAL → BOS is roughly 2600 miles."""
    dist = _miles_between("LAL", "BOS")
    assert 2500 < dist < 2900, f"LAL-BOS distance unexpected: {dist}"


def test_miles_between_same_city():
    """Same arena → 0 miles."""
    assert _miles_between("LAL", "LAC") < 5.0  # same arena


def test_miles_between_unknown():
    assert _miles_between("XYZ", "BOS") == 0.0


# ── Synthetic schedule integration tests ──────────────────────────────────────

def _inject_schedule(monkeypatch, team_abbrev: str, season: str, games: list):
    """Monkeypatch _load_schedule to return synthetic data."""
    import src.features.schedule_pressure as sp

    def fake_load(abbrev: str, s: str) -> list:
        if abbrev == team_abbrev and s == season:
            return games
        return []

    monkeypatch.setattr(sp, "_load_schedule", fake_load)
    monkeypatch.setattr(sp, "_get_team_abbrev", lambda tid: team_abbrev)


def test_3_game_schedule_basic_counts(monkeypatch):
    """Three games in 5 days → games_in_last_7d=3."""
    base = datetime(2025, 1, 10)
    sched = _make_schedule([
        ((base - timedelta(days=5)).strftime("%Y-%m-%d"), True,  "BOS", "W"),
        ((base - timedelta(days=3)).strftime("%Y-%m-%d"), False, "GSW", "L"),
        ((base - timedelta(days=1)).strftime("%Y-%m-%d"), True,  "MIA", "W"),
    ])
    _inject_schedule(monkeypatch, "LAL", "2024-25", sched)

    feats = get_team_schedule_features(1610612747, base.strftime("%Y-%m-%d"), "2024-25")
    assert feats["games_in_last_7d"] == 3
    assert feats["games_in_last_14d"] == 3
    assert feats["days_since_last_game"] == 1


def test_days_since_last_game(monkeypatch):
    """3 days rest correctly computed."""
    target = datetime(2025, 2, 5)
    last_game = target - timedelta(days=3)
    sched = _make_schedule([
        (last_game.strftime("%Y-%m-%d"), True, "BOS", "W"),
    ])
    _inject_schedule(monkeypatch, "LAL", "2024-25", sched)

    feats = get_team_schedule_features(1610612747, target.strftime("%Y-%m-%d"), "2024-25")
    assert feats["days_since_last_game"] == 3


def test_days_until_next_game(monkeypatch):
    """days_until_next_game computed when future games present."""
    target = datetime(2025, 2, 10)
    sched = _make_schedule([
        ((target - timedelta(days=2)).strftime("%Y-%m-%d"), True, "BOS", "W"),
        (target.strftime("%Y-%m-%d"), True, "MIA", "W"),  # target game
        ((target + timedelta(days=2)).strftime("%Y-%m-%d"), False, "GSW", "L"),
    ])
    _inject_schedule(monkeypatch, "LAL", "2024-25", sched)

    feats = get_team_schedule_features(1610612747, target.strftime("%Y-%m-%d"), "2024-25")
    assert feats["days_until_next_game"] == 2


def test_is_4in6_flag(monkeypatch):
    """4 games in 6 days → is_4in6=1."""
    target = datetime(2025, 3, 7)
    sched = _make_schedule([
        ((target - timedelta(days=5)).strftime("%Y-%m-%d"), True,  "ATL", "W"),
        ((target - timedelta(days=4)).strftime("%Y-%m-%d"), False, "BOS", "L"),
        ((target - timedelta(days=2)).strftime("%Y-%m-%d"), True,  "CHI", "W"),
        ((target - timedelta(days=1)).strftime("%Y-%m-%d"), False, "DAL", "L"),
        (target.strftime("%Y-%m-%d"),                       True,  "DEN", "W"),
    ])
    _inject_schedule(monkeypatch, "LAL", "2024-25", sched)

    feats = get_team_schedule_features(1610612747, target.strftime("%Y-%m-%d"), "2024-25")
    assert feats["is_4in6"] == 1


def test_is_5in7_flag(monkeypatch):
    """5 games in 7 days → is_5in7=1."""
    target = datetime(2025, 3, 15)
    sched = _make_schedule([
        ((target - timedelta(days=6)).strftime("%Y-%m-%d"), True,  "BOS", "W"),
        ((target - timedelta(days=5)).strftime("%Y-%m-%d"), False, "GSW", "L"),
        ((target - timedelta(days=3)).strftime("%Y-%m-%d"), True,  "HOU", "W"),
        ((target - timedelta(days=2)).strftime("%Y-%m-%d"), False, "IND", "W"),
        ((target - timedelta(days=1)).strftime("%Y-%m-%d"), True,  "MIA", "L"),
        (target.strftime("%Y-%m-%d"),                       False, "MIL", "W"),
    ])
    _inject_schedule(monkeypatch, "LAL", "2024-25", sched)

    feats = get_team_schedule_features(1610612747, target.strftime("%Y-%m-%d"), "2024-25")
    assert feats["is_5in7"] == 1


def test_mileage_cross_country(monkeypatch):
    """Round trip LAL→BOS produces >2500 miles in 7d window."""
    target = datetime(2025, 3, 20)
    sched = _make_schedule([
        ((target - timedelta(days=3)).strftime("%Y-%m-%d"), True,  "BOS", "W"),  # LAL home
        ((target - timedelta(days=1)).strftime("%Y-%m-%d"), False, "BOS", "L"),  # Road in BOS
        (target.strftime("%Y-%m-%d"),                       True,  "MIA", "W"),
    ])
    _inject_schedule(monkeypatch, "LAL", "2024-25", sched)

    feats = get_team_schedule_features(1610612747, target.strftime("%Y-%m-%d"), "2024-25")
    # BOS→LAL travel leg > 2500 miles
    assert feats["miles_traveled_last_7d"] > 2500


def test_consecutive_road_games(monkeypatch):
    """3 consecutive road games detected."""
    target = datetime(2025, 4, 1)
    sched = _make_schedule([
        ((target - timedelta(days=6)).strftime("%Y-%m-%d"), True,  "BOS", "W"),  # home
        ((target - timedelta(days=4)).strftime("%Y-%m-%d"), False, "DAL", "W"),  # road
        ((target - timedelta(days=2)).strftime("%Y-%m-%d"), False, "HOU", "L"),  # road
        ((target - timedelta(days=1)).strftime("%Y-%m-%d"), False, "MEM", "W"),  # road
        (target.strftime("%Y-%m-%d"),                       False, "NOP", "W"),
    ])
    _inject_schedule(monkeypatch, "LAL", "2024-25", sched)

    feats = get_team_schedule_features(1610612747, target.strftime("%Y-%m-%d"), "2024-25")
    assert feats["consecutive_road_games"] >= 3


def test_default_features_on_empty_schedule(monkeypatch):
    """Empty schedule returns all-zero defaults."""
    import src.features.schedule_pressure as sp
    monkeypatch.setattr(sp, "_load_schedule", lambda a, s: [])
    monkeypatch.setattr(sp, "_get_team_abbrev", lambda tid: "LAL")

    feats = get_team_schedule_features(1610612747, "2025-01-01", "2024-25")
    assert feats["games_in_last_7d"] == 0
    assert feats["days_since_last_game"] == 99


def test_output_keys_complete():
    """Default features dict has all expected keys."""
    feats = _default_features(1610612747, "2025-01-01")
    expected = [
        "games_in_last_7d", "games_in_last_14d",
        "miles_traveled_last_7d", "miles_traveled_last_14d",
        "time_zones_crossed_last_7d",
        "consecutive_road_games", "consecutive_home_games",
        "days_since_last_game", "days_until_next_game",
        "is_4in6", "is_5in7", "cross_country_flag",
    ]
    for k in expected:
        assert k in feats, f"Missing key: {k}"
