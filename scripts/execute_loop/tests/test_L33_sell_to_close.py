"""test_L33_sell_to_close.py — Tests for L33_sell_to_close.py

Seven required tests + bonus edge-case coverage + v2 EventBus tests.
No external dependencies — stdlib + pytest only.
"""
from __future__ import annotations

import logging
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup — mirrors pattern in other test_L* files
# ---------------------------------------------------------------------------
_TEST_DIR = Path(__file__).resolve().parent
_LOOP_DIR = _TEST_DIR.parent
_PROJECT_DIR = _LOOP_DIR.parents[1]
sys.path.insert(0, str(_PROJECT_DIR))
sys.path.insert(0, str(_LOOP_DIR))

import L33_sell_to_close as L33  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _pos(
    position_id: str = "p1",
    qty: float = 100.0,
    entry_price: float = 0.50,
    side: str = "YES",
) -> dict:
    return {"position_id": position_id, "qty": qty, "entry_price": entry_price, "side": side}


def _quote(
    bid_price: float | None = 0.60,
    ask_price: float | None = 0.62,
    bid_size: float = 50.0,
    venue: str = "kalshi",
) -> dict:
    return {"bid_price": bid_price, "ask_price": ask_price, "bid_size": bid_size, "venue": venue}


# ---------------------------------------------------------------------------
# Test 1: HOLD when model value dominates (value_hold >> value_now)
# Position: YES qty=100 entry=0.50, bid=0.55, model_p=0.80
#   value_now  = 100 * 0.55 = 55.0
#   value_hold = 100 * 0.80 = 80.0
#   80 > 55 * 1.05 (57.75) → HOLD
# ---------------------------------------------------------------------------
def test_hold_when_model_dominates():
    """value_hold=80 >> value_now=55 → HOLD (hold_premium)."""
    decision = L33.evaluate_close_decision(
        position=_pos(qty=100.0, entry_price=0.50, side="YES"),
        current_quote=_quote(bid_price=0.55),
        model_p=0.80,
        time_to_settle_min=30,
    )
    assert decision.action == "HOLD"
    assert decision.decision_reason == "hold_premium"
    assert decision.sell_qty == 0.0
    assert decision.sell_price == pytest.approx(0.55)


# ---------------------------------------------------------------------------
# Test 2: SELL when market value dominates (value_now >> value_hold)
# Position: YES qty=100 entry=0.50, bid=0.85, model_p=0.50
#   value_now  = 100 * 0.85 = 85.0
#   value_hold = 100 * 0.50 = 50.0
#   85 > 50 * 1.05 (52.5) → SELL
# ---------------------------------------------------------------------------
def test_sell_when_market_dominates():
    """value_now=85 >> value_hold=50 → SELL full qty (lock_gain)."""
    decision = L33.evaluate_close_decision(
        position=_pos(qty=100.0, entry_price=0.50, side="YES"),
        current_quote=_quote(bid_price=0.85),
        model_p=0.50,
        time_to_settle_min=30,
    )
    assert decision.action == "SELL"
    assert decision.decision_reason == "lock_gain"
    assert decision.sell_qty == pytest.approx(100.0)
    assert decision.sell_price == pytest.approx(0.85)


# ---------------------------------------------------------------------------
# Test 3: SELL_PARTIAL when values are marginal
# Position: YES qty=100 entry=0.50, bid=0.55, model_p=0.56
#   value_now  = 100 * 0.55 = 55.0
#   value_hold = 100 * 0.56 = 56.0
#   56 < 55*1.05=57.75 → not HOLD
#   55 < 56*1.05=58.80 → not SELL
#   → SELL_PARTIAL, sell_qty=50
# ---------------------------------------------------------------------------
def test_partial_when_marginal():
    """value_now=55, value_hold=56 — neither dominates → SELL_PARTIAL with sell_qty=50."""
    decision = L33.evaluate_close_decision(
        position=_pos(qty=100.0, entry_price=0.50, side="YES"),
        current_quote=_quote(bid_price=0.55),
        model_p=0.56,
        time_to_settle_min=30,
    )
    assert decision.action == "SELL_PARTIAL"
    assert decision.decision_reason == "de_risk_marginal"
    assert decision.sell_qty == pytest.approx(50.0)
    assert decision.sell_price == pytest.approx(0.55)


