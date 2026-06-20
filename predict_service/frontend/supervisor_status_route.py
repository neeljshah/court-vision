"""predict_service.frontend.supervisor_status_route -- GET /api/ops/supervisor.

Reads data/frontend/ops/supervisor_status.json (written by the supervisor daemon)
and returns the SupervisorStatus shape the FE LiveIndicator
(p5api.getSupervisorStatus) expects.

STALE-NEVER-GREEN invariant:
  live=True ONLY when ALL of these hold simultaneously:
    1. The file exists and is valid JSON.
    2. updated_at is present and not older than STALE_SEC seconds.
    3. Every proc is probe-healthy (see _proc_ok below).
  Any other condition -> status=unavailable, live=False. Never fabricate green.

KIND-AWARE freshness:
  'none'              -> ok iff proc.ready is True (alive = sufficient).
  'http' / 'http-200' -> ok iff http probe passed (detail.status==200) OR ready=True.
  'heartbeat*'        -> ok iff age_sec is not None AND age_sec <= fresh_sec.
  Anything else       -> follow proc.ready.

NO $ field. edge_claimed=False always. Read-only. UNITS not $.

INVARIANTS: <=300 LOC; ASCII only; no src/ imports; no network I/O.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# How old (seconds) the updated_at heartbeat may be before we consider the
# supervisor feed stale. The Next.js route uses 120s; match it exactly.
_STALE_SEC: float = 120.0

# Canonical path: repo-root / data / frontend / ops / supervisor_status.json.
# Resolve relative to this file's location (predict_service/frontend/) which is
# two levels below the repo root.
_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_DEFAULT_STATUS_PATH: Path = (
    _REPO_ROOT / "data" / "frontend" / "ops" / "supervisor_status.json"
)


def _unavailable(reason: str, status_code: int = 503) -> JSONResponse:
    """Honest degrade -- never green, never fabricated, no $."""
    return JSONResponse(
        {
            "status": "unavailable",
            "live": False,
            "overall": "down",
            "reason": reason,
            "all_ready": False,
            "any_degraded": True,
            "procs": [],
            "restarts_total": 0,
            "uptime_sec": None,
            "age_sec": None,
            "edge_claimed": False,
        },
        status_code=status_code,
    )


def _probe_kind(proc: Dict[str, Any]) -> str:
    """Extract the readiness probe kind from a proc dict. Returns 'none' as default."""
    detail = proc.get("detail")
    if isinstance(detail, dict):
        k = detail.get("kind")
        if isinstance(k, str):
            return k.lower()
    return "none"


def _proc_ok(proc: Dict[str, Any]) -> bool:
    """Return True when the proc is probe-healthy (kind-aware).

    Kind semantics:
      'none'               -- healthy iff proc.ready is True (alive = sufficient).
      'http' / 'http-200'  -- healthy iff http probe passed: detail.status==200
                              OR (no status field but proc.ready is True).
      'heartbeat*'         -- healthy iff age_sec is not None AND age_sec <= fresh_sec.
                              null age_sec (heartbeat file never written) -> NOT healthy.
      anything else        -- follow proc.ready.

    A proc with state != 'READY' or ready=False is never healthy regardless of kind.
    """
    # Process-level sanity: must be alive and in READY state.
    if proc.get("ready") is False:
        return False
    state = proc.get("state", "")
    if isinstance(state, str) and state.upper() != "READY":
        return False

    kind = _probe_kind(proc)
    detail = proc.get("detail") or {}

    # kind='none': alive is sufficient.
    if kind == "none":
        return True

    # http probes: use the http status from the probe result if present,
    # otherwise fall back to proc.ready (already True at this point).
    if kind in ("http", "http-200"):
        status = detail.get("status") if isinstance(detail, dict) else None
        if isinstance(status, int):
            return status == 200
        # No explicit status recorded -> trust proc.ready (already passed above).
        return True

    # Heartbeat probes: age_sec must be present and within SLA.
    if "heartbeat" in kind:
        age = detail.get("age_sec") if isinstance(detail, dict) else None
        fresh = detail.get("fresh_sec") if isinstance(detail, dict) else None
        if not isinstance(age, (int, float)):
            # Heartbeat file never written -> genuinely not healthy.
            return False
        if not isinstance(fresh, (int, float)):
            # No SLA defined; can't validate -> treat as not healthy.
            return False
        return float(age) <= float(fresh)

    # tcp / unknown: follow proc.ready (already True at this point).
    return True


def _proc_degraded(proc: Dict[str, Any]) -> bool:
    """Return True when the proc is not probe-healthy. Inverse of _proc_ok."""
    return not _proc_ok(proc)


def _fresh_label(proc: Dict[str, Any]) -> str:
    """Return 'ok' when the proc is probe-healthy, 'stale' otherwise."""
    return "ok" if _proc_ok(proc) else "stale"


def _build_proc(proc: Dict[str, Any]) -> Dict[str, Any]:
    """Map a raw proc dict to the SupervisorProc shape the FE expects."""
    detail = proc.get("detail") or {}
    kind = _probe_kind(proc)
    ok = _proc_ok(proc)
    return {
        "name": proc.get("name", ""),
        "state": proc.get("state", ""),
        "ready": proc.get("ready"),
        "restarts": int(proc.get("restarts", 0)),
        "degraded": not ok,
        "ok": ok,
        "fresh": _fresh_label(proc),
        "heartbeat_age_sec": detail.get("age_sec") if isinstance(detail, dict) else None,
        "heartbeat_fresh_sec": detail.get("fresh_sec") if isinstance(detail, dict) else None,
        "kind": kind,
    }


def read_supervisor_status(
    status_path: Optional[Path] = None,
) -> JSONResponse:
    """Core logic -- separated for testability.

    *status_path* defaults to _DEFAULT_STATUS_PATH. Tests can pass a tmp path.
    Returns a JSONResponse with the SupervisorStatus shape (200 on success,
    503 on any honest-degrade condition).
    """
    path = status_path or _DEFAULT_STATUS_PATH

    # -- 1. Read file -----------------------------------------------------------
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _unavailable("supervisor_status.json missing or unreadable")
    except OSError as exc:
        logger.warning("supervisor_status_route: read failed: %s", exc)
        return _unavailable("supervisor_status.json unreadable")

    # -- 2. Parse JSON ----------------------------------------------------------
    try:
        doc: Dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError:
        return _unavailable("supervisor_status.json torn / not JSON")

    # -- 3. Staleness check -----------------------------------------------------
    now_sec = time.time()
    updated = doc.get("updated_at")
    if not isinstance(updated, (int, float)):
        return _unavailable("supervisor_status.json has no updated_at heartbeat")

    age_sec = max(0.0, now_sec - float(updated))
    if age_sec > _STALE_SEC:
        return _unavailable(
            f"supervisor_status.json stale ({round(age_sec)}s > {int(_STALE_SEC)}s SLA)"
        )

    # -- 4. Derive green-condition ----------------------------------------------
    raw_procs: List[Dict[str, Any]] = doc.get("procs") or []
    if not isinstance(raw_procs, list):
        raw_procs = []

    # any_degraded is derived from per-proc probe-healthy checks (kind-aware).
    # This replaces the old heartbeat-only staleness check: http-200 and kind='none'
    # services that emit no heartbeat file are healthy iff their probe passed.
    any_degraded: bool = any(_proc_degraded(p) for p in raw_procs)

    # all_ready: honest probe-level liveness, not just the file's all_ready flag.
    # If the file says all_ready=True but a proc's probe is now unhealthy, we
    # surface that immediately rather than trusting a potentially stale stamp.
    all_ready: bool = bool(raw_procs) and not any_degraded

    # GREEN ONLY when: fresh AND all_ready AND no degraded proc.
    live: bool = all_ready and not any_degraded  # freshness enforced above

    overall: str = "ok" if live else ("down" if any_degraded else "degraded")

    restarts_total: int = sum(
        int(p.get("restarts", 0)) for p in raw_procs
        if isinstance(p.get("restarts"), (int, float))
    )

    started_at = doc.get("started_at")
    uptime_sec: Optional[float] = (
        max(0.0, now_sec - float(started_at))
        if isinstance(started_at, (int, float))
        else None
    )

    return JSONResponse(
        {
            "status": "ok",
            "live": live,
            "overall": overall,
            "profile": doc.get("profile"),
            "all_ready": all_ready,
            "any_degraded": any_degraded,
            "n_procs": len(raw_procs),
            "restarts_total": restarts_total,
            "uptime_sec": uptime_sec,
            "started_at": started_at if isinstance(started_at, (int, float)) else None,
            "updated_at": float(updated),
            "age_sec": age_sec,
            "procs": [_build_proc(p) for p in raw_procs],
            "edge_claimed": False,
        }
    )


@router.get("/api/ops/supervisor")
def get_supervisor_status() -> JSONResponse:
    """GET /api/ops/supervisor -- real daemon state from supervisor_status.json.

    Returns the SupervisorStatus shape the FE LiveIndicator expects:
      {status, live, overall, profile, all_ready, any_degraded, n_procs,
       restarts_total, uptime_sec, started_at, updated_at, age_sec,
       procs: [SupervisorProc], edge_claimed: false}

    live=True ONLY when file is FRESH (<=120s) AND all_ready AND no proc degraded.
    Missing/stale/torn file -> status=unavailable, live=False, 503.
    No $ field. Stale-never-green.
    """
    return read_supervisor_status()


__all__ = ["router", "read_supervisor_status"]
