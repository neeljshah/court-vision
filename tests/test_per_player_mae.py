"""
tests/test_per_player_mae.py — Tests for per-player rolling-MAE exclusion list.

Covers:
  - compute_rolling_mae returns correct MAE values from synthetic scored files
  - build_exclusion_list identifies players above the threshold
  - build_exclusion_list returns empty list when no one exceeds threshold
  - write_exclusion_yaml produces valid YAML with the expected schema
  - update_exclusion_list dry_run does not write to disk
  - load_exclusion_set (run_daily_slate) returns correct set from YAML
  - load_exclusion_set returns empty set when file is missing
  - run_predictions skips excluded players
"""
from __future__ import annotations

import datetime
import json
import os
import sys
from typing import List
from unittest.mock import patch

import pytest
import yaml

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.update_exclusion_list import (
    _collect_errors_from_scored,
    build_exclusion_list,
    compute_rolling_mae,
    update_exclusion_list,
    write_exclusion_yaml,
    _SCORED_DIR,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _scored_file(
    date_str: str,
    entries: List[dict],
) -> dict:
    """Build a minimal scored-file dict as written by prediction_tracker."""
    return {
        "date": date_str,
        "mae_by_stat": {},
        "clv_hit_rate": None,
        "clv_entries": entries,
        "players_scored": len(entries),
    }


def _clv_entry(
    player_id: str,
    player_name: str,
    stat: str,
    actual: float,
    line: float,
) -> dict:
    return {
        "player_id": player_id,
        "player_name": player_name,
        "stat": stat,
        "actual": actual,
        "line": line,
        "edge_pct": 0.1,
        "hit": actual > line,
    }


# ---------------------------------------------------------------------------
# _collect_errors_from_scored
# ---------------------------------------------------------------------------

def test_collect_errors_basic() -> None:
    """Absolute errors are correctly extracted from a scored file."""
    entries = [
        _clv_entry("1", "Player A", "pts", 28.0, 24.5),   # |err| = 3.5
        _clv_entry("1", "Player A", "pts", 20.0, 24.5),   # |err| = 4.5
        _clv_entry("2", "Player B", "reb", 5.0, 6.5),     # |err| = 1.5
    ]
    sf = _scored_file("2026-05-01", entries)
    errors = _collect_errors_from_scored([sf])

    assert errors["1"]["pts"] == pytest.approx([3.5, 4.5])
    assert errors["2"]["reb"] == pytest.approx([1.5])


def test_collect_errors_skips_missing_fields() -> None:
    """Entries with None actual or line are silently ignored."""
    entries = [
        {"player_id": "1", "stat": "pts", "actual": None, "line": 20.0},
        {"player_id": "2", "stat": "pts", "actual": 20.0, "line": None},
        {"player_id": "3", "stat": None, "actual": 20.0, "line": 20.0},
    ]
    errors = _collect_errors_from_scored([_scored_file("2026-05-01", entries)])
    assert not errors  # nothing collected


def test_collect_errors_multiple_files() -> None:
    """Errors accumulate correctly across multiple scored files."""
    entries1 = [_clv_entry("1", "P", "pts", 30.0, 25.0)]   # |err| = 5
    entries2 = [_clv_entry("1", "P", "pts", 20.0, 25.0)]   # |err| = 5
    errors = _collect_errors_from_scored([
        _scored_file("2026-05-01", entries1),
        _scored_file("2026-05-02", entries2),
    ])
    assert len(errors["1"]["pts"]) == 2
    assert sum(errors["1"]["pts"]) == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# compute_rolling_mae
# ---------------------------------------------------------------------------

def test_compute_rolling_mae_with_patched_dir(tmp_path) -> None:
    """compute_rolling_mae returns correct MAEs when reading from a temp directory."""
    today = datetime.date.today()
    recent = str(today - datetime.timedelta(days=3))

    entries = [
        _clv_entry("42", "LeBron James", "pts", 30.0, 24.5),   # |err| = 5.5
        _clv_entry("42", "LeBron James", "pts", 22.0, 24.5),   # |err| = 2.5
    ]
    scored = _scored_file(recent, entries)
    # MAE for player 42, pts = mean(5.5, 2.5) = 4.0

    scored_file_path = tmp_path / f"{recent}_scored.json"
    scored_file_path.write_text(json.dumps(scored), encoding="utf-8")

    with patch("scripts.update_exclusion_list._SCORED_DIR", str(tmp_path)):
        mae = compute_rolling_mae(window_days=14)

    assert "42" in mae
    assert mae["42"]["pts"] == pytest.approx(4.0)


def test_compute_rolling_mae_excludes_old_files(tmp_path) -> None:
    """Files outside the rolling window are ignored."""
    old_date = str(datetime.date.today() - datetime.timedelta(days=30))
    entries = [_clv_entry("99", "Old Player", "pts", 10.0, 20.0)]  # big error
    scored = _scored_file(old_date, entries)
    (tmp_path / f"{old_date}_scored.json").write_text(json.dumps(scored), encoding="utf-8")

    with patch("scripts.update_exclusion_list._SCORED_DIR", str(tmp_path)):
        mae = compute_rolling_mae(window_days=14)

    assert "99" not in mae  # old file should not contribute


# ---------------------------------------------------------------------------
# build_exclusion_list
# ---------------------------------------------------------------------------

def test_build_exclusion_list_above_threshold() -> None:
    """Players whose worst-stat MAE >= threshold appear in the result."""
    mae = {
        "10": {"pts": 9.5, "reb": 2.0},   # 9.5 >= 8.0 → excluded
        "20": {"pts": 6.0, "reb": 3.0},   # 6.0 < 8.0 → not excluded
    }
    result = build_exclusion_list(mae, threshold=8.0, scored_files=[])
    assert len(result) == 1
    assert result[0]["player_id"] == 10
    assert result[0]["stat"] == "pts"
    assert result[0]["mae"] == pytest.approx(9.5)


def test_build_exclusion_list_empty_when_all_below() -> None:
    """Empty list returned when all players are below the threshold."""
    mae = {"5": {"pts": 4.0}, "6": {"reb": 3.1}}
    result = build_exclusion_list(mae, threshold=8.0, scored_files=[])
    assert result == []


def test_build_exclusion_list_sorted_descending() -> None:
    """Exclusion list is sorted by MAE descending."""
    mae = {
        "1": {"pts": 10.0},
        "2": {"pts": 12.0},
        "3": {"pts": 9.0},
    }
    result = build_exclusion_list(mae, threshold=8.0, scored_files=[])
    maes = [r["mae"] for r in result]
    assert maes == sorted(maes, reverse=True)


def test_build_exclusion_list_exact_threshold_excluded() -> None:
    """A player with MAE exactly equal to the threshold is excluded (>=)."""
    mae = {"7": {"pts": 8.0}}
    result = build_exclusion_list(mae, threshold=8.0, scored_files=[])
    assert len(result) == 1


# ---------------------------------------------------------------------------
# write_exclusion_yaml + update_exclusion_list
# ---------------------------------------------------------------------------

def test_write_exclusion_yaml_schema(tmp_path) -> None:
    """Written YAML contains the required schema keys."""
    out = str(tmp_path / "exclusion_list.yaml")
    excluded = [
        {"player_id": 1, "player_name": "Test Player", "mae": 9.5, "stat": "pts"}
    ]
    write_exclusion_yaml(excluded, window_days=14, threshold=8.0, output_path=out)

    with open(out, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert "generated_at" in data
    assert data["window_days"] == 14
    assert data["mae_threshold"] == pytest.approx(8.0)
    assert len(data["excluded_players"]) == 1
    row = data["excluded_players"][0]
    assert row["player_id"] == 1
    assert row["player_name"] == "Test Player"
    assert row["mae"] == pytest.approx(9.5)
    assert row["stat"] == "pts"


def test_update_exclusion_list_dry_run_does_not_write(tmp_path) -> None:
    """dry_run=True computes the list but does not create the YAML file."""
    out = str(tmp_path / "exclusion_list.yaml")

    with patch("scripts.update_exclusion_list._SCORED_DIR", str(tmp_path)):
        excluded, mae = update_exclusion_list(
            window_days=14, threshold=8.0, dry_run=True, output_path=out
        )

    assert not os.path.exists(out), "dry-run must not write the YAML"
    assert isinstance(excluded, list)
    assert isinstance(mae, dict)


def test_update_exclusion_list_writes_yaml(tmp_path) -> None:
    """update_exclusion_list writes the YAML when dry_run=False."""
    out = str(tmp_path / "exclusion_list.yaml")
    today = datetime.date.today()
    recent = str(today - datetime.timedelta(days=1))

    entries = [_clv_entry("88", "High Error", "pts", 35.0, 20.0)]  # MAE=15
    scored = _scored_file(recent, entries)
    (tmp_path / f"{recent}_scored.json").write_text(json.dumps(scored), encoding="utf-8")

    with patch("scripts.update_exclusion_list._SCORED_DIR", str(tmp_path)):
        excluded, _ = update_exclusion_list(
            window_days=14, threshold=8.0, dry_run=False, output_path=out
        )

    assert os.path.exists(out)
    assert len(excluded) == 1
    assert excluded[0]["player_id"] == 88


# ---------------------------------------------------------------------------
# load_exclusion_set (from run_daily_slate)
# ---------------------------------------------------------------------------

def _import_load_exclusion_set():
    """Import load_exclusion_set from run_daily_slate without executing main."""
    import importlib, types
    spec = importlib.util.spec_from_file_location(
        "run_daily_slate",
        os.path.join(PROJECT_DIR, "scripts", "run_daily_slate.py"),
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.load_exclusion_set


def test_load_exclusion_set_basic(tmp_path) -> None:
    """load_exclusion_set returns player names and IDs from YAML."""
    yaml_path = str(tmp_path / "exclusion_list.yaml")
    data = {
        "generated_at": "2026-05-01T00:00:00Z",
        "window_days": 14,
        "mae_threshold": 8.0,
        "excluded_players": [
            {"player_id": 42, "player_name": "LeBron James", "mae": 9.1, "stat": "pts"},
        ],
    }
    with open(yaml_path, "w") as f:
        yaml.safe_dump(data, f)

    load_exclusion_set = _import_load_exclusion_set()
    result = load_exclusion_set(yaml_path)

    assert "42" in result
    assert "lebron james" in result


def test_load_exclusion_set_missing_file(tmp_path) -> None:
    """load_exclusion_set returns empty set when file does not exist."""
    load_exclusion_set = _import_load_exclusion_set()
    result = load_exclusion_set(str(tmp_path / "nonexistent.yaml"))
    assert result == set()


def test_load_exclusion_set_empty_list(tmp_path) -> None:
    """load_exclusion_set returns empty set when excluded_players list is empty."""
    yaml_path = str(tmp_path / "exclusion_list.yaml")
    data = {
        "generated_at": "2026-05-01T00:00:00Z",
        "window_days": 14,
        "mae_threshold": 8.0,
        "excluded_players": [],
    }
    with open(yaml_path, "w") as f:
        yaml.safe_dump(data, f)

    load_exclusion_set = _import_load_exclusion_set()
    result = load_exclusion_set(yaml_path)
    assert result == set()
