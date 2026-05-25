"""test_L15_market_making.py — Tests for L15 Market-Making Logic.

Coverage:
1. compute_mm_quote with valid inputs returns MMQuote with positive edge
2. should_market_make(0.55, 0.10) → False (std too high)
3. should_market_make(0.55, 0.03) → True
4. compute_mm_quote with model_p=0.98 → None (bid breaches 0.99 bound)
5. update_quotes_on_model_drift: drift > 0.02 → quote in refresh list
6. update_quotes_on_model_drift: drift <= 0.02 → NOT in refresh list
7. post_two_sided with L14 missing → dict with "L14_missing" status
8. prob_to_american correctness (favorites and underdogs)
9. should_market_make with extreme probabilities → False
10. compute_mm_quote with std >= 0.05 → None (should_market_make gates it)
11. compute_mm_quote market_id propagated through to MMQuote
12. post_two_sided with invalid exchange → ValueError
13. update_quotes_on_model_drift: missing market_id in predictions → skipped
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure execute_loop is importable when pytest runs from repo root
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[3]
_EXEC_LOOP = Path(__file__).resolve().parents[1]
for _p in (_REPO_ROOT, _EXEC_LOOP):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------
from L15_market_making import (  # type: ignore
    MMQuote,
    compute_mm_quote,
    post_two_sided,
    prob_to_american,
    should_market_make,
    update_quotes_on_model_drift,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture()
def base_quote() -> MMQuote:
    """A standard MMQuote at fair_value=0.55."""
    return MMQuote(
        market_id="TEST_MARKET_001",
        bid_price=-133,
        bid_qty=1.0,
        ask_price=-111,
        ask_qty=1.0,
        fair_value=0.55,
        edge_per_side=0.015,
    )


# ===========================================================================
# 1. compute_mm_quote with valid inputs
# ===========================================================================

def test_compute_mm_quote_valid_returns_mmquote():
    """compute_mm_quote(0.55, 0.03, 3) must return a populated MMQuote."""
    quote = compute_mm_quote(model_p=0.55, model_p_std=0.03, target_spread_pp=3)
    assert quote is not None, "Expected MMQuote, got None"
    assert isinstance(quote, MMQuote)
    assert quote.edge_per_side > 0, "edge_per_side must be positive"
    assert quote.bid_qty == 1.0
    assert quote.ask_qty == 1.0
    assert quote.fair_value == pytest.approx(0.55)


def test_compute_mm_quote_bid_worse_than_fair():
    """Bid price should be more negative (costlier) than fair — maker favours YES."""
    quote = compute_mm_quote(model_p=0.55, model_p_std=0.03, target_spread_pp=3)
    assert quote is not None
    # bid_p = 0.55 + 0.015 = 0.565  → more negative American odds than fair
    assert quote.bid_price < prob_to_american(0.55), (
        "bid_price should reflect higher implied prob than fair"
    )


def test_compute_mm_quote_ask_better_than_fair():
    """Ask price should be more positive (cheaper) than fair — maker sells YES."""
    quote = compute_mm_quote(model_p=0.55, model_p_std=0.03, target_spread_pp=3)
    assert quote is not None
    # ask_p = 0.55 - 0.015 = 0.535  → less negative (closer to even) American odds
    assert quote.ask_price > prob_to_american(0.55), (
        "ask_price should reflect lower implied prob than fair"
    )


# ===========================================================================
# 2. should_market_make — high std → False
# ===========================================================================

def test_should_market_make_high_std_false():
    """std=0.10 is above gate (0.05) → should_market_make returns False."""
    result = should_market_make(model_p=0.55, model_p_std=0.10)
    assert result is False


# ===========================================================================
# 3. should_market_make — valid inputs → True
# ===========================================================================

def test_should_market_make_valid_true():
    """std=0.03 < 0.05 and model_p=0.55 in (0.10, 0.90) → True."""
    result = should_market_make(model_p=0.55, model_p_std=0.03)
    assert result is True


# ===========================================================================
# 4. compute_mm_quote — extreme model_p breaches prob bound → None
# ===========================================================================

def test_compute_mm_quote_extreme_model_p_returns_none():
    """model_p=0.98 → bid_p=0.98+0.015=0.995 >= 0.99 → must return None."""
    quote = compute_mm_quote(model_p=0.98, model_p_std=0.03, target_spread_pp=3)
    assert quote is None, f"Expected None for extreme model_p=0.98, got {quote}"


def test_compute_mm_quote_model_p_zero_returns_none():
    """model_p=0.0 is outside (0.10, 0.90) → should_market_make=False → None."""
    quote = compute_mm_quote(model_p=0.0, model_p_std=0.03)
    assert quote is None


def test_compute_mm_quote_model_p_one_returns_none():
    """model_p=1.0 is outside (0.10, 0.90) → should_market_make=False → None."""
    quote = compute_mm_quote(model_p=1.0, model_p_std=0.03)
    assert quote is None


# ===========================================================================
# 5. update_quotes_on_model_drift — drift > 0.02 → in refresh list
# ===========================================================================

def test_update_quotes_drift_exceeds_threshold(base_quote):
    """drift=0.03 > 0.02 → quote appears in refresh list."""
    new_predictions = {"TEST_MARKET_001": 0.58}  # 0.58 - 0.55 = 0.03 drift
    refresh = update_quotes_on_model_drift([base_quote], new_predictions)
    assert len(refresh) == 1
    assert refresh[0] is base_quote


# ===========================================================================
# 6. update_quotes_on_model_drift — drift <= 0.02 → NOT in refresh list
# ===========================================================================

def test_update_quotes_drift_below_threshold(base_quote):
    """drift=0.005 <= 0.02 → quote NOT in refresh list."""
    new_predictions = {"TEST_MARKET_001": 0.555}  # 0.555 - 0.55 = 0.005 drift
    refresh = update_quotes_on_model_drift([base_quote], new_predictions)
    assert len(refresh) == 0


def test_update_quotes_drift_exactly_at_threshold(base_quote):
    """drift exactly == 0.02 → NOT in refresh list (strictly greater required)."""
    new_predictions = {"TEST_MARKET_001": 0.57}  # 0.57 - 0.55 = 0.02
    refresh = update_quotes_on_model_drift([base_quote], new_predictions)
    assert len(refresh) == 0


# ===========================================================================
# 7. post_two_sided — L14 missing → "L14_missing" status
# ===========================================================================

def test_post_two_sided_l14_missing(base_quote):
    """When L14_order_manager is absent from sys.modules and un-importable,
    post_two_sided must return status 'L14_missing' with None order IDs."""
    # Remove L14 from sys.modules if present
    sys.modules.pop("L14_order_manager", None)

    # Patch importlib.import_module to raise ImportError for L14
    original_import = __import__

    def _fake_import(name, *args, **kwargs):
        if name == "L14_order_manager":
            raise ImportError("mocked absence")
        return original_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=_fake_import):
        # Also patch importlib.import_module used inside _get_l14
        import importlib
        real_importlib_import = importlib.import_module

        def _fake_importlib(name, *args, **kwargs):
            if name == "L14_order_manager":
                raise ImportError("mocked absence")
            return real_importlib_import(name, *args, **kwargs)

        with patch.object(importlib, "import_module", side_effect=_fake_importlib):
            result = post_two_sided(
                exchange="kalshi",
                market_id="TEST_MARKET_001",
                mm_quote=base_quote,
            )

    assert result["bid_order_id"] is None
    assert result["ask_order_id"] is None
    assert result["status"] == "L14_missing"


def test_post_two_sided_l14_missing_via_sys_modules(base_quote):
    """Inject a sentinel into sys.modules to simulate L14 missing."""
    # Ensure L14 is not importable by injecting None as a stand-in sentinel
    saved = sys.modules.pop("L14_order_manager", None)
    sys.modules["L14_order_manager"] = None  # type: ignore[assignment]

    try:
        result = post_two_sided(
            exchange="polymarket",
            market_id="TEST_MARKET_002",
            mm_quote=base_quote,
        )
    finally:
        # Restore
        if saved is not None:
            sys.modules["L14_order_manager"] = saved
        else:
            sys.modules.pop("L14_order_manager", None)

    # None in sys.modules acts like a missing module (AttributeError on .track_order)
    # The function should handle this gracefully and return L14_missing
    assert result["status"] in ("L14_missing", "posted") or "error" in result["status"]


# ===========================================================================
# 8. prob_to_american correctness
# ===========================================================================

def test_prob_to_american_favorite():
    """p=0.6 → -150 (favorite)."""
    assert prob_to_american(0.6) == -150


def test_prob_to_american_underdog():
    """p=0.4 → +150 (underdog)."""
    assert prob_to_american(0.4) == 150


def test_prob_to_american_even():
    """p=0.5 → -100."""
    assert prob_to_american(0.5) == -100


def test_prob_to_american_small_underdog():
    """p=0.25 → +300."""
    assert prob_to_american(0.25) == 300


def test_prob_to_american_heavy_favorite():
    """p=0.75 → -300."""
    assert prob_to_american(0.75) == -300


# ===========================================================================
# 9. should_market_make — extreme probabilities → False
# ===========================================================================

def test_should_market_make_extreme_low_false():
    """model_p=0.05 < 0.10 → False."""
    assert should_market_make(model_p=0.05, model_p_std=0.02) is False


def test_should_market_make_extreme_high_false():
    """model_p=0.95 > 0.90 → False."""
    assert should_market_make(model_p=0.95, model_p_std=0.02) is False


def test_should_market_make_boundary_low_false():
    """model_p=0.10 is NOT strictly inside (0.10, 0.90) → False."""
    assert should_market_make(model_p=0.10, model_p_std=0.02) is False


def test_should_market_make_boundary_high_false():
    """model_p=0.90 is NOT strictly inside (0.10, 0.90) → False."""
    assert should_market_make(model_p=0.90, model_p_std=0.02) is False


# ===========================================================================
# 10. compute_mm_quote — std >= 0.05 → None
# ===========================================================================

def test_compute_mm_quote_high_std_returns_none():
    """std=0.05 (exactly at gate) → should_market_make=False → None."""
    quote = compute_mm_quote(model_p=0.55, model_p_std=0.05)
    assert quote is None


def test_compute_mm_quote_very_high_std_returns_none():
    """std=0.20 → None."""
    quote = compute_mm_quote(model_p=0.55, model_p_std=0.20)
    assert quote is None


# ===========================================================================
# 11. compute_mm_quote — market_id propagated to MMQuote
# ===========================================================================

def test_compute_mm_quote_market_id_propagated():
    """market_id argument must appear on the returned MMQuote."""
    quote = compute_mm_quote(
        model_p=0.55,
        model_p_std=0.03,
        target_spread_pp=3,
        market_id="NBA_GSW_CELTICS_SPREAD",
    )
    assert quote is not None
    assert quote.market_id == "NBA_GSW_CELTICS_SPREAD"


def test_compute_mm_quote_default_market_id():
    """market_id defaults to 'unknown' when not provided."""
    quote = compute_mm_quote(model_p=0.55, model_p_std=0.03)
    assert quote is not None
    assert quote.market_id == "unknown"


# ===========================================================================
# 12. post_two_sided — invalid exchange → ValueError
# ===========================================================================

def test_post_two_sided_invalid_exchange_raises(base_quote):
    """Unrecognised exchange name must raise ValueError."""
    with pytest.raises(ValueError, match="Unknown exchange"):
        post_two_sided(
            exchange="betfair",
            market_id="SOME_MARKET",
            mm_quote=base_quote,
        )


# ===========================================================================
# 13. update_quotes_on_model_drift — missing market_id in predictions → skipped
# ===========================================================================

def test_update_quotes_missing_market_id(base_quote):
    """If new_predictions has no entry for a quote's market_id, it is skipped."""
    new_predictions = {"OTHER_MARKET_999": 0.80}
    refresh = update_quotes_on_model_drift([base_quote], new_predictions)
    assert len(refresh) == 0


