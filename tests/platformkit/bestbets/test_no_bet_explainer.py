"""Per-file tests for scripts.platformkit.bestbets.no_bet_explainer (BBQ5-4).

Run ONLY this file (full pytest freezes the box):
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/bestbets/test_no_bet_explainer.py -q

Acceptance criteria (BBQ5-4):
  * candidate ev below C floor -> {decision:no_bet, tier:None, reason contains
    'below' and the floor value}
  * ev clearing A floor -> {decision:bet, tier:A}
  * mlb sport pulls raised floor from floor_config (proves per-sport wiring)
  * decimal_odds None (offseason) -> {decision:no_bet, reason:UNAVAILABLE} -- no
    fabricated ev
  * reason never claims $ profit
  * ev is EV-per-unit not $
  * empty/garbage inputs -> no_bet, never raises
  * no $/roi/pnl key in any result
"""
from __future__ import annotations

import math
import pytest

from scripts.platformkit.bestbets.no_bet_explainer import explain
from scripts.platformkit.bestbets.floor_config import get_floors
from scripts.platformkit.odds_shop import ev_vs_price


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _odds_for_ev(p: float, target_ev: float) -> float:
    """Decimal odds that yield exactly target_ev at probability p.

    EV = p*odds - 1  =>  odds = (1 + EV) / p
    """
    return (1.0 + target_ev) / p


def _assert_no_forbidden_keys(result: dict) -> None:
    forbidden = {"$", "roi", "pnl", "profit", "bankroll", "usd", "dollar"}
    for k in result:
        assert k.lower() not in forbidden, (
            "Result contains forbidden key %r: %r" % (k, result)
        )


def _assert_reason_no_dollar(result: dict) -> None:
    reason = result.get("reason", "")
    assert "$" not in reason, "reason must never mention $ profit: %r" % reason
    assert "profit" not in reason.lower(), "reason must never claim profit: %r" % reason
    assert "roi" not in reason.lower(), "reason must never mention roi: %r" % reason


# ---------------------------------------------------------------------------
# Core acceptance: below-floor -> no_bet with floor info in reason
# ---------------------------------------------------------------------------

def test_below_c_floor_returns_no_bet():
    """ev below C floor -> decision:no_bet, tier:None, reason contains 'below' + floor."""
    nba_floors = get_floors("nba")
    c_floor = nba_floors["C"]   # 0.02
    # Set EV to half the C floor -- clearly below
    target_ev = c_floor * 0.5   # 0.01
    p = 0.60
    odds = _odds_for_ev(p, target_ev)

    result = explain(p, 0.55, odds, sport="nba")

    assert result["decision"] == "no_bet"
    assert result["tier"] is None
    assert result["ev"] is not None
    assert abs(result["ev"] - target_ev) < 1e-4, (
        "Expected ev~%.4f but got %.4f" % (target_ev, result["ev"])
    )
    reason = result["reason"]
    assert "below" in reason.lower(), "reason must contain 'below': %r" % reason
    # floor value must appear as a numeric substring in the reason
    floor_str = "%.4f" % c_floor
    assert floor_str in reason or str(round(c_floor, 2)) in reason, (
        "reason must contain the floor value (%s): %r" % (floor_str, reason)
    )
    _assert_no_forbidden_keys(result)
    _assert_reason_no_dollar(result)


def test_below_c_floor_floor_used_field():
    """floor_used must be set to the C floor when below it."""
    nba_floors = get_floors("nba")
    c_floor = nba_floors["C"]
    p = 0.55
    odds = _odds_for_ev(p, c_floor - 0.005)   # just below

    result = explain(p, 0.50, odds, sport="nba")

    assert result["decision"] == "no_bet"
    assert result["floor_used"] is not None
    assert abs(result["floor_used"] - c_floor) < 1e-6, (
        "floor_used should be C floor %.4f, got %.4f" % (c_floor, result["floor_used"])
    )


# ---------------------------------------------------------------------------
# Core acceptance: clearing A floor -> bet
# ---------------------------------------------------------------------------

def test_above_a_floor_returns_bet_tier_a():
    """ev clearing A floor -> decision:bet, tier:A."""
    nba_floors = get_floors("nba")
    a_floor = nba_floors["A"]   # 0.08
    target_ev = a_floor + 0.02  # 0.10 -- comfortably above
    p = 0.65
    odds = _odds_for_ev(p, target_ev)

    result = explain(p, 0.55, odds, sport="nba")

    assert result["decision"] == "bet"
    assert result["tier"] == "A"
    assert result["ev"] is not None
    assert result["ev"] > a_floor - 1e-6
    _assert_no_forbidden_keys(result)
    _assert_reason_no_dollar(result)


