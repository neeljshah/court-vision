"""frontend.results_routes -- settled game finals for outcome display (read-only).

BE-P0-09. Surfaces the keyless settled-finals reader so a history view can show
the underlying game result next to a graded bet (so the user can confirm WHY a
bet graded win/loss).

  GET /api/results/{sport}[?game_id=]
      Settled finals: [{game_id, home, away, home_score, away_score, completed,
      state, status_detail, commence_time}]. Only COMPLETED games appear; an
      in-progress game is never reported as a final.

HONESTY: scores are the real reported finals or nothing -- never fabricated. No $
field. Outcome display only, calibration not edge. Never raises: a network /
fresh-clone miss degrades to an empty list with status='ok'.

INVARIANTS: build only under frontend/; <=300 LOC; ASCII only; no $ key; no secrets.
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

try:
    from fastapi import APIRouter, Query
    from fastapi.responses import JSONResponse
except Exception as exc:  # pragma: no cover -- fastapi required at runtime
    raise ImportError("frontend.results_routes requires fastapi.") from exc

logger = logging.getLogger(__name__)

router = APIRouter()

HONEST_NOTE = (
    "Settled game finals for outcome display only. Real reported scores or "
    "nothing -- never fabricated. No $ edge is claimed."
)


@router.get("/api/results/{sport}")
def results_for_sport(sport: str,
                      game_id: Optional[str] = Query(None)) -> JSONResponse:
    """Settled finals for *sport* (optionally one game_id). Never raises."""
    try:
        from predict_service.results_finals import finals  # noqa: PLC0415
        rows: List[dict] = finals(sport)
    except Exception as exc:  # noqa: BLE001 -- a miss is an empty list, not a crash
        logger.warning("results_routes /%s: finals failed: %s", sport, exc)
        return JSONResponse({
            "status": "unavailable", "sport": sport,
            "reason": "finals read failed (%s)" % type(exc).__name__,
            "results": [], "count": 0,
            "honest_note": HONEST_NOTE, "edge_claimed": False,
        })
    if game_id is not None:
        rows = [r for r in rows if r.get("game_id") == game_id]
    return JSONResponse({
        "status": "ok", "sport": sport,
        "results": rows, "count": len(rows),
        "honest_note": HONEST_NOTE, "edge_claimed": False,
    })


__all__ = ["router"]
