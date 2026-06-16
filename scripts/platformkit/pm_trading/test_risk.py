"""Per-file tests for risk.py -- kill-switch + sizing + exposure caps.

The kill-switch tests come FIRST: no strategy may place size once halted.
Run: python -m pytest scripts/platformkit/pm_trading/test_risk.py -q
"""
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import risk as R  # noqa: E402
from venues.base import Level, MarketVenue, OrderBook, OrderType, Side  # noqa: E402
from venues.paper import PaperVenue  # noqa: E402


def _mk_book(mid, depth=1_000_000):
    return OrderBook("M", bids=(Level(round(mid - 0.005, 4), depth),),
                     asks=(Level(round(mid + 0.005, 4), depth),))


def _rm(cash=10_000.0, **cfg):
    v = PaperVenue(initial_cash=cash)
    v.set_book(_mk_book(0.50))
    c = R.RiskConfig(bankroll_start=cfg.pop("bankroll_start", 10_000.0), **cfg)
    return v, R.RiskManager(v, c)


# --------------------------------------------------------------------------
# KILL-SWITCH FIRST -- nothing places size once halted
# --------------------------------------------------------------------------
def test_drawdown_kill_switch_halts_and_blocks_all_sizing():
    # equity 8000 vs bankroll_start 10000 -> 20% drawdown > 15% -> trip
    v, rm = _rm(cash=8_000.0, bankroll_start=10_000.0)
    assert rm.check_kill_switch() is True
    assert rm.halted is True and "drawdown" in rm.halt_reason
    blocked = rm.approve("M", Side.BUY, fair_prob=0.99, price=0.50)
    assert blocked is None
    assert "halted" in rm.last_block_reason


def test_daily_loss_limit_trips_and_flattens():
    v, rm = _rm(cash=10_000.0, bankroll_start=10_000.0, daily_loss_limit=500.0)
    v.place_order  # noqa  (ensure attr exists)
    # build a 5000-contract long at 0.50, then mark drops to 0.40 -> -$500 day P&L
    from venues.base import Order
    v.place_order(Order("M", Side.BUY, 5_000, OrderType.MARKET))
    rm.start_day()                       # day reference = equity at 0.50 = 10000
    v.set_book(_mk_book(0.40))           # mark down 0.10 on 5000 contracts = -500
    assert rm.check_kill_switch() is True
    assert "daily loss" in rm.halt_reason
    assert v.get_positions().get("M").net_qty == 0   # flattened


def test_halt_then_reset_reopens():
    v, rm = _rm(cash=8_000.0, bankroll_start=10_000.0)
    assert rm.check_kill_switch() is True
    rm.reset()
    assert rm.halted is False
    # now solvent again (no drawdown vs a fresh start) -> sizing allowed
    v2, rm2 = _rm(cash=10_000.0, bankroll_start=10_000.0)
    assert rm2.approve("M", Side.BUY, 0.60, 0.50) is not None


def test_flatten_closes_all_positions():
    from venues.base import Order
    v, rm = _rm()
    v.place_order(Order("M", Side.BUY, 100, OrderType.MARKET))
    assert v.get_positions()["M"].net_qty == 100
    n = rm.flatten()
    assert n == 1 and v.get_positions()["M"].net_qty == 0


# --------------------------------------------------------------------------
# Kelly sizing
# --------------------------------------------------------------------------
def test_kelly_binary_buy_positive_edge():
    f = R.kelly_fraction_binary(0.60, 0.50, Side.BUY)  # f_full .2 * .25
    assert abs(f - 0.05) < 1e-9


def test_kelly_binary_sell_positive_edge():
    f = R.kelly_fraction_binary(0.40, 0.50, Side.SELL)  # (.5-.4)/.5=.2 *.25
    assert abs(f - 0.05) < 1e-9


def test_kelly_zero_when_no_edge():
    assert R.kelly_fraction_binary(0.50, 0.50, Side.BUY) == 0.0
    assert R.kelly_fraction_binary(0.40, 0.50, Side.BUY) == 0.0   # buying overpriced
    assert R.kelly_fraction_binary(0.60, 0.50, Side.SELL) == 0.0  # selling underpriced


def test_kelly_corr_haircut_reduces_size():
    base = R.kelly_fraction_binary(0.60, 0.50, Side.BUY, corr=0.0)
    half = R.kelly_fraction_binary(0.60, 0.50, Side.BUY, corr=0.5)
    assert abs(half - base * 0.5) < 1e-9


