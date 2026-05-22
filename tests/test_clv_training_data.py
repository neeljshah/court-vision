"""
test_clv_training_data.py -- Tests for the CLV training-dataset builder (16.5-01).

Acceptance criterion: build_clv_training_data appends rows to
clv_training_data.csv with the schema our_edge, pinnacle_delta, public_pct,
time_to_game, lineup_freshness, line_movement_last_2h, clv_label.
"""

from __future__ import annotations

import csv
import json
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, "scripts"))

from clv_tracker import _CLV_TRAINING_COLUMNS, build_clv_training_data  # noqa: E402

_REQUIRED_SCHEMA = {
    "our_edge", "pinnacle_delta", "public_pct", "time_to_game",
    "lineup_freshness", "line_movement_last_2h", "clv_label",
}


def _write_bet_log(path, bets) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(bets, f)


def test_schema_includes_all_required_columns():
    """The CSV column set covers every field named in the acceptance criterion."""
    assert _REQUIRED_SCHEMA.issubset(set(_CLV_TRAINING_COLUMNS))


def test_builds_rows_for_bets_with_closing_lines(tmp_path):
    """Bets carrying a closing line produce labelled training rows."""
    bet_log = tmp_path / "bet_log.json"
    out_csv = tmp_path / "clv_training_data.csv"
    _write_bet_log(bet_log, [
        {
            "bet_id": "b1", "stat": "pts", "direction": "over",
            "opening_line": 25.0, "closing_line": 26.5, "edge_pct": 0.05,
            "pinnacle_delta": 0.4, "public_pct": 0.62,
            "time_to_game_hours": 3.0, "lineup_freshness_min": 12.0,
            "line_movement_2h": 0.5,
        },
        {
            "bet_id": "b2", "stat": "reb", "direction": "under",
            "opening_line": 9.0, "closing_line": 9.5, "edge_pct": 0.03,
        },
    ])

    n = build_clv_training_data(str(bet_log), str(out_csv))
    assert n == 2
    assert out_csv.exists()

    with open(out_csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert _REQUIRED_SCHEMA.issubset(set(rows[0].keys()))

    # b1: over bet, closing 26.5 > opening 25.0 -> favourable -> clv_label 1.
    b1 = next(r for r in rows if r["bet_id"] == "b1")
    assert b1["clv_label"] == "1"
    # b2: under bet, closing 9.5 > opening 9.0 -> unfavourable -> clv_label 0.
    b2 = next(r for r in rows if r["bet_id"] == "b2")
    assert b2["clv_label"] == "0"


def test_skips_bets_without_closing_line(tmp_path):
    """A bet with no closing line yields no row (cannot be labelled)."""
    bet_log = tmp_path / "bet_log.json"
    out_csv = tmp_path / "clv_training_data.csv"
    _write_bet_log(bet_log, [
        {"bet_id": "open1", "stat": "ast", "direction": "over",
         "opening_line": 7.0, "closing_line": None, "edge_pct": 0.04},
    ])
    n = build_clv_training_data(str(bet_log), str(out_csv))
    assert n == 0
    # Header is still written so a schema-correct file exists.
    assert out_csv.exists()
    with open(out_csv, newline="", encoding="utf-8") as f:
        assert _REQUIRED_SCHEMA.issubset(set(next(csv.reader(f))))


def test_idempotent_dedup_by_bet_id(tmp_path):
    """Re-running does not duplicate rows already present (keyed by bet_id)."""
    bet_log = tmp_path / "bet_log.json"
    out_csv = tmp_path / "clv_training_data.csv"
    _write_bet_log(bet_log, [
        {"bet_id": "b1", "stat": "pts", "direction": "over",
         "opening_line": 25.0, "closing_line": 26.0, "edge_pct": 0.05},
    ])
    first = build_clv_training_data(str(bet_log), str(out_csv))
    second = build_clv_training_data(str(bet_log), str(out_csv))
    assert first == 1
    assert second == 0
    with open(out_csv, newline="", encoding="utf-8") as f:
        assert len(list(csv.DictReader(f))) == 1


def test_missing_features_default_to_neutral(tmp_path):
    """A sparse bet still yields a row with neutral feature defaults."""
    bet_log = tmp_path / "bet_log.json"
    out_csv = tmp_path / "clv_training_data.csv"
    _write_bet_log(bet_log, [
        {"bet_id": "sparse", "stat": "pts", "direction": "over",
         "opening_line": 20.0, "closing_line": 21.0},
    ])
    build_clv_training_data(str(bet_log), str(out_csv))
    with open(out_csv, newline="", encoding="utf-8") as f:
        row = next(csv.DictReader(f))
    assert row["public_pct"] == "0.5"
    assert row["pinnacle_delta"] == "0.0"
    assert row["our_edge"] == "0.0"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