def test_exactly_at_a_floor_returns_bet_tier_a():
    """ev == A floor exactly -> decision:bet, tier:A."""
    nba_floors = get_floors("nba")
    a_floor = nba_floors["A"]
    p = 0.60
    odds = _odds_for_ev(p, a_floor)

    result = explain(p, 0.52, odds, sport="nba")

    assert result["decision"] == "bet"
    assert result["tier"] == "A"


def test_b_floor_clears_returns_bet_tier_b():
    """ev between B and A floors -> tier B."""
    nba_floors = get_floors("nba")
    b_floor = nba_floors["B"]   # 0.04
    a_floor = nba_floors["A"]   # 0.08
    target_ev = (b_floor + a_floor) / 2.0  # 0.06
    p = 0.60
    odds = _odds_for_ev(p, target_ev)

    result = explain(p, 0.54, odds, sport="nba")

    assert result["decision"] == "bet"
    assert result["tier"] == "B"
    _assert_no_forbidden_keys(result)


def test_c_floor_clears_returns_bet_tier_c():
    """ev exactly at C floor -> tier C."""
    nba_floors = get_floors("nba")
    c_floor = nba_floors["C"]   # 0.02
    p = 0.55
    odds = _odds_for_ev(p, c_floor)

    result = explain(p, 0.52, odds, sport="nba")

    assert result["decision"] == "bet"
    assert result["tier"] == "C"


# ---------------------------------------------------------------------------
# Per-sport floor wiring -- MLB has raised floor
# ---------------------------------------------------------------------------

def test_mlb_raised_floor_vs_nba():
    """MLB C floor > NBA C floor (proves per-sport floor_config wiring)."""
    mlb_floors = get_floors("mlb")
    nba_floors = get_floors("nba")
    assert mlb_floors["C"] > nba_floors["C"], (
        "MLB C floor (%s) should be greater than NBA C floor (%s)"
        % (mlb_floors["C"], nba_floors["C"])
    )


def test_mlb_candidate_below_mlb_floor_but_above_nba_floor():
    """Candidate clears NBA C floor but NOT MLB C floor -> no_bet for mlb."""
    nba_floors = get_floors("nba")
    mlb_floors = get_floors("mlb")
    # Choose an EV between the two C floors
    nba_c = nba_floors["C"]   # 0.02
    mlb_c = mlb_floors["C"]   # 0.04
    assert mlb_c > nba_c, "Precondition: MLB C > NBA C"
    target_ev = (nba_c + mlb_c) / 2.0   # 0.03 -- above NBA C, below MLB C
    p = 0.60
    odds = _odds_for_ev(p, target_ev)

    result_nba = explain(p, 0.55, odds, sport="nba")
    result_mlb = explain(p, 0.55, odds, sport="mlb")

    assert result_nba["decision"] == "bet", (
        "NBA should bet at ev=%.4f" % target_ev
    )
    assert result_mlb["decision"] == "no_bet", (
        "MLB should NOT bet at ev=%.4f (mlb C floor=%.4f)" % (target_ev, mlb_c)
    )


def test_mlb_floor_used_is_mlb_c_floor():
    """floor_used for an MLB no_bet must equal the MLB C floor."""
    mlb_floors = get_floors("mlb")
    mlb_c = mlb_floors["C"]
    p = 0.60
    odds = _odds_for_ev(p, mlb_c - 0.005)   # just below MLB C

    result = explain(p, 0.55, odds, sport="mlb")

    assert result["decision"] == "no_bet"
    assert result["floor_used"] is not None
    assert abs(result["floor_used"] - mlb_c) < 1e-6, (
        "floor_used should be MLB C floor %.4f, got %.4f" % (mlb_c, result["floor_used"])
    )


# ---------------------------------------------------------------------------
# Offseason / UNAVAILABLE: decimal_odds is None
# ---------------------------------------------------------------------------

def test_none_odds_returns_no_bet_unavailable():
    """decimal_odds None -> decision:no_bet, reason contains UNAVAILABLE."""
    result = explain(0.65, 0.55, None, sport="nba")

    assert result["decision"] == "no_bet"
    assert result["tier"] is None
    assert result["ev"] is None, (
        "ev must be None when odds unavailable; got %r" % result["ev"]
    )
    reason = result["reason"]
    assert "UNAVAILABLE" in reason, (
        "reason must contain 'UNAVAILABLE' when odds=None: %r" % reason
    )
    _assert_no_forbidden_keys(result)
    _assert_reason_no_dollar(result)


