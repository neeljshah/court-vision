"""Tests for src.prediction.heat_check_residual (cycle 102b, loop 5)."""
from __future__ import annotations

import os
import sys

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.prediction.heat_check_residual import (  # noqa: E402
    FEATURE_NAMES,
    HeatCheckResidualModel,
    build_feature_row,
    in_heat_check_stratum,
    stratified_heat_check_projection,
)


# ── 1. residual trains on synthetic "Q3-spike-reverses-in-Q4" data ───────────

def test_residual_trains_on_synthetic_reversion():
    """Build a synthetic corpus where high q3_ppm samples have target Q4 PPM
    REVERTING back toward q12_ppm baseline. Model must learn that the higher
    the q3/q12 ratio, the LOWER the Q4 PPM relative to q3_ppm.

    The training is judged by beating mean-prediction MAE by >= 30 %.
    """
    rng = np.random.default_rng(0)
    n = 500
    q12_ppm_arr = rng.uniform(0.4, 1.0, size=n)              # baseline
    ratio_arr = rng.uniform(1.6, 3.0, size=n)                # heat-check
    q3_ppm_arr = q12_ppm_arr * ratio_arr

    # Q4 PPM = q12 baseline + small residual (full reversion + noise).
    y_arr = q12_ppm_arr + rng.normal(0, 0.10, size=n)
    y_arr = np.clip(y_arr, 0.0, 3.0).tolist()

    # Build feature rows matching the schema. min fields are non-zero so the
    # PPMs match exactly (q1_pts + q2_pts = q12_ppm * (min_q1+min_q2)).
    X = []
    for q12, ratio in zip(q12_ppm_arr, ratio_arr):
        m1 = m2 = 8.0
        m3 = 8.0
        q12p = q12 * (m1 + m2)
        q3p = (q12 * ratio) * m3
        X.append(build_feature_row(
            q1_pts=q12p / 2, q2_pts=q12p / 2, q3_pts=q3p,
            min_q1=m1, min_q2=m2, min_q3=m3,
            season_pts_per_min=q12,
            l5_pts_per_min=q12,
            position_proxy="Guard",
        ))

    model = HeatCheckResidualModel()
    model.fit(X, y_arr, num_boost_round=200,
              learning_rate=0.05, num_leaves=15, min_data_in_leaf=10)
    preds = model.predict(X)
    learned_mae = float(np.mean(np.abs(preds - np.asarray(y_arr))))
    mean_baseline_mae = float(np.mean(np.abs(
        np.asarray(y_arr) - float(np.mean(y_arr)))))
    assert learned_mae < 0.7 * mean_baseline_mae, (
        f"learned MAE {learned_mae:.3f} did not beat mean-pred "
        f"{mean_baseline_mae:.3f}")


# ── 2. hot-Q3 fixture predicts LOWER PPM than naive extrapolation ────────────

def test_hot_q3_fixture_predicts_lower_than_naive():
    """Train model where Q4 PPM = q12_ppm baseline (full reversion). On a
    hot-Q3 fixture (ratio = 2.5), the learned Q4 PPM must be substantially
    LOWER than the naive extrapolation (which would be q3_ppm itself, i.e.
    2.5 * q12_ppm).
    """
    rng = np.random.default_rng(1)
    n = 400
    q12_arr = rng.uniform(0.5, 1.0, size=n)
    ratio_arr = rng.uniform(1.6, 3.0, size=n)
    # Strong reversion -> y ~ q12_ppm baseline.
    y = (q12_arr + rng.normal(0, 0.05, size=n)).clip(0.0, 3.0).tolist()
    X = []
    for q12, ratio in zip(q12_arr, ratio_arr):
        m1 = m2 = m3 = 8.0
        q12p = q12 * (m1 + m2)
        q3p = (q12 * ratio) * m3
        X.append(build_feature_row(
            q1_pts=q12p / 2, q2_pts=q12p / 2, q3_pts=q3p,
            min_q1=m1, min_q2=m2, min_q3=m3,
            season_pts_per_min=q12, l5_pts_per_min=q12,
            position_proxy="Forward",
        ))
    model = HeatCheckResidualModel()
    model.fit(X, y, num_boost_round=250,
              learning_rate=0.05, num_leaves=15, min_data_in_leaf=10)

    # Hot-Q3 probe: q12_ppm=0.7, q3_ppm = 0.7 * 2.5 = 1.75.
    hot_row = build_feature_row(
        q1_pts=5.6, q2_pts=5.6, q3_pts=14.0,   # 11.2/16 = 0.7 q12 ppm; 14/8 = 1.75 q3 ppm
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        season_pts_per_min=0.7, l5_pts_per_min=0.7,
        position_proxy="Forward",
    )
    pred_q4_ppm = model.predict_one(hot_row)
    naive_extrapolation = 1.75  # would be q3_ppm
    assert pred_q4_ppm < naive_extrapolation - 0.5, (
        f"expected learned PPM ({pred_q4_ppm:.3f}) to be MUCH lower than naive "
        f"extrapolation ({naive_extrapolation:.3f})")


