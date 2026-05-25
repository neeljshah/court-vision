"""test_fg3m_q50_v3_retrain.py — cycle 100c ship-script smoke tests.

5 tests cover the new helpers + the end-to-end shape of the metrics output.
Mirrors the v2 pattern (test_fg3m_q50_v2_retrain.py).
"""
from __future__ import annotations

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.retrain_fg3m_q50_v3 import (  # noqa: E402
    BASELINE_MAE, CANDIDATE_FEATURES, COVERAGE_FLOOR_PCT,
    _augment_row, _coverage_report, _fg3m_params,
)


def test_candidate_set_is_opp_l5_quartet():
    """v3 candidate set is exactly the 4 cycle-99e opp-context L5 features —
    no q1_fg3m_l5 (failed v2 coverage), no position one-hots / home_spread
    (already tested in v2 — net wash)."""
    assert len(CANDIDATE_FEATURES) == 4
    assert set(CANDIDATE_FEATURES) == {
        "opp_team_def_rtg_l5",
        "opp_team_pace_l5",
        "opp_team_ts_pct_l5",
        "opp_def_fg3m_l5",
    }
    # q1_fg3m_l5 is the cycle-99b coverage casualty — must NOT regress in.
    assert "q1_fg3m_l5" not in CANDIDATE_FEATURES
    # Anchor the cycle-27 baseline and the 30% coverage floor so a typo can't
    # silently weaken the ship gate.
    assert BASELINE_MAE == 0.8941
    assert COVERAGE_FLOOR_PCT == 30.0


def test_augment_row_fills_defaults_and_collapses_nan():
    """_augment_row fills every CANDIDATE_FEATURES key with a finite float,
    even when the source field is None or NaN."""
    row_missing = {"date": "2025-01-01", "target_fg3m": 1.0}
    aug = _augment_row(row_missing)
    for k in CANDIDATE_FEATURES:
        assert k in aug, f"missing augmented key {k}"
        v = aug[k]
        assert isinstance(v, float)
        assert v == v, f"{k} is NaN"
        assert v == 0.0, f"missing source must collapse to 0.0, got {v} for {k}"

    # Real row — verify each opp feature propagates through unchanged.
    row_full = {
        "date": "2025-01-01", "target_fg3m": 2.0,
        "opp_team_def_rtg_l5": 110.5,
        "opp_team_pace_l5":    99.2,
        "opp_team_ts_pct_l5":  0.578,
        "opp_def_fg3m_l5":     12.4,
    }
    aug2 = _augment_row(row_full)
    assert aug2["opp_team_def_rtg_l5"] == 110.5
    assert aug2["opp_team_pace_l5"]    == 99.2
    assert aug2["opp_team_ts_pct_l5"]  == 0.578
    assert aug2["opp_def_fg3m_l5"]     == 12.4

    # NaN inputs collapse to 0.0 — LGB never sees NaN on this path.
    row_nan = {"date": "2025-01-01", "target_fg3m": 0.0,
               "opp_team_def_rtg_l5": float("nan"),
               "opp_team_pace_l5":    float("nan"),
               "opp_team_ts_pct_l5":  float("nan"),
               "opp_def_fg3m_l5":     float("nan")}
    aug3 = _augment_row(row_nan)
    for k in CANDIDATE_FEATURES:
        assert aug3[k] == 0.0


def test_coverage_report_counts_non_none_source_fields():
    """_coverage_report uses the SOURCE fields (None vs. value), NOT the
    post-_augment_row defaults — confirms the report measures real holdout
    coverage instead of every row counting as 100%.
    """
    rows = [
        {"opp_team_def_rtg_l5": 110.0, "opp_team_pace_l5": 99.0,
         "opp_team_ts_pct_l5": 0.55, "opp_def_fg3m_l5": 12.0},
        {"opp_team_def_rtg_l5": None,  "opp_team_pace_l5": 100.0,
         "opp_team_ts_pct_l5": 0.56, "opp_def_fg3m_l5": None},
        {"opp_team_def_rtg_l5": 112.0, "opp_team_pace_l5": None,
         "opp_team_ts_pct_l5": None, "opp_def_fg3m_l5": 11.5},
        {"opp_team_def_rtg_l5": None,  "opp_team_pace_l5": None,
         "opp_team_ts_pct_l5": None, "opp_def_fg3m_l5": None},
    ]
    cov = _coverage_report(rows)
    assert cov["n_rows"] == 4
    # 2/4 non-None each:
    assert cov["opp_team_def_rtg_l5_pct"] == 50.0
    assert cov["opp_team_pace_l5_pct"]    == 50.0
    assert cov["opp_team_ts_pct_l5_pct"]  == 50.0
    assert cov["opp_def_fg3m_l5_pct"]     == 50.0


def test_fg3m_params_match_prop_quantiles_overrides():
    """The LGB-q50 recipe used by the retrain must match the production
    prop_quantiles._per_stat_xgb_params('fg3m') overrides — otherwise the
    'baseline' arm of the single-split eval would be incomparable to
    cycle 27's persisted model."""
    p = _fg3m_params()
    assert p["max_depth"] == 4
    assert p["learning_rate"] == 0.025
    assert p["min_child_weight"] == 15
    assert p["reg_lambda"] == 8.0
    assert p["gamma"] == 0.0
    assert p["subsample"] == 0.7
    assert p["n_estimators"] == 600
    assert p["random_state"] == 42


def test_coverage_empty_rows_returns_zero_n():
    """Empty holdout — _coverage_report short-circuits to n_rows=0 without
    division-by-zero. Guards against the rare fresh-checkout case where
    build_pergame_dataset returns < 5 rows."""
    cov = _coverage_report([])
    assert cov == {"n_rows": 0}
