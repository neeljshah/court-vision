"""scripts.platformkit.autonomy.loop_observer -- A6 self-monitor for the loops.

The status_composer answers "what is the whole system's state". This observer
answers the SHARPER per-loop question the A6 self-monitor exists for: is each
autonomous loop both BREATHING (fresh heartbeat) AND making PROGRESS (its work
cursor advanced) -- or is it hung, stalled, or honestly idle? It is the bridge
between the raw progress_tripwire primitive and the canonical status surface.

It reads ONLY non-fabricable signals:
  * heartbeat_at -- the loop service's last_seen (from the composed services[],
                    which come from ops.liveness heartbeat files).
  * cursor_at    -- the loop's high-water write time. The self-improve daemon
                    advances its checkpoint cursor (high_water + seen_ids) only
                    when it actually folds a settled game, so a frozen cursor is a
                    real stall, not a display artifact.
  * idle         -- the daemon's OWN last status row says "no_new_games" -> there
                    is genuinely nothing to advance, so the observer reports an
                    honest IDLE instead of a fabricated STALLED_CURSOR.

The classification is delegated VERBATIM to progress_tripwire.classify (liveness
!= progress); this module only assembles its inputs from the canonical status and
maps the verdict onto the composer's ok/degraded/down scale -- and it can only
DEGRADE. A fresh heartbeat over a frozen cursor is DEGRADED, never green.

INVARIANTS: additive + reversible + flag-OFF; reads only; pure + injectable
clock/status; NEVER raises; stdlib-only; ASCII-only; <=300 LOC.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.autonomy import progress_tripwire as _trip
from scripts.platformkit.autonomy import status_composer as _composer

OK = _composer.OK
DEGRADED = _composer.DEGRADED
DOWN = _composer.DOWN

# Map a progress_tripwire status onto the composer severity scale. NONE of these
# is ever "green by accident": a stalled or hung loop is at least DEGRADED.
_TRIP_TO_SEVERITY: Dict[str, str] = {
    _trip.HEALTHY: OK,
    _trip.IDLE: OK,             # honest idle is fine -- but carries an explicit reason
    _trip.STALLED_CURSOR: DEGRADED,
    _trip.HEARTBEAT_STALE: DOWN,
    _trip.UNKNOWN: DEGRADED,    # cannot prove progress -> never silently ok
}

# Daemon status strings that mean "genuinely no work to advance" (honest idle).
_IDLE_STATUSES = {"no_new_games"}


def _iso_to_epoch(iso: Optional[str]) -> Optional[float]:
    """Parse an ISO-8601 'YYYY-mm-ddTHH:MM:SSZ' to epoch seconds. None on failure."""
    if not iso or not isinstance(iso, str):
        return None
    try:
        from datetime import datetime, timezone
        s = iso.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:  # noqa: BLE001
        return None


def _loop_service_last_seen(
    services: List[Dict[str, Any]],
    loop_services: tuple,
) -> Optional[float]:
    """Most-recent last_seen epoch across the loop services. None if none present.

    Provenance: services[].last_seen is the composer's pass-through of the loop's
    heartbeat file age, so this is the real heartbeat clock -- not invented.
    """
    best: Optional[float] = None
    for svc in services:
        if svc.get("name") not in loop_services:
            continue
        ep = _iso_to_epoch(svc.get("last_seen"))
        if ep is None:
            continue
        best = ep if best is None else max(best, ep)
    return best


def observe(
    *,
    now: Optional[float] = None,
    status: Optional[Dict[str, Any]] = None,
    compose_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    hb_fresh_sec: float = 300.0,
    stall_sec: float = 1800.0,
    loop_services: tuple = _composer._LOOP_SERVICES,  # noqa: SLF001
) -> Dict[str, Any]:
    """Observe each loop's liveness-vs-progress and return ONE verdict. NEVER raises.

    *status* may be passed directly (offline test); otherwise it is composed via
    *compose_fn* (default: the real status_composer.compose). Returns:

      {"status": ok|degraded|down,
       "loop_status": <progress_tripwire status>,
       "heartbeat_age": float|None, "cursor_age": float|None,
       "idle": bool, "idle_reason": str|None, "detail": {...}}

    The severity can only DEGRADE relative to the composer (a hung loop is DOWN,
    a stalled cursor DEGRADED, an honest idle stays OK but names the reason).
    """
    try:
        t = float(now) if now is not None else time.time()
        if status is None:
            cf = compose_fn or _composer.compose
            status = cf(now=t)
        status = status if isinstance(status, dict) else {}

        services = status.get("services") or []
        loop = status.get("loop") or {}
        last_status = (loop.get("last_status") or {}) if isinstance(loop, dict) else {}
        daemon_status = str(last_status.get("status") or "")

        heartbeat_at = _loop_service_last_seen(services, loop_services)

        # Cursor advance time: the high_water mark itself is an opaque key, so we
        # use the daemon's last status timestamp as the cursor clock ONLY when the
        # last cycle actually did work (cycle_done) -- otherwise the cursor is
        # whatever the heartbeat says minus an unknown, so we report UNKNOWN rather
        # than fabricate advancement. A genuine "no_new_games" is honest IDLE.
        idle = daemon_status in _IDLE_STATUSES
        cursor_at: Optional[float] = None
        if daemon_status in ("cycle_done",) and isinstance(last_status.get("ts"), (int, float)):
            cursor_at = float(last_status["ts"])

        verdict = _trip.classify(
            heartbeat_at=heartbeat_at,
            cursor_at=cursor_at,
            now=t,
            hb_fresh_sec=hb_fresh_sec,
            stall_sec=stall_sec,
            idle=idle,
        )

        loop_status = verdict["status"]
        severity = _TRIP_TO_SEVERITY.get(loop_status, DEGRADED)

        idle_reason: Optional[str] = None
        if loop_status == _trip.IDLE:
            idle_reason = "idle: no newly-settled games to fold (waiting on slate)"
        elif loop_status == _trip.STALLED_CURSOR:
            idle_reason = "degraded: fresh heartbeat but work cursor frozen"
        elif loop_status == _trip.HEARTBEAT_STALE:
            idle_reason = "down: loop heartbeat stale/dead (not breathing)"
        elif loop_status == _trip.UNKNOWN:
            idle_reason = "degraded: cannot prove the loop advanced (no cursor clock)"

        return {
            "status": severity,
            "loop_status": loop_status,
            "heartbeat_age": verdict.get("heartbeat_age"),
            "cursor_age": verdict.get("cursor_age"),
            "idle": bool(idle),
            "idle_reason": idle_reason,
            "detail": {
                "daemon_status": daemon_status or None,
                "loop_services": list(loop_services),
                "tripwire": verdict.get("detail"),
            },
            "honest_note": (
                "liveness != progress; a fresh heartbeat over a frozen cursor is "
                "DEGRADED, a dead heartbeat is DOWN -- never green."
            ),
        }
    except Exception:  # noqa: BLE001 -- the self-monitor must never crash a loop.
        return {
            "status": DEGRADED,
            "loop_status": _trip.UNKNOWN,
            "heartbeat_age": None,
            "cursor_age": None,
            "idle": False,
            "idle_reason": "degraded: observer raised (defensive)",
            "detail": {"error": "observe_raised"},
        }


__all__ = ["OK", "DEGRADED", "DOWN", "observe"]
