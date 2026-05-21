"""Tests for src/prediction/signal_router.py

Covers:
  - SignalRouter.register / registered
  - SignalRouter.route: calls strategies, deduplicates, sorts by edge
  - _dedup_sort: keeps highest-edge per (player_id, stat, direction)
  - Faulty strategy does not crash the router
  - Empty slate returns empty list
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from src.prediction.signal_router import SignalRouter, _dedup_sort
from src.prediction.strategy_base import SignalResult, StrategyBase


# ---------------------------------------------------------------------------
# Minimal concrete strategies for testing
# ---------------------------------------------------------------------------

def _result(player_id: str, stat: str, direction: str, edge: float,
            strategy: str = "test") -> SignalResult:
    return SignalResult(
        strategy=strategy,
        player_id=player_id,
        stat=stat,
        game_id="g1",
        direction=direction,
        model_prob=0.55,
        edge=edge,
        kelly_fraction=max(edge, 0.01),
        confidence=0.8,
    )


class FixedStrategy(StrategyBase):
    """Returns a fixed list of signals regardless of input."""

    name = "fixed"

    def __init__(self, signals: List[SignalResult], cfg=None) -> None:
        super().__init__(cfg)
        self._signals = signals

    def generate_signals(self, slate: List[Dict[str, Any]]) -> List[SignalResult]:
        return list(self._signals)


class BrokenStrategy(StrategyBase):
    """Always raises to test fault tolerance."""

    name = "broken"

    def generate_signals(self, slate: List[Dict[str, Any]]) -> List[SignalResult]:
        raise RuntimeError("intentional failure")


# ---------------------------------------------------------------------------
# SignalRouter tests
# ---------------------------------------------------------------------------

class TestSignalRouterRegister:
    def test_register_returns_router(self) -> None:
        router = SignalRouter()
        strat = FixedStrategy([])
        result = router.register(strat)
        assert result is router

    def test_registered_names(self) -> None:
        router = SignalRouter()
        router.register(FixedStrategy([], {"min_edge": 0.0}))
        assert "fixed" in router.registered()

    def test_multiple_strategies(self) -> None:
        router = SignalRouter()
        strat_a = FixedStrategy([])
        strat_a.name = "alpha"
        strat_b = FixedStrategy([])
        strat_b.name = "beta"
        router.register(strat_a).register(strat_b)
        assert set(router.registered()) == {"alpha", "beta"}


class TestSignalRouterRoute:
    def test_empty_slate_empty_result(self) -> None:
        router = SignalRouter()
        signals = router.route([])
        assert signals == []

    def test_no_strategies_empty_result(self) -> None:
        router = SignalRouter()
        signals = router.route([{"game_id": "g1"}])
        assert signals == []

    def test_signals_sorted_by_edge_descending(self) -> None:
        sigs = [
            _result("p1", "pts", "over", edge=0.05),
            _result("p2", "reb", "over", edge=0.12),
            _result("p3", "ast", "under", edge=0.08),
        ]
        # Give each signal a different player so no dedup
        strat = FixedStrategy(sigs, {"min_edge": 0.0})
        router = SignalRouter().register(strat)
        out = router.route([])
        edges = [s.edge for s in out]
        assert edges == sorted(edges, reverse=True)

    def test_below_min_edge_filtered(self) -> None:
        sigs = [_result("p1", "pts", "over", edge=0.01)]  # below default 0.04
        strat = FixedStrategy(sigs)  # uses default min_edge=0.04
        router = SignalRouter().register(strat)
        out = router.route([])
        assert all(s.edge >= 0.04 for s in out)

    def test_broken_strategy_does_not_crash(self) -> None:
        good_sig = _result("p1", "pts", "over", edge=0.06)
        good = FixedStrategy([good_sig], {"min_edge": 0.0})
        broken = BrokenStrategy()
        router = SignalRouter().register(broken).register(good)
        out = router.route([])
        assert len(out) == 1
        assert out[0].player_id == "p1"

    def test_returns_signal_result_instances(self) -> None:
        sig = _result("p1", "pts", "over", edge=0.06)
        strat = FixedStrategy([sig], {"min_edge": 0.0})
        router = SignalRouter().register(strat)
        out = router.route([])
        assert all(isinstance(s, SignalResult) for s in out)


# ---------------------------------------------------------------------------
# _dedup_sort tests
# ---------------------------------------------------------------------------

class TestDedupSort:
    def test_keeps_highest_edge_per_key(self) -> None:
        sigs = [
            _result("p1", "pts", "over", edge=0.05),
            _result("p1", "pts", "over", edge=0.10),  # same key, higher edge
        ]
        out = _dedup_sort(sigs)
        assert len(out) == 1
        assert out[0].edge == pytest.approx(0.10)

    def test_different_directions_not_deduped(self) -> None:
        sigs = [
            _result("p1", "pts", "over", edge=0.06),
            _result("p1", "pts", "under", edge=0.07),
        ]
        out = _dedup_sort(sigs)
        assert len(out) == 2

    def test_different_stats_not_deduped(self) -> None:
        sigs = [
            _result("p1", "pts", "over", edge=0.06),
            _result("p1", "reb", "over", edge=0.06),
        ]
        out = _dedup_sort(sigs)
        assert len(out) == 2

    def test_sorted_descending(self) -> None:
        sigs = [
            _result("p1", "pts", "over", edge=0.04),
            _result("p2", "reb", "over", edge=0.09),
            _result("p3", "ast", "under", edge=0.06),
        ]
        out = _dedup_sort(sigs)
        assert [s.edge for s in out] == [0.09, 0.06, 0.04]

    def test_empty_input(self) -> None:
        assert _dedup_sort([]) == []
