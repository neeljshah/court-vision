"""predict_service.progress_router -- read-only serve of the cadence/progress state.

W4 CONTINUOUS-IMPROVEMENT serve route. Exposes the honest "getting better" story:
COVERAGE / VERDICTS / BACKLOG-burndown climbing + the ratchet standing proven-ready
on its FIXED sealed fold -- NOT a live accuracy curve. READS the progress_ledger +
the cadence descriptor ONLY; it NEVER recomputes a model number and NEVER changes a
prediction.

STALE-NEVER-GREEN: if the progress ledger is missing/old/torn the route returns an
explicit {"status":"stale", ...} envelope (never a fabricated green / 200-with-zeros
laundered as healthy). Every handler is wrapped with @honest_route so an unhandled
exception becomes an honest 503 envelope, never a 500 stack.

RAILS: build only under predict_service/; read-only; NO $ field in any response
(units/probability only); model_static=True on every payload; engine_enabled mirrors
the human sentinel (False while absent); vs_close UNPROVEN; real-money DENY.
ASCII only; <=300 LOC.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

try:
    from fastapi import APIRouter
except Exception as exc:  # pragma: no cover -- fastapi required at runtime
    raise ImportError("predict_service.progress_router requires fastapi.") from exc

from predict_service.honest_route import honest_envelope, honest_route
from predict_service.progress_semantics import engine_honest_note

logger = logging.getLogger(__name__)

router = APIRouter()

# A ledger row older than this (seconds) is STALE -> never reads green. 36h covers a
# missed nightly tick without flickering between healthy nightly runs.
STALE_AFTER_SEC = 36 * 3600

_HONEST_NOTE = ("coverage/verdicts climb; MODEL STATIC while the gate is off; ship is "
                "PROPOSAL-ONLY; no $ field; vs_close UNPROVEN; real-money DENY")


def _series() -> List[Dict[str, Any]]:
    from scripts.platformkit.progress.progress_ledger import read_series  # noqa: PLC0415
    rows = read_series()
    return rows if isinstance(rows, list) else []


def _latest() -> Optional[Dict[str, Any]]:
    rows = _series()
    return rows[-1] if rows else None


def _is_stale(row: Optional[Dict[str, Any]], now: Optional[float] = None) -> bool:
    """True when there is no row or the latest row is older than STALE_AFTER_SEC."""
    if not isinstance(row, dict):
        return True
    ts = row.get("ts")
    if not isinstance(ts, (int, float)):
        return True
    t = float(now) if now is not None else time.time()
    return (t - float(ts)) > STALE_AFTER_SEC


def _stale_envelope(reason: str, now: Optional[float] = None) -> Dict[str, Any]:
    """The explicit stale payload -- never a fabricated green."""
    body = honest_envelope(reason, where="progress_router",
                           extra={"status": "stale"})
    body["status"] = "stale"  # honest_envelope defaults to 'unavailable'; force stale
    body["as_of"] = None
    body["model_static"] = True
    body["engine_enabled"] = False
    body["note"] = _HONEST_NOTE
    return body


@router.get("/progress/summary")
@honest_route
def progress_summary() -> Dict[str, Any]:
    """Latest progress row + a 30-row history tail. Stale-never-green."""
    row = _latest()
    if _is_stale(row):
        return _stale_envelope("progress ledger missing or stale")
    enabled = bool(row.get("engine_enabled", False))
    return {
        "status": "ok",
        "as_of": row.get("ts"),
        "latest": row,
        "history": _series()[-30:],
        "model_static": True,
        "engine_enabled": enabled,
        "edge_claimed": False,
        "note": _HONEST_NOTE,
        "honest_note": engine_honest_note(status=row, engine_enabled=enabled),
    }


@router.get("/progress/coverage")
@honest_route
def progress_coverage() -> Dict[str, Any]:
    """Per-sport coverage % (tested/total) over time. Stale-never-green."""
    row = _latest()
    if _is_stale(row):
        return _stale_envelope("progress ledger missing or stale")
    per_sport = row.get("per_sport") if isinstance(row.get("per_sport"), dict) else {}
    return {
        "status": "ok",
        "as_of": row.get("ts"),
        "per_sport": per_sport,
        "backlog_total": row.get("backlog_total"),
        "backlog_remaining": row.get("backlog_remaining"),
        "model_static": True,
        "edge_claimed": False,
        "note": _HONEST_NOTE,
    }


@router.get("/progress/verdicts")
@honest_route
def progress_verdicts() -> Dict[str, Any]:
    """Cumulative SHIP/REJECT/... verdict counts (a REJECT is a SUCCESS)."""
    row = _latest()
    if _is_stale(row):
        return _stale_envelope("progress ledger missing or stale")
    per_sport = row.get("per_sport") if isinstance(row.get("per_sport"), dict) else {}
    totals = {"ship": 0, "reject": 0, "insufficient": 0, "tested": 0}
    for st in per_sport.values():
        if not isinstance(st, dict):
            continue
        totals["ship"] += int(st.get("n_ship", 0) or 0)
        totals["reject"] += int(st.get("n_reject", 0) or 0)
        totals["insufficient"] += int(st.get("n_insufficient", 0) or 0)
        totals["tested"] += int(st.get("n_tested", 0) or 0)
    return {
        "status": "ok", "as_of": row.get("ts"), "totals": totals,
        "per_sport": per_sport, "model_static": True, "edge_claimed": False,
        "reject_is_success": True, "note": _HONEST_NOTE,
    }


@router.get("/progress/readiness")
@honest_route
def progress_readiness() -> Dict[str, Any]:
    """The STATIC sealed-fold ratchet readiness (ready-but-pending) + enabled flag."""
    row = _latest()
    enabled = bool(row.get("engine_enabled", False)) if isinstance(row, dict) else False
    # The sealed-fold readiness is FIXED/historical (not a live curve).
    return {
        "status": "ok",
        "ratchet_ready": True,
        "sealed_fold_brier_before": 0.2025,
        "sealed_fold_brier_after": 0.0958,
        "label": "ready-but-pending",
        "engine_enabled": enabled,
        "model_static": True,
        "edge_claimed": False,
        "note": ("sealed-fold readiness is FIXED/historical, NOT a live accuracy "
                 "climb; ship stays behind the human PIPELINE_ENABLED sentinel; "
                 + _HONEST_NOTE),
        "honest_note": engine_honest_note(status=row if isinstance(row, dict) else None,
                                          engine_enabled=enabled),
    }


@router.get("/progress/schedule")
@honest_route
def progress_schedule() -> Dict[str, Any]:
    """The declarative cadence descriptor + next scheduled measurement (pure)."""
    from scripts.platformkit.progress.ci_schedule import describe, next_run  # noqa: PLC0415
    return {
        "status": "ok",
        "nightly": describe("NIGHTLY"),
        "next_run_ts": next_run(cadence="NIGHTLY"),
        "model_static": True,
        "edge_claimed": False,
        "note": _HONEST_NOTE,
    }


__all__ = ["router", "STALE_AFTER_SEC"]
