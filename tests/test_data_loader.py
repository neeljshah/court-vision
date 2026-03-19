"""
Tests for src/pipeline/data_loader.py.

All DB calls are mocked via monkeypatch. No live PostgreSQL or NBA API needed.
"""

from __future__ import annotations

import json
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GAME_ID = "22401001"   # no leading zeros so pandas reads it back as same string
SEASON  = "2024-25"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _write_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def _write_csv(path: str, df: pd.DataFrame) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path, index=False)


# ── load_tracking_data ────────────────────────────────────────────────────────

class TestLoadTrackingData:

    def test_csv_fallback_no_db(self, tmp_path, monkeypatch):
        """When PostgreSQL returns None, falls back to CSV."""
        import src.pipeline.data_loader as dl
        # Force pg path to return None (no DB available)
        monkeypatch.setattr(dl, "_try_pg_tracking", lambda *a, **kw: None)
        monkeypatch.setattr(dl, "_TRACKING_CSV", str(tmp_path / "tracking_data.csv"))

        df_written = pd.DataFrame([
            {"game_id": GAME_ID, "frame": 1, "player_id": 1, "team_id": 0,
             "x_position": 10.0, "y_position": 20.0},
            {"game_id": GAME_ID, "frame": 2, "player_id": 2, "team_id": 1,
             "x_position": 30.0, "y_position": 40.0},
        ])
        _write_csv(str(tmp_path / "tracking_data.csv"), df_written)

        result = dl.load_tracking_data(GAME_ID)
        assert len(result) == 2
        assert list(result["frame"]) == [1, 2]

    def test_csv_filter_by_game_id(self, tmp_path, monkeypatch):
        """CSV fallback filters rows to matching game_id."""
        import src.pipeline.data_loader as dl
        monkeypatch.setattr(dl, "_try_pg_tracking", lambda *a, **kw: None)
        monkeypatch.setattr(dl, "_TRACKING_CSV", str(tmp_path / "tracking_data.csv"))

        df_written = pd.DataFrame([
            {"game_id": GAME_ID, "frame": 1, "player_id": 1},
            {"game_id": "9999999", "frame": 2, "player_id": 2},
        ])
        _write_csv(str(tmp_path / "tracking_data.csv"), df_written)

        result = dl.load_tracking_data(GAME_ID)
        assert len(result) == 1
        assert str(result.iloc[0]["game_id"]) == str(GAME_ID)

    def test_missing_csv_returns_empty_df(self, tmp_path, monkeypatch):
        """When no CSV exists and no DB, returns empty DataFrame."""
        import src.pipeline.data_loader as dl
        monkeypatch.setenv("DATABASE_URL", "")
        monkeypatch.setattr(dl, "_TRACKING_CSV", str(tmp_path / "nonexistent.csv"))

        result = dl.load_tracking_data(GAME_ID)
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_mock_postgresql_returns_data(self, monkeypatch):
        """When PostgreSQL is mocked to return rows, they come back as DataFrame."""
        import src.pipeline.data_loader as dl

        # Mock psycopg2 connection
        class _MockCursor:
            description = [("frame",), ("player_id",), ("x_position",)]

            def __enter__(self): return self
            def __exit__(self, *a): pass
            def execute(self, *a): pass
            def fetchall(self): return [(1, 10, 5.0), (2, 11, 6.0)]

        class _MockConn:
            def cursor(self): return _MockCursor()
            def close(self): pass

        import psycopg2
        monkeypatch.setattr(psycopg2, "connect", lambda url: _MockConn())
        monkeypatch.setenv("DATABASE_URL", "postgresql://fake:5432/db")

        result = dl.load_tracking_data(GAME_ID)
        assert len(result) == 2
        assert list(result.columns) == ["frame", "player_id", "x_position"]

    def test_postgresql_empty_result_returns_empty_df(self, monkeypatch):
        """PostgreSQL returns 0 rows → empty DataFrame (with columns)."""
        import src.pipeline.data_loader as dl

        class _MockCursor:
            description = [("frame",), ("player_id",)]

            def __enter__(self): return self
            def __exit__(self, *a): pass
            def execute(self, *a): pass
            def fetchall(self): return []

        class _MockConn:
            def cursor(self): return _MockCursor()
            def close(self): pass

        import psycopg2
        monkeypatch.setattr(psycopg2, "connect", lambda url: _MockConn())
        monkeypatch.setenv("DATABASE_URL", "postgresql://fake:5432/db")

        result = dl.load_tracking_data(GAME_ID)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    def test_postgresql_error_falls_back_to_csv(self, tmp_path, monkeypatch):
        """PostgreSQL connection error → falls back to CSV."""
        import src.pipeline.data_loader as dl
        import psycopg2

        def _raise_connect(url):
            raise psycopg2.OperationalError("connection refused")

        monkeypatch.setattr(psycopg2, "connect", _raise_connect)
        monkeypatch.setenv("DATABASE_URL", "postgresql://fake:5432/db")
        monkeypatch.setattr(dl, "_TRACKING_CSV", str(tmp_path / "tracking_data.csv"))

        df_written = pd.DataFrame([
            {"game_id": GAME_ID, "frame": 1, "player_id": 1},
        ])
        _write_csv(str(tmp_path / "tracking_data.csv"), df_written)

        result = dl.load_tracking_data(GAME_ID)
        assert len(result) == 1


