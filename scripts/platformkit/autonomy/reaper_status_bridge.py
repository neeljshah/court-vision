"""scripts.platformkit.autonomy.reaper_status_bridge -- surface reaper verdicts.

IOP-08: HeartbeatReaper STALE_HUNG verdicts are invisible to the services view
because the reaper runs inside the supervisor (process-level) but its status is
never written to a file the UI / runbook can read. This bridge closes that gap.

WHAT THIS MODULE DOES
---------------------
1.  ``write_reaper_status(rows, *, out_path)`` -- atomically writes a JSON file
    (reaper_status.json) containing the reaper's per-service snapshot (the list
    returned by ``HeartbeatReaper.status()``). Called by the supervisor on every
    tick -- pure serialisation, no computation.

2.  ``merge_reaper_into_services(services, reaper_rows)`` -- degrade-only merge.
    For each reaper row whose ``status`` is STALE_HUNG or NO_HEARTBEAT, the
    matching entry in the services[] list is DEGRADED (severity set to "degraded"
    or "down" if already "down"; never upgraded to "ok"). A service not mentioned
    in reaper_rows is left unchanged. A reaper row with HEALTHY status changes
    nothing -- the merge is monotone-DOWN only.

3.  ``load_reaper_status(*, path)`` -- best-effort JSON read; missing file ->
    empty list (never raises, never reads "unknown" as "ok").

INVARIANTS
----------
- No $ field; calibration not edge; real-money path stays DENY.
- Degrade-only: merge NEVER upgrades a service severity to "ok".
- Missing reaper file -> list of zero rows (unknown) -- not green.
- NEVER raises; stdlib + ASCII; <=300 LOC.
- Reads/writes only under data/frontend/ops/ (never data/registry/).
- No fabricated probabilities, no ROI, no PnL field anywhere.

OUTPUT FILE
-----------
``data/frontend/ops/reaper_status.json`` shape::

    {
      "generated_at": <epoch float>,
      "rows": [
        {"name": str, "status": "STALE_HUNG"|"HEALTHY"|"NO_HEARTBEAT",
         "breaker": {...}},
        ...
      ],
      "honest_note": "calibration not edge; no $ field; ..."
    }
"""
from __future__ import annotations

import json
import os
import pathlib
import time
from typing import Any, Dict, List, Optional

from scripts.platformkit.autonomy.heartbeat_reaper import STALE_HUNG, NO_HEARTBEAT

# Severity constants (mirrors status_composer; no import to avoid circular dep).
_OK = "ok"
_DEGRADED = "degraded"
_DOWN = "down"
_RANK = {_OK: 0, _DEGRADED: 1, _DOWN: 2}
_BY_RANK = {0: _OK, 1: _DEGRADED, 2: _DOWN}

_REPO = pathlib.Path(__file__).resolve().parents[3]
DEFAULT_REAPER_STATUS_PATH = (
    _REPO / "data" / "frontend" / "ops" / "reaper_status.json"
)

_HONEST_NOTE = (
    "calibration not edge; no $ field; degrade-only merge; "
    "missing file -> unknown rows, never green."
)

# Reaper status strings that represent a non-healthy (degraded/down) state.
_UNHEALTHY_STATUSES = frozenset({STALE_HUNG, NO_HEARTBEAT})


# ---------------------------------------------------------------------------
# Severity helpers
# ---------------------------------------------------------------------------

