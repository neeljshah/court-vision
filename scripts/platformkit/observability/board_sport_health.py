"""board_sport_health.py -- per-sport best-bets board health surface (OBS-BOARD-SPORT-HEALTH).

Reads a pre-sanitize list of BestBetCard dicts (as produced by bestbets_compute),
groups them by sport, and returns one health row per sport summarising:

  * n_served    -- cards that passed board_sanitizer.sanitize()
  * n_dropped   -- cards removed by sanitize() (sum of drop reasons below)
  * n_dropped_binary     -- 'yes vs no' matchup binary events
  * n_dropped_degenerate -- market_prob below threshold
  * n_dropped_stale_tipoff -- stale-tipoff stub cards (tipoff_stale=True or
                               odds_unavailable stub where best_odds is None
                               AND market_prob is None/0.0)
  * n_dropped_odds_extreme  -- best_odds > MAX_BEST_ODDS threshold
  * non_discriminating -- True when discrimination_guard fires on served cards
  * status      -- "ok" | "INSUFFICIENT_DATA" | "NON_DISCRIMINATING"
  * honest_note -- provenance label

A card with no "sport" key is bucketed under sport="unknown".

Top-level function: compute_sport_health(cards) -> List[Dict[str, Any]]

RAILS:
  * Pure function: no IO, no network, no global state, no side effects.
  * Returns a new list; never mutates input.
  * Never raises -- degrades gracefully on bad input.
  * No $ / roi / pnl / bankroll / profit / stake / usd / dollar field.
  * Reads board_sanitizer and discrimination_guard helpers (both never-raise).
  * INSUFFICIENT_DATA when sport has zero cards total.
  * ASCII only; <= 300 LOC.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Internal import of helpers (never raises; graceful fallback when absent)
# ---------------------------------------------------------------------------

def _sanitize(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Apply board_sanitizer.sanitize(); fallback = identity (no drop)."""
    try:
        from scripts.platformkit.bestbets.board_sanitizer import sanitize  # type: ignore
        return sanitize(cards)
    except Exception:  # noqa: BLE001
        return list(cards)


