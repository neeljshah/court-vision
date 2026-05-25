"""Tests for src.prediction.blowout_residual (cycle 102a, loop 5)."""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.prediction.blowout_residual import (  # noqa: E402
    FEATURE_NAMES,
    BlowoutResidualModel,
    build_feature_row,
    in_blowout_flip_stratum,
    in_blowout_flip_live_proxy,
    stratified_blowout_factor,
)


# ── 1. residual trains on synthetic data with strong margin signal ──────────

def test_residual_trains_with_strong_margin_signal():
    """Synthetic target = 12 - 0.8 * abs(signed_margin) + noise.

    Wide-margin (leading team starters in blowout) -> fewer remaining minutes.
    Model must learn the negative slope well below the mean-pred baseline.
    """
    rng = np.random.default_rng(0)
    n = 400
    signed_margins = rng.integers(-10, 11, size=n)  # signed swing
    velocities = rng.integers(2, 12, size=n).astype(float)
    noise = rng.normal(0, 0.8, size=n)
    # Stronger signal on |margin| for leading-team starters.
    y = (12.0 - 0.8 * np.abs(signed_margins).astype(float) + noise).clip(0.0, 24.0).tolist()
    X = [build_feature_row(
        pf_through_q3=2, q3_pf=1,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        score_margin_abs=abs(int(sm)),
        score_margin_signed_q3=float(sm),
        score_velocity_q3=float(v),
        is_leading_team=1 if sm > 0 else 0,
        position_proxy="Guard", l20_min=28.0, l5_min=26.0,
    ) for sm, v in zip(signed_margins, velocities)]

    model = BlowoutResidualModel()
    model.fit(X, y, num_boost_round=150,
              learning_rate=0.05, num_leaves=10, min_data_in_leaf=10)
    preds = model.predict(X)
    learned_mae = float(np.mean(np.abs(preds - np.asarray(y))))
    mean_baseline_mae = float(np.mean(np.abs(np.asarray(y) - np.mean(y))))
    assert learned_mae < 0.75 * mean_baseline_mae, (
        f"learned MAE {learned_mae:.3f} did not beat mean-pred "
        f"{mean_baseline_mae:.3f}")


# ── 2. blowout fixture: leading-team starter projects LOWER remaining min ────

def test_leading_starter_blowout_predicts_fewer_minutes():
    """Train a clear negative relationship between |margin| and minutes for
    leading-team starters. Predict on a fixture with high abs margin vs low
    abs margin: high should yield FEWER remaining minutes.
    """
    rng = np.random.default_rng(1)
    n = 500
    margins = rng.integers(-15, 16, size=n)
    velocities = rng.normal(6, 3, size=n)
    # Pronounced negative slope on leading-team rows for the signed margin.
    y = (14.0 - 0.7 * np.abs(margins).astype(float) + rng.normal(0, 0.5, size=n))
    y = y.clip(0.0, 24.0).tolist()
    X = [build_feature_row(
        pf_through_q3=2, q3_pf=1,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        score_margin_abs=abs(int(m)),
        score_margin_signed_q3=float(m),
        score_velocity_q3=float(v),
        is_leading_team=1 if m > 0 else 0,
        position_proxy="Forward", l20_min=30.0, l5_min=28.0,
    ) for m, v in zip(margins, velocities)]
    model = BlowoutResidualModel()
    model.fit(X, y, num_boost_round=200,
              learning_rate=0.05, num_leaves=10, min_data_in_leaf=10)

    wide_lead = build_feature_row(
        pf_through_q3=2, q3_pf=1,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        score_margin_abs=15,
        score_margin_signed_q3=15.0,
        score_velocity_q3=8.0,
        is_leading_team=1,
        position_proxy="Forward", l20_min=30.0, l5_min=28.0,
    )
    close = build_feature_row(
        pf_through_q3=2, q3_pf=1,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        score_margin_abs=2,
        score_margin_signed_q3=2.0,
        score_velocity_q3=0.0,
        is_leading_team=1,
        position_proxy="Forward", l20_min=30.0, l5_min=28.0,
    )
    pred_wide = model.predict_one(wide_lead)
    pred_close = model.predict_one(close)
    assert pred_wide < pred_close, (
        f"expected wide-margin ({pred_wide:.2f}) < close ({pred_close:.2f})")


# ── 3. gate functions correctly classify blowout_flip vs not ────────────────

def test_gates_classify_correctly():
    """Ground-truth + live-proxy gate truth-tables."""
    # Ground-truth gate: requires both q3_margin and final_margin.
    # Narrow clause: |Q3| <= 18 AND |final| >= 20.
    assert in_blowout_flip_stratum(q3_margin_abs=15, final_margin_abs=22) is True
    assert in_blowout_flip_stratum(q3_margin_abs=18, final_margin_abs=20) is True
    # Tight clause: |Q3| <= 12 AND |final| >= 18.
    assert in_blowout_flip_stratum(q3_margin_abs=10, final_margin_abs=18) is True
    assert in_blowout_flip_stratum(q3_margin_abs=12, final_margin_abs=19) is True
    # Below both: |Q3|=20 too wide.
    assert in_blowout_flip_stratum(q3_margin_abs=20, final_margin_abs=25) is False
    # Final too small.
    assert in_blowout_flip_stratum(q3_margin_abs=10, final_margin_abs=15) is False
    # Within Q3 ceil but final under both thresholds.
    assert in_blowout_flip_stratum(q3_margin_abs=15, final_margin_abs=17) is False

    # Live proxy gate: requires |Q3 margin| <= 18 AND |velocity| >= 4.
    assert in_blowout_flip_live_proxy(q3_margin_abs=10, score_velocity_q3=6) is True
    assert in_blowout_flip_live_proxy(q3_margin_abs=18, score_velocity_q3=-5) is True
    # Too wide -- already a blowout, not a flip.
    assert in_blowout_flip_live_proxy(q3_margin_abs=20, score_velocity_q3=8) is False
    # Velocity too low -- no Q4 momentum.
    assert in_blowout_flip_live_proxy(q3_margin_abs=5, score_velocity_q3=2) is False
    # Zero velocity in close game -- gate doesn't fire.
    assert in_blowout_flip_live_proxy(q3_margin_abs=2, score_velocity_q3=0) is False


