"""divergence_rank.py -- rank best-bet cards by calibrated model-vs-market divergence.

BB-Q1 (P0 keystone): replaces raw model_prob as the sort key with:

    divergence_score = |model_prob - market_prob| / sigma

so a card with stronger edge against the market always outranks a card with a
higher raw model_prob at the same tier.

RAILS (all binding):
  * UNITS not $. No dollar / ROI / PnL key anywhere.
  * sigma=None path must not raise (falls back to DEFAULT_SIGMA).
  * Tiers ranked via the same _TIER_FLOORS registry as pm_trading.policy.
  * Pure module: no IO, no network, no global state mutation.
  * <= 300 LOC; ASCII only.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

# Tier ordering: "A" is strongest -> lowest rank_index (sorts first).
_TIER_ORDER: Dict[str, int] = {"A": 0, "B": 1, "C": 2}
_UNKNOWN_TIER_RANK: int = 99

# Default sigma used when caller passes sigma=None or sigma<=0.
# 5% is a reasonable prior spread for a well-calibrated binary market.
DEFAULT_SIGMA: float = 0.05


def divergence_score(
    model_prob: float,
    market_prob: float,
    sigma: Optional[float] = None,
) -> float:
    """Compute |model_prob - market_prob| / sigma.

    Parameters
    ----------
    model_prob:
        Calibrated model probability (0..1). Must be finite.
    market_prob:
        Devigged market implied probability (0..1). Must be finite.
    sigma:
        Optional uncertainty / spread. When None or <= 0, DEFAULT_SIGMA is used.
        Passing sigma=None is safe and will not raise.

    Returns
    -------
    float
        Non-negative divergence score. Returns 0.0 on any bad input rather
        than raising, so callers can safely sort.
    """
    try:
        mp = float(model_prob)
        mk = float(market_prob)
    except (TypeError, ValueError):
        return 0.0

    if not math.isfinite(mp) or not math.isfinite(mk):
        return 0.0

    # Clamp probabilities to a valid range (defensive; callers should pass valid probs)
    if not (0.0 <= mp <= 1.0) or not (0.0 <= mk <= 1.0):
        return 0.0

    sig: float
    if sigma is None or not isinstance(sigma, (int, float)):
        sig = DEFAULT_SIGMA
    else:
        try:
            sig = float(sigma)
        except (TypeError, ValueError):
            sig = DEFAULT_SIGMA
    if not math.isfinite(sig) or sig <= 0.0:
        sig = DEFAULT_SIGMA

    return abs(mp - mk) / sig


def _tier_rank(card: Dict[str, Any]) -> int:
    """Return sort key for tier: lower = higher priority.

    Reads 'tier' from the card dict. Cards with no tier or unrecognised
    tier sort after known tiers.
    """
    tier_str = card.get("tier") or ""
    return _TIER_ORDER.get(str(tier_str).upper(), _UNKNOWN_TIER_RANK)


def rank_cards(
    cards: List[Dict[str, Any]],
    *,
    default_sigma: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Attach 'divergence_score' to each card and sort by (tier_rank, -divergence_score).

    Within the same tier the card with the larger |model_prob - market_prob| / sigma
    ranks first -- it has the strongest edge against the market, which is the honest
    selection criterion.

    Parameters
    ----------
    cards:
        Mutable list of card dicts. Each card should have:
          - 'tier'          (str "A"/"B"/"C" or missing)
          - 'model_prob'    (float or missing)
          - 'market_prob'   (float or missing)
          - 'sigma'         (float, optional; per-card override)
        Cards missing model_prob/market_prob receive divergence_score=0.0.

    default_sigma:
        Sigma to use when neither the card nor the caller specifies one.
        Falls back to module DEFAULT_SIGMA (0.05).

    Returns
    -------
    List[Dict[str, Any]]
        The same card objects with 'divergence_score' set, sorted by
        (tier_rank ascending, divergence_score descending).

    Notes
    -----
    - Does NOT produce any dollar / ROI / PnL field.
    - sigma=None path is safe; uses DEFAULT_SIGMA.
    - Empty input returns [].
    """
    if not cards:
        return []

    resolved_default_sigma: float = (
        float(default_sigma)
        if (default_sigma is not None and math.isfinite(float(default_sigma or 0.0)) and (float(default_sigma) > 0.0))
        else DEFAULT_SIGMA
    )

    for card in cards:
        mp = card.get("model_prob")
        mk = card.get("market_prob")

        if mp is None or mk is None:
            card["divergence_score"] = 0.0
            continue

        # Per-card sigma overrides the default; None is safe.
        card_sigma = card.get("sigma")
        effective_sigma: Optional[float]
        if card_sigma is not None:
            try:
                effective_sigma = float(card_sigma)
            except (TypeError, ValueError):
                effective_sigma = resolved_default_sigma
        else:
            effective_sigma = resolved_default_sigma

        card["divergence_score"] = divergence_score(mp, mk, effective_sigma)

    cards.sort(key=lambda c: (_tier_rank(c), -c.get("divergence_score", 0.0)))
    return cards


__all__ = [
    "DEFAULT_SIGMA",
    "divergence_score",
    "rank_cards",
]
