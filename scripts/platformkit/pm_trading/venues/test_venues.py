"""Per-file tests for the venue layer (PaperVenue + MarketVenue interface).

Run: python -m pytest scripts/platformkit/pm_trading/venues/test_venues.py -q
"""
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from base import (  # noqa: E402
    Balance, Level, MarketVenue, Order, OrderBook, OrderStatus, OrderType, Side,
)
from paper import PaperVenue  # noqa: E402


def _book():
    return OrderBook(
        market_id="NBA-BOS-YES",
        bids=(Level(0.58, 100), Level(0.57, 200)),
        asks=(Level(0.60, 50), Level(0.61, 100)),
        ts="t0",
    )


def _venue(cash=1000.0, fee_bps=0.0):
    v = PaperVenue(initial_cash=cash, fee_bps=fee_bps)
    v.set_book(_book())
    return v


def test_is_market_venue_and_not_live():
    v = _venue()
    assert isinstance(v, MarketVenue)
    assert v.name == "paper"
    assert v.is_live() is False


def test_orderbook_helpers():
    b = _book()
    assert b.best_bid().price == 0.58
    assert b.best_ask().price == 0.60
    assert b.mid() == 0.59
    assert b.spread() == 0.02
    empty = OrderBook(market_id="x")
    assert empty.mid() is None and empty.best_bid() is None


def test_market_buy_walks_levels():
    v = _venue()
    o = v.place_order(Order("NBA-BOS-YES", Side.BUY, 70, OrderType.MARKET))
    assert o.status == OrderStatus.FILLED
    assert o.filled_qty == 70
    # 50 @ 0.60 + 20 @ 0.61 -> avg
    assert o.avg_fill_price == round((50 * 0.60 + 20 * 0.61) / 70, 6)
    fills = v.get_fills()
    assert [f.qty for f in fills] == [50, 20]
    assert [f.price for f in fills] == [0.60, 0.61]


def test_cash_decreases_on_buy_increases_on_sell():
    v = _venue(cash=1000.0)
    v.place_order(Order("NBA-BOS-YES", Side.BUY, 50, OrderType.MARKET))
    assert v.get_balance().cash == round(1000.0 - 50 * 0.60, 6)
    v.place_order(Order("NBA-BOS-YES", Side.SELL, 50, OrderType.MARKET))
    # sold 50 into bid 0.58 -> cash back up
    assert v.get_balance().cash == round(1000.0 - 50 * 0.60 + 50 * 0.58, 6)


def test_position_avg_and_realized_pnl_on_reduce():
    v = _venue(cash=1000.0)
    v.place_order(Order("NBA-BOS-YES", Side.BUY, 70, OrderType.MARKET))  # avg above
    avg = v.get_positions()["NBA-BOS-YES"].avg_price
    v.place_order(Order("NBA-BOS-YES", Side.SELL, 50, OrderType.MARKET))  # sell 50 @0.58
    pos = v.get_positions()["NBA-BOS-YES"]
    assert pos.net_qty == 20
    assert pos.avg_price == avg  # unchanged on reduce
    assert pos.realized_pnl == round(50 * (0.58 - avg), 6)


def test_position_flip_resets_avg():
    v = PaperVenue(initial_cash=1000.0)
    v.set_book(OrderBook("M", bids=(Level(0.40, 100),), asks=(Level(0.50, 100),)))
    v.place_order(Order("M", Side.BUY, 30, OrderType.MARKET))   # long 30 @0.50
    v.place_order(Order("M", Side.SELL, 50, OrderType.MARKET))  # sell 50 @0.40 -> short 20
    pos = v.get_positions()["M"]
    assert pos.net_qty == -20
    assert pos.avg_price == 0.40           # new short opened at fill price
    assert pos.realized_pnl == round(30 * (0.40 - 0.50), 6)


def test_limit_partial_rests_reserves_and_cancels():
    v = _venue(cash=1000.0)
    # buy 80 @0.60 limit: only 50 @0.60 available, 0.61 doesn't cross -> 50 fill, 30 rest
    o = v.place_order(Order("NBA-BOS-YES", Side.BUY, 80, OrderType.LIMIT, limit_price=0.60))
    assert o.status == OrderStatus.PARTIAL and o.filled_qty == 50
    bal = v.get_balance()
    assert bal.reserved == round(30 * 0.60, 6)
    assert bal.available == round(bal.cash - bal.reserved, 6)
    assert v.cancel_order(o.order_id) is True
    assert v.get_balance().reserved == 0.0
    assert v.cancel_order(o.order_id) is False


def test_non_crossing_limit_does_not_fill():
    v = _venue()
    o = v.place_order(Order("NBA-BOS-YES", Side.BUY, 10, OrderType.LIMIT, limit_price=0.55))
    assert o.filled_qty == 0 and o.status == OrderStatus.NEW
    assert v.get_fills() == []


def test_book_depletes_across_orders():
    v = _venue()
    v.place_order(Order("NBA-BOS-YES", Side.BUY, 50, OrderType.MARKET))  # eats 0.60 level
    assert v.get_orderbook("NBA-BOS-YES").best_ask().price == 0.61
    o2 = v.place_order(Order("NBA-BOS-YES", Side.BUY, 10, OrderType.MARKET))
    assert o2.avg_fill_price == 0.61


def test_fee_applied():
    v = _venue(cash=1000.0, fee_bps=100.0)  # 1%
    v.place_order(Order("NBA-BOS-YES", Side.BUY, 50, OrderType.MARKET))
    f = v.get_fills()[0]
    assert f.fee == round(0.01 * 50 * 0.60, 6)
    assert v.get_balance().cash == round(1000.0 - 50 * 0.60 - f.fee, 6)


def test_rejects_bad_orders():
    v = _venue()
    assert v.place_order(Order("NBA-BOS-YES", Side.BUY, 0, OrderType.MARKET)).status == OrderStatus.REJECTED
    bad = v.place_order(Order("NBA-BOS-YES", Side.BUY, 10, OrderType.LIMIT, limit_price=1.5))
    assert bad.status == OrderStatus.REJECTED


def test_determinism_identical_runs():
    def run():
        v = _venue(cash=1000.0)
        v.place_order(Order("NBA-BOS-YES", Side.BUY, 70, OrderType.MARKET))
        v.place_order(Order("NBA-BOS-YES", Side.SELL, 30, OrderType.MARKET))
        return (round(v.get_balance().cash, 6),
                [(f.qty, f.price, f.fee) for f in v.get_fills()])
    assert run() == run()


def test_empty_market_price_is_none():
    v = PaperVenue()
    assert v.get_price("UNKNOWN") is None
    assert v.get_balance().available == 10_000.0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print("PASS", fn.__name__)
    print("%d/%d green" % (passed, len(fns)))
