"""Synthetic-jsonl test for soccer_grid: minute-less exclusion counts + buckets.

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/calibration_grid/test_soccer_grid.py -q
"""
from __future__ import annotations

import json

import pytest

from scripts.platformkit.calibration_grid import soccer_grid as sg


def _write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


@pytest.fixture
def data_dir(tmp_path):
    # game A: minute 52, home_score=2 away_score=1 (diff +1), home win
    _write_jsonl(tmp_path / "gameA.jsonl", [
        {"state_summary": "minute=52 home_score=2 away_score=1",
         "model_prob": 0.65, "market_prob": 0.60, "outcome": 1.0},
    ])
    # game B: minute 10, no score in state_summary -> score_unknown band; draw outcome
    _write_jsonl(tmp_path / "gameB.jsonl", [
        {"state_summary": "minute=10 live", "model_prob": 0.50,
         "market_prob": 0.52, "outcome": 0.5},
    ])
    # game C: older capture format with no minute at all -> excluded entirely
    _write_jsonl(tmp_path / "gameC.jsonl", [
        {"state_summary": "live", "model_prob": 0.40, "market_prob": 0.45, "outcome": 0.0},
    ])
    return tmp_path


def test_load_with_counts_excludes_minute_less_rows(data_dir):
    rows, counts = sg.load_with_counts(data_dir)
    assert len(rows) == 2  # gameC's row is excluded
    assert counts["n_files"] == 3
    assert counts["n_rows_no_minute_timeline"] == 1


def test_score_diff_parsed_and_unknown_band(data_dir):
    rows, _counts = sg.load_with_counts(data_dir)
    by_game = {r["game_id"]: r for r in rows}
    assert by_game["gameA"]["bucket"] == "min_45_60|diff_+01"
    assert by_game["gameB"]["bucket"] == "min_00_15|score_unknown"


def test_draw_outcome_gets_half_credit(data_dir):
    rows, _counts = sg.load_with_counts(data_dir)
    by_game = {r["game_id"]: r for r in rows}
    assert by_game["gameB"]["outcome"] == 0.5


def test_build_reliability_map_honest_note_and_thin_n(data_dir):
    doc = sg.build_reliability_map(data_dir)
    assert doc["edge_claimed"] is False
    assert doc["n_rows_used"] == 2
    assert "THIN" in doc["honest_note"]
    for bkt in doc["buckets"].values():
        assert bkt["can_price"] is False  # 1 game per bucket, far under MIN_GAMES


def test_missing_data_dir_returns_zero_rows(tmp_path):
    rows, counts = sg.load_with_counts(tmp_path / "does_not_exist")
    assert rows == []
    assert counts["n_files"] == 0


def test_missing_fields_row_excluded(tmp_path):
    _write_jsonl(tmp_path / "gameD.jsonl", [
        {"state_summary": "minute=20", "model_prob": 0.5},  # no market_prob/outcome
    ])
    rows, counts = sg.load_with_counts(tmp_path)
    assert rows == []
    assert counts["n_rows_missing_fields"] == 1
