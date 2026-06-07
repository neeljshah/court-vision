"""Tests for the line-movement gate harness verdict logic.

Covers the honest dual gate plus the INSUFFICIENT_DATA short-circuit that fires
whenever the line-movement columns are all-neutral across evaluable rows (no
date overlap between data/lines/ and the prop gamelog targets).
"""
import os
import sys

import pytest

os.environ.setdefault("NBA_OFFLINE", "1")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scripts.loop.eval_linemove_gate import _verdict  # noqa: E402


def _base_result(per_stat, n_real):
    return {
        "n_rows_with_real_movement": n_real,
        "lines_dates_min": "2026-05-25",
        "lines_dates_max": "2026-05-31",
        "dataset_dates_max": "2026-05-24",
        "per_stat": per_stat,
    }


def test_insufficient_data_short_circuit():
    # No row carries real movement -> every stat is INSUFFICIENT_DATA regardless
    # of the (noise) deltas, and base+lm is identical to base.
    per = {
        "pts": {"evaluated": True, "delta_mae_mean": -0.01, "all_improve": True,
                "neg_folds": 4, "n_folds": 4},
        "reb": {"evaluated": True, "delta_mae_mean": +0.01, "all_improve": False,
                "neg_folds": 0, "n_folds": 4},
    }
    out = _verdict(_base_result(per, n_real=0))
    assert out["overall_verdict"] == "INSUFFICIENT_DATA"
    assert out["per_stat_verdict"]["pts"] == "INSUFFICIENT_DATA"
    assert out["per_stat_verdict"]["reb"] == "INSUFFICIENT_DATA"
    assert "Zero date overlap" in out["overall_reason"]


def test_ship_when_all_folds_improve():
    per = {"pts": {"evaluated": True, "delta_mae_mean": -0.02, "all_improve": True,
                   "neg_folds": 4, "n_folds": 4}}
    out = _verdict(_base_result(per, n_real=1500))
    assert out["per_stat_verdict"]["pts"] == "SHIP"
    assert out["overall_verdict"] == "SHIP"


def test_variance_only_when_negative_but_not_all_folds():
    per = {"pts": {"evaluated": True, "delta_mae_mean": -0.005, "all_improve": False,
                   "neg_folds": 2, "n_folds": 4}}
    out = _verdict(_base_result(per, n_real=1500))
    assert out["per_stat_verdict"]["pts"] == "VARIANCE-ONLY"
    assert out["overall_verdict"] == "VARIANCE-ONLY"


def test_reject_when_delta_nonnegative():
    per = {"pts": {"evaluated": True, "delta_mae_mean": +0.003, "all_improve": False,
                   "neg_folds": 1, "n_folds": 4}}
    out = _verdict(_base_result(per, n_real=1500))
    assert out["per_stat_verdict"]["pts"] == "REJECT"
    assert out["overall_verdict"] == "REJECT"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
