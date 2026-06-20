"""predict_service.mlb_board_uniformity_label -- MLB moneyline uniformity labelling pass.

BE-F-mlb-uniformity-board-wire (QA iter 1/8 P1):

The generic degenerate_guard.mark_degenerate_sports correctly demotes whole
flat-prior sports, but the original QA finding was specifically about MLB
moneyline cards collapsing to exactly 2 distinct model_prob values
(0.5345 / 0.4655 across 11 games). The uniformity guard
(mlb_prob_uniformity_guard.check_uniformity) exists and is tested, but it was
not wired as an explicit LABELLING pass on the MLB moneyline slice of the board.

This module provides label_mlb_moneyline_cards(), which:
  1. Isolates cards whose sport == 'mlb' and market_type in the moneyline family.
  2. Runs check_uniformity on that slice.
  3. If the guard returns FALLBACK_SUSPECTED (>= N cards share the same prob
     OR the whole slice collapses to 2 distinct values), every MLB moneyline
     card in the list is relabelled:
       - honest_note  -> UNIFORMITY_NOTE  (ASCII, no $)
       - edge_claimed -> False
       - tier         -> 'C'              (never ranked as calibrated Tier-A/B)
       - degenerate_model -> True         (machine-readable flag)
  4. Non-MLB cards and non-moneyline MLB cards are NEVER touched.
  5. A diverse (non-degenerate) MLB moneyline slice is returned unchanged.

Integration note:
  BE-A owns bestbets_compute.py and imports + calls this function immediately
  after _mark_degenerate_sports(). This module is disjoint from that lane and
  purely additive.

RAILS:
  - Pure module: no IO, no network, no global mutable state.
  - Never raises; degrades silently (returns cards unchanged on any error).
  - Returns the same list; MLB moneyline card dicts mutated in place.
  - ASCII only; <= 300 LOC.
  - No $ / roi / pnl / bankroll / profit / stake / usd / dollar field.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# -- Constants -----------------------------------------------------------------

#: Written onto every relabelled card.
UNIFORMITY_NOTE: str = (
    "model unavailable -- base rate only, not a calibrated per-game edge "
    "(MLB moneyline model_prob collapsed to 2 values; uniformity guard tripped)"
)

#: sport value that triggers this labelling pass.
_MLB_SPORT: str = "mlb"

#: market_type values treated as 'moneyline' for this guard.
_MONEYLINE_MARKETS = frozenset({
    "moneyline", "ml", "game_result", "h2h",
})

#: Minimum distinct model_prob values that a HEALTHY board should show.
#: A slate stuck at exactly 2 values (0.5345 / 0.4655) is the canonical failure.
_DISTINCT_PROB_FLOOR: int = 3


# -- Internal helpers ----------------------------------------------------------

def _is_mlb_moneyline(card: Any) -> bool:
    """True when *card* is an MLB moneyline-family bet card."""
    if not isinstance(card, dict):
        return False
    sport = str(card.get("sport", "")).lower()
    market = str(card.get("market_type", "")).lower()
    return sport == _MLB_SPORT and market in _MONEYLINE_MARKETS


def _run_uniformity(cards: List[Dict[str, Any]]) -> bool:
    """Return True when the uniformity guard flags the slice as degenerate."""
    try:
        from scripts.platformkit.bestbets.mlb_prob_uniformity_guard import (  # noqa: PLC0415
            check_uniformity,
        )
        result = check_uniformity(cards)
        return bool(result.get("uniform"))
    except Exception:  # noqa: BLE001
        return False


def _two_value_collapse(cards: List[Dict[str, Any]]) -> bool:
    """True when the slice has > 3 cards but <= 2 distinct model_prob values.

    This catches the QA-iter-1/8 case (11 cards, 2 values) even when the
    uniformity guard's n-threshold is not met by either single value alone.
    """
    if len(cards) < _DISTINCT_PROB_FLOOR:
        return False
    seen: set = set()
    for c in cards:
        try:
            seen.add(round(float(c.get("model_prob")), 6))
        except (TypeError, ValueError):
            continue
    return 0 < len(seen) <= 2


def _is_degenerate_slice(cards: List[Dict[str, Any]]) -> bool:
    """True when *cards* show a flat-prior / model-unavailable collapse."""
    if not cards:
        return False
    return _two_value_collapse(cards) or _run_uniformity(cards)


def _relabel(card: Dict[str, Any]) -> None:
    """Mutate *card* in place: mark it as model-unavailable, demote tier."""
    card["edge_claimed"] = False
    card["tier"] = "C"
    card["honest_note"] = UNIFORMITY_NOTE
    card["degenerate_model"] = True


# -- Public API ----------------------------------------------------------------

def label_mlb_moneyline_cards(
    cards: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Label MLB moneyline cards whose model_prob has collapsed to a flat prior.

    This is a post-mark_degenerate_sports labelling pass targeted specifically
    at the MLB 2-value collapse symptom (QA iter 1/8 P1). It filters the full
    board to the MLB moneyline slice, runs the uniformity guard on that slice,
    and relabels every MLB moneyline card when the guard trips.

    Parameters
    ----------
    cards:
        The full best-bet card list (all sports, all market types). The list
        and individual dicts from non-MLB or non-moneyline rows are never
        mutated. MLB moneyline dicts are mutated in place when degenerate.

    Returns
    -------
    List[Dict[str, Any]]
        The same *cards* list (same object). Never raises; returns *cards*
        unchanged if an unexpected error occurs.
    """
    if not cards:
        return cards
    try:
        return _label_inner(cards)
    except Exception:  # noqa: BLE001
        logger.debug("label_mlb_moneyline_cards: unexpected error; returning cards unchanged")
        return cards


def _label_inner(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Inner implementation; always called through label_mlb_moneyline_cards."""
    mlb_ml_cards = [c for c in cards if _is_mlb_moneyline(c)]

    if not mlb_ml_cards:
        return cards  # nothing to check

    if not _is_degenerate_slice(mlb_ml_cards):
        return cards  # diverse probs -- board is fine

    # Uniformity guard tripped: relabel every MLB moneyline card in the full list.
    for c in cards:
        if _is_mlb_moneyline(c):
            _relabel(c)

    n = len(mlb_ml_cards)
    logger.warning(
        "label_mlb_moneyline_cards: MLB moneyline slice (%d cards) shows "
        "flat-prior collapse; all relabelled as model-unavailable.", n,
    )
    return cards


__all__ = [
    "UNIFORMITY_NOTE",
    "label_mlb_moneyline_cards",
]
