"""Network smoke tests for PMClient — skipped when SKIP_NETWORK_TESTS is set."""

from __future__ import annotations

import os

import pytest

from predmarkets.pm_client import PMClient, PMClientError, PMGeoBlockedError

pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(
        bool(os.environ.get("SKIP_NETWORK_TESTS")),
        reason="SKIP_NETWORK_TESTS is set",
    ),
]

_REQUIRED_KEYS = ("id", "question", "conditionId")


@pytest.fixture(scope="module")
def client() -> PMClient:
    return PMClient()


def _skip_if_geoblocked(exc: Exception) -> None:
    if isinstance(exc, PMGeoBlockedError):
        pytest.skip(f"geo-blocked: {exc}")


def test_list_markets_returns_dicts(client: PMClient) -> None:
    try:
        rows = client.list_markets(limit=10)
    except PMGeoBlockedError as exc:
        _skip_if_geoblocked(exc)
        return
    assert isinstance(rows, list)
    assert len(rows) >= 5
    for r in rows:
        assert isinstance(r, dict)
        for k in _REQUIRED_KEYS:
            assert k in r, f"missing key {k} in market row"


def test_get_market_roundtrip(client: PMClient) -> None:
    try:
        rows = client.list_markets(limit=5)
        assert rows, "no markets returned"
        market_id = str(rows[0]["id"])
        single = client.get_market(market_id)
    except PMGeoBlockedError as exc:
        _skip_if_geoblocked(exc)
        return
    assert str(single["id"]) == market_id
    assert "question" in single


def test_get_orderbook_top_volume(client: PMClient) -> None:
    try:
        rows = client.list_markets(limit=25)
    except PMGeoBlockedError as exc:
        _skip_if_geoblocked(exc)
        return
    tradeable = [r for r in rows if r.get("enableOrderBook")]
    if not tradeable:
        pytest.skip("no tradeable markets in top volume slice")
    last_err: Exception | None = None
    for market in tradeable[:5]:
        try:
            book = client.get_orderbook(str(market["id"]), outcome="YES")
        except PMGeoBlockedError as exc:
            _skip_if_geoblocked(exc)
            return
        except PMClientError as exc:
            last_err = exc
            continue
        assert "bids" in book and "asks" in book
        assert book["bids"] or book["asks"], "empty book on both sides"
        return
    pytest.skip(f"no orderbook available across sample (last error: {last_err})")


def test_get_resolved_markets(client: PMClient) -> None:
    try:
        rows = client.get_resolved_markets(lookback_days=180, limit=50)
    except PMGeoBlockedError as exc:
        _skip_if_geoblocked(exc)
        return
    assert isinstance(rows, list)
    assert len(rows) >= 1
    assert "id" in rows[0]