def test_kelly_never_exceeds_cap():
    f = R.kelly_fraction_binary(0.999, 0.001, Side.BUY, kelly_fraction=5.0)
    assert f <= R.KELLY_PCT_MAX + 1e-12


# --------------------------------------------------------------------------
# Approval gate: sizing + exposure caps
# --------------------------------------------------------------------------
def test_approve_sizes_by_kelly():
    v, rm = _rm()
    o = rm.approve("M", Side.BUY, 0.60, 0.50)
    # frac .05 * 10000 / risk .50 = 1000 contracts
    assert o is not None and o.qty == 1000


def test_market_exposure_cap_downsizes():
    v, rm = _rm(max_market_exposure=100.0)
    o = rm.approve("M", Side.BUY, 0.60, 0.50)
    assert o.qty == 200  # floor(100 / 0.50)
    assert "market" in rm.last_block_reason


def test_total_exposure_cap_downsizes():
    v, rm = _rm(max_total_exposure=50.0)
    o = rm.approve("M", Side.BUY, 0.60, 0.50)
    assert o.qty == 100  # floor(50 / 0.50)
    assert "total" in rm.last_block_reason


def test_event_exposure_cap_downsizes():
    from venues.base import Order
    v, rm = _rm(max_event_exposure=600.0)
    # existing 1000-contract long in market A @0.50 -> $500 exposure, tagged event E
    v.set_book(OrderBook("A", bids=(Level(0.50, 10**6),), asks=(Level(0.50, 10**6),)))
    v.place_order(Order("A", Side.BUY, 1000, OrderType.MARKET))  # fills @0.50 -> $500
    rm._market_event["A"] = "E"
    v.set_book(_mk_book(0.50))  # for market M pricing
    o = rm.approve("M", Side.BUY, 0.60, 0.50, event_id="E")
    assert o.qty == 200  # headroom (600-500)=100 / 0.50
    assert "event" in rm.last_block_reason


def test_approve_blocked_when_no_edge():
    v, rm = _rm()
    assert rm.approve("M", Side.BUY, 0.50, 0.50) is None
    assert "edge" in rm.last_block_reason


def test_live_venue_blocked_when_disabled():
    class LiveVenue(PaperVenue):
        def is_live(self):
            return True
    v = LiveVenue(initial_cash=10_000.0)
    v.set_book(_mk_book(0.50))
    rm = R.RiskManager(v, R.RiskConfig(bankroll_start=10_000.0, enabled=False))
    assert rm.approve("M", Side.BUY, 0.60, 0.50) is None
    assert "live trading disabled" in rm.last_block_reason
    # even cfg.enabled True stays blocked while the GLOBAL flag is OFF (default)
    rm2 = R.RiskManager(v, R.RiskConfig(bankroll_start=10_000.0, enabled=True))
    assert rm2.approve("M", Side.BUY, 0.60, 0.50) is None


def test_paper_venue_allowed():
    v, rm = _rm()
    assert v.is_live() is False
    assert rm.approve("M", Side.BUY, 0.60, 0.50) is not None


# --------------------------------------------------------------------------
# cap_quantity: non-Kelly sizing path (arb / market-making quotes)
# --------------------------------------------------------------------------
def test_cap_quantity_passes_through_under_caps():
    v, rm = _rm()
    assert rm.cap_quantity("M", Side.BUY, 0.50, 300) == 300


def test_cap_quantity_trims_to_market_cap():
    v, rm = _rm(max_market_exposure=100.0)
    assert rm.cap_quantity("M", Side.BUY, 0.50, 1000) == 200  # 100/0.50
    assert "market" in rm.last_block_reason


def test_cap_quantity_zero_when_halted():
    v, rm = _rm(cash=8_000.0, bankroll_start=10_000.0)  # drawdown trip
    assert rm.cap_quantity("M", Side.BUY, 0.50, 300) == 0
    assert "halted" in rm.last_block_reason


def test_cap_quantity_zero_for_nonpositive_want():
    v, rm = _rm()
    assert rm.cap_quantity("M", Side.BUY, 0.50, 0) == 0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("PASS", fn.__name__)
    print("%d/%d green" % (len(fns), len(fns)))