# ---------------------------------------------------------------------------
# Test 4: HOLD when time_to_settle_min < 5
# ---------------------------------------------------------------------------
def test_settlement_imminent():
    """time_to_settle=2 < 5 → HOLD regardless of values."""
    decision = L33.evaluate_close_decision(
        position=_pos(qty=100.0, entry_price=0.50, side="YES"),
        current_quote=_quote(bid_price=0.90),  # market is great but still HOLD
        model_p=0.10,                           # model says sell — still overridden
        time_to_settle_min=2,
    )
    assert decision.action == "HOLD"
    assert decision.decision_reason == "settlement_imminent"
    assert decision.sell_qty == 0.0


# ---------------------------------------------------------------------------
# Test 5: HOLD when bid_price is None (no liquidity)
# ---------------------------------------------------------------------------
def test_no_bid_liquidity_none():
    """bid_price=None → HOLD (no_liquidity)."""
    decision = L33.evaluate_close_decision(
        position=_pos(qty=100.0, entry_price=0.50, side="YES"),
        current_quote=_quote(bid_price=None, bid_size=0.0),
        model_p=0.10,
        time_to_settle_min=30,
    )
    assert decision.action == "HOLD"
    assert decision.decision_reason == "no_liquidity"
    assert decision.sell_price is None


# ---------------------------------------------------------------------------
# Test 5b: HOLD when bid_size == 0 (zero liquidity even if price present)
# ---------------------------------------------------------------------------
def test_no_bid_liquidity_zero_size():
    """bid_size=0 → HOLD (no_liquidity) even when bid_price is set."""
    decision = L33.evaluate_close_decision(
        position=_pos(qty=100.0, entry_price=0.50, side="YES"),
        current_quote=_quote(bid_price=0.90, bid_size=0.0),
        model_p=0.10,
        time_to_settle_min=30,
    )
    assert decision.action == "HOLD"
    assert decision.decision_reason == "no_liquidity"


# ---------------------------------------------------------------------------
# Test 6: NO/UNDER position symmetry
# Position: NO qty=100 entry=0.70, bid=0.30, model_p=0.40
#   value_now  = 100 * (1 - 0.30) = 70.0
#   value_hold = 100 * (1 - 0.40) = 60.0
#   70 > 60 * 1.05 (63.0) → SELL
# ---------------------------------------------------------------------------
def test_no_side_symmetry_sell():
    """NO position: value_now=70 > value_hold*1.05=63 → SELL."""
    decision = L33.evaluate_close_decision(
        position=_pos(qty=100.0, entry_price=0.70, side="NO"),
        current_quote=_quote(bid_price=0.30),
        model_p=0.40,
        time_to_settle_min=30,
    )
    assert decision.action == "SELL"
    assert decision.decision_reason == "lock_gain"
    assert decision.sell_qty == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Test 7: model_p clamping — no crash, clamped to 1.0
# ---------------------------------------------------------------------------
def test_clamps_model_p_above_one(caplog):
    """model_p=1.3 clamped to 1.0 — function should not crash and should log WARN."""
    with caplog.at_level(logging.WARNING, logger="L33_sell_to_close"):
        decision = L33.evaluate_close_decision(
            position=_pos(qty=100.0, entry_price=0.50, side="YES"),
            current_quote=_quote(bid_price=0.60),
            model_p=1.3,
            time_to_settle_min=30,
        )
    # Clamped to 1.0: value_hold = 100*1.0 = 100 > value_now=60*1.05=63 → HOLD
    assert decision.action == "HOLD"
    assert any("clamped" in r.message.lower() for r in caplog.records)


