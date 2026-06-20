"""board_sanitizer.py -- drop degenerate / non-sports binary cards before serving.

QA1-board-sanitizer: Polymarket binary events (Yes vs No) and pathological odds
produce garbage best-bet cards that erode user trust and break calibration.
This module provides a pure sanitize() step that removes them.

Drop a card when ANY of the following holds:
  1. matchup contains 'yes vs no' (case-insensitive) -- non-sports binary event.
  2. market_prob < 0.02 -- near-certain / degenerate market.
  3. best_odds > 50   -- extreme longshot; no liquid two-sided market.
  4. |edge_vs_market| > 0.30 -- gap too wide; almost certainly stale/corrupt data.
  5. tipoff_utc / game_datetime is at or before now (UTC) -- stale/completed event
     served as live edge against a resolved market (stale-never-green).
  6. market_prob < 0.001 -- secondary dead-market signal (a resolved Polymarket
     'No'/'Yes' contract collapses to ~0); a card must never display an edge
     against a resolved/stale market.

QA-ISSUE-1 (stale/dead market): a soccer_intl card (Polymarket binary, tipoff
nearly a year past, market_prob ~0.0005) was served as a pregame Tier-A edge.
Criteria 1, 5 and 6 close that hole at the source.

RAILS:
  - Pure module: no network, no global state. Reads the wall clock ONLY for the
    stale-tipoff check (a UTC `now` is injectable for deterministic tests).
  - Returns a new list; never mutates the input.
  - ASCII only; <= 300 LOC.
  - No $ / ROI / PnL field.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Thresholds (module-level constants so callers can inspect them in tests).
MATCHUP_BINARY_TOKEN: str = "yes vs no"
MIN_MARKET_PROB: float = 0.02
MAX_BEST_ODDS: float = 50.0
MAX_ABS_EDGE: float = 0.30
# Secondary dead-market signal: a resolved binary contract collapses to ~0.
DEAD_MARKET_PROB: float = 0.001
# Card keys that may carry the event start time (ISO-8601 string or datetime).
_TIPOFF_KEYS = ("tipoff_utc", "tipoff", "game_datetime", "commence_time")


def _is_non_sports_binary(matchup: Any) -> bool:
    """Return True when matchup is a Polymarket-style 'Yes vs No' binary."""
    if not isinstance(matchup, str):
        return False
    return MATCHUP_BINARY_TOKEN in matchup.lower()


def _market_prob_degenerate(market_prob: Any) -> bool:
    """Return True when market_prob is below the minimum meaningful threshold."""
    try:
        mp = float(market_prob)
    except (TypeError, ValueError):
        return True  # unparseable -> treat as degenerate
    if not math.isfinite(mp):
        return True
    return mp < MIN_MARKET_PROB


def _odds_too_extreme(best_odds: Any) -> bool:
    """Return True when best_odds is above the extreme-longshot ceiling."""
    if best_odds is None:
        return False  # missing odds: don't filter on this criterion alone
    try:
        bo = float(best_odds)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(bo):
        return True
    return bo > MAX_BEST_ODDS


def _edge_too_wide(edge_vs_market: Any) -> bool:
    """Return True when |edge_vs_market| exceeds the corruption threshold."""
    try:
        ev = float(edge_vs_market)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(ev):
        return True
    return abs(ev) > MAX_ABS_EDGE


def _market_dead(market_prob: Any) -> bool:
    """Return True when market_prob is below the dead-market floor (resolved book).

    Secondary signal for a resolved/settled binary contract whose price has
    collapsed to ~0. A card must never display an edge against such a market.
    """
    try:
        mp = float(market_prob)
    except (TypeError, ValueError):
        return False  # handled by _market_prob_degenerate instead
    if not math.isfinite(mp):
        return True
    return mp < DEAD_MARKET_PROB


def _tipoff_in_past(card: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    """Return True when the card's event start time is at or before *now* (UTC).

    Stale-never-green: an event that has already started/completed must not be
    served as a live/pregame edge. Checks every known tipoff key; accepts an
    ISO-8601 string (with or without a trailing 'Z') or a datetime. A missing or
    unparseable time is NOT a drop on this criterion alone (returns False).
    """
    if now is None:
        now = datetime.now(tz=timezone.utc)
    for key in _TIPOFF_KEYS:
        raw = card.get(key)
        if raw is None:
            continue
        tip: Optional[datetime] = None
        if isinstance(raw, datetime):
            tip = raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
        elif isinstance(raw, str):
            try:
                s = raw.strip().replace("Z", "+00:00")
                tip = datetime.fromisoformat(s)
                if tip.tzinfo is None:
                    tip = tip.replace(tzinfo=timezone.utc)
            except (ValueError, AttributeError):
                tip = None
        if tip is not None and tip <= now:
            return True
    return False


def _should_drop(card: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    """Return True when the card fails any sanitization criterion."""
    if not isinstance(card, dict):
        return True  # garbage entry -> drop
    if _is_non_sports_binary(card.get("matchup")):
        return True
    if _market_prob_degenerate(card.get("market_prob")):
        return True
    if _market_dead(card.get("market_prob")):
        return True
    if _odds_too_extreme(card.get("best_odds")):
        return True
    if _edge_too_wide(card.get("edge_vs_market")):
        return True
    if _tipoff_in_past(card, now=now):
        return True
    return False


def sanitize(
    cards: List[Dict[str, Any]],
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Return a filtered list with degenerate / non-sports binary cards removed.

    Parameters
    ----------
    cards:
        List of BestBetCard dicts as produced by bestbets_compute.

    Returns
    -------
    List[Dict[str, Any]]
        New list containing only the cards that pass all sanity checks.
        The original list and card dicts are not mutated.

    *now* is an injectable UTC reference time for the stale-tipoff check
    (defaults to datetime.now(timezone.utc)); pass it for deterministic tests.

    Drop criteria (any one triggers removal):
      * matchup contains 'yes vs no' (case-insensitive)
      * market_prob < 0.02
      * market_prob < 0.001 (dead/resolved market secondary signal)
      * best_odds > 50
      * |edge_vs_market| > 0.30
      * tipoff_utc / game_datetime at or before now (stale/completed event)
    """
    if not cards:
        return []
    return [c for c in cards if not _should_drop(c, now=now)]


__all__ = [
    "MATCHUP_BINARY_TOKEN",
    "MIN_MARKET_PROB",
    "MAX_BEST_ODDS",
    "MAX_ABS_EDGE",
    "DEAD_MARKET_PROB",
    "sanitize",
]
