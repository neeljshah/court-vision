"""Tests for src.prediction.minute_trajectory_foul_residual (tier1-2, loop 5)."""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.prediction.minute_trajectory_foul_residual import (  # noqa: E402
    FEATURE_NAMES,
    FoulChangeResidualModel,
    build_feature_row,
    in_foul_change_stratum,
    stratified_minute_factor,
)


# ── 1. residual trains on synthetic with strong pf signal ─────────────────────

def test_residual_trains_with_strong_pf_signal():
    """Synthetic target = 12 - 2 * pf_through_q3 + noise. Model must learn the
    negative slope (heavy fouls -> few remaining minutes) substantially
    better than predicting the mean.
    """
    rng = np.random.default_rng(0)
    n = 400
    pf_vals = rng.integers(3, 6, size=n)  # all in foul_change band (>=3)
    q3_vals = rng.integers(0, 3, size=n)
    noise = rng.normal(0, 1.0, size=n)
    y = (12.0 - 2.0 * pf_vals.astype(float) + noise).clip(0.0, 24.0).tolist()
    X = [build_feature_row(
        pf_through_q3=int(pf), q3_pf=int(q),
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        position_proxy="Guard", l20_min=28.0, l5_min=26.0, q2_pf=1,
    ) for pf, q in zip(pf_vals, q3_vals)]

    model = FoulChangeResidualModel()
    model.fit(X, y, num_boost_round=150,
              learning_rate=0.05, num_leaves=10, min_data_in_leaf=10)
    preds = model.predict(X)
    learned_mae = float(np.mean(np.abs(preds - np.asarray(y))))
    mean_baseline_mae = float(np.mean(np.abs(np.asarray(y) - np.mean(y))))
    assert learned_mae < 0.7 * mean_baseline_mae, (
        f"learned MAE {learned_mae:.3f} did not beat mean-pred "
        f"{mean_baseline_mae:.3f}")


# ── 2. foul-trouble fixture predicts FEWER minutes than no-foul ───────────────

def test_foul_trouble_predicts_fewer_minutes():
    """With a model trained on a clear negative pf->minutes relationship,
    a pf=5 fixture row must yield a LOWER prediction than a pf=3 row
    (within-stratum, both rows pass the gate).
    """
    rng = np.random.default_rng(1)
    n = 500
    pf_vals = rng.integers(3, 6, size=n)
    y = (14.0 - 2.5 * pf_vals.astype(float) + rng.normal(0, 0.5, size=n))
    y = y.clip(0.0, 24.0).tolist()
    X = [build_feature_row(
        pf_through_q3=int(pf), q3_pf=2,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        position_proxy="Forward", l20_min=30.0, l5_min=28.0, q2_pf=1,
    ) for pf in pf_vals]
    model = FoulChangeResidualModel()
    model.fit(X, y, num_boost_round=200,
              learning_rate=0.05, num_leaves=10, min_data_in_leaf=10)

    high_foul = build_feature_row(
        pf_through_q3=5, q3_pf=2,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        position_proxy="Forward", l20_min=30.0, l5_min=28.0, q2_pf=1,
    )
    low_foul = build_feature_row(
        pf_through_q3=3, q3_pf=2,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        position_proxy="Forward", l20_min=30.0, l5_min=28.0, q2_pf=1,
    )
    pred_high = model.predict_one(high_foul)
    pred_low = model.predict_one(low_foul)
    assert pred_high < pred_low, (
        f"expected pf=5 ({pred_high:.2f}) < pf=3 ({pred_low:.2f})")


# ── 3. gate function classifies correctly ─────────────────────────────────────

def test_gate_classifies_correctly():
    """Truth-table check of in_foul_change_stratum across the boundary."""
    # Q3 foul-burst clause: q3_pf >= 2 fires regardless of total.
    assert in_foul_change_stratum(q3_pf=2, pf_through_q3=2) is True
    assert in_foul_change_stratum(q3_pf=4, pf_through_q3=4) is True

    # Total-pf clause: pf_through_q3 >= 3 fires even if q3_pf was quiet.
    assert in_foul_change_stratum(q3_pf=1, pf_through_q3=3) is True
    assert in_foul_change_stratum(q3_pf=0, pf_through_q3=5) is True

    # Foul-out edge clause: q3_pf=0, total=4.
    assert in_foul_change_stratum(q3_pf=0, pf_through_q3=4) is True

    # Below all thresholds -> False.
    assert in_foul_change_stratum(q3_pf=1, pf_through_q3=1) is False
    assert in_foul_change_stratum(q3_pf=1, pf_through_q3=2) is False
    assert in_foul_change_stratum(q3_pf=0, pf_through_q3=0) is False
    # Edge: q3_pf=0, total=2 (below the 4-edge AND below total=3) -> False.
    assert in_foul_change_stratum(q3_pf=0, pf_through_q3=2) is False


