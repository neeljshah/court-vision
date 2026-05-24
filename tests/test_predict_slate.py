"""Tests for scripts/predict_slate.py — the --save CSV writer.

The slate CLI itself hits nba_api at runtime, so the live happy-path is not
exercised here. These tests target the CSV-writing branch added in cycle 47:
input → canonical row layout, default vs explicit path, and one-row-per-stat
expansion. STATS comes from prop_pergame and must stay in sync.
"""
from __future__ import annotations

import csv
import os
import sys
import tempfile
import unittest
from unittest import mock

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Import after sys.path append so module-level nba_api header patch runs.
import scripts.predict_slate as ps  # noqa: E402


def _fake_game():
    return {
        "game_id":     "0022400999",
        "home_id":     1610612747,
        "away_id":     1610612743,
        "home_abbrev": "LAL",
        "away_abbrev": "DEN",
    }


def _fake_row(name, pid, team, preds=None):
    preds = preds if preds is not None else {
        "pts": 25.3, "reb": 5.1, "ast": 7.4, "fg3m": 2.1,
        "stl": 1.0, "blk": 0.4, "tov": 2.6,
    }
    return {"player_id": pid, "name": name, "team": team, "preds": preds}


def test_save_predictions_csv_writes_one_row_per_stat():
    g = _fake_game()
    home_rows = [_fake_row("LeBron James", 2544, "LAL")]
    away_rows = [_fake_row("Nikola Jokic", 203999, "DEN")]
    per_game = [(g, home_rows, away_rows)]

    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.csv")
        n = ps.save_predictions_csv(out, "2026-05-24", [g], per_game)
        # 2 players × 7 stats = 14
        assert n == 14
        with open(out) as fh:
            rows = list(csv.DictReader(fh))
    assert len(rows) == 14
    assert {r["stat"] for r in rows} == set(ps.STATS)
    lebron = [r for r in rows if r["player"] == "LeBron James"]
    assert {r["venue"] for r in lebron} == {"home"}
    assert {r["opp"] for r in lebron} == {"DEN"}
    jokic = [r for r in rows if r["player"] == "Nikola Jokic"]
    assert {r["venue"] for r in jokic} == {"away"}
    assert {r["opp"] for r in jokic} == {"LAL"}


def test_save_skips_missing_stats():
    g = _fake_game()
    # Player only has PTS predicted — REB/AST/... missing in the preds dict.
    rows = [_fake_row("X. Player", 99, "LAL", preds={"pts": 10.0})]
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.csv")
        n = ps.save_predictions_csv(out, "2026-05-24", [g], [(g, rows, [])])
        assert n == 1
        with open(out) as fh:
            rows_out = list(csv.DictReader(fh))
    assert len(rows_out) == 1
    assert rows_out[0]["stat"] == "pts"
    assert rows_out[0]["pred"] == "10.0000"


def test_save_creates_parent_dir():
    g = _fake_game()
    rows = [_fake_row("X. Player", 99, "LAL")]
    with tempfile.TemporaryDirectory() as tmp:
        nested = os.path.join(tmp, "deep", "nested", "out.csv")
        n = ps.save_predictions_csv(nested, "2026-05-24", [g], [(g, rows, [])])
        assert n == 7
        assert os.path.exists(nested)


def test_save_handles_empty_per_game():
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.csv")
        n = ps.save_predictions_csv(out, "2026-05-24", [], [])
        assert n == 0
        # File is created with just the header row.
        with open(out) as fh:
            content = fh.read().strip().splitlines()
        assert len(content) == 1
        assert content[0].startswith("date,game_id,")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
