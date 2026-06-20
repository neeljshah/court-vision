"""board_metrics.py -- read-only best-bets board health metrics (BE-BOARD-METRICS).

Computes a metrics dict from a snapshot of best-bet cards so board degeneracy
is caught automatically each tick rather than by manual QA.

Metrics surface
---------------
{
    "n_cards":              int,       -- total cards in the post-sanitize board
    "distinct_prob_ratio":  float,     -- n_distinct_model_prob / n_cards (0..1)
    "n_dropped_sanitizer":  int,       -- cards removed by board_sanitizer.sanitize()
    "non_discriminating":   bool,      -- True when discrimination_guard flags collapse
    "prop_share":           float,     -- fraction of cards that are prop markets (0..1)
    "game_share":           float,     -- fraction of cards that are game/team markets
    "status":               str,       -- "ok" | "INSUFFICIENT_DATA" | "NON_DISCRIMINATING"
    "honest_note":          str,       -- short provenance label
}

When the input board is empty (pre-sanitize) or all cards are dropped, the
function returns a sentinel dict with status="INSUFFICIENT_DATA" rather than
a misleading zero-ratio value.

RAILS:
  * Pure function: no IO, no network, no global state, no side effects.
  * Returns a new dict; never mutates inputs.
  * Never raises -- degrades gracefully on bad input.
  * No $ / roi / pnl / bankroll / profit / stake / usd / dollar field.
  * Reads board_sanitizer and discrimination_guard; does NOT call either in
    a way that can raise (both are already never-raise modules).
  * ASCII only; <= 300 LOC.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Sentinel / status constants
# ---------------------------------------------------------------------------

STATUS_OK: str = "ok"
STATUS_INSUFFICIENT_DATA: str = "INSUFFICIENT_DATA"
STATUS_NON_DISCRIMINATING: str = "NON_DISCRIMINATING"

_HONEST_NOTE: str = (
    "BE-BOARD-METRICS read-only surface. "
    "CALIBRATION not edge; UNITS not $; "
    "non_discriminating=True means model collapsed (fabricated-edge risk)."
)

# Minimum cards needed to produce meaningful ratios.
MIN_CARDS_FOR_METRICS: int = 1

# Round model_prob to this many digits before counting distinct values
# (mirrors discrimination_guard.PROB_ROUND_DIGITS).
_PROB_DIGITS: int = 6

# Prop-market detection: card["market_type"] in this set -> prop.
_PROP_MARKET_TYPES: frozenset = frozenset({
    "player_prop", "prop", "player_props",
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_model_prob(card: Any) -> Optional[float]:
    """Return model_prob as a rounded float or None."""
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
    return round(val, _PROB_DIGITS)


def _is_prop_card(card: Any) -> bool:
    """Return True when the card is a player-prop market."""
    if not isinstance(card, dict):
        return False
    mt = card.get("market_type")
    if isinstance(mt, str) and mt.lower() in _PROP_MARKET_TYPES:
        return True
    # Fallback: if no market_type field, check for a "stat" key (prop-specific).
    return "stat" in card and "market_type" not in card


def _distinct_prob_ratio(cards: List[Dict[str, Any]]) -> Optional[float]:
    """Return n_distinct_model_prob / n_cards, or None when n_cards == 0."""
    if not cards:
        return None
    probs = [_extract_model_prob(c) for c in cards]
    valid = [p for p in probs if p is not None]
    if not valid:
        return None
    return len(set(valid)) / len(valid)


def _non_discriminating(cards: List[Dict[str, Any]]) -> bool:
    """Return True when discrimination_guard classifies the board as collapsed.

    Delegates to discrimination_guard.check_discrimination() when available;
    falls back to a simple ratio check so board_metrics works standalone.
    """
    try:
        from scripts.platformkit.bestbets.discrimination_guard import (  # type: ignore
            check_discrimination,
            VERDICT_NON_DISCRIMINATING,
        )
        result = check_discrimination(cards)
        return result.get("verdict") == VERDICT_NON_DISCRIMINATING
    except Exception:  # noqa: BLE001
        pass

    # Standalone fallback: same logic as discrimination_guard.
    probs = [_extract_model_prob(c) for c in cards if isinstance(c, dict)]
    valid = [p for p in probs if p is not None]
    if len(valid) < 3:
        return False
    n_distinct = len(set(valid))
    ratio = n_distinct / len(valid)
    return ratio < 0.5

def _count_dropped_by_sanitizer(
    raw_cards: List[Dict[str, Any]],
) -> int:
    """Return the number of cards that board_sanitizer.sanitize() would drop."""
    try:
        from scripts.platformkit.bestbets.board_sanitizer import sanitize  # type: ignore
        kept = sanitize(raw_cards)
        return len(raw_cards) - len(kept)
    except Exception:  # noqa: BLE001
        pass
    # Standalone fallback: replicate sanitize() drop criteria.
    dropped = 0
    for card in raw_cards:
        if not isinstance(card, dict):
            continue
        matchup = card.get("matchup")
        if isinstance(matchup, str) and "yes vs no" in matchup.lower():
            dropped += 1
            continue
        mp = card.get("market_prob")
        try:
            mp_f = float(mp)
        except (TypeError, ValueError):
            dropped += 1
            continue
        if not math.isfinite(mp_f) or mp_f < 0.02:
            dropped += 1
            continue
        bo = card.get("best_odds")
        if bo is not None:
            try:
                bo_f = float(bo)
                if not math.isfinite(bo_f) or bo_f > 50.0:
                    dropped += 1
                    continue
            except (TypeError, ValueError):
                pass
        ev = card.get("edge_vs_market")
        if ev is not None:
            try:
                ev_f = float(ev)
                if not math.isfinite(ev_f) or abs(ev_f) > 0.30:
                    dropped += 1
                    continue
            except (TypeError, ValueError):
                pass
    return dropped

def _apply_sanitizer(
    raw_cards: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Return post-sanitize card list. Never raises."""
    try:
        from scripts.platformkit.bestbets.board_sanitizer import sanitize  # type: ignore
        return sanitize(raw_cards)
    except Exception:  # noqa: BLE001
        # Fallback: return all cards if sanitizer unavailable.
        return list(raw_cards)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_board_metrics(
    cards: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute health metrics for a best-bet board snapshot.

    Parameters
    ----------
    cards:
        List of BestBetCard dicts as produced by bestbets_compute (PRE-sanitize).
        The list and dicts are never mutated.

    Returns
    -------
    Dict[str, Any]
        {
            "n_cards":             int,
            "distinct_prob_ratio": float | None,
            "n_dropped_sanitizer": int,
            "non_discriminating":  bool,
            "prop_share":          float | None,
            "game_share":          float | None,
            "status":              str,
            "honest_note":         str,
        }

    Empty board (cards=[]) -> status="INSUFFICIENT_DATA".
    Board where all cards are dropped -> status="INSUFFICIENT_DATA".
    Board where discrimination guard fires -> status="NON_DISCRIMINATING".
    Otherwise -> status="ok".
    Never raises.
    """
    try:
        return _compute_inner(cards)
    except Exception:  # noqa: BLE001
        return _insufficient_data_sentinel(n_cards=0, n_dropped=0)


def _insufficient_data_sentinel(
    n_cards: int,
    n_dropped: int,
) -> Dict[str, Any]:
    return {
        "n_cards": n_cards,
        "distinct_prob_ratio": None,
        "n_dropped_sanitizer": n_dropped,
        "non_discriminating": False,
        "prop_share": None,
        "game_share": None,
        "status": STATUS_INSUFFICIENT_DATA,
        "honest_note": _HONEST_NOTE,
    }


def _compute_inner(
    cards: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Inner impl; wrapped by compute_board_metrics for error isolation."""
    if not isinstance(cards, list):
        cards = []

    n_raw = len(cards)
    n_dropped = _count_dropped_by_sanitizer(cards)
    post_cards = _apply_sanitizer(cards)
    n_cards = len(post_cards)

    if n_cards == 0:
        return _insufficient_data_sentinel(n_cards=0, n_dropped=n_dropped)

    # Distinct probability ratio (over post-sanitize cards).
    ratio = _distinct_prob_ratio(post_cards)

    # Prop vs game split.
    n_prop = sum(1 for c in post_cards if _is_prop_card(c))
    n_game = n_cards - n_prop
    prop_share = round(n_prop / n_cards, 6) if n_cards else None
    game_share = round(n_game / n_cards, 6) if n_cards else None

    # Discrimination check.
    nd = _non_discriminating(post_cards)

    status: str
    if nd:
        status = STATUS_NON_DISCRIMINATING
    else:
        status = STATUS_OK

    return {
        "n_cards": n_cards,
        "distinct_prob_ratio": round(ratio, 6) if ratio is not None else None,
        "n_dropped_sanitizer": n_dropped,
        "non_discriminating": nd,
        "prop_share": prop_share,
        "game_share": game_share,
        "status": status,
        "honest_note": _HONEST_NOTE,
    }


__all__ = [
    "STATUS_OK",
    "STATUS_INSUFFICIENT_DATA",
    "STATUS_NON_DISCRIMINATING",
    "MIN_CARDS_FOR_METRICS",
    "compute_board_metrics",
]
