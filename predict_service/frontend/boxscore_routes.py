"""predict_service.frontend.boxscore_routes -- FastAPI router for live boxscore.

Exposes:
  GET /api/boxscore/{sport}/{game_id}
    -> {game_id, sport, game_meta: GameMeta, players: [PlayerBoxRow], honest_note}

Only the NBA CDN path is fully populated (keyless, no auth).  For other sports
the endpoint degrades to an empty players list with game_meta.game_status=
"UNAVAILABLE", which is the honest state (no equivalent keyless CDN for MLB,
soccer, tennis player stats at this level).

HONESTY: no $ field; no edge claim; stale-never-green.  If the CDN is down or
the game is not found the response is {status:"unavailable"} + HTTP 200 (not a
500), so the frontend can always read a valid JSON envelope.

INVARIANTS: <=300 LOC; ASCII-only; no secrets; no src/kernel/api imports.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

try:
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse
except ImportError as exc:  # pragma: no cover
    raise ImportError("boxscore_routes requires fastapi") from exc

logger = logging.getLogger(__name__)

router = APIRouter()

_HONEST_NOTE = (
    "Live player boxscore (NBA CDN / ESPN). "
    "No dollar edge is claimed. Calibration only. "
    "Degrades to [] for non-NBA or when the CDN is unavailable."
)

_NBA_SPORTS = {"nba"}


def _fetch_box(game_id: str) -> tuple:
    """Thin wrapper; import is deferred so the router loads even without deps."""
    try:
        from scripts.platformkit.ingame.boxscore_read import fetch_box  # noqa: PLC0415
        return fetch_box(game_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("boxscore_routes: fetch_box failed (%s)", exc)
        meta: Dict[str, Any] = {
            "game_id": game_id, "captured_at": None,
            "game_status": "UNAVAILABLE", "period": 0, "clock": "",
            "home_team": "", "away_team": "",
            "home_score": 0, "away_score": 0,
        }
        return meta, []


@router.get("/api/boxscore/{sport}/{game_id}")
def boxscore(sport: str, game_id: str) -> JSONResponse:
    """Live player boxscore for *sport*/*game_id*.

    NBA: fetches from cdn.nba.com (keyless). Non-NBA: returns empty players list
    with game_meta.game_status=UNAVAILABLE (honest -- no keyless CDN for other
    sports at this time). Never raises; degrades gracefully.

    Response fields:
      game_id       -- as supplied
      sport         -- as supplied
      game_meta     -- {game_id, game_status, period, clock, home/away_team,
                        home/away_score, captured_at}
      players       -- [{player_id, name, team, side, min, pts, reb, ast,
                         fg3m, stl, blk, tov, pf}]  sorted by side then player_id
      honest_note   -- calibration note
      edge_claimed  -- always False
    """
    if sport not in _NBA_SPORTS:
        # Non-NBA: degrade honestly (no equivalent keyless CDN player stats).
        logger.debug("boxscore_routes: non-NBA sport=%s -> UNAVAILABLE", sport)
        return JSONResponse({
            "game_id":      game_id,
            "sport":        sport,
            "game_meta":    {
                "game_id": game_id, "captured_at": None,
                "game_status": "UNAVAILABLE", "period": 0, "clock": "",
                "home_team": "", "away_team": "",
                "home_score": 0, "away_score": 0,
            },
            "players":     [],
            "honest_note": _HONEST_NOTE,
            "edge_claimed": False,
            "note":        f"Boxscore CDN not available for sport={sport!r}",
        })

    try:
        game_meta, players = _fetch_box(game_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("boxscore_routes: unexpected error sport=%s gid=%s (%s)",
                       sport, game_id, exc)
        return JSONResponse({
            "game_id": game_id, "sport": sport,
            "status": "unavailable",
            "reason": str(exc),
            "game_meta": None, "players": [],
            "honest_note": _HONEST_NOTE, "edge_claimed": False,
        })

    # Sort players: home first, then by player_id descending pts for readability.
    players_sorted: List[Dict[str, Any]] = sorted(
        players,
        key=lambda p: (0 if p.get("side") == "home" else 1, -int(p.get("pts", 0))),
    )

    return JSONResponse({
        "game_id":      game_id,
        "sport":        sport,
        "game_meta":    game_meta,
        "players":      players_sorted,
        "honest_note":  _HONEST_NOTE,
        "edge_claimed": False,
    })


__all__ = ["router"]
