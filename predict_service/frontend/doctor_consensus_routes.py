"""predict_service.frontend.doctor_consensus_routes -- /api/ops/doctor (consensus).

QA-DOCTOR-CONSENSUS (P1, QA iter 3+9).  Root cause: ops.runbook._is_problem()
does NOT treat fresh=null as a problem, so a port-probed service with null fresh
reads OK in doctor while /api/ops/autonomy + /api/freshness read degraded.

Fix: pipe every services[] row through status_freshness_normalizer.normalize_rows
(fresh=null->stale, monotone-DOWN rollup) BEFORE computing per-service severity.
This is the single shared normalizer that autonomy + freshness also go through, so
doctor overall == WORST of normalized severities == cannot disagree with autonomy.

Response shape (same as ops.runbook.doctor() so UI needs no changes):
  {overall, summary, problems:[{service,severity,symptom,remedy}],
   ok_services, generated_at, honest_note, edge_claimed}

CONTRACT: fresh=null+age>=sla -> degraded/down (NEVER ok); monotone-DOWN;
fresh child cannot lift stale parent; no $/roi/pnl key; stale-never-green.
INVARIANTS: <=300 LOC; ASCII only; no secrets; no $ field; NEVER raises.
Build only under predict_service/frontend/.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse
except Exception as exc:  # pragma: no cover
    raise ImportError(
        "predict_service.frontend.doctor_consensus_routes requires fastapi."
    ) from exc

from predict_service.status_freshness_normalizer import (
    DEFAULT_SLA_SEC,
    normalize_rows,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ops"])

HONEST_NOTE = (
    "doctor_consensus: freshness derived via status_freshness_normalizer "
    "(fresh=null->stale, monotone-DOWN rollup). overall == WORST of all "
    "normalized service severities. Calibration not edge; no $ field."
)

# SLA overrides matching the supervisor manifest SLA values.
# Default 300s (5 min) for producers; longer for hourly daemons.
_SLA_MAP: Dict[str, float] = {
    "m6_ingame_loop": 300.0,
    "m7_ingame_refresh": 3600.0,
    "m4_selfimprove": 3600.0,
}

# Per-service remedy hints (mirrors ops.runbook._REMEDIES, read-only).
_REMEDIES: Dict[str, str] = {
    "m1_producer": (
        "Producer/scheduler heartbeat stale -- predict-service not writing "
        "data/frontend/predict_service/_heartbeat.json. Restart: .\\boot.ps1"
    ),
    "m1_api_paper": (
        "Auto-API :8099 not answering /health. Restart: .\\boot.ps1. "
        "Verify with: curl http://127.0.0.1:8099/health"
    ),
    "m1_api_boards": (
        "Boards API :8098 port closed. Restart: .\\boot.ps1"
    ),
    "m1_ui": (
        "Next.js UI :3000 down. Restart: .\\boot.ps1 or npm run dev "
        "in court-visions. Non-critical: backend keeps serving."
    ),
    "m1_paper": (
        "Paper auto_loop not running. Restart: .\\boot.ps1. Non-critical."
    ),
    "m1_line_daemon": (
        "Line snapshot daemon stale -- odds going stale. Restart: .\\boot.ps1"
    ),
    "m6_ingame_loop": (
        "In-game live_loop heartbeat stale -- live re-pricing stopped. "
        "Restart: .\\boot.ps1. Check data/frontend/ingame/_heartbeat.json age."
    ),
    "m2_inplay": (
        "In-play capture daemon (P2) heartbeat stale. Restart: .\\boot.ps1. "
        "Non-critical (capture only). Check logs/m2_inplay.err."
    ),
    "m4_selfimprove": (
        "Self-improve daemon (P4) heartbeat stale -- ratchet stopped. "
        "Restart: .\\boot.ps1. Resumes from checkpoint. Non-critical."
    ),
    "m7_ingame_refresh": (
        "In-game refresh loop (P7) heartbeat stale -- beats hourly; "
        "stale means genuinely dead. Restart: .\\boot.ps1. "
        "Check data/cache/daemon_heartbeats/m7_ingame_refresh.txt age."
    ),
}

_DEFAULT_REMEDY = (
    "Service heartbeat stale or port closed. Restart: .\\boot.ps1 "
    "(posix: bash boot.sh) and inspect logs/<name>.err."
)

# Severity rank for monotone-DOWN operations in this module.
_RANK = {"ok": 0, "degraded": 1, "down": 2}
_BY_RANK = {0: "ok", 1: "degraded", 2: "down"}


def _degrade(current: str, candidate: str) -> str:
    """Monotone-DOWN: return the WORSE of two severities. NEVER raises."""
    cur = _RANK.get(current, 1)
    cand = _RANK.get(candidate, 1)
    return _BY_RANK[max(cur, cand)]


def _row_severity(norm_row: Dict[str, Any]) -> str:
    """Map a NORMALIZED row (fresh already coerced) -> ok/degraded/down.

    fresh='fresh' -> ok (unless heartbeat dead or breaker OPEN)
    fresh='stale' -> degraded
    fresh='down'  -> down
    live=False    -> down (heartbeat absent)
    breaker='OPEN'-> down
    """
    if norm_row.get("live") is False:
        return "down"
    if norm_row.get("breaker") == "OPEN":
        return "down"
    fresh = norm_row.get("fresh")
    if fresh == "down":
        return "down"
    if fresh == "stale":
        return "degraded"
    return "ok"


def _symptom(norm_row: Dict[str, Any]) -> str:
    """Human-readable symptom string from a normalized row."""
    reason = norm_row.get("reason") or norm_row.get("_norm_reason")
    fresh = norm_row.get("fresh", "unknown")
    if reason:
        base = str(reason)
    elif norm_row.get("breaker") == "OPEN":
        base = "circuit breaker OPEN (repeated failures)"
    elif fresh in ("stale", "down"):
        base = "data source %s" % fresh
    else:
        base = "not live"
    age = norm_row.get("age_sec")
    if age is not None:
        try:
            base += " (last seen %.0fs ago)" % float(age)
        except (TypeError, ValueError):
            pass
    port = norm_row.get("port")
    if port is not None:
        base += " [port %s]" % port
    return base


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _aggregate_services() -> List[Dict[str, Any]]:
    """Pull the raw services[] from health_aggregator. Returns [] on failure."""
    try:
        from ops import health_aggregator as _agg  # noqa: PLC0415
        doc = _agg.aggregate()
        rows = doc.get("services") or []
        return [r for r in rows if isinstance(r, dict)]
    except Exception as exc:  # noqa: BLE001
        logger.warning("doctor_consensus: health_aggregator.aggregate failed: %s", exc)
        return []


def build_diagnosis(
    services: Optional[List[Dict[str, Any]]] = None,
    *,
    sla_sec: float = DEFAULT_SLA_SEC,
    sla_map: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Build the consensus doctor diagnosis dict from raw services[] rows.

    This is the testable pure function: accepts an injected services list so
    tests can feed any shape without touching the filesystem or real aggregator.

    Returns the doctor envelope with the same shape as ops.runbook.doctor() so
    the UI can consume either route without changes.

    NEVER raises.
    """
    try:
        raw = services if services is not None else _aggregate_services()
        sla_override = sla_map if sla_map is not None else _SLA_MAP

        norm_result = normalize_rows(raw, default_sla_sec=sla_sec,
                                     sla_map=sla_override)
        norm_rows: List[Dict[str, Any]] = norm_result.get("rows") or []

        problems: List[Dict[str, Any]] = []
        ok_services: List[str] = []
        overall = "ok"

        for nr in norm_rows:
            name = nr.get("name") or "?"
            sev = _row_severity(nr)
            overall = _degrade(overall, sev)
            if sev != "ok":
                # Map row severity to critical/warning using the 'critical' field.
                crit = bool(nr.get("critical"))
                problems.append({
                    "service": name,
                    "severity": "critical" if crit else "warning",
                    "symptom": _symptom(nr),
                    "remedy": _REMEDIES.get(name, _DEFAULT_REMEDY),
                })
            else:
                ok_services.append(name)

        if not norm_rows:
            # No rows at all: cannot assert healthy -> degrade.
            overall = _degrade(overall, "degraded")

        if not problems:
            summary = "All %d services healthy (overall=%s)." % (
                len(ok_services), overall)
        else:
            crits = [p["service"] for p in problems if p["severity"] == "critical"]
            summary = "%d problem(s); overall=%s. Critical: %s." % (
                len(problems), overall, ", ".join(crits) or "none")

        return {
            "overall": overall,
            "summary": summary,
            "problems": problems,
            "ok_services": ok_services,
            "generated_at": _utc_iso(),
            "honest_note": HONEST_NOTE,
            "edge_claimed": False,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("doctor_consensus.build_diagnosis failed: %s", exc)
        return {
            "overall": "down",
            "summary": "doctor_consensus internal error (%s)" % type(exc).__name__,
            "problems": [],
            "ok_services": [],
            "generated_at": _utc_iso(),
            "honest_note": HONEST_NOTE,
            "edge_claimed": False,
        }


@router.get("/api/ops/doctor")
def ops_doctor_consensus() -> JSONResponse:
    """Consensus doctor: derives freshness through normalize_rows so this route
    NEVER disagrees with /api/ops/autonomy + /api/freshness for the same poll.

    A service row with fresh=null and age_sec >= sla -> severity 'degraded',
    NEVER 'ok'. overall is the WORST of all normalized service severities.
    """
    try:
        diag = build_diagnosis()
        return JSONResponse(diag)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ops_doctor_consensus handler failed: %s", exc)
        return JSONResponse(
            {"overall": "down",
             "summary": "doctor_consensus handler error (%s)" % type(exc).__name__,
             "problems": [], "ok_services": [],
             "honest_note": HONEST_NOTE,
             "edge_claimed": False},
            status_code=503,
        )


def register(app: Any) -> bool:
    """Guarded include_router into *app*.  Returns True on success, never raises.

    Called from predict_service.core_mounts BEFORE the unavailable fallback for
    /api/ops/doctor so this consensus route takes precedence.
    """
    try:
        app.include_router(router)
        logger.info("doctor_consensus_routes: /api/ops/doctor consensus mounted")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("doctor_consensus_routes: mount failed: %s", exc)
        return False


__all__ = ["router", "register", "build_diagnosis", "HONEST_NOTE"]
