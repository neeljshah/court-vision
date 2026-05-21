"""
pinnacle_gate.py — Pinnacle no-vig converter.

Strips bookmaker margin from an over/under American odds pair to produce
fair (vig-free) probabilities suitable for edge calculation.

Public API
----------
    strip_vig(over_odds, under_odds) -> dict
    american_to_implied(odds)        -> float
"""
from __future__ import annotations

__all__ = ["strip_vig", "american_to_implied"]


def american_to_implied(odds: int) -> float:
    """Convert American odds to implied (raw, with vig) probability."""
    if odds >= 0:
        return 100.0 / (odds + 100.0)
    return abs(odds) / (abs(odds) + 100.0)


def strip_vig(over_odds: int, under_odds: int) -> dict:
    """
    Remove bookmaker margin from an over/under American odds pair.

    Uses the standard additive normalization method: compute implied probs
    for each side, divide by their sum to remove vig.

    Args:
        over_odds:  American odds for the Over outcome (e.g. -110, +100).
        under_odds: American odds for the Under outcome.

    Returns:
        {
            "over_prob":  float,  # vig-free P(over)
            "under_prob": float,  # vig-free P(under); == 1 - over_prob
            "vig":        float,  # total margin removed, e.g. 0.0476 for -110/-110
        }

    Example:
        >>> strip_vig(-110, -110)
        {'over_prob': 0.5, 'under_prob': 0.5, 'vig': 0.0476...}
    """
    p_over = american_to_implied(over_odds)
    p_under = american_to_implied(under_odds)
    total = p_over + p_under
    if total <= 0:
        return {"over_prob": 0.5, "under_prob": 0.5, "vig": 0.0}
    vig = round(total - 1.0, 6)
    over_prob = round(p_over / total, 6)
    under_prob = round(p_under / total, 6)
    return {"over_prob": over_prob, "under_prob": under_prob, "vig": vig}
