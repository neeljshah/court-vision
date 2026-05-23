"""
tests/test_team_form.py — Unit tests for src/features/team_form.py

Uses fixture L10 data (no API calls) to verify all 6 form features
are computed and fall in expected ranges.
"""
import json
import os
import sys
import pytest
from datetime import datetime, timedelta

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.features.team_form import (
    get_team_form_features,
    _default_form,
    _load_net_ratings,
)


# ── Fixture builder ────────────────────────────────────────────────────────────

def _make_games(base_date: datetime, specs: list) -> list:
    """
    specs: list of (days_back, is_home, opponent, wl, plus_minus)
    Returns list of schedule-format game dicts.
    """
    result = []
    for i, (days_back, is_home, opp, wl, pm) in enumerate(specs):
        gdate = (base_date - timedelta(days=days_back)).strftime("%Y-%m-%d")
        result.append({
            "game_id":     f"FORM{i:05d}",
            "date":        gdate,
            "home":        is_home,
            "opponent":    opp,
            "wl":          wl,
            "plus_minus":  pm,
        })
    return result


def _inject_schedule(monkeypatch, team: str, season: str, games: list):
    import src.features.team_form as tf

    def fake_load(abbrev: str, s: str) -> list:
        if abbrev == team and s == season:
            return games
        return []

    monkeypatch.setattr(tf, "_load_schedule", fake_load)


# ── Net-rating tests ───────────────────────────────────────────────────────────

def test_net_ratings_loaded():
    """Net ratings dict has all 30 teams."""
    nr = _load_net_ratings()
    assert len(nr) == 30
    # BOS should be positive (top team)
    assert nr["BOS"] > 0


# ── Form feature tests ─────────────────────────────────────────────────────────

def test_quality_of_wins(monkeypatch):
    """Wins against high-rated opponents produce positive quality_of_wins."""
    target = datetime(2025, 2, 20)
    # Win vs BOS (high net), loss vs UTA (low net), win vs OKC (high net)
    games = _make_games(target, [
        (20, False, "BOS", "W", 7),    # Win vs BOS (nr 9.2)
        (17, True,  "UTA", "L", -5),   # Loss vs UTA (nr -8.1)
        (14, False, "OKC", "W", 12),   # Win vs OKC (nr 7.8)
        (11, True,  "DET", "L", -9),
        (8,  False, "CLE", "W", 3),
        (5,  True,  "WAS", "W", 20),
        (3,  False, "NOP", "L", -4),
        (2,  True,  "CHA", "W", 8),
        (1,  False, "POR", "W", 11),
    ])
    _inject_schedule(monkeypatch, "LAL", "2024-25", games)

    feats = get_team_form_features("LAL", target.strftime("%Y-%m-%d"), "2024-25")
    qow = feats["team_quality_of_wins_l10"]
    # Won vs BOS (9.2) + OKC (7.8) + CLE (7.1) + WAS (-7.4) + CHA (-3.1) + POR (-4.8)
    assert qow > 0, f"Expected positive QoW, got {qow}"


def test_strength_of_schedule(monkeypatch):
    """SOS is average opponent net rating — bounded in reasonable range."""
    target = datetime(2025, 3, 5)
    games = _make_games(target, [
        (18, False, "BOS", "L", -10),
        (15, True,  "GSW", "W", 4),
        (12, False, "OKC", "L", -6),
        (9,  True,  "DEN", "W", 2),
        (7,  False, "NYK", "W", 5),
        (5,  True,  "MIL", "L", -3),
        (3,  False, "MIA", "W", 8),
        (2,  True,  "IND", "W", 7),
        (1,  False, "PHI", "L", -2),
    ])
    _inject_schedule(monkeypatch, "GSW", "2024-25", games)

    feats = get_team_form_features("GSW", target.strftime("%Y-%m-%d"), "2024-25")
    sos = feats["team_strength_of_schedule_l10"]
    assert -15.0 <= sos <= 15.0


def test_clutch_record_computed(monkeypatch):
    """Clutch record is between 0 and 1."""
    target = datetime(2025, 3, 12)
    games = _make_games(target, [
        (19, True,  "BOS", "W",  3),   # close win
        (16, False, "DAL", "L", -4),   # close loss
        (13, True,  "HOU", "W",  1),   # close win
        (10, False, "IND", "L", -20),  # blowout loss
        (7,  True,  "MEM", "W",  5),   # close win
        (5,  False, "MIN", "L", -2),   # close loss
        (3,  True,  "NOP", "W",  18),  # blowout win
        (2,  False, "NYK", "L", -5),   # close loss
        (1,  True,  "OKC", "W",  3),   # close win
    ])
    _inject_schedule(monkeypatch, "LAL", "2024-25", games)

    feats = get_team_form_features("LAL", target.strftime("%Y-%m-%d"), "2024-25")
    cr = feats["team_clutch_record_l10"]
    # 4 close wins / 8 close games = 0.5
    assert 0.0 <= cr <= 1.0