def _degrade(current: str, candidate: str) -> str:
    """Return the WORSE of two severity strings; never upgrades."""
    cur = _RANK.get(current, _RANK[_DEGRADED])
    cand = _RANK.get(candidate, _RANK[_DEGRADED])
    return _BY_RANK[max(cur, cand)]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_reaper_status(
    rows: List[Dict[str, Any]],
    *,
    out_path: Optional[pathlib.Path] = None,
    now: Optional[float] = None,
) -> bool:
    """Atomically write reaper rows to *out_path* (tmp + os.replace).

    Parameters
    ----------
    rows:
        The list returned by ``HeartbeatReaper.status()``.
    out_path:
        Destination path; defaults to ``data/frontend/ops/reaper_status.json``.
    now:
        Epoch timestamp for ``generated_at``; defaults to ``time.time()``.

    Returns
    -------
    bool
        True on success; False on any I/O error. Never raises.
    """
    try:
        path = out_path if out_path is not None else DEFAULT_REAPER_STATUS_PATH
        ts = float(now) if now is not None else time.time()
        # Sanitise rows: accept only dicts; drop anything else.
        safe_rows: List[Dict[str, Any]] = [
            r for r in (rows or []) if isinstance(r, dict)
        ]
        doc: Dict[str, Any] = {
            "generated_at": ts,
            "rows": safe_rows,
            "honest_note": _HONEST_NOTE,
        }
        raw = json.dumps(doc, ensure_ascii=True, indent=2, sort_keys=True)
        path = pathlib.Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(raw, encoding="ascii")
        os.replace(str(tmp), str(path))
        return True
    except Exception:  # noqa: BLE001 -- write must never crash the supervise tick
        return False


def load_reaper_status(
    *,
    path: Optional[pathlib.Path] = None,
) -> List[Dict[str, Any]]:
    """Best-effort load of the reaper_status.json rows list.

    Returns an empty list when the file is absent, unreadable, or malformed.
    An empty list means "unknown" -- it is NOT treated as "all healthy".
    Never raises.
    """
    try:
        p = pathlib.Path(path) if path is not None else DEFAULT_REAPER_STATUS_PATH
        if not p.exists():
            return []
        raw = p.read_text(encoding="ascii")
        if not raw.strip():
            return []
        doc = json.loads(raw)
        if not isinstance(doc, dict):
            return []
        rows = doc.get("rows")
        if not isinstance(rows, list):
            return []
        return [r for r in rows if isinstance(r, dict)]
    except Exception:  # noqa: BLE001 -- a bad file is unknown, not green
        return []


def merge_reaper_into_services(
    services: List[Dict[str, Any]],
    reaper_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Degrade-only merge of reaper verdicts into the services[] list.

    For each reaper row whose ``status`` is in ``_UNHEALTHY_STATUSES``
    (STALE_HUNG or NO_HEARTBEAT), the matching entry in *services* (matched by
    ``name``) has its ``severity`` DEGRADED (never upgraded).  A reaper row with
    status HEALTHY leaves the matching service unchanged.

    Services not mentioned in *reaper_rows* are returned unchanged.
    Reaper rows that do not match any service are IGNORED (additive-only for
    existing services; the bridge cannot invent new service entries).

    Parameters
    ----------
    services:
        The ``services[]`` list from the autonomy_status / compose document.
        Each item is a dict that MAY have a ``severity`` key.
    reaper_rows:
        The list from ``HeartbeatReaper.status()`` or ``load_reaper_status()``.

    Returns
    -------
    list
        A NEW list of service dicts with severity potentially degraded. The
        original *services* list is never mutated in place. Never raises.
    """
    try:
        # Build a name -> reaper_status index for O(1) lookup.
        reaper_index: Dict[str, str] = {}
        for row in (reaper_rows or []):
            if not isinstance(row, dict):
                continue
            name = row.get("name")
            status = row.get("status")
            if name and isinstance(name, str) and isinstance(status, str):
                reaper_index[name] = status

        result: List[Dict[str, Any]] = []
        for svc in (services or []):
            if not isinstance(svc, dict):
                result.append(svc)
                continue
            name = svc.get("name")
            reaper_status = reaper_index.get(name) if name else None
            if reaper_status in _UNHEALTHY_STATUSES:
                # Degrade but never upgrade; unknown current severity -> DEGRADED.
                current_sev = str(svc.get("severity", _OK))
                new_sev = _degrade(current_sev, _DEGRADED)
                item = dict(svc)
                item["severity"] = new_sev
                item["reaper_status"] = reaper_status
                result.append(item)
            else:
                result.append(dict(svc))
        return result
    except Exception:  # noqa: BLE001 -- merge must never crash compose
        # Defensive: return a shallow copy of the input unchanged.
        try:
            return [dict(s) if isinstance(s, dict) else s for s in (services or [])]
        except Exception:  # noqa: BLE001
            return []


__all__ = [
    "write_reaper_status",
    "load_reaper_status",
    "merge_reaper_into_services",
    "DEFAULT_REAPER_STATUS_PATH",
]
