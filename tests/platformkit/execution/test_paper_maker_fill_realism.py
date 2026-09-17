"""Paper maker: the fee must carry price information and a fill must be a CROSS.

Audit 2026-09-17:
  defect #5 -- fee_kalshi_maker(1.0, p) ceils to exactly $0.01 at every price,
    and the dollar result was stored in a field named ``_units``.
  defect #6 -- the fill book was collapsed to a point at the mid
    ({"best_bid": home, "best_ask": home}), so a resting quote filled the moment
    the mid TOUCHED its price. Adverse selection was impossible by construction.

Run: python -m pytest tests/platformkit/execution/test_paper_maker_fill_realism.py -q
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scripts.platformkit.execution import paper_maker as pm
from scripts.platformkit.execution.paper_maker import PaperMakerAdapter

_NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)
_TICK = {"ticker": "KXTEST", "tick_p50_sec": 10.0}


def _quote(side="home", fair=0.65):
    return PaperMakerAdapter().quote("mlb", "401860100", side, fair, units={},
                                     tick=dict(_TICK), now=_NOW)


def _advance(quote, tick, after_s=1):
    return PaperMakerAdapter().advance({"maker_quote": quote, "status": "resting"},
                                       tick, now=_NOW + timedelta(seconds=after_s))


# -- defect #5: fee ---------------------------------------------------------

def test_fee_is_reported_in_dollars_and_per_contract_units():
    q = _quote()
    assert q["maker_fee_dollars"] > 0.0
    assert q["maker_fee_contracts"] == 1
    # $1-payout contract: per-contract dollars ARE probability points, so the
    # legacy units field stays numerically identical for existing readers.
    assert q["maker_fee_units"] == q["maker_fee_dollars"] / q["maker_fee_contracts"]


def test_fee_is_charged_on_the_size_actually_quoted():
    # The fee call must take the order's own contract count, not a literal 1.0 --
    # Kalshi ceils ONCE per order, so the two differ as soon as qty moves.
    from scripts.platformkit.execution.venue_fees import fee_kalshi_maker
    assert fee_kalshi_maker(pm._QTY, 0.65) == _quote()["maker_fee_dollars"]
    assert fee_kalshi_maker(10.0, 0.50) < 10.0 * fee_kalshi_maker(1.0, 0.50)


# -- defect #6: fill realism ------------------------------------------------

def test_touching_the_quote_price_does_not_fill():
    q = _quote(fair=0.65)
    event = _advance(q, {"yes_home_prob": 0.65})
    assert event["status"] == "resting"
    assert event["reason"] == "no_through_trade"


def test_trading_through_the_quote_fills_at_our_own_price():
    q = _quote(fair=0.65)
    event = _advance(q, {"yes_home_prob": 0.60})
    assert event["status"] == "filled"
    # A maker gets no price improvement: the resting price IS the fill price.
    assert event["fill"]["price"] == 0.65
    assert event["fill"]["side"] == "yes"
    assert event["fill"]["fee_units"] == q["maker_fee_units"]


def test_quoted_book_on_the_tick_beats_the_assumed_half_spread():
    # A tick carrying a real book must be used verbatim: a 10c-wide book whose
    # offer sits ABOVE our quote cannot fill, even though its mid is below us.
    q = _quote(fair=0.65)
    event = _advance(q, {"yes_home_prob": 0.60, "best_bid": 0.57, "best_ask": 0.67})
    assert event["status"] == "resting"
    assert event["book_cents"] == [57, 67]


def test_away_side_fills_only_when_the_yes_bid_trades_through():
    q = _quote(side="away", fair=0.35)  # NO order at 35c
    assert _advance(q, {"yes_home_prob": 0.65})["status"] == "resting"   # touch
    filled = _advance(q, {"yes_home_prob": 0.70})
    assert filled["status"] == "filled"
    assert filled["fill"]["side"] == "no" and filled["fill"]["price"] == 0.35


def test_unpriced_tick_can_never_fill():
    event = _advance(_quote(), {"yes_home_prob": None})
    assert event["status"] == "resting" and event["reason"] == "no_observed_book"


def test_assumed_half_spread_is_the_preregistered_p50():
    # 200bp p50 spread (thresholds.py) -> 1 cent per side.
    assert pm._ASSUMED_HALF_SPREAD_CENTS == 1
    assert pm.observed_book({"yes_home_prob": 0.50}) == (49, 51)
    assert pm.trades_through("yes", 50, (49, 51)) is False
    assert pm.trades_through("yes", 52, (49, 51)) is True
    assert pm.trades_through("no", 50, (49, 51)) is False
    assert pm.trades_through("no", 52, (49, 51)) is True