# ── 4. stratified blend dispatches correctly ──────────────────────────────────

def test_stratified_blend_dispatches_correctly():
    """When the gate fires, the residual model is consulted; when not, the
    global model is consulted. Verified by training two models with
    DELIBERATELY DIFFERENT constant outputs and observing which one drives
    the result.
    """
    # Residual: predicts ~3.0 min on every row (target=3).
    rng = np.random.default_rng(2)
    y_res = (3.0 + rng.normal(0, 0.05, size=200)).tolist()
    X_res = [build_feature_row(
        pf_through_q3=4, q3_pf=2,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        position_proxy="Center", q2_pf=1,
    ) for _ in range(200)]
    res_model = FoulChangeResidualModel()
    res_model.fit(X_res, y_res, num_boost_round=80, min_data_in_leaf=10)

    # Global: import + train a constant ~9.0 model.
    from src.prediction.minute_trajectory import (
        MinuteTrajectoryModel,
        build_feature_row as global_build,
    )
    y_glob = (9.0 + rng.normal(0, 0.05, size=200)).tolist()
    X_glob = [global_build(
        pf_through_q3=1, q3_pf=0,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        position_proxy="Guard",
    ) for _ in range(200)]
    glob_model = MinuteTrajectoryModel()
    glob_model.fit(X_glob, y_glob, num_boost_round=80, min_data_in_leaf=10)

    # Gate fires -> residual (~3/12 = 0.25 ratio).
    fired = stratified_minute_factor(
        global_model=glob_model, residual_model=res_model,
        pf_through_q3=4, q3_pf=2,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        position_proxy="Center", q2_pf=1,
    )
    # Gate does NOT fire -> global (~9/12 = 0.75 ratio).
    no_fire = stratified_minute_factor(
        global_model=glob_model, residual_model=res_model,
        pf_through_q3=1, q3_pf=0,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        position_proxy="Guard", q2_pf=0,
    )
    # Residual output is meaningfully smaller than global.
    assert fired < no_fire - 0.2, (
        f"expected residual<<global, got fired={fired:.3f} no_fire={no_fire:.3f}")
    # Sanity: the gate-fired path returned ~3/12 = 0.25.
    assert 0.15 <= fired <= 0.40, f"fired ratio={fired:.3f} unexpected"


# ── 5. no-gate fallback: residual missing -> defaults to global ───────────────

def test_residual_missing_falls_back_to_global():
    """``stratified_minute_factor(residual_model=None)`` must transparently
    delegate to the global model (this is the back-compat path before the
    residual artifact has been trained).
    """
    from src.prediction.minute_trajectory import (
        MinuteTrajectoryModel,
        build_feature_row as global_build,
        learned_minute_factor,
    )
    rng = np.random.default_rng(3)
    y = (6.0 + rng.normal(0, 0.1, size=300)).tolist()
    X = [global_build(
        pf_through_q3=4, q3_pf=2,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        position_proxy="Center",
    ) for _ in range(300)]
    glob = MinuteTrajectoryModel()
    glob.fit(X, y, num_boost_round=50, min_data_in_leaf=10)

    # Gate WOULD fire (pf>=3) but residual_model=None -> falls back to global.
    out = stratified_minute_factor(
        global_model=glob, residual_model=None,
        pf_through_q3=4, q3_pf=2,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        position_proxy="Center",
    )
    expected = learned_minute_factor(
        glob,
        pf_through_q3=4, q3_pf=2,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        position_proxy="Center",
    )
    assert out == pytest.approx(expected, abs=1e-6), (
        f"fallback mismatch: got {out:.4f}, expected {expected:.4f}")

    # Also: BOTH models None -> 1.0 (no adjustment).
    out_none = stratified_minute_factor(
        global_model=None, residual_model=None,
        pf_through_q3=4, q3_pf=2,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
    )
    assert out_none == 1.0


def test_feature_row_schema_length():
    """Sanity: builder emits exactly len(FEATURE_NAMES) floats."""
    row = build_feature_row(
        pf_through_q3=3, q3_pf=2,
        min_q1=8.0, min_q2=8.0, min_q3=8.0, q2_pf=1,
    )
    assert len(row) == len(FEATURE_NAMES) == 18
    # last 4 fields are foul-extras.
    assert row[FEATURE_NAMES.index("q2_pf")] == 1.0
    assert row[FEATURE_NAMES.index("total_pf_through_q3")] == 3.0
    # pf_per_min_q3 = q3_pf/min_q3 = 2/8 = 0.25
    assert row[FEATURE_NAMES.index("pf_per_min_q3")] == pytest.approx(0.25)
    assert row[FEATURE_NAMES.index("q3_pf_extra")] == 2.0