# ── 4. stratified blend dispatches correctly per row ────────────────────────

def test_stratified_blend_dispatches_correctly():
    """When live-proxy gate fires AND residual is loaded -> residual prediction.
    When gate doesn't fire OR residual is None -> heuristic passes through.
    """
    rng = np.random.default_rng(2)
    # Residual: trained to predict ~3.0 minutes (very pulled-out blowout).
    y_res = (3.0 + rng.normal(0, 0.05, size=200)).tolist()
    X_res = [build_feature_row(
        pf_through_q3=2, q3_pf=1,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        score_margin_abs=12,
        score_margin_signed_q3=12.0,
        score_velocity_q3=8.0,
        is_leading_team=1,
        position_proxy="Center",
    ) for _ in range(200)]
    res_model = BlowoutResidualModel()
    res_model.fit(X_res, y_res, num_boost_round=80, min_data_in_leaf=10)

    HEURISTIC = 0.55  # cycle-88f Q4 margin 20-29 starter factor

    # Gate fires (|Q3|=12, vel=8) -> residual (~3/12 = 0.25 ratio).
    fired = stratified_blowout_factor(
        heuristic_factor=HEURISTIC,
        residual_model=res_model,
        pf_through_q3=2, q3_pf=1,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        score_margin_abs=12,
        score_margin_signed_q3=12.0,
        score_velocity_q3=8.0,
        is_leading_team=1,
        position_proxy="Center",
    )
    assert 0.15 <= fired <= 0.40, f"fired ratio={fired:.3f} unexpected"

    # Gate does NOT fire (velocity=0) -> heuristic.
    no_fire = stratified_blowout_factor(
        heuristic_factor=HEURISTIC,
        residual_model=res_model,
        pf_through_q3=2, q3_pf=1,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        score_margin_abs=5,
        score_margin_signed_q3=5.0,
        score_velocity_q3=0.0,
        is_leading_team=1,
        position_proxy="Center",
    )
    assert no_fire == pytest.approx(HEURISTIC, abs=1e-6), (
        f"expected heuristic={HEURISTIC}, got {no_fire:.4f}")

    # Gate fires BUT |Q3|=22 -> too wide -> gate False -> heuristic.
    too_wide = stratified_blowout_factor(
        heuristic_factor=HEURISTIC,
        residual_model=res_model,
        pf_through_q3=2, q3_pf=1,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        score_margin_abs=22,
        score_margin_signed_q3=22.0,
        score_velocity_q3=8.0,
        is_leading_team=1,
        position_proxy="Center",
    )
    assert too_wide == pytest.approx(HEURISTIC, abs=1e-6)


# ── 5. back-compat: missing residual artifact -> defaults to heuristic ──────

def test_residual_missing_falls_back_to_heuristic():
    """``stratified_blowout_factor(residual_model=None)`` must transparently
    return the heuristic factor regardless of whether the gate fires.
    """
    HEURISTIC = 0.25  # cycle-88f Q4 margin 30+ starter factor

    # Gate WOULD fire but residual is None -> heuristic.
    out = stratified_blowout_factor(
        heuristic_factor=HEURISTIC,
        residual_model=None,
        pf_through_q3=2, q3_pf=1,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        score_margin_abs=10,
        score_margin_signed_q3=10.0,
        score_velocity_q3=8.0,
        is_leading_team=1,
        position_proxy="Center",
    )
    assert out == pytest.approx(HEURISTIC, abs=1e-6), (
        f"fallback mismatch: got {out:.4f}, expected {HEURISTIC}")

    # Gate doesn't fire AND residual None -> heuristic.
    out_calm = stratified_blowout_factor(
        heuristic_factor=HEURISTIC,
        residual_model=None,
        pf_through_q3=1, q3_pf=0,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        score_margin_abs=5,
        score_margin_signed_q3=5.0,
        score_velocity_q3=0.0,
    )
    assert out_calm == pytest.approx(HEURISTIC, abs=1e-6)


def test_feature_row_schema_length():
    """Sanity: builder emits exactly len(FEATURE_NAMES)=18 floats; extras OK."""
    row = build_feature_row(
        pf_through_q3=2, q3_pf=1,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        score_margin_abs=10,
        score_margin_signed_q3=10.0,
        score_velocity_q3=6.0,
        is_leading_team=1,
    )
    assert len(row) == len(FEATURE_NAMES) == 18
    assert row[FEATURE_NAMES.index("score_margin_signed_q3")] == 10.0
    assert row[FEATURE_NAMES.index("score_velocity_q3")] == 6.0
    assert row[FEATURE_NAMES.index("abs_q3_margin")] == 10.0
    # |q3|=10 -> margin_class=1 (mid bucket 9-15).
    assert row[FEATURE_NAMES.index("margin_class")] == 1.0
