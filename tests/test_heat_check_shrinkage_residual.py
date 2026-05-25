"""Tests for src.prediction.heat_check_shrinkage_residual (cycle 103b, loop 5)."""
from __future__ import annotations

import os
import sys

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.prediction.heat_check_shrinkage_residual import (  # noqa: E402
    FACTOR_CEIL,
    FACTOR_FLOOR,
    FEATURE_NAMES,
    HEAT_CHECK_STATS,
    HeatCheckShrinkageResidualModel,
    apply_shrinkage_to_projection,
    build_feature_row,
    heat_check_shrinkage_factor,
    in_heat_check_stratum,
)


def _make_row(q12_ppm, ratio, *, pos="Guard"):
    m1 = m2 = m3 = 8.0
    q12p = q12_ppm * (m1 + m2)
    q3p = (q12_ppm * ratio) * m3
    return build_feature_row(
        q1_pts=q12p / 2, q2_pts=q12p / 2, q3_pts=q3p,
        min_q1=m1, min_q2=m2, min_q3=m3,
        season_pts_per_min=q12_ppm, l5_pts_per_min=q12_ppm,
        position_proxy=pos, score_margin_abs=0.0,
    )


# ── 1. trains on synthetic Q3-spike-reverts data → outputs shrinkage < 1.0 ──

def test_trains_on_reversion_outputs_shrinkage_below_one():
    """Q4 PPM reverts strongly to q12_ppm baseline; learned ratio
    (q4_ppm / q3_ppm) should be substantially below 1.0 on hot fixtures."""
    rng = np.random.default_rng(0)
    n = 500
    q12 = rng.uniform(0.5, 1.0, n)
    ratio = rng.uniform(1.6, 3.0, n)
    # Strong reversion: y_q4_ppm ~ q12 baseline + noise.
    q4_ppm = (q12 + rng.normal(0, 0.05, n)).clip(0.05, 3.0)
    q3_ppm = q12 * ratio
    y = (q4_ppm / q3_ppm).tolist()
    X = [_make_row(q12[i], ratio[i]) for i in range(n)]

    model = HeatCheckShrinkageResidualModel()
    model.fit(X, y, num_boost_round=200, learning_rate=0.05,
              num_leaves=15, min_data_in_leaf=10)

    # Hot fixture: q12=0.7, ratio=2.5 → expected shrinkage well below 1.
    pred = model.predict_one(_make_row(0.7, 2.5))
    assert pred < 0.95, f"expected shrinkage < 0.95, got {pred:.3f}"
    # And clamped above floor.
    assert pred >= FACTOR_FLOOR


# ── 2. stable-scorer (low ratio target=1.0) → factor ≈ 1.0 ─────────────

def test_stable_scorer_outputs_factor_near_one():
    """When training labels are all ≈ 1.0 (no reversion), model should
    output ≈ 1.0 (no shrinkage) on any input."""
    rng = np.random.default_rng(1)
    n = 300
    q12 = rng.uniform(0.5, 1.0, n)
    ratio = rng.uniform(1.6, 3.0, n)
    # No reversion: q4_ppm == q3_ppm → ratio target = 1.0
    y = (1.0 + rng.normal(0, 0.01, n)).clip(FACTOR_FLOOR, FACTOR_CEIL).tolist()
    X = [_make_row(q12[i], ratio[i]) for i in range(n)]
    model = HeatCheckShrinkageResidualModel()
    model.fit(X, y, num_boost_round=150, min_data_in_leaf=10)
    pred = model.predict_one(_make_row(0.8, 2.0))
    assert pred >= 0.95, f"expected factor ≈ 1.0, got {pred:.3f}"


# ── 3. output is clamped to [0.70, 1.00] on all test inputs ────────────

