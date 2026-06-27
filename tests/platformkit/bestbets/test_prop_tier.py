"""Per-file tests for scripts.platformkit.bestbets.prop_tier.

Run ONLY this file (full pytest freezes the box):
    python -m pytest tests/platformkit/bestbets/test_prop_tier.py -q

Acceptance criteria (BB-Q2):
  * EV ~0.09 -> "A"       (EV_FLOOR_A = 0.08; proxy bump 0.01 -> effective 0.09)
  * EV ~0.01 -> None      (below EV_FLOOR_C = 0.02; proxy bump -> effective 0.03)
  * missing/None odds -> None
  * no dollar key in any return
"""
from __future__ import annotations

import pytest

from scripts.platformkit.bestbets.prop_tier import tier_prop
from scripts.platformkit.pm_trading.policy import (
    EV_FLOOR_A,
    EV_FLOOR_B,
    EV_FLOOR_C,
    EV_PROXY_PENALTY,
)
from scripts.platformkit.odds_shop import ev_vs_price


# ---------------------------------------------------------------------------
# Helper: choose decimal_odds that yields exactly the desired EV for p_over.
# EV = p*odds - 1  =>  odds = (1 + EV) / p
# ---------------------------------------------------------------------------
def _odds_for_ev(p_over: float, target_ev: float) -> float:
    return (1.0 + target_ev) / p_over


# ---------------------------------------------------------------------------
# Core tiering cases -- proxy=True (default for props)
# ---------------------------------------------------------------------------

def test_high_ev_returns_A():
    """EV of ~0.09 clears the proxy-adjusted A floor (0.08 + 0.01 = 0.09)."""
    p = 0.60
    # EV = 0.09 exactly at the proxy-bumped A floor -> should be tier A.
    ev_target = EV_FLOOR_A + EV_PROXY_PENALTY  # 0.09
    odds = _odds_for_ev(p, ev_target)
    result = tier_prop(p, odds, clv_is_proxy=True)
    assert result == "A", (
        "Expected 'A' for EV=%.4f (proxy-adjusted floor=%.4f) but got %r"
        % (ev_target, EV_FLOOR_A + EV_PROXY_PENALTY, result)
    )


def test_ev_well_above_A_floor_returns_A():
    """Strong EV (0.15) returns A regardless of proxy bump."""
    p = 0.65
    ev_target = 0.15
    odds = _odds_for_ev(p, ev_target)
    assert tier_prop(p, odds, clv_is_proxy=True) == "A"


def test_low_ev_below_floor_returns_None():
    """EV of ~0.01 is below even the raw C floor (0.02); proxy makes it worse."""
    p = 0.55
    ev_target = 0.01  # well below EV_FLOOR_C=0.02; proxy bump -> effective 0.03
    odds = _odds_for_ev(p, ev_target)
    result = tier_prop(p, odds, clv_is_proxy=True)
    assert result is None, (
        "Expected None for EV=%.4f (below proxy floor) but got %r" % (ev_target, result)
    )


def test_missing_odds_returns_None():
    """None decimal_odds (UNAVAILABLE offseason) -> None, no exception."""
    assert tier_prop(0.60, None) is None


def test_none_odds_no_fabricated_price():
    """None odds must NEVER produce a tier -- not even a low one."""
    for p in (0.50, 0.70, 0.99):
        assert tier_prop(p, None) is None


# ---------------------------------------------------------------------------
# Floor boundary behaviour
# ---------------------------------------------------------------------------

def test_exactly_at_proxy_C_floor_returns_C():
    """EV == EV_FLOOR_C + EV_PROXY_PENALTY should just clear tier C."""
    p = 0.55
    ev_target = EV_FLOOR_C + EV_PROXY_PENALTY  # 0.02 + 0.01 = 0.03
    odds = _odds_for_ev(p, ev_target)
    assert tier_prop(p, odds, clv_is_proxy=True) == "C"


def test_just_below_proxy_C_floor_returns_None():
    """One epsilon below proxy C floor -> no bet."""
    p = 0.55
    ev_target = EV_FLOOR_C + EV_PROXY_PENALTY - 1e-6  # just under 0.03
    odds = _odds_for_ev(p, ev_target)
    assert tier_prop(p, odds, clv_is_proxy=True) is None


def test_proxy_false_true_close_uses_lower_floor():
    """With clv_is_proxy=False, a raw-C-floor EV clears; with True it does not."""
    p = 0.55
    ev_target = EV_FLOOR_C  # 0.02: clears without proxy, does NOT with proxy bump
    odds = _odds_for_ev(p, ev_target)
    assert tier_prop(p, odds, clv_is_proxy=False) == "C"
    assert tier_prop(p, odds, clv_is_proxy=True) is None


def test_exactly_at_proxy_B_floor_returns_B():
    p = 0.60
    ev_target = EV_FLOOR_B + EV_PROXY_PENALTY  # 0.04 + 0.01 = 0.05
    odds = _odds_for_ev(p, ev_target)
    assert tier_prop(p, odds, clv_is_proxy=True) == "B"


# ---------------------------------------------------------------------------
# Bad / edge-case inputs
# ---------------------------------------------------------------------------

def test_invalid_odds_at_or_below_one():
    """Decimal odds <= 1.0 are not valid bettable prices -> None."""
    assert tier_prop(0.60, 1.0) is None
    assert tier_prop(0.60, 0.5) is None
    assert tier_prop(0.60, -2.0) is None


def test_no_dollar_key_in_return():
    """tier_prop must return a str or None, never a dict containing a $ field."""
    result = tier_prop(0.65, 2.0, clv_is_proxy=True)
    # The return value is Optional[str] -- check it is not a mapping.
    assert not isinstance(result, dict), (
        "tier_prop must return Optional[str], not a dict with hidden $ fields"
    )


def test_return_is_string_or_none():
    """Sanity: return type is str or None."""
    valid = tier_prop(0.65, 2.0)
    assert valid is None or isinstance(valid, str)
    missing = tier_prop(0.65, None)
    assert missing is None


def test_ev_monotone_in_odds():
    """Higher decimal odds -> higher EV -> same-or-stronger tier."""
    p = 0.60
    tier_rank = {None: 0, "C": 1, "B": 2, "A": 3}
    odds_grid = [1.5, 1.8, 2.0, 2.2, 2.5, 3.0]
    prev_rank = -1
    for o in odds_grid:
        r = tier_rank[tier_prop(p, o, clv_is_proxy=True)]
        assert r >= prev_rank, (
            "Tier weakened as odds rose: odds=%r gave rank %d, prev=%d" % (o, r, prev_rank)
        )
        prev_rank = r
