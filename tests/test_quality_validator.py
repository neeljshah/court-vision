"""
test_quality_validator.py — Unit tests for src/data/quality_validator.py.

Covers QualityValidator.THRESHOLDS logic, validate() result structure,
grade() levels, and all individual threshold checks.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.data.quality_validator import QualityValidator, SENTINEL_THRESHOLD


# ── fixtures ──────────────────────────────────────────────────────────────────

def _write_tracking_csv(path: Path, rows: list[dict] | None = None, n_rows: int = 0) -> None:
    """Write a minimal tracking_data.csv with given rows (or fill to n_rows)."""
    if rows is None:
        rows = []
    if not rows and n_rows:
        rows = [{"player_name": "LeBron", "team_abbrev": "LAL",
                 "homography_valid": 1, "nearest_opponent": 5.0,
                 "distance_to_ball": 3.0, "handler_isolation": 2.0}] * n_rows
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_possessions_csv(path: Path, n: int = 50) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["id", "duration_sec"])
        writer.writeheader()
        for i in range(n):
            writer.writerow({"id": i, "duration_sec": 18.0})


def _write_shot_log(path: Path, n: int = 30) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["frame", "player"])
        writer.writeheader()
        for i in range(n):
            writer.writerow({"frame": i, "player": "LeBron"})


def _make_healthy_game_dir(tmp_path: Path) -> Path:
    gd = tmp_path / "game_001"
    gd.mkdir()
    _write_tracking_csv(gd / "tracking_data.csv", n_rows=6000)
    _write_possessions_csv(gd / "possessions.csv", n=60)
    _write_shot_log(gd / "shot_log.csv", n=80)
    return gd


# ── THRESHOLDS dict ───────────────────────────────────────────────────────────

def test_thresholds_has_all_required_keys() -> None:
    """THRESHOLDS must contain the documented keys."""
    required = {
        "min_tracking_rows", "max_sentinel_pct", "min_possession_count",
        "min_shot_count", "min_player_name_pct", "min_homography_pct",
    }
    missing = required - set(QualityValidator.THRESHOLDS.keys())
    assert not missing, f"Missing threshold keys: {sorted(missing)}"


def test_sentinel_threshold_constant() -> None:
    """SENTINEL_THRESHOLD must be 199.5 (spatial sentinel values above this are invalid)."""
    assert SENTINEL_THRESHOLD == 199.5


# ── validate() result structure ───────────────────────────────────────────────

def test_validate_returns_dict_with_overall_passed(tmp_path: Path) -> None:
    """validate() returns a dict with 'overall_passed' key."""
    gd = _make_healthy_game_dir(tmp_path)
    v = QualityValidator(str(gd))
    result = v.validate()
    assert isinstance(result, dict)
    assert "overall_passed" in result


def test_validate_healthy_game_passes(tmp_path: Path) -> None:
    """A well-formed game directory should pass all thresholds."""
    gd = _make_healthy_game_dir(tmp_path)
    v = QualityValidator(str(gd))
    result = v.validate()
    assert result["overall_passed"] is True


def test_validate_tracking_rows_below_minimum(tmp_path: Path) -> None:
    """tracking_data.csv with < 5000 rows fails tracking_rows check."""
    gd = tmp_path / "game_bad"
    gd.mkdir()
    _write_tracking_csv(gd / "tracking_data.csv", n_rows=100)
    v = QualityValidator(str(gd))
    result = v.validate()
    assert not result["tracking_rows"]["passed"]
    assert result["overall_passed"] is False


def test_validate_each_metric_has_required_keys(tmp_path: Path) -> None:
    """Each metric sub-dict must have 'value', 'threshold', 'passed' keys."""
    gd = _make_healthy_game_dir(tmp_path)
    v = QualityValidator(str(gd))
    result = v.validate()
    for key, val in result.items():
        if isinstance(val, dict) and key != "overall_passed":
            assert "value" in val, f"metric '{key}' missing 'value'"
            assert "threshold" in val, f"metric '{key}' missing 'threshold'"
            assert "passed" in val, f"metric '{key}' missing 'passed'"


def test_validate_sentinel_flag_with_high_values(tmp_path: Path) -> None:
    """Rows with sentinel values > 199.5 should inflate sentinel_pct."""
    gd = tmp_path / "game_sentinel"
    gd.mkdir()
    n_total = 6000
    n_sentinel = 1500  # 25% sentinel — above 5% threshold
    rows = []
    for i in range(n_total):
        sentinel_val = 200.0 if i < n_sentinel else 5.0
        rows.append({
            "player_name": "LeBron",
            "team_abbrev": "LAL",
            "homography_valid": 1,
            "nearest_opponent": sentinel_val,
            "distance_to_ball": 3.0,
            "handler_isolation": 2.0,
        })
    _write_tracking_csv(gd / "tracking_data.csv", rows=rows)
    v = QualityValidator(str(gd))
    result = v.validate()
    assert not result["sentinel_pct"]["passed"]


def test_validate_no_tracking_file(tmp_path: Path) -> None:
    """Empty game dir (no CSVs) should have tracking_rows = 0 → failed."""
    gd = tmp_path / "game_empty"
    gd.mkdir()
    v = QualityValidator(str(gd))
    result = v.validate()
    assert result["tracking_rows"]["value"] == 0
    assert not result["tracking_rows"]["passed"]


# ── possession checks ─────────────────────────────────────────────────────────

def test_validate_insufficient_possessions(tmp_path: Path) -> None:
    """possessions.csv with < 30 rows fails possession_count check."""
    gd = tmp_path / "game_poss"
    gd.mkdir()
    _write_tracking_csv(gd / "tracking_data.csv", n_rows=6000)
    _write_possessions_csv(gd / "possessions.csv", n=10)
    v = QualityValidator(str(gd))
    result = v.validate()
    assert not result["possession_count"]["passed"]


# ── shot count checks ─────────────────────────────────────────────────────────

def test_validate_shot_count_below_minimum(tmp_path: Path) -> None:
    """shot_log.csv with fewer than 5 shots fails shot_count check."""
    gd = tmp_path / "game_shots"
    gd.mkdir()
    _write_tracking_csv(gd / "tracking_data.csv", n_rows=6000)
    _write_possessions_csv(gd / "possessions.csv", n=60)
    _write_shot_log(gd / "shot_log.csv", n=2)
    v = QualityValidator(str(gd))
    result = v.validate()
    assert not result["shot_count"]["passed"]


# ── grade() ───────────────────────────────────────────────────────────────────

def test_grade_a_for_healthy_game(tmp_path: Path) -> None:
    """Healthy game directory should receive grade 'A' (≥90% checks pass)."""
    gd = _make_healthy_game_dir(tmp_path)
    v = QualityValidator(str(gd))
    assert v.grade() == "A"


def test_grade_f_for_empty_dir(tmp_path: Path) -> None:
    """Empty game dir with all zeros should receive grade 'F'."""
    gd = tmp_path / "game_f"
    gd.mkdir()
    v = QualityValidator(str(gd))
    assert v.grade() == "F"


def test_grade_returns_valid_letter(tmp_path: Path) -> None:
    """grade() always returns one of A, B, C, F."""
    gd = tmp_path / "game_any"
    gd.mkdir()
    v = QualityValidator(str(gd))
    assert v.grade() in ("A", "B", "C", "F")
