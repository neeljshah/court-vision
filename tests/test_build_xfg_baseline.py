"""
tests/test_build_xfg_baseline.py — Phase 41: xFG gap baseline tests.

Covers:
    1. gap = actual_fg - expected_fg is computed correctly from synthetic data.
    2. Output JSON has the required structure for every player.
    3. No-data path exits cleanly and writes a valid empty baseline.
    4. Players with identical shots receive gap == 0 when model is perfectly calibrated.
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# Ensure project root is on sys.path
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.build_xfg_baseline import build_baseline, write_output, main


# ── helpers ───────────────────────────────────────────────────────────────────

def _shot_row(
    player_id: int,
    made: int,
    xfg_pred: float,
    name: str = "",
) -> dict:
    """Return a minimal shot row with all columns expected by build_baseline."""
    return {
        "player_id":       player_id,
        "player_name":     name,
        "shot_made_flag":  made,
        "shot_zone_basic": "Above the Break 3",
        "shot_zone_area":  "Center(C)",
        "shot_zone_range": "24+ ft.",
        "shot_distance":   25,
        "shot_type":       "3PT Field Goal",
        "action_type":     "Jump Shot",
        "_xfg_preset":     xfg_pred,   # consumed by helper below
    }


def _build(rows: list[dict]) -> dict:
    """
    Convenience: build DataFrame from rows, extract preset xfg predictions,
    wire mock model, and call build_baseline.
    """
    df = pd.DataFrame(rows)
    preset = df.pop("_xfg_preset").reset_index(drop=True)

    mock_model = MagicMock()
    mock_model.predict_batch.return_value = preset

    return build_baseline(df, model=mock_model)


# ── test: correct gap calculation ─────────────────────────────────────────────

def test_gap_equals_actual_minus_expected() -> None:
    """
    Given 4 shots for player 999:
        made=1, xfg=0.4
        made=1, xfg=0.5
        made=0, xfg=0.3
        made=0, xfg=0.6

    actual_fg   = 2/4 = 0.5
    expected_fg = (0.4+0.5+0.3+0.6)/4 = 0.45
    gap         = 0.5 - 0.45 = 0.05
    """
    result = _build([
        _shot_row(999, made=1, xfg_pred=0.4, name="Test Player"),
        _shot_row(999, made=1, xfg_pred=0.5),
        _shot_row(999, made=0, xfg_pred=0.3),
        _shot_row(999, made=0, xfg_pred=0.6),
    ])

    assert "999" in result, "Player 999 must appear in baseline"
    rec = result["999"]

    assert rec["n_shots"] == 4
    assert abs(rec["actual_fg"]   - 0.5)  < 1e-6, f"actual_fg={rec['actual_fg']}"
    assert abs(rec["expected_fg"] - 0.45) < 1e-6, f"expected_fg={rec['expected_fg']}"
    assert abs(rec["gap"]         - 0.05) < 1e-6, f"gap={rec['gap']}"
    assert rec["player_name"] == "Test Player"


# ── test: JSON output structure ────────────────────────────────────────────────

def test_output_structure_has_required_keys() -> None:
    """Every player record must contain actual_fg, expected_fg, gap, n_shots, player_name."""
    result = _build([
        _shot_row(1, made=1, xfg_pred=0.5),
        _shot_row(1, made=0, xfg_pred=0.5),
        _shot_row(2, made=1, xfg_pred=0.6),
        _shot_row(2, made=1, xfg_pred=0.6),
        _shot_row(2, made=0, xfg_pred=0.6),
    ])

    required_keys = {"actual_fg", "expected_fg", "gap", "n_shots", "player_name"}
    for pid, rec in result.items():
        missing = required_keys - set(rec.keys())
        assert not missing, f"Player {pid} record missing keys: {missing}"


def test_gap_is_actual_minus_expected_algebraically() -> None:
    """gap == actual_fg - expected_fg (rounded) for every player record."""
    result = _build([
        _shot_row(10, made=1, xfg_pred=0.3),
        _shot_row(10, made=0, xfg_pred=0.3),
        _shot_row(20, made=1, xfg_pred=0.7),
        _shot_row(20, made=1, xfg_pred=0.7),
    ])

    for pid, rec in result.items():
        expected_gap = round(rec["actual_fg"] - rec["expected_fg"], 4)
        assert abs(rec["gap"] - expected_gap) < 1e-6, (
            f"Player {pid}: gap {rec['gap']} != "
            f"actual-expected {expected_gap}"
        )


# ── test: no-data path ────────────────────────────────────────────────────────

def test_no_data_empty_dataframe_returns_empty_dict() -> None:
    """build_baseline on an empty DataFrame returns {} without crashing."""
    result = build_baseline(pd.DataFrame())
    assert result == {}


def test_no_data_write_produces_valid_empty_json(tmp_path) -> None:
    """write_output({}) creates a file that parses as an empty JSON object."""
    out_file = tmp_path / "player_xfg_gaps.json"

    import scripts.build_xfg_baseline as mod
    original_out = mod.OUT_PATH
    mod.OUT_PATH = str(out_file)
    try:
        write_output({})
    finally:
        mod.OUT_PATH = original_out

    assert out_file.exists(), "Output file must be created by write_output"
    with open(out_file) as fh:
        data = json.load(fh)
    assert data == {}, f"Expected {{}} but got: {data!r}"


def test_main_no_data_exits_cleanly_and_writes_valid_file(tmp_path, monkeypatch) -> None:
    """
    When no shot_chart files exist, main() must not raise and must write
    a valid JSON file containing {}.
    """
    out_file = tmp_path / "player_xfg_gaps.json"

    import scripts.build_xfg_baseline as mod
    monkeypatch.setattr(mod, "OUT_PATH", str(out_file))
    monkeypatch.setattr(mod, "NBA_DIR",  str(tmp_path))  # empty dir → no files

    main()  # must not raise

    assert out_file.exists(), "main() must create output file even with no data"
    with open(out_file) as fh:
        data = json.load(fh)
    assert isinstance(data, dict), "Output must be a JSON object"
    assert data == {}, f"Expected {{}} but got: {data!r}"


# ── test: edge case — model perfectly calibrated ──────────────────────────────

def test_zero_gap_when_model_perfectly_calibrated() -> None:
    """gap is 0.0 when model's expected_fg matches actual_fg exactly."""
    result = _build([
        _shot_row(77, made=1, xfg_pred=0.5),
        _shot_row(77, made=1, xfg_pred=0.5),
        _shot_row(77, made=0, xfg_pred=0.5),
        _shot_row(77, made=0, xfg_pred=0.5),
    ])
    assert abs(result["77"]["gap"]) < 1e-6, f"gap={result['77']['gap']!r}"
