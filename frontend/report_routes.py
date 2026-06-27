"""frontend.report_routes -- APIRouter for GET /api/report/{sport}/{game_id}.

Exposes the full per-game report from frontend.report.build_report over HTTP.
Mounted into predict_service.app with a guarded include_router identical to the
paper_routes pattern so a boot failure here never sinks the rest of the API.

Endpoints
---------
GET /api/report/{sport}/{game_id}
    Full per-game report (status='ok') or the clean unavailable sentinel.
    Returns build_report(sport, game_id) verbatim -- never raises, never
    fabricates. Shape is documented in frontend/report.py.

GET /api/report/{sport}
    Light browse list: available game_ids for *sport* from the canonical store
    (status='ok' envelope only). Powers the browse grid in the React UI.
    Returns::

        {
          "status": "ok" | "unavailable",
          "sport": "<str>",
          "game_ids": ["<str>", ...],
          "count": <int>,
          "generated_at": "<ISO-8601>" | null,
          "honest_note": "<str>"
        }

HONESTY: no $-edge / roi / profit key anywhere; all fields are real or explicit
null/unavailable sentinels; honest_note carried on every response.

INVARIANTS: build only under frontend/; <=300 LOC; ASCII only; no secrets;
no $ key; reuse build_report + read_latest verbatim.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Same env var as predict_service.app so test monkeypatches flow through.
_STORE_DIR_ENV = "PREDICT_SERVICE_STORE_DIR"


def _store_out_dir() -> Optional[str]:
    """Resolve the store root override from the environment, or None."""
    val = os.environ.get(_STORE_DIR_ENV)
    return val or None

try:
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse
except Exception as exc:  # pragma: no cover -- fastapi required at runtime
    raise ImportError(
        "frontend.report_routes requires fastapi (pip install fastapi)."
    ) from exc

from predict_service.contracts import HONEST_NOTE

router = APIRouter()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UNAVAIL_NOTE = (
    "Calibrated decision-support only. No $ edge is claimed. "
    "All fields are real or explicit null/unavailable sentinels."
)


def _report(sport: str, game_id: str) -> Dict[str, Any]:
    """Thin guarded wrapper around build_report; degrades to a sentinel on error."""
    try:
        from frontend.report import build_report  # noqa: PLC0415
        return build_report(sport, game_id, store_out_dir=_store_out_dir())
    except Exception as exc:  # noqa: BLE001 -- report must never 500
        logger.warning("report_routes: build_report failed (%s %s): %s",
                       sport, game_id, exc)
        return {
            "status": "unavailable",
            "sport": str(sport),
            "game_id": str(game_id),
            "reason": "report build failed (%s)" % type(exc).__name__,
            "pregame": None,
            "markets": [],
            "edges": [],
            "live": {"status": "unavailable", "reason": "report build failed"},
            "intel": None,
            "meta": {"as_of": None, "honest_note": HONEST_NOTE,
                     "schema_version": "1.0.0"},
        }


def _game_list(sport: str) -> Dict[str, Any]:
    """Return available game_ids for *sport* from the canonical store.

    Never raises. Unknown sport or unavailable snapshot -> status='unavailable'
    with an empty game_ids list and an honest reason string.
    """
    try:
        from predict_service.store import read_latest  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        logger.warning("report_routes: store import failed: %s", exc)
        return {
            "status": "unavailable",
            "sport": str(sport),
            "game_ids": [],
            "count": 0,
            "generated_at": None,
            "honest_note": HONEST_NOTE,
            "reason": "store module unavailable (%s)" % type(exc).__name__,
        }
    try:
        env = read_latest(str(sport), out_dir=_store_out_dir())
    except Exception as exc:  # noqa: BLE001 -- store.read_latest is guarded but belt+braces
        logger.warning("report_routes: read_latest(%s) error: %s", sport, exc)
        return {
            "status": "unavailable",
            "sport": str(sport),
            "game_ids": [],
            "count": 0,
            "generated_at": None,
            "honest_note": HONEST_NOTE,
            "reason": "store read error (%s)" % type(exc).__name__,
        }
    if getattr(env, "status", "") != "ok":
        return {
            "status": "unavailable",
            "sport": str(sport),
            "game_ids": [],
            "count": 0,
            "generated_at": getattr(env, "generated_at", None),
            "honest_note": HONEST_NOTE,
            "reason": "snapshot unavailable (%s)" % (env.note or "no snapshot"),
        }
    game_ids: List[str] = [str(p.game_id) for p in env.predictions]
    return {
        "status": "ok",
        "sport": str(sport),
        "game_ids": game_ids,
        "count": len(game_ids),
        "generated_at": env.generated_at or None,
        "honest_note": HONEST_NOTE,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/api/report/{sport}/{game_id}")
def report_game(sport: str, game_id: str) -> JSONResponse:
    """Full per-game report for (sport, game_id).

    Returns build_report(sport, game_id) verbatim -- the ok variant or the
    clean unavailable sentinel. NEVER raises. NEVER fabricates a $ edge.
    """
    body = _report(sport, game_id)
    return JSONResponse(body)


@router.get("/api/report/{sport}")
def report_sport_list(sport: str) -> JSONResponse:
    """Browse list: available game_ids for *sport* from the canonical store.

    Returns a light dict with game_ids[] and count so the React browse grid can
    enumerate games without downloading the full SnapshotEnvelope.
    """
    body = _game_list(sport)
    return JSONResponse(body)


__all__ = ["router"]
