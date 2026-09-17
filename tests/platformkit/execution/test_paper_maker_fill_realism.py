"""Paper maker: the fee must carry price information and a fill must be a CROSS.

Audit 2026-09-17:
  defect #5 -- the dollar result of fee_kalshi_maker was stored in a field named
    ``_units``, and the call hardcoded a contract count of 1.0. NOT closed: at
    qty=1 the once-per-order cent ceiling still makes the charged fee exactly
    $0.01 at every price. That is asserted below, not glossed over.
  defect #6 -- the fill book was collapsed to a point at the mid
    ({"best_bid": home, "best_ask": home}), so a resting quote filled the moment
    the mid TOUCHED its price. Adverse selection was impossible by construction.

Run: python -m pytest tests/platformkit/execution/test_paper_maker_fill_realism.py -q
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

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


def test_at_qty_one_the_charged_fee_is_price_invariant():
    # HONEST LIMIT, asserted rather than glossed: the once-per-order cent
    # ceiling makes the qty=1 maker fee exactly $0.01 at every price. This
    # commit did NOT change that number; it changed how the fee is computed
    # and how it is reported.
    assert {pm._maker_fee(1, c) for c in range(1, 100)} == {0.01}
    assert _quote(fair=0.05)["maker_fee_dollars"] == 0.01
    assert _quote(fair=0.50)["maker_fee_dollars"] == 0.01
    assert _quote(fair=0.95)["maker_fee_dollars"] == 0.01


@pytest.mark.parametrize("qty,cents", [(10, 50), (10, 65), (40, 50), (3, 20)])
def test_fee_is_charged_on_the_size_actually_quoted(monkeypatch, qty, cents):
    # The fee must come from the ORDER's contract count, not a literal 1.0.
    # Kalshi ceils ONCE per order, so beyond qty=1 the true fee is strictly
    # cheaper than qty x the single-contract fee -- charging per contract would
    # overstate cost by up to a cent each.
    from scripts.platformkit.execution.venue_fees import fee_kalshi_maker
    assert pm._maker_fee(qty, cents) == fee_kalshi_maker(qty, cents / 100.0)
    assert pm._maker_fee(qty, cents) < qty * pm._maker_fee(1, cents)

    monkeypatch.setattr(pm, "_QTY", qty)
    q = _quote(fair=cents / 100.0)
    assert q["maker_fee_contracts"] == qty
    assert q["maker_fee_dollars"] == fee_kalshi_maker(qty, cents / 100.0)
    assert q["maker_fee_units"] == q["maker_fee_dollars"] / qty
    assert q["order"].qty == qty          # the quoted size and the fee agree


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