def _check_discrimination(cards: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Check discrimination; fallback = INSUFFICIENT_DATA dict."""
    try:
        from scripts.platformkit.bestbets.discrimination_guard import (  # type: ignore
            check_discrimination,
        )
        return check_discrimination(cards)
    except Exception:  # noqa: BLE001
        return {"verdict": "INSUFFICIENT_DATA", "suppressed": False}


# ---------------------------------------------------------------------------
# Drop-reason classifiers (mirror sanitizer thresholds)
# ---------------------------------------------------------------------------

# Kept in sync with board_sanitizer constants (read-only; don't import to
# avoid a hard dep; fallback to these literals if the module drifts).
_MATCHUP_BINARY_TOKEN: str = "yes vs no"
_MIN_MARKET_PROB: float = 0.02
_MAX_BEST_ODDS: float = 50.0
_MAX_ABS_EDGE: float = 0.30


def _is_binary(card: Dict[str, Any]) -> bool:
    matchup = card.get("matchup")
    if not isinstance(matchup, str):
        return False
    return _MATCHUP_BINARY_TOKEN in matchup.lower()


def _is_degenerate(card: Dict[str, Any]) -> bool:
    """market_prob below threshold (degenerate or missing)."""
    mp = card.get("market_prob")
    try:
        val = float(mp)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return True
    return not math.isfinite(val) or val < _MIN_MARKET_PROB


def _is_stale_tipoff(card: Dict[str, Any]) -> bool:
    """Stale tipoff stub: card carries tipoff_stale=True OR both best_odds
    and market_prob are unavailable (odds_unavailable pattern)."""
    if card.get("tipoff_stale") is True:
        return True
    # odds_unavailable stub: no best_odds AND no usable market_prob
    bo = card.get("best_odds")
    mp = card.get("market_prob")
    bo_missing = bo is None
    try:
        mp_f = float(mp)  # type: ignore[arg-type]
        mp_missing = not math.isfinite(mp_f) or mp_f == 0.0
    except (TypeError, ValueError):
        mp_missing = True
    return bo_missing and mp_missing


def _is_odds_extreme(card: Dict[str, Any]) -> bool:
    """best_odds above extreme-longshot ceiling."""
    bo = card.get("best_odds")
    if bo is None:
        return False
    try:
        val = float(bo)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return math.isfinite(val) and val > _MAX_BEST_ODDS


def _classify_drop_reason(card: Dict[str, Any]) -> Optional[str]:
    """Return the FIRST drop reason (same priority as sanitizer), or None if kept."""
    if _is_binary(card):
        return "binary"
    if _is_degenerate(card):
        return "degenerate"
    if _is_stale_tipoff(card):
        return "stale_tipoff"
    if _is_odds_extreme(card):
        return "odds_extreme"
    return None


# ---------------------------------------------------------------------------
# Status + honest note constants
# ---------------------------------------------------------------------------

STATUS_OK: str = "ok"
STATUS_INSUFFICIENT_DATA: str = "INSUFFICIENT_DATA"
STATUS_NON_DISCRIMINATING: str = "NON_DISCRIMINATING"
VERDICT_NON_DISCRIMINATING: str = "NON_DISCRIMINATING"

_HONEST_NOTE: str = (
    "OBS-BOARD-SPORT-HEALTH read-only surface. "
    "CALIBRATION not edge; UNITS not $; "
    "non_discriminating=True means model collapsed (fabricated-edge risk); "
    "INSUFFICIENT_DATA when sport bucket is empty."
)


# ---------------------------------------------------------------------------
# Per-sport row builder
# ---------------------------------------------------------------------------

def _build_sport_row(sport: str, cards: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build one health row for the given sport's raw (pre-sanitize) card list."""
    n_total = len(cards)
    if n_total == 0:
        return {
            "sport": sport,
            "n_total": 0,
            "n_served": 0,
            "n_dropped": 0,
            "n_dropped_binary": 0,
            "n_dropped_degenerate": 0,
            "n_dropped_stale_tipoff": 0,
            "n_dropped_odds_extreme": 0,
            "non_discriminating": False,
            "status": STATUS_INSUFFICIENT_DATA,
            "honest_note": _HONEST_NOTE,
        }

    # Classify each card.
    n_binary = n_degenerate = n_stale = n_extreme = 0
    kept: List[Dict[str, Any]] = []

    for card in cards:
        reason = _classify_drop_reason(card)
        if reason == "binary":
            n_binary += 1
        elif reason == "degenerate":
            n_degenerate += 1
        elif reason == "stale_tipoff":
            n_stale += 1
        elif reason == "odds_extreme":
            n_extreme += 1
        else:
            kept.append(card)

    n_dropped = n_binary + n_degenerate + n_stale + n_extreme
    n_served = n_total - n_dropped

    # Cross-check against real sanitizer (trust it over local classifiers).
    try:
        real_kept = _sanitize(cards)
        n_served = len(real_kept)
        n_dropped = n_total - n_served
        kept = real_kept
    except Exception:  # noqa: BLE001
        pass

    # Discrimination check over served cards only.
    non_discrim = False
    if n_served >= 1:
        disc = _check_discrimination(kept)
        non_discrim = disc.get("verdict") == VERDICT_NON_DISCRIMINATING

    if n_served == 0:
        status = STATUS_INSUFFICIENT_DATA
    elif non_discrim:
        status = STATUS_NON_DISCRIMINATING
    else:
        status = STATUS_OK

    return {
        "sport": sport,
        "n_total": n_total,
        "n_served": n_served,
        "n_dropped": n_dropped,
        "n_dropped_binary": n_binary,
        "n_dropped_degenerate": n_degenerate,
        "n_dropped_stale_tipoff": n_stale,
        "n_dropped_odds_extreme": n_extreme,
        "non_discriminating": non_discrim,
        "status": status,
        "honest_note": _HONEST_NOTE,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_sport_health(
    cards: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Compute per-sport board health from a raw (pre-sanitize) best-bet card list.

    Parameters
    ----------
    cards:
        List of BestBetCard dicts.  Each card must carry a "sport" field;
        cards without one are bucketed under sport="unknown".
        The list and dicts are never mutated.

    Returns
    -------
    List[Dict[str, Any]]
        One row per sport (sorted alphabetically by sport name), each containing:
          sport, n_total, n_served, n_dropped, n_dropped_binary,
          n_dropped_degenerate, n_dropped_stale_tipoff, n_dropped_odds_extreme,
          non_discriminating, status, honest_note.
        Empty input -> returns [] (not an error sentinel; caller checks for empty).
    Never raises.
    """
    try:
        return _compute_inner(cards)
    except Exception:  # noqa: BLE001
        return []


def _compute_inner(
    cards: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Inner implementation; wrapped by compute_sport_health."""
    if not isinstance(cards, list):
        return []
    if not cards:
        return []

    # Bucket by sport.
    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for card in cards:
        if not isinstance(card, dict):
            continue
        sport_val = card.get("sport")
        sport = str(sport_val) if sport_val is not None else "unknown"
        buckets[sport].append(card)

    rows = []
    for sport in sorted(buckets.keys()):
        rows.append(_build_sport_row(sport, buckets[sport]))
    return rows


__all__ = [
    "STATUS_OK",
    "STATUS_INSUFFICIENT_DATA",
    "STATUS_NON_DISCRIMINATING",
    "compute_sport_health",
]
