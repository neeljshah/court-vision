"""Tests for scripts/ledger_summary.py (cycle 58)."""
from __future__ import annotations

import csv
import os
import sys
import tempfile
from datetime import date

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.ledger_summary as ls  # noqa: E402


def _write_ledger(tmp: str, dt: str, rows):
    path = os.path.join(tmp, f"{dt}.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "game_id", "player_id", "player",
                    "team", "opp", "venue", "stat", "pred"])
        for r in rows:
            w.writerow(r)
    return path


def test_list_ledger_files_filters_by_date_range():
    with tempfile.TemporaryDirectory() as tmp:
        for dt in ("2026-05-01", "2026-05-02", "2026-05-10"):
            _write_ledger(tmp, dt, [])
        paths = ls.list_ledger_files(date(2026, 5, 1), date(2026, 5, 5), pred_dir=tmp)
        assert len(paths) == 2
        names = sorted(os.path.basename(p) for p in paths)
        assert names == ["2026-05-01.csv", "2026-05-02.csv"]


def test_list_ledger_files_skips_non_date_filenames():
    with tempfile.TemporaryDirectory() as tmp:
        _write_ledger(tmp, "2026-05-01", [])
        # Stray file that doesn't match the date pattern.
        with open(os.path.join(tmp, "notes.csv"), "w") as fh:
            fh.write("x\n")
        paths = ls.list_ledger_files(date(2026, 5, 1), date(2026, 5, 31), pred_dir=tmp)
        assert [os.path.basename(p) for p in paths] == ["2026-05-01.csv"]


def test_load_rows_aggregates_across_files():
    with tempfile.TemporaryDirectory() as tmp:
        p1 = _write_ledger(tmp, "2026-05-01", [
            ["2026-05-01", "", 1, "P A", "", "LAL", "home", "pts", "10"],
        ])
        p2 = _write_ledger(tmp, "2026-05-02", [
            ["2026-05-02", "", 2, "P B", "", "LAL", "away", "reb", "5"],
        ])
        rows = ls.load_rows([p1, p2])
        assert len(rows) == 2


def test_summarize_means_count_and_top_player():
    rows = [
        {"date": "2026-05-01", "player": "A", "stat": "pts", "pred": "20.0", "opp": "X", "venue": "home"},
        {"date": "2026-05-02", "player": "A", "stat": "pts", "pred": "25.0", "opp": "Y", "venue": "away"},
        {"date": "2026-05-01", "player": "B", "stat": "pts", "pred": "30.0", "opp": "X", "venue": "home"},
        {"date": "2026-05-01", "player": "A", "stat": "reb", "pred": "10.0", "opp": "X", "venue": "home"},
    ]
    s = ls.summarize(rows)
    assert s["n_rows"] == 4
    assert s["n_dates"] == 2
    assert s["n_players"] == 2
    # 3 PTS rows mean = (20+25+30)/3 = 25.0; 1 REB row mean = 10.0
    assert s["by_stat_mean"]["pts"] == 25.0
    assert s["by_stat_mean"]["reb"] == 10.0
    assert s["by_stat_count"]["pts"] == 3
    # Player A has 3 predictions, B has 1
    assert s["top_predicted_players"][0] == ("A", 3)
    # Top by value: 30.0 (B PTS) first
    assert s["top_rows"][0]["pred_f"] == 30.0


def test_summarize_filter_by_player_and_stat():
    rows = [
        {"date": "2026-05-01", "player": "Nikola Jokic", "stat": "pts", "pred": "28.0"},
        {"date": "2026-05-01", "player": "LeBron James", "stat": "pts", "pred": "25.0"},
        {"date": "2026-05-01", "player": "Nikola Jokic", "stat": "reb", "pred": "12.0"},
    ]
    # Filter by player
    s = ls.summarize(rows, player="Nikola Jokic")
    assert s["n_rows"] == 2
    assert {p for p, _ in s["top_predicted_players"]} == {"Nikola Jokic"}
    # Filter by stat
    s = ls.summarize(rows, stat="reb")
    assert s["n_rows"] == 1
    # Filter by both
    s = ls.summarize(rows, player="LeBron James", stat="reb")
    assert s["n_rows"] == 0


def test_summarize_handles_bad_pred_values():
    rows = [
        {"date": "2026-05-01", "player": "A", "stat": "pts", "pred": "20.0"},
        {"date": "2026-05-01", "player": "B", "stat": "pts", "pred": "not-a-number"},
        {"date": "2026-05-01", "player": "C", "stat": "pts"},  # missing pred
    ]
    s = ls.summarize(rows)
    # Only the parseable row survives.
    assert s["n_rows"] == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
