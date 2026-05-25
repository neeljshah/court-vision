"""test_blk_q50_v4_retrain.py — cycle 101b ship-script smoke tests.

6 tests cover the new helpers + the end-to-end shape of the metrics output.
Mirrors the cycle-100b BLK v3 retrain tests — small synthetic inputs, no
production data dependencies.

Coverage:
  1. Candidate sets — numeric (4 opp + q1_blk_l5) + position one-hots are
     wired exactly and BLK params match cycle-29.
  2. main() saves the retrained artifact when both gates pass (mocked).
  3. No-op regression against the persisted cycle-29 LGB-q50 BLK model —
     pins the v1 baseline at 85 features so a silent swap is caught.
  4. _augment_row produces finite values + plausible BLK-range outputs.
  5. WF sign matches single-split sign — main() ships only when both
     directions agree; mocked WF-fail path triggers REJECT.
  6. _select_features applies the 30% coverage gate correctly per-feature
     AND treats position one-hots as a group.
"""
from __future__ import annotations

import json
import os
import sys
from unittest import mock

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.retrain_blk_q50_v4 import (  # noqa: E402
    ALL_CANDIDATES, BASELINE_MAE, COVERAGE_FLOOR_PCT,
    NUMERIC_CANDIDATES, POSITION_BUCKETS,
    _augment_row, _blk_params, _coverage_report, _position_one_hot,
    _select_features,
)


def test_candidate_set_and_blk_params():
    """The v4 candidate set must contain EVERY cycle-99e opp feature AND
    q1_blk_l5 (unlocked by the tier1-3 daemon refresh) AND the three
    position one-hots. Guards against accidental drift.
    """
    assert set(NUMERIC_CANDIDATES) == {
        "opp_team_pace_l5",
        "opp_team_def_rtg_l5",
        "opp_team_oreb_pct_l5",
        "opp_def_blk_l5",
        "q1_blk_l5",
    }
    assert set(POSITION_BUCKETS) == {"position_C", "position_F", "position_G"}
    assert set(ALL_CANDIDATES) == set(NUMERIC_CANDIDATES) | set(POSITION_BUCKETS)
    # Anchors that lock the ship gate.
    assert BASELINE_MAE == 0.4398
    assert COVERAGE_FLOOR_PCT == 30.0
    # _blk_params must match prop_quantiles overrides — guards against
    # accidental HP tuning under cover of a feature-set cycle.
    p = _blk_params()
    assert p["max_depth"] == 3
    assert p["learning_rate"] == 0.06
    assert p["min_child_weight"] == 25
    assert p["reg_lambda"] == 4.0
    assert p["gamma"] == 0.4
    assert p["colsample_bytree"] == 1.0
    assert p["n_estimators"] == 800


def test_retrained_model_saved_on_ship(tmp_path):
    """When BOTH ship gates PASS, main() writes blk_q50_v4.pkl + metrics."""
    import scripts.retrain_blk_q50_v4 as mod

    # Synthetic rows — only need the candidate-feature keys + date for the
    # coverage report. main() will fail open on 0% coverage; we mock the
    # downstream eval functions instead of trying to train a real model.
    synth_rows = []
    for i in range(120):
        r = {"date": f"2024-{(i % 12) + 1:02d}-01", "target_blk": 0.5,
             "position": "Center"}
        for k in NUMERIC_CANDIDATES:
            r[k] = 1.0
        synth_rows.append(r)

    fake_model = {"_synthetic_blk_q50_v4": True}
    fake_ss = {
        "n_rows": 120, "n_train": 80, "n_val": 20, "n_holdout": 20,
        "mae_baseline_85": 0.45, "mae_wide": 0.43,
        "delta_mae": -0.02, "mae_vs_cycle27": -0.0098,
        "wide_model": fake_model, "wide_pred_sample": [0.5] * 25,
    }
    fake_wf = {
        "folds": [
            {"fold": 1, "mae_base": 0.46, "mae_wide": 0.44, "delta_mae": -0.02},
            {"fold": 2, "mae_base": 0.45, "mae_wide": 0.43, "delta_mae": -0.02},
            {"fold": 3, "mae_base": 0.44, "mae_wide": 0.42, "delta_mae": -0.02},
            {"fold": 4, "mae_base": 0.45, "mae_wide": 0.43, "delta_mae": -0.02},
        ],
        "n_folds": 4, "n_folds_negative": 4, "wf_4_of_4_negative": True,
        "delta_mae_mean": -0.02, "delta_mae_std": 0.0,
    }

    tmp_model_dir = tmp_path / "models"
    tmp_model_dir.mkdir()

    with mock.patch.object(mod, "MODEL_DIR", str(tmp_model_dir)), \
         mock.patch.object(mod, "build_pergame_dataset",
                           return_value=(synth_rows, [])), \
         mock.patch.object(mod, "single_split_eval", return_value=fake_ss), \
         mock.patch.object(mod, "walk_forward_eval", return_value=fake_wf):
        ret = mod.main()

    assert ret == 0
    artifact = tmp_model_dir / "blk_q50_v4.pkl"
    metrics = tmp_model_dir / "blk_q50_v4_metrics.json"
    assert artifact.exists(), "ship=True path should write blk_q50_v4.pkl"
    assert metrics.exists()
    meta = json.loads(metrics.read_text())
    assert meta["ship"] is True
    assert meta["single_split"]["mae_wide"] == 0.43
    assert meta["walk_forward"]["wf_4_of_4_negative"] is True


