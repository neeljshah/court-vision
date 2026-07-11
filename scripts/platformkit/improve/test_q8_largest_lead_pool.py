"""Per-file test for improve.q8_largest_lead_pool. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/improve/test_q8_largest_lead_pool.py -q
"""
from __future__ import annotations

from scripts.platformkit.improve import q8_largest_lead_pool as q8


def test_fisher_z_ci_brackets_the_point_estimate():
    ci = q8._fisher_z_ci(0.75, 40)
    assert ci["ci_lo"] < 0.75 < ci["ci_hi"]


def test_fisher_z_ci_nan_for_tiny_n():
    ci = q8._fisher_z_ci(0.5, 3)
    assert ci["ci_lo"] != ci["ci_lo"]  # NaN


def test_leg_verdict_ci_straddle_forces_underpowered_even_with_low_p():
    ci = {"ci_lo": -0.05, "ci_hi": 0.4}
    assert q8._leg_verdict([0.6, 0.7, 0.8], 1e-6, 0.5, ci, 1) == "NULL_UNDERPOWERED"


def test_leg_verdict_requires_two_of_three_sign_consistent():
    ci = {"ci_lo": 0.1, "ci_hi": 0.6}
    # only 1/3 seasons matches original positive sign -> NULL_LOCAL, not PASS
    assert q8._leg_verdict([-0.6, -0.7, 0.8], 1e-6, 0.4, ci, 1) == "NULL_LOCAL"
