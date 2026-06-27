"""Per-file tests for scripts.platformkit.quant.clv_core -- the sign-audited yardstick.

Covers the four contract points of INCREMENT 1:
  1. sign-agreement holds on an aligned bet (both verified paths agree -> no raise);
  2. a CONSTRUCTED sign mismatch RAISES (no silent divergence);
  3. assert_vintage REJECTS a hindsight bet (pred_ts >= close_captured_at);
  4. true-close vs proxy-close are NEVER merged (carried separately, proxy flagged).

Run: C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
        tests/platformkit/quant/test_clv_core.py -q
"""
from __future__ import annotations

import pytest

from scripts.platformkit.quant import clv_core


# Aligned HOME bet: taken price 2.20 beats the devigged close (pct > 0) AND the
# calibrated prob 0.60 is above the devigged close ~0.487 (prob > 0).
_ALIGNED = dict(
    side="home",
    taken_decimal=2.20,
    closing_decimal_home=2.00,
    closing_decimal_away=1.90,
    pred_ts="2024-01-15T18:00:00Z",
    close_captured_at="2024-01-15T22:00:00Z",
    calibrated_prob=0.60,
    is_true_close=True,
    pred_id="aligned-1",
)


def test_sign_agreement_holds_on_aligned_bet():
    """Both verified paths positive -> audit returns sign=+1, no raise."""
    res = clv_core.audit_clv(**_ALIGNED)
    assert res.clv_pct is not None and res.clv_pct > 0.0
    assert res.clv_prob is not None and res.clv_prob > 0.0
    assert res.sign == 1
    assert clv_core.clv_sign(res.clv_pct) == clv_core.clv_sign(res.clv_prob)


def test_constructed_sign_mismatch_raises():
    """pct path positive (taken price beats close) but prob path negative
    (calibrated prob BELOW the devigged close ~0.487) must RAISE, never merge."""
    bad = dict(_ALIGNED)
    bad["calibrated_prob"] = 0.30  # below devig_home ~0.487 -> clv_prob < 0
    bad["pred_id"] = "mismatch-1"
    with pytest.raises(AssertionError) as ei:
        clv_core.audit_clv(**bad)
    assert "SIGN MISMATCH" in str(ei.value)


def test_assert_vintage_rejects_hindsight_bet():
    """A prediction stamped AT/AFTER the close it is graded against is hindsight
    and must trip the verified LEAK guard."""
    with pytest.raises(AssertionError) as ei:
        clv_core.assert_vintage(
            "2024-01-15T22:00:00Z", "2024-01-15T22:00:00Z", pred_id="late-1"
        )
    assert "LEAK" in str(ei.value)
    # and the full audit refuses a hindsight bet before computing anything
    hindsight = dict(_ALIGNED)
    hindsight["pred_ts"] = "2024-01-15T23:00:00Z"  # after the close
    hindsight["pred_id"] = "late-2"
    with pytest.raises(AssertionError):
        clv_core.audit_clv(**hindsight)


def test_assert_vintage_passes_clean_vintage():
    """pred_ts strictly before the captured close passes (returns None)."""
    assert clv_core.assert_vintage(
        "2024-01-15T18:00:00Z", "2024-01-15T22:00:00Z", pred_id="ok-1"
    ) is None


def test_true_and_proxy_close_never_merged():
    """is_true_close is carried separately; a proxy reading is flagged proxy=True,
    a true reading proxy=False -- they are never collapsed into one headline."""
    true_res = clv_core.audit_clv(**_ALIGNED)
    assert true_res.is_true_close is True
    assert true_res.proxy is False

    proxy_in = dict(_ALIGNED)
    proxy_in["is_true_close"] = False
    proxy_in["pred_id"] = "proxy-1"
    proxy_res = clv_core.audit_clv(**proxy_in)
    assert proxy_res.is_true_close is False
    assert proxy_res.proxy is True

    # the record surfaces both flags distinctly (no merged headline field)
    rec = proxy_res.as_record()
    assert rec["is_true_close"] is False and rec["proxy"] is True
    assert "units" in rec and rec["units"] == "probability"
    # NO dollar / roi / pnl / stake field anywhere
    for banned in ("roi", "pnl", "dollars", "usd", "stake", "bankroll"):
        assert banned not in rec
