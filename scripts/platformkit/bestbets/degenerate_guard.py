"""degenerate_guard.py -- demote a flat-prior / model-unavailable sport.

QA-ISSUE-2 (degenerate model shown as calibration): all 11 MLB best-bet cards
carried model_prob of exactly 0.5345 / 0.4655 -- only 2 distinct values across
11 games. That is a flat prior / unavailable model presented as individualized
calibrated per-game divergence (a fabricated-edge violation).

THIS MODULE groups cards by sport and, when a sport's model_probs collapse to
<=2 distinct values over many games (or the uniformity guard flags a constant
fallback), relabels every card from that sport so it is NEVER presented as a
calibrated edge:

  * edge_claimed       -> False
  * tier               -> 'C'   (never ranked Tier-A/B calibrated divergence)
  * honest_note        -> "model unavailable -- base rate only, ..."
  * degenerate_model   -> True  (machine-readable flag for the UI)

A small slate (< MIN_CARDS) is left untouched: a 1-2 game card list sharing one
prob is not evidence of a flat-prior collapse.

RAILS:
  - Pure-ish: no IO, no network, no global mutable state. Reuses the tested
    mlb_prob_uniformity_guard.check_uniformity for the constant-fallback signal.
  - Mutates the freshly built card dicts in place (owned by bestbets_compute) and
    returns the same list. Never raises.
  - ASCII only; <= 300 LOC. No $ / ROI / PnL field; this DEMOTES an edge claim,
    it never mints one.

Per-file test:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      tests/platformkit/bestbets/test_degenerate_guard.py -q
"""
from __future__ import annotations

from typing import Any, Dict, List

#: Honest label written onto every demoted card.
DEGENERATE_NOTE: str = (
    "model unavailable -- base rate only, not a calibrated per-game edge"
)

#: A sport needs at least this many cards before a degeneracy verdict is trusted.
MIN_CARDS: int = 4

#: A flat prior collapses to at most this many distinct model_prob values.
MAX_DISTINCT_PROBS: int = 2


def _distinct_probs(cards: List[Dict[str, Any]]) -> int:
    """Number of distinct rounded model_prob values across *cards*."""
    seen = set()
    for c in cards:
        try:
            seen.add(round(float(c.get("model_prob")), 6))
        except (TypeError, ValueError):
            continue
    return len(seen)


def _is_degenerate(cards: List[Dict[str, Any]]) -> bool:
    """True when *cards* show a flat-prior / model-unavailable collapse."""
    if len(cards) < MIN_CARDS:
        return False
    if _distinct_probs(cards) <= MAX_DISTINCT_PROBS:
        return True
    # Secondary signal: the tested uniformity guard flags a constant fallback.
    try:
        from scripts.platformkit.bestbets.mlb_prob_uniformity_guard import (
            check_uniformity,
        )
        return bool(check_uniformity(cards).get("uniform"))
    except Exception:  # noqa: BLE001
        return False


def mark_degenerate_sports(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Relabel cards from any sport whose model collapses to a flat prior.

    Groups *cards* by sport; for each degenerate sport sets edge_claimed=False,
    demotes tier to 'C', writes an honest note, and flags degenerate_model=True.
    Genuine (non-degenerate) sports are left untouched. Never raises; returns the
    same list (degenerate card dicts mutated in place).
    """
    if not cards:
        return cards
    try:
        by_sport: Dict[str, List[Dict[str, Any]]] = {}
        for c in cards:
            if isinstance(c, dict):
                by_sport.setdefault(str(c.get("sport", "")), []).append(c)

        for _sport, sport_cards in by_sport.items():
            if not _is_degenerate(sport_cards):
                continue
            for c in sport_cards:
                c["edge_claimed"] = False
                c["tier"] = "C"
                c["honest_note"] = DEGENERATE_NOTE
                c["degenerate_model"] = True
        return cards
    except Exception:  # noqa: BLE001 -- never break the board over a guard
        return cards


__all__ = [
    "DEGENERATE_NOTE",
    "MIN_CARDS",
    "MAX_DISTINCT_PROBS",
    "mark_degenerate_sports",
]
