"""Per-file tests for run_trader.py (the paper daemon).

Run: python -m pytest scripts/platformkit/pm_trading/test_run_trader.py -q
"""
import pathlib
import sys
import tempfile

_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import run_trader as RT  # noqa: E402
import risk as R  # noqa: E402
from pnl import PnLBlotter  # noqa: E402
from venues.base import Level, OrderBook  # noqa: E402
from venues.paper import PaperVenue  # noqa: E402


def _book(mid, depth=10**6, m="M"):
    return OrderBook(m, bids=(Level(round(mid - 0.005, 4), depth),),
                     asks=(Level(round(mid + 0.005, 4), depth),))


def _blotter():
    return PnLBlotter(base_dir=tempfile.mkdtemp(prefix="pm_rt_"))


def _trader(cash=10_000.0, **cfgkw):
    v = PaperVenue(initial_cash=cash)
    v.set_book(_book(0.50))
    rm = R.RiskManager(v, R.RiskConfig(bankroll_start=10_000.0))
    cfg = RT.TraderConfig(**cfgkw)
    return v, rm, RT.PaperTrader(v, rm, _blotter(), cfg)


def test_banner_is_loud_and_paper():
    _, _, t = _trader()
    b = t.banner()
    assert "PAPER" in b and "WIRE KEYS" in b and "HUMAN-CONFIRM" in b
    assert t.venue.is_live() is False


def test_gate_open_produces_fills():
    v, rm, t = _trader(gate_verdict="BEATS_CLOSE", min_edge_bps=50.0)
    states = [RT.MarketState("M", fair_prob=0.62, devig_prob=0.60)]
    fills = t.step(states, pred_ts="2026-06-16T00:00:00+00:00")
    assert len(fills) > 0
    assert t.blotter.summary()["n_fills"] == len(fills)


def test_gate_closed_no_fills():
    v, rm, t = _trader(gate_verdict="MATCHES_CLOSE")
    states = [RT.MarketState("M", fair_prob=0.62, devig_prob=0.60)]
    assert t.step(states) == []
    assert t.blotter.summary()["n_fills"] == 0


def test_kill_switch_halts_daemon():
    v = PaperVenue(initial_cash=8_000.0)  # 20% drawdown vs 10k start
    v.set_book(_book(0.50))
    rm = R.RiskManager(v, R.RiskConfig(bankroll_start=10_000.0))
    t = RT.PaperTrader(v, rm, _blotter(),
                       RT.TraderConfig(gate_verdict="BEATS_CLOSE"))
    states = [RT.MarketState("M", fair_prob=0.62)]
    assert t.step(states) == [] and t.halted is True


def test_run_over_feed_accumulates_and_reports():
    v, rm, t = _trader(gate_verdict="BEATS_CLOSE", min_edge_bps=50.0)
    feed = [([RT.MarketState("M", 0.62, 0.60)], "t%d" % i) for i in range(3)]
    summary = t.run(feed, verbose=False)
    assert summary["ticks"] == 3
    assert summary["total_fills_this_run"] > 0
    assert summary["halted"] is False


def test_market_maker_places_resting_quotes():
    v, rm, t = _trader(use_model_vs_market=False, use_market_maker=True)
    # quotes rest (don't cross the 0.50 book) -> recorded as fills only if they
    # cross; here half_spread keeps them passive, so no immediate fills.
    states = [RT.MarketState("M", fair_prob=0.50, half_spread=0.02)]
    t.step(states)
    # the daemon ran without error and stayed solvent
    assert t.halted is False


def test_arb_two_venue_run():
    va = PaperVenue(initial_cash=10_000.0)
    vb = PaperVenue(initial_cash=10_000.0)
    va.set_book(OrderBook("M", bids=(Level(0.38, 500),), asks=(Level(0.40, 500),)))
    vb.set_book(OrderBook("M", bids=(Level(0.45, 500),), asks=(Level(0.47, 500),)))
    ra = R.RiskManager(va, R.RiskConfig(bankroll_start=10_000.0))
    rb = R.RiskManager(vb, R.RiskConfig(bankroll_start=10_000.0))
    t = RT.PaperTrader(va, ra, _blotter(),
                       RT.TraderConfig(use_model_vs_market=False, use_arb=True),
                       venue_b=vb, risk_b=rb)
    fills = t.step([RT.MarketState("M", fair_prob=0.42)], pred_ts="t0")
    # both legs (buy on A, sell on B) fill
    assert len(fills) == 2


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("PASS", fn.__name__)
    print("%d/%d green" % (len(fns), len(fns)))
