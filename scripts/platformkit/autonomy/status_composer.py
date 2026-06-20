"""scripts.platformkit.autonomy.status_composer -- the ONE canonical autonomy status.

A6 self-monitor. This is the SINGLE document the UI panels (OpsPanel / ParityGrid /
RatchetPanel) and an operator runbook read to answer "is the autonomous system
honestly working, and if it is idle, WHY?". It composes -- never recomputes --
every observability primitive into one envelope so the UI never has to stitch four
half-overlapping JSONs and so no surface can read a dead feed as green.

WHAT IT COVERS (every value is NON-FABRICABLE; provenance per field below):
  * services[]   <- ops.health_aggregator.aggregate() VERBATIM (ops.liveness heartbeat
                    files + ops.freshness_guard manifest SLA). Per-row severity is
                    health_aggregator._row_severity; composer may only DEGRADE, never up.
  * loop         <- self-improve checkpoint data/cache/improve/checkpoint.json (cycle,
                    last_decision) + daemon tail data/cache/improve/status.jsonl. A loop
                    whose heartbeat is stale (per services[]) reads DEGRADED, not running.
  * ratchet      <- ratchet FSM checkpoint data/frontend/calib/_ratchet_state.json (state
                    + ships/rollbacks/downgrades history). Pure read.
  * high_water   <- self-improve checkpoint cursors (per-sport last settled game folded).
                    Cannot be fabricated: it is the cursor the daemon actually advanced.
  * idle_reason  <- EXPLICIT honest "idle because X" derived from the daemon's OWN last
                    status row (no_new_games / no_candidate). Never a green blank.

CRITICAL RAIL -- a stale/dead feed can NEVER roll up to green. overall = WORST of
health's own overall AND every per-row severity AND loop liveness. The composer is
monotone-DOWN only (`_degrade` can push ok->degraded->down but never back). A missing
source yields DEGRADED with an explicit reason, never absent-as-ok.

INVARIANTS: additive + reversible + flag-OFF; reads only (never data/registry/,
MEMORY.md, never flips a flag); pure + injectable clock; NEVER raises; stdlib + ASCII;
<=300 LOC.
"""
from __future__ import annotations

import json
import pathlib
import time
from typing import Any, Dict, List, Optional

from ops import health_aggregator as _health

OK = "ok"
DEGRADED = "degraded"
DOWN = "down"

# Severity rank: higher == worse. Used to prove the composer only ever DEGRADES.
_RANK = {OK: 0, DEGRADED: 1, DOWN: 2}
_BY_RANK = {0: OK, 1: DEGRADED, 2: DOWN}

_REPO = pathlib.Path(__file__).resolve().parents[3]
_IMPROVE_CKPT = _REPO / "data" / "cache" / "improve" / "checkpoint.json"
_IMPROVE_STATUS = _REPO / "data" / "cache" / "improve" / "status.jsonl"
_RATCHET_CKPT = _REPO / "data" / "frontend" / "calib" / "_ratchet_state.json"

# The supervised loop services whose liveness gates the loop block. These map to
# ops.service_registry liveness names; if any is not OK in services[], the loop
# block is degraded (a stale loop heartbeat must never read "running").
_LOOP_SERVICES = ("paper_loop", "ingame_live_loop", "predict_service")


def _degrade(current: str, candidate: str) -> str:
    """Return the WORSE of two severities. The composer is monotone-DOWN ONLY.

    This is the single chokepoint that guarantees the rail: a composer can push
    ok->degraded->down but can NEVER turn a worse severity back to a better one.
    Any unknown label is treated as DEGRADED (conservative), never OK.
    """
    cur = _RANK.get(current, _RANK[DEGRADED])
    cand = _RANK.get(candidate, _RANK[DEGRADED])
    return _BY_RANK[max(cur, cand)]


