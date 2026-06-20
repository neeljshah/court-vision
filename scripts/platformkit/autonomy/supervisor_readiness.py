"""scripts.platformkit.autonomy.supervisor_readiness -- per-service readiness rows.

RB-D-1 (R-AUTO-2). A PURE composer that turns the supervised-stack inventory plus
each service's heartbeat age and circuit-breaker state into ONE honest readiness
row per service. It answers, for every manifested service: "is this service READY,
or is it stale/hung/down -- and WHY?". It NEVER reads a hung-but-alive service as
ready.

COVERAGE RAIL (the gap this closes): every service the supervisor manages must have
a readiness PREDICATE. A service that expects a heartbeat but whose heartbeat is
ABSENT or STALE reads NOT-READY (status DEGRADED / DOWN), never green-on-missing.
A service whose breaker is OPEN (the heartbeat_reaper tripped it -> a restart was
signalled) reads DOWN. A NONE-readiness service (legitimately writes no heartbeat)
is READY when alive -- but is reported with an explicit ``expects_heartbeat=False``
so an operator can see it was deliberately exempted, never silently assumed green.

PROVENANCE (every field is non-fabricable):
  * name / expects_heartbeat / fresh_sec <- supervisor.manifest ProcSpec readiness.
  * alive / hb_age / breaker / last_restart <- the live observation the supervisor
    feeds in (heartbeat_reaper verdict + supervisor proc state). This module READS
    those; it does not probe sockets or spawn anything.
  * status <- derived by the SAME monotone-DOWN rank the status_composer uses, so a
    stale feed is RED here too.

The rollup is monotone-DOWN: overall = WORST of every per-row status. A single
hung/dead service degrades the whole readiness surface; a green row never lifts it.

INVARIANTS: reads only (never data/registry/, MEMORY.md); never spawns; never flips
a flag; pure + deterministic; NEVER raises; stdlib + repo-internal; ASCII; <=300 LOC.
MEASUREMENT-ONLY: no $ field, calibration not edge, self-improve untouched.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from scripts.platformkit.autonomy.heartbeat_reaper import STALE_HUNG

# Honest status strings (shared rank with status_composer: ok<degraded<down).
OK = "ok"
DEGRADED = "degraded"
DOWN = "down"

_RANK = {OK: 0, DEGRADED: 1, DOWN: 2}
_BY_RANK = {0: OK, 1: DEGRADED, 2: DOWN}

# Heartbeat readiness kind in the manifest (a service that beats a heartbeat).
_HEARTBEAT_KIND = "heartbeat-file-fresh"
_NONE_KIND = "none"


def _degrade(current: str, candidate: str) -> str:
    """Return the WORSE of two statuses. Monotone-DOWN ONLY (never upgrades).

    An unknown label is treated as DEGRADED (conservative), never OK -- so an
    absent/garbage status can never read green.
    """
    cur = _RANK.get(current, _RANK[DEGRADED])
    cand = _RANK.get(candidate, _RANK[DEGRADED])
    return _BY_RANK[max(cur, cand)]


def _breaker_open(breaker: Any) -> bool:
    """True iff the service's circuit breaker is OPEN (reaper signalled restart)."""
    try:
        if isinstance(breaker, dict):
            return str(breaker.get("state", "")).upper() == "OPEN"
    except Exception:  # noqa: BLE001 -- a garbage breaker dict is not 'open'
        return False
    return False


def _row_status(
    *,
    expects_heartbeat: bool,
    alive: bool,
    hb_age: Optional[float],
    fresh_sec: float,
    breaker: Any,
) -> str:
    """Derive ONE honest status for a service. NEVER returns OK on missing data.

    Order of severity (worst wins):
      * breaker OPEN          -> DOWN  (the reaper tripped; a restart was signalled)
      * not alive             -> DOWN  (the proc is dead)
      * expects a heartbeat but it is ABSENT          -> DEGRADED (stale-never-green)
      * expects a heartbeat but it is STALE (> fresh)  -> DEGRADED (hung loop)
      * expects a heartbeat, FRESH                     -> OK
      * does NOT expect a heartbeat, alive             -> OK (exempt, alive)
    A negative hb_age (future-stamped / clock skew) is treated as NOT fresh so a
    constant-future stamp can never read green forever.
    """
    if _breaker_open(breaker):
        return DOWN
    if not alive:
        return DOWN
    if not expects_heartbeat:
        return OK  # NONE-readiness service: ready as soon as it is alive.
    if hb_age is None:
        return DEGRADED  # expected a beat, none present -> NOT green.
    try:
        age = float(hb_age)
    except Exception:  # noqa: BLE001 -- unparseable age is not fresh
        return DEGRADED
    fresh = 0.0 <= age <= float(fresh_sec)
    return OK if fresh else DEGRADED


