"""Per-file test for scripts.platformkit.execution_model.

Synthetic book only -- no archives, no network. Checks the crossing cost and
the partial-fill VWAP to the exact cent, and that the replay's three scenarios
come out ordered mid >= crossing >= crossing+slippage.
Run: python -m pytest scripts/platformkit/test_execution_model.py -q
"""
from __future__ import annotations

import pytest

from scripts.platformkit.execution_model import (
    CROSSING,
    CROSSING_SLIPPAGE,
    MID,
    SCENARIOS,
    SpreadModel,
    effective_edge,
    replay_costs,
)

# Synthetic top-of-book: 4-tick spread, mid 0.42.
BID, ASK, MID_PX = 0.40, 0.44, 0.42
TICK = 0.01


def _model(slippage_ticks: float = 0.0) -> SpreadModel:
    return SpreadModel(tick=TICK, slippage_ticks=slippage_ticks)


def test_mid_price_is_the_flattering_baseline() -> None:
    assert SpreadModel.mid_price(BID, ASK) == pytest.approx(MID_PX)


def test_crossing_cost_is_exact() -> None:
    m = _model()
    buy = m.fill_price("buy", BID, ASK, 10.0)
    sell = m.fill_price("sell", BID, ASK, 10.0)
    assert buy == pytest.approx(ASK)
    assert sell == pytest.approx(BID)
    # Half the spread, charged against you on each side.
    assert buy - MID_PX == pytest.approx(0.02)
    assert MID_PX - sell == pytest.approx(0.02)


def test_partial_fill_math_is_exact() -> None:
    m = _model()
    # 60 units at 0.44, 40 at the next tick 0.45 -> 0.444
    buy = m.fill_price("buy", BID, ASK, 100.0, depth_units=60.0)
    assert buy == pytest.approx((60 * 0.44 + 40 * 0.45) / 100.0)
    assert buy == pytest.approx(0.444)
    # Selling walks DOWN: 60 at 0.40, 40 at 0.39 -> 0.396
    sell = m.fill_price("sell", BID, ASK, 100.0, depth_units=60.0)
    assert sell == pytest.approx(0.396)


def test_depth_edges() -> None:
    m = _model()
    # Depth covers the order -> pure top-of-book.
    assert m.fill_price("buy", BID, ASK, 10.0, depth_units=50.0) == pytest.approx(ASK)
    # No depth at top of book -> the whole order pays the next tick.
    assert m.fill_price("buy", BID, ASK, 10.0, depth_units=0.0) == pytest.approx(0.45)
    # depth_units=None means top of book is deep enough.
    assert m.fill_price("sell", BID, ASK, 999.0) == pytest.approx(BID)


def test_slippage_ticks_are_additive_and_adverse() -> None:
    slipped = _model(slippage_ticks=2.0)
    assert slipped.fill_price("buy", BID, ASK, 10.0) == pytest.approx(ASK + 0.02)
    assert slipped.fill_price("sell", BID, ASK, 10.0) == pytest.approx(BID - 0.02)
    # Stacks on top of a partial fill.
    assert slipped.fill_price("buy", BID, ASK, 100.0, 60.0) == pytest.approx(0.464)


def test_fill_price_clamped_to_probability_range() -> None:
    assert _model(slippage_ticks=3.0).fill_price("buy", 0.97, 0.99, 1.0) == 1.0
    assert _model(slippage_ticks=5.0).fill_price("sell", 0.02, 0.04, 1.0) == 0.0


def test_effective_edge_is_signed_by_side() -> None:
    assert effective_edge(0.50, 0.44) == pytest.approx(0.06)
    assert effective_edge(0.50, 0.44, side="buy") == pytest.approx(0.06)
    assert effective_edge(0.50, 0.55, side="sell") == pytest.approx(0.05)
    assert effective_edge(0.50, 0.44, side="sell") == pytest.approx(-0.06)


