"""predict_service.produce_status -- producer freshness + guarded refresh routes.

BE-P0-04. Surfaces the canonical-store producer's per-sport freshness so the UI
(and an operator) can tell "lines are stale / never produced" apart from "no
games on the slate", and offers a GUARDED refresh that runs produce_once for the
active sports before serving.

  GET /api/produce/status
      Per sport: {generated_at, age_seconds, ok, status, n_games, n_markets}.
      ok=True only when a real snapshot exists AND its status=='ok'. A missing /
      unavailable snapshot reads ok=False with status carried verbatim -- a STALE
      or absent producer can NEVER read fresh/green (stale-never-green rail).

  POST /api/produce/refresh   (guarded)
      Runs produce.produce_once for the active sports (or a ?sport= subset) and
      reports each result. Guarded by REFRESH_ENABLED_ENV: refresh is DISABLED by
      default (returns 403 'refresh disabled') so a public deployment cannot be
      driven to spin the producer; an operator sets PREDICT_SERVICE_REFRESH=1.

Both endpoints NEVER raise: every failure degrades to an explicit sentinel. No $
field is emitted -- this is freshness observability only, calibration not edge.

INVARIANTS: build only under predict_service/; <=300 LOC; ASCII only; no secrets;
no $ field; reuse store/registry/produce verbatim.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from fastapi import APIRouter, Query
    from fastapi.responses import JSONResponse
except Exception as exc:  # pragma: no cover -- fastapi required at runtime
    raise ImportError("predict_service.produce_status requires fastapi.") from exc

from predict_service import produce, registry, store
from predict_service.honest_route import honest_route
from predict_service.produce_sla_degrade import (
    evaluate_scheduler_gap,
    evaluate_sport_freshness,
)
from predict_service.scheduler import read_heartbeat

logger = logging.getLogger(__name__)

router = APIRouter()

# Same env var the app/bestbets use so test monkeypatches flow through.
_STORE_DIR_ENV = "PREDICT_SERVICE_STORE_DIR"
# Refresh is OFF by default. An operator opts in; a public deploy cannot spin it.
REFRESH_ENABLED_ENV = "PREDICT_SERVICE_REFRESH"

HONEST_NOTE = (
    "Producer freshness only. ok=True requires a real 'ok' snapshot; a missing or "
    "stale producer reads ok=False (stale-never-green). No $ edge is claimed."
)


def _store_out_dir() -> Optional[str]:
    val = os.environ.get(_STORE_DIR_ENV)
    return val or None


def _parse_iso(ts: Any) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _age_seconds(generated_at: Any) -> Optional[float]:
    """Whole seconds since generated_at, or None if it cannot be parsed."""
    dt = _parse_iso(generated_at)
    if dt is None:
        return None
    now = datetime.now(timezone.utc)
    return max(0.0, round((now - dt).total_seconds(), 1))


def _active_sports() -> List[str]:
    try:
        return list(registry.active_sports())
    except Exception as exc:  # noqa: BLE001 -- registry is guarded; belt + braces
        logger.warning("produce_status: active_sports failed: %s", exc)
        return []


def _status_for(sport: str, out_dir: Optional[str]) -> Dict[str, Any]:
    """One sport's freshness entry with SLA-degrade evaluation. NEVER raises.

    Applies the shared SLA-degrade evaluator (produce_sla_degrade) so that a
    sport whose snapshot age >= its SLA degrades ok to False even when the
    envelope itself has status='ok'.  Stale-never-green: an existing but stale
    snapshot can NEVER read ok=True.
    """
    try:
        env = store.read_latest(sport, out_dir=out_dir)
    except Exception as exc:  # noqa: BLE001 -- a read miss is not-fresh
        logger.warning("produce_status: read_latest(%s) failed: %s", sport, exc)
        return {"sport": sport, "ok": False, "status": "unavailable",
                "generated_at": None, "age_seconds": None,
                "n_games": 0, "n_markets": 0,
                "reason": "read error (%s)" % type(exc).__name__,
                "honest_note": HONEST_NOTE, "edge_claimed": False}

    age = _age_seconds(env.generated_at)
    # Apply the shared SLA-degrade evaluator (Rule A: age vs SLA).
    sla_result = evaluate_sport_freshness(sport, age_sec=age,
                                          snapshot_status=env.status)
    ok = sla_result["ok"]  # False when age>=SLA OR snapshot_status != 'ok'
    return {
        "sport": sport,
        "ok": bool(ok),
        "status": env.status,
        "generated_at": env.generated_at or None,
        "age_seconds": age,
        "n_games": len(env.predictions),
        "n_markets": len(env.markets),
        "reason": None if ok else (env.note or "snapshot age exceeded SLA"),
        "sla_severity": sla_result.get("severity"),
        "honest_note": HONEST_NOTE,
        "edge_claimed": False,
    }


@router.get("/api/produce/status")
@honest_route(extra={"sports": [], "n_sports": 0, "any_fresh": False})
def produce_status(sport: Optional[str] = Query(None)) -> JSONResponse:
    """Per-sport producer freshness with SLA-degrade + scheduler-gap check.

    In addition to per-sport age checks (Rule A via produce_sla_degrade), the
    rollup also checks whether any registered sport was silently dropped from
    the scheduler's last heartbeat sports_run (Rule B -- Iter-2 P1 gap).
    Never raises; no $ field.
    """
    out_dir = _store_out_dir()
    sports = [sport.lower()] if sport else _active_sports()
    entries = [_status_for(s, out_dir) for s in sports]
    any_ok = any(e["ok"] for e in entries)

    # Rule B: scheduler sports_run gap check.
    scheduler_gap: Optional[Dict[str, Any]] = None
    try:
        hb = read_heartbeat(out_dir)
        sports_run = hb.get("sports_run") if isinstance(hb, dict) else []
        if sports_run is None:
            sports_run = []
        gap_result = evaluate_scheduler_gap(sports, list(sports_run))
        if gap_result.get("gap_detected"):
            scheduler_gap = gap_result
    except Exception as exc:  # noqa: BLE001 -- gap check must never crash status
        logger.warning("produce_status: scheduler gap check failed: %s", exc)

    payload: Dict[str, Any] = {
        "status": "ok",
        "sports": entries,
        "n_sports": len(entries),
        "any_fresh": bool(any_ok),
        "honest_note": HONEST_NOTE,
        "edge_claimed": False,
    }
    if scheduler_gap is not None:
        payload["scheduler_gap"] = scheduler_gap
        payload["warning"] = scheduler_gap.get("warning")
    return JSONResponse(payload)


def _refresh_enabled() -> bool:
    return os.environ.get(REFRESH_ENABLED_ENV, "").strip().lower() in (
        "1", "true", "yes", "on")


def _refresh_one(sport: str, out_dir: Optional[str]) -> Dict[str, Any]:
    """Run produce_once for one sport, returning a result entry. Never raises."""
    try:
        path = produce.produce_once(sport, out_dir=out_dir)
    except Exception as exc:  # noqa: BLE001 -- one bad sport must not sink the rest
        logger.warning("produce_status: refresh(%s) failed: %s", sport, exc)
        return {"sport": sport, "ok": False, "error": type(exc).__name__}
    return {"sport": sport, "ok": True, "saved": str(path),
            **_status_for(sport, out_dir)}


@router.post("/api/produce/refresh")
@honest_route(extra={"refreshed": [], "n_refreshed": 0, "n_attempted": 0})
def produce_refresh(sport: Optional[str] = Query(None)) -> JSONResponse:
    """Guarded: run produce_once for the active sports (or ?sport=). Default-DENY.

    Refresh is DISABLED unless PREDICT_SERVICE_REFRESH is truthy in the env, so a
    public deployment cannot be driven to spin the producer. Returns 403 when off.
    """
    if not _refresh_enabled():
        return JSONResponse(
            {"status": "disabled",
             "reason": "producer refresh is disabled; set %s=1 to enable"
                       % REFRESH_ENABLED_ENV,
             "refreshed": [], "edge_claimed": False},
            status_code=403,
        )
    out_dir = _store_out_dir()
    sports = [sport.lower()] if sport else _active_sports()
    results = [_refresh_one(s, out_dir) for s in sports]
    n_ok = sum(1 for r in results if r.get("ok"))
    return JSONResponse({
        "status": "ok",
        "refreshed": results,
        "n_refreshed": n_ok,
        "n_attempted": len(results),
        "honest_note": HONEST_NOTE,
        "edge_claimed": False,
    })


@router.get("/api/freshness")
@honest_route(extra={"feeds": [], "n_feeds": 0, "n_fresh": 0, "n_stale": 0})
def freshness(sport: Optional[str] = Query(None)) -> JSONResponse:
    """Monotone-DOWN composite freshness rollup (STALE-never-green) for the status
    surface. The launcher -Health probe and the UI consume this: a reachable-but-
    stale feed reads STALE (ok=False), and ANY stale child degrades the rollup off
    green. Never raises; no $ field."""
    from predict_service.freshness_sidecar import feed_rollup  # noqa: PLC0415
    sports = [sport.lower()] if sport else _active_sports()
    return JSONResponse(feed_rollup(sports))


__all__ = ["router"]
