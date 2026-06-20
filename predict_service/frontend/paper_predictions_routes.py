"""predict_service.frontend.paper_predictions_routes -- GET /api/paper/predictions.

Paginated real model predictions from paper_predictions.jsonl WITH graded results.
Predictions are joined against settled game finals (results_finals.finals) so
settled games carry result='win'/'loss'/'push' and pending games carry
result='pending' or null. No fabrication; no $ field; calibration only.

HONESTY: result = real graded outcome from settled ESPN finals ONLY, or null.
executed=False; edge_claimed=False; real_money_enabled=False; no $ key anywhere.

INVARIANTS: predict_service/frontend/ only; <=300 LOC; ASCII; no secrets.
"""
from __future__ import annotations

import json
import logging
import pathlib
from typing import Any, Callable, Dict, List, Optional

try:
    from fastapi import APIRouter, Query
    from fastapi.responses import JSONResponse
except Exception as exc:  # pragma: no cover
    raise ImportError(
        "paper_predictions_routes requires fastapi (pip install fastapi)."
    ) from exc

logger = logging.getLogger(__name__)

router = APIRouter()

_REPO = pathlib.Path(__file__).resolve().parents[2]
_DEFAULT_JSONL = _REPO / "data" / "frontend" / "paper_predictions.jsonl"

_HONEST_NOTE = (
    "Real model predictions (paper channel) -- executed=False, no real orders. "
    "model_prob is the calibrated model probability. "
    "market_prob = 1/fair_odds where available (null otherwise). "
    "clv is null when no closing line was captured (INSUFFICIENT_DATA). "
    "result is the real graded outcome from settled finals (win/loss/push/pending/null). "
    "No $ / edge / roi / profit is claimed. "
    "edge_claimed=False. real_money_enabled=False."
)

_BANNED_KEYS = ("$", "roi", "pnl", "profit", "dollar")


def _market_prob(row: Dict[str, Any]) -> Optional[float]:
    """Derive market_prob from fair_odds (1/fair_odds). null when unavailable."""
    try:
        fo = float(row.get("fair_odds") or 0)
        if fo > 0:
            return round(1.0 / fo, 6)
    except (TypeError, ValueError):
        pass
    return None


def _clv_from_close_proxy(row: Dict[str, Any]) -> Optional[float]:
    """Derive a CLV estimate from close_proxy when available.

    close_proxy carries {close_decimal_home, close_decimal_away, fair_close_prob}.
    When fair_close_prob is present: clv = model_prob - fair_close_prob.
    Otherwise returns null (INSUFFICIENT_DATA, never fabricated).
    """
    cp = row.get("close_proxy")
    if not isinstance(cp, dict):
        return None
    fcp = cp.get("fair_close_prob")
    if fcp is None:
        return None
    try:
        model_p = float(row.get("model_prob") or 0)
        return round(model_p - float(fcp), 6)
    except (TypeError, ValueError):
        return None


def _clv_status(row: Dict[str, Any]) -> str:
    """'proxy' when close_proxy present, 'no_close' otherwise."""
    if isinstance(row.get("close_proxy"), dict) and row["close_proxy"]:
        return "proxy"
    return "no_close"


def _grade_row(
    row: Dict[str, Any],
    finals_index: Dict[str, Dict[str, Any]],
) -> Optional[str]:
    """Derive the real graded result for one prediction row.

    Looks up the row's event_id in finals_index (settled completed games).
    - No matching final -> None (game not yet settled or not found).
    - Matching final found -> delegates to grade_prediction.
      Returns 'win', 'loss', 'push', or 'pending' when grading is ambiguous.
    Never raises; never fabricates.
    """
    event_id = str(row.get("event_id") or "").strip()
    if not event_id or not finals_index:
        return None
    final = finals_index.get(event_id)
    if final is None:
        return None  # no settled final for this game
    try:
        from predict_service.results_finals import grade_prediction  # noqa: PLC0415
        verdict = grade_prediction(row, final)
    except Exception:  # noqa: BLE001 -- grading failure -> pending, never raise
        verdict = None
    # If the game has a final but grading returned None (ambiguous market),
    # surface 'pending' so the caller knows the game IS settled but we can't
    # derive a win/loss from this market type.
    return verdict if verdict is not None else "pending"


