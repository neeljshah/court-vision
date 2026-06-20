"""predict_service.frontend.bestbets_board_filter -- pre-serve filter for best-bets board.

QAFIX-2-1: Non-sports Polymarket binary events (home='Yes', away='No') leak onto
the best-bets board as soccer_intl Tier-A cards with absurd odds (666.67/2000) and
fabricated edge_vs_market against a settled/dead market. This module applies a pure
filter before the board is served to the UI.

QAFIX-8 (iter 8): Hardened to cover additional edge cases that slipped through:
  - datetime strings without timezone (naive ISO-8601) now treated as UTC.
  - Cards with no tipoff_utc but a past commence_time/game_datetime/tipoff key
    are now dropped (all known tipoff keys are checked, not just tipoff_utc).
  - market_prob < DEAD_MARKET_PROB (0.001) secondary dead-market signal dropped
    (resolved Polymarket binary contracts collapse to ~0).
  - best_odds > MAX_BEST_ODDS (50.0) secondary staleness signal catches >200 odds.

Drop a card when ANY of the following holds:
  1. matchup contains 'yes vs no' (case-insensitive) -- non-sports Polymarket binary.
  2. market_prob < MIN_MARKET_PROB (0.02) -- degenerate/near-certain market.
  3. market_prob < DEAD_MARKET_PROB (0.001) -- dead/resolved market secondary signal.
  4. best_odds > MAX_BEST_ODDS (50.0) -- extreme longshot; no liquid two-sided market.
  5. Any tipoff key (tipoff_utc, commence_time, game_datetime, tipoff) is present
     and is at or before now -- stale/completed event (stale-never-green).

Reuses constants from board_sanitizer where possible so thresholds stay in sync.

RAILS:
  - Pure module: no IO, no network, no global mutable state.
  - Returns a new list; never mutates the input.
  - ASCII only; <= 300 LOC.
  - No $ / ROI / PnL field anywhere.
  - stale-never-green: past tipoff -> excluded (status 'done' or stale event).
  - Never raises; wraps all type coercions defensively.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Re-use constants from board_sanitizer so thresholds stay in one place.
try:
    from scripts.platformkit.bestbets.board_sanitizer import (  # noqa: PLC0415
        MATCHUP_BINARY_TOKEN,
        MIN_MARKET_PROB,
        MAX_BEST_ODDS,
        DEAD_MARKET_PROB,
    )
except Exception:  # pragma: no cover -- fallback if platformkit not on path
    MATCHUP_BINARY_TOKEN: str = "yes vs no"
    MIN_MARKET_PROB: float = 0.02
    MAX_BEST_ODDS: float = 50.0
    DEAD_MARKET_PROB: float = 0.001

# All card keys that may carry the event start time (ISO-8601 string or datetime).
# Checked in order; first non-None parseable value that is past triggers the drop.
_TIPOFF_KEYS = ("tipoff_utc", "commence_time", "game_datetime", "tipoff")

# ---------------------------------------------------------------------------
# Individual drop predicates
# ---------------------------------------------------------------------------


def _is_non_sports_binary(matchup: Any) -> bool:
    """True when matchup is a Polymarket-style 'Yes vs No' binary event."""
    if not isinstance(matchup, str):
        return False
    return MATCHUP_BINARY_TOKEN in matchup.lower()


def _market_prob_degenerate(market_prob: Any) -> bool:
    """True when market_prob is missing, unparseable, or below the minimum threshold."""
    try:
        mp = float(market_prob)
    except (TypeError, ValueError):
        return True  # unparseable -> treat as degenerate
    if not math.isfinite(mp):
        return True
    return mp < MIN_MARKET_PROB


def _odds_too_extreme(best_odds: Any) -> bool:
    """True when best_odds exceeds the extreme-longshot ceiling."""
    if best_odds is None:
        return False  # missing odds: not sufficient alone to drop
    try:
        bo = float(best_odds)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(bo):
        return True
    return bo > MAX_BEST_ODDS


def _parse_tipoff(raw: Any) -> Optional[datetime]:
    """Parse a raw tipoff value into a tz-aware UTC datetime, or None if unparseable.

    Accepts:
      - datetime objects (naive treated as UTC, aware used as-is).
      - ISO-8601 strings with or without a trailing 'Z' or explicit offset.
      - Naive ISO-8601 strings (no tz suffix) treated as UTC per convention.
    Returns None for any unknown type or unparseable string.
    """
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, str):
        try:
            s = raw.strip().replace("Z", "+00:00")
            tip = datetime.fromisoformat(s)
            if tip.tzinfo is None:
                tip = tip.replace(tzinfo=timezone.utc)
            return tip
        except (ValueError, AttributeError):
            return None
    return None


def _tipoff_in_past(card: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    """True when ANY known tipoff key on the card carries a timestamp in the past.

    Stale-never-green: events that have already started or completed must not appear
    on the live board as actionable bets.  Checks all known event-start keys so that
    a card with no tipoff_utc but a past commence_time is still dropped.

    Parameters
    ----------
    card:
        BestBetCard dict. Checked keys: tipoff_utc, commence_time, game_datetime,
        tipoff (all ISO-8601 string or datetime).
    now:
        Reference UTC datetime. Defaults to datetime.now(timezone.utc). Injectable
        for tests.

    Returns
    -------
    bool
        True -> drop; False -> keep (no parseable tipoff info found, or tipoff is
        strictly in the future).
    """
    if now is None:
        now = datetime.now(tz=timezone.utc)
    for key in _TIPOFF_KEYS:
        raw = card.get(key)
        if raw is None:
            continue
        tip = _parse_tipoff(raw)
        if tip is not None and tip <= now:
            return True
    return False


# ---------------------------------------------------------------------------
# Composite drop decision
# ---------------------------------------------------------------------------


def _market_dead(market_prob: Any) -> bool:
    """True when market_prob is below the dead-market floor (resolved binary contract).

    A resolved Polymarket binary contract collapses its losing side to ~0.  A card
    must never display an edge against such a market.  This is a secondary signal
    that catches cases where market_prob is a very small positive number not caught
    by _market_prob_degenerate (e.g. a 'No' contract at 0.0005).
    """
    try:
        mp = float(market_prob)
    except (TypeError, ValueError):
        return False  # handled by _market_prob_degenerate
    if not math.isfinite(mp):
        return True
    return mp < DEAD_MARKET_PROB


def _should_drop(card: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    """True when the card fails any filter criterion and must be excluded."""
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
    if _tipoff_in_past(card, now=now):
        return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def filter_cards(
    cards: List[Dict[str, Any]],
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Return a filtered list with non-sports binary / stale / degenerate cards removed.

    This is the single pre-serve gate applied by bestbets_board_routes before the
    board JSON is returned to the UI.  It is a pure function: it never mutates the
    input list or any card dict, has no IO, and never raises.

    Parameters
    ----------
    cards:
        List of BestBetCard dicts as produced by bestbets_compute.compute_best_bets.
    now:
        Optional UTC reference time for the tipoff check (injectable for tests).
        Defaults to datetime.now(timezone.utc).

    Returns
    -------
    List[Dict[str, Any]]
        New list containing only cards that pass all criteria.

    Drop criteria (any one triggers removal):
      * matchup contains 'yes vs no' (case-insensitive)          -- Polymarket binary
      * market_prob < 0.02                                        -- degenerate market
      * market_prob < 0.001                                       -- dead/resolved market
      * best_odds > 50.0                                          -- extreme longshot
      * any tipoff key (tipoff_utc/commence_time/game_datetime/tipoff)
        present and at-or-before now                              -- stale/done event
    """
    if not cards:
        return []
    try:
        return [c for c in cards if not _should_drop(c, now=now)]
    except Exception:  # noqa: BLE001 -- never raises from the public surface
        return []


__all__ = [
    "MATCHUP_BINARY_TOKEN",
    "MIN_MARKET_PROB",
    "MAX_BEST_ODDS",
    "DEAD_MARKET_PROB",
    "filter_cards",
]
