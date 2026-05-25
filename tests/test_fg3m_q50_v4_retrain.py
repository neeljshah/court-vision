"""test_fg3m_q50_v4_retrain.py — cycle 101c ship-script smoke tests.

6 tests covering the candidate union, helper correctness, coverage gate,
and parameter pinning. Mirrors the v3 pattern but verifies the v4 wider
union (4 opp_l5 + q1 + home_spread + 3 position) that came in once
q1_fg3m_l5 coverage rose from 0% to ~85%.
"""
from __future__ import annotations

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.retrain_fg3m_q50_v4 import (  # noqa: E402
    BASELINE_MAE, CANDIDATE_FEATURES, COVERAGE_FLOOR_PCT, COVERAGE_KEY,
    _augment_row, _coverage_report, _fg3m_params, _position_onehot,
)


def test_candidate_set_is_full_union_of_v2_and_v3():
    """v4 candidate set is the FULL union of v2's q1+spread+position trio
    AND v3's 4 cycle-99e opp-context L5 features — exactly 9 candidates."""
    assert len(CANDIDATE_FEATURES) == 9
    expected = {
        "opp_team_def_rtg_l5", "opp_team_pace_l5",
        "opp_team_ts_pct_l5",  "opp_def_fg3m_l5",
        "q1_fg3m_l5", "home_spread",
        "position_C", "position_F", "position_G",
    }
    assert set(CANDIDATE_FEATURES) == expected
    # q1_fg3m_l5 must be present this cycle (the whole point of v4 is the
    # coverage backfill that took q1 from 0% to ~85%).
    assert "q1_fg3m_l5" in CANDIDATE_FEATURES
    # Pin the cycle-27 baseline + 30% floor so a typo can't silently widen
    # or weaken the ship gate.
    assert BASELINE_MAE == 0.8941
    assert COVERAGE_FLOOR_PCT == 30.0
    # COVERAGE_KEY must cover every candidate; position one-hots share one
    # source field ("position") since they all derive from row['position'].
    for feat in CANDIDATE_FEATURES:
        assert feat in COVERAGE_KEY, f"{feat} missing coverage key"
    assert (COVERAGE_KEY["position_C"] == COVERAGE_KEY["position_F"]
            == COVERAGE_KEY["position_G"] == "position_pct")


def test_augment_row_fills_defaults_and_collapses_nan():
    """_augment_row fills every CANDIDATE_FEATURES key with a finite float,
    even when the source field is None or NaN. Position one-hots default
    to (0, 0, 0) when row['position'] is missing."""
    row_missing = {"date": "2025-01-01", "target_fg3m": 1.0}
    aug = _augment_row(row_missing)
    for k in CANDIDATE_FEATURES:
        assert k in aug, f"missing augmented key {k}"
        v = aug[k]
        assert isinstance(v, float)
        assert v == v, f"{k} is NaN"
        assert v == 0.0, f"missing source must collapse to 0.0, got {v} for {k}"

    # Real row — every candidate propagates with the right value.
    row_full = {
        "date": "2025-01-01", "target_fg3m": 2.0,
        "opp_team_def_rtg_l5": 110.5,
        "opp_team_pace_l5":    99.2,
        "opp_team_ts_pct_l5":  0.578,
        "opp_def_fg3m_l5":     12.4,
        "q1_fg3m_l5":          0.65,
        "home_spread":         -4.5,
        "position":            "Guard-Forward",
    }
    aug2 = _augment_row(row_full)
    assert aug2["opp_team_def_rtg_l5"] == 110.5
    assert aug2["opp_team_pace_l5"]    == 99.2
    assert aug2["opp_team_ts_pct_l5"]  == 0.578
    assert aug2["opp_def_fg3m_l5"]     == 12.4
    assert aug2["q1_fg3m_l5"]          == 0.65
    assert aug2["home_spread"]         == -4.5
    # Guard-Forward sets BOTH position_F and position_G; not position_C.
    assert aug2["position_F"] == 1.0
    assert aug2["position_G"] == 1.0
    assert aug2["position_C"] == 0.0

    # NaN inputs collapse to 0.0 — LGB never sees NaN on this path.
    row_nan = {"date": "2025-01-01", "target_fg3m": 0.0,
               "opp_team_def_rtg_l5": float("nan"),
               "q1_fg3m_l5":          float("nan"),
               "home_spread":         float("nan"),
               "position":            None}
    aug3 = _augment_row(row_nan)
    for k in CANDIDATE_FEATURES:
        assert aug3[k] == 0.0, f"NaN should collapse to 0.0 for {k}"


