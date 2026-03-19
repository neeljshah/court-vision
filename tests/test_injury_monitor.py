"""
Tests for src/data/injury_monitor.py — Injury Monitor.

All tests mock ESPN network calls. No external requests are made.
"""

from __future__ import annotations

import json
import os
import sys
import time
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Fixtures ───────────────────────────────────────────────────────────────────

SAMPLE_INJURIES = [
    {
        "player_name":    "LeBron James",
        "player_id_espn": "1966",
        "team_name":      "Los Angeles Lakers",
        "team_abbrev":    "LAL",
        "status":         "Out",
        "short_comment":  "Ankle sprain",
        "long_comment":   "Out indefinitely",
        "injury_date":    "2026-03-15",
        "injury_type":    "Ankle",
    },
    {
        "player_name":    "Anthony Davis",
        "player_id_espn": "6583",
        "team_name":      "Los Angeles Lakers",
        "team_abbrev":    "LAL",
        "status":         "Questionable",
        "short_comment":  "Knee soreness",
        "long_comment":   "",
        "injury_date":    "2026-03-16",
        "injury_type":    "Knee",
    },
    {
        "player_name":    "Jayson Tatum",
        "player_id_espn": "4065648",
        "team_name":      "Boston Celtics",
        "team_abbrev":    "BOS",
        "status":         "Doubtful",
        "short_comment":  "Wrist",
        "long_comment":   "",
        "injury_date":    "2026-03-17",
        "injury_type":    "Wrist",
    },
    {
        "player_name":    "Nikola Jokic",
        "player_id_espn": "3112335",
        "team_name":      "Denver Nuggets",
        "team_abbrev":    "DEN",
        "status":         "Probable",
        "short_comment":  "",
        "long_comment":   "",
        "injury_date":    "",
        "injury_type":    "",
    },
]


def _write_cache(path: str, injuries: list, fetched_at: str = "2026-03-17T10:00:00+00:00") -> None:
    data = {"fetched_at": fetched_at, "source": "espn", "injuries": injuries}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


# ── _norm_name() ──────────────────────────────────────────────────────────────

class TestNormName:

    def test_lowercases(self):
        from src.data.injury_monitor import _norm_name
        assert _norm_name("LeBron James") == "lebron james"

    def test_strips_accents(self):
        from src.data.injury_monitor import _norm_name
        assert _norm_name("Nikola Jokić") == "nikola jokic"

    def test_strips_whitespace(self):
        from src.data.injury_monitor import _norm_name
        assert _norm_name("  Joel Embiid  ") == "joel embiid"


# ── _norm_status() ────────────────────────────────────────────────────────────

class TestNormStatus:

    @pytest.mark.parametrize("raw,expected", [
        ("out",          "Out"),
        ("Out",          "Out"),
        ("doubtful",     "Doubtful"),
        ("questionable", "Questionable"),
        ("day-to-day",   "Day-To-Day"),
        ("probable",     "Probable"),
        ("available",    "Available"),
        ("active",       "Available"),
        ("healthy",      "Available"),
        ("Unknown Status", "Unknown Status"),
    ])
    def test_status_mapping(self, raw, expected):
        from src.data.injury_monitor import _norm_status
        assert _norm_status(raw) == expected


# ── get_injury_status() ───────────────────────────────────────────────────────