# ── 3. gate function classifies heat_check vs non-heat ───────────────────────

def test_gate_classifies_heat_check_correctly():
    # Above threshold: q3_ppm = 1.0, q12_ppm = 0.5 -> ratio 2.0 -> True
    assert in_heat_check_stratum(q3_ppm=1.0, q12_ppm=0.5) is True
    # Just above 1.5x: ratio 1.51 with q12 > 0.3 -> True
    assert in_heat_check_stratum(q3_ppm=0.61, q12_ppm=0.40) is True
    # Exactly 1.5x -> NOT > 1.5 -> False
    assert in_heat_check_stratum(q3_ppm=0.6, q12_ppm=0.4) is False
    # Cold Q1+Q2 (q12_ppm <= 0.3): always False even with huge q3_ppm.
    assert in_heat_check_stratum(q3_ppm=2.0, q12_ppm=0.25) is False
    assert in_heat_check_stratum(q3_ppm=2.0, q12_ppm=0.30) is False
    # Zero Q3 -> False (no heat to check).
    assert in_heat_check_stratum(q3_ppm=0.0, q12_ppm=0.5) is False
    # Non-numeric -> safe False.
    assert in_heat_check_stratum(q3_ppm=None, q12_ppm=None) is False


# ── 4. stratified dispatch returns override for in-gate, None for out ────────

def test_stratified_dispatch_overrides_only_in_gate():
    """``stratified_heat_check_projection`` must return:
      * a learned float when gate fires AND residual is loaded
      * None when gate doesn't fire (caller keeps its projection)
    """
    # Build a trivial constant-output residual.
    rng = np.random.default_rng(2)
    y = (0.5 + rng.normal(0, 0.02, size=200)).tolist()
    X = [build_feature_row(
        q1_pts=6.0, q2_pts=6.0, q3_pts=14.0,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        season_pts_per_min=0.75, l5_pts_per_min=0.75,
        position_proxy="Guard",
    ) for _ in range(200)]
    model = HeatCheckResidualModel()
    model.fit(X, y, num_boost_round=80, min_data_in_leaf=10)

    # Gate fires (q3_ppm 1.75, q12_ppm 0.75 -> ratio 2.33).
    override = stratified_heat_check_projection(
        residual_model=model,
        current_pts=26.0, q1_pts=6.0, q2_pts=6.0, q3_pts=14.0,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        remaining_min=12.0,
        season_pts_per_min=0.75, l5_pts_per_min=0.75,
        position_proxy="Guard",
        fallback_projection=999.0,
    )
    # current_pts (26) + ~0.5 ppm * 12 min ~ 32.
    assert override is not None
    assert 30.0 <= override <= 34.0, f"unexpected override {override}"

    # Gate does NOT fire (q3_ppm 0.5, q12_ppm 0.75 -> ratio 0.67).
    no_override = stratified_heat_check_projection(
        residual_model=model,
        current_pts=26.0, q1_pts=6.0, q2_pts=6.0, q3_pts=4.0,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        remaining_min=12.0,
        season_pts_per_min=0.75, l5_pts_per_min=0.75,
        position_proxy="Guard",
        fallback_projection=999.0,
    )
    assert no_override is None


# ── 5. back-compat: missing artifact -> falls back to heuristic ──────────────

def test_missing_artifact_returns_fallback_for_in_gate():
    """When residual_model=None AND gate fires, return the caller's
    fallback projection (preserves existing heuristic behavior).
    """
    fallback = 32.5
    out = stratified_heat_check_projection(
        residual_model=None,
        current_pts=26.0, q1_pts=6.0, q2_pts=6.0, q3_pts=14.0,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        remaining_min=12.0,
        fallback_projection=fallback,
    )
    assert out == fallback

    # Gate doesn't fire: still None even with residual missing.
    out2 = stratified_heat_check_projection(
        residual_model=None,
        current_pts=26.0, q1_pts=6.0, q2_pts=6.0, q3_pts=4.0,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        remaining_min=12.0,
        fallback_projection=fallback,
    )
    assert out2 is None


def test_feature_row_schema_length():
    """Sanity: builder emits exactly len(FEATURE_NAMES) floats."""
    row = build_feature_row(
        q1_pts=6.0, q2_pts=6.0, q3_pts=14.0,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        position_proxy="Guard",
    )
    assert len(row) == len(FEATURE_NAMES) == 14
    assert row[FEATURE_NAMES.index("q1_pts")] == 6.0
    assert row[FEATURE_NAMES.index("q3_ppm")] == 14.0 / 8.0
    assert row[FEATURE_NAMES.index("q12_ppm")] == 12.0 / 16.0
    # Ratio = q3_ppm / max(q12_ppm, 0.01) = 1.75 / 0.75
    assert abs(row[FEATURE_NAMES.index("q3_q12_ratio")] - (1.75 / 0.75)) < 1e-6
