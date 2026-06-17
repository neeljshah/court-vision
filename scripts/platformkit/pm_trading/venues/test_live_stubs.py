"""Per-file tests for live_stubs.py (env-gated real venue stubs).

Run: python -m pytest scripts/platformkit/pm_trading/venues/test_live_stubs.py -q
"""
import os
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from base import Order, OrderType, Side  # noqa: E402
from live_stubs import KalshiVenue, PolymarketVenue, _LiveVenueStub  # noqa: E402


def test_is_live_and_not_wired():
    for V in (KalshiVenue, PolymarketVenue):
        v = V()
        assert v.is_live() is True
        assert v.wired() is False
        assert v.name in ("kalshi", "polymarket")


def test_credentials_presence_only_returns_bool_not_secret():
    saved = {k: os.environ.get(k) for k in KalshiVenue.ENV_KEYS}
    try:
        for k in KalshiVenue.ENV_KEYS:
            os.environ.pop(k, None)
        v = KalshiVenue()
        assert v.has_credentials() is False
        assert set(v.missing_credentials()) == set(KalshiVenue.ENV_KEYS)
        # set fake presence -> bool True, never the value
        for k in KalshiVenue.ENV_KEYS:
            os.environ[k] = "PRESENT"
        v2 = KalshiVenue()
        assert v2.has_credentials() is True
        assert isinstance(v2.has_credentials(), bool)
        assert v2.missing_credentials() == []
    finally:
        for k, val in saved.items():
            if val is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = val


def test_place_order_hard_refuses():
    v = KalshiVenue()
    try:
        v.place_order(Order("M", Side.BUY, 100, OrderType.MARKET))
        assert False, "place_order must refuse"
    except RuntimeError as e:
        assert "No real order was sent" in str(e)


def test_cancel_order_refuses():
    v = PolymarketVenue()
    try:
        v.cancel_order("X")
        assert False
    except RuntimeError:
        pass


def test_read_methods_safe_empties():
    v = PolymarketVenue()
    assert v.get_orderbook("M").market_id == "M"
    assert v.get_price("M") is None
    assert v.get_positions() == {}
    assert v.get_balance().cash == 0.0
    assert v.get_fills() == []


def test_risk_blocks_live_stub_while_enabled_off():
    # the stub plugs into risk.py and is blocked by the global ENABLED flag
    sys.path.insert(0, str(_HERE.parent))
    import risk as R  # noqa: E402
    v = KalshiVenue()
    # bankroll_start=0 disables the drawdown guard (the unwired stub reports
    # cash 0.0); this isolates the live-ENABLED gate we want to assert.
    rm = R.RiskManager(v, R.RiskConfig(bankroll_start=0.0, enabled=True))
    assert rm.approve("M", Side.BUY, 0.62, 0.50) is None
    assert "live trading disabled" in rm.last_block_reason


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("PASS", fn.__name__)
    print("%d/%d green" % (len(fns), len(fns)))
