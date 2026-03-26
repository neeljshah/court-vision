"""
edge_detector.py — Queries all model outputs and compares projections to live lines.

Finds +EV bets, ranks by expected value, applies Kelly sizing.

Public API
----------
    EdgeDetector()
    detector.find_edges(game_ids, min_ev)  -> list[BetEdge]
    detector.rank_edges(edges)             -> list[BetEdge]
    detector.find_today_edges()            -> list[BetEdge]
"""

from __future__ import annotations

import json
import logging
import math
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

log = logging.getLogger(__name__)

# Standard vig on -110 lines
_JUICE           = 0.0909   # juice on standard -110 line
_MIN_EV          = 0.03     # minimum EV to flag
_KELLY_FRACTION  = 0.25     # use quarter Kelly for risk management
_KELLY_MAX       = 0.10     # never bet more than 10% of bankroll

# Model agreement threshold
_HIGH_AGREEMENT  = 3   # 3+ models agree = high confidence
_MED_AGREEMENT   = 2


@dataclass
class BetEdge:
    player_id: str
    player_name: str
    stat: str           # 'pts', 'reb', 'ast', etc.
    direction: str      # 'over' / 'under'
    line: float         # book line
    projection: float   # model projection
    ev: float           # expected value (fraction)
    kelly_fraction: float
    confidence: str     # 'high' / 'medium' / 'low'
    model_agreement: int
    game_id: str = ""
    date: str = ""
    team: str = ""
    opp_team: str = ""
    dnp_prob: float = 0.0
    edge_sources: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "player_id":      self.player_id,
            "player_name":    self.player_name,
            "stat":           self.stat,
            "direction":      self.direction,
            "line":           self.line,
            "projection":     round(self.projection, 2),
            "ev":             round(self.ev, 4),
            "kelly_fraction": round(self.kelly_fraction, 4),
            "confidence":     self.confidence,
            "model_agreement": self.model_agreement,
            "game_id":        self.game_id,
            "date":           self.date,
            "team":           self.team,
            "opp_team":       self.opp_team,
        }


def _compute_ev(projection: float, line: float, is_over: bool, juice: float = _JUICE) -> float:
    """
    Compute expected value for an over/under bet.

    Args:
        projection:  model's projection for the stat
        line:        book line
        is_over:     True for over bet, False for under
        juice:       vig fraction (e.g. 0.0909 for -110)

    Returns:
        EV as a fraction of bet amount (positive = profitable)
    """
    # Estimate win probability from projection vs line
    # Using a simple normal distribution model
    import math

    # Standard deviation proxy (vary by stat)
    # pts: ~5 pts std, reb: ~2.5, ast: ~2
    std_map = {"pts": 5.0, "reb": 2.5, "ast": 2.0, "fg3m": 1.5,
               "stl": 0.8, "blk": 0.8, "tov": 1.2}

    # Approximate std from line magnitude
    std = max(abs(projection) * 0.3, 1.0)

    # P(over) using normal CDF approximation
    z = (projection - line) / max(std, 0.5)
    # Sigmoid approximation of normal CDF
    p_over = 1.0 / (1.0 + math.exp(-1.702 * z))

    win_prob = p_over if is_over else (1.0 - p_over)
    # Payout odds: -110 = 10/11 payout
    payout   = (1.0 - juice)
    ev       = win_prob * payout - (1.0 - win_prob) * 1.0
    return float(ev)


def _kelly_size(ev: float, win_prob: float) -> float:
    """
    Kelly criterion: f* = (b*p - q) / b
    where b = payout odds, p = win prob, q = 1-p
    Fractional Kelly: multiply by _KELLY_FRACTION.
    """
    if ev <= 0:
        return 0.0
    b = 1.0 - _JUICE  # ~0.909 for -110
    q = 1.0 - win_prob
    kelly = (b * win_prob - q) / b
    kelly = kelly * _KELLY_FRACTION
    return float(min(max(kelly, 0.0), _KELLY_MAX))


