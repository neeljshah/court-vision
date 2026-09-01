"""Golden-number + property tests for execution.venue_fees.

Numbers below are hand-computed from the formulas in venue_fees.py's own
docstring citations, not copied from the implementation.
"""
from __future__ import annotations

import pytest

from scripts.platformkit.execution import venue_fees as F


# ---------------------------------------------------------------------------
# Kalshi golden numbers
# ---------------------------------------------------------------------------

def test_kalshi_taker_golden_p50():
    # 0.07 * 1 * 0.5 * 0.5 = 0.0175 -> 1.75 cents -> ceil to 2 cents = $0.02
    assert F.fee_kalshi_taker(1, 0.50) == 0.02


def test_kalshi_maker_golden_p50():
    # 0.0175 * 1 * 0.5 * 0.5 = 0.004375 -> 0.4375 cents -> ceil to 1 cent = $0.01
    assert F.fee_kalshi_maker(1, 0.50) == 0.01


def test_kalshi_ceiling_applies_once_per_batch_not_per_contract():
    # REGRESSION: the cited schedule is ceil(0.07 * C * P * (1-P)) -- C is INSIDE
    # the ceiling. 10 @ 0.50: 0.07*10*0.25 = $0.175 -> ceil = $0.18.
    # Ceiling per-contract then multiplying gives $0.20, an 11% overcharge.
    assert F.fee_kalshi_taker(10, 0.50) == 0.18
    # 100 @ 0.50: 0.07*100*0.25 = $1.75, already whole cents -> $1.75 (not $2.00)
    assert F.fee_kalshi_taker(100, 0.50) == 1.75


def test_kalshi_fee_is_sublinear_in_size():
    # A consequence of the batch ceiling: doubling size never more than doubles
    # the fee, and here strictly less than doubles it.
    assert F.fee_kalshi_taker(20, 0.50) < 2 * F.fee_kalshi_taker(10, 0.50)


def test_kalshi_maker_lt_taker_at_mid_price():
    assert F.fee_kalshi_maker(1, 0.50) < F.fee_kalshi_taker(1, 0.50)


def test_kalshi_symmetry_p_and_1_minus_p():
    assert F.fee_kalshi_taker(1, 0.30) == F.fee_kalshi_taker(1, 0.70)
    assert F.fee_kalshi_maker(1, 0.22) == F.fee_kalshi_maker(1, 0.78)


def test_kalshi_zero_at_boundary_prices():
    assert F.fee_kalshi_taker(1, 0.0) == 0.0
    assert F.fee_kalshi_taker(1, 1.0) == 0.0
    assert F.fee_kalshi_maker(1, 0.0) == 0.0
    assert F.fee_kalshi_maker(1, 1.0) == 0.0


def test_kalshi_bad_input_never_raises():
    assert F.fee_kalshi_taker(1, None) == 0.0
    assert F.fee_kalshi_taker(1, "nonsense") == 0.0
    assert F.fee_kalshi_taker("nonsense", 0.5) == 0.0


def test_kalshi_negative_size_never_credits_a_fee():
    # REGRESSION: a signed size must not flip the fee negative -- a negative fee
    # would ADD to EV. Sizes are magnitudes.
    assert F.fee_kalshi_taker(-10, 0.50) == F.fee_kalshi_taker(10, 0.50)
    assert F.fee_kalshi_taker(-10, 0.50) > 0.0


# ---------------------------------------------------------------------------
# Cents-vs-dollars unit guard
# ---------------------------------------------------------------------------

def test_price_in_cents_raises_instead_of_silently_zero_fee():
    # REGRESSION: clamping 50 -> 1.0 produced a $0.00 fee, i.e. a unit error
    # silently made trading free and inflated EV. It must be loud.
    for fn in (F.fee_kalshi_taker, F.fee_kalshi_maker):
        with pytest.raises(ValueError):
            fn(1, 50)
    with pytest.raises(ValueError):
        F.fee_polymarket("taker", 100.0, 50)
    with pytest.raises(ValueError):
        F.expected_value_after_fees(0.6, 50, "yes", "kalshi", "taker")


def test_float_noise_around_bounds_still_accepted():
    assert F.fee_kalshi_taker(1, 1.0 + 1e-12) == 0.0
    assert F.fee_kalshi_taker(1, -1e-12) == 0.0


# ---------------------------------------------------------------------------
# Polymarket golden numbers
# ---------------------------------------------------------------------------

def test_polymarket_taker_golden_peak():
    # docs.polymarket.com worked example: 100 shares @ P=0.50 -> $1.25
    # 100 * 0.05 * 0.5 * 0.5 = 1.25
    assert F.fee_polymarket("taker", 100.0, 0.50) == 1.25


