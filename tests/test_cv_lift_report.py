"""
tests/test_cv_lift_report.py — Tests for scripts/cv_lift_report.py.

Covers:
  - run() exits 0 on the no-CV-data path (synthetic residuals, no CV columns).
  - Resulting JSON has the expected top-level structure.
  - Stats that have no CV records are reported as "no CV data".
  - When CV records DO exist, delta R² and MAE are computed correctly.
  - Missing residuals file is handled gracefully (exits 0, "no CV data" per stat).
"""

from __future__ import annotations

import json
import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.cv_lift_report import (  # noqa: E402
    _STATS,
    _has_cv_features,
    compute_lift,
    run,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(
    stat: str = "pts",
    actual: float = 20.0,
    predicted: float = 18.0,
    **extra,
) -> dict:
    """Return a minimal residual record."""
    rec = {
        "player_id": 1,
        "player_name": "Test Player",
        "game_date": "Jan 01, 2025",
        "season": "2024-25",
        "stat": stat,
        "predicted": predicted,
        "actual": actual,
        "line": 20.0,
        "edge_pct": 0.05,
        "direction": "over",
    }
    rec.update(extra)
    return rec


# ---------------------------------------------------------------------------
# _has_cv_features
# ---------------------------------------------------------------------------

def test_has_cv_features_no_cv_columns() -> None:
    """Record with no CV columns returns False."""
    rec = _make_record()
    assert _has_cv_features(rec) is False


def test_has_cv_features_with_defender_distance() -> None:
    """Record with defender_distance populated returns True."""
    rec = _make_record(defender_distance=3.5)
    assert _has_cv_features(rec) is True


def test_has_cv_features_with_none_value() -> None:
    """Record with defender_distance=None is still treated as non-CV."""
    rec = _make_record(defender_distance=None)
    assert _has_cv_features(rec) is False


def test_has_cv_features_with_spacing() -> None:
    """Record with spacing column returns True."""
    rec = _make_record(spacing=12.4)
    assert _has_cv_features(rec) is True


# ---------------------------------------------------------------------------
# compute_lift — no-CV path
# ---------------------------------------------------------------------------

def test_compute_lift_no_cv_records() -> None:
    """All stats are reported as 'no CV data' when no CV columns are present."""
    records = [_make_record(stat=s) for s in _STATS for _ in range(5)]
    report = compute_lift(records)

    assert report["has_cv_data"] is False
    for stat in _STATS:
        assert report["stats"][stat] == "no CV data", f"Expected 'no CV data' for {stat}"


def test_compute_lift_empty_records() -> None:
    """Empty records list produces no-CV report without crashing."""
    report = compute_lift([])
    assert report["has_cv_data"] is False
    assert set(report["stats"].keys()) == set(_STATS)


# ---------------------------------------------------------------------------
# compute_lift — with CV records
# ---------------------------------------------------------------------------

def test_compute_lift_with_cv_records() -> None:
    """Delta values are computed when CV records are present."""
    no_cv = [_make_record(stat="pts", actual=float(i), predicted=float(i) - 1) for i in range(1, 11)]
    cv = [_make_record(stat="pts", actual=float(i), predicted=float(i) - 0.5, defender_distance=3.0) for i in range(1, 11)]
    records = no_cv + cv

    report = compute_lift(records)

    assert report["has_cv_data"] is True
    pts = report["stats"]["pts"]
    assert isinstance(pts, dict), "pts entry should be a dict when CV data exists"
    assert pts["cv"]["n"] == 10
    assert pts["no_cv"]["n"] == 10
    # CV group has smaller residuals → better MAE → negative delta_mae
    assert pts["delta"]["mae"] is not None
    assert pts["delta"]["mae"] < 0  # CV MAE < no-CV MAE


def test_compute_lift_stats_without_cv_show_no_cv_data() -> None:
    """Stats with no CV records at all show 'no CV data' even when other stats have CV."""
    # Only pts has CV records; all others lack CV columns
    cv_pts = [_make_record(stat="pts", actual=10.0, predicted=9.0, defender_distance=2.5)]
    no_cv_pts = [_make_record(stat="pts", actual=12.0, predicted=11.0)]
    no_cv_reb = [_make_record(stat="reb", actual=5.0, predicted=4.5)]

    records = cv_pts + no_cv_pts + no_cv_reb
    report = compute_lift(records)

    # has_cv_data is True (at least one record has CV features)
    assert report["has_cv_data"] is True
    # pts is a proper dict
    assert isinstance(report["stats"]["pts"], dict)
    # reb has no CV records → its delta fields should be None
    reb = report["stats"]["reb"]
    assert isinstance(reb, dict)
    assert reb["cv"]["n"] == 0
    assert reb["delta"]["r2"] is None
    assert reb["delta"]["mae"] is None


# ---------------------------------------------------------------------------
# run() — no-CV path via file
# ---------------------------------------------------------------------------

def test_run_no_cv_exits_0_and_writes_json(tmp_path) -> None:
    """run() exits 0 on the no-CV path and writes expected JSON structure."""
    # Build synthetic residuals without any CV columns
    records = [_make_record(stat=s) for s in _STATS for _ in range(10)]
    residuals_file = str(tmp_path / "prop_residuals.json")
    with open(residuals_file, "w") as fh:
        json.dump(records, fh)

    output_file = str(tmp_path / "cv_lift_report.json")
    exit_code = run(residuals_path=residuals_file, output_path=output_file)

    assert exit_code == 0, "run() must exit 0 on no-CV path"
    assert os.path.exists(output_file), "Output JSON must be written"

    with open(output_file) as fh:
        report = json.load(fh)

    # Top-level keys
    assert "has_cv_data" in report
    assert "stats" in report
    assert report["has_cv_data"] is False

    # Every target stat present and marked "no CV data"
    for stat in _STATS:
        assert stat in report["stats"]
        assert report["stats"][stat] == "no CV data"


def test_run_missing_residuals_file_exits_0(tmp_path) -> None:
    """run() exits 0 even when the residuals file does not exist."""
    residuals_file = str(tmp_path / "nonexistent.json")
    output_file = str(tmp_path / "cv_lift_report.json")

    exit_code = run(residuals_path=residuals_file, output_path=output_file)

    assert exit_code == 0
    assert os.path.exists(output_file)

    with open(output_file) as fh:
        report = json.load(fh)

    assert report["has_cv_data"] is False
    for stat in _STATS:
        assert report["stats"][stat] == "no CV data"


def test_run_with_cv_data_writes_delta_structure(tmp_path) -> None:
    """run() writes delta dict entries when CV data is present."""
    no_cv = [_make_record(stat="pts", actual=float(i), predicted=float(i) * 0.9) for i in range(1, 21)]
    cv = [_make_record(stat="pts", actual=float(i), predicted=float(i) * 0.95, spacing=10.0) for i in range(1, 21)]
    records = no_cv + cv

    residuals_file = str(tmp_path / "prop_residuals.json")
    with open(residuals_file, "w") as fh:
        json.dump(records, fh)

    output_file = str(tmp_path / "cv_lift_report.json")
    exit_code = run(residuals_path=residuals_file, output_path=output_file)

    assert exit_code == 0

    with open(output_file) as fh:
        report = json.load(fh)

    assert report["has_cv_data"] is True
    pts = report["stats"]["pts"]
    assert isinstance(pts, dict)
    assert "cv" in pts and "no_cv" in pts and "delta" in pts
    assert "r2" in pts["delta"]
    assert "mae" in pts["delta"]
