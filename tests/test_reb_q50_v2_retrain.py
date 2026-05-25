"""test_reb_q50_v2_retrain.py — cycle 100d ship-script smoke tests.

5 tests for the REB LGB-q50 v2 retrain helpers:
  1. CANDIDATE_FEATURES set is exactly the 4 cycle-99e opp-context columns.
  2. BASELINE_MAE + COVERAGE_FLOOR_PCT constants haven't drifted.
  3. _augment_row coerces None / NaN / strings to finite 0.0 floats and
     propagates real numeric values unchanged.
  4. _coverage_report counts only non-None, non-NaN source fields (so a
     parquet-rebuilt holdout slice with partial coverage is detected
     instead of falsely reading 100% from the post-_augment_row defaults).
  5. _reb_params matches the cycle-29 LGB-q50 REB recipe used by
     prop_quantiles._per_stat_xgb_params('reb') so the baseline arm of
     the eval is comparable to the on-disk model.
"""
from __future__ import annotations

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.retrain_reb_q50_v2 import (  # noqa: E402
    BASELINE_MAE, CANDIDATE_FEATURES, COVERAGE_FLOOR_PCT,
    _augment_row, _coverage_report, _reb_params,
)


def test_candidate_features_match_cycle_99e_unlock():
    """The candidate set is exactly the 4 cycle-99e opp-context columns —
    3 from team_advanced_stats (opp_team_oreb_pct_l5, opp_team_dreb_pct_l5,
    opp_team_pace_l5) + 1 from oppdef.l5_allowed (opp_def_reb_l5). Guard
    against accidental drift (e.g. a future cycle silently adds opp_team_ts_l5
    without bumping the model filename and shape gates)."""
    assert len(CANDIDATE_FEATURES) == 4
    assert set(CANDIDATE_FEATURES) == {
        "opp_team_oreb_pct_l5",
        "opp_team_dreb_pct_l5",
        "opp_team_pace_l5",
        "opp_def_reb_l5",
    }


def test_anchor_constants():
    """Anchor the cycle-29 REB MAE and the 30% coverage floor in tests so
    a typo in the ship-gate constant is caught before silently shipping."""
    assert BASELINE_MAE == 1.9023
    assert COVERAGE_FLOOR_PCT == 30.0


def test_augment_row_collapses_missing_and_nan_to_finite_floats():
    """_augment_row fills every CANDIDATE_FEATURES key with a finite float,
    even when the source field is None, NaN, or non-numeric."""
    row_missing = {"date": "2025-01-01", "target_reb": 5.0}
    aug = _augment_row(row_missing)
    for k in CANDIDATE_FEATURES:
        assert k in aug, f"missing augmented key {k}"
        v = aug[k]
        assert isinstance(v, float)
        assert v == v, f"{k} is NaN"
        assert v == 0.0, f"{k} should default to 0.0 when source is missing"

    # Real numeric values propagate unchanged.
    row_full = {
        "date": "2025-01-01", "target_reb": 8.0,
        "opp_team_oreb_pct_l5": 0.27,
        "opp_team_dreb_pct_l5": 0.74,
        "opp_team_pace_l5": 99.5,
        "opp_def_reb_l5": 45.6,
    }
    aug2 = _augment_row(row_full)
    assert aug2["opp_team_oreb_pct_l5"] == 0.27
    assert aug2["opp_team_dreb_pct_l5"] == 0.74
    assert aug2["opp_team_pace_l5"] == 99.5
    assert aug2["opp_def_reb_l5"] == 45.6

    # NaN / non-numeric collapse to 0.0 — LGB never sees NaN.
    row_nan = {"date": "2025-01-01", "target_reb": 3.0,
               "opp_team_oreb_pct_l5": float("nan"),
               "opp_team_dreb_pct_l5": "junk",
               "opp_team_pace_l5": None,
               "opp_def_reb_l5": 42.0}
    aug3 = _augment_row(row_nan)
    assert aug3["opp_team_oreb_pct_l5"] == 0.0
    assert aug3["opp_team_dreb_pct_l5"] == 0.0
    assert aug3["opp_team_pace_l5"] == 0.0
    assert aug3["opp_def_reb_l5"] == 42.0   # real value still propagates


def test_coverage_report_counts_only_real_source_values():
    """_coverage_report reads the SOURCE fields BEFORE _augment_row collapses
    to 0.0 — so a partial-parquet holdout shows real coverage, not 100%.
    None AND NaN both count as missing."""
    rows = [
        {"opp_team_oreb_pct_l5": 0.27, "opp_team_dreb_pct_l5": 0.74,
         "opp_team_pace_l5": 99.5,     "opp_def_reb_l5": 45.0},
        {"opp_team_oreb_pct_l5": None, "opp_team_dreb_pct_l5": 0.72,
         "opp_team_pace_l5": float("nan"), "opp_def_reb_l5": 44.0},
        {"opp_team_oreb_pct_l5": 0.30, "opp_team_dreb_pct_l5": None,
         "opp_team_pace_l5": 101.0,    "opp_def_reb_l5": None},
        {"opp_team_oreb_pct_l5": None, "opp_team_dreb_pct_l5": None,
         "opp_team_pace_l5": None,     "opp_def_reb_l5": None},
    ]
    cov = _coverage_report(rows)
    assert cov["n_rows"] == 4
    assert cov["opp_team_oreb_pct_l5_pct"] == 50.0   # 2/4 (rows 0 + 2)
    assert cov["opp_team_dreb_pct_l5_pct"] == 50.0   # 2/4 (rows 0 + 1)
    assert cov["opp_team_pace_l5_pct"] == 50.0       # 2/4 (rows 0 + 2; NaN drops row 1)
    assert cov["opp_def_reb_l5_pct"] == 50.0         # 2/4 (rows 0 + 1)


def test_reb_params_match_cycle_29_recipe():
    """The LGB-q50 recipe used by the v2 retrain must match the cycle-29
    REB overrides from prop_quantiles._per_stat_xgb_params('reb') so the
    'baseline' arm of the eval is comparable to the persisted REB model."""
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
