"""
tests/test_shot_log_team_abbrev.py — BUG1 regression: shot_log team_abbrev column.

BUG1 root cause: mid-loop flushes write raw HSV color labels ('green'/'white') to the
`team` column; _backfill_team_abbrev() only touches tracking_data.csv, never shot_log.csv.
Fix: (a) add `team_abbrev` column to every shot_log flush (empty at emit-time), and
(b) add _backfill_shot_log_team_abbrev() to do a post-run disk rewrite with the final map.

Tests here verify the rewrite produces correct NBA abbreviations on disk.
"""
from __future__ import annotations

import csv
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_shot_log_csv(tmp_dir: str, rows: list[dict], fields: list[str] | None = None) -> str:
    """Write a synthetic shot_log.csv to tmp_dir and return its path."""
    path = os.path.join(tmp_dir, "shot_log.csv")
    if fields is None:
        fields = ["game_id", "shot_id", "frame", "timestamp", "player_id",
                  "player_name", "team", "team_abbrev", "x_position", "y_position",
                  "court_zone", "made", "shot_distance"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return path


def _import_backfill():
    """Import _backfill_shot_log_team_abbrev or skip if not yet present."""
    try:
        from src.pipeline.unified_pipeline import UnifiedPipeline
        return UnifiedPipeline
    except ImportError:
        pytest.skip("unified_pipeline not importable in this environment")


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestShotLogTeamAbbrev:

    def test_team_abbrev_column_present_in_export_fields(self):
        """_export_shot_log fieldnames must include 'team_abbrev'."""
        _import_backfill()  # ensures module importable
        import inspect
        import src.pipeline.unified_pipeline as _up
        source = inspect.getsource(_up.UnifiedPipeline._export_shot_log)
        assert "team_abbrev" in source, (
            "_export_shot_log must include 'team_abbrev' in fieldnames list"
        )

    def test_backfill_rewrites_team_column(self):
        """_backfill_shot_log_team_abbrev must map 'green' → 'DAL' in team column."""
        cls = _import_backfill()

        color_map = {"green": "DAL", "white": "GSW"}
        rows = [
            {"game_id": "0022500568", "shot_id": "1", "frame": "100",
             "timestamp": "10.0", "player_id": "5", "player_name": "Test Player",
             "team": "green", "team_abbrev": "",
             "x_position": "200", "y_position": "250", "court_zone": "paint",
             "made": "", "shot_distance": "8.5"},
            {"game_id": "0022500568", "shot_id": "2", "frame": "400",
             "timestamp": "25.0", "player_id": "7", "player_name": "Other Player",
             "team": "white", "team_abbrev": "",
             "x_position": "700", "y_position": "250", "court_zone": "mid_range",
             "made": "", "shot_distance": "18.0"},
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            _make_shot_log_csv(tmp_dir, rows)

            # Create a minimal pipeline instance-like object just to call the method
            # by binding _data_dir — avoids full __init__ (no GPU needed)
            obj = object.__new__(cls)
            object.__setattr__(obj, "_data_dir", tmp_dir)
            cls._backfill_shot_log_team_abbrev(obj, color_map)

            # Read back and verify
            shot_log_path = os.path.join(tmp_dir, "shot_log.csv")
            with open(shot_log_path, newline="", encoding="utf-8") as f:
                result_rows = list(csv.DictReader(f))

        assert len(result_rows) == 2

        # Row 1: 'green' → 'DAL' in both team and team_abbrev
        assert result_rows[0]["team"] == "DAL", (
            f"Expected team='DAL' after rewrite, got {result_rows[0]['team']!r}"
        )
        assert result_rows[0]["team_abbrev"] == "DAL", (
            f"Expected team_abbrev='DAL' after rewrite, got {result_rows[0]['team_abbrev']!r}"
        )

        # Row 2: 'white' → 'GSW'
        assert result_rows[1]["team"] == "GSW", (
            f"Expected team='GSW' after rewrite, got {result_rows[1]['team']!r}"
        )
        assert result_rows[1]["team_abbrev"] == "GSW", (
            f"Expected team_abbrev='GSW' after rewrite, got {result_rows[1]['team_abbrev']!r}"
        )

    def test_backfill_adds_team_abbrev_column_if_missing(self):
        """If shot_log.csv was flushed without team_abbrev column, backfill must add it."""
        cls = _import_backfill()

        color_map = {"green": "DAL"}
        # Write shot_log WITHOUT team_abbrev column (legacy format)
        rows = [
            {"game_id": "X", "shot_id": "1", "frame": "50", "timestamp": "5.0",
             "player_id": "3", "player_name": "P", "team": "green",
             "x_position": "100", "y_position": "250", "court_zone": "paint",
             "made": "", "shot_distance": "5.0"},
        ]
        fields_no_abbrev = ["game_id", "shot_id", "frame", "timestamp", "player_id",
                            "player_name", "team", "x_position", "y_position",
                            "court_zone", "made", "shot_distance"]

        with tempfile.TemporaryDirectory() as tmp_dir:
            _make_shot_log_csv(tmp_dir, rows, fields=fields_no_abbrev)

            obj = object.__new__(cls)
            object.__setattr__(obj, "_data_dir", tmp_dir)
            cls._backfill_shot_log_team_abbrev(obj, color_map)

            shot_log_path = os.path.join(tmp_dir, "shot_log.csv")
            with open(shot_log_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                result_fields = reader.fieldnames or []
                result_rows = list(reader)

        assert "team_abbrev" in result_fields, (
            "team_abbrev column must be added by backfill even if absent from original"
        )
        assert result_rows[0]["team_abbrev"] == "DAL"

    def test_backfill_noop_on_empty_color_map(self):
        """Empty color_map must not corrupt the file."""
        cls = _import_backfill()

        rows = [
            {"game_id": "X", "shot_id": "1", "frame": "10", "timestamp": "1.0",
             "player_id": "2", "player_name": "P", "team": "green", "team_abbrev": "",
             "x_position": "100", "y_position": "250", "court_zone": "paint",
             "made": "", "shot_distance": "5.0"},
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            _make_shot_log_csv(tmp_dir, rows)
            original_path = os.path.join(tmp_dir, "shot_log.csv")
            with open(original_path, "rb") as f:
                original_bytes = f.read()

            obj = object.__new__(cls)
            object.__setattr__(obj, "_data_dir", tmp_dir)
            cls._backfill_shot_log_team_abbrev(obj, {})   # empty map → noop

            with open(original_path, "rb") as f:
                after_bytes = f.read()

        # File must be unchanged
        assert original_bytes == after_bytes, (
            "Empty color_map must not modify shot_log.csv"
        )
