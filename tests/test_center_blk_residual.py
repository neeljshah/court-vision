"""tests/test_center_blk_residual.py -- cycle 106d (loop 5).

Six regression tests for center_blk_residual:
    1. model trains on synthetic data with strong opp signal
    2. output is clamped to [FACTOR_FLOOR, FACTOR_CEIL]
    3. gate (position in CENTER_POSITIONS AND stat=='blk') classifies correctly
    4. apply at factor=1.0 is a no-op (preserves input)
    5. back-compat: missing artifact -> factor = 1.0
    6. non-Center rows unaffected (gate returns 1.0)
"""
from __future__ import annotations

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import numpy as np

from src.prediction.center_blk_residual import (
    CENTER_POSITIONS,
    FACTOR_CEIL,
    FACTOR_FLOOR,
    CenterBlkResidualModel,
    apply_center_blk_shrinkage,
    build_feature_row,
    center_blk_shrinkage_factor,
    in_center_blk_stratum,
    is_center_position,
)


def _synth_rows(n=400, seed=0):
    rng = np.random.default_rng(seed)
    X = []
    y = []
    for _ in range(n):
        opp_def = float(rng.uniform(0.7, 1.3))
        l5b = float(rng.uniform(0.2, 2.5))
        l10b = l5b + float(rng.uniform(-0.3, 0.3))
        l5m = float(rng.uniform(18.0, 34.0))
        l10m = l5m + float(rng.uniform(-3.0, 3.0))
        pace = float(rng.uniform(95.0, 105.0))
        oreb = float(rng.uniform(0.20, 0.32))
        margin = float(rng.uniform(0.0, 12.0))
        # Strong opp-def signal: ratio scales with opp_def
        ratio = 0.95 + 0.4 * (opp_def - 1.0) + float(rng.normal(0, 0.05))
        row = build_feature_row(
            l5_blk=l5b, l10_blk=l10b, l5_min=l5m, l10_min=l10m,
            opp_def_blk=opp_def, opp_team_pace_l5=pace,
            opp_team_oreb_pct_l5=oreb, home_spread=-margin,
        )
        X.append(row)
        y.append(ratio)
    return X, y


def test_trains_on_synthetic_opp_signal():
    X, y = _synth_rows(n=400, seed=1)
    model = CenterBlkResidualModel()
    model.fit(X, y, num_boost_round=80, learning_rate=0.05,
              num_leaves=15, min_data_in_leaf=10, seed=42)
    pred = model.predict(X)
    y_clipped = np.clip(np.asarray(y), FACTOR_FLOOR, FACTOR_CEIL)
    mae = float(np.mean(np.abs(pred - y_clipped)))
    baseline = float(np.mean(np.abs(y_clipped - np.mean(y_clipped))))
    # Model must beat the constant-mean baseline by a clear margin
    assert mae < baseline * 0.9, f"mae={mae:.4f} baseline={baseline:.4f}"


def test_output_clamped_to_band():
    X, y = _synth_rows(n=200, seed=2)
    # Push some targets way outside the band; the model should still clamp on predict.
    y = [3.0 if i % 2 == 0 else 0.1 for i in range(len(y))]
    model = CenterBlkResidualModel()
    model.fit(X, y, num_boost_round=40, seed=42)
    pred = model.predict(X)
    assert pred.min() >= FACTOR_FLOOR - 1e-9
    assert pred.max() <= FACTOR_CEIL + 1e-9


def test_gate_classifies_correctly():
    assert is_center_position("Center")
    assert is_center_position("Center-Forward")
    assert is_center_position("Forward-Center")
    assert not is_center_position("Guard")
    assert not is_center_position("Forward")
    assert not is_center_position(None)
    assert in_center_blk_stratum("blk", "Center")
    assert not in_center_blk_stratum("blk", "Guard")
    assert not in_center_blk_stratum("pts", "Center")
    assert not in_center_blk_stratum("blk", None)


def test_factor_1_is_noop():
    pred = 0.752
    out = apply_center_blk_shrinkage(pred, 1.0)
    assert abs(out - pred) < 1e-12


def test_missing_artifact_returns_unit_factor():
    # residual_model=None must return 1.0 even when stratum gate fires.
    f = center_blk_shrinkage_factor(
        residual_model=None,
        stat="blk",
        position="Center",
        feature_row={"l5_blk": 1.5, "l10_blk": 1.4, "l5_min": 30.0,
                     "l10_min": 31.0, "opp_def_blk": 1.0,
                     "opp_team_pace_l5": 100.0, "opp_team_oreb_pct_l5": 0.25,
                     "home_spread": -3.0},
    )
    assert f == 1.0


def test_non_center_rows_unaffected():
    # Train a real model
    X, y = _synth_rows(n=300, seed=3)
    model = CenterBlkResidualModel().fit(X, y, num_boost_round=50, seed=42)

    feat = {"l5_blk": 1.2, "l10_blk": 1.3, "l5_min": 28.0,
            "l10_min": 29.0, "opp_def_blk": 1.1, "opp_team_pace_l5": 100.0,
            "opp_team_oreb_pct_l5": 0.26, "home_spread": -5.0}

    # Non-Center position: factor must be exactly 1.0
    for pos in ("Guard", "Forward", "Guard-Forward", "Forward-Guard", None, ""):
        f = center_blk_shrinkage_factor(
            residual_model=model, stat="blk", position=pos, feature_row=feat,
        )
        assert f == 1.0, f"factor for pos={pos!r} was {f}"

    # Non-BLK stat: factor must be exactly 1.0 even when position is Center
    for stat in ("pts", "reb", "ast", "fg3m", "stl", "tov"):
        f = center_blk_shrinkage_factor(
            residual_model=model, stat=stat, position="Center", feature_row=feat,
        )
        assert f == 1.0, f"factor for stat={stat} pos=Center was {f}"

    # Center + BLK: factor must be inside band and may differ from 1.0
    f_center = center_blk_shrinkage_factor(
        residual_model=model, stat="blk", position="Center", feature_row=feat,
    )
    assert FACTOR_FLOOR <= f_center <= FACTOR_CEIL
