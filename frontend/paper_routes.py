"""frontend.paper_routes -- FastAPI APIRouter for the paper-trail endpoints.

Mounts GET /api/paper/trail and GET /api/paper/clv on top of frontend/serve.py
via a guarded include_router (failure cannot break serve.py boot).

  GET /api/paper/trail
    Returns the full collapsed trail (one row per bet, open->settled merged).
    Query params: sport (str, optional filter) and limit (int, default 200).

  GET /api/paper/clv
    Returns aggregate CLV stats over all settled bets (reuses clv_ledger).

HONESTY: no $ / dollar / roi / profit key anywhere. executed is always False.
CLV = better-number-than-close; positive = good. Proxy closes are labelled.

INVARIANTS: build only under frontend/; <=300 LOC; ASCII-only; no secrets.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from fastapi import APIRouter, Query
    from fastapi.responses import JSONResponse
except Exception as exc:  # pragma: no cover -- fastapi is required at runtime
    raise ImportError(
        "frontend.paper_routes requires fastapi (pip install fastapi)."
    ) from exc

from frontend.paper_trail import clv_summary, read_trail

router = APIRouter()

# -- helpers ------------------------------------------------------------------

_HONEST_NOTE = (
    "Paper-only. executed is always False. "
    "Edges are EV/CLV (probability-space); no $ edge is claimed. "
    "CLV = better-number-than-close (positive = good). "
    "Proxy closes are labelled clv_is_proxy=true."
)


def _trail_response(
    trail: List[Dict[str, Any]],
    sport_filter: Optional[str],
    limit: int,
) -> Dict[str, Any]:
    rows = trail
    if sport_filter:
        rows = [r for r in rows if str(r.get("sport", "")).lower() == sport_filter.lower()]
    rows = rows[:limit]
    return {
        "status": "ok",
        "count": len(rows),
        "trail": rows,
        "honest_note": _HONEST_NOTE,
    }


# -- endpoints ----------------------------------------------------------------

@router.get("/api/paper/trail")
def paper_trail(
    sport: Optional[str] = Query(None, description="Filter by sport (e.g. nba, mlb)"),
    limit: int = Query(200, ge=1, le=2000, description="Max rows to return"),
    ledger: Optional[str] = Query(None, description="Override ledger path (tests only)"),
) -> JSONResponse:
    """Collapsed paper trail: one row per bet (open->settled merged).

    Response shape::

        {
          "status": "ok",
          "count": <int>,
          "trail": [
            {
              "game_id": "<sport>|<matchup>|<ts>",
              "matchup": "<away>@<home>",
              "sport": "<str>",
              "side": "home" | "away",
              "taken_book": "<str>",
              "taken_decimal": <float>,
              "model_prob": <float | null>,
              "model_ev": <float | null>,
              "tier": "<A|B|C|null>",
              "status": "open" | "settled",
              "graded": <bool>,
              "outcome": "win" | "loss" | null,
              "clv_pct": <float | null>,
              "beat_close": <bool | null>,
              "clv_is_proxy": <bool>,
              "clv_note": "<str | null>",
              "executed": false,
              "ts": "<ISO-8601>",
              "settled_at": "<ISO-8601 | null>"
            },
            ...
          ],
          "honest_note": "<str>"
        }

    Never raises (missing ledger -> empty trail, status='ok').
    """
    ledger_path: Optional[Path] = Path(ledger) if ledger else None
    try:
        trail = read_trail(ledger_path=ledger_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("paper_routes /api/paper/trail error: %s", exc)
        trail = []
    return JSONResponse(_trail_response(trail, sport, limit))


@router.post("/api/paper/settle")
def paper_settle(
    ledger: Optional[str] = Query(None, description="Override ledger path (tests only)"),
) -> JSONResponse:
    """Guarded settle pass (BE-P0-03): settle every OPEN paper bet whose game is
    FINAL, then return the grade status so settled history populates.

    PAPER ONLY. Settles ONLY genuinely final games -- never fabricates an outcome
    or a close (a missing close -> clv_pct=None / VOID, not a 0-fill win). Idempotent
    on bet_id, so re-POSTing settles nothing already settled. Never raises -> a feed
    error degrades to a status dict, never a 500 that hides the engine state.
    """
    ledger_path: Optional[Path] = Path(ledger) if ledger else None
    try:
        from scripts.platformkit.grade_paper import grade_open_bets
        result = grade_open_bets(ledger_path)
        result["status"] = "ok"
    except Exception as exc:  # noqa: BLE001
        logger.warning("paper_routes /api/paper/settle error: %s", exc)
        result = {"status": "error", "reason": type(exc).__name__,
                  "n_open": 0, "n_settled_now": 0, "n_pending": 0}
    result["honest_note"] = _HONEST_NOTE
    return JSONResponse(result)


@router.get("/api/paper/clv/series")
def paper_clv_series(
    sport: Optional[str] = Query(None, description="Filter by sport (e.g. nba, mlb)"),
    ledger: Optional[str] = Query(None, description="Override ledger path (tests only)"),
) -> JSONResponse:
    """CLV time series (BE-P1-02/04): one point per SETTLED bet that has a REAL CLV,
    in settle order, with a running cumulative mean.

    Bets with NO real close (clv_pct=None -> VOID/pending) are EXCLUDED from the
    series (never plotted as a 0). Each point carries ts, clv_pct, beat_close,
    clv_is_proxy, and the running mean so the dashboard can draw the CLV trend.

    When NONE of the settled bets have a real closing line the response is still
    status='ok' with count=0 and an explicit no_close reason envelope -- never a
    silent empty. The UI should render this as INSUFFICIENT_DATA with n_no_close
    shown so the user understands WHY the series is empty.
    """
    ledger_path: Optional[Path] = Path(ledger) if ledger else None
    try:
        trail = read_trail(ledger_path=ledger_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("paper_routes /api/paper/clv/series error: %s", exc)
        trail = []

    pts: List[Dict[str, Any]] = []
    running = 0.0
    n_no_close_in_scope = 0
    n_open_in_scope = 0

    for r in trail:
        if sport and str(r.get("sport", "")).lower() != sport.lower():
            continue
        row_status = str(r.get("status", ""))
        if row_status != "settled":
            n_open_in_scope += 1
            continue
        if r.get("clv_pct") is None:
            n_no_close_in_scope += 1
            continue  # no real CLV -> VOID/pending, excluded (never a 0-fill)
        clv = float(r["clv_pct"])
        running += clv
        n = len(pts) + 1
        pts.append({
            "ts": r.get("settled_at") or r.get("ts"),
            "matchup": r.get("matchup"),
            "sport": r.get("sport"),
            "clv_pct": clv,
            "beat_close": r.get("beat_close"),
            "clv_is_proxy": bool(r.get("clv_is_proxy", False)),
            "cumulative_mean_clv_pct": round(running / n, 6),
        })

    resp: Dict[str, Any] = {
        "status": "ok",
        "count": len(pts),
        "series": pts,
        "n_no_close": n_no_close_in_scope,
        "n_open": n_open_in_scope,
        "honest_note": _HONEST_NOTE,
    }

    # When there are no gradeable points (count=0) but there ARE settled bets
    # with no closing line, surface an explicit reason so the UI never shows a
    # silent empty and the caller can render INSUFFICIENT_DATA honestly.
    if len(pts) == 0 and n_no_close_in_scope > 0:
        resp["no_close_reason"] = (
            "no closing lines captured -- INSUFFICIENT_DATA"
        )

    return JSONResponse(resp)


@router.get("/api/paper/clv")
def paper_clv(
    ledger: Optional[str] = Query(None, description="Override ledger path (tests only)"),
) -> JSONResponse:
    """Aggregate CLV stats over all settled bets.

    Response shape::

        {
          "status": "ok",
          "n_bets": <int>,
          "pct_beat_close": <float | null>,
          "mean_clv_pct": <float | null>,
          "clv_is_proxy": <bool>,
          "by_sport": {
            "<sport>": {
              "n": <int>,
              "mean_clv_pct": <float>,
              "pct_beat_close": <float>
            },
            ...
          },
          "note": "<str>",
          "honest_note": "<str>"
        }

    Never raises (empty / missing ledger -> n_bets=0 with all nulls).
    """
    ledger_path: Optional[Path] = Path(ledger) if ledger else None
    try:
        summary = clv_summary(ledger_path=ledger_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("paper_routes /api/paper/clv error: %s", exc)
        summary = {
            "n_bets": 0,
            "pct_beat_close": None,
            "mean_clv_pct": None,
            "clv_is_proxy": False,
            "by_sport": {},
            "note": "CLV ledger unavailable (%s)" % type(exc).__name__,
        }
    summary["status"] = "ok"
    summary["honest_note"] = _HONEST_NOTE
    return JSONResponse(summary)


__all__ = ["router"]
