"""
tests/test_garbage_time.py — Tests for garbage-time-aware rolling stats.

Covers:
  - is_garbage_time thresholds
  - estimate_garbage_minutes_per_game with synthetic boxscore/PBP
  - get_clean_rolling_avg < get_raw_rolling_avg for bench players in blowouts
  - Edge case: close game → garbage minutes ≈ 0
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import shutil
from unittest import mock

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.features.garbage_time_filter import (
    is_garbage_time,
    estimate_garbage_minutes_per_game,
    get_clean_rolling_avg,
    get_raw_rolling_avg,
    _GT_Q4_MARGIN,
    _GT_Q3_MARGIN,
    _Q4_TOTAL_SEC,
)


# ── is_garbage_time ──────────────────────────────────────────────────────────

class TestIsGarbageTime:
    def test_q4_over_threshold(self):
        assert is_garbage_time(30, 4, 400) is True

    def test_q4_at_exact_threshold(self):
        assert is_garbage_time(_GT_Q4_MARGIN, 4, 100) is True

    def test_q4_under_threshold(self):
        assert is_garbage_time(20, 4, 600) is False

    def test_q3_blowout(self):
        assert is_garbage_time(_GT_Q3_MARGIN, 3, 500) is True

    def test_q3_close(self):
        assert is_garbage_time(15, 3, 700) is False

    def test_q1_large_margin_not_garbage(self):
        # Q1 — even a 30-pt margin isn't garbage time
        assert is_garbage_time(35, 1, 600) is False

    def test_q2_large_margin_not_garbage(self):
        assert is_garbage_time(35, 2, 600) is False

    def test_close_game_q4(self):
        assert is_garbage_time(5, 4, 700) is False


# ── Synthetic fixture helpers ─────────────────────────────────────────────────

def _make_boxscore(game_id: str, home_score: int, away_score: int,
                   players: list[dict]) -> dict:
    return {
        "game_id": game_id,
        "home_team": "HOM",
        "away_team": "AWY",
        "home_score": home_score,
        "away_score": away_score,
        "game_status": "Final",
        "players": players,
        "total_players": len(players),
        "total_fga": 80,
    }


def _make_player(pid: int, name: str, starter: bool, minutes: float, pts: int = 10) -> dict:
    return {
        "player_id": pid, "player_name": name, "team_abbreviation": "HOM",
        "starter": starter, "min": minutes, "pts": pts,
        "reb": 2, "ast": 1, "stl": 0, "blk": 0, "tov": 1,
        "fgm": 4, "fga": 8, "fg3m": 1, "fg3a": 3, "ftm": 1, "fta": 2,
        "plus_minus": 5 if starter else -5,
    }


def _make_q4_pbp(game_id: str, blowout_from_clock: int, margin: int = 28) -> list[dict]:
    """Minimal Q4 PBP that reaches blowout at blowout_from_clock."""
    events = [{"period": 4, "game_clock_sec": 0, "event_type": 0,
               "event_desc": "Start of 4th Period", "player_name": "",
               "team_abbrev": "", "score": "100-72", "score_margin": str(margin - 5)}]
    if blowout_from_clock > 0:
        events.append({
            "period": 4, "game_clock_sec": blowout_from_clock,
            "event_type": 1, "event_desc": "Some Shot",
            "player_name": "BenchGuy", "team_abbrev": "HOM",
            "score": "", "score_margin": str(margin),
        })
    else:
        events[0]["score_margin"] = str(margin)

    events.append({
        "period": 4, "game_clock_sec": 720, "event_type": 13,
        "event_desc": "End of 4th Period", "player_name": "",
        "team_abbrev": "", "score": "120-85", "score_margin": str(margin),
    })
    return events


# ── estimate_garbage_minutes_per_game ─────────────────────────────────────────

class TestEstimateGarbageMinutes:
    """Uses a temp dir to isolate NBA cache reads."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.orig_cache = None

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_boxscore(self, game_id: str, data: dict):
        path = os.path.join(self.tmpdir, f"boxscore_{game_id}.json")
        with open(path, "w") as f:
            json.dump(data, f)

    def _write_pbp(self, game_id: str, period: int, data: list):
        path = os.path.join(self.tmpdir, f"pbp_{game_id}_p{period}.json")
        with open(path, "w") as f:
            json.dump(data, f)

    def test_blowout_bench_player_gets_garbage_minutes(self):
        """20-min bench player in a 35-pt blowout should receive >0 garbage minutes."""
        game_id = "TESTG001"
        players = [
            _make_player(1001, "Star1",  starter=True,  minutes=25),
            _make_player(1002, "Star2",  starter=True,  minutes=28),
            _make_player(2001, "Bench1", starter=False, minutes=20),
            _make_player(2002, "Bench2", starter=False, minutes=15),
        ]
        bs = _make_boxscore(game_id, 130, 95, players)  # 35-pt blowout
        self._write_boxscore(game_id, bs)
        # Provide Q4 PBP showing blowout from clock=100
        pbp = _make_q4_pbp(game_id, blowout_from_clock=100, margin=35)
        self._write_pbp(game_id, 4, pbp)

        with mock.patch("src.features.garbage_time_filter._NBA_CACHE", self.tmpdir):
            result = estimate_garbage_minutes_per_game(game_id)

        assert isinstance(result, dict)
        bench_ids = {2001, 2002}
        assert any(pid in bench_ids for pid in result), \
            f"Expected bench player IDs in garbage map, got {result}"
        for pid, gmin in result.items():
            assert gmin > 0, f"Player {pid} should have >0 garbage minutes"
            assert gmin <= 25, f"Player {pid} garbage min {gmin} exceeds starter max"

    def test_close_game_no_garbage_minutes(self):
        """A competitive 3-point game should yield zero garbage minutes."""
        game_id = "TESTG002"
        players = [
            _make_player(1001, "Star1",  starter=True,  minutes=38),
            _make_player(2001, "Bench1", starter=False, minutes=16),
        ]
        bs = _make_boxscore(game_id, 112, 109, players)  # 3-pt game
        self._write_boxscore(game_id, bs)
        # Q4 PBP — margin stays at 3, never hits threshold
        pbp = [
            {"period": 4, "game_clock_sec": 0,   "event_type": 0, "event_desc": "Start of 4th",
             "player_name": "", "team_abbrev": "", "score": "100-97", "score_margin": "3"},
            {"period": 4, "game_clock_sec": 720,  "event_type": 13, "event_desc": "End of 4th",
             "player_name": "", "team_abbrev": "", "score": "112-109", "score_margin": "3"},
        ]
        self._write_pbp(game_id, 4, pbp)

        with mock.patch("src.features.garbage_time_filter._NBA_CACHE", self.tmpdir):
            result = estimate_garbage_minutes_per_game(game_id)

        assert result == {}, f"Expected empty map for close game, got {result}"

    def test_missing_boxscore_returns_empty(self):
        """Missing boxscore file → return empty dict gracefully."""
        with mock.patch("src.features.garbage_time_filter._NBA_CACHE", self.tmpdir):
            result = estimate_garbage_minutes_per_game("NONEXISTENT_GAME")
        assert result == {}