# ── load_player_features ──────────────────────────────────────────────────────

class TestLoadPlayerFeatures:

    def test_player_found_in_cache(self, tmp_path, monkeypatch):
        """Player found in players_{season}.json returns feature dict."""
        import src.pipeline.data_loader as dl
        monkeypatch.setattr(dl, "_NBA_CACHE", str(tmp_path))

        players = {
            "2544": {
                "player_name": "LeBron James",
                "pts": 25.4, "reb": 7.2, "ast": 8.1,
                "usg_pct": 31.2, "ts_pct": 0.585,
            }
        }
        _write_json(str(tmp_path / f"players_{SEASON}.json"), players)

        result = dl.load_player_features(2544, SEASON)
        assert result["found"] is True
        assert result["player_name"] == "LeBron James"
        assert result["pts"] == 25.4

    def test_player_not_in_cache_returns_not_found(self, tmp_path, monkeypatch):
        """Unknown player_id returns found=False."""
        import src.pipeline.data_loader as dl
        monkeypatch.setattr(dl, "_NBA_CACHE", str(tmp_path))

        _write_json(str(tmp_path / f"players_{SEASON}.json"), {})

        result = dl.load_player_features(99999, SEASON)
        assert result["found"] is False

    def test_gamelog_l5_averages_computed(self, tmp_path, monkeypatch):
        """Gamelog present → l5_pts, l5_reb, l5_ast computed from last 5 games."""
        import src.pipeline.data_loader as dl
        monkeypatch.setattr(dl, "_NBA_CACHE", str(tmp_path))

        gamelogs = {
            "2544": {
                "games": [
                    {"pts": 20, "reb": 8, "ast": 7},
                    {"pts": 30, "reb": 6, "ast": 9},
                    {"pts": 25, "reb": 7, "ast": 8},
                    {"pts": 28, "reb": 9, "ast": 6},
                    {"pts": 22, "reb": 5, "ast": 10},
                ]
            }
        }
        _write_json(str(tmp_path / f"gamelogs_{SEASON}.json"), gamelogs)

        result = dl.load_player_features(2544, SEASON)
        assert result["found"] is True
        assert abs(result["l5_pts"] - 25.0) < 0.1

    def test_injury_status_injected(self, tmp_path, monkeypatch):
        """Player name in injury_report → injury_status set correctly."""
        import src.pipeline.data_loader as dl
        monkeypatch.setattr(dl, "_NBA_CACHE", str(tmp_path))

        players = {"2544": {"player_name": "LeBron James", "pts": 25.0}}
        _write_json(str(tmp_path / f"players_{SEASON}.json"), players)

        report = {
            "fetched_at": "2026-03-17T10:00:00+00:00",
            "source": "espn",
            "injuries": [
                {"player_name": "LeBron James", "status": "Out",
                 "team_abbrev": "LAL", "short_comment": "Ankle"}
            ]
        }
        _write_json(str(tmp_path / "injury_report.json"), report)

        result = dl.load_player_features(2544, SEASON)
        assert result["injury_status"] == "Out"

    def test_healthy_player_defaults_to_available(self, tmp_path, monkeypatch):
        """Player not in injury report → injury_status='Available'."""
        import src.pipeline.data_loader as dl
        monkeypatch.setattr(dl, "_NBA_CACHE", str(tmp_path))

        players = {"2544": {"player_name": "LeBron James", "pts": 25.0}}
        _write_json(str(tmp_path / f"players_{SEASON}.json"), players)
        _write_json(str(tmp_path / "injury_report.json"),
                    {"fetched_at": "", "source": "espn", "injuries": []})

        result = dl.load_player_features(2544, SEASON)
        assert result["injury_status"] == "Available"

    def test_no_cache_files_returns_defaults(self, tmp_path, monkeypatch):
        """No cache files → returns minimal dict with found=False."""
        import src.pipeline.data_loader as dl
        monkeypatch.setattr(dl, "_NBA_CACHE", str(tmp_path))

        result = dl.load_player_features(2544, SEASON)
        assert result["found"] is False
        assert result["player_id"] == 2544
        assert result["injury_status"] == "Available"


