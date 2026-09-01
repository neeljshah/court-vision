"""Tests for cost_model -- per-venue TAKER cost model (6.1).

Per-file: python -m pytest scripts/platformkit/econ/test_cost_model.py -q
"""
from __future__ import annotations

import math

import pytest

from scripts.platformkit.econ import cost_model as C


# ---------------------------------------------------------------------------
# Kalshi fee formula fixtures -- exact cent values at known prices
# ---------------------------------------------------------------------------

def test_kalshi_taker_fee_at_p50_is_max_1_75c():
    # 0.07 * 0.5 * 0.5 = 0.0175 -> ceil to cent -> 0.02 (ceil, not round)
    fee = C.kalshi_fee_per_contract(0.50, side="taker")
    assert fee == 0.02


def test_kalshi_maker_fee_is_quarter_of_taker_formula():
    # 0.0175 * 0.5 * 0.5 = 0.004375 -> ceil to cent -> 0.01
    fee = C.kalshi_fee_per_contract(0.50, side="maker")
    assert fee == 0.01


def test_kalshi_fee_at_p10():
    # 0.07 * 0.1 * 0.9 = 0.0063 -> ceil -> 0.01
    fee = C.kalshi_fee_per_contract(0.10, side="taker")
    assert fee == 0.01


def test_kalshi_fee_at_p90_symmetric_to_p10():
    fee10 = C.kalshi_fee_per_contract(0.10, side="taker")
    fee90 = C.kalshi_fee_per_contract(0.90, side="taker")
    assert fee10 == fee90  # P*(1-P) is symmetric about 0.5


def test_kalshi_fee_clamps_out_of_range_price():
    # never raises; clamps into [0.01, 0.99]
    fee_low = C.kalshi_fee_per_contract(0.0)
    fee_high = C.kalshi_fee_per_contract(1.5)
    assert fee_low >= 0.0
    assert fee_high >= 0.0


def test_kalshi_fee_invalid_input_never_raises():
    assert C.kalshi_fee_per_contract(None) == 0.0
    assert C.kalshi_fee_per_contract("nonsense") == 0.0


# ---------------------------------------------------------------------------
# Polymarket
# ---------------------------------------------------------------------------

def test_polymarket_taker_fee_matches_cited_parabolic_schedule():
    # docs.polymarket.com/trading/fees worked example (2026-09-01 schedule,
    # via venue_fees): 100 shares @ P=0.50 -> 100 * 0.05 * 0.50 * 0.50 = $1.25
    fee = C.polymarket_fee(100.0, side="taker", price=0.50)
    assert math.isclose(fee, 1.25, rel_tol=1e-9)


def test_polymarket_taker_fee_away_from_midprice():
    # 100 shares @ P=0.10 -> 100 * 0.05 * 0.10 * 0.90 = $0.45
    fee = C.polymarket_fee(100.0, side="taker", price=0.10)
    assert math.isclose(fee, 0.45, rel_tol=1e-9)


def test_polymarket_maker_fee_is_zero():
    # "Makers are never charged fees. Only takers pay."
    fee = C.polymarket_fee(100.0, side="maker", price=0.50)
    assert fee == 0.0


def test_polymarket_gas_included_only_when_requested():
    fee_no_gas = C.polymarket_fee(10.0, side="taker", include_gas=False, price=0.50)
    fee_gas = C.polymarket_fee(10.0, side="taker", include_gas=True, price=0.50)
    assert fee_gas > fee_no_gas
    assert math.isclose(fee_gas - fee_no_gas, C.POLYMARKET_GAS_PER_TRADE)


def test_polymarket_fee_invalid_input_never_raises():
    assert C.polymarket_fee(None, price=0.50) == 0.0


def test_polymarket_fee_out_of_range_price_raises_unit_error():
    # Cents passed where a probability belongs is a unit error; a silent $0
    # fee would inflate EV (venue_fees defect #4) -- must raise, never zero.
    with pytest.raises(ValueError):
        C.polymarket_fee(100.0, side="taker", price=50)


# ---------------------------------------------------------------------------
# breakeven_edge_prob -- monotonicity + venue coverage
# ---------------------------------------------------------------------------

