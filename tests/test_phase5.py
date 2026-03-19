"""
test_phase5.py — Phase 5 External Factors tests.

Covers:
  - src/data/injury_monitor.py  (3 tests)
  - src/data/ref_tracker.py     (4 tests)
  - src/data/line_monitor.py    (5 tests)

All tests use mocks / tmp_path — no real API or network calls.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


_INJURIES = [
    {
        "player_name": "LeBron James", "player_id_espn": "1966",
        "team_name": "Los Angeles Lakers", "team_abbrev": "LAL",
        "status": "Out", "short_comment": "Ankle", "long_comment": "",
        "injury_date": "2026-03-17", "injury_type": "Ankle",
    },
    {
        "player_name": "Anthony Davis", "player_id_espn": "6583",
        "team_name": "Los Angeles Lakers", "team_abbrev": "LAL",
        "status": "Questionable", "short_comment": "Knee", "long_comment": "",
        "injury_date": "2026-03-16", "injury_type": "Knee",
    },
]

_REF_PROFILES = {
    "Scott Foster": {
        "avg_fouls_per_game": 42.5,
        "home_win_pct":       0.55,
        "avg_pace":           98.3,
        "games_counted":      80,
    },
    "Tony Brothers": {
        "avg_fouls_per_game": 40.1,
        "home_win_pct":       0.48,
        "avg_pace":           99.1,
        "games_counted":      75,
    },
}

_LINES_CACHE = {
    "abc123": {
        "home_team":        "Boston Celtics",
        "away_team":        "Miami Heat",
        "commence_time":    "2026-03-18T00:00:00Z",
        "spread_home":      -6.5,
        "total_over":       215.5,
        "home_ml":          -260,
        "away_ml":          220,
        "bookmakers_count": 8,
        "fetched_at":       "2026-03-17T20:00:00+00:00",
    }
}

_OPENING_HISTORY = {
    "BOS_MIA": {
        "spread_home_open": -5.0,
        "total_open":       214.5,
        "recorded_at":      "2026-03-17T10:00:00+00:00",
    }
}


# ══════════════════════════════════════════════════════════════════════════════
# injury_monitor — 3 tests
# ══════════════════════════════════════════════════════════════════════════════

class TestInjuryMonitorPhase5:

    def test_out_player_is_not_available(self, tmp_path, monkeypatch):
        """Out player returns is_available == False."""
        import src.data.injury_monitor as im

        cache = str(tmp_path / "nba" / "injury_report.json")
        _write_json(cache, {"fetched_at": "2026-03-17T10:00:00+00:00",
                             "source": "espn", "injuries": _INJURIES})
        monkeypatch.setattr(im, "_CACHE_PATH", cache)
        monkeypatch.setattr(im, "_cache_is_fresh", lambda: True)

        assert im.is_available("LeBron James") is False

    def test_questionable_player_is_available(self, tmp_path, monkeypatch):
        """Questionable player returns is_available == True."""
        import src.data.injury_monitor as im

        cache = str(tmp_path / "nba" / "injury_report.json")
        _write_json(cache, {"fetched_at": "2026-03-17T10:00:00+00:00",
                             "source": "espn", "injuries": _INJURIES})
        monkeypatch.setattr(im, "_CACHE_PATH", cache)
        monkeypatch.setattr(im, "_cache_is_fresh", lambda: True)

        assert im.is_available("Anthony Davis") is True

    def test_network_failure_returns_empty_injuries(self, tmp_path, monkeypatch):
        """Network failure with no cache → returns empty injuries list."""
        import src.data.injury_monitor as im
        import requests as req_mod

        cache = str(tmp_path / "nba" / "injury_report.json")
        monkeypatch.setattr(im, "_CACHE_PATH", cache)
        monkeypatch.setattr(im, "_cache_is_fresh", lambda: False)
        monkeypatch.setattr(req_mod, "get", lambda *a, **kw: (_ for _ in ()).throw(ConnectionError("down")))

        result = im.refresh()
        assert result["injuries"] == []


# ══════════════════════════════════════════════════════════════════════════════
# ref_tracker — 4 tests
# ══════════════════════════════════════════════════════════════════════════════

class TestRefTracker:

    def test_get_ref_features_known_refs(self, tmp_path, monkeypatch):
        """get_ref_features returns averaged stats for known refs."""
        import src.data.ref_tracker as rt

        cache = str(tmp_path / "nba" / "ref_tendencies.json")
        _write_json(cache, _REF_PROFILES)
        monkeypatch.setattr(rt, "_CACHE_PATH", cache)

        result = rt.get_ref_features(["Scott Foster", "Tony Brothers"])
        assert result["refs_found"] == 2
        assert result["avg_fouls_per_game"] == pytest.approx(41.3, abs=0.1)
        assert result["home_win_pct"] == pytest.approx(0.515, abs=0.01)

    def test_get_ref_features_unknown_refs_returns_none(self, tmp_path, monkeypatch):
        """get_ref_features returns None fields when refs are not in cache."""
        import src.data.ref_tracker as rt

        cache = str(tmp_path / "nba" / "ref_tendencies.json")
        _write_json(cache, _REF_PROFILES)
        monkeypatch.setattr(rt, "_CACHE_PATH", cache)

        result = rt.get_ref_features(["Unknown Ref"])
        assert result["refs_found"] == 0
        assert result["avg_fouls_per_game"] is None
        assert result["home_win_pct"] is None

    def test_get_ref_features_partial_crew(self, tmp_path, monkeypatch):
        """get_ref_features handles a crew where only some refs are known."""
        import src.data.ref_tracker as rt

        cache = str(tmp_path / "nba" / "ref_tendencies.json")
        _write_json(cache, _REF_PROFILES)
        monkeypatch.setattr(rt, "_CACHE_PATH", cache)

        result = rt.get_ref_features(["Scott Foster", "Ghost Ref"])
        assert result["refs_found"] == 1
        assert result["avg_fouls_per_game"] == pytest.approx(42.5)
        assert result["refs_total"] == 2

    def test_get_all_refs_returns_sorted_list(self, tmp_path, monkeypatch):
        """get_all_refs returns sorted list of referee names."""
        import src.data.ref_tracker as rt

        cache = str(tmp_path / "nba" / "ref_tendencies.json")
        _write_json(cache, _REF_PROFILES)
        monkeypatch.setattr(rt, "_CACHE_PATH", cache)

        refs = rt.get_all_refs()
        assert refs == sorted(_REF_PROFILES.keys())
        assert "Scott Foster" in refs

    def test_scrape_uses_cache_when_fresh(self, tmp_path, monkeypatch):
        """scrape_ref_tendencies returns cached data when cache is fresh."""
        import src.data.ref_tracker as rt

        cache = str(tmp_path / "nba" / "ref_tendencies.json")
        _write_json(cache, _REF_PROFILES)
        monkeypatch.setattr(rt, "_CACHE_PATH", cache)
        monkeypatch.setattr(rt, "_cache_is_fresh", lambda: True)

        result = rt.scrape_ref_tendencies()
        assert "Scott Foster" in result
        # If cache was used no NBA API should have been imported
        assert result["Scott Foster"]["games_counted"] == 80

    def test_scrape_network_failure_returns_stale_cache(self, tmp_path, monkeypatch):
        """Network/API failure falls back to stale cache rather than crashing."""
        import src.data.ref_tracker as rt

        cache = str(tmp_path / "nba" / "ref_tendencies.json")
        _write_json(cache, _REF_PROFILES)
        monkeypatch.setattr(rt, "_CACHE_PATH", cache)
        monkeypatch.setattr(rt, "_cache_is_fresh", lambda: False)

        # Make the nba_api import fail
        import builtins
        real_import = builtins.__import__

        def _broken_import(name, *a, **kw):
            if "nba_api" in name:
                raise ImportError("nba_api unavailable")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", _broken_import)

        result = rt.scrape_ref_tendencies(force=True)
        assert "Scott Foster" in result


# ══════════════════════════════════════════════════════════════════════════════
# line_monitor — 5 tests
# ══════════════════════════════════════════════════════════════════════════════

class TestLineMonitor:

    def test_get_game_lines_found(self, tmp_path, monkeypatch):
        """get_game_lines returns line data for a known matchup."""
        import src.data.line_monitor as lm

        cache   = str(tmp_path / "nba" / "lines_cache.json")
        history = str(tmp_path / "nba" / "lines_opening.json")
        _write_json(cache,   _LINES_CACHE)
        _write_json(history, _OPENING_HISTORY)
        monkeypatch.setattr(lm, "_CACHE_PATH",   cache)
        monkeypatch.setattr(lm, "_HISTORY_PATH", history)
        monkeypatch.setattr(lm, "_cache_is_fresh", lambda: True)

        result = lm.get_game_lines("BOS", "MIA")
        assert result["found"] is True
        assert result["spread_home"] == pytest.approx(-6.5)
        assert result["total_over"]  == pytest.approx(215.5)

    def test_get_game_lines_not_found(self, tmp_path, monkeypatch):
        """get_game_lines returns found=False for an unknown matchup."""
        import src.data.line_monitor as lm

        cache = str(tmp_path / "nba" / "lines_cache.json")
        _write_json(cache, _LINES_CACHE)
        monkeypatch.setattr(lm, "_CACHE_PATH",   cache)
        monkeypatch.setattr(lm, "_HISTORY_PATH", str(tmp_path / "nba" / "lines_opening.json"))
        monkeypatch.setattr(lm, "_cache_is_fresh", lambda: True)

        result = lm.get_game_lines("GSW", "PHX")
        assert result["found"] is False
        assert result["spread_home"] is None

    def test_get_sharp_signal_positive(self, tmp_path, monkeypatch):
        """Line moving home-team-favourable produces positive sharp signal."""
        import src.data.line_monitor as lm

        # Opening: BOS -5.0 → Closing: BOS -6.5 → signal = -5.0 - (-6.5) = +1.5
        cache   = str(tmp_path / "nba" / "lines_cache.json")
        history = str(tmp_path / "nba" / "lines_opening.json")
        _write_json(cache,   _LINES_CACHE)
        _write_json(history, _OPENING_HISTORY)
        monkeypatch.setattr(lm, "_CACHE_PATH",   cache)
        monkeypatch.setattr(lm, "_HISTORY_PATH", history)
        monkeypatch.setattr(lm, "_cache_is_fresh", lambda: True)

        signal = lm.get_sharp_signal("BOS", "MIA")
        assert signal == pytest.approx(1.5)

    def test_get_sharp_signal_no_history_returns_zero(self, tmp_path, monkeypatch):
        """Sharp signal is 0.0 when no opening line history exists."""
        import src.data.line_monitor as lm

        cache   = str(tmp_path / "nba" / "lines_cache.json")
        history = str(tmp_path / "nba" / "lines_opening.json")
        _write_json(cache,   _LINES_CACHE)
        _write_json(history, {})   # empty history
        monkeypatch.setattr(lm, "_CACHE_PATH",   cache)
        monkeypatch.setattr(lm, "_HISTORY_PATH", history)
        monkeypatch.setattr(lm, "_cache_is_fresh", lambda: True)

        signal = lm.get_sharp_signal("BOS", "MIA")
        assert signal == 0.0

    def test_no_api_key_skips_network_returns_cache(self, tmp_path, monkeypatch):
        """refresh_lines silently returns cache when ODDS_API_KEY is not set."""
        import src.data.line_monitor as lm

        cache = str(tmp_path / "nba" / "lines_cache.json")
        _write_json(cache, _LINES_CACHE)
        monkeypatch.setattr(lm, "_CACHE_PATH",   cache)
        monkeypatch.setattr(lm, "_HISTORY_PATH", str(tmp_path / "nba" / "lines_opening.json"))
        monkeypatch.delenv("ODDS_API_KEY", raising=False)
        monkeypatch.setenv("ODDS_API_KEY", "")  # empty = not set

        result = lm.refresh_lines(force=True)
        # Should return the on-disk cache without raising
        assert isinstance(result, dict)

    def test_network_failure_returns_stale_cache(self, tmp_path, monkeypatch):
        """Network failure returns stale cache rather than crashing."""
        import src.data.line_monitor as lm
        import requests as req_mod

        cache   = str(tmp_path / "nba" / "lines_cache.json")
        history = str(tmp_path / "nba" / "lines_opening.json")
        _write_json(cache,   _LINES_CACHE)
        _write_json(history, {})
        monkeypatch.setattr(lm, "_CACHE_PATH",   cache)
        monkeypatch.setattr(lm, "_HISTORY_PATH", history)
        monkeypatch.setattr(lm, "_cache_is_fresh", lambda: False)
        monkeypatch.setenv("ODDS_API_KEY", "fake_key_xyz")

        def _fail(*a, **kw):
            raise ConnectionError("API down")

        monkeypatch.setattr(req_mod, "get", _fail)

        result = lm.refresh_lines(force=True)
        assert "abc123" in result


# ══════════════════════════════════════════════════════════════════════════════
# PostgreSQL wiring — 3 tests (mocks db.get_connection)
# ══════════════════════════════════════════════════════════════════════════════

class TestUnifiedPipelinePgWrite:
    """
    Validate that _pg_write_tracking_rows writes rows when conditions are met.

    All tests are unit-level: no video processing, no real PG connection.
    """

    def _make_pipeline_stub(self, game_id: str = "0022400001"):
        """Create a minimal UnifiedPipeline-like stub with just what we test."""
        import types

        # Import the method without instantiating the full pipeline
        import importlib.util, pathlib
        src = pathlib.Path(__file__).parents[1] / "src" / "pipeline" / "unified_pipeline.py"
        spec = importlib.util.spec_from_file_location("unified_pipeline", src)
        mod  = importlib.util.module_from_spec(spec)

        import uuid
        stub = types.SimpleNamespace()
        stub.game_id = game_id
        stub.clip_id = str(uuid.uuid4())
        # Bind the method directly from the module source
        import src.pipeline.unified_pipeline as up
        stub._pg_write_tracking_rows = up.UnifiedPipeline._pg_write_tracking_rows.__get__(stub)
        return stub

    def test_rows_attempted_when_conditions_met(self, monkeypatch):
        """Rows are passed to execute_batch when DATABASE_URL set and game_id present."""
        import src.pipeline.unified_pipeline as up
        import src.data.db as db_mod
        import psycopg2.extras

        rows_inserted = []

        class _FakeCursor:
            def close(self): pass

        class _FakeConn:
            def cursor(self): return _FakeCursor()
            def commit(self): pass
            def close(self): pass

        monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
        monkeypatch.setattr(db_mod, "get_connection", lambda: _FakeConn())

        def _capture_batch(cur, sql, data, page_size=500):
            rows_inserted.extend(data)

        monkeypatch.setattr(psycopg2.extras, "execute_batch", _capture_batch)

        stub = self._make_pipeline_stub(game_id="0022400001")
        sample_rows = [
            {"frame": 1, "timestamp": 0.033, "player_id": 1, "team": "green",
             "x_position": 100.0, "y_position": 200.0, "velocity": 2.0,
             "acceleration": 0.1, "ball_possession": False, "event": "none",
             "confidence": 0.85, "team_spacing": 5000.0,
             "paint_count_own": 2, "paint_count_opp": 1},
        ]
        stub._pg_write_tracking_rows(sample_rows)
        assert len(rows_inserted) == 1
        assert rows_inserted[0]["game_id"] == "0022400001"
        assert rows_inserted[0]["frame_number"] == 1

    def test_no_database_url_skips_silently(self, monkeypatch, capsys):
        """No DATABASE_URL → skip silently, print warning, no exception."""
        import src.pipeline.unified_pipeline as up

        monkeypatch.delenv("DATABASE_URL", raising=False)
        stub = self._make_pipeline_stub(game_id="0022400001")
        stub._pg_write_tracking_rows([{"frame": 1}])  # should not raise

        out = capsys.readouterr().out
        assert "DATABASE_URL" in out

    def test_no_game_id_skips_silently(self, monkeypatch, capsys):
        """No game_id → skip silently, print warning, no exception."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
        stub = self._make_pipeline_stub(game_id=None)
        stub._pg_write_tracking_rows([{"frame": 1}])  # should not raise

        out = capsys.readouterr().out
        assert "game_id" in out.lower() or "No game" in out