# ── get_clean_rolling_avg ─────────────────────────────────────────────────────

class TestCleanRollingAvg:
    """Synthetic gamelog + pre-loaded garbage cache to verify clean < raw for bench players."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.gt_cache_dir = os.path.join(self.tmpdir, "cache", "garbage_time")
        os.makedirs(self.gt_cache_dir, exist_ok=True)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_gamelog(self, player_id: int, season: str, games: list[dict]):
        path = os.path.join(self.tmpdir, f"gamelog_full_{player_id}_{season}.json")
        with open(path, "w") as f:
            json.dump(games, f)

    def _write_gt_cache(self, season: str, data: dict):
        path = os.path.join(self.gt_cache_dir, f"{season}.json")
        with open(path, "w") as f:
            json.dump(data, f)

    def test_clean_avg_lower_than_raw_for_blowout_bench(self):
        """
        Bench player plays 20 min with 15 pts in a blowout.
        Cache says 8 min of those 20 were garbage → clean pts = 15 * (12/20) = 9.
        Clean rolling avg should be strictly less than raw rolling avg.
        """
        player_id = 5001
        season    = "2024-25"

        # 10 games — all blowout bench appearances with 20 min / 15 pts
        games = []
        for i in range(10):
            games.append({
                "game_id":   f"BLOWOUT{i:04d}",
                "game_date": f"Jan {i+1:02d}, 2025",
                "matchup":   "TST vs OPP",
                "wl":        "W",
                "min":       20.0,
                "pts":       15,
                "reb":       4, "ast": 2, "stl": 1, "blk": 0, "tov": 1,
                "plus_minus": -3,
            })
        self._write_gamelog(player_id, season, games)

        # Garbage cache: each game has 8 garbage minutes for this player
        gt_cache = {
            f"BLOWOUT{i:04d}": {str(player_id): 8.0}
            for i in range(10)
        }
        self._write_gt_cache(season, gt_cache)

        with mock.patch("src.features.garbage_time_filter._NBA_CACHE", self.tmpdir), \
             mock.patch("src.features.garbage_time_filter._GT_CACHE_DIR", self.gt_cache_dir):
            raw   = get_raw_rolling_avg(player_id, "pts", season, "Feb 01, 2025", n_games=10)
            clean = get_clean_rolling_avg(player_id, "pts", season, "Feb 01, 2025", n_games=10)

        assert raw   == pytest.approx(15.0, abs=0.1), f"Raw avg should be 15.0, got {raw}"
        assert clean < raw, f"Clean avg {clean} should be < raw avg {raw}"
        # clean = 15 * (12/20) = 9.0
        assert clean == pytest.approx(9.0, abs=0.1), f"Expected clean avg ≈ 9.0, got {clean}"

    def test_no_garbage_clean_equals_raw(self):
        """If no garbage time in cache, clean avg equals raw avg."""
        player_id = 5002
        season    = "2024-25"

        games = [
            {"game_id": f"CLEAN{i:04d}", "game_date": f"Jan {i+1:02d}, 2025",
             "matchup": "TST vs OPP", "wl": "W", "min": 35.0, "pts": 28,
             "reb": 7, "ast": 8, "stl": 2, "blk": 1, "tov": 3, "plus_minus": 10}
            for i in range(10)
        ]
        self._write_gamelog(player_id, season, games)
        # Empty garbage cache (no games have garbage)
        self._write_gt_cache(season, {})

        with mock.patch("src.features.garbage_time_filter._NBA_CACHE", self.tmpdir), \
             mock.patch("src.features.garbage_time_filter._GT_CACHE_DIR", self.gt_cache_dir):
            raw   = get_raw_rolling_avg(player_id, "pts", season, "Feb 01, 2025")
            clean = get_clean_rolling_avg(player_id, "pts", season, "Feb 01, 2025")

        assert raw   == pytest.approx(28.0, abs=0.01)
        assert clean == pytest.approx(28.0, abs=0.01)

    def test_missing_gamelog_returns_zero(self):
        """Missing gamelog file → returns 0.0 without crashing."""
        with mock.patch("src.features.garbage_time_filter._NBA_CACHE", self.tmpdir), \
             mock.patch("src.features.garbage_time_filter._GT_CACHE_DIR", self.gt_cache_dir):
            result = get_clean_rolling_avg(9999, "pts", "2024-25", "Jan 01, 2025")
        assert result == 0.0

    def test_through_date_filter(self):
        """Only games strictly before through_date should be included."""
        player_id = 5003
        season    = "2024-25"

        games = [
            {"game_id": "DT0001", "game_date": "Jan 10, 2025",
             "min": 30.0, "pts": 20, "reb": 5, "ast": 3,
             "stl": 1, "blk": 0, "tov": 2, "wl": "W", "matchup": "X", "plus_minus": 5},
            {"game_id": "DT0002", "game_date": "Jan 15, 2025",  # after cutoff
             "min": 30.0, "pts": 40, "reb": 5, "ast": 3,
             "stl": 1, "blk": 0, "tov": 2, "wl": "W", "matchup": "X", "plus_minus": 5},
        ]
        self._write_gamelog(player_id, season, games)
        self._write_gt_cache(season, {})

        with mock.patch("src.features.garbage_time_filter._NBA_CACHE", self.tmpdir), \
             mock.patch("src.features.garbage_time_filter._GT_CACHE_DIR", self.gt_cache_dir):
            raw = get_raw_rolling_avg(player_id, "pts", season, "Jan 12, 2025")

        # Only Jan 10 game should be included (Jan 15 is after cutoff)
        assert raw == pytest.approx(20.0, abs=0.01)
