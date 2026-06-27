"""Gate-matrix test: every lever of the in-play edge signal independently blocks.

BACKLOG TH-02 -- tests/platformkit/ingame/test_inplay_edge_signal_gate_matrix.py

OFFLINE + deterministic: all inputs are injected -- no network, no corpus, no venue.

Acceptance criteria (verbatim from BACKLOG):
  * 4 distinct failing-lever inputs (below-floor edge, stale tick, illiquid price,
    model==market) each produce action="no_bet".
  * 1 all-pass input produces a tiered bet in UNITS (tier in A/B/C).
  * No key in the result dict matches /(\\$|roi|pnl|profit)/.

RAILS: UNITS / probability only. No $ field. edge_claimed=False. ASCII only.

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_inplay_edge_signal_gate_matrix.py -q
"""
from __future__ import annotations

import re
from typing import Any, Dict

import pytest

from scripts.platformkit.ingame import inplay_edge_signal as sig

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
_BANNED_RE = re.compile(r"(\$|roi|pnl|profit)", re.IGNORECASE)


def _assert_no_dollar_field(obj: Any) -> None:
    """Assert no key in the (possibly nested) result matches the banned pattern."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert not _BANNED_RE.search(str(k)), (
                "Banned $ / roi / pnl / profit field found: %r" % k
            )
            _assert_no_dollar_field(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _assert_no_dollar_field(v)


def _all_pass_result() -> Dict[str, Any]:
    """Return an evaluate() call that should clear all gates and yield a tiered bet.

    model_prob=0.80, market implied ~0.55 -> large +EV -> clears tier A floor (.08).
    All gates ON: liquid, fresh, calibration_justified, clv_is_proxy=False (true close).
    """
    return sig.evaluate(
        model_prob=0.80,
        yes_home_prob=0.55,
        yes_away_prob=0.50,
        calibration_justified=True,
        is_liquid=True,
        is_fresh=True,
        clv_is_proxy=False,
    )


# ---------------------------------------------------------------------------
# Matrix: 4 negative controls -- each lever independently blocks to no_bet
# ---------------------------------------------------------------------------

def test_negative_control_below_floor_edge_is_no_bet():
    """Lever: edge (model_prob == devigged market price) -> EV==0 -> below_floor -> no_bet."""
    # Compute the fair price then set model_prob == that fair price so EV ~ 0.
    yes_h, yes_a = 0.55, 0.50
    fair_h = sig.devig_home_price(yes_h, yes_a)
    assert fair_h is not None, "devig_home_price should return a valid prob"

    result = sig.evaluate(
        model_prob=fair_h,          # model == devigged market -> EV ~ 0
        yes_home_prob=yes_h,
        yes_away_prob=yes_a,
        calibration_justified=True,
        is_liquid=True,
        is_fresh=True,
        clv_is_proxy=False,
    )
    assert result["action"] == "no_bet", (
        "Below-floor edge must produce no_bet, got: %r" % result["action"]
    )
    assert result["reason"] == "below_floor", (
        "Reason must be below_floor, got: %r" % result["reason"]
    )
    assert result["tier"] is None, "Tier must be None when below floor"
    _assert_no_dollar_field(result)


def test_negative_control_stale_tick_is_no_bet():
    """Lever: is_fresh=False (stale snapshot) -> no_bet even with a big edge."""
    result = sig.evaluate(
        model_prob=0.80,
        yes_home_prob=0.55,
        yes_away_prob=0.50,
        calibration_justified=True,
        is_liquid=True,
        is_fresh=False,             # STALE -- the blocking lever
        clv_is_proxy=False,
    )
    assert result["action"] == "no_bet", (
        "Stale tick must produce no_bet, got: %r" % result["action"]
    )
    assert result["reason"] == "stale", (
        "Reason must be stale, got: %r" % result["reason"]
    )
    _assert_no_dollar_field(result)


def test_negative_control_illiquid_price_is_no_bet():
    """Lever: is_liquid=False -> no_bet even with a large, fresh, justified edge."""
    result = sig.evaluate(
        model_prob=0.80,
        yes_home_prob=0.55,
        yes_away_prob=0.50,
        calibration_justified=True,
        is_liquid=False,            # ILLIQUID -- the blocking lever
        is_fresh=True,
        clv_is_proxy=False,
    )
    assert result["action"] == "no_bet", (
        "Illiquid price must produce no_bet, got: %r" % result["action"]
    )
    assert result["reason"] == "illiquid", (
        "Reason must be illiquid, got: %r" % result["reason"]
    )
    _assert_no_dollar_field(result)


def test_negative_control_model_equals_market_is_no_bet():
    """Lever: model_prob equals the devigged market price -> no calibration edge -> no_bet.

    When the model and market agree exactly, the edge is 0 and EV is 0 (or marginally
    negative after devig round-trip). The tier floor (.02 minimum) is not cleared, so
    action must be no_bet with reason below_floor.
    """
    yes_h, yes_a = 0.60, 0.45
    fair_h = sig.devig_home_price(yes_h, yes_a)
    assert fair_h is not None

    # Set model_prob to exactly the devigged fair home prob -- model==market.
    result = sig.evaluate(
        model_prob=fair_h,
        yes_home_prob=yes_h,
        yes_away_prob=yes_a,
        calibration_justified=True,
        is_liquid=True,
        is_fresh=True,
        clv_is_proxy=False,
    )
    assert result["action"] == "no_bet", (
        "model==market must produce no_bet, got: %r" % result["action"]
    )
    # edge should be ~0 (within floating-point noise of the devig round-trip)
    assert abs(result["edge"]) < 1e-6, (
        "Edge should be ~0 when model==market, got: %r" % result["edge"]
    )
    assert result["reason"] == "below_floor", (
        "Reason must be below_floor when model==market, got: %r" % result["reason"]
    )
    _assert_no_dollar_field(result)


# ---------------------------------------------------------------------------
# Positive control: all-pass produces a tiered bet in UNITS
# ---------------------------------------------------------------------------

def test_positive_all_pass_yields_tiered_bet():
    """Positive control: all gates pass + large edge -> tiered bet, UNITS only, no $."""
    result = _all_pass_result()

    assert result["action"] == "bet", (
        "All-pass input must produce action=bet, got: %r" % result["action"]
    )
    assert result["tier"] in ("A", "B", "C"), (
        "Tier must be A, B, or C, got: %r" % result["tier"]
    )
    assert result["units"] == "probability", (
        "units field must be 'probability', got: %r" % result["units"]
    )
    assert result["ev"] is not None and result["ev"] > 0.0, (
        "EV must be positive for a tiered bet, got: %r" % result["ev"]
    )
    assert result["edge"] is not None and result["edge"] > 0.0, (
        "Edge must be positive, got: %r" % result["edge"]
    )
    assert result["edge_claimed"] is False, (
        "edge_claimed must always be False (honesty rail)"
    )
    _assert_no_dollar_field(result)


# ---------------------------------------------------------------------------
# Ancillary: confirm the banned-key check is itself correct
# ---------------------------------------------------------------------------

def test_banned_key_check_rejects_dollar_keys():
    """Sanity-check that the regex helper itself flags known bad keys."""
    for bad_key in ("$amount", "roi", "pnl", "profit_usd", "net_profit"):
        assert _BANNED_RE.search(bad_key), (
            "Expected _BANNED_RE to match %r but it did not" % bad_key
        )


def test_banned_key_check_passes_clean_keys():
    """Sanity-check that the regex helper does not flag valid keys."""
    for good_key in ("action", "tier", "edge", "ev", "units", "model_prob",
                     "devigged_price", "reason", "side", "clv_is_proxy"):
        assert not _BANNED_RE.search(good_key), (
            "Expected _BANNED_RE to NOT match %r but it did" % good_key
        )
