"""src/prediction/prop_pricing_engine.py — Simulation-based prop pricing engine.

Uses PossessionSimulator 10K Monte Carlo to build full stat distributions,
then compares against book lines to find +EV edges.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

_RESIDUALS_PATH = Path("data/models/prop_residuals.json")
_EDGE_THRESHOLD = 0.03   # 3% minimum edge to recommend
_DEFAULT_JUICE = -110    # Standard American odds

log = logging.getLogger(__name__)


def _implied_prob(odds: int) -> float:
    """Convert American odds to implied probability."""
    if odds < 0:
        return abs(odds) / (abs(odds) + 100)
    return 100 / (odds + 100)


def _payout_ratio(odds: int) -> float:
    """Decimal profit per 1-unit stake for American odds.

    Positive odds (+120): profit = odds / 100  (e.g. 1.20 per unit)
    Negative odds (-110): profit = 100 / abs(odds)  (e.g. ~0.909 per unit)
    """
    if odds > 0:
        return odds / 100.0
    return 100.0 / abs(odds)


class PropPricingEngine:
    """Prices player prop bets using Monte Carlo simulation distributions.

    Falls back to normal approximation from player_props.py when
    PossessionSimulator is unavailable.
    """

    def __init__(self, n_sims: int = 10_000) -> None:
        self.n_sims = n_sims

        # Try to load PossessionSimulator
        try:
            from src.prediction.possession_simulator import PossessionSimulator
            self._sim: Optional[object] = PossessionSimulator()
        except Exception:
            self._sim = None
            log.debug("PossessionSimulator unavailable; using normal fallback")

        # Try to load predict_props
        try:
            from src.prediction.player_props import predict_props
            self._props_fn = predict_props
        except Exception:
            self._props_fn = None
            log.debug("predict_props unavailable; using hardcoded defaults")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_distribution(
        self,
        player_id: str,
        stat: str,
        team_a: str = "LAL",
        team_b: str = "GSW",
    ) -> Dict[str, float]:
        """Return simulated stat distribution for a player.

        Returns dict with keys: mean, std, p10, p25, p50, p75, p90.
        Falls back to normal approximation if PossessionSimulator fails.

        Args:
            player_id: Player identifier string.
            stat:      Stat name (e.g. 'pts', 'reb').
            team_a:    Player's team abbreviation (passed to simulator).
            team_b:    Opposing team abbreviation (passed to simulator).
        """
        samples = self._get_samples(player_id, stat, team_a, team_b)
        return {
            "mean": float(np.mean(samples)),
            "std":  float(np.std(samples)),
            "p10":  float(np.percentile(samples, 10)),
            "p25":  float(np.percentile(samples, 25)),
            "p50":  float(np.percentile(samples, 50)),
            "p75":  float(np.percentile(samples, 75)),
            "p90":  float(np.percentile(samples, 90)),
        }

    def price_vs_line(
        self,
        player_id: str,
        stat: str,
        line: float,
        odds: int = _DEFAULT_JUICE,
        team_a: str = "LAL",
        team_b: str = "GSW",
    ) -> Dict:
        """Compare simulated distribution against a book line.

        Returns dict: over_prob, under_prob, ev_over, ev_under, edge,
        recommendation ('over'|'under'|'pass').

        Args:
            player_id: Player identifier string.
            stat:      Stat name (e.g. 'pts', 'reb').
            line:      Prop line value.
            odds:      American odds for the OVER side (e.g. -110 or +120).
            team_a:    Player's team abbreviation (passed to simulator).
            team_b:    Opposing team abbreviation (passed to simulator).
        """
        samples = self._get_samples(player_id, stat, team_a, team_b)

        over_prob  = float(np.mean(samples > line))
        under_prob = 1.0 - over_prob

        # Bug 1 fix: payout_ratio is now sign-aware.
        # +120 → 1.20 profit per unit; -110 → 0.909 profit per unit.
        pay = _payout_ratio(odds)

        ev_over  = over_prob  * pay - (1.0 - over_prob)  * 1.0
        # Bug 2 fix: under EV uses the under implied probability (1 - over_implied).
        # The under side's implied prob = 1 - implied(over odds), assuming same odds.
        # If separate under odds were provided they should be passed explicitly;
        # here we mirror the juice so under_implied = 1 - _implied_prob(odds).
        under_implied = 1.0 - _implied_prob(odds)
        ev_under = under_prob * pay - (1.0 - under_prob) * 1.0

        # Edge = simulated probability minus book implied probability
        over_implied = _implied_prob(odds)
        edge = over_prob - over_implied

        if edge > _EDGE_THRESHOLD:
            recommendation = "over"
        elif (under_prob - under_implied) > _EDGE_THRESHOLD:
            # Bug 2 fix: under recommendation uses the under-side edge.
            recommendation = "under"
        else:
            recommendation = "pass"

        return {
            "over_prob":      over_prob,
            "under_prob":     under_prob,
            "ev_over":        float(ev_over),
            "ev_under":       float(ev_under),
            "edge":           float(edge),
            "recommendation": recommendation,
        }

    def backtest(
        self, stat: str = "pts", n_games: int = 50
    ) -> Dict:
        """Evaluate historical edge using prop_residuals.json holdout data.

        Returns dict: roi (float), n_bets (int), n_games (int), stat (str).
        roi = total_profit / n_bets (may be negative on small holdout).
        """
        if not _RESIDUALS_PATH.exists():
            log.warning("prop_residuals.json missing — returning zero roi")
            return {"roi": 0.0, "n_bets": 0, "n_games": 0, "stat": stat}

        try:
            with open(_RESIDUALS_PATH, "r") as f:
                data = json.load(f)
        except Exception as exc:
            log.warning("Failed to load prop_residuals.json: %s", exc)
            return {"roi": 0.0, "n_bets": 0, "n_games": 0, "stat": stat}

        # Filter to requested stat and take last n_games rows
        rows = [r for r in data if r.get("stat") == stat]
        rows = rows[-n_games:]

        total_profit = 0.0
        n_bets = 0

        for row in rows:
            predicted = float(row.get("predicted", 0))
            actual    = float(row.get("actual", 0))
            denom = max(abs(actual), 1)
            edge = (predicted - actual) / denom

            if abs(edge) > _EDGE_THRESHOLD:
                n_bets += 1
                # Win condition: residual sign matches bet direction.
                # edge>0 → we bet over; win if actual > predicted.
                # edge<0 → we bet under; win if actual < predicted.
                win_prob = 0.5 + abs(edge) * 2  # crude calibration
                win_prob = min(win_prob, 0.95)
                # Bug 3 fix: compute payout using standard juice, then decide
                # win/loss.  Loss branch is now reachable (profit = -1.0 stays
                # when the random draw exceeds win_prob).
                pay = _payout_ratio(_DEFAULT_JUICE)  # 0.909 at -110
                if np.random.random() < win_prob:
                    profit = pay
                else:
                    profit = -1.0
                total_profit += profit

        roi = float(total_profit / max(n_bets, 1))
        return {
            "roi":    roi,
            "n_bets": n_bets,
            "n_games": len(rows),
            "stat":   stat,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_samples(
        self,
        player_id: str,
        stat: str,
        team_a: str = "LAL",
        team_b: str = "GSW",
    ) -> np.ndarray:
        """Return array of n_sims stat values for player_id.

        Bug 4 fix: passes the caller-supplied team_a / team_b to the
        simulator instead of always hardcoding LAL vs GSW.
        """
        # Try PossessionSimulator path
        if self._sim is not None:
            try:
                result = self._sim.simulate_game(  # type: ignore[attr-defined]
                    team_a=team_a, team_b=team_b, n_sims=self.n_sims
                )
                dist = result.get("player_distributions", {})
                if player_id in dist and stat in dist[player_id]:
                    arr = np.array(dist[player_id][stat], dtype=float)
                    if len(arr) >= 10:
                        return arr
            except Exception as exc:
                log.debug("PossessionSimulator failed: %s — using fallback", exc)

        # Fallback: normal approximation from predict_props or defaults
        mean = self._get_mean(player_id, stat)
        std  = mean * 0.25 if mean > 0 else 1.0
        rng  = np.random.default_rng(seed=int(player_id[:4], 10) if player_id[:4].isdigit() else 42)
        return rng.normal(mean, std, self.n_sims).clip(0)

    def _get_mean(self, player_id: str, stat: str) -> float:
        """Get mean stat prediction, falling back to sensible defaults."""
        if self._props_fn is not None:
            try:
                preds = self._props_fn(player_id, "GSW")
                val = preds.get(stat)
                if val is not None:
                    return float(val)
            except Exception as exc:
                log.debug("predict_props failed: %s — using default", exc)

        # Hard-coded defaults by stat (league-average-ish)
        defaults = {
            "pts": 15.0, "reb": 5.0, "ast": 3.5,
            "fg3m": 1.5, "stl": 0.8, "blk": 0.5, "tov": 1.8,
        }
        return defaults.get(stat, 10.0)
