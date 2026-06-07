"""tests/test_pts_minmodel.py — Unit tests for the PTS two-stage minutes model.

Tests:
  1. is_enabled() returns False when CV_PREGAME_PTS_MINMODEL is not set.
  2. predict_pts_minmodel returns a finite, non-negative float.
  3. Divide-by-zero is guarded (zero minutes in row dict).
  4. Prediction is clamped to [0, 70].
  5. Artifact is serialisable (basic dict check).
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_row(
    *,
    target_min: float = 28.0,
    target_pts: float = 18.0,
    date: str = "2025-01-15",
    **overrides,
) -> dict:
    """Return a minimal row dict compatible with pts_minutes_model features."""
    base = {
        "date":       date,
        "game_id":    "0022500001",
        "player_id":  2544,
        "season":     "2024-25",
        # minutes features
        "l5_min":     28.0,
        "l10_min":    27.5,
        "std_min":    27.0,
        "ewma_min":   28.2,
        "prev_min":   30.0,
        "rest_days":  1.0,
        "is_b2b":     0.0,
        "is_b3b":     0.0,
        "days_since_last_game": 1.0,
        "games_since_long_absence": 0.0,
        "games_played": 40.0,
        "is_home":    1.0,
        # bbref rate features
        "bbref_usg_pct":   0.28,
        "bbref_ts_pct":    0.58,
        "bbref_three_par": 0.35,
        "bbref_ftr":       0.30,
        # ratio features
        "pts_share_3pt":   0.25,
        "opp_def_pts":     1.0,
        # form features used in per-minute ratios
        "l5_pts":    18.5,
        "l10_pts":   17.8,
        "ewma_pts":  18.1,
        "prev_pts":  21.0,
        # targets
        "target_min": target_min,
        "target_pts": target_pts,
    }
    base.update(overrides)
    return base


def _make_training_rows(n: int = 200) -> list:
    """Make n synthetic training rows with deterministic variability."""
    rng = np.random.default_rng(seed=0)
    rows = []
    for i in range(n):
        minutes = float(rng.uniform(5, 40))
        pts     = float(rng.uniform(0, 50))
        rows.append(_make_row(
            target_min=minutes,
            target_pts=pts,
            date=f"2025-{1 + i // 30:02d}-{1 + i % 28:02d}",
            l5_min=float(rng.uniform(10, 35)),
            ewma_min=float(rng.uniform(10, 35)),
            l5_pts=float(rng.uniform(5, 35)),
            ewma_pts=float(rng.uniform(5, 35)),
        ))
    return rows


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_is_enabled_off_by_default(monkeypatch):
    """is_enabled() must return False when the env var is absent."""
    monkeypatch.delenv("CV_PREGAME_PTS_MINMODEL", raising=False)
    from src.prediction.pts_minutes_model import is_enabled
    assert is_enabled() is False


def test_is_enabled_on_when_set(monkeypatch):
    """is_enabled() returns True when CV_PREGAME_PTS_MINMODEL='1'."""
    monkeypatch.setenv("CV_PREGAME_PTS_MINMODEL", "1")
    # Reload to pick up env change (the function reads os.environ at call time)
    from src.prediction.pts_minutes_model import is_enabled
    assert is_enabled() is True


def test_predict_returns_finite_nonnegative():
    """predict_pts_minmodel must return a finite, non-negative float."""
    from src.prediction.pts_minutes_model import train_pts_minmodel, predict_pts_minmodel
    rows = _make_training_rows(200)
    artifact = train_pts_minmodel(rows)
    row = _make_row()
    result = predict_pts_minmodel(artifact, row)
    assert isinstance(result, float)
    assert np.isfinite(result)
    assert result >= 0.0


def test_divide_by_zero_guarded():
    """Zero minutes in row dict must NOT cause a ZeroDivisionError or NaN."""
    from src.prediction.pts_minutes_model import train_pts_minmodel, predict_pts_minmodel
    rows = _make_training_rows(200)
    artifact = train_pts_minmodel(rows)
    row = _make_row(l5_min=0.0, l10_min=0.0, ewma_min=0.0, prev_min=0.0,
                    target_min=0.0, target_pts=0.0)
    result = predict_pts_minmodel(artifact, row)
    assert np.isfinite(result)
    assert result >= 0.0


def test_prediction_clamped_to_range():
    """Predictions must always lie within [0, 70]."""
    from src.prediction.pts_minutes_model import train_pts_minmodel, predict_pts_minmodel
    rows = _make_training_rows(200)
    artifact = train_pts_minmodel(rows)
    # Extreme inputs that might produce out-of-range predictions
    for l5_min, l5_pts in [(0.1, 100.0), (100.0, 0.0), (50.0, 50.0)]:
        row = _make_row(l5_min=l5_min, l5_pts=l5_pts,
                        ewma_min=l5_min, ewma_pts=l5_pts)
        result = predict_pts_minmodel(artifact, row)
        assert 0.0 <= result <= 70.0, f"Out of range: {result} (l5_min={l5_min}, l5_pts={l5_pts})"


def test_artifact_has_expected_keys():
    """Train artifact must contain min_head, rate_head keys."""
    from src.prediction.pts_minutes_model import train_pts_minmodel
    rows = _make_training_rows(200)
    artifact = train_pts_minmodel(rows)
    assert "min_head"  in artifact
    assert "rate_head" in artifact
    assert "isotonic"  in artifact


def test_predictions_span_realistic_range():
    """Predictions across varied rows must NOT be a constant (degeneracy guard)."""
    from src.prediction.pts_minutes_model import train_pts_minmodel, predict_pts_minmodel
    rows = _make_training_rows(200)
    artifact = train_pts_minmodel(rows)

    # Generate 20 rows with varied minutes and points form
    rng = np.random.default_rng(seed=7)
    preds = []
    for _ in range(20):
        l5m = float(rng.uniform(3.0, 38.0))
        l5p = float(rng.uniform(1.0, 40.0))
        row = _make_row(l5_min=l5m, ewma_min=l5m * 0.9,
                        l5_pts=l5p, ewma_pts=l5p * 0.9,
                        target_min=l5m, target_pts=l5p)
        preds.append(predict_pts_minmodel(artifact, row))

    pred_std = float(np.std(preds))
    pred_span = float(np.max(preds) - np.min(preds))
    assert pred_std > 0.5, f"Predictions collapsed to near-constant (std={pred_std:.3f})"
    assert pred_span > 2.0, f"Predictions span too narrow (span={pred_span:.3f})"