def test_blowout_factor(monkeypatch):
    """Blowout factor between 0 and 1."""
    target = datetime(2025, 4, 1)
    games = _make_games(target, [
        (19, True,  "BOS", "W",  25),   # blowout
        (16, False, "CLE", "L", -18),   # blowout
        (13, True,  "DAL", "W",  4),
        (10, False, "DEN", "W",  2),
        (7,  True,  "DET", "W",  16),   # blowout
        (5,  False, "GSW", "L", -3),
        (3,  True,  "HOU", "W",  8),
        (2,  False, "IND", "L", -1),
        (1,  True,  "LAC", "W",  19),   # blowout
    ])
    _inject_schedule(monkeypatch, "LAL", "2024-25", games)

    feats = get_team_form_features("LAL", target.strftime("%Y-%m-%d"), "2024-25")
    bf = feats["team_blowout_factor_l10"]
    # 4 blowouts / 9 games with pm data = ~0.44
    assert 0.0 <= bf <= 1.0
    assert bf > 0.3, f"Expected >0.3 blowout rate with 4 blowouts, got {bf}"


def test_win_pct_correct(monkeypatch):
    """Win pct matches manually computed value."""
    target = datetime(2025, 1, 25)
    # 7W 3L
    games = _make_games(target, [
        (20, True,  "ATL", "W", 10),
        (18, False, "BKN", "L", -5),
        (16, True,  "CHA", "W",  8),
        (14, False, "CHI", "W", 12),
        (12, True,  "CLE", "L", -7),
        (10, False, "DAL", "W",  4),
        (8,  True,  "DEN", "W",  3),
        (6,  False, "DET", "L", -9),
        (4,  True,  "GSW", "W", 15),
        (2,  False, "HOU", "W",  6),
    ])
    _inject_schedule(monkeypatch, "MIA", "2024-25", games)

    feats = get_team_form_features("MIA", target.strftime("%Y-%m-%d"), "2024-25", window=10)
    assert abs(feats["team_win_pct_l10"] - 0.7) < 0.01


def test_all_6_features_present(monkeypatch):
    """All 6 required form features are present in the output."""
    target = datetime(2025, 2, 1)
    games = _make_games(target, [
        (i + 1, True, "BOS", "W" if i % 2 == 0 else "L", (i % 2) * 8 - 4)
        for i in range(10)
    ])
    _inject_schedule(monkeypatch, "BOS", "2024-25", games)

    feats = get_team_form_features("BOS", target.strftime("%Y-%m-%d"), "2024-25")
    required = [
        "team_quality_of_wins_l10",
        "team_strength_of_schedule_l10",
        "team_clutch_record_l10",
        "team_3pt_variance_l10",
        "team_blowout_factor_l10",
        "team_avg_minutes_starters_l10",
    ]
    for k in required:
        assert k in feats, f"Missing key: {k}"


def test_default_form_keys_complete():
    """_default_form returns all expected keys."""
    feats = _default_form("LAL", 10)
    required = [
        "team_quality_of_wins_l10",
        "team_strength_of_schedule_l10",
        "team_clutch_record_l10",
        "team_3pt_variance_l10",
        "team_blowout_factor_l10",
        "team_avg_minutes_starters_l10",
        "team_win_pct_l10",
        "team_form_games",
    ]
    for k in required:
        assert k in feats


def test_empty_schedule_returns_defaults(monkeypatch):
    """Empty schedule falls back to _default_form values."""
    import src.features.team_form as tf
    monkeypatch.setattr(tf, "_load_schedule", lambda a, s: [])

    feats = get_team_form_features("LAL", "2025-01-01", "2024-25")
    assert feats["team_form_games"] == 0
    assert feats["team_win_pct_l10"] == 0.5


def test_custom_window(monkeypatch):
    """Window parameter respected — window=5 uses only 5 most recent games."""
    target = datetime(2025, 3, 1)
    # 10 games: first 5 all losses, last 5 all wins
    games = _make_games(target, [
        (20, True,  "BOS", "L", -5),
        (18, False, "CLE", "L", -8),
        (16, True,  "DAL", "L", -3),
        (14, False, "DEN", "L", -12),
        (12, True,  "GSW", "L", -6),
        (8,  False, "HOU", "W",  4),
        (6,  True,  "IND", "W",  7),
        (4,  False, "LAC", "W",  3),
        (2,  True,  "MEM", "W", 10),
        (1,  False, "MIA", "W",  5),
    ])
    _inject_schedule(monkeypatch, "NYK", "2024-25", games)

    feats = get_team_form_features("NYK", target.strftime("%Y-%m-%d"), "2024-25", window=5)
    assert feats["team_win_pct_l5"] == 1.0  # last 5 all wins
    assert feats["team_form_games"] == 5
