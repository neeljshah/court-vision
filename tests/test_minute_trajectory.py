"""Tests for src.prediction.minute_trajectory (tier3-10, loop 5)."""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.prediction.minute_trajectory import (  # noqa: E402
    FEATURE_NAMES,
    MinuteTrajectoryModel,
    build_feature_row,
    learned_minute_factor,
)


def test_model_recovers_linear_slope_on_synthetic_data():
    """Train on y = 0.5 * pf + 8 + noise; learned MAE should be small
    relative to a zero-information predictor.
    """
    rng = np.random.default_rng(0)
    n = 600
    pf_vals = rng.integers(0, 6, size=n)
    noise = rng.normal(0, 1.0, size=n)
    y = 0.5 * pf_vals.astype(float) + 8.0 + noise
    X = []
    for pf in pf_vals:
        X.append(build_feature_row(
            pf_through_q3=int(pf), q3_pf=0,
            min_q1=8.0, min_q2=8.0, min_q3=8.0,
            position_proxy="Guard",
        ))
    model = MinuteTrajectoryModel()
    model.fit(X, y.tolist(), num_boost_round=200,
              learning_rate=0.05, num_leaves=15, min_data_in_leaf=20)
    preds = model.predict(X)
    learned_mae = float(np.mean(np.abs(preds - y)))
    mean_baseline_mae = float(np.mean(np.abs(y - y.mean())))
    # Learned model must beat the mean-predictor by at least 30%.
    assert learned_mae < 0.7 * mean_baseline_mae, (
        f"learned MAE {learned_mae:.3f} did not beat mean-pred "
        f"{mean_baseline_mae:.3f}")
    # And on this very simple data, MAE should be near the noise floor of 1.0.
    assert learned_mae < 1.5


def test_predict_returns_positive_minutes():
    """Synthetic-fit model + arbitrary feature row -> positive scalar."""
    rng = np.random.default_rng(1)
    n = 200
    pf = rng.integers(0, 6, size=n)
    y = (10.0 + rng.normal(0, 1.0, size=n)).tolist()
    X = [build_feature_row(pf_through_q3=int(p), q3_pf=0,
                           min_q1=8.0, min_q2=8.0, min_q3=8.0) for p in pf]
    model = MinuteTrajectoryModel()
    model.fit(X, y, num_boost_round=50, min_data_in_leaf=10)
    one_row = build_feature_row(
        pf_through_q3=3, q3_pf=1,
        min_q1=10.0, min_q2=9.0, min_q3=8.5,
        position_proxy="Center",
    )
    pred = model.predict_one(one_row)
    assert pred >= 0.0
    assert pred <= 24.0  # clip bound


def test_missing_features_default_to_global_mean():
    """An untrained wrapper must still produce a valid scalar (the fallback
    global mean), and feature builder must NaN out unknown l5/l20.
    """
    model = MinuteTrajectoryModel(fallback_mean=9.0)  # booster=None
    row = build_feature_row(
        pf_through_q3=None, q3_pf=None,
        min_q1=None, min_q2=None, min_q3=None,
        l20_min=None, l5_min=None,
    )
    # builder fills NaN for l20/l5 (positions 12, 13).
    assert np.isnan(row[FEATURE_NAMES.index("l20_min")])
    assert np.isnan(row[FEATURE_NAMES.index("l5_min")])
    assert model.predict_one(row) == pytest.approx(9.0)


def test_load_returns_none_when_artifact_missing():
    """Back-compat: loader must NOT raise when the artifact file is absent."""
    missing_model = "/tmp/__definitely_does_not_exist_minute_traj__.lgb"
    missing_meta = "/tmp/__definitely_does_not_exist_minute_traj_meta__.json"
    out = MinuteTrajectoryModel.load(missing_model, missing_meta)
    assert out is None


def test_substitution_helper_integrates_with_project_snapshot():
    """``learned_minute_factor`` returns a ratio scaled around 1.0 that
    can be dropped straight into pig.project_final as the foul_factor arg.
    Smoke test: passing model=None must return 1.0 (no-op back-compat).
    """
    # No model -> exactly 1.0 (preserves baseline projection).
    f = learned_minute_factor(
        None,
        pf_through_q3=3, q3_pf=1,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
    )
    assert f == 1.0

    # With a trivial trained model that predicts ~6.0 min on a typical row,
    # the helper returns ~0.5 (= 6 / 12).
    rng = np.random.default_rng(7)
    y = (6.0 + rng.normal(0, 0.1, size=300)).tolist()
    X = [build_feature_row(
        pf_through_q3=2, q3_pf=0,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        position_proxy="Guard",
        l20_min=28.0, l5_min=27.0,
    ) for _ in range(300)]
    model = MinuteTrajectoryModel()
    model.fit(X, y, num_boost_round=50, min_data_in_leaf=10)

    f2 = learned_minute_factor(
        model,
        pf_through_q3=2, q3_pf=0,
        min_q1=8.0, min_q2=8.0, min_q3=8.0,
        position_proxy="Guard",
        l20_min=28.0, l5_min=27.0,
    )
    # Predicted ~6 min / 12 = ~0.5; allow a wide band for the synthetic fit.
    assert 0.3 <= f2 <= 0.8, f"unexpected ratio {f2:.3f}"

    # Now integrate with project_final via the foul_factor slot.
    import scripts.predict_in_game as pig  # noqa: E402
    final = pig.project_final(
        current_stat=18.0,
        period=4,
        clock_remaining_min=12.0,
        foul_factor=f2,
    )
    # current 18, share_played=0.75, share_remaining=0.25, ratio=0.333,
    # remaining_proj = 18 * 0.333 * f2 -> 18 + that.
    assert final > 18.0  # always added something
    assert final < 30.0  # sanity ceiling
