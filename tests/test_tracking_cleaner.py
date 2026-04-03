"""Tests for TrackingCleaner and QualityValidator."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from src.data.tracking_cleaner import TrackingCleaner, SENTINEL_THRESHOLD
from src.data.quality_validator import QualityValidator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def game_dir(tmp_path):
    """Create a minimal game directory with test CSVs."""
    return tmp_path


def _write_tracking(game_dir: Path, df: pd.DataFrame) -> None:
    df.to_csv(game_dir / "tracking_data.csv", index=False, encoding="utf-8")


def _write_possessions(game_dir: Path, df: pd.DataFrame) -> None:
    df.to_csv(game_dir / "possessions.csv", index=False, encoding="utf-8")


def _write_shots(game_dir: Path, df: pd.DataFrame) -> None:
    df.to_csv(game_dir / "shot_log.csv", index=False, encoding="utf-8")


def _write_features(game_dir: Path, df: pd.DataFrame) -> None:
    df.to_csv(game_dir / "features.csv", index=False, encoding="utf-8")


# ---------------------------------------------------------------------------
# TrackingCleaner — sentinel removal
# ---------------------------------------------------------------------------

def test_sentinel_nearest_opponent_blanked(game_dir):
    df = pd.DataFrame({
        "nearest_opponent": [200.0, 5.0, 199.5, 1.0],
        "handler_isolation": [1.0, 2.0, 3.0, 4.0],
    })
    _write_tracking(game_dir, df)
    cleaner = TrackingCleaner(str(game_dir))
    result = cleaner.clean_tracking()
    # 200.0 and 199.5 should be NaN
    assert pd.isna(result["nearest_opponent"].iloc[0])
    assert pd.isna(result["nearest_opponent"].iloc[2])
    assert result["nearest_opponent"].iloc[1] == 5.0


def test_sentinel_handler_isolation_blanked(game_dir):
    df = pd.DataFrame({
        "handler_isolation": [200.0, 3.5, 199.6],
        "nearest_opponent": [1.0, 2.0, 3.0],
    })
    _write_tracking(game_dir, df)
    result = TrackingCleaner(str(game_dir)).clean_tracking()
    assert pd.isna(result["handler_isolation"].iloc[0])
    assert pd.isna(result["handler_isolation"].iloc[2])
    assert result["handler_isolation"].iloc[1] == 3.5


# ---------------------------------------------------------------------------
# TrackingCleaner — coordinate clipping
# ---------------------------------------------------------------------------

def test_x_norm_clipped(game_dir):
    df = pd.DataFrame({
        "x_norm": [1.5, 0.5, -0.1],
        "y_norm": [0.5, 0.5, 0.5],
    })
    _write_tracking(game_dir, df)
    result = TrackingCleaner(str(game_dir)).clean_tracking()
    assert result["x_norm"].iloc[0] == 1.0
    assert result["x_norm"].iloc[1] == 0.5
    assert result["x_norm"].iloc[2] == 0.0


def test_ft_x_clipped(game_dir):
    df = pd.DataFrame({"ft_x": [100.0, 50.0, -5.0], "ft_y": [25.0, 25.0, 25.0]})
    _write_tracking(game_dir, df)
    result = TrackingCleaner(str(game_dir)).clean_tracking()
    assert result["ft_x"].iloc[0] == 94.0
    assert result["ft_x"].iloc[2] == 0.0


# ---------------------------------------------------------------------------
# TrackingCleaner — homography_valid added when missing
# ---------------------------------------------------------------------------

def test_homography_valid_added_when_missing(game_dir):
    df = pd.DataFrame({"x_norm": [0.5], "y_norm": [0.5]})
    _write_tracking(game_dir, df)
    result = TrackingCleaner(str(game_dir)).clean_tracking()
    assert "homography_valid" in result.columns
    assert result["homography_valid"].iloc[0] == 0


# ---------------------------------------------------------------------------
# TrackingCleaner — spacing_advantage clipped
# ---------------------------------------------------------------------------

def test_spacing_advantage_clipped(game_dir):
    df = pd.DataFrame({"spacing_advantage": [10000.0, -8000.0, 100.0]})
    _write_features(game_dir, df)
    result = TrackingCleaner(str(game_dir)).clean_features()
    assert result["spacing_advantage"].iloc[0] == 5000.0
    assert result["spacing_advantage"].iloc[1] == -5000.0
    assert result["spacing_advantage"].iloc[2] == 100.0


# ---------------------------------------------------------------------------
# TrackingCleaner — possession merge
# ---------------------------------------------------------------------------

def test_possession_merge_small_gap(game_dir):
    """Two same-team possessions 3s apart should merge into one."""
    fps = 30
    df = pd.DataFrame({
        "team": ["NYK", "NYK"],
        "start_frame": [0, int(5 * fps)],    # 0s, 5s start
        "end_frame":   [int(3 * fps), int(10 * fps)],  # 3s, 10s end
        "duration_sec": [3.0, 5.0],
        "duration_frames": [90, 150],
    })
    _write_possessions(game_dir, df)
    result = TrackingCleaner(str(game_dir)).clean_possessions()
    # gap = 5s - 3s = 2s < 5s → should merge to one row
    assert len(result) == 1
    assert result["end_frame"].iloc[0] == int(10 * fps)


def test_possession_filter_short(game_dir):
    """Possessions < 2s should be dropped."""
    fps = 30
    df = pd.DataFrame({
        "team": ["NYK", "CLE"],
        "start_frame": [0, 100],
        "end_frame": [30, 200],       # 1s and ~3.3s
        "duration_sec": [1.0, 3.3],
        "duration_frames": [30, 100],
    })
    _write_possessions(game_dir, df)
    result = TrackingCleaner(str(game_dir)).clean_possessions()
    assert len(result) == 1
    assert result["team"].iloc[0] == "CLE"


# ---------------------------------------------------------------------------
# TrackingCleaner — shot dedup
# ---------------------------------------------------------------------------

def test_shot_dedup_within_window(game_dir):
    """Two shots within 8s should collapse to one."""
    df = pd.DataFrame({
        "timestamp": [10.0, 14.0, 30.0],
        "player_id": ["p1", "p2", "p3"],
        "defender_distance": [5.0, 6.0, 7.0],
    })
    _write_shots(game_dir, df)
    result = TrackingCleaner(str(game_dir)).clean_shots()
    assert len(result) == 2
    assert result["timestamp"].iloc[0] == 10.0
    assert result["timestamp"].iloc[1] == 30.0


def test_shot_defender_distance_sentinel(game_dir):
    """defender_distance >= 199.5 → NaN in shot_log."""
    df = pd.DataFrame({
        "timestamp": [10.0, 30.0],
        "defender_distance": [200.0, 4.5],
    })
    _write_shots(game_dir, df)
    result = TrackingCleaner(str(game_dir)).clean_shots()
    assert pd.isna(result["defender_distance"].iloc[0])
    assert result["defender_distance"].iloc[1] == 4.5


# ---------------------------------------------------------------------------
# TrackingCleaner — backup files created
# ---------------------------------------------------------------------------

def test_backup_created(game_dir):
    df = pd.DataFrame({"nearest_opponent": [200.0, 5.0]})
    _write_tracking(game_dir, df)
    TrackingCleaner(str(game_dir)).clean_tracking()
    assert (game_dir / "tracking_data.csv.bak").exists()


def test_clean_idempotent(game_dir):
    """Running cleaner twice should produce same result as running once."""
    df = pd.DataFrame({
        "nearest_opponent": [200.0, 5.0],
        "x_norm": [1.5, 0.5],
        "y_norm": [0.5, 0.5],
    })
    _write_tracking(game_dir, df)
    r1 = TrackingCleaner(str(game_dir)).clean_tracking()
    r2 = TrackingCleaner(str(game_dir)).clean_tracking()
    pd.testing.assert_frame_equal(r1.reset_index(drop=True), r2.reset_index(drop=True))


# ---------------------------------------------------------------------------
# TrackingCleaner — overflow guard
# ---------------------------------------------------------------------------

def test_overflow_guard(game_dir):
    df = pd.DataFrame({"some_rolling_col": [1e7, 5.0, -2e8]})
    _write_features(game_dir, df)
    result = TrackingCleaner(str(game_dir)).clean_features()
    assert pd.isna(result["some_rolling_col"].iloc[0])
    assert result["some_rolling_col"].iloc[1] == 5.0
    assert pd.isna(result["some_rolling_col"].iloc[2])


# ---------------------------------------------------------------------------
# QualityValidator
# ---------------------------------------------------------------------------

def _make_good_game(game_dir: Path) -> None:
    """Write a game that passes all quality thresholds."""
    tracking = pd.DataFrame({
        "nearest_opponent": [5.0] * 6000,
        "handler_isolation": [3.0] * 6000,
        "player_name": ["LeBron"] * 6000,
        "team_abbrev": ["LAL"] * 6000,
        "homography_valid": [1] * 6000,
    })
    poss = pd.DataFrame({
        "team": ["LAL"] * 50,
        "start_frame": range(0, 50 * 450, 450),
        "end_frame": range(300, 50 * 450 + 300, 450),
        "duration_sec": [10.0] * 50,
    })
    shots = pd.DataFrame({
        "timestamp": list(range(10, 310, 10)),
        "player_id": ["p1"] * 30,
    })
    _write_tracking(game_dir, tracking)
    _write_possessions(game_dir, poss)
    _write_shots(game_dir, shots)


def test_validator_passes_good_game(game_dir):
    _make_good_game(game_dir)
    v = QualityValidator(str(game_dir))
    result = v.validate()
    assert result["tracking_rows"]["passed"]
    assert result["sentinel_pct"]["passed"]
    assert result["player_name_pct"]["passed"]
    assert result["team_abbrev_pct"]["passed"]
    assert result["homography_pct"]["passed"]
    assert result["possession_count"]["passed"]
    assert result["shot_count"]["passed"]


def test_validator_grade_a(game_dir):
    _make_good_game(game_dir)
    assert QualityValidator(str(game_dir)).grade() == "A"


def test_validator_fails_too_few_rows(game_dir):
    df = pd.DataFrame({"nearest_opponent": [5.0] * 100})
    _write_tracking(game_dir, df)
    result = QualityValidator(str(game_dir)).validate()
    assert not result["tracking_rows"]["passed"]


def test_validator_fails_sentinel_pct(game_dir):
    """If > 5% of values are sentinels, validator should flag it."""
    df = pd.DataFrame({
        "nearest_opponent": [200.0] * 1000 + [5.0] * 5000,
        "player_name": ["p"] * 6000,
        "team_abbrev": ["NYK"] * 6000,
        "homography_valid": [1] * 6000,
    })
    _write_tracking(game_dir, df)
    result = QualityValidator(str(game_dir)).validate()
    assert not result["sentinel_pct"]["passed"]