def test_v1_no_op_regression_against_persisted_lgb_blk():
    """Predicting random feature rows against the persisted cycle-29 LGB-q50
    BLK model produces plausible blocks-per-game values. Pins the v1 model
    as the same 85-col baseline the script reads. If a future cycle
    accidentally replaces the v1 artifact with a wider model the
    n_features_in_ assertion below catches it.

    Skipped when the v1 artifact is absent (fresh checkout / sparse CI).
    """
    import joblib

    v1_path = os.path.join(PROJECT_DIR, "data", "models",
                           "quantile_pergame_lgb_blk_q50.pkl")
    if not os.path.exists(v1_path):
        import pytest
        pytest.skip(f"v1 artifact not present: {v1_path}")
    model = joblib.load(v1_path)
    assert getattr(model, "n_features_in_", None) == 85
    rng = np.random.default_rng(42)
    X = rng.uniform(low=0.0, high=1.0, size=(50, 85)).astype(float)
    yt = model.predict(X)
    y = np.clip(np.expm1(yt), 0.0, None)
    assert (y >= 0.0).all()
    assert y.max() < 10.0, f"v1 prediction outlier: {y.max():.2f}"
    assert 0.0 <= float(y.mean()) <= 3.0


def test_augment_row_finite_and_position_one_hot():
    """_augment_row never emits NaN/inf for the new opp/q1 features and
    correctly bucketises compound position strings."""
    rows = [
        {"opp_team_pace_l5": 100.5, "opp_team_def_rtg_l5": 112.3,
         "opp_team_oreb_pct_l5": 0.27, "opp_def_blk_l5": 5.0,
         "q1_blk_l5": 0.7, "position": "Center"},
        # all numerics missing, position hybrid
        {"position": "Forward-Center"},
        # NaN + None for numerics, position absent
        {"opp_team_pace_l5": None, "opp_team_def_rtg_l5": float("nan"),
         "opp_team_oreb_pct_l5": 0.28, "opp_def_blk_l5": 4.5,
         "q1_blk_l5": None, "position": None},
        # plain guard
        {"q1_blk_l5": 0.0, "position": "Guard"},
    ]
    aug = [_augment_row(r) for r in rows]
    for row in aug:
        for k in NUMERIC_CANDIDATES:
            assert k in row
            v = row[k]
            assert isinstance(v, float)
            assert v == v, f"{k} is NaN after augment"
            assert v != float("inf")
        for k in POSITION_BUCKETS:
            assert k in row
            assert row[k] in (0.0, 1.0)

    # Hybrid Forward-Center lights both buckets.
    assert aug[1]["position_C"] == 1.0
    assert aug[1]["position_F"] == 1.0
    assert aug[1]["position_G"] == 0.0
    # Pure Center -> only C.
    assert aug[0]["position_C"] == 1.0 and aug[0]["position_F"] == 0.0
    # Missing position -> all zeros.
    assert (aug[2]["position_C"], aug[2]["position_F"], aug[2]["position_G"]) == (
        0.0, 0.0, 0.0)
    # Guard -> only G.
    assert aug[3]["position_G"] == 1.0 and aug[3]["position_C"] == 0.0

    # _position_one_hot also handles edge cases standalone.
    assert _position_one_hot("") == {k: 0.0 for k in POSITION_BUCKETS}
    assert _position_one_hot(None) == {k: 0.0 for k in POSITION_BUCKETS}


