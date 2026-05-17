"""strategy_base.py — Abstract base for all alpha strategies (Phases 24–30).

Each strategy implements generate_signals() and returns a list of SignalResult.
signal_router.py collects them all; bet_selector.py filters + sizes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SignalResult:
    strategy: str           # e.g. "vol_arb", "pairs", "cross_market"
    player_id: str
    stat: str               # "pts", "reb", "ast", ...
    game_id: str
    direction: str          # "over" | "under"
    model_prob: float
    edge: float             # model_prob - implied_prob
    kelly_fraction: float   # pre-correlation kelly
    confidence: float       # ensemble agreement [0, 1]
    meta: Dict[str, Any] = field(default_factory=dict)


class StrategyBase(ABC):
    """Base class for all alpha-generating strategies."""

    name: str = "base"

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}

    @abstractmethod
    def generate_signals(self, slate: List[Dict[str, Any]]) -> List[SignalResult]:
        """Return signals for today's slate.

        Args:
            slate: list of dicts from run_daily_slate.py top_edges output.

        Returns:
            List of SignalResult — may be empty if no edge found.
        """

    def min_edge(self) -> float:
        return float(self.config.get("min_edge", 0.04))

    def max_kelly(self) -> float:
        return float(self.config.get("max_kelly", 0.25))

    def filter(self, signals: List[SignalResult]) -> List[SignalResult]:
        """Drop signals below min_edge or kelly threshold."""
        return [
            s for s in signals
            if s.edge >= self.min_edge() and s.kelly_fraction > 0
        ]
