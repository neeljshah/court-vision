"""Tests for src/data/live.py — shared live game state helpers (cycle 88).

The downstream cycle-88 agents (predict_in_game, foul_trouble_adjust,
blowout_adjust, live_run) all import from this module. Tests here protect
the contract those agents rely on.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.data.live import (  # noqa: E402
    _name_key, _strip_accents,
    load_live_state, latest_snapshot_path, list_today_snapshots, live_dir,
    parse_clock, period_length_minutes,
    elapsed_game_minutes, remaining_game_minutes, clock_share_played,
    find_player, find_player_by_id, starters,
    score_margin, absolute_margin, is_blowout, is_live, is_final,
)


def _player(name, pid, team="LAL", is_starter=True, **kwargs):
    base = {"name": name, "player_id": pid, "team": team,
            "is_starter": is_starter,
            "min": 14.5, "pts": 12, "reb": 4, "ast": 3,
            "fg3m": 2, "stl": 1, "blk": 0, "tov": 1, "pf": 2}
    base.update(kwargs)
    return base


def _snapshot(period=2, clock="5:30", home_score=56, away_score=48,
              home_team="LAL", away_team="OKC", status="LIVE",
              players=None):
    return {
        "game_id": "0022400123", "captured_at": "2026-05-24T19:42:00",
        "game_status": status, "period": period, "clock": clock,
        "home_score": home_score, "away_score": away_score,
        "home_team": home_team, "away_team": away_team,
        "players": players if players is not None else [
            _player("LeBron James", 2544, team=home_team),
            _player("Shai Gilgeous-Alexander", 4387, team=away_team),
        ],
    }


# ── name key / accents ──────────────────────────────────────────────────────

def test_name_key_strips_diacritics():
    assert _name_key("Nikola Jokić") == "nikola jokic"
    assert _name_key("Luka Dončić") == "luka doncic"
    assert _name_key("  LEBRON JAMES  ") == "lebron james"
    assert _name_key(None) == ""


# ── file discovery ──────────────────────────────────────────────────────────

def test_latest_snapshot_path_picks_chronological_last():
    with tempfile.TemporaryDirectory() as tmp:
        live_root = os.path.join(tmp, "data", "live")
        os.makedirs(live_root)
        # Three snapshots — lex sort gives chronological order.
        for ts in ("2026-05-24T19-00-00", "2026-05-24T19-30-00", "2026-05-24T20-00-00"):
            with open(os.path.join(live_root, f"0022400123_{ts}.json"), "w") as fh:
                json.dump({}, fh)
        latest = latest_snapshot_path("0022400123", project_dir=tmp)
        assert latest.endswith("2026-05-24T20-00-00.json")


def test_latest_snapshot_path_returns_none_when_no_snapshots():
    with tempfile.TemporaryDirectory() as tmp:
        assert latest_snapshot_path("0022400123", project_dir=tmp) is None


def test_load_live_state_handles_missing_or_malformed():
    assert load_live_state(None) == {}
    assert load_live_state("") == {}
    assert load_live_state("/tmp/never_exists_xyz.json") == {}
    fh = tempfile.NamedTemporaryFile("w", delete=False, suffix=".json",
                                       encoding="utf-8")
    fh.write("{not-json"); fh.close()
    try:
        assert load_live_state(fh.name) == {}
    finally:
        os.unlink(fh.name)


# ── time math ───────────────────────────────────────────────────────────────

def test_parse_clock_mm_ss_format():
    assert parse_clock("5:30") == pytest.approx(5.5)
    assert parse_clock("0:00") == pytest.approx(0.0)
    assert parse_clock("12:00") == pytest.approx(12.0)
    assert parse_clock("0:45") == pytest.approx(0.75)


def test_parse_clock_handles_garbage():
    assert parse_clock(None) == 0.0
    assert parse_clock("") == 0.0
    assert parse_clock("garbage") == 0.0
    # Bare numeric strings are interpreted as minutes
    assert parse_clock("7") == pytest.approx(7.0)


def test_period_length_regulation_vs_ot():
    assert period_length_minutes(1) == 12.0
    assert period_length_minutes(4) == 12.0
    assert period_length_minutes(5) == 5.0    # OT
    assert period_length_minutes(7) == 5.0    # 3OT


def test_elapsed_minutes_q2_with_eight_remaining():
    """Q2 with 8:00 on the clock -> 12 (Q1) + 4 (Q2 elapsed) = 16 elapsed."""
    assert elapsed_game_minutes(2, "8:00") == pytest.approx(16.0)


def test_elapsed_minutes_q4_late():
    """Q4 with 2:00 on the clock -> 36 (Q1-Q3) + 10 (Q4 elapsed) = 46."""
    assert elapsed_game_minutes(4, "2:00") == pytest.approx(46.0)


def test_elapsed_minutes_pre_game():
    """Period 1 with full 12:00 = 0 elapsed."""
    assert elapsed_game_minutes(1, "12:00") == pytest.approx(0.0)


def test_remaining_minutes_inverse_of_elapsed():
    """remaining + elapsed = 48 for regulation."""
    for period in (1, 2, 3, 4):
        for clock in ("12:00", "5:30", "1:00", "0:00"):
            assert (remaining_game_minutes(period, clock)
                    + elapsed_game_minutes(period, clock)) == pytest.approx(48.0)


def test_clock_share_played_is_bounded():
    assert clock_share_played(1, "12:00") == 0.0
    assert clock_share_played(4, "0:00") == 1.0
    assert clock_share_played(2, "6:00") == pytest.approx(18 / 48)


# ── player lookup ───────────────────────────────────────────────────────────

def test_find_player_diacritic_insensitive():
    snap = _snapshot(players=[_player("Nikola Jokić", 203999, team="DEN")])
    assert find_player(snap, "Nikola Jokic")["player_id"] == 203999
    assert find_player(snap, "NIKOLA JOKIC")["player_id"] == 203999
    assert find_player(snap, "Stephen Curry") is None


def test_find_player_by_id_coerces_string():
    snap = _snapshot(players=[_player("LeBron James", 2544)])
    assert find_player_by_id(snap, 2544)["name"] == "LeBron James"
    assert find_player_by_id(snap, "2544")["name"] == "LeBron James"
    assert find_player_by_id(snap, 999) is None


def test_starters_filter_by_team_and_starter_flag():
    snap = _snapshot(players=[
        _player("Starter A", 1, team="LAL", is_starter=True),
        _player("Bench A", 2, team="LAL", is_starter=False),
        _player("Starter B", 3, team="OKC", is_starter=True),
    ])
    all_starters = starters(snap)
    assert len(all_starters) == 2
    lal = starters(snap, team="LAL")
    assert len(lal) == 1
    assert lal[0]["name"] == "Starter A"


# ── score / game state ─────────────────────────────────────────────────────

def test_score_margin_home_perspective():
    snap = _snapshot(home_score=110, away_score=95)
    assert score_margin(snap, "home") == 15
    assert score_margin(snap, "away") == -15
    assert absolute_margin(snap) == 15


def test_is_blowout_only_triggers_in_Q4():
    """Margin of 25 in Q1 is NOT a blowout — could swing back."""
    snap = _snapshot(period=1, home_score=40, away_score=15)
    assert not is_blowout(snap, threshold=20)
    snap_q4 = _snapshot(period=4, home_score=40, away_score=15)
    assert is_blowout(snap_q4, threshold=20)


def test_is_blowout_respects_threshold():
    snap = _snapshot(period=4, home_score=95, away_score=80)
    assert not is_blowout(snap, threshold=20)
    assert is_blowout(snap, threshold=10)


def test_is_live_and_is_final():
    assert is_live(_snapshot(status="LIVE"))
    assert not is_live(_snapshot(status="FINAL"))
    assert is_final(_snapshot(status="FINAL"))
    assert not is_final(_snapshot(status="LIVE"))
    # Missing status defaults to neither
    assert not is_live({})
    assert not is_final({})


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
