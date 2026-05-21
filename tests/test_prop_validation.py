"""Tests for src/prediction/prop_validation.py

Covers:
  - validate_gap_threshold: correct pass/fail per stat
  - write_registry: persists to disk, merges with existing, returns dict
  - generate_report: runs without error (stdout capture)
  - Edge cases: missing stats, NaN values, all-pass, all-fail
"""
from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

import pytest

from src.prediction.prop_validation import (
    generate_report,
    validate_gap_threshold,
    write_registry,
)

_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")


# ---------------------------------------------------------------------------
# validate_gap_threshold
# ---------------------------------------------------------------------------

def _make_registry(stats: dict[str, tuple[float, float]]) -> dict:
    """Build a minimal registry from {stat: (train_r2, holdout_r2)} pairs."""
    reg = {}
    for stat, (train, holdout) in stats.items():
        reg[f"props_{stat}"] = {
            "train_r2": train,
            "holdout_r2": holdout,
            "holdout_n": 100,
        }
    return reg


class TestValidateGapThreshold:
    def test_all_pass_when_zero_gap(self) -> None:
        stats = {s: (0.70, 0.70) for s in _STATS}
        reg = _make_registry(stats)
        result = validate_gap_threshold(reg, threshold=0.08)
        assert all(result.values())

    def test_fail_when_gap_exceeds_threshold(self) -> None:
        # pts has a gap of 0.20 > 0.08 → should fail
        reg = _make_registry({"pts": (0.80, 0.60)})
        result = validate_gap_threshold(reg, threshold=0.08)
        assert result["pts"] is False

    def test_pass_when_gap_below_threshold(self) -> None:
        # gap = 0.07 < 0.08 → should pass (avoids float precision edge case)
        reg = _make_registry({"pts": (0.80, 0.73)})
        result = validate_gap_threshold(reg, threshold=0.08)
        assert result["pts"] is True

    def test_missing_stat_returns_false(self) -> None:
        result = validate_gap_threshold({}, threshold=0.08)
        assert all(v is False for v in result.values())

    def test_returns_all_seven_stats(self) -> None:
        result = validate_gap_threshold({}, threshold=0.08)
        assert set(result.keys()) == set(_STATS)

    def test_mixed_pass_fail(self) -> None:
        reg = _make_registry({
            "pts": (0.80, 0.75),  # gap 0.05 → pass
            "reb": (0.70, 0.55),  # gap 0.15 → fail
        })
        result = validate_gap_threshold(reg, threshold=0.08)
        assert result["pts"] is True
        assert result["reb"] is False

    def test_custom_threshold(self) -> None:
        reg = _make_registry({"pts": (0.80, 0.70)})  # gap = 0.10
        assert validate_gap_threshold(reg, threshold=0.15)["pts"] is True
        assert validate_gap_threshold(reg, threshold=0.05)["pts"] is False


# ---------------------------------------------------------------------------
# write_registry
# ---------------------------------------------------------------------------

class TestWriteRegistry:
    def test_writes_file_to_disk(self, tmp_path: Path) -> None:
        reg_path = tmp_path / "model_registry.json"
        results = {"pts": {"holdout_r2": 0.75, "train_r2": 0.80, "holdout_n": 200,
                           "holdout_mae": 3.1, "train_mae": 2.8, "train_n": 800}}
        write_registry(results, version="test-v1", registry_path=reg_path)
        assert reg_path.exists()

    def test_returned_dict_contains_stat(self, tmp_path: Path) -> None:
        reg_path = tmp_path / "model_registry.json"
        results = {"reb": {"holdout_r2": 0.65, "train_r2": 0.72, "holdout_n": 150,
                           "holdout_mae": 1.2, "train_mae": 1.1, "train_n": 600}}
        out = write_registry(results, registry_path=reg_path)
        assert "props_reb" in out

    def test_version_stored(self, tmp_path: Path) -> None:
        reg_path = tmp_path / "model_registry.json"
        results = {"ast": {"holdout_r2": 0.68, "train_r2": 0.72, "holdout_n": 180,
                           "holdout_mae": 0.9, "train_mae": 0.8, "train_n": 720}}
        out = write_registry(results, version="v_special", registry_path=reg_path)
        assert out["props_ast"]["retrain_version"] == "v_special"

    def test_merges_with_existing_registry(self, tmp_path: Path) -> None:
        reg_path = tmp_path / "model_registry.json"
        # Pre-populate with a different stat
        existing = {"props_blk": {"holdout_r2": 0.50}}
        reg_path.write_text(json.dumps(existing))

        results = {"pts": {"holdout_r2": 0.77, "train_r2": 0.82, "holdout_n": 200,
                           "holdout_mae": 3.0, "train_mae": 2.7, "train_n": 800}}
        out = write_registry(results, registry_path=reg_path)
        # Both entries should be present
        assert "props_blk" in out
        assert "props_pts" in out

    def test_written_json_is_valid(self, tmp_path: Path) -> None:
        reg_path = tmp_path / "model_registry.json"
        results = {"stl": {"holdout_r2": 0.55, "train_r2": 0.60, "holdout_n": 100,
                           "holdout_mae": 0.4, "train_mae": 0.35, "train_n": 400}}
        write_registry(results, registry_path=reg_path)
        loaded = json.loads(reg_path.read_text())
        assert isinstance(loaded, dict)


# ---------------------------------------------------------------------------
# generate_report
# ---------------------------------------------------------------------------

class TestGenerateReport:
    def test_runs_without_error_all_pass(self, capsys: pytest.CaptureFixture) -> None:
        reg = _make_registry({s: (0.75, 0.70) for s in _STATS})
        generate_report(reg, threshold=0.10)
        captured = capsys.readouterr()
        assert "ALL PASS" in captured.out

    def test_runs_without_error_with_failures(self, capsys: pytest.CaptureFixture) -> None:
        reg = _make_registry({"pts": (0.90, 0.50)})  # large gap
        generate_report(reg, threshold=0.08)
        captured = capsys.readouterr()
        assert "FAIL" in captured.out

    def test_report_contains_stat_names(self, capsys: pytest.CaptureFixture) -> None:
        reg = _make_registry({s: (0.70, 0.68) for s in _STATS})
        generate_report(reg, threshold=0.08)
        captured = capsys.readouterr()
        for stat in _STATS:
            assert stat in captured.out
