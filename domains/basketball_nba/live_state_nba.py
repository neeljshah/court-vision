"""domains.basketball_nba.live_state_nba -- ESPN live scoreboard -> NBA GameState.

Parses ESPN's keyless public scoreboard payload (the same feed
scripts.platformkit.frontend.live_board already pulls) into the sport-blind
GameState carried by the in-game spine. We REUSE live_board's battle-tested event
normalizer (_parse_event) and its NBA elapsed-minutes math (_nba_elapsed) rather
than re-deriving them, so there is exactly one parse of the ESPN shape.

HONEST + SAFE (binding):
  * NEVER fabricates. A malformed event, an absent game, or a non-NBA payload
    yields None (or is skipped) -- never an invented score or clock.
  * STATE only: no prediction, no edge. The validated in-game number is produced
    downstream and is eval-gated.
  * Offline-testable: the payload is INJECTED; no network at import or in tests.

FRESHNESS: we stash elapsed_min + period_len_sec into GameState.extras so the
repricer can compute fraction_elapsed() -- the only validated in-game lever
(variance must SHRINK as the game progresses).

INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; no secrets.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from scripts.platformkit.frontend import live_board as _lb
from scripts.platformkit.ingame.state_bus import GameState

logger = logging.getLogger(__name__)

SPORT = "nba"
_PERIOD_LEN_SEC = 12.0 * 60.0  # NBA regulation quarter length.


def _clock_to_sec(clock: Optional[str]) -> Optional[float]:
    """ESPN displayClock ('5:00' = time REMAINING in the period) -> seconds, or None."""
    if not clock or ":" not in str(clock):
        return None
    try:
        mm, ss = str(clock).split(":")
        return max(0.0, float(mm) * 60.0 + float(ss))
    except (ValueError, TypeError):
        return None


def _status_from_state(state: Optional[str]) -> str:
    """ESPN 'pre'|'in'|'post' -> sport-blind 'pre'|'live'|'final'."""
    return {"pre": "pre", "in": "live", "post": "final"}.get(state or "", "pre")


def _game_id(ev: Dict[str, Any], row: Dict[str, Any]) -> str:
    """Stable game id: ESPN event id when present, else an away@home fallback."""
    eid = ev.get("id")
    if eid:
        return str(eid)
    return f"{row.get('away_abbr') or row.get('away')}@" \
           f"{row.get('home_abbr') or row.get('home')}"


def state_from_event(ev: Dict[str, Any]) -> Optional[GameState]:
    """One ESPN scoreboard event -> an NBA GameState, or None if unparseable.

    Reuses live_board._parse_event for the home/away/score/clock/period extraction
    (single source of truth for the ESPN shape), then maps it onto GameState.
    Never raises; a malformed event returns None (not a fabricated game).
    """
    try:
        row = _lb._parse_event(ev, SPORT)
    except Exception as exc:  # noqa: BLE001 - one bad event never sinks ingest
        logger.warning("live_state_nba parse failed: %s", exc)
        return None
    if row is None:
        return None
    status = _status_from_state(row.get("state"))
    clock_sec = _clock_to_sec(row.get("clock"))
    elapsed_min = _lb._nba_elapsed(row.get("period"), row.get("clock"))
    extras: Dict[str, Any] = {
        "detail": row.get("detail"),
        "home_team": row.get("home"), "away_team": row.get("away"),
        "home_abbr": row.get("home_abbr"), "away_abbr": row.get("away_abbr"),
        "period_len_sec": _PERIOD_LEN_SEC,
    }
    if elapsed_min is not None:
        extras["elapsed_min"] = elapsed_min
    return GameState(
        sport=SPORT,
        game_id=_game_id(ev, row),
        period=row.get("period"),
        clock_sec=clock_sec,
        home_score=row.get("home_score") or 0,
        away_score=row.get("away_score") or 0,
        possession=None,  # ESPN scoreboard does not expose possession; never faked.
        status=status,
        extras=extras,
    )


def parse_scoreboard(payload: Optional[Dict[str, Any]]) -> List[GameState]:
    """An ESPN NBA scoreboard payload -> a list of GameState (one per parseable game).

    Malformed / empty payloads yield [] (never a fabricated game). Per-event parse
    errors are skipped individually so one bad event never drops the whole slate.
    """
    if not isinstance(payload, dict):
        return []
    events = payload.get("events")
    if not isinstance(events, list):
        return []
    out: List[GameState] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        gs = state_from_event(ev)
        if gs is not None:
            out.append(gs)
    return out


def state_for_game(payload: Optional[Dict[str, Any]],
                   game_id: str) -> Optional[GameState]:
    """The GameState for a specific *game_id* in *payload*, or None if absent.

    Absence is honest: an unknown / missing game returns None, never a fabricated
    placeholder.
    """
    for gs in parse_scoreboard(payload):
        if gs.game_id == str(game_id):
            return gs
    return None
