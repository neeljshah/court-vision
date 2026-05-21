"""
tests/test_execution.py — Exchange adapter test stubs (Phase 17, EX-01 to EX-07).

All tests are xfail until Wave 2-3 plans implement the adapters.
Remove @pytest.mark.xfail from individual tests as each plan completes.
"""
import os
import pytest
from unittest.mock import MagicMock, patch

# Attempt imports — tests skip if modules not yet created
try:
    from src.execution.base_adapter import ExchangeAdapter, MarketQuote, OrderResult
    from src.execution.book_router import BookRouter
    from src.execution.sporttrade import SporttradeAdapter
    from src.execution.kalshi import _make_kalshi_headers, win_prob_to_kalshi_price
    from src.execution.polymarket import extract_token_id
    _ADAPTERS_AVAILABLE = True
except ImportError:
    _ADAPTERS_AVAILABLE = False

_skip_if_no_adapters = pytest.mark.skipif(
    not _ADAPTERS_AVAILABLE,
    reason="Exchange adapters not yet implemented — Wave 2-3 pending",
)


@pytest.mark.xfail(strict=False, reason="BookRouter not yet implemented")
@_skip_if_no_adapters
def test_router_picks_best_price() -> None:
    """EX-01: Router selects adapter with lowest yes_ask."""
    adapter_a = MagicMock()
    adapter_a.find_market.return_value = [{"id": "market-1"}]
    adapter_a.get_quote.return_value = MarketQuote(
        exchange="kalshi", ticker="market-1", yes_ask=0.62, yes_bid=0.60, available_contracts=100
    )
    adapter_b = MagicMock()
    adapter_b.find_market.return_value = [{"id": "market-2"}]
    adapter_b.get_quote.return_value = MarketQuote(
        exchange="polymarket", ticker="market-2", yes_ask=0.58, yes_bid=0.56, available_contracts=50
    )
    router = BookRouter([adapter_a, adapter_b])
    result = router.route("LeBron James points over 25.5", "yes", 10, max_price=0.65)
    assert result is not None
    assert result.exchange == "polymarket"  # lower ask wins


@pytest.mark.xfail(strict=False, reason="BookRouter dry-run not yet implemented")
@_skip_if_no_adapters
def test_dry_run_no_http() -> None:
    """EX-02: LIVE_BETTING=0 returns paper status, no real HTTP calls."""
    adapter = MagicMock()
    adapter.find_market.return_value = [{"id": "market-1"}]
    adapter.get_quote.return_value = MarketQuote(
        exchange="kalshi", ticker="market-1", yes_ask=0.60, yes_bid=0.58, available_contracts=100
    )
    with patch.dict(os.environ, {"LIVE_BETTING": "0"}):
        router = BookRouter([adapter])
        result = router.route("LeBron James points", "yes", 5, max_price=0.65)
    assert result is not None
    assert result.status == "paper"
    # place_limit_order should NOT have been called on the real adapter
    adapter.place_limit_order.assert_not_called()


@pytest.mark.xfail(strict=False, reason="Kalshi price conversion not yet implemented")
@_skip_if_no_adapters
def test_kalshi_price_clamp() -> None:
    """EX-03: win_prob_to_kalshi_price clamps 0.0 -> 1 and 1.0 -> 99."""
    assert win_prob_to_kalshi_price(0.0) == 1
    assert win_prob_to_kalshi_price(1.0) == 99
    assert win_prob_to_kalshi_price(0.623) == 62
    assert win_prob_to_kalshi_price(0.625) == 63  # rounding


@pytest.mark.xfail(strict=False, reason="Kalshi RSA auth not yet implemented")
@_skip_if_no_adapters
def test_kalshi_auth_headers() -> None:
    """EX-04: RSA-PSS headers generated correctly from a test key."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()
    with patch.dict(os.environ, {"KALSHI_ACCESS_KEY": "test-key-id"}):
        headers = _make_kalshi_headers(pem, "POST", "/trade-api/v2/portfolio/orders")
    assert "KALSHI-ACCESS-KEY" in headers
    assert "KALSHI-ACCESS-SIGNATURE" in headers
    assert "KALSHI-ACCESS-TIMESTAMP" in headers
    assert headers["Content-Type"] == "application/json"


@pytest.mark.xfail(strict=False, reason="Polymarket token lookup not yet implemented")
@_skip_if_no_adapters
def test_polymarket_token_lookup() -> None:
    """EX-05: extract_token_id correctly pulls YES/NO token from Gamma API market dict."""
    market = {
        "question": "Will LeBron James score over 25.5 points?",
        "conditionId": "0xabc123",
        "clobTokenIds": ["token_yes_abc", "token_no_def"],
        "outcomes": ["Yes", "No"],
    }
    assert extract_token_id(market, "yes") == "token_yes_abc"
    assert extract_token_id(market, "no") == "token_no_def"


@pytest.mark.xfail(strict=False, reason="SporttradeAdapter stub not yet implemented")
@_skip_if_no_adapters
def test_sporttrade_stub() -> None:
    """EX-06: SporttradeAdapter raises NotImplementedError on all methods."""
    adapter = SporttradeAdapter()
    with pytest.raises(NotImplementedError):
        adapter.get_quote("any-market-id")
    with pytest.raises(NotImplementedError):
        adapter.place_limit_order("ticker", "yes", 1, 0.50)
    with pytest.raises(NotImplementedError):
        adapter.find_market("LeBron points")


@pytest.mark.xfail(strict=False, reason="BookRouter result schema not yet implemented")
@_skip_if_no_adapters
def test_router_logs_route() -> None:
    """EX-07: Route result is an OrderResult with all required fields."""
    adapter = MagicMock()
    adapter.find_market.return_value = [{"id": "market-1"}]
    adapter.get_quote.return_value = MarketQuote(
        exchange="kalshi", ticker="KXNBA-TEST", yes_ask=0.60, yes_bid=0.58, available_contracts=100
    )
    with patch.dict(os.environ, {"LIVE_BETTING": "0"}):
        router = BookRouter([adapter])
        result = router.route("test query", "yes", 3, max_price=0.65)
    assert result is not None
    assert hasattr(result, "exchange")
    assert hasattr(result, "ticker")
    assert hasattr(result, "side")
    assert hasattr(result, "count")
    assert hasattr(result, "fill_price")
    assert hasattr(result, "status")
