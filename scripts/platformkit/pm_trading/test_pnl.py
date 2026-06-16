"""Per-file tests for pnl.py (paper blotter + ledger reuse).

Run: python -m pytest scripts/platformkit/pm_trading/test_pnl.py -q
"""
import pathlib
import sys
import tempfile

_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import pnl as P  # noqa: E402
from venues.base import Fill, Order, OrderBook, Level, OrderType, Side  # noqa: E402
from venues.paper import PaperVenue  # noqa: E402


def _blotter():
    d = tempfile.mkdtemp(prefix="pm_pnl_")
    return P.PnLBlotter(base_dir=d)


def test_record_fill_and_read():
    b = _blotter()
    b.record_fill(Fill("F1", "O1", "M", Side.BUY, 100, 0.50, 0.5, "t1"),
                  pred_ts="2026-06-16T00:00:00+00:00", strategy="arb")
    recs = b.read()
    assert len(recs) == 1 and recs[0]["kind"] == "fill"
    assert recs[0]["qty"] == 100 and recs[0]["pred_ts"].startswith("2026")


def test_settlement_pnl_long_win_and_loss():
    b = _blotter()
    # long 100 @0.40 -> resolves YES(1): +0.60 each = +60
    assert b.record_settlement("M", 1.0, 100, 0.40) == 60.0
    # long 100 @0.40 -> resolves NO(0): -0.40 each = -40
    assert b.record_settlement("M", 0.0, 100, 0.40) == -40.0


def test_settlement_pnl_short():
    b = _blotter()
    # short 100 @0.40 -> resolves NO(0): keep 0.40 each = +40
    assert b.record_settlement("M", 0.0, -100, 0.40) == 40.0
    # short 100 @0.40 -> resolves YES(1): -0.60 each = -60
    assert b.record_settlement("M", 1.0, -100, 0.40) == -60.0


def test_settle_from_venue():
    v = PaperVenue(initial_cash=10_000.0)
    v.set_book(OrderBook("M", asks=(Level(0.40, 1000),), bids=(Level(0.39, 1000),)))
    v.place_order(Order("M", Side.BUY, 100, OrderType.MARKET))  # long 100 @0.40
    b = _blotter()
    pnl = b.settle_from_venue(v, "M", resolution=1.0)
    assert pnl == round(100 * (1.0 - 0.40), 6)
    # no position -> zero
    assert b.settle_from_venue(v, "UNKNOWN", 1.0) == 0.0


def test_summary_nets_fees():
    b = _blotter()
    b.record_fill(Fill("F1", "O1", "M", Side.BUY, 100, 0.40, 2.0, "t1"))
    b.record_settlement("M", 1.0, 100, 0.40)  # +60 gross
    s = b.summary()
    assert s["n_fills"] == 1 and s["fees_paid"] == 2.0
    assert s["realized_settlement_pnl"] == 60.0
    assert s["net_paper_pnl"] == 58.0  # 60 - 2 fees
    assert s["n_settled_markets"] == 1 and s["n_open_markets"] == 0


def test_summary_tracks_open_markets():
    b = _blotter()
    b.record_fill(Fill("F1", "O1", "A", Side.BUY, 100, 0.40, 0.0, "t1"))
    b.record_fill(Fill("F2", "O2", "B", Side.BUY, 100, 0.40, 0.0, "t1"))
    b.record_settlement("A", 1.0, 100, 0.40)
    s = b.summary()
    assert s["n_open_markets"] == 1  # B not settled


def test_log_prediction_writes_real_ledger():
    from scripts.platformkit.ledger.ledger import read_ledger
    d = tempfile.mkdtemp(prefix="pm_led_")
    pid = P.log_prediction("nba", "ml", "BOS", "LAL", 0.61,
                           "2026-06-16T00:00:00+00:00", strategy="model_vs_market",
                           base_dir=d)
    assert isinstance(pid, str) and pid
    df = read_ledger(base_dir=d)
    assert len(df) == 1 and float(df.iloc[0]["calibrated_prob"]) == 0.61


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("PASS", fn.__name__)
    print("%d/%d green" % (len(fns), len(fns)))
