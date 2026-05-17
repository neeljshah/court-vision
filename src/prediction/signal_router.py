"""signal_router.py — Collects signals from all registered strategies.

Usage:
    router = SignalRouter()
    router.register(VolArbStrategy())
    router.register(PairsStrategy())
    signals = router.route(slate)   # deduped, sorted by edge desc

bet_selector.py calls router.route() instead of calling strategies directly.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Type

from src.prediction.strategy_base import SignalResult, StrategyBase

log = logging.getLogger(__name__)


class SignalRouter:
    def __init__(self) -> None:
        self._strategies: List[StrategyBase] = []

    def register(self, strategy: StrategyBase) -> "SignalRouter":
        self._strategies.append(strategy)
        return self

    def route(self, slate: List[Dict]) -> List[SignalResult]:
        """Run all strategies, deduplicate, sort by edge descending."""
        all_signals: List[SignalResult] = []
        for strat in self._strategies:
            try:
                raw = strat.generate_signals(slate)
                filtered = strat.filter(raw)
                all_signals.extend(filtered)
                log.debug("%s: %d/%d signals passed filter", strat.name, len(filtered), len(raw))
            except Exception:
                log.exception("Strategy %s failed — skipping", strat.name)

        return _dedup_sort(all_signals)

    def registered(self) -> List[str]:
        return [s.name for s in self._strategies]


def _dedup_sort(signals: List[SignalResult]) -> List[SignalResult]:
    """Keep highest-edge signal per (player_id, stat, direction) tuple."""
    seen: Dict[tuple, SignalResult] = {}
    for s in signals:
        key = (s.player_id, s.stat, s.direction)
        if key not in seen or s.edge > seen[key].edge:
            seen[key] = s
    return sorted(seen.values(), key=lambda s: s.edge, reverse=True)