def _read_json(path: pathlib.Path) -> Optional[Dict[str, Any]]:
    """Best-effort JSON read; missing/torn/garbage -> None (NEVER raises)."""
    try:
        if not path.exists():
            return None
        raw = path.read_text(encoding="ascii")
        data = json.loads(raw) if raw.strip() else None
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _read_jsonl_tail(path: pathlib.Path, n: int = 1) -> List[Dict[str, Any]]:
    """Return the last *n* JSON objects of a .jsonl file (NEVER raises)."""
    try:
        if not path.exists():
            return []
        lines = path.read_text(encoding="ascii").splitlines()
        out: List[Dict[str, Any]] = []
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(obj, dict):
                out.append(obj)
            if len(out) >= n:
                break
        return out
    except Exception:  # noqa: BLE001
        return []


def _services_block(
    health_doc: Dict[str, Any],
) -> Dict[str, Any]:
    """Per-service rows + the WORST per-row severity. Inherits _row_severity.

    Provenance: ops.health_aggregator.aggregate() already merged liveness +
    freshness + breaker. We re-derive each row's severity with the SAME function
    the aggregator uses (_row_severity) so a stale feed is RED here too, then take
    the worst. We never recompute liveness/freshness -- only read the verdict.
    """
    rows = health_doc.get("services") or []
    worst = OK
    enriched: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        sev = _health._row_severity(row)  # noqa: SLF001 -- the documented inherit
        worst = _degrade(worst, sev)
        item = dict(row)
        item["severity"] = sev
        enriched.append(item)
    return {"services": enriched, "worst_row_severity": worst}


