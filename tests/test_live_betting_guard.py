"""
test_live_betting_guard.py -- Tests for the LIVE_BETTING=0 kill switch (19-01).

Acceptance criterion: book_router reads LIVE_BETTING at startup and raises
RuntimeError if any adapter attempts a real order placement when LIVE_BETTING=0.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.execution.base_adapter import (  # noqa: E402
    ExchangeAdapter,
    MarketQuote,
    OrderResult,
    assert_live_betting_enabled,
    live_betting_enabled,
)
from src.execution.book_router import BookRouter  # noqa: E402


class _FakeLiveAdapter(ExchangeAdapter):
    """A 'real' adapter — its place_limit_order is guarded by the kill switch."""

    def __init__(self):
        self.placed = False

    def get_quote(self, market_id: str) -> MarketQuote:
        return MarketQuote("fakelive", market_id, 0.55, 0.53, 100)

    def place_limit_order(self, ticker, side, count, price) -> OrderResult:
        self.guard_live_order()   # <-- kill-switch guard
        self.placed = True
        return OrderResult("fakelive", "ord-1", ticker, side, count, price, "filled")

    def find_market(self, query: str) -> list:
        return [{"id": "fakelive-market"}]


# ── guard primitive ───────────────────────────────────────────────────────────

def test_guard_raises_when_live_betting_disabled():
    """assert_live_betting_enabled raises RuntimeError when LIVE_BETTING=0."""
    with patch.dict(os.environ, {"LIVE_BETTING": "0"}):
        with pytest.raises(RuntimeError, match="LIVE_BETTING"):
            assert_live_betting_enabled("kalshi")


def test_guard_passes_when_live_betting_enabled():
    """assert_live_betting_enabled is a no-op when LIVE_BETTING=1."""
    with patch.dict(os.environ, {"LIVE_BETTING": "1"}):
        assert live_betting_enabled() is True
        assert_live_betting_enabled("kalshi")   # must not raise


def test_guard_raises_when_env_var_absent():
    """An unset LIVE_BETTING defaults to paper mode and the guard fires."""
    env = {k: v for k, v in os.environ.items() if k != "LIVE_BETTING"}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(RuntimeError):
            assert_live_betting_enabled()


# ── adapter-level enforcement ─────────────────────────────────────────────────

def test_real_adapter_place_order_blocked_in_paper_mode():
    """A real adapter's place_limit_order raises RuntimeError when paper."""
    adapter = _FakeLiveAdapter()
    with patch.dict(os.environ, {"LIVE_BETTING": "0"}):
        with pytest.raises(RuntimeError, match="refusing real order"):
            adapter.place_limit_order("t-1", "yes", 5, 0.55)
    assert adapter.placed is False


def test_real_adapter_place_order_allowed_when_live():
    """The same placement succeeds when LIVE_BETTING=1."""
    adapter = _FakeLiveAdapter()
    with patch.dict(os.environ, {"LIVE_BETTING": "1"}):
        result = adapter.place_limit_order("t-1", "yes", 5, 0.55)
    assert adapter.placed is True
    assert result.status == "filled"


# ── router-level enforcement ──────────────────────────────────────────────────

def test_router_paper_mode_never_calls_place_order():
    """In paper mode the router returns paper and never reaches a real order."""
    adapter = _FakeLiveAdapter()
    with patch.dict(os.environ, {"LIVE_BETTING": "0"}):
        result = BookRouter([adapter]).route("query", "yes", 5, 0.65)
    assert result.status == "paper"
    assert adapter.placed is False


def test_router_records_startup_mode():
    """BookRouter reads the LIVE_BETTING kill switch at construction time."""
    with patch.dict(os.environ, {"LIVE_BETTING": "0"}):
        assert BookRouter([])._startup_live is False
    with patch.dict(os.environ, {"LIVE_BETTING": "1"}):
        assert BookRouter([])._startup_live is True


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
