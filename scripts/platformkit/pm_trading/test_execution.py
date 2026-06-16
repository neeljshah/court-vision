"""Per-file tests for execution.py (best execution).

Run: python -m pytest scripts/platformkit/pm_trading/test_execution.py -q
"""
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import execution as E  # noqa: E402
from venues.base import Level, Order, OrderBook, OrderType, Side  # noqa: E402
from venues.paper import PaperVenue  # noqa: E402


def _venue(asks=(), bids=()):
    v = PaperVenue(initial_cash=100_000.0)
    v.set_book(OrderBook("M", bids=tuple(bids), asks=tuple(asks)))
    return v


def test_round_tick():
    ex = E.BestExecution(E.ExecConfig(tick=0.01))
    assert ex._round_tick(0.5049) == 0.50
    assert ex._round_tick(0.5051) == 0.51


def test_full_fill_single_level():
    v = _venue(asks=(Level(0.50, 1000),))
    ex = E.BestExecution(E.ExecConfig())
    r = ex.execute(v, Order("M", Side.BUY, 300, OrderType.MARKET))
    assert r.status == "FILLED" and r.filled_qty == 300
    assert r.avg_price == 0.50 and r.slippage == 0.0 and r.n_orders == 1


def test_splitting_walks_children():
    v = _venue(asks=(Level(0.50, 1000),))
    ex = E.BestExecution(E.ExecConfig(child_size=50))
    r = ex.execute(v, Order("M", Side.BUY, 200, OrderType.MARKET))
    assert r.filled_qty == 200 and r.n_orders == 4 and r.avg_price == 0.50


def test_requote_steps_toward_market_within_cap():
    # depth at 0.50/0.51/0.52 reachable; 0.55 is beyond the 0.02 cap
    v = _venue(asks=(Level(0.50, 100), Level(0.51, 100), Level(0.52, 100),
                     Level(0.55, 100)))
    ex = E.BestExecution(E.ExecConfig(max_slippage=0.02, max_requotes=3))
    r = ex.execute(v, Order("M", Side.BUY, 350, OrderType.MARKET))
    assert r.filled_qty == 300            # 100+100+100, 0.55 level skipped
    assert r.status == "PARTIAL"
    assert r.avg_price == round((100 * 0.50 + 100 * 0.51 + 100 * 0.52) / 300, 6)
    # never paid beyond the cap
    assert all(f.price <= 0.52 + 1e-9 for f in r.fills)


def test_slippage_cap_blocks_far_level():
    v = _venue(asks=(Level(0.50, 50), Level(0.70, 100)))
    ex = E.BestExecution(E.ExecConfig(max_slippage=0.02))
    r = ex.execute(v, Order("M", Side.BUY, 100, OrderType.MARKET))
    assert r.filled_qty == 50 and r.status == "PARTIAL"
    assert all(f.price <= 0.52 + 1e-9 for f in r.fills)  # 0.70 never touched


def test_sell_side_uses_bids_and_slippage():
    v = _venue(bids=(Level(0.50, 100), Level(0.49, 100)))
    ex = E.BestExecution(E.ExecConfig(max_slippage=0.02))
    r = ex.execute(v, Order("M", Side.SELL, 200, OrderType.MARKET))
    assert r.filled_qty == 200 and r.status == "FILLED"
    assert r.avg_price == round((100 * 0.50 + 100 * 0.49) / 200, 6)
    assert r.slippage == round(0.50 - r.avg_price, 6)  # ref is best bid 0.50


def test_min_size_reject():
    v = _venue(asks=(Level(0.50, 1000),))
    ex = E.BestExecution(E.ExecConfig(min_size=10))
    r = ex.execute(v, Order("M", Side.BUY, 5, OrderType.MARKET))
    assert r.status == "REJECTED" and r.filled_qty == 0


def test_no_book_no_ref_rejected():
    v = _venue()  # empty book
    ex = E.BestExecution(E.ExecConfig())
    r = ex.execute(v, Order("M", Side.BUY, 100, OrderType.MARKET))
    assert r.status == "REJECTED"


def test_limit_price_caps_below_slippage():
    # user limit 0.50 tighter than the slippage cap -> never pays 0.51
    v = _venue(asks=(Level(0.50, 50), Level(0.51, 100)))
    ex = E.BestExecution(E.ExecConfig(max_slippage=0.05))
    r = ex.execute(v, Order("M", Side.BUY, 150, OrderType.LIMIT, limit_price=0.50))
    assert r.filled_qty == 50 and all(f.price <= 0.50 + 1e-9 for f in r.fills)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("PASS", fn.__name__)
    print("%d/%d green" % (len(fns), len(fns)))