def _shape_row(
    row: Dict[str, Any],
    finals_index: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Project one raw JSONL row to the honest API trade shape.

    Every banned key ($, roi, pnl, profit, dollar) is excluded. executed is
    forced to False. clv is null unless fair_close_prob is present. No tier
    fabrication. result is the REAL graded outcome or None/pending (never
    fabricated).
    """
    return {
        "logged_at":         row.get("logged_at"),
        "sport":             row.get("sport"),
        "matchup":           row.get("matchup"),
        "group":             row.get("group"),
        "selection":         row.get("selection"),
        "model_prob":        row.get("model_prob"),
        "market_prob":       _market_prob(row),
        "side":              row.get("selection"),
        "tier":              None,
        "result":            _grade_row(row, finals_index or {}),
        "clv":               _clv_from_close_proxy(row),
        "clv_status":        _clv_status(row),
        "executed":          False,
        "event_id":          row.get("event_id"),
        "commence_time":     row.get("commence_time"),
        "channel":           "paper",
        "note":              row.get("note"),
    }


def _read_predictions(
    jsonl_path: pathlib.Path,
    sport_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Read and filter all rows from the predictions JSONL. Never raises."""
    if not jsonl_path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        text = jsonl_path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            if sport_filter:
                if str(obj.get("sport", "")).lower() != sport_filter.lower():
                    continue
            rows.append(obj)
    except Exception as exc:  # noqa: BLE001
        logger.warning("paper_predictions_routes: read error %s: %s",
                       jsonl_path, exc)
    return rows


def _build_finals_index_for_sport(
    sport: Optional[str],
    finals_feed: Optional[Callable],
) -> Dict[str, Dict[str, Any]]:
    """Fetch settled finals for *sport* and build an event_id->final index.

    *finals_feed* is an injectable callable(sport) -> list[final] used in tests.
    When None the real results_finals.finals() is used. A fetch failure or fresh
    clone yields an empty index (graceful degradation). Never raises.
    """
    if finals_feed is not None:
        try:
            feed_fn = finals_feed
        except Exception:  # noqa: BLE001
            return {}
    else:
        try:
            from predict_service.results_finals import finals as _finals  # noqa: PLC0415
            feed_fn = _finals
        except Exception:  # noqa: BLE001
            return {}
    # Fetch all relevant sports; when sport filter is set fetch that sport only;
    # otherwise fetch all known sports (best-effort, ignoring failures).
    sports_to_fetch = [sport] if sport else ["nba", "mlb", "soccer_intl", "tennis"]
    index: Dict[str, Dict[str, Any]] = {}
    for sp in sports_to_fetch:
        if not sp:
            continue
        try:
            recs = feed_fn(sp)
            for rec in recs or []:
                gid = str(rec.get("game_id") or "").strip()
                if gid:
                    index[gid] = rec
        except Exception:  # noqa: BLE001 -- one sport failure never blocks others
            pass
    return index


# Module-level injectable for tests (set before request; None = use real finals).
_finals_feed_override: Optional[Callable] = None


@router.get("/api/paper/predictions")
def paper_predictions(
    sport: Optional[str] = Query(
        default=None,
        description="Filter to one sport: nba | mlb | soccer_intl.",
    ),
    offset: int = Query(
        default=0, ge=0,
        description="Pagination offset (0-based).",
    ),
    limit: int = Query(
        default=100, ge=1, le=500,
        description="Max rows per page (default 100, max 500).",
    ),
    file: Optional[str] = Query(
        default=None,
        description="Override jsonl path (tests only).",
    ),
) -> JSONResponse:
    """Paginated model predictions from paper_predictions.jsonl with graded results.

    Each row is a real model view logged at prediction time. Settled games carry
    a real graded result (win/loss/push) derived from ESPN final scores.
    Pending/unmatched games carry result=null or 'pending'. No $ field.
    executed=False always (paper channel). clv is null when no closing line
    exists (INSUFFICIENT_DATA). Missing or empty file -> status='ok', trades=[].
    Never raises to caller. No fabrication.
    """
    path = pathlib.Path(file) if file else _DEFAULT_JSONL
    raw = _read_predictions(path, sport_filter=sport)
    total = len(raw)
    page = raw[offset: offset + limit]
    finals_index = _build_finals_index_for_sport(sport, _finals_feed_override)
    trades = [_shape_row(r, finals_index) for r in page]
    return JSONResponse({
        "status":             "ok",
        "total":              total,
        "offset":             offset,
        "limit":              limit,
        "trades":             trades,
        "edge_claimed":       False,
        "real_money_enabled": False,
        "honest_note":        _HONEST_NOTE,
    })


__all__ = [
    "router",
    "_shape_row",
    "_grade_row",
    "_read_predictions",
    "_market_prob",
    "_clv_from_close_proxy",
    "_clv_status",
    "_build_finals_index_for_sport",
    "_DEFAULT_JSONL",
    "_HONEST_NOTE",
    "_finals_feed_override",
]
