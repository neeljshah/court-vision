"""scripts.platformkit.autonomy.status_composer_m5fix -- IOP-07 m5 self-reporting fix.

The autonomy monitor (m5) publishes autonomy_status.json every ~60s and beats
data/cache/daemon_heartbeats/m5_autonomy_monitor.txt so the supervisor can see
the monitor is itself alive. The bug: when the monitor dies the services[] row it
last wrote may still read ok (the heartbeat file exists but is stale). This module
adds a single composable patch:

    patch_m5_row(doc, now=None) -> dict

It reads the m5 heartbeat mtime DIRECTLY, computes age, and DEGRADES the
``m5_autonomy_monitor`` row in services[] (and overall) to match the honest age.
The patch is MONOTONE-DOWN: it can push ok->degraded->down but NEVER upgrades a
worse row back to ok. A missing heartbeat file yields DEGRADED (absent != ok).

INVARIANTS:
  * Never raises (all paths return a valid dict, no exceptions leak out).
  * No $ field (calibration not edge; CLV not ROI).
  * DEGRADE-ONLY: _degrade() is the single chokepoint.
  * Pure injectable clock (``now`` kwarg) for deterministic offline tests.
  * Reads only m5_autonomy_monitor.txt; never data/registry/ or flags.
  * Stdlib + ASCII; <=300 LOC.

Acceptance (see test_status_composer_m5fix.py):
  * stale m5 heartbeat -> services[] row severity DEGRADED (never ok), overall DEGRADED.
  * very stale (absent) m5 heartbeat -> severity DEGRADED (absent != ok).
  * fresh m5 heartbeat -> severity ok, overall ok (monotone-down respects upstream).
  * monotone-down: age 0 -> ok, age fresh+1 -> degraded, age 2x -> degraded (never green again).
  * no $ or edge field in the returned document.
"""
from __future__ import annotations

import pathlib
import time
from typing import Any, Dict, List, Optional

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

OK = "ok"
DEGRADED = "degraded"
DOWN = "down"

_RANK: Dict[str, int] = {OK: 0, DEGRADED: 1, DOWN: 2}
_BY_RANK: Dict[int, str] = {0: OK, 1: DEGRADED, 2: DOWN}

# The m5 heartbeat component name (must match autonomy_monitor_runner.HEARTBEAT_COMPONENT
# and the filename stem in stack_specs._AUTONOMY_MONITOR_HB).
M5_COMPONENT = "m5_autonomy_monitor"

# fresh_sec mirrors stack_specs ReadinessSpec fresh_sec=300.0 for m5.  A heartbeat
# older than this is DEGRADED (the monitor may have hung or been killed).
M5_FRESH_SEC: float = 300.0

_REPO = pathlib.Path(__file__).resolve().parents[3]
_M5_HB_PATH = _REPO / "data" / "cache" / "daemon_heartbeats" / "m5_autonomy_monitor.txt"


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #

def _degrade(current: str, candidate: str) -> str:
    """Return the WORSE of two severities. Monotone-DOWN only (never upgrades).

    Unknown labels are treated conservatively as DEGRADED, never OK.
    """
    cur = _RANK.get(current, _RANK[DEGRADED])
    cand = _RANK.get(candidate, _RANK[DEGRADED])
    return _BY_RANK[max(cur, cand)]


def _m5_age_sec(hb_path: pathlib.Path, now: float) -> Optional[float]:
    """Return age in seconds of the m5 heartbeat file, or None if unreadable.

    Reads the ISO timestamp embedded in the file (same convention as
    ops.liveness._age_from_text_hb).  Falls back to mtime if the text cannot
    be parsed.  Never raises.
    """
    try:
        if not hb_path.exists():
            return None
        raw = hb_path.read_text(encoding="ascii", errors="replace").strip()
        if raw:
            # Try to parse embedded ISO-8601 UTC timestamp (e.g. "2026-06-20T05:49:37Z").
            try:
                from datetime import datetime, timezone
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return now - dt.timestamp()
            except Exception:  # noqa: BLE001
                pass
            # Try plain numeric epoch.
            try:
                return now - float(raw)
            except Exception:  # noqa: BLE001
                pass
        # Fall back to mtime.
        import os
        mtime = os.path.getmtime(str(hb_path))
        return now - mtime
    except Exception:  # noqa: BLE001
        return None


def _m5_row_severity(age_sec: Optional[float], fresh_sec: float) -> str:
    """Convert a heartbeat age to a severity verdict.

    None (absent/unreadable) -> DEGRADED (absent-as-ok is the core bug we fix).
    age <= 0 (future stamp / clock skew) -> DEGRADED (untrusted, not ok).
    age > fresh_sec -> DEGRADED (stale monitor; may have crashed).
    age in (0, fresh_sec] -> OK.

    DEGRADED (not DOWN) because a stale monitor is a measurement-gap; the
    supervised stack itself may still be running.  Only the heartbeat is missing.
    """
    if age_sec is None:
        return DEGRADED
    if age_sec <= 0:
        return DEGRADED  # future stamp (clock skew) -- not trusted as fresh
    if age_sec > fresh_sec:
        return DEGRADED
    return OK


