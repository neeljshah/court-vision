"""Network smoke tests for KalshiClient — read-only public endpoints.

Skipped when env var SKIP_NETWORK_TESTS is set.
Run only the network suite: pytest -m network predmarkets/tests/test_kalshi_smoke.py
"""

from __future__ import annotations

import os

import pytest

from predmarkets.kalshi_client import KalshiClient, KalshiClientError

pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(
        bool(os.environ.get("SKIP_NETWORK_TESTS")),
        reason="SKIP_NETWORK_TESTS set",
    ),
]


@pytest.fixture(scope="module")
def client() -> KalshiClient:
    return KalshiClient(rps=5.0, timeout=15.0)


def test_get_events_open_returns_rows(client: KalshiClient) -> None:
    events = client.get_events(status="open", limit=20)
    assert isinstance(events, list)
    assert len(events) >= 5, f"expected >=5 open events, got {len(events)}"
    assert all(isinstance(e, dict) for e in events)
    assert "event_ticker" in events[0]


def test_get_markets_open_limit_five(client: KalshiClient) -> None:
    markets = client.get_markets(status="open", limit=5)
    assert isinstance(markets, list)
    assert len(markets) == 5
    for m in markets:
        assert isinstance(m, dict)
        assert "ticker" in m and m["ticker"]


def test_get_orderbook_first_open_market(client: KalshiClient) -> None:
    markets = client.get_markets(status="open", limit=5)
    assert markets, "no open markets to test orderbook against"
    ticker = markets[0]["ticker"]
    ob = client.get_orderbook(ticker)
    assert isinstance(ob, dict)
    assert "yes" in ob and "no" in ob
    assert isinstance(ob["yes"], list) and isinstance(ob["no"], list)


def test_get_settlements_recent(client: KalshiClient) -> None:
    rows = client.get_settlements(lookback_days=30, limit=200)
    assert isinstance(rows, list)
    assert len(rows) >= 1, "expected at least one settled market in last 30 days"
    sample = rows[0]
    for key in ("ticker", "event_ticker", "result", "close_time"):
        assert key in sample


def test_exclude_multivariate_returns_clean_markets(client: KalshiClient) -> None:
    """Default /markets ordering returns parlay (MVE) markets; exclude_multivariate
    must walk events with nested markets and return only standard binary markets."""
    clean = client.get_markets(status="open", limit=10, exclude_multivariate=True)
    assert len(clean) >= 5, f"expected >=5 non-MVE markets, got {len(clean)}"
    assert all(m.get("is_multivariate") is False for m in clean)
    assert all(m.get("yes_bid") is not None or m.get("yes_ask") is not None for m in clean), \
        "normalized markets should have at least one of yes_bid / yes_ask populated"


def test_orderbook_fp_dollars_schema(client: KalshiClient) -> None:
    """Kalshi serves the newer orderbook_fp schema with yes_dollars/no_dollars
    string ladders for fractional pricing. Confirm the client handles it."""
    # KXWARMING-50 is a high-liquidity, long-tenured market reliably present
    clean = client.get_markets(status="open", limit=10, exclude_multivariate=True)
    target = next((m["ticker"] for m in clean if m.get("yes_bid") and m.get("yes_ask")), None)
    assert target, "no clean market with both yes_bid and yes_ask available"
    ob = client.get_orderbook(target)
    assert ob["yes"] or ob["no"], f"orderbook for {target} should have entries on at least one side"
    if ob["yes"]:
        p, q = ob["yes"][0]
        assert 0.0 < p < 1.0, f"yes price out of range: {p}"
        assert q > 0
