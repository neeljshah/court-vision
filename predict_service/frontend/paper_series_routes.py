"""predict_service.frontend.paper_series_routes -- paper P&L series + bankroll.

Serves the daemon-written paper-trail summaries verbatim so the webapp can render
the paper-track-record panel WITHOUT recomputing anything:

  GET /api/paper/pnl/series
      Returns data/frontend/paper_pnl_series.json verbatim. Schema:
        {start_units, points:[{ts,day,balance_units,daily_units,cumulative_units,
         n_bets,n_win,n_loss}], daily:[{day,daily_units}],
         summary:{total_units,n_bets,n_win,n_loss,n_push,win_rate,
         mean_clv_pct_or_INSUFFICIENT,current_units},
         honest_note, edge_claimed:false, executed:false}

  GET /api/paper/bankroll
      Returns data/frontend/paper_bankroll.json verbatim. Schema:
        {start_units,current_units,updated_at,honest_note}

HONESTY (binding):
  * UNITS only -- never a $ / pnl_dollars / roi / profit field.
  * A positive curve here is a PAPER track record, not realized profit; CLV is the
    honest yardstick and may be INSUFFICIENT.
  * edge_claimed=false; executed=false stamped on the series envelope.
  * UNAVAILABLE-HONEST: a missing / unreadable / non-dict file returns
    {status:"unavailable", honest_note:"..."} with HTTP 200 -- NEVER a fabricated
    curve, never a fabricated balance.

INVARIANTS: predict_service/frontend/ only; <=300 LOC; ASCII; no secrets.
"""
from __future__ import annotations

import json
import logging
import pathlib
from typing import Any, Dict, Optional

try:
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse
except Exception as exc:  # pragma: no cover -- fastapi required at runtime
    raise ImportError(
        "paper_series_routes requires fastapi (pip install fastapi)."
    ) from exc

logger = logging.getLogger(__name__)

router = APIRouter()

_REPO = pathlib.Path(__file__).resolve().parents[2]
_SERIES_PATH = _REPO / "data" / "frontend" / "paper_pnl_series.json"
_BANKROLL_PATH = _REPO / "data" / "frontend" / "paper_bankroll.json"

_SERIES_UNAVAILABLE_NOTE = (
    "Paper P&L series unavailable -- the summary file is missing or unreadable. "
    "No curve is fabricated. UNITS only; a positive paper curve is a track record, "
    "not realized profit; CLV is the honest yardstick. edge_claimed=False; "
    "executed=False; real money stays default-DENY."
)
_BANKROLL_UNAVAILABLE_NOTE = (
    "Paper bankroll unavailable -- the summary file is missing or unreadable. "
    "No balance is fabricated. UNITS only (never $). edge_claimed=False; "
    "executed=False; real money stays default-DENY."
)

# Keys that must never appear in a paper summary (defense-in-depth; the honesty
# middleware also gates these, but we never want to emit them in the first place).
_BANNED_KEYS = ("pnl_dollars", "roi", "profit", "dollar", "usd", "bankroll_usd")


def _strip_banned(obj: Any) -> Any:
    """Recursively drop any banned $/roi key from a loaded summary. Never raises."""
    if isinstance(obj, dict):
        return {
            k: _strip_banned(v)
            for k, v in obj.items()
            if str(k).lower() not in _BANNED_KEYS
        }
    if isinstance(obj, list):
        return [_strip_banned(v) for v in obj]
    return obj


def _load_summary(path: pathlib.Path) -> Optional[Dict[str, Any]]:
    """Read + parse a paper summary JSON file. None on any miss (missing/corrupt)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        doc = json.loads(text)
    except FileNotFoundError:
        return None
    except Exception as exc:  # noqa: BLE001 -- torn/corrupt file -> unavailable
        logger.warning("paper_series_routes: read error %s: %s", path, exc)
        return None
    if not isinstance(doc, dict):
        return None
    return doc


@router.get("/api/paper/pnl/series")
def paper_pnl_series() -> JSONResponse:
    """Return the paper P&L series JSON verbatim, or an honest unavailable sentinel.

    The file is served as-is (banned $/roi keys stripped as defense-in-depth).
    A missing/unreadable/non-dict file yields {status:"unavailable", honest_note}
    with HTTP 200 -- never a fabricated curve.
    """
    doc = _load_summary(_SERIES_PATH)
    if doc is None:
        return JSONResponse({
            "status": "unavailable",
            "honest_note": _SERIES_UNAVAILABLE_NOTE,
            "edge_claimed": False,
            "executed": False,
            "points": [],
            "daily": [],
            "summary": None,
        })
    body = _strip_banned(doc)
    # Stamp the honesty rails (idempotent if already present in the file).
    body.setdefault("edge_claimed", False)
    body.setdefault("executed", False)
    return JSONResponse(body)


@router.get("/api/paper/bankroll")
def paper_bankroll() -> JSONResponse:
    """Return the paper bankroll JSON verbatim, or an honest unavailable sentinel.

    A missing/unreadable/non-dict file yields {status:"unavailable", honest_note}
    with HTTP 200 -- never a fabricated balance. UNITS only; no $ field.
    """
    doc = _load_summary(_BANKROLL_PATH)
    if doc is None:
        return JSONResponse({
            "status": "unavailable",
            "honest_note": _BANKROLL_UNAVAILABLE_NOTE,
            "edge_claimed": False,
            "executed": False,
            "start_units": None,
            "current_units": None,
            "updated_at": None,
        })
    body = _strip_banned(doc)
    body.setdefault("edge_claimed", False)
    body.setdefault("executed", False)
    return JSONResponse(body)


__all__ = [
    "router",
    "_load_summary",
    "_strip_banned",
    "_SERIES_PATH",
    "_BANKROLL_PATH",
    "_SERIES_UNAVAILABLE_NOTE",
    "_BANKROLL_UNAVAILABLE_NOTE",
]
