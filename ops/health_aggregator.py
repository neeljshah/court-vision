"""ops.health_aggregator -- ONE status.json the UI renders + the doctor reads.

Aggregates liveness + freshness_guard + circuit_breaker into a single document.
The service inventory comes from ops.service_registry (derived from
supervisor.manifest) so this never drifts from the real supervised stack.

OVERALL ROLLUP: "ok" all-live-fresh | "degraded" non-critical-down/stale
               | "down" critical-service-down.

STALE-NEVER-GREEN invariant: a feed past its SLA (or a heartbeat past its
declared ReadinessSpec fresh_sec while the liveness snapshot still says live)
can NEVER roll up to "ok". Freshness is a FIRST-CLASS gate.

Public API: aggregate(), write_status(), aggregate_and_write() -- see each.
Shape: {generated_at, overall, services[{name,critical,live,fresh,breaker,
        last_seen,age_sec,fresh_sec,port,reason}], notes}.

INVARIANTS: <=300 LOC; ASCII only; stdlib only; never raises; injectable clock;
never writes data/registry/. Build only under ops/.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ops import liveness as _liveness
from ops import service_registry as _registry
from ops.freshness_guard import guard_status

OK = "ok"
DEGRADED = "degraded"
DOWN = "down"


def _find_repo_root() -> Path:
    candidate = Path(__file__).resolve()
    for _ in range(8):
        candidate = candidate.parent
        if (candidate / "CLAUDE.md").exists():
            return candidate
    return Path(__file__).resolve().parents[1]


_REPO_ROOT = _find_repo_root()
_DEFAULT_OUT = _REPO_ROOT / "data" / "frontend" / "ops" / "status.json"

# The in-game loop writes n_live (live-game count) to its frontend heartbeat;
# n_live==0 means the system is honestly idle (e.g. NBA offseason), not broken.
_INGAME_COMPONENT = "ingame_live_loop"


def _ingame_n_live() -> Optional[int]:
    """Read n_live from the in-game frontend heartbeat. Never raises.

    None when missing / unreadable / lacking the field (a crashed loop is not
    "idle", so it makes no idle claim).
    """
    try:
        hb_path = _liveness._FRONTEND_HEARTBEATS.get(_INGAME_COMPONENT)
        if hb_path is not None and hb_path.exists():
            data = json.loads(hb_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "n_live" in data:
                return int(data["n_live"])
    except Exception:  # noqa: BLE001 -- an unreadable heartbeat makes no claim
        pass
    return None


def _utc_iso(ts: Optional[float] = None) -> str:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc) if ts is not None else datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _last_seen(now: Optional[float], age_sec: Optional[float]) -> Optional[str]:
    """ISO timestamp of the last heartbeat, derived from now - age."""
    if now is None or age_sec is None:
        return None
    try:
        return _utc_iso(float(now) - float(age_sec))
    except Exception:  # noqa: BLE001
        return None


def _service_row(
    desc,
    *,
    snap: Dict[str, Any],
    now: Optional[float],
    breakers: Dict[str, Any],
) -> Dict[str, Any]:
    """Build one services[] row for *desc*. Never raises."""
    name = desc.name
    comp = desc.liveness_component
    live: Optional[bool] = None
    age_sec: Optional[float] = None
    reason: Optional[str] = None

    if comp is not None:
        info = snap.get(comp, {}) if isinstance(snap, dict) else {}
        if isinstance(info, dict) and "live" in info:
            live = bool(info.get("live"))
            age_sec = info.get("age_sec")
            if not live:
                reason = "heartbeat absent" if age_sec is None else "heartbeat stale"
    # Port-probed servers (no heartbeat) keep live=None; the supervisor probe
    # governs them at boot, so we never mark them DOWN on a missing heartbeat.

    # Honest-idle: a present-but-quiet in-game beat (age_sec not None -> loop
    # alive; n_live==0) says WHY it is quiet. A crashed loop (age_sec None)
    # keeps its "heartbeat absent" reason and stays DOWN.
    if comp == _INGAME_COMPONENT and age_sec is not None and _ingame_n_live() == 0:
        reason = "idle: no live games"

    fresh: Optional[str] = None
    if desc.freshness_source is not None and age_sec is not None and now is not None:
        try:
            captured = _utc_iso(float(now) - float(age_sec))
            fresh = guard_status(
                desc.freshness_source, captured,
                now=datetime.fromtimestamp(float(now), tz=timezone.utc),
            ).get("status")
        except Exception:  # noqa: BLE001
            fresh = None

    breaker_state: Optional[str] = None
    cb = breakers.get(name) if isinstance(breakers, dict) else None
    if cb is not None:
        try:
            breaker_state = cb.status().get("state") if hasattr(cb, "status") else str(cb)
        except Exception:  # noqa: BLE001
            breaker_state = None

    return {
        "name": name,
        "critical": bool(desc.critical),
        "live": live,
        "fresh": fresh,
        "breaker": breaker_state,
        "last_seen": _last_seen(now, age_sec),
        "age_sec": round(age_sec, 1) if isinstance(age_sec, (int, float)) else None,
        "fresh_sec": desc.fresh_sec,
        "port": desc.port,
        "reason": reason,
    }


def _row_severity(row: Dict[str, Any]) -> str:
    """Per-service severity: OK / DEGRADED / DOWN.

    DOWN     -- live False, breaker OPEN, or fresh=="down".
    DEGRADED -- fresh=="stale" OR (live==True and age_sec >= fresh_sec).
                The second arm closes the stale-never-green gap: a daemon whose
                liveness snapshot still reads live (wider internal threshold) but
                whose heartbeat age has passed the manifest ReadinessSpec fresh_sec
                must score DEGRADED, not OK. Degrade-only; never invents green.
    OK       -- otherwise.
    """
    if row.get("live") is False:
        return DOWN
    if row.get("breaker") == "OPEN":
        return DOWN
    fresh = row.get("fresh")
    if fresh == "down":
        return DOWN
    if fresh == "stale":
        return DEGRADED
    # Stale-never-green: live==True but heartbeat age has passed the declared
    # readiness window (fresh_sec from the manifest ReadinessSpec).
    age_sec = row.get("age_sec")
    fresh_sec = row.get("fresh_sec")
    if (
        row.get("live") is True
        and age_sec is not None
        and fresh_sec is not None
        and float(age_sec) >= float(fresh_sec)
    ):
        return DEGRADED
    return OK


def _reason_for(row: Dict[str, Any], severity: str) -> str:
    """A short human reason for a non-ok row (reused in notes + doctor)."""
    if row.get("reason"):
        return str(row.get("reason"))
    if row.get("breaker") == "OPEN":
        return "circuit breaker OPEN"
    fresh = row.get("fresh")
    if fresh in ("stale", "down"):
        return "data source %s (past SLA)" % fresh
    # Stale heartbeat: live but past declared fresh_sec window.
    age_sec = row.get("age_sec")
    fresh_sec = row.get("fresh_sec")
    if (
        row.get("live") is True
        and age_sec is not None
        and fresh_sec is not None
        and float(age_sec) >= float(fresh_sec)
    ):
        return "heartbeat stale (age %.0fs >= fresh_sec %.0fs)" % (age_sec, fresh_sec)
    return "down" if severity == DOWN else "degraded"


def aggregate(
    *,
    now: Optional[float] = None,
    breakers: Optional[Dict[str, Any]] = None,
    profile: str = "default",
    registry_path: Optional[Union[str, Path]] = None,
    hb_dir: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Aggregate liveness + freshness + breaker state into one status doc.

    *breakers* maps a service name to a CircuitBreaker (or its state str).
    Never raises -- any failure degrades to a conservative document.
    """
    breakers = breakers or {}
    try:
        snap = _liveness.liveness_snapshot(
            now=now, _registry_path=registry_path, _hb_dir=hb_dir)
    except Exception:  # noqa: BLE001
        snap = {}

    descriptors = _registry.service_descriptors(profile)
    rows: List[Dict[str, Any]] = []
    notes: List[str] = []
    for desc in descriptors:
        try:
            rows.append(_service_row(desc, snap=snap, now=now, breakers=breakers))
        except Exception:  # noqa: BLE001
            continue

    overall = OK
    for row in rows:
        sev = _row_severity(row)
        if sev == OK:
            continue
        reason = _reason_for(row, sev)
        # Surface a stale/down data-feed reason on the row so the doctor names it.
        if not row.get("reason") and row.get("fresh") in ("stale", "down"):
            row["reason"] = reason
        if sev == DOWN:
            label = "critical service" if row.get("critical") else "service"
            notes.append("%s %s is down (%s)" % (label, row.get("name"), reason))
            if row.get("critical"):
                overall = DOWN
            elif overall != DOWN:
                overall = DEGRADED
        else:  # DEGRADED -- e.g. a data feed past its SLA (stale)
            notes.append("service %s is degraded (%s)" % (row.get("name"), reason))
            if overall == OK:
                overall = DEGRADED

    if not descriptors:
        notes.append("no services in manifest (profile=%s)" % profile)

    return {
        "generated_at": _utc_iso(now),
        "overall": overall,
        "services": rows,
        "notes": notes,
    }


def write_status(
    status: Dict[str, Any],
    *,
    out_path: Optional[Union[str, Path]] = None,
) -> Path:
    """Atomically write *status* to data/frontend/ops/status.json. Never raises."""
    dest = Path(out_path) if out_path is not None else _DEFAULT_OUT
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        tmp.write_text(json.dumps(status, indent=2), encoding="ascii")
        os.replace(str(tmp), str(dest))
    except Exception:  # noqa: BLE001 -- a write failure must not crash callers
        pass
    return dest


def aggregate_and_write(
    *,
    now: Optional[float] = None,
    breakers: Optional[Dict[str, Any]] = None,
    profile: str = "default",
    out_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Aggregate then persist; returns the status doc."""
    status = aggregate(now=now, breakers=breakers, profile=profile)
    write_status(status, out_path=out_path)
    return status


__all__ = [
    "OK", "DEGRADED", "DOWN",
    "aggregate", "write_status", "aggregate_and_write",
]