def test_wf_sign_matches_single_split_sign(tmp_path):
    """Sign agreement check: when single-split improves AND WF 4/4
    negative -> ship True; when single-split improves but WF only 1/4
    negative (cycle 99a's exact failure mode) -> ship False.
    """
    import scripts.retrain_blk_q50_v4 as mod

    synth_rows = []
    for i in range(120):
        r = {"date": f"2024-{(i % 12) + 1:02d}-01", "target_blk": 0.5,
             "position": "Center"}
        for k in NUMERIC_CANDIDATES:
            r[k] = 1.0
        synth_rows.append(r)

    fake_ss_ok = {
        "n_rows": 120, "n_train": 80, "n_val": 20, "n_holdout": 20,
        "mae_baseline_85": 0.45, "mae_wide": 0.42,
        "delta_mae": -0.03, "mae_vs_cycle27": -0.0198,
        "wide_model": {"_synthetic_blk_q50_v4": True},
        "wide_pred_sample": [0.5] * 25,
    }

    # CASE A: signs agree -> ship True.
    fake_wf_ok = {
        "folds": [{"fold": i, "mae_base": 0.45,
                   "mae_wide": 0.42, "delta_mae": -0.03} for i in range(1, 5)],
        "n_folds": 4, "n_folds_negative": 4, "wf_4_of_4_negative": True,
        "delta_mae_mean": -0.03, "delta_mae_std": 0.0,
    }
    tmp_a = tmp_path / "shipA"
    tmp_a.mkdir()
    with mock.patch.object(mod, "MODEL_DIR", str(tmp_a)), \
         mock.patch.object(mod, "build_pergame_dataset",
                           return_value=(synth_rows, [])), \
         mock.patch.object(mod, "single_split_eval", return_value=fake_ss_ok), \
         mock.patch.object(mod, "walk_forward_eval", return_value=fake_wf_ok):
        mod.main()
    meta = json.loads((tmp_a / "blk_q50_v4_metrics.json").read_text())
    assert meta["ship"] is True
    assert meta["single_split"]["mae_wide"] < BASELINE_MAE
    assert meta["walk_forward"]["delta_mae_mean"] < 0.0

    # CASE B: 99a's failure mode — ss improved, WF only 1/4 -> ship False.
    fake_wf_bad = {
        "folds": [{"fold": 1, "mae_base": 0.45, "mae_wide": 0.42, "delta_mae": -0.03},
                  {"fold": 2, "mae_base": 0.44, "mae_wide": 0.46, "delta_mae": 0.02},
                  {"fold": 3, "mae_base": 0.45, "mae_wide": 0.47, "delta_mae": 0.02},
                  {"fold": 4, "mae_base": 0.46, "mae_wide": 0.48, "delta_mae": 0.02}],
        "n_folds": 4, "n_folds_negative": 1, "wf_4_of_4_negative": False,
        "delta_mae_mean": 0.0075, "delta_mae_std": 0.02,
    }
    tmp_b = tmp_path / "shipB"
    tmp_b.mkdir()
    with mock.patch.object(mod, "MODEL_DIR", str(tmp_b)), \
         mock.patch.object(mod, "build_pergame_dataset",
                           return_value=(synth_rows, [])), \
         mock.patch.object(mod, "single_split_eval", return_value=fake_ss_ok), \
         mock.patch.object(mod, "walk_forward_eval", return_value=fake_wf_bad):
        mod.main()
    meta = json.loads((tmp_b / "blk_q50_v4_metrics.json").read_text())
    assert meta["ship"] is False
    assert meta["reason"] == "wf_failed"


def test_coverage_gate_drops_below_floor_features():
    """_select_features drops numerics below 30% AND treats position one-hots
    as a group (all three keep / all three drop together). Mirrors cycle
    99a's q1_blk_l5 0% drop AND cycle 100b's all-pass scenario."""
    # All above floor.
    cov_all = {
        "n_rows": 100,
        "opp_team_pace_l5_pct": 100.0,
        "opp_team_def_rtg_l5_pct": 100.0,
        "opp_team_oreb_pct_l5_pct": 100.0,
        "opp_def_blk_l5_pct": 100.0,
        "q1_blk_l5_pct": 85.0,
        "position_C_pct": 100.0,
        "position_F_pct": 100.0,
        "position_G_pct": 100.0,
    }
    sel, dropped = _select_features(cov_all)
    assert set(sel) == set(ALL_CANDIDATES)
    assert dropped == []

    # 99a's exact case: q1_blk_l5 at 0% must be dropped; positions stay.
    cov_q1_dropped = dict(cov_all)
    cov_q1_dropped["q1_blk_l5_pct"] = 0.0
    sel, dropped = _select_features(cov_q1_dropped)
    assert "q1_blk_l5" not in sel
    assert ("q1_blk_l5", 0.0) in dropped
    for k in POSITION_BUCKETS:
        assert k in sel

    # Position group drop: all three buckets fall together.
    cov_no_pos = dict(cov_all)
    for k in POSITION_BUCKETS:
        cov_no_pos[f"{k}_pct"] = 5.0
    sel, dropped = _select_features(cov_no_pos)
    for k in POSITION_BUCKETS:
        assert k not in sel
        assert (k, 5.0) in dropped
    # All numerics still selected.
    for k in NUMERIC_CANDIDATES:
        assert k in sel

    # _coverage_report counts non-None source fields, NOT post-augment defaults.
    raw_rows = [
        {"opp_team_pace_l5": 100.0, "q1_blk_l5": 0.5, "position": "Center"},
        {"opp_team_pace_l5": None, "q1_blk_l5": None, "position": None},
        {"opp_team_pace_l5": 99.0, "q1_blk_l5": 0.7, "position": "Guard"},
        {},  # everything missing
    ]
    cov = _coverage_report(raw_rows)
    assert cov["n_rows"] == 4
    assert cov["opp_team_pace_l5_pct"] == 50.0  # 2/4
    assert cov["q1_blk_l5_pct"] == 50.0          # 2/4
    # Position bucket coverage is the SHARE of rows with a non-empty
    # position string (2/4 here), shared across all three buckets.
    for k in POSITION_BUCKETS:
        assert cov[f"{k}_pct"] == 50.0
