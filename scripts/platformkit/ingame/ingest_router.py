"""scripts.platformkit.ingame.ingest_router -- sport -> live-state parser router.

Routes a platform sport id to its live-state parser (nba -> domains.basketball_nba.
live_state_nba) and ingests the parsed GameStates onto a StateBus. Sport-blind by
design: new sports register a parser here without touching the bus or the loop.

HONEST + SAFE (binding):
  * An unknown sport, a missing parser, or a parser error returns [] / None --
    never a fabricated game. Guarded so a bad payload never raises into the loop.
  * STATE only: no prediction, no edge claim. Validated numbers come downstream.
  * Offline: parsers take an INJECTED payload; no network here or at import.

INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; no secrets.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.ingame.state_bus import GameState, StateBus, STATE_BUS

logger = logging.getLogger(__name__)

# A live-state parser: ESPN scoreboard payload -> list[GameState]. Lazy-imported so
# importing the router never drags in a domain unless that sport is used.
ParserFn = Callable[[Optional[Dict[str, Any]]], List[GameState]]


def _norm_sport(sport: str) -> str:
    s = str(sport).lower()
    return {"basketball_nba": "nba", "worldcup": "soccer_intl",
            "wc": "soccer_intl"}.get(s, s)


def _nba_parser() -> ParserFn:
    from domains.basketball_nba.live_state_nba import parse_scoreboard
    return parse_scoreboard


# sport id -> a zero-arg factory returning its parser (lazy import inside).
_PARSER_FACTORIES: Dict[str, Callable[[], ParserFn]] = {
    "nba": _nba_parser,
}


def supported_sports() -> List[str]:
    return sorted(_PARSER_FACTORIES)


def get_parser(sport: str) -> Optional[ParserFn]:
    """Return the live-state parser for *sport*, or None for an unknown/broken one.

    Never raises: an unknown sport or a parser that fails to import yields None
    (caller degrades, never fabricates).
    """
    factory = _PARSER_FACTORIES.get(_norm_sport(sport))
    if factory is None:
        return None
    try:
        return factory()
    except Exception as exc:  # noqa: BLE001 - missing/broken parser -> None, not raise
        logger.warning("ingest_router: parser load failed for %s: %s", sport, exc)
        return None


def parse(sport: str, payload: Optional[Dict[str, Any]]) -> List[GameState]:
    """Parse *payload* for *sport* into GameStates. [] on unknown sport or any error."""
    parser = get_parser(sport)
    if parser is None:
        logger.info("ingest_router: no parser for sport '%s'", sport)
        return []
    try:
        states = parser(payload)
    except Exception as exc:  # noqa: BLE001 - one bad payload never sinks the loop
        logger.warning("ingest_router: parse error for %s: %s", sport, exc)
        return []
    return [s for s in states if isinstance(s, GameState)]


def ingest(sport: str, payload: Optional[Dict[str, Any]],
           bus: Optional[StateBus] = None) -> List[GameState]:
    """Parse *payload* for *sport* and publish each GameState onto *bus*.

    Returns the published states. Uses the process-wide STATE_BUS when *bus* is
    None. Unknown sport / parse error -> [] (nothing published, never fabricated).
    """
    target = bus if bus is not None else STATE_BUS
    states = parse(sport, payload)
    for gs in states:
        target.publish(gs)
    return states