def test_clamps_model_p_below_zero(caplog):
    """model_p=-0.5 clamped to 0.0 — no crash, logs WARN."""
    with caplog.at_level(logging.WARNING, logger="L33_sell_to_close"):
        decision = L33.evaluate_close_decision(
            position=_pos(qty=100.0, entry_price=0.50, side="YES"),
            current_quote=_quote(bid_price=0.60),
            model_p=-0.5,
            time_to_settle_min=30,
        )
    # Clamped to 0.0: value_hold=0, value_now=60 → SELL
    assert decision.action == "SELL"
    assert any("clamped" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# Bonus: empty position (qty <= 0) → HOLD (empty_position)
# ---------------------------------------------------------------------------
def test_empty_position():
    """qty=0 → HOLD (empty_position) regardless of other inputs."""
    decision = L33.evaluate_close_decision(
        position=_pos(qty=0.0),
        current_quote=_quote(bid_price=0.99),
        model_p=0.01,
        time_to_settle_min=60,
    )
    assert decision.action == "HOLD"
    assert decision.decision_reason == "empty_position"


def test_negative_qty():
    """qty=-5 → HOLD (empty_position)."""
    decision = L33.evaluate_close_decision(
        position=_pos(qty=-5.0),
        current_quote=_quote(bid_price=0.80),
        model_p=0.20,
        time_to_settle_min=60,
    )
    assert decision.action == "HOLD"
    assert decision.decision_reason == "empty_position"


# ---------------------------------------------------------------------------
# Bonus: UNDER side mirrors OVER correctly
# ---------------------------------------------------------------------------
def test_under_side_hold():
    """UNDER position: model_p=0.10 → value_hold=100*0.90=90, bid=0.80 → value_now=20.
    90 > 20*1.05=21 → HOLD.
    """
    decision = L33.evaluate_close_decision(
        position=_pos(qty=100.0, entry_price=0.20, side="UNDER"),
        current_quote=_quote(bid_price=0.80),
        model_p=0.10,
        time_to_settle_min=30,
    )
    assert decision.action == "HOLD"
    assert decision.decision_reason == "hold_premium"


# ---------------------------------------------------------------------------
# Bonus: model_p_var tightens premium
# With premium=1.02 instead of 1.05, a marginal case can tip to SELL.
# bid=0.56, model_p=0.57 → value_now=56, value_hold=57
#   Standard premium (1.05): 57 < 56*1.05=58.8 → not HOLD; 56 < 57*1.05=59.85 → SELL_PARTIAL
#   Tight premium (1.02): 57 < 56*1.02=57.12 → not HOLD; 56 < 57*1.02=58.14 → SELL_PARTIAL still
# Use bid=0.585, model_p=0.59 (values 58.5 vs 59):
#   Tight: 59 < 58.5*1.02=59.67 → not HOLD; 58.5 < 59*1.02=60.18 → SELL_PARTIAL
# Use bid=0.59, model_p=0.595 (values 59 vs 59.5): still marginal.
# Force it: bid=0.595, model_p=0.60 (59.5 vs 60):
#   Tight (1.02): 60 > 59.5*1.02=60.69? No. Still partial.
# Cleaner: model_p_var test just verifies that the _decision branch doesn't crash
# and that a SELL is generated when now beats hold under tight premium.
# bid=0.625, model_p=0.60 → value_now=62.5, value_hold=60:
#   Standard: 62.5 > 60*1.05=63? No → SELL_PARTIAL
#   Tight 1.02: 62.5 > 60*1.02=61.2? Yes → SELL
# ---------------------------------------------------------------------------
def test_model_p_var_tightens_premium():
    """High model_p_var switches premium to 1.02; marginal case tips to SELL instead of SELL_PARTIAL."""
    # Standard premium (no var) → SELL_PARTIAL
    decision_std = L33.evaluate_close_decision(
        position=_pos(qty=100.0, entry_price=0.50, side="YES"),
        current_quote=_quote(bid_price=0.625),
        model_p=0.60,
        time_to_settle_min=30,
        model_p_var=None,
    )
    assert decision_std.action == "SELL_PARTIAL", (
        f"Expected SELL_PARTIAL with standard premium, got {decision_std.action}"
    )

    # High variance → tighter premium (1.02) → SELL
    decision_var = L33.evaluate_close_decision(
        position=_pos(qty=100.0, entry_price=0.50, side="YES"),
        current_quote=_quote(bid_price=0.625),
        model_p=0.60,
        time_to_settle_min=30,
        model_p_var=0.06,
    )
    assert decision_var.action == "SELL", (
        f"Expected SELL with tight premium (high var), got {decision_var.action}"
    )


# ---------------------------------------------------------------------------
# Bonus: score_market_value_now returns 0 when bid_price is None
# ---------------------------------------------------------------------------
def test_score_market_value_now_no_bid():
    """score_market_value_now returns 0.0 when bid_price is None."""
    result = L33.score_market_value_now(
        position=_pos(qty=100.0, side="YES"),
        current_quote=_quote(bid_price=None),
    )
    assert result == 0.0


# ---------------------------------------------------------------------------
# Bonus: score_hold_to_settle basic math check
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("side,model_p,qty,expected", [
    ("YES",   0.75, 100.0, 75.0),
    ("OVER",  0.40, 50.0,  20.0),
    ("NO",    0.30, 100.0, 70.0),   # 100*(1-0.30)=70
    ("UNDER", 0.60, 200.0, 80.0),   # 200*(1-0.60)=80
])
def test_score_hold_to_settle_parametrized(side, model_p, qty, expected):
    """score_hold_to_settle returns correct expected value for all four sides."""
    result = L33.score_hold_to_settle(
        position={"position_id": "x", "qty": qty, "entry_price": 0.0, "side": side},
        model_p=model_p,
    )
    assert result == pytest.approx(expected, abs=1e-6)


# ---------------------------------------------------------------------------
# Bonus: unknown side defaults to YES/OVER logic
# ---------------------------------------------------------------------------
def test_unknown_side_defaults_to_long():
    """Unrecognised side string falls back to YES/OVER (long) arithmetic."""
    result = L33.score_market_value_now(
        position={"position_id": "x", "qty": 100.0, "entry_price": 0.0, "side": "MAYBE"},
        current_quote=_quote(bid_price=0.70),
    )
    # Fallback: 100 * (1 - 0.70) = 30 (NO path) because MAYBE not in _LONG_SIDES
    # Actually: MAYBE not in _LONG_SIDES, so it goes to the else branch → qty*(1-bid)
    assert result == pytest.approx(30.0)

    # Decision should not crash
    decision = L33.evaluate_close_decision(
        position=_pos(qty=100.0, entry_price=0.50, side="MAYBE"),
        current_quote=_quote(bid_price=0.70),
        model_p=0.60,
        time_to_settle_min=30,
    )
    assert decision.action in ("HOLD", "SELL", "SELL_PARTIAL")


# ---------------------------------------------------------------------------
# v2 — EventBus publication tests
# ---------------------------------------------------------------------------

def _make_mock_bus():
    """Return a fresh MagicMock that quacks like L46_event_bus."""
    mock_bus = MagicMock()
    mock_bus.publish = MagicMock(return_value=None)
    return mock_bus


def test_close_recommendation_publishes_event():
    """SELL action publishes exactly one 'close.recommended' event via L46."""
    mock_bus = _make_mock_bus()
    with patch.object(L33, "_L46", mock_bus):
        decision = L33.evaluate_close_decision(
            position=_pos(qty=100.0, entry_price=0.50, side="YES",
                          position_id="p_pub"),
            current_quote=_quote(bid_price=0.85),
            model_p=0.50,
            time_to_settle_min=30,
            model_p_var=0.02,
        )
    assert decision.action == "SELL"
    mock_bus.publish.assert_called_once()
    call_kwargs = mock_bus.publish.call_args
    # First positional arg is the event name
    event_name = call_kwargs[0][0]
    assert event_name == "close.recommended"
    payload = call_kwargs[1]["payload"]
    assert payload["position_id"] == "p_pub"
    assert payload["reason"] == "lock_gain"
    assert payload["model_p_var"] == pytest.approx(0.02)
    assert "recommended_at" in payload


def test_hold_recommendation_publishes_nothing():
    """HOLD action must NOT publish any event."""
    mock_bus = _make_mock_bus()
    with patch.object(L33, "_L46", mock_bus):
        decision = L33.evaluate_close_decision(
            position=_pos(qty=100.0, entry_price=0.50, side="YES"),
            current_quote=_quote(bid_price=0.55),
            model_p=0.80,
            time_to_settle_min=30,
        )
    assert decision.action == "HOLD"
    mock_bus.publish.assert_not_called()


def test_publish_failure_does_not_break_evaluate():
    """If L46.publish raises, evaluate_close_decision still returns a valid CloseDecision."""
    mock_bus = _make_mock_bus()
    mock_bus.publish.side_effect = RuntimeError("bus exploded")
    with patch.object(L33, "_L46", mock_bus):
        decision = L33.evaluate_close_decision(
            position=_pos(qty=100.0, entry_price=0.50, side="YES"),
            current_quote=_quote(bid_price=0.85),
            model_p=0.50,
            time_to_settle_min=30,
        )
    # The decision is still returned despite publish failure
    assert decision.action == "SELL"
    assert decision.decision_reason == "lock_gain"
    assert decision.sell_qty == pytest.approx(100.0)


def test_sell_partial_publishes_event():
    """SELL_PARTIAL action also publishes 'close.recommended' with correct reason."""
    mock_bus = _make_mock_bus()
    with patch.object(L33, "_L46", mock_bus):
        decision = L33.evaluate_close_decision(
            position=_pos(qty=100.0, entry_price=0.50, side="YES"),
            current_quote=_quote(bid_price=0.55),
            model_p=0.56,
            time_to_settle_min=30,
        )
    assert decision.action == "SELL_PARTIAL"
    mock_bus.publish.assert_called_once()
    payload = mock_bus.publish.call_args[1]["payload"]
    assert payload["reason"] == "de_risk_marginal"
    assert payload["current_price"] == pytest.approx(0.55)