# ── load_game_context ─────────────────────────────────────────────────────────

class TestLoadGameContext:

    def test_returns_required_keys(self, tmp_path, monkeypatch):
        """load_game_context always returns dict with all required keys."""
        import src.pipeline.data_loader as dl
        monkeypatch.setattr(dl, "_SCHEDULE_JSON", str(tmp_path / "nope.json"))

        ctx = dl.load_game_context(GAME_ID)
        for key in ("game_id", "home_team", "away_team", "date", "refs",
                    "home_rest", "away_rest", "home_b2b", "away_b2b", "found"):
            assert key in ctx

    def test_schedule_context_loaded(self, tmp_path, monkeypatch):
        """When schedule_context.json exists, home/away/rest/b2b populated."""
        import src.pipeline.data_loader as dl

        sched = {
            GAME_ID: {
                "home_team":      "GSW",
                "away_team":      "BOS",
                "game_date":      "2026-03-17",
                "home_rest_days": 2,
                "away_rest_days": 1,
                "home_b2b":       False,
                "away_b2b":       True,
            }
        }
        sched_path = str(tmp_path / "schedule_context.json")
        _write_json(sched_path, sched)
        monkeypatch.setattr(dl, "_SCHEDULE_JSON", sched_path)

        ctx = dl.load_game_context(GAME_ID)
        assert ctx["home_team"] == "GSW"
        assert ctx["away_team"] == "BOS"
        assert ctx["home_rest"] == 2
        assert ctx["away_b2b"] is True
        assert ctx["found"] is True

    def test_missing_schedule_returns_defaults(self, tmp_path, monkeypatch):
        """When schedule_context.json missing, returns defaults with found=False."""
        import src.pipeline.data_loader as dl
        monkeypatch.setattr(dl, "_SCHEDULE_JSON", str(tmp_path / "nonexistent.json"))

        ctx = dl.load_game_context(GAME_ID)
        assert ctx["found"] is False
        assert ctx["home_team"] == ""
        assert ctx["refs"] == []

    def test_unknown_game_id_returns_not_found(self, tmp_path, monkeypatch):
        """Known schedule but unknown game_id → found=False."""
        import src.pipeline.data_loader as dl

        sched = {"other_game": {"home_team": "LAL", "away_team": "MIA"}}
        sched_path = str(tmp_path / "schedule_context.json")
        _write_json(sched_path, sched)
        monkeypatch.setattr(dl, "_SCHEDULE_JSON", sched_path)

        ctx = dl.load_game_context("0000000000")
        assert ctx["found"] is False

    def test_boxscores_refs_loaded(self, tmp_path, monkeypatch):
        """Refs come from boxscores.json when available."""
        import src.pipeline.data_loader as dl
        monkeypatch.setattr(dl, "_SCHEDULE_JSON", str(tmp_path / "nope.json"))

        boxes = {
            GAME_ID: {
                "home_team":  "DEN",
                "away_team":  "PHX",
                "officials":  ["Ref A", "Ref B", "Ref C"],
            }
        }
        boxes_path = str(tmp_path / "boxscores.json")
        _write_json(boxes_path, boxes)
        # patch _NBA_CACHE so the module constructs the right path
        import src.pipeline.data_loader as dl2
        monkeypatch.setattr(dl2, "_NBA_CACHE", str(tmp_path))

        ctx = dl2.load_game_context(GAME_ID)
        assert ctx["refs"] == ["Ref A", "Ref B", "Ref C"]
        assert ctx["found"] is True