class TestGetInjuryStatus:

    def test_out_player_returns_out(self, tmp_path, monkeypatch):
        """Player with Out status → status == 'Out', found == True."""
        import src.data.injury_monitor as im
        cache_path = str(tmp_path / "nba" / "injury_report.json")
        _write_cache(cache_path, SAMPLE_INJURIES)
        monkeypatch.setattr(im, "_CACHE_PATH", cache_path)
        monkeypatch.setattr(im, "_cache_is_fresh", lambda: True)

        result = im.get_injury_status("LeBron James")
        assert result["status"] == "Out"
        assert result["found"] is True

    def test_questionable_player(self, tmp_path, monkeypatch):
        """Player with Questionable status."""
        import src.data.injury_monitor as im
        cache_path = str(tmp_path / "nba" / "injury_report.json")
        _write_cache(cache_path, SAMPLE_INJURIES)
        monkeypatch.setattr(im, "_CACHE_PATH", cache_path)
        monkeypatch.setattr(im, "_cache_is_fresh", lambda: True)

        result = im.get_injury_status("Anthony Davis")
        assert result["status"] == "Questionable"
        assert result["found"] is True

    def test_doubtful_player(self, tmp_path, monkeypatch):
        """Player with Doubtful status."""
        import src.data.injury_monitor as im
        cache_path = str(tmp_path / "nba" / "injury_report.json")
        _write_cache(cache_path, SAMPLE_INJURIES)
        monkeypatch.setattr(im, "_CACHE_PATH", cache_path)
        monkeypatch.setattr(im, "_cache_is_fresh", lambda: True)

        result = im.get_injury_status("Jayson Tatum")
        assert result["status"] == "Doubtful"

    def test_probable_player(self, tmp_path, monkeypatch):
        """Player with Probable status."""
        import src.data.injury_monitor as im
        cache_path = str(tmp_path / "nba" / "injury_report.json")
        _write_cache(cache_path, SAMPLE_INJURIES)
        monkeypatch.setattr(im, "_CACHE_PATH", cache_path)
        monkeypatch.setattr(im, "_cache_is_fresh", lambda: True)

        result = im.get_injury_status("Nikola Jokic")
        assert result["status"] == "Probable"

    def test_player_not_in_list_returns_available(self, tmp_path, monkeypatch):
        """Player not in injury list → status == 'Available', found == False."""
        import src.data.injury_monitor as im
        cache_path = str(tmp_path / "nba" / "injury_report.json")
        _write_cache(cache_path, SAMPLE_INJURIES)
        monkeypatch.setattr(im, "_CACHE_PATH", cache_path)
        monkeypatch.setattr(im, "_cache_is_fresh", lambda: True)

        result = im.get_injury_status("Stephen Curry")
        assert result["status"] == "Available"
        assert result["found"] is False

    def test_accent_insensitive_lookup(self, tmp_path, monkeypatch):
        """Accented name lookup works via norm."""
        import src.data.injury_monitor as im
        injuries = [{"player_name": "Nikola Jokić", "player_id_espn": "1",
                     "team_name": "Denver Nuggets", "team_abbrev": "DEN",
                     "status": "Probable", "short_comment": "", "long_comment": "",
                     "injury_date": "", "injury_type": ""}]
        cache_path = str(tmp_path / "nba" / "injury_report.json")
        _write_cache(cache_path, injuries)
        monkeypatch.setattr(im, "_CACHE_PATH", cache_path)
        monkeypatch.setattr(im, "_cache_is_fresh", lambda: True)

        # Query without accent
        result = im.get_injury_status("Nikola Jokic")
        assert result["found"] is True

    def test_result_has_required_keys(self, tmp_path, monkeypatch):
        """get_injury_status always returns dict with player_name, status, comment, team_abbrev, found."""
        import src.data.injury_monitor as im
        cache_path = str(tmp_path / "nba" / "injury_report.json")
        _write_cache(cache_path, SAMPLE_INJURIES)
        monkeypatch.setattr(im, "_CACHE_PATH", cache_path)
        monkeypatch.setattr(im, "_cache_is_fresh", lambda: True)

        result = im.get_injury_status("LeBron James")
        for key in ("player_name", "status", "comment", "team_abbrev", "found"):
            assert key in result


# ── is_available() ────────────────────────────────────────────────────────────

class TestIsAvailable:

    def test_out_player_is_not_available(self, tmp_path, monkeypatch):
        """OUT player → is_available == False."""
        import src.data.injury_monitor as im
        cache_path = str(tmp_path / "nba" / "injury_report.json")
        _write_cache(cache_path, SAMPLE_INJURIES)
        monkeypatch.setattr(im, "_CACHE_PATH", cache_path)
        monkeypatch.setattr(im, "_cache_is_fresh", lambda: True)

        assert im.is_available("LeBron James") is False

    def test_doubtful_player_is_not_available(self, tmp_path, monkeypatch):
        """Doubtful player → is_available == False."""
        import src.data.injury_monitor as im
        cache_path = str(tmp_path / "nba" / "injury_report.json")
        _write_cache(cache_path, SAMPLE_INJURIES)
        monkeypatch.setattr(im, "_CACHE_PATH", cache_path)
        monkeypatch.setattr(im, "_cache_is_fresh", lambda: True)

        assert im.is_available("Jayson Tatum") is False

    def test_questionable_player_is_available(self, tmp_path, monkeypatch):
        """Questionable player → is_available == True (not Out/Doubtful)."""
        import src.data.injury_monitor as im
        cache_path = str(tmp_path / "nba" / "injury_report.json")
        _write_cache(cache_path, SAMPLE_INJURIES)
        monkeypatch.setattr(im, "_CACHE_PATH", cache_path)
        monkeypatch.setattr(im, "_cache_is_fresh", lambda: True)

        assert im.is_available("Anthony Davis") is True

    def test_healthy_player_is_available(self, tmp_path, monkeypatch):
        """Player not in list → is_available == True."""
        import src.data.injury_monitor as im
        cache_path = str(tmp_path / "nba" / "injury_report.json")
        _write_cache(cache_path, SAMPLE_INJURIES)
        monkeypatch.setattr(im, "_CACHE_PATH", cache_path)
        monkeypatch.setattr(im, "_cache_is_fresh", lambda: True)

        assert im.is_available("Stephen Curry") is True

    def test_probable_player_is_available(self, tmp_path, monkeypatch):
        """Probable player → is_available == True."""
        import src.data.injury_monitor as im
        cache_path = str(tmp_path / "nba" / "injury_report.json")
        _write_cache(cache_path, SAMPLE_INJURIES)
        monkeypatch.setattr(im, "_CACHE_PATH", cache_path)
        monkeypatch.setattr(im, "_cache_is_fresh", lambda: True)

        assert im.is_available("Nikola Jokic") is True