def _build_m5_services_row(age_sec: Optional[float], fresh_sec: float) -> Dict[str, Any]:
    """Build a services[] row dict for m5_autonomy_monitor from its heartbeat age."""
    sev = _m5_row_severity(age_sec, fresh_sec)
    reason: Optional[str]
    if age_sec is None:
        reason = "m5 heartbeat absent (monitor may be dead)"
    elif age_sec <= 0:
        reason = "m5 heartbeat timestamp in future (clock skew)"
    elif age_sec > fresh_sec:
        reason = "m5 heartbeat stale (age %.0fs > fresh_sec %.0fs)" % (age_sec, fresh_sec)
    else:
        reason = None
    return {
        "name": M5_COMPONENT,
        "severity": sev,
        "age_sec": round(age_sec, 1) if isinstance(age_sec, float) else None,
        "fresh_sec": fresh_sec,
        "reason": reason,
        "source": "m5fix_direct_hb_read",
    }


def _patch_services_row(
    services: List[Dict[str, Any]],
    m5_row: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Degrade the m5_autonomy_monitor row in services[], appending if absent.

    MONOTONE-DOWN: for an existing m5 row, we only apply _degrade (never upgrade
    an already-worse severity back to ok).  A missing row is appended outright so
    the monitor is ALWAYS visible (absent-as-ok is the core invariant violation).
    """
    patched: List[Dict[str, Any]] = []
    found = False
    for row in services:
        if not isinstance(row, dict):
            patched.append(row)
            continue
        if row.get("name") == M5_COMPONENT:
            found = True
            updated = dict(row)
            old_sev = str(updated.get("severity", OK))
            new_sev = _degrade(old_sev, m5_row["severity"])
            updated["severity"] = new_sev
            # Propagate reason only when we are the one degrading.
            if new_sev != old_sev and m5_row.get("reason"):
                updated["reason"] = m5_row["reason"]
            updated["age_sec"] = m5_row["age_sec"]
            updated["m5fix_applied"] = True
            patched.append(updated)
        else:
            patched.append(row)
    if not found:
        # Row absent -> append it so the monitor is never invisible.
        row_copy = dict(m5_row)
        row_copy["m5fix_applied"] = True
        patched.append(row_copy)
    return patched


def _worst_row_severity(services: List[Dict[str, Any]]) -> str:
    """Return the worst severity across all services[] rows."""
    worst = OK
    for row in services:
        if not isinstance(row, dict):
            continue
        sev = str(row.get("severity", OK))
        worst = _degrade(worst, sev)
    return worst


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def patch_m5_row(
    doc: Dict[str, Any],
    *,
    now: Optional[float] = None,
    hb_path: Optional[pathlib.Path] = None,
    fresh_sec: float = M5_FRESH_SEC,
) -> Dict[str, Any]:
    """Patch *doc* so the m5_autonomy_monitor services[] row is never stale-green.

    Reads the m5 heartbeat file DIRECTLY, computes age, and DEGRADES the row
    (and overall) if the heartbeat is absent or older than fresh_sec.  The patch
    is MONOTONE-DOWN: it never upgrades a row that is already worse.

    Args:
        doc:       The autonomy status document (from status_composer.compose or
                   autonomy_status.json).  Must be a dict.  Mutated copy is returned.
        now:       Epoch float (injectable for tests); defaults to time.time().
        hb_path:   Override the heartbeat path (injectable for tests).
        fresh_sec: Freshness window in seconds (default: M5_FRESH_SEC = 300.0).

    Returns:
        A new dict (copy of *doc*) with the m5 row patched and overall degraded
        if necessary.  Never raises.
    """
    try:
        if not isinstance(doc, dict):
            return {
                "overall": DEGRADED,
                "services": [],
                "notes": ["m5fix: doc is not a dict -> degraded envelope"],
                "m5fix_applied": True,
                "honest_note": "calibration not edge; no $ field",
            }
        t = float(now) if now is not None else time.time()
        path = hb_path if hb_path is not None else _M5_HB_PATH
        age_sec = _m5_age_sec(path, t)
        m5_row = _build_m5_services_row(age_sec, fresh_sec)

        out = dict(doc)
        services = list(doc.get("services") or [])
        services = _patch_services_row(services, m5_row)
        out["services"] = services

        # Recompute overall: start from doc's own overall, then DEGRADE by
        # the worst row severity and the new m5 row severity. Never upgrades.
        current_overall = str(out.get("overall", DEGRADED))
        if current_overall not in _RANK:
            current_overall = DEGRADED
        current_overall = _degrade(current_overall, _worst_row_severity(services))
        current_overall = _degrade(current_overall, m5_row["severity"])
        out["overall"] = current_overall

        # Append a note only when the m5 is the degrading factor.
        if m5_row["severity"] != OK:
            notes = list(out.get("notes") or [])
            notes.append("m5fix: %s" % (m5_row["reason"] or "m5 degraded"))
            out["notes"] = notes

        out["m5fix_applied"] = True
        # Honest rail: no $ field, no fabricated edge.
        out.setdefault(
            "honest_note",
            "calibration not edge; no $ field; stale-never-green for m5",
        )
        return out
    except Exception:  # noqa: BLE001 -- a patch failure must never crash callers
        safe = dict(doc) if isinstance(doc, dict) else {}
        safe["overall"] = _degrade(str(safe.get("overall", DEGRADED)), DEGRADED)
        safe["m5fix_applied"] = True
        notes = list(safe.get("notes") or [])
        notes.append("m5fix: internal error -> overall degraded (fail-safe)")
        safe["notes"] = notes
        return safe


__all__ = [
    "OK", "DEGRADED", "DOWN",
    "M5_COMPONENT", "M5_FRESH_SEC",
    "patch_m5_row",
]