def test_none_odds_no_fabricated_ev():
    """None odds must NEVER produce a fabricated ev."""
    for p in (0.50, 0.70, 0.99):
        result = explain(p, None, None, sport="nba")
        assert result["ev"] is None, (
            "ev must be None for unavailable odds (p=%.2f): got %r" % (p, result["ev"])
        )


# ---------------------------------------------------------------------------
# Garbage / empty inputs -> no_bet, never raises
# ---------------------------------------------------------------------------

def test_garbage_model_prob_no_crash():
    """Garbage model_prob -> no_bet, no exception."""
    for bad in (None, "abc", float("nan"), -0.5, 1.5, {}, []):
        result = explain(bad, 0.50, 2.0, sport="nba")
        assert result["decision"] == "no_bet", (
            "Expected no_bet for bad model_prob=%r, got %r" % (bad, result)
        )


def test_garbage_decimal_odds_no_crash():
    """Garbage / invalid decimal_odds -> no_bet, no exception."""
    for bad in ("xyz", {}, [], float("nan")):
        result = explain(0.60, 0.55, bad, sport="nba")
        assert result["decision"] == "no_bet"


def test_invalid_decimal_odds_at_or_below_one():
    """decimal_odds <= 1.0 is not a valid bettable price -> no_bet."""
    for bad_odds in (1.0, 0.5, -1.0, 0.0):
        result = explain(0.60, 0.55, bad_odds, sport="nba")
        assert result["decision"] == "no_bet", (
            "Expected no_bet for odds=%r" % bad_odds
        )


def test_empty_call_no_crash():
    """Calling with all Nones must not raise."""
    result = explain(None, None, None, sport="nba")
    assert result["decision"] == "no_bet"


def test_unknown_sport_falls_back_to_default():
    """Unknown sport falls back to global default floors (no crash)."""
    nba_floors = get_floors("nba")
    a_floor = nba_floors["A"]
    target_ev = a_floor + 0.01
    p = 0.65
    odds = _odds_for_ev(p, target_ev)

    result = explain(p, 0.55, odds, sport="foobarXYZ")

    # Should not crash; should either bet or no_bet based on default floors.
    assert result["decision"] in ("bet", "no_bet")
    _assert_no_forbidden_keys(result)


# ---------------------------------------------------------------------------
# Invariant: no forbidden keys, ev is per-unit not $
# ---------------------------------------------------------------------------

def test_no_dollar_or_roi_keys_in_any_result():
    """No $/roi/pnl/profit/bankroll/usd/dollar key in any result ever."""
    cases = [
        (0.60, 0.55, 2.0, "nba"),
        (0.60, 0.55, None, "nba"),
        (None, None, None, "mlb"),
        (0.65, 0.50, 1.9, "tennis"),
    ]
    for args in cases:
        result = explain(*args)
        _assert_no_forbidden_keys(result)
        _assert_reason_no_dollar(result)


def test_ev_is_per_unit_not_dollar():
    """ev is p*odds - 1 (EV per 1 unit staked), consistent with ev_vs_price."""
    p = 0.60
    odds = 2.10
    expected_ev = ev_vs_price(p, odds)  # 0.60*2.10 - 1 = 0.26

    result = explain(p, 0.55, odds, sport="nba")

    if result["ev"] is not None:
        assert abs(result["ev"] - expected_ev) < 1e-5, (
            "ev mismatch: expected %.6f got %.6f" % (expected_ev, result["ev"])
        )


def test_result_always_has_all_keys():
    """Every result has decision, tier, ev, floor_used, reason."""
    required = {"decision", "tier", "ev", "floor_used", "reason"}
    cases = [
        (0.60, 0.55, 2.0, "nba"),
        (0.60, 0.55, None, "nba"),
        (None, None, None, "mlb"),
    ]
    for args in cases:
        result = explain(*args)
        for k in required:
            assert k in result, "Key %r missing from result: %r" % (k, result)


# ---------------------------------------------------------------------------
# Proxy floor bump
# ---------------------------------------------------------------------------

def test_proxy_true_raises_floor_for_props():
    """With clv_is_proxy=True a candidate just above the raw C floor may be no_bet."""
    nba_floors = get_floors("nba")
    c_floor = nba_floors["C"]   # 0.02
    # EV = raw C floor exactly -- clears without proxy, fails with proxy
    p = 0.55
    odds = _odds_for_ev(p, c_floor)

    result_no_proxy = explain(p, 0.52, odds, sport="nba", clv_is_proxy=False)
    result_proxy = explain(p, 0.52, odds, sport="nba", clv_is_proxy=True)

    assert result_no_proxy["decision"] == "bet", (
        "Should bet at ev=C_floor with no proxy"
    )
    assert result_proxy["decision"] == "no_bet", (
        "Should NOT bet at ev=C_floor with proxy (floor raised)"
    )
