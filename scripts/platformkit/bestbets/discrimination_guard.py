"""discrimination_guard.py -- detect and suppress non-discriminating best-bet boards.

QA-MLB-DISCRIM (P1): when a sport's best-bet board has too few distinct model_prob
values relative to the total card count, the model has collapsed to a fallback
probability and every card is treated as if it carries the same prediction.
Serving such a board as individualised edge is a fabricated-edge violation.

This guard runs as a pure post-filter over a card list (no IO, no network).

Verdict values
--------------
  NON_DISCRIMINATING  -- n_distinct / n_cards < MIN_DISCRIMINATION_RATIO;
                         board is collapsed; suppressed=True.
  OK                  -- n_distinct / n_cards >= MIN_DISCRIMINATION_RATIO;
                         suppressed=False.
  INSUFFICIENT_DATA   -- fewer than MIN_CARDS_REQUIRED cards; can't judge;
                         suppressed=False (no data is not an error).

Output shape (never raises)
---------------------------
{
    "verdict":           str,            # NON_DISCRIMINATING | OK | INSUFFICIENT_DATA
    "suppressed":        bool,           # True only when NON_DISCRIMINATING
    "n_cards":           int,
    "n_distinct_probs":  int,
    "discrimination_ratio": float | None,  # None when INSUFFICIENT_DATA
    "dominant_prob":     float | None,  # most common model_prob (or None)
    "n_dominant":        int,           # count of cards at dominant_prob
    "reason":            str,           # human-readable explanation
}

RAILS:
  * Pure module: no IO, no network, no global state.
  * Never raises; degrades gracefully to INSUFFICIENT_DATA on bad input.
  * Returns a new dict; never mutates the input list or card dicts.
  * No $ / roi / pnl / bankroll / profit / stake / usd / dollar field.
  * ASCII only; <= 300 LOC.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

# -- Tuneable thresholds (module-level so tests can inspect them) ---------------

#: Minimum number of cards needed to make a discrimination judgement.
MIN_CARDS_REQUIRED: int = 3

#: Board is flagged NON_DISCRIMINATING when n_distinct / n_cards < this.
#: 0.5 means fewer than half the cards carry a distinct probability.
MIN_DISCRIMINATION_RATIO: float = 0.5

#: Tolerance for treating two model_prob values as identical.
#: Rounding to 6 significant decimal places before de-duplication.
PROB_ROUND_DIGITS: int = 6


# -- Verdict constants ----------------------------------------------------------

VERDICT_NON_DISCRIMINATING: str = "NON_DISCRIMINATING"
VERDICT_OK: str = "OK"
VERDICT_INSUFFICIENT_DATA: str = "INSUFFICIENT_DATA"


# -- Internal helpers -----------------------------------------------------------

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
    import math  # noqa: PLC0415
    if not math.isfinite(val):
        return None
    return round(val, PROB_ROUND_DIGITS)


def _dominant(counter: Counter) -> tuple:
    """Return (dominant_prob, n_dominant) from a Counter, or (None, 0)."""
    if not counter:
        return (None, 0)
    prob, count = counter.most_common(1)[0]
    return (prob, count)


# -- Public API ----------------------------------------------------------------

def check_discrimination(
    cards: List[Dict[str, Any]],
    *,
    min_cards: int = MIN_CARDS_REQUIRED,
    min_ratio: float = MIN_DISCRIMINATION_RATIO,
) -> Dict[str, Any]:
    """Assess whether a best-bet card list shows adequate probability discrimination.

    Parameters
    ----------
    cards:
        List of BestBetCard dicts, each expected to carry a ``model_prob`` field.
        The list and individual dicts are never mutated.
    min_cards:
        Minimum number of cards required to make a discrimination judgement.
        Defaults to MIN_CARDS_REQUIRED (3).
    min_ratio:
        Fraction of distinct model_prob values required for an OK verdict.
        Defaults to MIN_DISCRIMINATION_RATIO (0.5).

    Returns
    -------
    Dict[str, Any]
        See module docstring for the full output shape.
        Never raises; returns INSUFFICIENT_DATA on any unexpected error.
    """
    try:
        return _check_discrimination_inner(cards, min_cards=min_cards, min_ratio=min_ratio)
    except Exception:  # noqa: BLE001
        return {
            "verdict": VERDICT_INSUFFICIENT_DATA,
            "suppressed": False,
            "n_cards": 0,
            "n_distinct_probs": 0,
            "discrimination_ratio": None,
            "dominant_prob": None,
            "n_dominant": 0,
            "reason": "Unexpected error during discrimination check; treating as insufficient data.",
        }


def _check_discrimination_inner(
    cards: List[Dict[str, Any]],
    *,
    min_cards: int,
    min_ratio: float,
) -> Dict[str, Any]:
    """Inner implementation; called from check_discrimination() which catches all exceptions."""
    # Handle non-list / None input safely.
    if not cards:
        return {
            "verdict": VERDICT_INSUFFICIENT_DATA,
            "suppressed": False,
            "n_cards": 0,
            "n_distinct_probs": 0,
            "discrimination_ratio": None,
            "dominant_prob": None,
            "n_dominant": 0,
            "reason": "Empty card list; no discrimination data available.",
        }

    # Extract valid model_prob values.
    probs = [_extract_prob(c) for c in cards if isinstance(c, dict)]
    # Filter out None (missing/invalid model_prob cards).
    valid_probs = [p for p in probs if p is not None]

    n_cards = len(valid_probs)

    if n_cards < min_cards:
        dominant_prob, n_dominant = _dominant(Counter(valid_probs)) if valid_probs else (None, 0)
        return {
            "verdict": VERDICT_INSUFFICIENT_DATA,
            "suppressed": False,
            "n_cards": n_cards,
            "n_distinct_probs": len(set(valid_probs)),
            "discrimination_ratio": None,
            "dominant_prob": dominant_prob,
            "n_dominant": n_dominant,
            "reason": (
                f"Only {n_cards} card(s) with valid model_prob (need >= {min_cards}); "
                "cannot assess discrimination."
            ),
        }

    counter = Counter(valid_probs)
    n_distinct = len(counter)
    ratio = n_distinct / n_cards
    dominant_prob, n_dominant = _dominant(counter)

    if ratio < min_ratio:
        reason = (
            f"Only {n_distinct} distinct model_prob value(s) across {n_cards} card(s) "
            f"(ratio {ratio:.3f} < {min_ratio:.3f}). "
            f"Dominant prob {dominant_prob} appears in {n_dominant}/{n_cards} cards. "
            "Model has likely collapsed to a fallback probability; "
            "board is suppressed to prevent fabricated-edge output."
        )
        return {
            "verdict": VERDICT_NON_DISCRIMINATING,
            "suppressed": True,
            "n_cards": n_cards,
            "n_distinct_probs": n_distinct,
            "discrimination_ratio": round(ratio, 6),
            "dominant_prob": dominant_prob,
            "n_dominant": n_dominant,
            "reason": reason,
        }

    reason = (
        f"{n_distinct} distinct model_prob value(s) across {n_cards} card(s) "
        f"(ratio {ratio:.3f} >= {min_ratio:.3f}). Board shows adequate discrimination."
    )
    return {
        "verdict": VERDICT_OK,
        "suppressed": False,
        "n_cards": n_cards,
        "n_distinct_probs": n_distinct,
        "discrimination_ratio": round(ratio, 6),
        "dominant_prob": dominant_prob,
        "n_dominant": n_dominant,
        "reason": reason,
    }


__all__ = [
    "MIN_CARDS_REQUIRED",
    "MIN_DISCRIMINATION_RATIO",
    "PROB_ROUND_DIGITS",
    "VERDICT_NON_DISCRIMINATING",
    "VERDICT_OK",
    "VERDICT_INSUFFICIENT_DATA",
    "check_discrimination",
]
