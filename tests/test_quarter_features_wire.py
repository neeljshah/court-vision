"""tests/test_quarter_features_wire.py — quarter_features loader + inplay wiring.

Known fixture: game_id='0022400001', player_id=1642258 (Zaccharie Risacher),
team_id=1610612737 (Atlanta Hawks), present in data/cache/quarter_features.parquet.
"""
from __future__ import annotations

import pytest

# ── loader ────────────────────────────────────────────────────────────────────

def test_load_quarter_features_nonempty():
    from src.data.quarter_features_loader import load_quarter_features, reset_cache
    reset_cache()
    df = load_quarter_features()
    assert not df.empty, "quarter_features parquet should load at least one row"
    assert "q1_usg" in df.columns
    assert "halftime_pace_shift" in df.columns
    assert "trailing_team_q4_usg_concentration" in df.columns


def test_get_quarter_row_known():
    from src.data.quarter_features_loader import get_quarter_row, reset_cache
    reset_cache()
    row = get_quarter_row("0022400001", 1642258)
    assert row is not None, "expected row for game 0022400001 / player 1642258"
    assert row["player_id"] == 1642258
    assert row["game_id"] == "0022400001"
    assert row["team_id"] == 1610612737
    # sanity-check a few numeric fields are present and finite
    import math
    assert not math.isnan(float(row["q1_usg"]))
    assert not math.isnan(float(row["halftime_pace_shift"]))


def test_get_quarter_row_missing():
    from src.data.quarter_features_loader import get_quarter_row, reset_cache
    reset_cache()
    row = get_quarter_row("0000000000", 0)
    assert row is None, "unknown (game_id, player_id) should return None"


def test_get_team_quarter_summary_structure():
    from src.data.quarter_features_loader import get_team_quarter_summary, reset_cache
    reset_cache()
    summary = get_team_quarter_summary("0022400001", 1610612737)
    assert summary, "expected non-empty summary for known (game_id, team_id)"
    expected_keys = {
        "game_id", "team_id", "n_players",
        "q1_pts_total", "q2_pts_total", "q3_pts_total", "q4_pts_total",
        "first_half_pts", "second_half_pts",
        "avg_q1_usg", "avg_halftime_pace_shift", "avg_trailing_team_q4_usg_hhi",
    }
    assert expected_keys.issubset(summary.keys()), (
        f"missing keys: {expected_keys - summary.keys()}"
    )
    assert summary["n_players"] > 0
    # first_half = q1 + q2
    assert abs(summary["first_half_pts"] - (summary["q1_pts_total"] + summary["q2_pts_total"])) < 1e-6
    assert 0.0 <= summary["avg_q1_usg"] <= 1.0, "q1_usg should be in [0, 1]"


def test_get_team_quarter_summary_missing():
    from src.data.quarter_features_loader import get_team_quarter_summary, reset_cache
    reset_cache()
    summary = get_team_quarter_summary("0000000000", 0)
    assert summary == {}, "missing team should return empty dict"


# ── inplay wiring ─────────────────────────────────────────────────────────────

def test_inject_quarter_features_adds_keys():
    from src.prediction.quarter_feature_helper import inject_quarter_features
    base = {"score_margin": 3.0, "total_pts": 47.0}
    result = inject_quarter_features(1610612737, "0022400001", base)
    assert result is base, "inject_quarter_features should modify in-place and return same dict"
    assert "q1_usg_avg" in result
    assert "halftime_pace_shift" in result
    assert "trailing_team_q4_usg_hhi" in result


def test_inject_quarter_features_noop_on_missing_game():
    from src.prediction.quarter_feature_helper import inject_quarter_features
    base = {"score_margin": 0.0}
    result = inject_quarter_features(0, "0000000000", base)
    # Should not add keys for missing game, but should not raise either.
    assert isinstance(result, dict)


def test_features_from_snapshot_quarter_inject():
    """features_from_snapshot should add quarter keys when game_id is present."""
    from src.prediction.inplay_winprob import features_from_snapshot
    snap = {
        "period": 3,
        "clock": 12.0,
        "home_q1": 28, "home_q2": 25,
        "away_q1": 24, "away_q2": 27,
        "home_team_id": 1610612737,
        "away_team_id": 1610612738,
        "game_id": "0022400001",
        "season": "2024-25",
        "pregame_win_prob": 0.55,
    }
    feats = features_from_snapshot(snap, inject_quarter=True)
    # Core v1 keys must still be present
    assert "score_margin" in feats
    assert "pace_so_far" in feats
    # Quarter keys should be injected (game_id exists in parquet)
    assert "q1_usg_avg" in feats
    assert "halftime_pace_shift" in feats
    assert "trailing_team_q4_usg_hhi" in feats


def test_features_from_snapshot_no_inject():
    """inject_quarter=False must suppress quarter key injection."""
    from src.prediction.inplay_winprob import features_from_snapshot
    snap = {
        "period": 3,
        "clock": 12.0,
        "home_q1": 28, "home_q2": 25,
        "away_q1": 24, "away_q2": 27,
        "home_team_id": 1610612737,
        "game_id": "0022400001",
        "season": "2024-25",
    }
    feats = features_from_snapshot(snap, inject_quarter=False)
    assert "q1_usg_avg" not in feats
    assert "halftime_pace_shift" not in feats


def test_features_from_snapshot_no_game_id():
    """When game_id is absent, quarter injection silently skips."""
    from src.prediction.inplay_winprob import features_from_snapshot
    snap = {
        "period": 3,
        "clock": 12.0,
        "home_q1": 28, "home_q2": 25,
        "away_q1": 24, "away_q2": 27,
        "home_team_id": 1610612737,
        "season": "2024-25",
    }
    feats = features_from_snapshot(snap, inject_quarter=True)
    # No crash + core keys present
    assert "score_margin" in feats
    assert "q1_usg_avg" not in feats
