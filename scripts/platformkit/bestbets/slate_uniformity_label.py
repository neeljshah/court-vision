"""slate_uniformity_label.py -- cross-card MLB constant-prob detector.

BE-R5-2: Closes the recurring iter1/8 fabricated-edge P1 for MLB.

When N>=3 cards in a sport's best-bet slate collapse to <=2 distinct
model_prob values the model is NOT producing individualized predictions;
it has fallen back to a constant base rate.  Serving that slate as
calibrated per-game edge is a fabricated-edge violation.

This module detects the collapse and stamps every affected card with:
  * model_unavailable  = True   (machine-readable flag; False when OK)
  * honest_label       = str    (human-readable; always ASCII)

Cards from genuinely discriminating sports are left entirely untouched.
Slates with fewer than MIN_SLATE_CARDS cards get INSUFFICIENT_DATA (too
small to verdict) and are also left untouched.

Thresholds (see constants below)
---------------------------------
  MIN_SLATE_CARDS      : int = 3   -- minimum cards to make a verdict
  MAX_DISTINCT_TRIGGER : int = 2   -- <=this many distinct probs triggers label

Output shape of label_slate()
------------------------------
{
    "status":           str,   # OK | CONSTANT_FALLBACK | INSUFFICIENT_DATA
    "model_unavailable": bool, # True only when CONSTANT_FALLBACK
    "n_cards":          int,   # count of cards with valid model_prob
    "n_distinct":       int,   # number of distinct model_prob values observed
    "reason":           str,   # human-readable explanation (ASCII only)
    "cards":            list,  # same list as input; flagged cards mutated in-place
}

Acceptance tests (per-file):
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/bestbets/test_slate_uniformity_label.py -q

RAILS:
  * Pure: no IO, no network, no global mutable state.
  * Mutates flagged card dicts in-place (owned by the caller); never replaces them.
  * Returns the same card list object as input.
  * Never raises; degrades gracefully on bad input.
  * No $ / roi / pnl / bankroll / profit / stake / usd / dollar field.
  * No fabricated edge_vs_market on unavailable cards.
  * ASCII only; <= 300 LOC.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Tuneable thresholds
# ---------------------------------------------------------------------------

#: Minimum cards in a sport's slate before a uniformity verdict is trusted.
MIN_SLATE_CARDS: int = 3

#: Trigger CONSTANT_FALLBACK when the slate has <= this many distinct probs.
#: <=2 distinct values across N>=3 cards = degenerate model output.
MAX_DISTINCT_TRIGGER: int = 2

#: Rounding precision for treating two model_prob values as equal.
PROB_ROUND_DIGITS: int = 6

# ---------------------------------------------------------------------------
# Status + label constants
# ---------------------------------------------------------------------------

STATUS_OK: str = "OK"
STATUS_CONSTANT_FALLBACK: str = "CONSTANT_FALLBACK"
STATUS_INSUFFICIENT_DATA: str = "INSUFFICIENT_DATA"

#: Honest label written onto every demoted card.  ASCII only.
MODEL_UNAVAILABLE_LABEL: str = (
    "model unavailable -- base rate only, not a calibrated per-game edge"
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_prob(card: Any) -> Optional[float]:
    """Return model_prob as a rounded float, or None when missing/invalid."""
    if not isinstance(card, dict):
        return None
    raw = card.get("model_prob")
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(val):
        return None
    return round(val, PROB_ROUND_DIGITS)


def _stamp_unavailable(card: Dict[str, Any], reason: str) -> None:
    """Add model_unavailable=True + honest_label to *card* in-place.

    Never adds a $ / roi / pnl / edge_vs_market fabricated field.
    """
    card["model_unavailable"] = True
    card["honest_label"] = MODEL_UNAVAILABLE_LABEL
    card["uniformity_reason"] = reason


def _stamp_available(card: Dict[str, Any]) -> None:
    """Add model_unavailable=False to *card* when the slate is healthy."""
    card["model_unavailable"] = False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def label_slate(
    cards: List[Dict[str, Any]],
    *,
    min_slate_cards: int = MIN_SLATE_CARDS,
    max_distinct_trigger: int = MAX_DISTINCT_TRIGGER,
) -> Dict[str, Any]:
    """Detect constant-prob collapse and label every card in *cards*.

    Groups cards by sport (via the ``sport`` field).  For each sport that
    triggers CONSTANT_FALLBACK, stamps model_unavailable=True + honest_label
    on every card from that sport.  Cards from healthy sports get
    model_unavailable=False.  Cards from too-small slates (< min_slate_cards)
    are skipped (INSUFFICIENT_DATA -- no label applied, no fabrication).

    Parameters
    ----------
    cards:
        Full board (may include multiple sports).  Dicts are mutated in-place.
    min_slate_cards:
        Minimum cards per sport before a verdict is made.
    max_distinct_trigger:
        Trigger CONSTANT_FALLBACK when the sport has <= this many distinct
        model_prob values.

    Returns
    -------
    Dict[str, Any]
        Top-level result describing the full cross-sport verdict:
        ``status`` = OK | CONSTANT_FALLBACK | INSUFFICIENT_DATA
        ``model_unavailable`` = True only when any sport triggered CONSTANT_FALLBACK
        ``cards`` = same list reference as input
        Never raises.
    """
    try:
        return _label_slate_inner(
            cards,
            min_slate_cards=min_slate_cards,
            max_distinct_trigger=max_distinct_trigger,
        )
    except Exception:  # noqa: BLE001
        return {
            "status": STATUS_INSUFFICIENT_DATA,
            "model_unavailable": False,
            "n_cards": 0,
            "n_distinct": 0,
            "reason": "Unexpected error during slate uniformity check.",
            "cards": cards if isinstance(cards, list) else [],
        }


def _label_slate_inner(
    cards: List[Dict[str, Any]],
    *,
    min_slate_cards: int,
    max_distinct_trigger: int,
) -> Dict[str, Any]:
    """Inner implementation; always called through label_slate()."""
    if not cards:
        return {
            "status": STATUS_INSUFFICIENT_DATA,
            "model_unavailable": False,
            "n_cards": 0,
            "n_distinct": 0,
            "reason": "Empty card list; no slate to label.",
            "cards": cards,
        }

    # Partition valid dict cards by sport.
    by_sport: Dict[str, List[Dict[str, Any]]] = {}
    for c in cards:
        if isinstance(c, dict):
            sport = str(c.get("sport", ""))
            by_sport.setdefault(sport, []).append(c)

    any_fallback = False
    sport_verdicts: List[str] = []

    for sport, sport_cards in by_sport.items():
        probs = [_extract_prob(c) for c in sport_cards]
        valid_probs = [p for p in probs if p is not None]
        n_valid = len(valid_probs)

        if n_valid < min_slate_cards:
            # Too few cards to verdict -- leave untouched, no label.
            continue

        n_distinct = len(set(valid_probs))
        counter = Counter(valid_probs)
        dominant_prob, n_dominant = counter.most_common(1)[0]

        if n_distinct <= max_distinct_trigger:
            # Constant fallback detected.
            reason = (
                f"sport={sport}: {n_valid} card(s) share only {n_distinct} "
                f"distinct model_prob value(s) (threshold >{max_distinct_trigger}); "
                f"dominant_prob={dominant_prob} appears {n_dominant} time(s); "
                "constant fallback detected -- model unavailable, base rate only."
            )
            for c in sport_cards:
                _stamp_unavailable(c, reason)
            any_fallback = True
            sport_verdicts.append(f"{sport}=CONSTANT_FALLBACK")
        else:
            # Healthy: stamp available flag, leave other fields alone.
            for c in sport_cards:
                _stamp_available(c)
            sport_verdicts.append(f"{sport}=OK")

    # Build aggregate counts over ALL valid cards.
    all_probs = [_extract_prob(c) for c in cards if isinstance(c, dict)]
    all_valid = [p for p in all_probs if p is not None]
    n_total = len(all_valid)
    n_distinct_total = len(set(all_valid)) if all_valid else 0

    if not sport_verdicts:
        # No sport had enough cards.
        status = STATUS_INSUFFICIENT_DATA
        model_unavailable = False
        reason = (
            f"No sport slate reached {min_slate_cards} cards; "
            "INSUFFICIENT_DATA -- no label applied."
        )
    elif any_fallback:
        status = STATUS_CONSTANT_FALLBACK
        model_unavailable = True
        reason = (
            "One or more sport slates collapsed to a constant model_prob; "
            "affected cards labelled model_unavailable. "
            + "; ".join(sport_verdicts)
        )
    else:
        status = STATUS_OK
        model_unavailable = False
        reason = (
            "All sport slates show adequate probability discrimination. "
            + "; ".join(sport_verdicts)
        )

    return {
        "status": status,
        "model_unavailable": model_unavailable,
        "n_cards": n_total,
        "n_distinct": n_distinct_total,
        "reason": reason,
        "cards": cards,
    }


__all__ = [
    "MIN_SLATE_CARDS",
    "MAX_DISTINCT_TRIGGER",
    "PROB_ROUND_DIGITS",
    "STATUS_OK",
    "STATUS_CONSTANT_FALLBACK",
    "STATUS_INSUFFICIENT_DATA",
    "MODEL_UNAVAILABLE_LABEL",
    "label_slate",
]
