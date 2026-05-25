"""test_reb_q50_v3_retrain.py — cycle 101d ship-script smoke tests.

6 tests for the REB LGB-q50 v3 retrain helpers (4 opp + q1_reb_l5 +
position_C/F/G one-hots):

  1. CANDIDATE_FEATURES set is exactly the 8 expected columns (4 opp + 1
     q1 + 3 position) — guards against drift if a future cycle silently
     adds a feature without bumping the model filename / shape.
  2. BASELINE_MAE + COVERAGE_FLOOR_PCT constants haven't drifted and
     _reb_params matches the cycle-29 LGB-q50 REB recipe.
  3. _augment_row coerces None / NaN / string to finite 0.0 floats AND
     correctly emits position one-hots from "Center" / "Guard-Forward"
     style position strings.
  4. _coverage_report counts only real source values for opp/q1 features
     AND reads the position one-hot coverage from row["position"], not the
     post-_augment_row defaults. A row with position=None has zero coverage
     in every position bucket.
  5. _position_one_hot lights up multiple buckets for hybrid positions
     (Guard-Forward → position_G=1 AND position_F=1) and zero buckets for
     None / empty / unknown strings.
  6. End-to-end mock: when both ship gates PASS, main() writes
     reb_q50_v3.pkl + metrics with ship=True; when WF fails (100d's
     exact failure mode — single-split passes but WF only 2/4 negative),
     main() records ship=False + reason='wf_failed' and skips the
     artifact write.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from unittest import mock

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.retrain_reb_q50_v3 import (  # noqa: E402
    BASELINE_MAE, CANDIDATE_FEATURES, COVERAGE_FLOOR_PCT,
    _augment_row, _coverage_report, _position_one_hot, _reb_params,
)


def test_candidate_features_match_v3_unlock():
    """Exactly the 8 candidates: 4 opp + q1_reb_l5 + 3 position buckets."""
    assert len(CANDIDATE_FEATURES) == 8
    assert set(CANDIDATE_FEATURES) == {
        "opp_team_oreb_pct_l5",
        "opp_team_dreb_pct_l5",
        "opp_team_pace_l5",
        "opp_def_reb_l5",
        "q1_reb_l5",
        "position_C",
        "position_F",
        "position_G",
    }
    # Order is load-bearing for downstream column alignment — guard it.
    assert CANDIDATE_FEATURES[:4] == (
        "opp_team_oreb_pct_l5", "opp_team_dreb_pct_l5",
        "opp_team_pace_l5", "opp_def_reb_l5",
    )
    assert CANDIDATE_FEATURES[4] == "q1_reb_l5"
    assert CANDIDATE_FEATURES[5:] == ("position_C", "position_F", "position_G")


def test_anchor_constants_and_reb_params():
    """Anchor the cycle-29 REB MAE, the 30% coverage floor, and the LGB-q50
    REB hyperparameters in tests so a typo in the ship-gate constant is
    caught before silently shipping."""
    assert BASELINE_MAE == 1.9023
    assert COVERAGE_FLOOR_PCT == 30.0
    p = _reb_params()
    assert p["max_depth"] == 3
    assert p["learning_rate"] == 0.025
    assert p["min_child_weight"] == 30
    assert p["reg_lambda"] == 4.0
    assert p["gamma"] == 0.3
    assert p["subsample"] == 0.7
    assert p["colsample_bytree"] == 0.9
    assert p["n_estimators"] == 800
    assert p["random_state"] == 42


def test_augment_row_collapses_missing_and_nan_and_emits_position_buckets():
    """_augment_row fills every CANDIDATE_FEATURES key with a finite float
    AND maps row['position'] -> the 3 position one-hots."""
    # Pure missing row
    row_missing = {"date": "2025-01-01", "target_reb": 5.0}
    aug = _augment_row(row_missing)
    for k in CANDIDATE_FEATURES:
        assert k in aug, f"missing augmented key {k}"
        v = aug[k]
        assert isinstance(v, float)
        assert v == v, f"{k} is NaN"
        assert v == 0.0, f"{k} should default to 0.0 when source is missing"

    # Real numeric values + Center position propagate
    row_full = {
        "date": "2025-01-01", "target_reb": 8.0,
        "opp_team_oreb_pct_l5": 0.27,
        "opp_team_dreb_pct_l5": 0.74,
        "opp_team_pace_l5": 99.5,
        "opp_def_reb_l5": 45.6,
        "q1_reb_l5": 2.4,
        "position": "Center",
    }
    aug2 = _augment_row(row_full)
    assert aug2["opp_team_oreb_pct_l5"] == 0.27
    assert aug2["opp_team_dreb_pct_l5"] == 0.74
    assert aug2["opp_team_pace_l5"] == 99.5
    assert aug2["opp_def_reb_l5"] == 45.6
    assert aug2["q1_reb_l5"] == 2.4
    assert aug2["position_C"] == 1.0
    assert aug2["position_F"] == 0.0
    assert aug2["position_G"] == 0.0

    # NaN / non-numeric / hybrid position
    row_nan = {"date": "2025-01-01", "target_reb": 3.0,
               "opp_team_oreb_pct_l5": float("nan"),
               "opp_team_dreb_pct_l5": "junk",
               "opp_team_pace_l5": None,
               "opp_def_reb_l5": 42.0,
               "q1_reb_l5": float("inf") * 0,  # NaN via 0 * inf
               "position": "Guard-Forward"}
    aug3 = _augment_row(row_nan)
    assert aug3["opp_team_oreb_pct_l5"] == 0.0
    assert aug3["opp_team_dreb_pct_l5"] == 0.0
    assert aug3["opp_team_pace_l5"] == 0.0
    assert aug3["opp_def_reb_l5"] == 42.0
    assert aug3["q1_reb_l5"] == 0.0
    # Hybrid lights up BOTH G and F (cycle 96e convention)
    assert aug3["position_G"] == 1.0
    assert aug3["position_F"] == 1.0
    assert aug3["position_C"] == 0.0


def test_coverage_report_counts_real_sources_and_position_buckets():
    """opp_*/q1_reb_l5 coverage is computed from the raw source field;
    position-bucket coverage is computed from row['position'] via the
    one-hot mapping (NOT from the augmented bucket value)."""
    rows = [
        {"opp_team_oreb_pct_l5": 0.27, "opp_team_dreb_pct_l5": 0.74,
         "opp_team_pace_l5": 99.5,     "opp_def_reb_l5": 45.0,
         "q1_reb_l5": 2.5, "position": "Center"},
        {"opp_team_oreb_pct_l5": None, "opp_team_dreb_pct_l5": 0.72,
         "opp_team_pace_l5": float("nan"), "opp_def_reb_l5": 44.0,
         "q1_reb_l5": None, "position": "Guard"},
        {"opp_team_oreb_pct_l5": 0.30, "opp_team_dreb_pct_l5": None,
         "opp_team_pace_l5": 101.0,    "opp_def_reb_l5": None,
         "q1_reb_l5": 1.8, "position": "Forward-Center"},
        {"opp_team_oreb_pct_l5": None, "opp_team_dreb_pct_l5": None,
         "opp_team_pace_l5": None,     "opp_def_reb_l5": None,
         "q1_reb_l5": None, "position": None},
    ]
    cov = _coverage_report(rows)
    assert cov["n_rows"] == 4
    assert cov["opp_team_oreb_pct_l5_pct"] == 50.0   # rows 0 + 2
    assert cov["opp_team_dreb_pct_l5_pct"] == 50.0   # rows 0 + 1
    assert cov["opp_team_pace_l5_pct"] == 50.0       # rows 0 + 2 (NaN drops 1)
    assert cov["opp_def_reb_l5_pct"] == 50.0         # rows 0 + 1
    assert cov["q1_reb_l5_pct"] == 50.0              # rows 0 + 2
    # position buckets — only rows with a non-None position contribute
    assert cov["position_C_pct"] == 50.0   # row 0 (Center) + row 2 (Forward-Center)
    assert cov["position_F_pct"] == 25.0   # row 2 (Forward-Center)
    assert cov["position_G_pct"] == 25.0   # row 1 (Guard)


def test_position_one_hot_substring_matching():
    """_position_one_hot fires the correct buckets for known strings,
    multi-position hybrids, and degrades to all-zero for None / unknown."""
    # Single positions
    assert _position_one_hot("Center") == {"position_C": 1.0,
                                            "position_F": 0.0,
                                            "position_G": 0.0}
    assert _position_one_hot("Forward") == {"position_C": 0.0,
                                             "position_F": 1.0,
                                             "position_G": 0.0}
    assert _position_one_hot("Guard") == {"position_C": 0.0,
                                           "position_F": 0.0,
                                           "position_G": 1.0}
    # Hybrids
    assert _position_one_hot("Guard-Forward") == {"position_C": 0.0,
                                                    "position_F": 1.0,
                                                    "position_G": 1.0}
    assert _position_one_hot("Forward-Center") == {"position_C": 1.0,
                                                     "position_F": 1.0,
                                                     "position_G": 0.0}
    # Missing / unknown
    assert _position_one_hot(None) == {"position_C": 0.0,
                                        "position_F": 0.0,
                                        "position_G": 0.0}
    assert _position_one_hot("") == {"position_C": 0.0,
                                      "position_F": 0.0,
                                      "position_G": 0.0}
    assert _position_one_hot("Unknown") == {"position_C": 0.0,
                                              "position_F": 0.0,
                                              "position_G": 0.0}


def test_ship_and_reject_paths_end_to_end():
    """End-to-end shape with mocked train/eval. SHIP path: both gates pass
    -> artifact written + ship=True. REJECT path (100d's exact failure):
    single-split passes but WF only 2/4 negative -> ship=False, reason=
    'wf_failed', NO artifact write."""
    import scripts.retrain_reb_q50_v3 as mod

    # Rotate position across all 3 buckets so every bucket clears the 30%
    # coverage gate (else selected_features < CANDIDATE_FEATURES).
    _positions = ["Center", "Forward", "Guard"]
    synth_rows = []
    for i in range(120):
        r = {"date": f"2024-{(i % 12) + 1:02d}-01", "target_reb": 5.0,
             "position": _positions[i % 3]}
        for k in CANDIDATE_FEATURES:
            r.setdefault(k, 1.0)
        synth_rows.append(r)

    # CASE A: both gates pass -> ship True
    fake_model = {"_synthetic_reb_q50_v3": True}
    fake_ss_ok = {
        "n_rows": 120, "n_train": 80, "n_val": 20, "n_holdout": 20,
        "mae_baseline_85": 1.92, "mae_wide": 1.88,
        "delta_mae": -0.04, "mae_vs_cycle29": -0.0223,
        "wide_model": fake_model, "wide_pred_sample": [5.0] * 25,
    }
    fake_wf_ok = {
        "folds": [{"fold": i, "mae_base": 1.92,
                   "mae_wide": 1.88, "delta_mae": -0.04} for i in range(1, 5)],
        "n_folds": 4, "n_folds_negative": 4, "wf_4_of_4_negative": True,
        "delta_mae_mean": -0.04, "delta_mae_std": 0.0,
    }
    with tempfile.TemporaryDirectory() as td:
        with mock.patch.object(mod, "_MODEL_DIR", td), \
             mock.patch.object(mod, "build_pergame_dataset",
                               return_value=(synth_rows, [])), \
             mock.patch.object(mod, "single_split_eval", return_value=fake_ss_ok), \
             mock.patch.object(mod, "walk_forward_eval", return_value=fake_wf_ok):
            ret = mod.main()
        assert ret == 0
        artifact = os.path.join(td, "reb_q50_v3.pkl")
        metrics = os.path.join(td, "reb_q50_v3_metrics.json")
        assert os.path.exists(artifact), "ship=True path must write reb_q50_v3.pkl"
        assert os.path.exists(metrics)
        meta = json.loads(open(metrics).read())
        assert meta["ship"] is True
        assert meta["single_split"]["mae_wide"] == 1.88
        assert meta["walk_forward"]["wf_4_of_4_negative"] is True
        # The 4 opp features + q1_reb_l5 should all clear the 30% gate on
        # synthetic rows (every synth row sets them to 1.0). Position-bucket
        # coverage depends on the holdout slice rotation, so only check the
        # 5 stable candidates here.
        for must in ("opp_team_oreb_pct_l5", "opp_team_dreb_pct_l5",
                     "opp_team_pace_l5", "opp_def_reb_l5", "q1_reb_l5"):
            assert must in meta["selected_features"], f"{must} missing"

    # CASE B: 100d's exact failure mode — single-split passes, WF 2/4
    fake_wf_bad = {
        "folds": [{"fold": 1, "mae_base": 1.92, "mae_wide": 1.91, "delta_mae": -0.01},
                  {"fold": 2, "mae_base": 1.93, "mae_wide": 1.94, "delta_mae": +0.01},
                  {"fold": 3, "mae_base": 1.91, "mae_wide": 1.92, "delta_mae": +0.01},
                  {"fold": 4, "mae_base": 1.90, "mae_wide": 1.89, "delta_mae": -0.01}],
        "n_folds": 4, "n_folds_negative": 2, "wf_4_of_4_negative": False,
        "delta_mae_mean": 0.0, "delta_mae_std": 0.01,
    }
    with tempfile.TemporaryDirectory() as td:
        with mock.patch.object(mod, "_MODEL_DIR", td), \
             mock.patch.object(mod, "build_pergame_dataset",
                               return_value=(synth_rows, [])), \
             mock.patch.object(mod, "single_split_eval", return_value=fake_ss_ok), \
             mock.patch.object(mod, "walk_forward_eval", return_value=fake_wf_bad):
            ret = mod.main()
        assert ret == 0
        artifact = os.path.join(td, "reb_q50_v3.pkl")
        metrics = os.path.join(td, "reb_q50_v3_metrics.json")
        assert not os.path.exists(artifact), \
            "ship=False path must NOT write reb_q50_v3.pkl"
        assert os.path.exists(metrics)
        meta = json.loads(open(metrics).read())
        assert meta["ship"] is False
        assert meta["reason"] == "wf_failed"