# ── get_team_injuries() ───────────────────────────────────────────────────────

class TestGetTeamInjuries:

    def test_lal_has_two_injured_players(self, tmp_path, monkeypatch):
        """LAL has 2 players in sample injuries."""
        import src.data.injury_monitor as im
        cache_path = str(tmp_path / "nba" / "injury_report.json")
        _write_cache(cache_path, SAMPLE_INJURIES)
        monkeypatch.setattr(im, "_CACHE_PATH", cache_path)
        monkeypatch.setattr(im, "_cache_is_fresh", lambda: True)

        result = im.get_team_injuries("LAL")
        assert len(result) == 2

    def test_team_with_no_injuries_returns_empty(self, tmp_path, monkeypatch):
        """Team with no entries returns empty list."""
        import src.data.injury_monitor as im
        cache_path = str(tmp_path / "nba" / "injury_report.json")
        _write_cache(cache_path, SAMPLE_INJURIES)
        monkeypatch.setattr(im, "_CACHE_PATH", cache_path)
        monkeypatch.setattr(im, "_cache_is_fresh", lambda: True)

        result = im.get_team_injuries("GSW")
        assert result == []

    def test_case_insensitive_abbrev(self, tmp_path, monkeypatch):
        """Team abbreviation lookup is case-insensitive."""
        import src.data.injury_monitor as im
        cache_path = str(tmp_path / "nba" / "injury_report.json")
        _write_cache(cache_path, SAMPLE_INJURIES)
        monkeypatch.setattr(im, "_CACHE_PATH", cache_path)
        monkeypatch.setattr(im, "_cache_is_fresh", lambda: True)

        result_lower = im.get_team_injuries("lal")
        result_upper = im.get_team_injuries("LAL")
        assert len(result_lower) == len(result_upper)


# ── refresh() with stale/missing cache ───────────────────────────────────────

class TestRefresh:

    def test_fresh_cache_not_refetched(self, tmp_path, monkeypatch):
        """refresh() returns cached data without calling ESPN when cache is fresh."""
        import src.data.injury_monitor as im
        cache_path = str(tmp_path / "nba" / "injury_report.json")
        _write_cache(cache_path, SAMPLE_INJURIES)
        monkeypatch.setattr(im, "_CACHE_PATH", cache_path)
        monkeypatch.setattr(im, "_cache_is_fresh", lambda: True)

        call_count = {"n": 0}

        import requests as req_mod
        original_get = req_mod.get

        def _no_network(*a, **kw):
            call_count["n"] += 1
            raise AssertionError("Should not call network when cache is fresh")

        monkeypatch.setattr(req_mod, "get", _no_network)

        result = im.refresh()
        assert "injuries" in result
        assert call_count["n"] == 0

    def test_espn_error_with_stale_cache_returns_stale(self, tmp_path, monkeypatch):
        """When ESPN fetch fails but stale cache exists, refresh() returns stale data."""
        import src.data.injury_monitor as im
        import requests as req_mod

        cache_path = str(tmp_path / "nba" / "injury_report.json")
        _write_cache(cache_path, SAMPLE_INJURIES)
        monkeypatch.setattr(im, "_CACHE_PATH", cache_path)
        monkeypatch.setattr(im, "_cache_is_fresh", lambda: False)

        def _fail(*a, **kw):
            raise ConnectionError("ESPN down")

        monkeypatch.setattr(req_mod, "get", _fail)

        result = im.refresh()
        assert len(result["injuries"]) == len(SAMPLE_INJURIES)

    def test_espn_error_no_cache_returns_empty(self, tmp_path, monkeypatch):
        """When ESPN fetch fails and no cache exists, refresh() returns empty injuries list."""
        import src.data.injury_monitor as im
        import requests as req_mod

        cache_path = str(tmp_path / "nba" / "injury_report.json")
        monkeypatch.setattr(im, "_CACHE_PATH", cache_path)
        monkeypatch.setattr(im, "_cache_is_fresh", lambda: False)

        def _fail(*a, **kw):
            raise ConnectionError("ESPN down")

        monkeypatch.setattr(req_mod, "get", _fail)

        result = im.refresh()
        assert result["injuries"] == []
