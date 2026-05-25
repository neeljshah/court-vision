"""test_period_specific_heads.py -- cycle 105b (loop 5).

5 tests covering the period-specific projection heads module:
  1. artifact_paths covers all 21 (stat, point) combinations
  2. save+load round-trips correctly
  3. snapshot_point_for dispatches by (period, clock)
  4. predict_remaining returns None when artifact missing (back-compat)
  5. synthetic linear data fits near-1.0 slope
"""
from __future__ import annotations

import os
import sys
import tempfile

import numpy as np
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.prediction import period_specific_heads as psh  # noqa: E402


def test_artifact_paths_covers_all_21_combinations(tmp_path):
    """All 7 stats x 3 snapshot points -> 21 distinct artifact paths."""
    paths = set()
    for stat in psh.STATS:
        for point in psh.SNAPSHOT_POINTS:
            m, meta = psh.artifact_paths(stat, point, models_dir=str(tmp_path))
            assert m.endswith(f"{stat}_{point}.lgb")
            assert meta.endswith(f"{stat}_{point}.meta.json")
            paths.add(m)
            paths.add(meta)
    assert len(paths) == 21 * 2


def test_save_load_roundtrip(tmp_path):
    """Train a tiny head, save, reload, verify predictions match."""
    rng = np.random.default_rng(0)
    X = rng.uniform(0, 10, size=(300, len(psh.FEATURE_NAMES))).tolist()
    y = [row[0] * 0.5 + rng.normal(0, 0.1) for row in X]
    head = psh.PeriodHead(stat="pts", point="endQ2")
    head.fit(X, y, num_boost_round=50, learning_rate=0.1,
             num_leaves=15, min_data_in_leaf=10, seed=42)

    model_path, meta_path = psh.artifact_paths("pts", "endQ2",
                                                models_dir=str(tmp_path))
    head.save(model_path=model_path, meta_path=meta_path)
    assert os.path.exists(model_path)
    assert os.path.exists(meta_path)

    # Clear cache so load() actually reads from disk.
    psh.reset_cache()
    loaded = psh.PeriodHead.load("pts", "endQ2", models_dir=str(tmp_path))
    assert loaded is not None
    p1 = head.predict(X[:5])
    p2 = loaded.predict(X[:5])
    np.testing.assert_allclose(p1, p2, rtol=1e-6)


def test_snapshot_point_for_dispatch():
    """(period, clock) -> snapshot point mapping."""
    assert psh.snapshot_point_for(2, "12:00") == "endQ1"
    assert psh.snapshot_point_for(3, "12:00") == "endQ2"
    assert psh.snapshot_point_for(4, "12:00") == "endQ3"
    # Numeric remaining-min also supported.
    assert psh.snapshot_point_for(3, 12.0) == "endQ2"
    # Mid-period -> None (not at boundary).
    assert psh.snapshot_point_for(3, "08:00") is None
    # Period 1 or 5+ -> None (no snapshot defined).
    assert psh.snapshot_point_for(1, "12:00") is None
    assert psh.snapshot_point_for(5, "12:00") is None


def test_predict_remaining_back_compat_missing_artifact(tmp_path):
    """predict_remaining returns None when artifact absent -> caller falls back."""
    psh.reset_cache()
    # tmp_path is empty -> no artifacts.
    result = psh.predict_remaining(
        "pts", "endQ2",
        current_stat=12.0, min_through=18.0,
        models_dir=str(tmp_path),
    )
    assert result is None


def test_synthetic_linear_data_learns_near_one_slope(tmp_path):
    """If y = current_stat (linear with slope 1.0), the head should learn it."""
    rng = np.random.default_rng(7)
    n = 1000
    X = []
    y = []
    for _ in range(n):
        cur = float(rng.uniform(0, 20))
        # Build a feature row where current_stat is the dominant signal.
        row = psh.build_feature_row(
            current_stat=cur, min_through=12.0,
            pf_through=0.0, score_margin_abs=0.0, is_leading_team=0,
            l5_stat=cur, l20_stat=cur, l20_min=12.0, position_proxy="G",
        )
        X.append(row)
        y.append(cur + rng.normal(0, 0.05))

    head = psh.PeriodHead(stat="pts", point="endQ3")
    head.fit(X, y, num_boost_round=200, learning_rate=0.1,
             num_leaves=31, min_data_in_leaf=20, seed=42)
    preds = head.predict(X[:200])
    actuals = np.asarray(y[:200])
    # Slope check via linear regression of preds on actuals.
    slope = float(np.polyfit(actuals, preds, 1)[0])
    assert 0.85 < slope < 1.15, f"slope {slope} not near 1.0"