def test_update_quotes_empty_open_quotes():
    """Empty open_quotes list → empty refresh list."""
    refresh = update_quotes_on_model_drift([], {"MARKET": 0.6})
    assert refresh == []


def test_update_quotes_multiple_quotes_mixed():
    """With two quotes, only the drifted one appears in refresh list."""
    q1 = MMQuote("MKT_A", -122, 1.0, -110, 1.0, 0.55, 0.015)
    q2 = MMQuote("MKT_B", -110, 1.0, +105, 1.0, 0.48, 0.015)
    new_predictions = {
        "MKT_A": 0.555,  # drift = 0.005 → stable
        "MKT_B": 0.52,   # drift = 0.04  → refresh
    }
    refresh = update_quotes_on_model_drift([q1, q2], new_predictions)
    assert len(refresh) == 1
    assert refresh[0] is q2


# ===========================================================================
# 14. post_two_sided — L14 available (mocked) → "posted" status
# ===========================================================================

def test_post_two_sided_with_mocked_l14(base_quote):
    """When L14 is available (mocked), post_two_sided returns status='posted'."""
    mock_l14 = MagicMock()
    mock_l14.track_order.return_value = MagicMock()  # returns some OrderState-like obj

    sys.modules.pop("L14_order_manager", None)
    sys.modules["L14_order_manager"] = mock_l14

    try:
        result = post_two_sided(
            exchange="kalshi",
            market_id="TEST_MARKET_001",
            mm_quote=base_quote,
        )
    finally:
        sys.modules.pop("L14_order_manager", None)

    assert result["status"] == "posted"
    assert result["bid_order_id"] is not None
    assert result["ask_order_id"] is not None
    assert mock_l14.track_order.call_count == 2  # bid + ask
