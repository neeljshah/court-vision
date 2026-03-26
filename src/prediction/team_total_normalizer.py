"""
team_total_normalizer.py — M70: Scale player projections to match game total.

HIGH PRIORITY — Fixes systematic bias where raw prop models sum to wrong totals.

Method: Sum projected points for all expected players on each team.
If sum != predicted_team_points (total/2 ± spread), scale proportionally.
Respect star usage hierarchy — scale role players more than stars.

Public API
----------
    normalise_team_totals(preds, home_team, away_team, predicted_total) -> list[PlayerPrediction]
    compute_team_sum(preds, team) -> float
    get_normalization_factor(team_sum, target_team_pts) -> float
"""

from __future__ import annotations

import logging
import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.pipeline.prediction_orchestrator import PlayerPrediction

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

log = logging.getLogger(__name__)

# Stars get much less scaling — their projections are well-calibrated
# Role players absorb more of the correction
_STAR_MIN_THRESHOLD = 28.0    # players averaging >= N min are "stars"
_STAR_SCALE_FACTOR  = 0.25    # stars get 25% of the correction
_ROLE_SCALE_FACTOR  = 1.00    # role players get 100%
_MIN_NORMALIZATION  = 0.80    # never scale below 80% of original projection
_MAX_NORMALIZATION  = 1.25    # never scale above 125%


def compute_team_sum(preds: list, team: str) -> float:
    """Sum projected points for all players on a team."""
    total = 0.0
    for p in preds:
        if getattr(p, "team", "") == team:
            total += float(getattr(p, "proj_pts", 0) or 0)
    return total


def get_normalization_factor(team_sum: float, target_team_pts: float) -> float:
    """Compute normalization factor to scale team total."""
    if team_sum <= 0:
        return 1.0
    factor = target_team_pts / team_sum
    # Clip to reasonable range
    return max(_MIN_NORMALIZATION, min(_MAX_NORMALIZATION, factor))


def normalise_team_totals(
    preds: list,
    home_team: str,
    away_team: str,
    predicted_total: float,
    spread: float = 0.0,
) -> list:
    """
    Scale all player proj_pts so each team sums to expected team total.

    Args:
        preds:           List of PlayerPrediction objects.
        home_team:       Home team abbreviation.
        away_team:       Away team abbreviation.
        predicted_total: Predicted combined total (e.g. 220.5).
        spread:          Predicted spread (positive = home favored).

    Returns:
        Modified list of PlayerPrediction with normalised proj_pts.
    """
    # Target team totals from game prediction
    # Home pts = total/2 + spread/2, Away pts = total/2 - spread/2
    home_target = predicted_total / 2 + spread / 2
    away_target = predicted_total / 2 - spread / 2

    # Ensure at least some pts per team
    home_target = max(90.0, home_target)
    away_target = max(90.0, away_target)

    for team, target in ((home_team, home_target), (away_team, away_target)):
        team_preds = [p for p in preds if getattr(p, "team", "") == team]
        if not team_preds:
            continue

        team_sum = sum(float(getattr(p, "proj_pts", 0) or 0) for p in team_preds)
        if team_sum < 5:
            log.debug("Team %s sum too low (%.1f) — skipping normalisation", team, team_sum)
            continue

        factor = get_normalization_factor(team_sum, target)

        if abs(factor - 1.0) < 0.02:
            continue  # close enough — skip

        log.debug("Team %s: sum=%.1f target=%.1f factor=%.4f",
                  team, team_sum, target, factor)

        # Identify stars vs role players by projected minutes
        avg_proj_min = sum(float(getattr(p, "proj_min", 24) or 24)
                          for p in team_preds) / max(len(team_preds), 1)

        for p in team_preds:
            proj_min = float(getattr(p, "proj_min", 24) or 24)
            is_star  = proj_min >= _STAR_MIN_THRESHOLD

            # Stars get smaller correction; role players get full correction
            scale_weight = _STAR_SCALE_FACTOR if is_star else _ROLE_SCALE_FACTOR
            effective_factor = 1.0 + (factor - 1.0) * scale_weight

            # Apply normalisation
            old_pts = float(getattr(p, "proj_pts", 0) or 0)
            new_pts = old_pts * effective_factor
            p.proj_pts = round(max(0.0, new_pts), 2)

    return preds
