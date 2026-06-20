"""scripts.platformkit.ingame.postgame_suppress -- post-game suppression verdict.

Workstream R6-1-postgame-suppress.

Derives a {suppress_bet, freshness, reason} verdict for a single game so that the
per-game /api/v1/edges and /api/v1/bestbets paths NEVER serve decision:'bet' +
fresh badge on a completed (state=post/Final) game.

QA iter 11 P1: NYK@SAS Final served 'bet 1 unit' tier B with freshness fresh. Root
cause: suppression was never derived from game-completion truth -- only from
odds captured_at. This module closes that hole.

Design
------
Completion truth is injected (NOT imported from predict_service directly) via one of:
  - A finals list  (list[dict] where each dict has 'game_id', 'completed', 'state')
    as returned by predict_service.results_finals.finals() -- read pattern only.
  - A state dict   (game_id -> {completed, state, commence_time})
    for callers that already have a state snapshot.

Two independent completion signals (either triggers suppress):
  1. EXPLICIT:  the game appears in a finals list with completed=True OR state=='post'.
  2. TIMEOUT:   commence_time (ISO-8601 UTC) + MAX_GAME_DURATION_H is in the past.
     -- catches games the scoreboard hasn't refreshed yet.
     -- future commence -> not suppressed by this arm.
     -- missing commence -> not suppressed by this arm (conservative).

Return shape (never raises, no $ field):
  {
    "suppress_bet": bool,
    "freshness":    "stale" | "live" | "unknown",
    "reason":       str,
  }

RAILS: pure (injectable now); no network; no src/kernel/api imports; no $ field;
ASCII only; <=300 LOC.

CLI:
  python -m scripts.platformkit.ingame.postgame_suppress <game_id> [commence_iso]
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# Max game duration used for the timeout arm.  NBA games rarely exceed 3.5 h
# (4 OT periods); use 5 h as a conservative buffer covering all supported sports.
MAX_GAME_DURATION_H: float = 5.0

# State values that definitively signal a completed game.
_COMPLETED_STATES = frozenset({"post", "final", "STATUS_FINAL",
                               "STATUS_FULL_TIME", "STATUS_FINAL_PEN",
                               "STATUS_FINAL_OVERTIME"})


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #

def suppress_verdict(
    game_id: str,
    *,
    finals: Optional[List[Dict[str, Any]]] = None,
    state_map: Optional[Dict[str, Dict[str, Any]]] = None,
    commence_time: Optional[str] = None,
    now: Optional[datetime] = None,
    max_game_duration_h: float = MAX_GAME_DURATION_H,
) -> Dict[str, Any]:
    """Return a suppression verdict for *game_id*.

    Parameters
    ----------
    game_id:
        The canonical event id (string, as stored in finals lists and state maps).
    finals:
        Optional list of settled-final dicts as returned by
        predict_service.results_finals.finals() -- each dict must carry at minimum
        'game_id' and at least one of 'completed' (bool) or 'state' (str).
        The caller decides when and how to fetch this list; this function is pure.
    state_map:
        Optional mapping of game_id -> {completed, state, commence_time} for
        callers that already hold a state snapshot.  Checked AFTER finals.
    commence_time:
        ISO-8601 UTC string (e.g. '2026-06-19T18:00:00Z') for the timeout arm.
        Takes precedence over any commence_time in state_map.  Optional -- when
        absent AND not in state_map, the timeout arm is skipped (conservative).
    now:
        Injectable UTC reference datetime for deterministic tests.
        Defaults to datetime.now(timezone.utc).
    max_game_duration_h:
        Hours added to commence_time for the timeout threshold (default 5 h).

    Returns
    -------
    Dict[str, Any]:
        {
          "suppress_bet": bool,
          "freshness":    "stale" | "live" | "unknown",
          "reason":       str,
        }
    Never raises; no $ field.
    """
    if now is None:
        now = datetime.now(tz=timezone.utc)

    gid = str(game_id)

    # --- Arm 1: explicit finals list ------------------------------------------
    if finals:
        for rec in finals:
            if not isinstance(rec, dict):
                continue
            if str(rec.get("game_id") or "") != gid:
                continue
            if _rec_is_complete(rec):
                return _suppressed("game_complete_finals_list")

    # --- Arm 2: state_map entry -----------------------------------------------
    if state_map:
        entry = state_map.get(gid) or state_map.get(str(gid))
        if isinstance(entry, dict) and _rec_is_complete(entry):
            return _suppressed("game_complete_state_map")

    # --- Arm 3: timeout (commence_time + max_game_duration_h < now) -----------
    ct_str = commence_time
    if ct_str is None and state_map:
        entry = (state_map.get(gid) or state_map.get(str(gid))) or {}
        ct_str = entry.get("commence_time")
    if ct_str is not None:
        commence_dt = _parse_utc(ct_str)
        if commence_dt is not None:
            deadline = commence_dt + timedelta(hours=max_game_duration_h)
            if now >= deadline:
                return _suppressed("game_complete_timeout")

    # --- Not suppressed -------------------------------------------------------
    return {
        "suppress_bet": False,
        "freshness": "live",
        "reason": "game_not_complete",
    }


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

def _rec_is_complete(rec: Dict[str, Any]) -> bool:
    """Return True if a finals/state record indicates the game is complete."""
    if bool(rec.get("completed")):
        return True
    state = str(rec.get("state") or "").strip()
    if state.lower() in {"post", "final"}:
        return True
    if state in _COMPLETED_STATES:
        return True
    return False


def _suppressed(reason: str) -> Dict[str, Any]:
    return {
        "suppress_bet": True,
        "freshness": "stale",
        "reason": reason,
    }


def _parse_utc(s: str) -> Optional[datetime]:
    """Parse an ISO-8601 UTC string to a timezone-aware datetime. None on failure."""
    try:
        cleaned = s.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError, TypeError):
        return None


# --------------------------------------------------------------------------- #
# CLI (for manual inspection only)                                             #
# --------------------------------------------------------------------------- #

def _cli() -> None:  # pragma: no cover
    import sys
    args = sys.argv[1:]
    if not args:
        print("usage: postgame_suppress <game_id> [commence_iso]")
        sys.exit(1)
    gid = args[0]
    ct = args[1] if len(args) > 1 else None
    verdict = suppress_verdict(gid, commence_time=ct)
    import json as _json
    print(_json.dumps(verdict, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    _cli()


__all__ = [
    "suppress_verdict",
    "MAX_GAME_DURATION_H",
]
