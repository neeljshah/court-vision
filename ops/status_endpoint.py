"""ops.status_endpoint -- the /api/ops/* APIRouter the UI renders.

Exposes the aggregated observability document over HTTP so the React status
page can poll one URL. Mounted (guarded) into predict_service.app, exactly like
the existing paper/report/sse routers -- a failure here can never sink the API.

Routes
------
GET /api/ops/status
    -> ops.health_aggregator.aggregate()  (the one status.json shape)
GET /api/ops/metrics
    -> ops.metrics_rollup.rollup()        (CLV + counts + liveness, no $/ROI)
GET /api/ops/doctor
    -> ops.runbook.doctor()               (structured what-is-wrong diagnosis)

Every route is wrapped so an internal failure returns a degraded sentinel with
status_code 503 (the panel can detect it) rather than a 500.

INVARIANTS: <=300 LOC; ASCII only; never raises out of a handler; no $/ROI.
Build only under ops/.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

try:
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse
except Exception as exc:  # pragma: no cover -- fastapi required at mount time
    raise ImportError(
        "ops.status_endpoint requires fastapi (pip install fastapi)."
    ) from exc

from ops import health_aggregator as _agg
from ops import metrics_rollup as _metrics
from ops import runbook as _runbook

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ops", tags=["ops"])


@router.get("/status")
def ops_status() -> JSONResponse:
    """The aggregated status.json (overall + per-service liveness/freshness)."""
    try:
        return JSONResponse(_agg.aggregate())
    except Exception as exc:  # noqa: BLE001
        logger.warning("ops_status failed: %s", exc)
        return JSONResponse(
            {"overall": "down", "services": [],
             "notes": ["status aggregation failed"]},
            status_code=503,
        )


@router.get("/metrics")
def ops_metrics() -> JSONResponse:
    """CLV + counts + liveness metrics for the status page (no $/ROI)."""
    try:
        return JSONResponse(_metrics.rollup())
    except Exception as exc:  # noqa: BLE001
        logger.warning("ops_metrics failed: %s", exc)
        return JSONResponse(
            {"status": "unavailable", "reason": "metrics rollup failed",
             "clv": None, "liveness": None},
            status_code=503,
        )


@router.get("/doctor")
def ops_doctor() -> JSONResponse:
    """Structured 'what is wrong + what to do' diagnosis."""
    try:
        return JSONResponse(_runbook.doctor())
    except Exception as exc:  # noqa: BLE001
        logger.warning("ops_doctor failed: %s", exc)
        return JSONResponse(
            {"overall": "down", "summary": "doctor failed",
             "problems": [], "ok_services": []},
            status_code=503,
        )


def mount(app: Any) -> bool:
    """Guarded include_router into *app*. Returns True on success, never raises.

    Used by predict_service.app's additive mount block so a bad import here
    degrades the /api/ops/* paths without sinking the rest of the API.
    """
    try:
        app.include_router(router)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("ops.status_endpoint mount failed: %s", exc)
        return False


__all__ = ["router", "mount"]