def _loop_block(services: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Loop cycle count + last verdict + current candidate + liveness severity.

    Provenance: cycle/last_decision <- checkpoint.json; last_status <- status.jsonl
    tail (the daemon's own escalation log). A loop SERVICE not OK in services[]
    forces this block off "running" -- a stale loop heartbeat never reads healthy.
    """
    ckpt = _read_json(_IMPROVE_CKPT) or {}
    cursors = ckpt.get("cursors") if isinstance(ckpt.get("cursors"), dict) else {}
    tail = _read_jsonl_tail(_IMPROVE_STATUS, n=1)
    last_status = tail[0] if tail else None

    # Liveness severity from the loop services (worst of the three).
    loop_sev = OK
    missing = True
    for svc in services:
        if svc.get("name") in _LOOP_SERVICES:
            missing = False
            loop_sev = _degrade(loop_sev, _health._row_severity(svc))  # noqa: SLF001
    if missing:
        # No loop service present in the registry snapshot -> cannot assert the
        # loop is alive. DEGRADED (absent != ok), with an explicit reason.
        loop_sev = _degrade(loop_sev, DEGRADED)

    last_decision = None
    for cur in (cursors or {}).values():
        if isinstance(cur, dict) and cur.get("last_decision"):
            last_decision = str(cur.get("last_decision"))
            break
    # Most recent escalation row is the live "candidate" view (None if no log yet).
    cand = (last_status.get("decision") or last_status.get("status")) \
        if (last_status and last_status.get("status")) else None

    return {
        "cycle": int(ckpt.get("cycle", 0) or 0),
        "last_decision": last_decision,
        "current_candidate": cand,
        "last_status": last_status,
        "liveness_severity": loop_sev,
        "liveness_missing": bool(missing),
    }


def _ratchet_block() -> Dict[str, Any]:
    """Ratchet FSM state + ships/rollbacks/downgrades history. Pure read.

    Provenance: data/frontend/calib/_ratchet_state.json -- written ONLY by the
    real improve.ratchet_state FSM (atomic). A missing file -> an honest IDLE
    shell with empty history, never a fabricated SHIP.
    """
    st = _read_json(_RATCHET_CKPT) or {}
    history = st.get("history") if isinstance(st.get("history"), list) else []
    ships = [h for h in history if isinstance(h, dict) and h.get("decision") == "SHIP"]
    rollbacks = [
        h for h in history
        if isinstance(h, dict) and h.get("rolled_back_to") is not None
    ]
    return {
        "state": str(st.get("state", "IDLE")),
        "last_decision": st.get("last_decision"),
        "shipped_version": st.get("shipped_version"),
        "n_ships": len(ships),
        "n_rollbacks": len(rollbacks),
        "history": history[-20:],
        "present": bool(st),
    }


def _high_water_block() -> Dict[str, Any]:
    """Per-sport data high-water marks (last settled game folded). Pure read.

    Provenance: self-improve checkpoint cursors -- the high_water key the daemon
    ACTUALLY advanced when it folded a settled game. Nothing else writes it.
    """
    ckpt = _read_json(_IMPROVE_CKPT) or {}
    cursors = ckpt.get("cursors") if isinstance(ckpt.get("cursors"), dict) else {}
    out: Dict[str, Any] = {}
    for sport, cur in (cursors or {}).items():
        if not isinstance(cur, dict):
            continue
        out[str(sport)] = {
            "high_water": cur.get("high_water"),
            "last_decision": cur.get("last_decision"),
            "n_seen": len(cur.get("seen_ids") or []),
        }
    return out


def _idle_reason(loop: Dict[str, Any], overall: str) -> Optional[str]:
    """Explicit honest 'idle because X', or None when actively shipping/working.

    Only emitted when the system is breathing (overall != down) but not shipping.
    Derives the reason from the daemon's OWN last status row (no invention): e.g.
    'no_new_games' / 'no_candidate'. Never a blank that could read as healthy.
    """
    if overall == DOWN:
        return None  # not idle -- something is down; the severity already says so.
    status = str((loop.get("last_status") or {}).get("status") or "")
    mapping = {  # cycle_done is WORK, not idle -> deliberately absent (returns None)
        "no_new_games": "idle: no newly-settled games to fold (waiting on slate)",
        "no_candidate": "idle: settled games folded but no candidate met the gate",
        "source_error": "degraded: a settled-games source raised (isolated)",
        "recalibrate_error": "degraded: recalibrate step raised (isolated)",
        "gate_error": "degraded: the gate raised (isolated, candidate rejected)",
    }
    if status in mapping:
        return mapping[status]
    if not status:
        return "idle: no loop status recorded yet (cold start)"
    return None


def compose(
    *,
    now: Optional[float] = None,
    profile: str = "default",
    breakers: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the ONE canonical autonomy status document. NEVER raises.

    The overall severity is the WORST of: health_aggregator's own overall, the
    worst per-service row severity, and the loop liveness severity. The composer
    can only DEGRADE -- a green feed never overrides a stale/down one.
    """
    t = float(now) if now is not None else time.time()
    try:
        health_doc = _health.aggregate(now=t, breakers=breakers, profile=profile)
    except Exception:  # noqa: BLE001 -- a health failure degrades, never crashes.
        health_doc = {"overall": DEGRADED, "services": [],
                      "notes": ["health_aggregator.aggregate raised"]}

    svc = _services_block(health_doc)
    loop = _loop_block(svc["services"])
    ratchet = _ratchet_block()
    high_water = _high_water_block()

    # Monotone-DOWN rollup: start from health's own overall, then DEGRADE by every
    # per-row severity and the loop liveness. Never upgrades.
    overall = str(health_doc.get("overall", DEGRADED))
    if overall not in _RANK:
        overall = DEGRADED
    overall = _degrade(overall, svc["worst_row_severity"])
    overall = _degrade(overall, loop["liveness_severity"])

    idle_reason = _idle_reason(loop, overall)

    notes = list(health_doc.get("notes") or [])
    if loop.get("liveness_missing"):
        notes.append("loop liveness service absent -> degraded (not assumed ok)")
    if idle_reason:
        notes.append(idle_reason)

    return {
        "generated_at": health_doc.get("generated_at"),
        "overall": overall,
        "services": svc["services"],
        "loop": loop,
        "ratchet": ratchet,
        "high_water": high_water,
        "idle_reason": idle_reason,
        "notes": notes,
        "honest_note": (
            "calibration, not edge; no $ field. A stale/dead feed is RED, never "
            "green; an idle system says WHY it is idle."
        ),
    }


__all__ = ["OK", "DEGRADED", "DOWN", "compose"]
