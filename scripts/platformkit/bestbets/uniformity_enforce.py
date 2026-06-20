"""uniformity_enforce.py -- post-filter that demotes a sport whose model_prob
values collapse to a uniform/constant fallback pattern.

QA iter 1/8 fabricated-edge P1: a board where 11 MLB cards carry only 2 distinct
model_prob values (0.5345 / 0.4655) is NOT individualized calibrated divergence.
Serving it as Tier-A/B edge is a fabricated-edge violation.

THIS MODULE applies the existing mlb_prob_uniformity_guard.check_uniformity
detection as a post-filter over the full card list.  For each sport that
triggers FALLBACK_SUSPECTED it relabels every card so the board is NEVER
presented as a calibrated edge:

  * edge_claimed        -> False
  * tier                -> 'C'   (never ranked Tier-A/B calibrated divergence)
  * flat_prior          -> True  (machine-readable flag for the UI)
  * honest_note         -> "model unavailable -- base rate only, ..."
  * degenerate_model    -> True  (reuse the UI-facing key from degenerate_guard)

A small slate (< MIN_CARDS_PER_SPORT) is left untouched:
1-2 game cards sharing one prob is not evidence of a flat-prior collapse.

Integration points
------------------
  * Call enforce_uniformity(cards) inside the runner/build_cards path AFTER
    card construction and BEFORE caching / serving.
  * degenerate_guard.mark_degenerate_sports already handles the <= 2 distinct
    values threshold; this module adds a second layer specifically keyed on the
    constant-fallback uniformity signal so both guards run independently and
    their demotion is idempotent when both fire.

RAILS:
  - Pure: no IO, no network, no global mutable state.
  - Mutates the freshly built card dicts in-place (owned by the caller) and
    returns the same list.  Never raises.
  - ASCII only; <= 300 LOC.
  - No $ / roi / pnl / bankroll / profit / stake / usd / dollar field.
  - Per-file test:
      cd /c/Users/neelj/nba-ai-system && python -m pytest \\
        scripts/platformkit/bestbets/test_uniformity_enforce.py -q
"""
from __future__ import annotations

from typing import Any, Dict, List

# -- Constants -----------------------------------------------------------------

#: Minimum cards per sport before a uniformity verdict is trusted.
MIN_CARDS_PER_SPORT: int = 3

#: Honest label written onto every demoted card (ASCII only).
FLAT_PRIOR_NOTE: str = (
    "model unavailable -- base rate only, not a calibrated per-game edge"
)

#: Uniformity threshold forwarded to check_uniformity (cards sharing same prob).
UNIFORM_N_THRESHOLD: int = 3


# -- Helpers -------------------------------------------------------------------

def _group_by_sport(
    cards: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Return cards bucketed by sport string.  Non-dict entries are skipped."""
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for c in cards:
        if isinstance(c, dict):
            groups.setdefault(str(c.get("sport", "")), []).append(c)
    return groups


def _is_uniform_fallback(sport_cards: List[Dict[str, Any]]) -> bool:
    """Return True when *sport_cards* shows a constant-fallback model_prob pattern.

    Uses mlb_prob_uniformity_guard.check_uniformity as the detector.
    A small slate (< MIN_CARDS_PER_SPORT) is never flagged.
    Never raises.
    """
    if len(sport_cards) < MIN_CARDS_PER_SPORT:
        return False
    try:
        from scripts.platformkit.bestbets.mlb_prob_uniformity_guard import (
            check_uniformity,
            STATUS_FALLBACK_SUSPECTED,
        )
        result = check_uniformity(sport_cards, uniform_n=UNIFORM_N_THRESHOLD)
        return result.get("status") == STATUS_FALLBACK_SUSPECTED
    except Exception:  # noqa: BLE001
        return False


def _demote_card(card: Dict[str, Any], reason: str) -> None:
    """Stamp demotion fields onto *card* in-place."""
    card["edge_claimed"] = False
    card["tier"] = "C"
    card["flat_prior"] = True
    card["degenerate_model"] = True
    card["honest_note"] = FLAT_PRIOR_NOTE
    card["flat_prior_reason"] = reason


# -- Public API ----------------------------------------------------------------

def enforce_uniformity(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Demote all cards from any sport whose model_prob shows a constant fallback.

    Groups *cards* by sport string; for each sport that triggers
    FALLBACK_SUSPECTED via check_uniformity, stamps edge_claimed=False,
    tier='C', flat_prior=True, degenerate_model=True, and an honest_note onto
    every card from that sport.  Genuine discriminating sports are left entirely
    untouched.

    Parameters
    ----------
    cards:
        List of BestBetCard dicts (typically the full board across all sports).
        The list is returned as-is; flagged card dicts are mutated in-place.

    Returns
    -------
    List[Dict[str, Any]]
        The same list with degenerate-sport cards demoted.  Never raises.
        Returns the input unchanged on any unexpected error.
    """
    if not cards:
        return cards
    try:
        return _enforce_inner(cards)
    except Exception:  # noqa: BLE001 -- guard must never crash the board
        return cards


def _enforce_inner(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Inner implementation; always called through enforce_uniformity()."""
    by_sport = _group_by_sport(cards)
    for sport, sport_cards in by_sport.items():
        if not _is_uniform_fallback(sport_cards):
            continue
        # Build a brief reason string once, reuse for all cards in this sport.
        n = len(sport_cards)
        try:
            probs = set(
                round(float(c.get("model_prob")), 6)
                for c in sport_cards
                if c.get("model_prob") is not None
            )
            n_distinct = len(probs)
        except Exception:  # noqa: BLE001
            n_distinct = 0
        reason = (
            f"sport={sport}: {n} card(s) share only {n_distinct} distinct "
            "model_prob value(s); constant fallback detected; "
            "board demoted to base-rate-only."
        )
        for c in sport_cards:
            _demote_card(c, reason)
    return cards


__all__ = [
    "MIN_CARDS_PER_SPORT",
    "FLAT_PRIOR_NOTE",
    "UNIFORM_N_THRESHOLD",
    "enforce_uniformity",
]
