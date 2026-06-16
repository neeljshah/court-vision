"""Per-file tests for the three strategies.

Run: python -m pytest scripts/platformkit/pm_trading/strategies/test_strategies.py -q
"""
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
_PKG = _HERE.parent
for _p in (str(_PKG), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import risk as R  # noqa: E402
from venues.base import Level, Order, OrderBook, OrderType, Side  # noqa: E402
from venues.paper import PaperVenue  # noqa: E402
from edge_signal import build_signal  # noqa: E402

import cross_market_arb as ARB  # noqa: E402
import market_maker as MM  # noqa: E402
import model_vs_market as MVM  # noqa: E402


def _book(mid, depth=10**6, m="M"):
    return OrderBook(m, bids=(Level(round(mid - 0.005, 4), depth),),
                     asks=(Level(round(mid + 0.005, 4), depth),))


def _rm(cash=10_000.0, **cfg):
    v = PaperVenue(initial_cash=cash)
    v.set_book(_book(0.50))
    c = R.RiskConfig(bankroll_start=cfg.pop("bankroll_start", 10_000.0), **cfg)
    return v, R.RiskManager(v, c)


# -- model_vs_market (gate-gated) -------------------------------------------
def test_mvm_gate_closed_emits_nothing():
    v, rm = _rm()
    sig = build_signal("M", 0.62, 0.50, devig_prob=0.60)
    for verdict in ("MATCHES_CLOSE", "BEHIND", "anything"):
        strat = MVM.ModelVsMarket(rm, verdict)
        assert strat.evaluate([sig]) == []
        assert "gate verdict" in strat.last_skip_reason


def test_mvm_gate_open_emits_sized_order():
    v, rm = _rm()
    sig = build_signal("M", 0.62, 0.50, devig_prob=0.60)
    strat = MVM.ModelVsMarket(rm, "BEATS_CLOSE")
    intents = strat.evaluate([sig])
    assert len(intents) == 1
    assert intents[0].order.side == Side.BUY and intents[0].order.qty > 0
    assert intents[0].venue is v


def test_mvm_skips_when_model_fights_consensus():
    v, rm = _rm()
    sig = build_signal("M", 0.62, 0.50, devig_prob=0.40)  # book leans other way
    strat = MVM.ModelVsMarket(rm, "BEATS_CLOSE", require_consensus=True)
    assert strat.evaluate([sig]) == []
    # but allowed when consensus check is off
    strat2 = MVM.ModelVsMarket(rm, "BEATS_CLOSE", require_consensus=False)
    assert len(strat2.evaluate([sig])) == 1


def test_mvm_halted_emits_nothing():
    v, rm = _rm(cash=8_000.0, bankroll_start=10_000.0)  # drawdown -> halt
    sig = build_signal("M", 0.62, 0.50, devig_prob=0.60)
    strat = MVM.ModelVsMarket(rm, "BEATS_CLOSE")
    assert strat.evaluate([sig]) == []


# -- cross_market_arb -------------------------------------------------------
def _two_venues(ask_a, bid_b, depth=500):
    va = PaperVenue(initial_cash=10_000.0)
    vb = PaperVenue(initial_cash=10_000.0)
    va.set_book(OrderBook("M", bids=(Level(ask_a - 0.02, depth),),
                          asks=(Level(ask_a, depth),)))
    vb.set_book(OrderBook("M", bids=(Level(bid_b, depth),),
                          asks=(Level(bid_b + 0.02, depth),)))
    ra = R.RiskManager(va, R.RiskConfig(bankroll_start=10_000.0))
    rb = R.RiskManager(vb, R.RiskConfig(bankroll_start=10_000.0))
    return va, vb, ra, rb


def test_arb_detected_and_legs_balanced():
    va, vb, ra, rb = _two_venues(ask_a=0.40, bid_b=0.45)
    strat = ARB.CrossMarketArb(min_edge=0.0)
    intents = strat.evaluate(va, vb, "M", ra, rb)
    assert len(intents) == 2
    buy, sell = intents
    assert buy.order.side == Side.BUY and buy.venue is va and buy.order.limit_price == 0.40
    assert sell.order.side == Side.SELL and sell.venue is vb and sell.order.limit_price == 0.45
    assert buy.order.qty == sell.order.qty == 500
    assert abs(strat.last_opportunities[0].locked_edge - 0.05) < 1e-9


def test_no_arb_when_books_aligned():
    va, vb, ra, rb = _two_venues(ask_a=0.505, bid_b=0.495)  # bid < ask both ways
    strat = ARB.CrossMarketArb(min_edge=0.0)
    assert strat.evaluate(va, vb, "M", ra, rb) == []


def test_arb_capped_by_exposure():
    va, vb, ra, rb = _two_venues(ask_a=0.40, bid_b=0.45)
    ra.cfg.max_market_exposure = 40.0   # BUY leg rpc 0.40 -> floor(40/0.4)=100
    strat = ARB.CrossMarketArb(min_edge=0.0)
    intents = strat.evaluate(va, vb, "M", ra, rb)
    assert intents[0].order.qty == 100 and intents[1].order.qty == 100


# -- market_maker -----------------------------------------------------------
def test_mm_emits_two_sided_quotes():
    v, rm = _rm()
    strat = MM.MarketMaker(rm, base_qty=100, inventory_band=500)
    intents = strat.evaluate("M", fair_prob=0.50, half_spread=0.02)
    assert len(intents) == 2
    bid = [i for i in intents if i.order.side == Side.BUY][0]
    ask = [i for i in intents if i.order.side == Side.SELL][0]
    assert bid.order.limit_price == 0.48 and ask.order.limit_price == 0.52
    assert bid.order.qty == 100 and ask.order.qty == 100


def test_mm_inventory_skew_when_long():
    v, rm = _rm()
    v.place_order(Order("M", Side.BUY, 250, OrderType.MARKET))  # net +250
    strat = MM.MarketMaker(rm, base_qty=100, inventory_band=500)
    intents = strat.evaluate("M", fair_prob=0.50, half_spread=0.02)
    bid = [i for i in intents if i.order.side == Side.BUY][0]
    ask = [i for i in intents if i.order.side == Side.SELL][0]
    assert bid.order.qty == 50 and ask.order.qty == 150  # skew 0.5 -> smaller bid


def test_mm_halted_no_quotes():
    v, rm = _rm(cash=8_000.0, bankroll_start=10_000.0)
    strat = MM.MarketMaker(rm)
    assert strat.evaluate("M", 0.50, 0.02) == []


def test_mm_crossed_spread_no_quotes():
    v, rm = _rm()
    strat = MM.MarketMaker(rm)
    assert strat.evaluate("M", 0.50, 0.0) == []  # bid == ask


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("PASS", fn.__name__)
    print("%d/%d green" % (len(fns), len(fns)))