def _spec_readiness(spec: Any) -> Dict[str, Any]:
    """Extract (expects_heartbeat, fresh_sec, hb_path) from a ProcSpec. Never raises."""
    rd = getattr(spec, "readiness", None)
    kind = getattr(rd, "kind", _NONE_KIND) if rd is not None else _NONE_KIND
    expects = kind == _HEARTBEAT_KIND
    fresh_sec = float(getattr(rd, "fresh_sec", 120.0) or 120.0) if rd is not None else 120.0
    hb_path = getattr(rd, "heartbeat_path", None) if rd is not None else None
    return {"expects_heartbeat": expects, "fresh_sec": fresh_sec,
            "heartbeat_path": hb_path}


def compose_readiness(
    specs: List[Any],
    observations: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build the per-service readiness surface + a monotone-DOWN overall. Never raises.

    Parameters
    ----------
    specs : list of supervisor ProcSpec (the manifest inventory).
    observations : optional {name -> {"alive", "hb_age", "breaker", "last_restart"}}.
        Each value is the live observation the supervisor feeds in (heartbeat_reaper
        verdict + proc state). A service ABSENT from observations is treated as
        UNOBSERVED: alive=False, hb_age=None -> it cannot read READY (a missing
        observation is never assumed green).

    Returns
    -------
    {"overall": status, "services": [row, ...], "honest_note": str} where each row is
    {name, expects_heartbeat, alive, hb_age, fresh_sec, breaker, last_restart, status}.
    """
    obs = observations or {}
    rows: List[Dict[str, Any]] = []
    overall = OK
    try:
        spec_list = list(specs or [])
    except Exception:  # noqa: BLE001 -- a bad specs arg degrades, never crashes
        spec_list = []

    for spec in spec_list:
        try:
            name = str(getattr(spec, "name", "") or "")
            rd = _spec_readiness(spec)
            o = obs.get(name) or {}
            # A service with NO observation cannot be assumed alive -> not green.
            observed = name in obs
            alive = bool(o.get("alive", False)) if observed else False
            hb_age = o.get("hb_age", None)
            breaker = o.get("breaker", {})
            last_restart = o.get("last_restart", None)
            status = _row_status(
                expects_heartbeat=rd["expects_heartbeat"],
                alive=alive,
                hb_age=hb_age,
                fresh_sec=rd["fresh_sec"],
                breaker=breaker,
            )
            # If the service expects a heartbeat and the reaper status string says
            # STALE_HUNG, surface that hint (the row is already >= DEGRADED).
            reaper_status = o.get("reaper_status")
            hung = reaper_status == STALE_HUNG
            row = {
                "name": name,
                "expects_heartbeat": rd["expects_heartbeat"],
                "alive": alive,
                "observed": observed,
                "hb_age": hb_age,
                "fresh_sec": rd["fresh_sec"],
                "breaker": breaker if isinstance(breaker, dict) else {},
                "last_restart": last_restart,
                "stale_hung": bool(hung),
                "status": status,
            }
            rows.append(row)
            overall = _degrade(overall, status)
        except Exception:  # noqa: BLE001 -- one bad spec degrades, never crashes
            overall = _degrade(overall, DEGRADED)
            rows.append({"name": str(getattr(spec, "name", "?")),
                         "status": DEGRADED, "observed": False,
                         "note": "row composition raised -> degraded"})

    if not rows:
        # No services to assess -> we cannot assert readiness. Honest DEGRADED,
        # never an empty-green surface.
        overall = _degrade(overall, DEGRADED)

    return {
        "overall": overall,
        "services": rows,
        "honest_note": (
            "MEASUREMENT-ONLY readiness surface; calibration not edge, no $ field. "
            "A hung/dead/unobserved service reads DEGRADED/DOWN, never READY; a "
            "stale heartbeat is RED, never green."
        ),
    }


__all__ = ["OK", "DEGRADED", "DOWN", "compose_readiness"]
