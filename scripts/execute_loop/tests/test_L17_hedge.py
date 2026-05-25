"""test_L17_hedge.py — Tests for L17_hedge_calculator.py

Seven tests covering hedge math, recommendation logic, and edge cases.
No external dependencies — stdlib only + pytest.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# -- path setup ---------------------------------------------------------------
_TEST_DIR = Path(__file__).resolve().parent
_LOOP_DIR = _TEST_DIR.parent
_PROJECT_DIR = _LOOP_DIR.parents[1]
sys.path.insert(0, str(_PROJECT_DIR))
sys.path.insert(0, str(_LOOP_DIR))

import L17_hedge_calculator as L17  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_bet(
    bet_id: str = "BET001",
    side: str = "OVER",
    stake: float = 100.0,
    odds_american: float = -110.0,
    status: str = "OPEN",
) -> dict:
    return {
        "bet_id": bet_id,
        "side": side,
        "stake": stake,
        "odds_american": odds_american,
        "status": status,
    }


def _make_market(
    opposite_side: str = "UNDER",
    odds_american_opposite: float = 200.0,
    book: str = "DK",
) -> dict:
    return {
        "opposite_side": opposite_side,
        "odds_american_opposite": odds_american_opposite,
        "book": book,
    }


# ---------------------------------------------------------------------------
# Test 1: Full hedge math
# stake=100, original=-110 (dec=1.9091), opposite=+120 (dec=2.20)
# original_payout = 100 * 1.9091 = 190.91
# hedge_stake = 190.91 / 2.20 ≈ 86.78
# ---------------------------------------------------------------------------
def test_full_hedge_math():
    """Full hedge: stake=100@-110, opposite=+120 → stake_opposite ≈ 86.78."""
    stake_opp = L17.calculate_full_hedge(
        stake_original=100.0,
        odds_original=-110.0,
        current_odds_opposite=120.0,
    )

    dec_original = L17._american_to_decimal(-110.0)   # 1 + 100/110 ≈ 1.9091
    original_payout = 100.0 * dec_original
    dec_opposite = L17._american_to_decimal(120.0)     # 1 + 120/100 = 2.20
    expected = original_payout / dec_opposite

    assert stake_opp == pytest.approx(expected, abs=0.01)
    assert stake_opp == pytest.approx(86.78, abs=0.05)


# ---------------------------------------------------------------------------
# Test 2: recommend_hedge → hedge_full for profitable, high lock_ratio bet
# stake=100, original=-110 (dec≈1.909), opposite=+200 (dec=3.00)
# original_payout = 190.91
# full_hedge_stake = 190.91 / 3.00 ≈ 63.64
# net_original_wins = 190.91 - 100 - 63.64 = 27.27
# net_opp_wins = 63.64*(3-1) - 100 = 127.28 - 100 = 27.28
# locked_pnl ≈ 27.27
# max_win_original = 100*(1.909-1) = 90.91
# lock_ratio = 27.27/90.91 ≈ 0.30 → should be hedge_partial
# ---------------------------------------------------------------------------
def test_recommend_full_positive_pnl():
    """100@-110 opposite +200 → positive locked_pnl_min on full hedge, decision not no_hedge.

    For the partial path, locked_pnl_min can be negative (partial stake doesn't cover
    both legs), but locked_pnl_max must be positive (the original bet still wins cleanly).
    The full hedge itself always has pnl_min > 0 when lock_ratio > 0 — we verify that
    directly via calculate_full_hedge + _compute_pnl_bounds.
    """
    bet = _make_bet(stake=100.0, odds_american=-110.0)
    market = _make_market(odds_american_opposite=200.0, book="DK")

    rec = L17.recommend_hedge(bet, market, mode="full")

    assert rec is not None
    assert rec.decision in ("hedge_full", "hedge_partial")
    assert rec.hedge_book == "DK"
    assert rec.hedge_side == "UNDER"
    assert rec.original_bet_id == "BET001"

    # Verify the full-hedge path locks a positive PnL (both legs)
    stake_full = L17.calculate_full_hedge(100.0, -110.0, 200.0)
    dec_orig = L17._american_to_decimal(-110.0)
    dec_opp = L17._american_to_decimal(200.0)
    pnl_min, pnl_max = L17._compute_pnl_bounds(100.0, dec_orig, stake_full, dec_opp)
    assert pnl_min > 0, f"Full hedge pnl_min should be > 0, got {pnl_min}"


# ---------------------------------------------------------------------------
# Test 3: no_hedge when hedge locks negative PnL (opposite = -300, dec≈1.333)
# stake=100@-110, dec_original≈1.909, original_payout≈190.91
# full_hedge_stake = 190.91/1.333 ≈ 143.25
# net_original_wins = 190.91 - 100 - 143.25 = -52.34  → NEGATIVE
# ---------------------------------------------------------------------------
def test_no_hedge_negative_ev():
    """Opposite -300 (dec≈1.333) locks negative PnL → no_hedge, note='negative_ev'."""
    bet = _make_bet(stake=100.0, odds_american=-110.0)
    market = _make_market(odds_american_opposite=-300.0, book="FD")

    rec = L17.recommend_hedge(bet, market, mode="full")

    assert rec is not None
    assert rec.decision == "no_hedge"
    assert rec.note == "negative_ev"
    assert rec.locked_pnl_min < 0


# ---------------------------------------------------------------------------
# Test 4: partial hedge stake = full_hedge_stake * target_lock_pct
# ---------------------------------------------------------------------------
def test_partial_hedge_stake_fraction():
    """calculate_partial_hedge(target_lock_pct=0.5) == 0.5 * calculate_full_hedge(...)."""
    stake_full = L17.calculate_full_hedge(100.0, -110.0, 200.0)
    stake_partial = L17.calculate_partial_hedge(
        stake_original=100.0,
        odds_original=-110.0,
        current_odds_opposite=200.0,
        target_lock_pct=0.5,
    )
    assert stake_partial == pytest.approx(stake_full * 0.5, abs=0.01)


# ---------------------------------------------------------------------------
# Test 5: decimal_odds_opposite == 1.0 → ValueError
# ---------------------------------------------------------------------------
def test_decimal_odds_opposite_one_raises():
    """Calling calculate_full_hedge with odds that yield dec_opposite=1.0 raises ValueError."""
    # American odds of -inf would give dec=1.0 but we can't express that.
    # Instead, patch directly: any odds_american that yields dec<=1.0 is invalid.
    # odds_american = 0 isn't standard; use a mocked dec by passing an extreme negative value.
    # Actually: dec = 1 + 100/abs(neg) → as neg→∞ dec→1.0.
    # Simplest: just call _american_to_decimal and check, then test ValueError guard.

    # For the ValueError to fire from recommend_hedge we need dec_opposite <= 1.0.
    # Internally L17 converts American → decimal. The only way dec <= 1.0 is if
    # the decimal odds computation returns ≤ 1.0. We test the ValueError by calling
    # calculate_full_hedge with an extremely large negative number that still gives
    # dec > 1, so we patch _american_to_decimal for the opposite side via monkeypatching.
    # More cleanly: just verify the ValueError guard in calculate_full_hedge:
    original_fn = L17._american_to_decimal

    def _patched_to_decimal(odds):
        """Return 1.0 for the opposite side to trigger ValueError."""
        return 1.0

    L17._american_to_decimal = _patched_to_decimal
    try:
        with pytest.raises(ValueError, match="decimal_odds_opposite must be > 1.0"):
            L17.calculate_full_hedge(100.0, -110.0, 200.0)
    finally:
        L17._american_to_decimal = original_fn


# ---------------------------------------------------------------------------
# Test 6: status == "settled" → no_hedge, note="already_settled"
# ---------------------------------------------------------------------------
def test_settled_bet_no_hedge():
    """Settled bet immediately returns no_hedge with note='already_settled'."""
    bet = _make_bet(status="SETTLED")
    market = _make_market()

    rec = L17.recommend_hedge(bet, market)

    assert rec is not None
    assert rec.decision == "no_hedge"
    assert rec.note == "already_settled"
    assert rec.hedge_stake == 0.0


# ---------------------------------------------------------------------------
# Test 7: live_market missing opposite_side → returns None
# ---------------------------------------------------------------------------
def test_missing_opposite_side_returns_none():
    """live_market without 'opposite_side' key → recommend_hedge returns None."""
    bet = _make_bet()
    bad_market = {"odds_american_opposite": 200.0, "book": "DK"}  # missing opposite_side

    rec = L17.recommend_hedge(bet, bad_market)
    assert rec is None


# ---------------------------------------------------------------------------
# Bonus: live_market=None also returns None
# ---------------------------------------------------------------------------
def test_none_market_returns_none():
    """live_market=None → recommend_hedge returns None."""
    bet = _make_bet()
    rec = L17.recommend_hedge(bet, None)
    assert rec is None


# ---------------------------------------------------------------------------
# Bonus: lock_ratio > 0.5 triggers hedge_full
# Construct a scenario where locking in profit is very efficient.
# stake=100@-110, opposite=-105 (dec≈1.952)
# original_payout = 190.91
# full_hedge_stake = 190.91/1.952 ≈ 97.80
# net_original_wins = 190.91 - 100 - 97.80 = -6.89  → negative → no_hedge
#
# Use opposite = +150 (dec=2.50) for a clean test:
# original_payout = 100*1.909 = 190.9
# full_hedge_stake = 190.9/2.50 = 76.36
# net_original_wins = 190.9 - 100 - 76.36 = 14.54
# max_win_original = 100*(1.909-1) = 90.9
# lock_ratio = 14.54/90.9 ≈ 0.160 → hedge_partial
#
# To force hedge_full we need lock_ratio > 0.5:
# Use original = +300 (dec=4.0), opposite = +130 (dec=2.30)
# original_payout = 100*4.0 = 400
# full_hedge_stake = 400/2.30 ≈ 173.91
# net_original_wins = 400 - 100 - 173.91 = 126.09
# max_win_original = 100*(4-1) = 300
# lock_ratio = 126.09/300 ≈ 0.420 → still partial
#
# original=+500 (dec=6.0), opposite=+120 (dec=2.20):
# payout = 600, hedge = 600/2.20 = 272.73
# net_orig_wins = 600 - 100 - 272.73 = 227.27
# max_win = 500
# lock_ratio = 227.27/500 = 0.455 → partial
#
# original=+500, opposite=+110 (dec=2.10):
# payout=600, hedge=600/2.10=285.71
# net=600-100-285.71=214.29, max=500, ratio=0.429 → still partial
#
# original=+1000 (dec=11.0), opposite=+120 (dec=2.20):
# payout=1100, hedge=1100/2.20=500
# net=1100-100-500=500, max=1000, ratio=0.5 → still not > 0.5
#
# original=+1000, opposite=+115 (dec=2.15):
# payout=1100, hedge=1100/2.15≈511.63
# net=1100-100-511.63=488.37, max=1000, ratio=0.488 → partial
#
# original=+2000 (dec=21.0), opposite=+120 (dec=2.20):
# payout=2100, hedge=2100/2.20=954.55
# net=2100-100-954.55=1045.45, max=2000, ratio=0.523 → hedge_full!
# ---------------------------------------------------------------------------
def test_high_lock_ratio_triggers_hedge_full():
    """High lock_ratio (>0.5) → decision='hedge_full'."""
    # original=+2000 (dec=21.0), opposite=+120 (dec=2.20)
    bet = _make_bet(stake=100.0, odds_american=2000.0)
    market = _make_market(odds_american_opposite=120.0)

    rec = L17.recommend_hedge(bet, market)

    assert rec is not None
    assert rec.decision == "hedge_full"
    assert rec.locked_pnl_min > 0