def test_output_always_clamped_to_band():
    rng = np.random.default_rng(2)
    n = 200
    # Train with extreme (out-of-band) raw labels; .fit() clips internally.
    y = rng.uniform(-0.5, 2.0, n).tolist()
    X = [_make_row(rng.uniform(0.4, 1.0), rng.uniform(1.6, 3.0))
         for _ in range(n)]
    model = HeatCheckShrinkageResidualModel()
    model.fit(X, y, num_boost_round=80, min_data_in_leaf=10)
    preds = model.predict(X)
    assert (preds >= FACTOR_FLOOR - 1e-9).all()
    assert (preds <= FACTOR_CEIL + 1e-9).all()

    # Even fallback (no booster) is clamped.
    empty = HeatCheckShrinkageResidualModel(fallback_mean=99.0)
    assert empty.fallback_mean == FACTOR_CEIL
    empty2 = HeatCheckShrinkageResidualModel(fallback_mean=-5.0)
    assert empty2.fallback_mean == FACTOR_FLOOR


# ── 4. gate function classifies heat_check vs not ─────────────────────

def test_gate_function():
    assert in_heat_check_stratum(1.0, 0.5) is True
    assert in_heat_check_stratum(0.6, 0.4) is False   # exactly 1.5x
    assert in_heat_check_stratum(0.61, 0.40) is True
    assert in_heat_check_stratum(2.0, 0.25) is False  # below q12 floor
    assert in_heat_check_stratum(0.0, 0.5) is False   # no Q3 heat
    assert in_heat_check_stratum(None, None) is False
    # Sanity: stat set matches scoring stats only.
    assert HEAT_CHECK_STATS == frozenset({"pts", "ast", "fg3m"})


# ── 5. apply_shrinkage_to_projection blends correctly ─────────────────

def test_apply_shrinkage_blends_correctly():
    """Only the REMAINING portion is shrunk; current_stat is preserved."""
    # cycle-88 projected 32 PTS, currently has 26. Remaining = 6.
    # Shrinkage 0.80 → remaining becomes 4.8 → final 30.8.
    out = apply_shrinkage_to_projection(
        cycle88_projection=32.0, current_stat=26.0, shrinkage_factor=0.80)
    assert abs(out - 30.8) < 1e-6

    # Factor 1.0 → no change (cycle-88 unchanged).
    out_noop = apply_shrinkage_to_projection(32.0, 26.0, 1.0)
    assert abs(out_noop - 32.0) < 1e-6

    # Factor clamped defensively.
    out_floor = apply_shrinkage_to_projection(32.0, 26.0, 0.5)
    # Effective factor = 0.70 → remaining 6*0.7 = 4.2 → 30.2.
    assert abs(out_floor - 30.2) < 1e-6


# ── 6. back-compat: missing artifact → factor = 1.0 (no override) ─────

def test_missing_artifact_returns_one():
    factor = heat_check_shrinkage_factor(
        residual_model=None,
        q1_pts=6.0, q2_pts=6.0, q3_pts=14.0,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
    )
    assert factor == 1.0

    # Gate doesn't fire either → still 1.0 even with a real model.
    rng = np.random.default_rng(3)
    n = 200
    X = [_make_row(rng.uniform(0.5, 1.0), rng.uniform(1.6, 3.0)) for _ in range(n)]
    y = rng.uniform(FACTOR_FLOOR, FACTOR_CEIL, n).tolist()
    model = HeatCheckShrinkageResidualModel()
    model.fit(X, y, num_boost_round=50, min_data_in_leaf=10)
    no_gate = heat_check_shrinkage_factor(
        residual_model=model,
        q1_pts=6.0, q2_pts=6.0, q3_pts=4.0,   # Q3 cold → no heat-check
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
    )
    assert no_gate == 1.0


def test_feature_row_schema():
    row = build_feature_row(
        q1_pts=6.0, q2_pts=6.0, q3_pts=14.0,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        position_proxy="Guard", score_margin_abs=7.5,
    )
    assert len(row) == len(FEATURE_NAMES) == 15
    assert row[FEATURE_NAMES.index("score_margin_abs")] == 7.5