class EdgeDetector:
    """Finds and ranks betting edges by comparing model projections to book lines."""

    def __init__(self, season: str = "2024-25") -> None:
        self.season = season
        self._min_ev = _MIN_EV

    def find_edges(
        self,
        player_predictions: list,
        min_ev: float = _MIN_EV,
    ) -> list[BetEdge]:
        """
        Find edges from a list of PlayerPrediction objects.

        Args:
            player_predictions: List of PlayerPrediction from orchestrator.
            min_ev:             Minimum EV threshold to flag.

        Returns:
            List of BetEdge objects sorted by EV descending.
        """
        edges: list[BetEdge] = []
        self._min_ev = min_ev

        for pred in player_predictions:
            if not hasattr(pred, "book_lines") or not pred.book_lines:
                continue

            # Skip if player likely DNP
            dnp_prob = float(getattr(pred, "dnp_prob", 0.05))
            if dnp_prob > 0.6:
                log.debug("Skip %s — dnp_prob=%.2f", pred.player_name, dnp_prob)
                continue

            for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
                proj = float(getattr(pred, f"proj_{stat}", 0.0) or 0.0)
                line = float(pred.book_lines.get(stat, float("nan")))

                if proj <= 0 or (isinstance(line, float) and line != line):
                    continue

                # Over edge
                ev_over  = _compute_ev(proj, line, is_over=True)
                ev_under = _compute_ev(proj, line, is_over=False)

                for direction, ev in (("over", ev_over), ("under", ev_under)):
                    if ev < min_ev:
                        continue

                    import math
                    std = max(proj * 0.3, 1.0)
                    z = (proj - line) / max(std, 0.5)
                    p_over = 1.0 / (1.0 + math.exp(-1.702 * z))
                    win_prob = p_over if direction == "over" else (1.0 - p_over)
                    kelly = _kelly_size(ev, win_prob)

                    # Model agreement count
                    agreement = self._count_model_agreement(pred, stat, line, direction)

                    confidence = (
                        "high"   if ev > 0.06 and agreement >= _HIGH_AGREEMENT else
                        "medium" if ev > 0.03 and agreement >= _MED_AGREEMENT  else
                        "low"
                    )

                    edge = BetEdge(
                        player_id      = str(getattr(pred, "player_id", "")),
                        player_name    = getattr(pred, "player_name", ""),
                        stat           = stat,
                        direction      = direction,
                        line           = line,
                        projection     = proj,
                        ev             = ev,
                        kelly_fraction = kelly,
                        confidence     = confidence,
                        model_agreement = agreement,
                        game_id        = getattr(pred, "game_id", ""),
                        date           = getattr(pred, "date", ""),
                        team           = getattr(pred, "team", ""),
                        opp_team       = getattr(pred, "opp_team", ""),
                        dnp_prob       = dnp_prob,
                    )
                    edges.append(edge)

        return self.rank_edges(edges)

    def _count_model_agreement(self, pred, stat: str, line: float, direction: str) -> int:
        """Count how many signals agree with this direction."""
        count = 0
        proj = float(getattr(pred, f"proj_{stat}", 0.0) or 0.0)

        # Agreement from raw projection
        if direction == "over" and proj > line:
            count += 1
        elif direction == "under" and proj < line:
            count += 1

        # Agreement from matchup adjustment
        matchup_adj = float(getattr(pred, "matchup_adj", 1.0))
        if direction == "over" and matchup_adj > 1.0:
            count += 1
        elif direction == "under" and matchup_adj < 1.0:
            count += 1

        # Agreement from usage adjustment
        usage_adj = float(getattr(pred, "usage_adj", 1.0))
        if direction == "over" and usage_adj > 1.05:
            count += 1
        elif direction == "under" and usage_adj < 0.95:
            count += 1

        return count

    def rank_edges(self, edges: list[BetEdge]) -> list[BetEdge]:
        """Rank edges by EV descending, with confidence tiebreaker."""
        conf_score = {"high": 3, "medium": 2, "low": 1}
        return sorted(
            edges,
            key=lambda e: (e.ev, conf_score.get(e.confidence, 1)),
            reverse=True,
        )

    def find_today_edges(self, min_ev: float = _MIN_EV) -> list[BetEdge]:
        """
        Full today pipeline: fetch today's predictions, find edges.
        Returns ranked list of BetEdge objects.
        """
        try:
            from src.pipeline.prediction_orchestrator import PredictionOrchestrator
            orch = PredictionOrchestrator(season=self.season)
            predictions = orch.predict_today()
            return self.find_edges(predictions, min_ev=min_ev)
        except Exception as e:
            log.error("find_today_edges failed: %s", e)
            return []

    def format_edge_report(self, edges: list[BetEdge]) -> str:
        """Format edges as a human-readable report."""
        if not edges:
            return "No edges found above minimum EV threshold."

        lines = ["=== TODAY'S EDGES (ranked by EV) ===", ""]
        for i, edge in enumerate(edges[:20], 1):
            lines.append(
                f"{i:2d}. {edge.player_name} {edge.stat.upper()} {edge.direction.upper()} "
                f"{edge.line} | Proj: {edge.projection:.1f} | EV: {edge.ev:.1%} | "
                f"Kelly: {edge.kelly_fraction:.1%} | {edge.confidence.upper()} | "
                f"Models: {edge.model_agreement}"
            )
        return "\n".join(lines)