def test_polymarket_rate_of_dollar_notional_is_2x_the_per_share_cents():
    # The unit trap the wiring fell into: $1.25 on 100 shares @ $0.50 is
    # 1.25 cents/share but 2.5% of the $50 dollar notional, not 1.25%.
    fee = F.fee_polymarket("taker", 100.0, 0.50)
    dollar_notional = 100.0 * 0.50
    assert round(fee / dollar_notional, 9) == 0.025


def test_polymarket_rate_of_notional_rises_as_price_falls():
    # fee/dollar_notional = feeRate * (1 - P), so cheap shares cost MORE in bps.
    def rate(p):
        return F.fee_polymarket("taker", 100.0, p) / (100.0 * p)
    assert rate(0.10) > rate(0.50) > rate(0.90)


def test_polymarket_maker_always_zero():
    assert F.fee_polymarket("maker", 100.0, 0.50) == 0.0
    assert F.fee_polymarket("maker", 100.0, 0.10) == 0.0


def test_polymarket_unknown_mode_fails_closed_not_billed_as_taker():
    # REGRESSION: `else TAKER` billed any unrecognized mode at the taker rate.
    # thresholds.ORDER_MODE is the literal string "maker_only", which used to
    # silently return the TAKER fee for a maker-only order.
    for bad in ("maker_only", "yes", "no", "", None):
        with pytest.raises(NotImplementedError):
            F.fee_polymarket(bad, 100.0, 0.50)


def test_polymarket_mode_tolerates_case_and_whitespace():
    assert F.fee_polymarket("  MAKER ", 100.0, 0.50) == 0.0
    assert F.fee_polymarket("Taker", 100.0, 0.50) == 1.25


def test_polymarket_symmetry_p_and_1_minus_p():
    a = F.fee_polymarket("taker", 50.0, 0.20)
    b = F.fee_polymarket("taker", 50.0, 0.80)
    assert round(a, 9) == round(b, 9)


def test_polymarket_zero_at_boundary_prices():
    assert F.fee_polymarket("taker", 100.0, 0.0) == 0.0
    assert F.fee_polymarket("taker", 100.0, 1.0) == 0.0


def test_polymarket_bad_input_never_raises():
    assert F.fee_polymarket("taker", 100.0, None) == 0.0
    assert F.fee_polymarket("taker", "nonsense", 0.5) == 0.0


def test_polymarket_negative_size_never_credits_a_fee():
    assert F.fee_polymarket("taker", -100.0, 0.50) == 1.25


# ---------------------------------------------------------------------------
# expected_value_after_fees
# ---------------------------------------------------------------------------

def test_ev_kalshi_taker_golden():
    # p_true=0.6 (side="yes"), price=0.5 -> gross 0.10, fee $0.02 -> ev 0.08
    ev = F.expected_value_after_fees(0.6, 0.5, "yes", "kalshi", "taker")
    assert round(ev, 6) == 0.08


def test_ev_no_side_flips_p_true():
    # side="no": p_true = 1 - p_model = 0.4; price=0.3 -> gross 0.10, fee $0.02
    ev = F.expected_value_after_fees(0.6, 0.3, "no", "kalshi", "taker")
    assert round(ev, 6) == 0.08


def test_ev_fee_always_reduces_ev_across_the_grid():
    # The load-bearing invariant: net EV is never above gross EV, at any
    # price/side/venue/mode combination.
    for venue in ("kalshi", "polymarket"):
        for mode in ("maker", "taker"):
            for side in ("yes", "no"):
                for price in (0.01, 0.25, 0.5, 0.75, 0.99):
                    for pm in (0.05, 0.5, 0.95):
                        p_true = pm if side == "yes" else 1.0 - pm
                        gross = p_true - price
                        net = F.expected_value_after_fees(pm, price, side, venue, mode)
                        assert net <= gross + 1e-12


def test_ev_maker_beats_taker_ev_at_same_inputs():
    ev_taker = F.expected_value_after_fees(0.6, 0.5, "yes", "kalshi", "taker")
    ev_maker = F.expected_value_after_fees(0.6, 0.5, "yes", "kalshi", "maker")
    assert ev_maker > ev_taker


def test_ev_polymarket_maker_is_free_so_net_equals_gross():
    ev = F.expected_value_after_fees(0.6, 0.5, "yes", "polymarket", "maker")
    assert round(ev, 9) == round(0.6 - 0.5, 9)


def test_ev_unverified_venue_fails_closed():
    with pytest.raises(NotImplementedError):
        F.expected_value_after_fees(0.6, 0.5, "yes", "draftkings", "taker")


def test_ev_unverified_mode_fails_closed():
    with pytest.raises(NotImplementedError):
        F.expected_value_after_fees(0.6, 0.5, "yes", "kalshi", "midtaker")


def test_ev_unverified_side_fails_closed():
    with pytest.raises(NotImplementedError):
        F.expected_value_after_fees(0.6, 0.5, "sideways", "kalshi", "taker")
