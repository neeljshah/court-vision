"""stale_game_suppressor.py -- BE8-2: stale/completed-game card suppressor.

Pure function over a board card + completion signal.  Two outcomes:
  DEMOTE  -- game complete/timed-out -> status='done', decision='no_bet',
             stake_units cleared, suppressed=True.  Card preserved for display.
  EXCLUDE -- non-sports binary matchup ('yes vs no'), market_prob<DEAD_MARKET_PROB,
             or tipoff > STALE_TIPOFF_HOURS ago with no completion signal -> None.

Completion truth injected via finals list or state_map; delegates to
ingame.postgame_suppress.suppress_verdict (inline fallback when import fails).

RAILS: pure; no network/IO; no $ field; stale-never-green; <=300 LOC; ASCII.
Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \\
    scripts/platformkit/bestbets/test_stale_game_suppressor.py -q
"""
from __future__ import annotations

import copy
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEAD_MARKET_PROB: float = 0.001   # Polymarket dead-contract floor
STALE_TIPOFF_HOURS: float = 12.0  # hours before tipoff -> exclude (no signal)

_COMPLETED_STATES = frozenset({
    "post", "final", "STATUS_FINAL", "STATUS_FULL_TIME",
    "STATUS_FINAL_PEN", "STATUS_FINAL_OVERTIME",
})
_TIPOFF_KEYS = ("tipoff_utc", "tipoff", "game_datetime", "commence_time")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_non_sports_binary(matchup: Any) -> bool:
    if not isinstance(matchup, str):
        return False
    return "yes vs no" in matchup.lower()


def _market_dead(market_prob: Any) -> bool:
    try:
        mp = float(market_prob)
    except (TypeError, ValueError):
        return False
    return math.isfinite(mp) and mp < DEAD_MARKET_PROB


def _parse_utc(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, str):
        try:
            dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            return None
    return None


def _get_tipoff(card: Dict[str, Any]) -> Optional[datetime]:
    for key in _TIPOFF_KEYS:
        tip = _parse_utc(card.get(key))
        if tip is not None:
            return tip
    return None


def _rec_is_complete(rec: Dict[str, Any]) -> bool:
    if bool(rec.get("completed")):
        return True
    state = str(rec.get("state") or "").strip()
    return state.lower() in {"post", "final"} or state in _COMPLETED_STATES


def _completion_reason(
    card: Dict[str, Any],
    finals: Optional[List[Dict[str, Any]]],
    state_map: Optional[Dict[str, Any]],
    now: datetime,
) -> Optional[str]:
    """Return suppression reason or None.  Tries postgame_suppress first."""
    gid = str(card.get("game_id") or card.get("event_id") or "")
    ct_raw = card.get("commence_time") or card.get("tipoff_utc") or card.get("game_datetime")
    ct_str = ct_raw if isinstance(ct_raw, str) else None

    try:
        from scripts.platformkit.ingame.postgame_suppress import suppress_verdict  # noqa
        v = suppress_verdict(gid, finals=finals, state_map=state_map,
                             commence_time=ct_str, now=now)
        if v.get("suppress_bet"):
            return str(v.get("reason", "game_complete"))
        return None
    except Exception:  # noqa: BLE001 -- inline fallback below
        pass

    # Arm 1: finals list
    if finals and gid:
        for rec in finals:
            if isinstance(rec, dict) and str(rec.get("game_id") or "") == gid:
                if _rec_is_complete(rec):
                    return "game_complete_finals_list"

    # Arm 2: state_map
    if state_map and gid:
        entry = state_map.get(gid) or state_map.get(str(gid))
        if isinstance(entry, dict) and _rec_is_complete(entry):
            return "game_complete_state_map"

    # Arm 3: timeout (5 h after commence)
    if ct_str is None and state_map and gid:
        entry = (state_map.get(gid) or state_map.get(str(gid))) or {}
        ct_str = entry.get("commence_time") if isinstance(entry, dict) else None
    if ct_str is not None:
        commence_dt = _parse_utc(ct_str)
        if commence_dt is not None and now >= commence_dt + timedelta(hours=5.0):
            return "game_complete_timeout"

    return None


def _demote(card: Dict[str, Any], reason: str) -> Dict[str, Any]:
    out = copy.deepcopy(card)
    out["status"] = "done"
    out["decision"] = "no_bet"
    out.pop("stake_units", None)
    out["suppressed"] = True
    out["suppress_note"] = reason
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def suppress_card(
    card: Dict[str, Any],
    *,
    finals: Optional[List[Dict[str, Any]]] = None,
    state_map: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
    stale_tipoff_hours: float = STALE_TIPOFF_HOURS,
) -> Optional[Dict[str, Any]]:
    """Suppress or demote a board card.

    Returns
    -------
    Dict or None
        DEMOTED dict (status='done', decision='no_bet', stake_units cleared)
        when game is complete/timed-out.
        None (EXCLUDE) when matchup is 'yes vs no', market_prob dead, or
        tipoff > stale_tipoff_hours without a completion signal.
        Deep copy of original card when live/upcoming.
        Never raises.
    """
    if not isinstance(card, dict):
        return None
    try:
        return _suppress_inner(card, finals, state_map, now, stale_tipoff_hours)
    except Exception as exc:  # noqa: BLE001
        logger.debug("suppress_card error: %s", exc)
        return None


def _suppress_inner(
    card: Dict[str, Any],
    finals: Optional[List[Dict[str, Any]]],
    state_map: Optional[Dict[str, Any]],
    now: Optional[datetime],
    stale_tipoff_hours: float,
) -> Optional[Dict[str, Any]]:
    if now is None:
        now = datetime.now(tz=timezone.utc)

    if _is_non_sports_binary(card.get("matchup")):
        return None

    if _market_dead(card.get("market_prob")):
        return None

    reason = _completion_reason(card, finals, state_map, now)
    if reason:
        return _demote(card, reason)

    tip = _get_tipoff(card)
    if tip is not None and tip < now - timedelta(hours=stale_tipoff_hours):
        return None

    return copy.deepcopy(card)


def apply_suppression(
    cards: List[Dict[str, Any]],
    *,
    finals: Optional[List[Dict[str, Any]]] = None,
    state_map: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
    stale_tipoff_hours: float = STALE_TIPOFF_HOURS,
) -> List[Dict[str, Any]]:
    """Apply suppress_card over a list; drop Nones, keep demoted + live cards."""
    if not cards:
        return []
    try:
        return [
            out for c in cards
            if (out := suppress_card(c, finals=finals, state_map=state_map,
                                     now=now, stale_tipoff_hours=stale_tipoff_hours))
            is not None
        ]
    except Exception as exc:  # noqa: BLE001
        logger.debug("apply_suppression error: %s", exc)
        return []


__all__ = ["DEAD_MARKET_PROB", "STALE_TIPOFF_HOURS", "suppress_card", "apply_suppression"]