def test_breakeven_kalshi_size_invariant():
    # Kalshi fee is PER-CONTRACT, not tiered/notional-scaled -- breakeven
    # PROBABILITY must be identical regardless of size (confirms the docstring
    # claim rather than assuming it).
    be_1 = C.breakeven_edge_prob("kalshi", 0.5, size=1)
    be_100 = C.breakeven_edge_prob("kalshi", 0.5, size=100)
    assert be_1 == be_100


def test_breakeven_polymarket_size_invariant():
    be_1 = C.breakeven_edge_prob("polymarket", 0.5, size=1)
    be_100 = C.breakeven_edge_prob("polymarket", 0.5, size=100)
    assert be_1 == be_100


def test_breakeven_kalshi_positive_at_midprice():
    be = C.breakeven_edge_prob("kalshi", 0.50)
    assert be is not None and be > 0.0


def test_breakeven_polymarket_positive_at_midprice():
    be = C.breakeven_edge_prob("polymarket", 0.50)
    assert be is not None and be > 0.0


def test_breakeven_unknown_venue_returns_none():
    assert C.breakeven_edge_prob("draftkings", 0.5) is None


def test_breakeven_invalid_price_returns_none():
    assert C.breakeven_edge_prob("kalshi", 0.0) is None
    assert C.breakeven_edge_prob("kalshi", 1.0) is None
    assert C.breakeven_edge_prob("kalshi", None) is None


def test_breakeven_kalshi_golden_at_midprice():
    # entry @0.50: ceil_to_cent(0.07 * 0.50 * 0.50) = ceil($0.0175) = $0.02;
    # exit @ 1-0.50 = 0.50: another $0.02 -> 0.04 prob-units per $1 contract.
    assert C.breakeven_edge_prob("kalshi", 0.50, side="taker") == 0.04


def test_breakeven_polymarket_golden_at_midprice():
    # per share each way: 0.05 * 0.50 * 0.50 = $0.0125 -> round trip 0.025
    # (superseded flat schedule said 2 * 0.0075 = 0.015 -- it undercharged here).
    be = C.breakeven_edge_prob("polymarket", 0.50, side="taker")
    assert math.isclose(be, 0.025, rel_tol=1e-9)


def test_breakeven_kalshi_maker_cheaper_than_taker():
    be_taker = C.breakeven_edge_prob("kalshi", 0.5, side="taker")
    be_maker = C.breakeven_edge_prob("kalshi", 0.5, side="maker")
    assert be_maker < be_taker


# ---------------------------------------------------------------------------
# DFS multiplier table lookups
# ---------------------------------------------------------------------------

def test_dfs_2pick_power_play_joint_breakeven_is_one_third():
    joint = C.dfs_joint_breakeven_prob("prizepicks", 2, "power_play")
    assert math.isclose(joint, 1.0 / 3.0, rel_tol=1e-5)


def test_dfs_2pick_per_leg_breakeven_is_sqrt_one_third():
    per_leg = C.dfs_breakeven_prob("prizepicks", 2, "power_play")
    assert math.isclose(per_leg, math.sqrt(1.0 / 3.0), rel_tol=1e-5)


def test_dfs_3pick_per_leg_breakeven():
    # 3-pick @ 6x -> joint = 1/6; per-leg = (1/6)**(1/3)
    per_leg = C.dfs_breakeven_prob("prizepicks", 3, "power_play")
    assert math.isclose(per_leg, (1.0 / 6.0) ** (1.0 / 3.0), rel_tol=1e-5)


def test_dfs_underdog_standard_matches_prizepicks_power_play():
    up = C.dfs_breakeven_prob("underdog", 2, "standard")
    pp = C.dfs_breakeven_prob("prizepicks", 2, "power_play")
    assert up == pp


def test_dfs_flex_play_not_implemented_returns_none():
    assert C.dfs_breakeven_prob("prizepicks", 3, "flex_play") is None


def test_dfs_unknown_platform_or_picks_returns_none():
    assert C.dfs_breakeven_prob("fanduel", 2, "power_play") is None
    assert C.dfs_breakeven_prob("prizepicks", 99, "power_play") is None
