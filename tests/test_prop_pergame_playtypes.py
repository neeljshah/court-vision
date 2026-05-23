"""
test_prop_pergame_playtypes.py -- Tests for PRED-12: playtype_rates wired into prop_pergame.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    _PLAY_TYPES,
    _PLAYTYPE_DEFAULTS,
    build_playtypes,
    build_prediction_row,
    feature_columns,
)


def test_playtype_columns_present_in_feature_columns():
    """All 9 pt_<playtype>_freq columns appear in feature_columns()."""
    cols = feature_columns()
    for pt in _PLAY_TYPES:
        assert f"pt_{pt}_freq" in cols, f"Missing column: pt_{pt}_freq"


def test_build_playtypes_no_parquet():
    """build_playtypes returns zero defaults when the parquet does not exist."""
    pt = build_playtypes(cache_path="/nonexistent.parquet")
    feats = pt.features(123, "2024-25")
    assert feats == dict(_PLAYTYPE_DEFAULTS)
    assert len(feats) == 9
    assert all(v == 0.0 for v in feats.values())


def test_build_playtypes_corrupt_file(tmp_path):
    """build_playtypes returns defaults without raising when the file is corrupt."""
    corrupt = tmp_path / "p.parquet"
    corrupt.write_text("not parquet")
    pt = build_playtypes(str(corrupt))
    feats = pt.features(1, "2024-25")
    assert feats == dict(_PLAYTYPE_DEFAULTS)


def test_build_playtypes_normalizes_play_type_names(tmp_path):
    """Mixed-case and spaced play_type values are normalized to lowercase-nospace."""
    pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")

    import pandas as _pd

    parquet_path = tmp_path / "playtypes.parquet"
    rows = [
        {"player_id": 1, "play_type": "PRBallHandler", "season": "2024-25", "freq_pct": 0.25},
        {"player_id": 1, "play_type": "Isolation",     "season": "2024-25", "freq_pct": 0.10},
        # "Off Screen" with a space — must normalize to "offscreen"
        {"player_id": 1, "play_type": "Off Screen",    "season": "2024-25", "freq_pct": 0.05},
    ]
    _pd.DataFrame(rows).to_parquet(str(parquet_path), index=False)

    pt = build_playtypes(str(parquet_path))
    feats = pt.features(1, "2024-25")

    assert feats["pt_prballhandler_freq"] == 0.25
    assert feats["pt_isolation_freq"] == 0.10
    assert feats["pt_offscreen_freq"] == 0.05
    # Missing play types fill with 0.0, not raise.
    assert feats["pt_cut_freq"] == 0.0
    # All 9 keys present.
    assert set(feats.keys()) == {f"pt_{p}_freq" for p in _PLAY_TYPES}


def test_build_prediction_row_includes_playtypes(tmp_path):
    """build_prediction_row returns a dict with all 9 pt_<pt>_freq keys."""
    # Write a minimal gamelog with >=6 played games.
    games = []
    for d in range(1, 10):
        games.append({
            "GAME_DATE": f"Jan {d:02d}, 2025",
            "MATCHUP": "SAS vs. TOR",
            "PTS": 20, "REB": 5, "AST": 4, "FG3M": 2,
            "STL": 1, "BLK": 0, "TOV": 2, "MIN": 30.0,
        })
    gamelog_path = tmp_path / "gamelog_42_2024-25.json"
    gamelog_path.write_text(json.dumps(games), encoding="utf-8")

    row = build_prediction_row(
        player_id=42,
        opp_team="TOR",
        season="2024-25",
        gamelog_dir=str(tmp_path),
    )
    assert row is not None, "build_prediction_row returned None unexpectedly"
    for pt in _PLAY_TYPES:
        key = f"pt_{pt}_freq"
        assert key in row, f"Missing key in prediction row: {key}"
        # No parquet in tmp_path -> all defaults = 0.0
        assert row[key] == 0.0
