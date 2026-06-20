"""degenerate_diagnostic.py -- diagnostic payload for degenerate / flat-prior sport boards.

R6-6-mlb-degenerate-emitter: when a sport's best-bet board collapses to only a small
number of distinct model_prob values (e.g. all MLB cards at 0.5345 / 0.4655), serving
those probs as calibrated divergence is a fabricated-edge violation.  This module emits
an honest diagnostic payload so the served row reads model_status='unavailable -- base
rate only' instead of passing as individualised prediction.

Output shape per sport (assess_sport):
  { sport, n_cards, n_distinct, degenerate, model_status, edge_claimed, reason }
  * degenerate + model_status=MODEL_STATUS_UNAVAILABLE + edge_claimed=False
    when n_distinct <= MAX_DISTINCT_PROBS AND n_cards >= MIN_CARDS (OR uniformity guard
    fires as secondary signal).
  * model_status=INSUFFICIENT_DATA_STATUS when n_cards < MIN_CARDS.
  * model_status=MODEL_STATUS_OK when board is healthy.

RAILS: no IO, no network, no global state.  Never raises.  No $ / roi / pnl field.
ASCII only; <= 300 LOC.

Per-file test:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/bestbets/test_degenerate_diagnostic.py -q
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

# -- Tuneable thresholds -------------------------------------------------------

#: Minimum cards in a sport group before a degeneracy verdict is trustworthy.
MIN_CARDS: int = 5

#: At most this many distinct model_prob values counts as a flat-prior collapse.
MAX_DISTINCT_PROBS: int = 2

#: Rounding precision for treating two model_prob values as identical.
PROB_ROUND_DIGITS: int = 6

# -- Status/label constants (ASCII only) ----------------------------------------

MODEL_STATUS_UNAVAILABLE: str = "unavailable -- base rate only"
INSUFFICIENT_DATA_STATUS: str = "INSUFFICIENT_DATA"
MODEL_STATUS_OK: str = "ok"


# -- Internal helpers ----------------------------------------------------------

def _safe_prob(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(val):
        return None
    return round(val, PROB_ROUND_DIGITS)


def _collect_probs(cards: Sequence[Dict[str, Any]]) -> List[float]:
    result = []
    for c in cards:
        if not isinstance(c, dict):
            continue
        p = _safe_prob(c.get("model_prob"))
        if p is not None:
            result.append(p)
    return result


def _uniformity_flag(cards: Sequence[Dict[str, Any]]) -> bool:
    """True when mlb_prob_uniformity_guard signals a constant-fallback."""
    try:
        from scripts.platformkit.bestbets.mlb_prob_uniformity_guard import (  # noqa: PLC0415
            check_uniformity,
        )
        return bool(check_uniformity(list(cards)).get("uniform"))
    except Exception:  # noqa: BLE001
        return False


def _build_result(
    sport: str,
    n_cards: int,
    n_distinct: int,
    degenerate: bool,
    model_status: str,
    edge_claimed: bool,
    reason: str,
) -> Dict[str, Any]:
    return {
        "sport": sport,
        "n_cards": n_cards,
        "n_distinct": n_distinct,
        "degenerate": degenerate,
        "model_status": model_status,
        "edge_claimed": edge_claimed,
        "reason": reason,
    }


# -- Public API ----------------------------------------------------------------

def assess_sport(
    cards: Sequence[Dict[str, Any]],
    sport: str = "",
    *,
    min_cards: int = MIN_CARDS,
    max_distinct: int = MAX_DISTINCT_PROBS,
) -> Dict[str, Any]:
    """Assess one sport's card group and emit an honest diagnostic payload.

    Never raises; returns INSUFFICIENT_DATA on any unexpected error.
    """
    try:
        return _assess_inner(cards, sport=sport, min_cards=min_cards, max_distinct=max_distinct)
    except Exception:  # noqa: BLE001
        return _build_result(
            sport=sport, n_cards=0, n_distinct=0, degenerate=False,
            model_status=INSUFFICIENT_DATA_STATUS, edge_claimed=False,
            reason="Unexpected error during degeneracy assessment.",
        )


def _assess_inner(
    cards: Sequence[Dict[str, Any]],
    *,
    sport: str,
    min_cards: int,
    max_distinct: int,
) -> Dict[str, Any]:
    if not cards:
        return _build_result(
            sport=sport, n_cards=0, n_distinct=0, degenerate=False,
            model_status=INSUFFICIENT_DATA_STATUS, edge_claimed=False,
            reason="Empty card list; cannot assess degeneracy.",
        )

    probs = _collect_probs(cards)
    n_cards = len(probs)
    n_distinct = len(set(probs))

    if n_cards < min_cards:
        return _build_result(
            sport=sport, n_cards=n_cards, n_distinct=n_distinct, degenerate=False,
            model_status=INSUFFICIENT_DATA_STATUS, edge_claimed=False,
            reason=(
                f"Only {n_cards} card(s) with valid model_prob "
                f"(need >= {min_cards}); cannot assess degeneracy."
            ),
        )

    primary_degenerate = n_distinct <= max_distinct
    secondary_uniform = _uniformity_flag(cards)
    is_degenerate = primary_degenerate or secondary_uniform

    if is_degenerate:
        why_parts = []
        if primary_degenerate:
            why_parts.append(
                f"only {n_distinct} distinct model_prob value(s) across "
                f"{n_cards} card(s) (max_distinct={max_distinct})"
            )
        if secondary_uniform:
            why_parts.append("uniformity guard detected constant-fallback")
        return _build_result(
            sport=sport, n_cards=n_cards, n_distinct=n_distinct, degenerate=True,
            model_status=MODEL_STATUS_UNAVAILABLE, edge_claimed=False,
            reason="Degenerate board: " + "; ".join(why_parts) + ".",
        )

    return _build_result(
        sport=sport, n_cards=n_cards, n_distinct=n_distinct, degenerate=False,
        model_status=MODEL_STATUS_OK, edge_claimed=True,
        reason=(
            f"{n_distinct} distinct model_prob value(s) across {n_cards} card(s); "
            "board shows adequate spread."
        ),
    )


def assess_board(
    cards: Sequence[Dict[str, Any]],
    *,
    min_cards: int = MIN_CARDS,
    max_distinct: int = MAX_DISTINCT_PROBS,
) -> Dict[str, Dict[str, Any]]:
    """Assess all sports on a multi-sport board; returns {sport: payload} mapping.

    Groups cards by the ``sport`` field.  Empty dict when cards is empty.
    Never raises.
    """
    try:
        return _assess_board_inner(cards, min_cards=min_cards, max_distinct=max_distinct)
    except Exception:  # noqa: BLE001
        return {}


def _assess_board_inner(
    cards: Sequence[Dict[str, Any]],
    *,
    min_cards: int,
    max_distinct: int,
) -> Dict[str, Dict[str, Any]]:
    if not cards:
        return {}
    by_sport: Dict[str, List[Dict[str, Any]]] = {}
    for c in cards:
        if isinstance(c, dict):
            s = str(c.get("sport", "unknown"))
            by_sport.setdefault(s, []).append(c)
    return {
        sport: assess_sport(
            sport_cards, sport=sport, min_cards=min_cards, max_distinct=max_distinct,
        )
        for sport, sport_cards in by_sport.items()
    }


__all__ = [
    "MIN_CARDS",
    "MAX_DISTINCT_PROBS",
    "PROB_ROUND_DIGITS",
    "MODEL_STATUS_UNAVAILABLE",
    "INSUFFICIENT_DATA_STATUS",
    "MODEL_STATUS_OK",
    "assess_sport",
    "assess_board",
]
