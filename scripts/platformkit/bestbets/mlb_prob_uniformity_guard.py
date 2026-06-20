"""mlb_prob_uniformity_guard.py -- detect constant model_prob fallback in best-bet boards.

QAFIX-2-2: when >= N cards in a sport's best-bet board share an *identical*
model_prob value, the model has collapsed to a constant fallback output.
Serving that board as individualised calibrated edge is a fabricated-edge
violation.  This guard flags the state as FALLBACK_SUSPECTED.

Example trigger from QA iter1/8: 7 of 12 MLB cards all shared model_prob=0.4655.

Output shape (never raises)
---------------------------
{
    "uniform":        bool,         # True when >= N cards share the same prob
    "dominant_prob":  float | None, # the repeated prob value (None when uniform=False)
    "n_uniform":      int,          # count of cards at dominant_prob (0 when uniform=False)
    "n_cards":        int,          # total cards with a valid model_prob
    "n_unique":       int,          # number of distinct model_prob values
    "status":         str,          # FALLBACK_SUSPECTED | OK | INSUFFICIENT_DATA
    "reason":         str,          # human-readable explanation (ASCII only)
}

RAILS:
  * Pure module: no IO, no network, no global state.
  * Never raises; degrades gracefully on bad input.
  * Returns a new dict; never mutates input.
  * No $ / roi / pnl / bankroll / profit / stake / usd / dollar field.
  * ASCII only; <= 300 LOC.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Any, Dict, List, Optional

# -- Tuneable thresholds -------------------------------------------------------

#: Minimum count of cards sharing one model_prob value to trigger FALLBACK_SUSPECTED.
UNIFORM_N_THRESHOLD: int = 3

#: Minimum total valid cards required before a uniformity judgement is made.
MIN_CARDS_REQUIRED: int = 2

#: Rounding precision for treating two model_prob values as identical.
PROB_ROUND_DIGITS: int = 6

# -- Status constants ----------------------------------------------------------

STATUS_FALLBACK_SUSPECTED: str = "FALLBACK_SUSPECTED"
STATUS_OK: str = "OK"
STATUS_INSUFFICIENT_DATA: str = "INSUFFICIENT_DATA"


# -- Internal helpers ----------------------------------------------------------

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


# -- Public API ----------------------------------------------------------------

def check_uniformity(
    cards: List[Dict[str, Any]],
    *,
    uniform_n: int = UNIFORM_N_THRESHOLD,
    min_cards: int = MIN_CARDS_REQUIRED,
) -> Dict[str, Any]:
    """Check whether a best-bet card list has a constant-fallback model_prob.

    Parameters
    ----------
    cards:
        List of BestBetCard dicts, each expected to carry a ``model_prob`` field.
        The list and individual dicts are never mutated.
    uniform_n:
        Flag FALLBACK_SUSPECTED when the most-common model_prob appears in at
        least this many cards.  Defaults to UNIFORM_N_THRESHOLD (3).
    min_cards:
        Minimum number of cards with a valid model_prob before a uniformity
        judgement can be made.  Defaults to MIN_CARDS_REQUIRED (2).

    Returns
    -------
    Dict[str, Any]
        See module docstring for the full output shape.  Never raises.
    """
    try:
        return _check_uniformity_inner(cards, uniform_n=uniform_n, min_cards=min_cards)
    except Exception:  # noqa: BLE001
        return _insufficient("Unexpected error during uniformity check.")


def _insufficient(reason: str, n_cards: int = 0, n_unique: int = 0) -> Dict[str, Any]:
    return {
        "uniform": False,
        "dominant_prob": None,
        "n_uniform": 0,
        "n_cards": n_cards,
        "n_unique": n_unique,
        "status": STATUS_INSUFFICIENT_DATA,
        "reason": reason,
    }


def _check_uniformity_inner(
    cards: List[Dict[str, Any]],
    *,
    uniform_n: int,
    min_cards: int,
) -> Dict[str, Any]:
    """Inner implementation; always called through check_uniformity()."""
    # Gracefully handle non-list / None input.
    if not cards:
        return _insufficient("Empty card list; no uniformity data available.")

    # Extract valid model_prob values from dict cards only.
    valid_probs = [p for c in cards if isinstance(c, dict) for p in [_extract_prob(c)] if p is not None]

    n_cards = len(valid_probs)
    n_unique = len(set(valid_probs))

    # n_unique == 1 means every card carries the same prob -- always flag regardless
    # of n_cards vs min_cards (a single repeated prob IS a fallback collapse).
    if n_unique == 1 and n_cards >= 1:
        dominant_prob = valid_probs[0]
        reason = (
            f"All {n_cards} card(s) share model_prob={dominant_prob}. "
            "Model output is constant; board flagged as FALLBACK_SUSPECTED."
        )
        return {
            "uniform": True,
            "dominant_prob": dominant_prob,
            "n_uniform": n_cards,
            "n_cards": n_cards,
            "n_unique": 1,
            "status": STATUS_FALLBACK_SUSPECTED,
            "reason": reason,
        }

    # Not enough cards to make a judgement (and n_unique != 1).
    if n_cards < min_cards:
        return _insufficient(
            f"Only {n_cards} card(s) with valid model_prob (need >= {min_cards}); "
            "cannot assess uniformity.",
            n_cards=n_cards,
            n_unique=n_unique,
        )

    counter = Counter(valid_probs)
    dominant_prob, n_dominant = counter.most_common(1)[0]

    if n_dominant >= uniform_n:
        reason = (
            f"{n_dominant} of {n_cards} card(s) share model_prob={dominant_prob}. "
            f"Threshold is {uniform_n}; model output appears constant; "
            "board flagged as FALLBACK_SUSPECTED."
        )
        return {
            "uniform": True,
            "dominant_prob": dominant_prob,
            "n_uniform": n_dominant,
            "n_cards": n_cards,
            "n_unique": n_unique,
            "status": STATUS_FALLBACK_SUSPECTED,
            "reason": reason,
        }

    reason = (
        f"Most-common model_prob={dominant_prob} appears {n_dominant} time(s) "
        f"across {n_cards} card(s) (threshold={uniform_n}). "
        "No constant-fallback pattern detected."
    )
    return {
        "uniform": False,
        "dominant_prob": dominant_prob,
        "n_uniform": n_dominant,
        "n_cards": n_cards,
        "n_unique": n_unique,
        "status": STATUS_OK,
        "reason": reason,
    }


__all__ = [
    "UNIFORM_N_THRESHOLD",
    "MIN_CARDS_REQUIRED",
    "PROB_ROUND_DIGITS",
    "STATUS_FALLBACK_SUSPECTED",
    "STATUS_OK",
    "STATUS_INSUFFICIENT_DATA",
    "check_uniformity",
]