def test_invalid_inputs_raise() -> None:
    m = _model()
    with pytest.raises(ValueError):
        m.fill_price("yes", BID, ASK, 1.0)          # no yes/no aliasing
    with pytest.raises(ValueError):
        m.fill_price("buy", BID, ASK, 0.0)          # non-positive size
    with pytest.raises(ValueError):
        m.fill_price("buy", 0.60, 0.50, 1.0)        # crossed book
    with pytest.raises(ValueError):
        m.fill_price("buy", BID, 1.4, 1.0)          # price outside [0, 1]
    with pytest.raises(ValueError):
        SpreadModel(tick=0.0)
    with pytest.raises(ValueError):
        SpreadModel(slippage_ticks=-1.0)


ROWS = [
    {"id": "a", "side": "buy", "bid": 0.40, "ask": 0.44, "prob": 0.50,
     "size_units": 10.0},
    {"id": "b", "side": "buy", "bid": 0.40, "ask": 0.44, "prob": 0.50,
     "size_units": 100.0, "depth_units": 60.0},
    {"id": "c", "side": "sell", "bid": 0.55, "ask": 0.60, "prob": 0.50,
     "size_units": 100.0, "depth_units": 25.0},
    {"id": "d", "side": "buy", "bid": 0.30, "ask": 0.31, "prob": 0.32,
     "size_units": 5.0},
]


def test_replay_orders_mid_ge_crossing_ge_slipped() -> None:
    out = replay_costs(ROWS, tick=TICK, slippage_ticks=1.0)
    assert out["n_rows"] == 4 and out["n_priced"] == 4 and out["n_skipped"] == 0
    assert out["units"] == "probability"
    for row in out["per_row"]:
        assert row[MID] >= row[CROSSING] >= row[CROSSING_SLIPPAGE]
    means = [out["scenarios"][name]["mean"] for name in SCENARIOS]
    assert means[0] >= means[1] >= means[2]
    for name in SCENARIOS:
        assert out["scenarios"][name]["n"] == 4


def test_replay_row_values_match_direct_pricing() -> None:
    out = replay_costs(ROWS[:2], tick=TICK, slippage_ticks=1.0)
    first = out["per_row"][0]
    assert first[MID] == pytest.approx(0.50 - MID_PX)
    assert first[CROSSING] == pytest.approx(0.50 - ASK)
    assert first[CROSSING_SLIPPAGE] == pytest.approx(0.50 - 0.45)
    # Partial fill row: 0.444 crossing, 0.454 with a tick of slippage.
    second = out["per_row"][1]
    assert second[CROSSING] == pytest.approx(0.50 - 0.444)
    assert second[CROSSING_SLIPPAGE] == pytest.approx(0.50 - 0.454)


def test_a_mid_only_survivor_is_exposed() -> None:
    """Edge thinner than half the spread flips negative once fills are charged."""
    thin = [{"side": "buy", "bid": 0.40, "ask": 0.44, "prob": 0.43}]
    out = replay_costs(thin, tick=TICK, slippage_ticks=1.0)
    assert out["scenarios"][MID]["mean"] > 0
    assert out["scenarios"][CROSSING]["mean"] < 0
    assert out["scenarios"][CROSSING_SLIPPAGE]["mean"] < out["scenarios"][CROSSING]["mean"]


def test_bad_rows_are_skipped_and_counted() -> None:
    rows = [ROWS[0], {"side": "nope", "bid": 0.4, "ask": 0.44, "prob": 0.5},
            {"side": "buy", "bid": 0.4, "ask": 0.44}, "not-a-row"]
    out = replay_costs(rows)
    assert out["n_rows"] == 4 and out["n_priced"] == 1 and out["n_skipped"] == 3
    assert all(entry["reason"] for entry in out["skipped"])


def test_empty_replay_is_null_not_zero() -> None:
    out = replay_costs([])
    assert out["n_rows"] == 0
    for name in SCENARIOS:
        assert out["scenarios"][name]["n"] == 0
        assert out["scenarios"][name]["mean"] is None