def test_position_onehot_handles_multi_position_and_unknown():
    """_position_onehot multi-bits hyphenated positions and zeros unknowns."""
    assert _position_onehot("Guard")          == (0.0, 0.0, 1.0)
    assert _position_onehot("Forward")        == (0.0, 1.0, 0.0)
    assert _position_onehot("Center")         == (1.0, 0.0, 0.0)
    # Multi-position strings set multiple bits.
    assert _position_onehot("Guard-Forward")  == (0.0, 1.0, 1.0)
    assert _position_onehot("Center-Forward") == (1.0, 1.0, 0.0)
    assert _position_onehot("Forward-Center") == (1.0, 1.0, 0.0)
    # Unknown / None / empty -> all-zero bucket.
    assert _position_onehot(None) == (0.0, 0.0, 0.0)
    assert _position_onehot("")   == (0.0, 0.0, 0.0)
    assert _position_onehot("Wing") == (0.0, 0.0, 0.0)


def test_coverage_report_counts_non_none_source_fields():
    """_coverage_report uses the SOURCE fields (None vs. value), NOT the
    post-_augment_row defaults — confirms the report measures real holdout
    coverage instead of every row counting as 100%."""
    rows = [
        # row 0 — full coverage
        {"opp_team_def_rtg_l5": 110.0, "opp_team_pace_l5": 99.0,
         "opp_team_ts_pct_l5": 0.55, "opp_def_fg3m_l5": 12.0,
         "q1_fg3m_l5": 0.5, "home_spread": -3.0, "position": "Guard"},
        # row 1 — partial
        {"opp_team_def_rtg_l5": None,  "opp_team_pace_l5": 100.0,
         "opp_team_ts_pct_l5": 0.56, "opp_def_fg3m_l5": None,
         "q1_fg3m_l5": None, "home_spread": 2.5, "position": None},
        # row 2 — partial (different mix)
        {"opp_team_def_rtg_l5": 112.0, "opp_team_pace_l5": None,
         "opp_team_ts_pct_l5": None, "opp_def_fg3m_l5": 11.5,
         "q1_fg3m_l5": 0.7, "home_spread": None, "position": "Center"},
        # row 3 — empty
        {"opp_team_def_rtg_l5": None,  "opp_team_pace_l5": None,
         "opp_team_ts_pct_l5": None, "opp_def_fg3m_l5": None,
         "q1_fg3m_l5": None, "home_spread": None, "position": None},
    ]
    cov = _coverage_report(rows)
    assert cov["n_rows"] == 4
    # 2/4 non-None each on opp_l5:
    assert cov["opp_team_def_rtg_l5_pct"] == 50.0
    assert cov["opp_team_pace_l5_pct"]    == 50.0
    assert cov["opp_team_ts_pct_l5_pct"]  == 50.0
    assert cov["opp_def_fg3m_l5_pct"]     == 50.0
    # 2/4 q1 + home_spread + position non-None:
    assert cov["q1_fg3m_l5_pct"]  == 50.0
    assert cov["home_spread_pct"] == 50.0
    assert cov["position_pct"]    == 50.0


def test_coverage_empty_rows_returns_zero_n():
    """Empty holdout — _coverage_report short-circuits to n_rows=0 without
    division-by-zero. Guards against the rare fresh-checkout case."""
    cov = _coverage_report([])
    assert cov == {"n_rows": 0}


def test_fg3m_params_match_prop_quantiles_overrides():
    """The LGB-q50 recipe used by the retrain must match the production
    prop_quantiles._per_stat_xgb_params('fg3m') overrides — otherwise the
    'baseline' arm of the single-split eval would be incomparable to the
    cycle-27 persisted model."""
    p = _fg3m_params()
    assert p["max_depth"]        == 4
    assert p["learning_rate"]    == 0.025
    assert p["min_child_weight"] == 15
    assert p["reg_lambda"]       == 8.0
    assert p["gamma"]            == 0.0
    assert p["subsample"]        == 0.7
    assert p["colsample_bytree"] == 0.8
    assert p["reg_alpha"]        == 0.5
    assert p["n_estimators"]     == 600
    assert p["random_state"]     == 42
