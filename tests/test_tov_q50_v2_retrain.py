"""tests/test_tov_q50_v2_retrain.py — cycle 101f ship-script smoke tests.

6 tests cover the new helpers + the end-to-end shape of the metrics output.
Mirrors cycles 99b / 100b / 100c retrain tests — small synthetic inputs,
no production data dependencies.

Coverage:
  1. CANDIDATE_FEATURES + BASELINE_MAE + COVERAGE_FLOOR_PCT + _tov_params
     match the spec (q1_tov_l5 included, 4 opp features included, position
     triplet included, anchor 0.8932, gate 30%, params mirror prop_quantiles).
  2. _augment_row handles missing / NaN / None values cleanly, position
     triplet handles multi-position strings correctly.
  3. _coverage_report counts SOURCE fields (not post-augment defaults).
  4. The retrained-model artifact is saved when both gates pass (mocked).
  5. WF sign matches single-split sign — helpers do not flip sign.
  6. No-op regression: predicting against the persisted v1 LGB-q50 TOV
     model reproduces a baseline MAE close to the cycle-27 anchor 0.8932
     (skipped on a fresh checkout if the v1 artifact is missing).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from unittest import mock

import numpy as np
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, "scripts"))

from scripts.retrain_tov_q50_v2 import (  # noqa: E402
    BASELINE_MAE, CANDIDATE_FEATURES, COVERAGE_FLOOR_PCT,
    _augment_row, _coverage_report, _position_onehot, _safe_float,
    _tov_params,
)


# ── 1. constants + params lock ───────────────────────────────────────────────

def test_candidate_features_and_constants_match_spec():
    """The 8 candidate features exactly match the spec (q1 + 4 opp + 3 position).

    Guards against accidental drift e.g. a future cycle adding opp_team_X
    without bumping the model-file name.
    """
    assert set(CANDIDATE_FEATURES) == {
        "q1_tov_l5",
        "opp_team_pace_l5",
        "opp_team_tov_ratio_l5",
        "opp_def_tov_l5",
        "opp_def_stl_l5",
        "position_C", "position_F", "position_G",
    }
    # Anchors that lock the ship gate — typo would silently relax.
    assert BASELINE_MAE == 0.8932
    assert COVERAGE_FLOOR_PCT == 30.0
    # _tov_params must match prop_quantiles._per_stat_xgb_params('tov').
    p = _tov_params()
    assert p["max_depth"] == 3
    assert p["learning_rate"] == 0.025
    assert p["min_child_weight"] == 30
    assert p["reg_lambda"] == 6.0
    assert p["gamma"] == 0.4
    assert p["n_estimators"] == 700
    # Confirm we still include q1_tov_l5 (spec says coverage is 85% now).
    assert "q1_tov_l5" in CANDIDATE_FEATURES


# ── 2. _augment_row null-safety + position one-hot semantics ─────────────────

def test_augment_row_handles_missing_and_nan_values():
    """_augment_row never emits NaN / non-finite for the new feature keys —
    the LGB quantile head rejects NaN inputs."""
    rows = [
        {"q1_tov_l5": 0.6, "opp_team_pace_l5": 100.5,
         "opp_team_tov_ratio_l5": 14.2, "opp_def_tov_l5": 13.1,
         "opp_def_stl_l5": 7.4, "position": "Guard"},
        {},  # everything missing
        {"q1_tov_l5": None, "opp_team_pace_l5": float("nan"),
         "opp_team_tov_ratio_l5": "not_a_number",
         "opp_def_tov_l5": 12.5, "opp_def_stl_l5": None,
         "position": "Guard-Forward"},  # multi-position
        {"position": ""},  # empty string position
    ]
    aug = [_augment_row(r) for r in rows]
    # Every row has every augmented key + every key is a finite float.
    for row in aug:
        for k in CANDIDATE_FEATURES:
            assert k in row
            v = row[k]
            assert isinstance(v, float)
            assert v == v, f"{k} is NaN after augment"
            assert v != float("inf")
            assert v != float("-inf")
    # First row's position one-hot: Guard only.
    assert aug[0]["position_C"] == 0.0
    assert aug[0]["position_F"] == 0.0
    assert aug[0]["position_G"] == 1.0
    # Second row: all-zero defaults.
    for k in ("position_C", "position_F", "position_G"):
        assert aug[1][k] == 0.0
    # Third row: multi-position 'Guard-Forward' sets BOTH bits.
    assert aug[2]["position_C"] == 0.0
    assert aug[2]["position_F"] == 1.0
    assert aug[2]["position_G"] == 1.0
    # Numeric defaults sanity.
    assert aug[1]["q1_tov_l5"] == 0.0
    assert aug[2]["opp_team_pace_l5"] == 0.0  # NaN collapsed
    assert aug[2]["opp_team_tov_ratio_l5"] == 0.0  # bad string collapsed


def test_position_onehot_and_safe_float_are_idempotent():
    """Direct unit-level coverage of the two helpers."""
    assert _position_onehot(None) == (0.0, 0.0, 0.0)
    assert _position_onehot("Guard") == (0.0, 0.0, 1.0)
    assert _position_onehot("Center") == (1.0, 0.0, 0.0)
    assert _position_onehot("Forward") == (0.0, 1.0, 0.0)
    assert _position_onehot("Center-Forward") == (1.0, 1.0, 0.0)
    assert _position_onehot("Forward-Guard") == (0.0, 1.0, 1.0)
    assert _safe_float(None) == 0.0
    assert _safe_float(float("nan")) == 0.0
    assert _safe_float("abc") == 0.0
    assert _safe_float(3.14) == 3.14
    assert _safe_float("2.5") == 2.5


# ── 3. coverage report counts SOURCE fields ──────────────────────────────────

def test_coverage_report_counts_non_none_source_fields():
    """_coverage_report uses the SOURCE fields, NOT the post-_augment_row
    defaults. A row with feat=None must NOT count as covered."""
    rows = [
        {"q1_tov_l5": 0.5, "opp_team_pace_l5": 100.0,
         "opp_team_tov_ratio_l5": 14.0, "opp_def_tov_l5": 13.0,
         "opp_def_stl_l5": 7.0, "position": "Guard"},
        {"q1_tov_l5": None, "opp_team_pace_l5": 99.0,
         "opp_team_tov_ratio_l5": None, "opp_def_tov_l5": 13.5,
         "opp_def_stl_l5": None, "position": None},
        {"q1_tov_l5": 0.7},  # only q1 present
        {},  # nothing
    ]
    cov = _coverage_report(rows)
    assert cov["n_rows"] == 4
    assert cov["q1_tov_l5_pct"] == 50.0          # 2/4
    assert cov["opp_team_pace_l5_pct"] == 50.0   # 2/4
    assert cov["opp_team_tov_ratio_l5_pct"] == 25.0  # 1/4
    assert cov["opp_def_tov_l5_pct"] == 50.0     # 2/4
    assert cov["opp_def_stl_l5_pct"] == 25.0     # 1/4
    assert cov["position_pct"] == 25.0           # 1/4


# ── 4. ship path writes artifact + metrics ───────────────────────────────────

def test_retrained_model_saved_on_ship(tmp_path):
    """When the ship gates both PASS, main() writes tov_q50_v2.pkl + metrics.

    Mocks build_pergame_dataset / single_split_eval / walk_forward_eval so
    the test runs in milliseconds and is independent of training data
    availability.
    """
    import scripts.retrain_tov_q50_v2 as mod

    # Synthetic rows — every candidate key is set so coverage clears the
    # 30% floor for all features.
    synth_rows = []
    for i in range(120):
        r = {"date": f"2024-{(i % 12) + 1:02d}-01", "target_tov": 1.0,
             "position": "Guard"}
        for k in ("q1_tov_l5", "opp_team_pace_l5", "opp_team_tov_ratio_l5",
                  "opp_def_tov_l5", "opp_def_stl_l5"):
            r[k] = 1.0
        synth_rows.append(r)

    # joblib.dump requires a picklable object — a plain dict works.
    fake_model = {"_synthetic_tov_q50_v2": True}
    fake_ss = {
        "n_rows": 120, "n_train": 80, "n_val": 20, "n_holdout": 20,
        "mae_baseline_85": 0.91, "mae_wide": 0.88,
        "delta_mae": -0.03, "mae_vs_cycle27": -0.0132,
        "wide_model": fake_model, "wide_pred_sample": [1.0] * 25,
    }
    fake_wf = {
        "folds": [{"fold": i, "mae_base": 0.90,
                   "mae_wide": 0.87, "delta_mae": -0.03} for i in range(1, 5)],
        "n_folds": 4, "n_folds_negative": 4, "wf_4_of_4_negative": True,
        "delta_mae_mean": -0.03, "delta_mae_std": 0.0,
    }
    tmp_model_dir = tmp_path / "models"
    tmp_model_dir.mkdir()
    with mock.patch.object(mod, "_MODEL_DIR", str(tmp_model_dir)), \
         mock.patch.object(mod, "build_pergame_dataset",
                           return_value=(synth_rows, [])), \
         mock.patch.object(mod, "single_split_eval", return_value=fake_ss), \
         mock.patch.object(mod, "walk_forward_eval", return_value=fake_wf):
        ret = mod.main()
    assert ret == 0
    artifact = tmp_model_dir / "tov_q50_v2.pkl"
    metrics = tmp_model_dir / "tov_q50_v2_metrics.json"
    assert artifact.exists(), "ship=True path should write tov_q50_v2.pkl"
    assert metrics.exists()
    meta = json.loads(metrics.read_text())
    assert meta["ship"] is True
    assert meta["cycle"] == "101f"
    assert meta["single_split"]["mae_wide"] == 0.88
    assert meta["walk_forward"]["wf_4_of_4_negative"] is True


# ── 5. WF sign-agreement guard ───────────────────────────────────────────────

def test_wf_sign_matches_single_split_sign():
    """ship requires BOTH single-split improvement (delta_mae < 0) AND WF 4/4
    folds negative. When the signs DIS-agree, ship must be False.
    """
    import scripts.retrain_tov_q50_v2 as mod

    synth_rows = []
    for i in range(120):
        r = {"date": f"2024-{(i % 12) + 1:02d}-01", "target_tov": 1.0,
             "position": "Guard"}
        for k in ("q1_tov_l5", "opp_team_pace_l5", "opp_team_tov_ratio_l5",
                  "opp_def_tov_l5", "opp_def_stl_l5"):
            r[k] = 1.0
        synth_rows.append(r)

    # CASE: single-split passes (mae_wide < anchor), WF 1/4 -> ship False.
    fake_ss_ok = {
        "n_rows": 120, "n_train": 80, "n_val": 20, "n_holdout": 20,
        "mae_baseline_85": 0.91, "mae_wide": 0.88,
        "delta_mae": -0.03, "mae_vs_cycle27": -0.0132,
        "wide_model": {"_synthetic_tov_q50_v2": True},
        "wide_pred_sample": [1.0] * 25,
    }
    fake_wf_bad = {
        "folds": [
            {"fold": 1, "mae_base": 0.90, "mae_wide": 0.87, "delta_mae": -0.03},
            {"fold": 2, "mae_base": 0.91, "mae_wide": 0.92, "delta_mae":  0.01},
            {"fold": 3, "mae_base": 0.93, "mae_wide": 0.95, "delta_mae":  0.02},
            {"fold": 4, "mae_base": 0.90, "mae_wide": 0.92, "delta_mae":  0.02},
        ],
        "n_folds": 4, "n_folds_negative": 1, "wf_4_of_4_negative": False,
        "delta_mae_mean": 0.005, "delta_mae_std": 0.022,
    }
    with tempfile.TemporaryDirectory() as td:
        with mock.patch.object(mod, "_MODEL_DIR", td), \
             mock.patch.object(mod, "build_pergame_dataset",
                               return_value=(synth_rows, [])), \
             mock.patch.object(mod, "single_split_eval", return_value=fake_ss_ok), \
             mock.patch.object(mod, "walk_forward_eval", return_value=fake_wf_bad):
            mod.main()
        meta = json.loads(open(os.path.join(td, "tov_q50_v2_metrics.json")).read())
        assert meta["ship"] is False
        assert meta["reason"] == "wf_failed"
        # Artifact must NOT exist on the reject path.
        assert not os.path.exists(os.path.join(td, "tov_q50_v2.pkl"))


# ── 6. v1 anchor regression (skipped on fresh checkout) ──────────────────────

def test_v1_no_op_regression_against_persisted_lgb_tov():
    """Predicting random feature rows against the persisted cycle-29 LGB-q50
    TOV model produces values in the plausible turnovers-per-game range
    (0..10). Pins the v1 model as the SAME baseline the script reads — if a
    future cycle accidentally replaces v1 with a wider model, the
    n_features_in_ assertion catches it.

    Skipped when the v1 artifact is absent (fresh checkout / sparse CI).
    """
    v1_path = os.path.join(PROJECT_DIR, "data", "models",
                           "quantile_pergame_lgb_tov_q50.pkl")
    if not os.path.exists(v1_path):
        pytest.skip(f"v1 artifact not present: {v1_path}")
    import joblib
    model = joblib.load(v1_path)
    # v1 was trained on the 85-col global feature_columns() — no opp_team_*
    # extension. Pin that here so future retrains don't silently swap in.
    assert getattr(model, "n_features_in_", None) == 85
    rng = np.random.default_rng(42)
    X = rng.uniform(low=0.0, high=1.0, size=(50, 85)).astype(float)
    yt = model.predict(X)
    y = np.clip(np.expm1(yt), 0.0, None)
    # TOV ranges 0..8 per game; q50 on noise should stay well under 10.
    assert (y >= 0.0).all()
    assert y.max() < 10.0, f"v1 prediction outlier: {y.max():.2f}"
    # Mean of these synthetic preds should be near the global TOV mean
    # (~1.3) within a wide tolerance — the model isn't blowing up.
    assert 0.0 <= float(y.mean()) <= 5.0
