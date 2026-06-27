"""supervisor.status -- render the supervised stack's live status to one JSON.

The supervisor calls :func:`write_status` on every supervise tick so the UI
(and an operator's ``ops doctor`` runbook) can render ONE document describing
what is up, what is restarting, and what has failed:

    data/frontend/ops/supervisor_status.json

Shape (stable, additive-only)::

    {
      "schema_version": "1.0.0",
      "profile": "default",
      "started_at": 1718700000.0,        # epoch the supervisor booted
      "updated_at": 1718700123.4,        # epoch this snapshot was written
      "all_ready": false,
      "procs": [
        {"name": "m1_api_paper", "state": "READY", "pid": 12345,
         "restarts": 0, "ready": true, "detail": {...}},
        ...
      ]
    }

``supervisor_status(...)`` builds the dict (pure, testable); ``write_status(...)``
atomically persists it (tmp + os.replace) and NEVER raises -- an always-on boot
must not die because a status write hit a transient filesystem error.

Stdlib-only, ASCII-only, <=300 LOC. Never writes ``data/registry/``; never
flips a flag on.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
_STATUS_REL = "data/frontend/ops/supervisor_status.json"
_STATUS_PATH = _REPO_ROOT / _STATUS_REL
_SCHEMA_VERSION = "1.0.0"


def supervisor_status(
    procs: List[Dict[str, Any]],
    *,
    profile: str = "default",
    started_at: Optional[float] = None,
    updated_at: Optional[float] = None,
) -> Dict[str, Any]:
    """Build the status document from a list of per-proc state dicts.

    Each entry of *procs* should carry at least ``name`` and ``state``; the
    optional keys ``pid``, ``restarts``, ``ready``, ``detail`` are passed
    through (defaulted) so the UI always sees the same shape. Pure -- does no
    I/O, so a test can assert the shape directly.
    """
    rows: List[Dict[str, Any]] = []
    all_ready = True
    for p in procs:
        ready = bool(p.get("ready", False))
        if not ready:
            all_ready = False
        rows.append({
            "name": str(p.get("name", "")),
            "state": str(p.get("state", "UNKNOWN")),
            "pid": p.get("pid"),
            "restarts": int(p.get("restarts", 0)),
            "ready": ready,
            "detail": p.get("detail", {}),
        })
    return {
        "schema_version": _SCHEMA_VERSION,
        "profile": str(profile),
        "started_at": started_at,
        "updated_at": float(updated_at if updated_at is not None else time.time()),
        "all_ready": all_ready if rows else False,
        "procs": rows,
    }


def render_rows(specs: List[Any], states: Dict[str, Any],
                breaker_tripped: Dict[str, bool]) -> List[Dict[str, Any]]:
    """Build the per-proc status rows from the supervisor's live state maps.

    Pulled out of Supervisor for the <=300 LOC rail. *states* maps name -> a
    _ProcState (state/pid/attempts/ready/detail); *breaker_tripped* maps name ->
    bool (C7 crash-rate breaker). A tripped spec gets detail["crash_breaker"] =
    "DEGRADED" so the status doc + UI show the honest chronically-broken state.
    """
    rows: List[Dict[str, Any]] = []
    for spec in specs:
        st = states[spec.name]
        detail = dict(st.detail) if isinstance(st.detail, dict) else {}
        if breaker_tripped.get(spec.name):
            detail["crash_breaker"] = "DEGRADED"
        rows.append({
            "name": spec.name, "state": st.state, "pid": st.pid,
            "restarts": st.attempts, "ready": st.ready, "detail": detail,
        })
    return rows


def write_status(
    doc: Dict[str, Any],
    *,
    path: Optional[Path] = None,
) -> Optional[str]:
    """Atomically write *doc* to the status path. Never raises.

    Returns the written path (str) on success, or None on failure. Uses a
    tmp file + ``os.replace`` so a reader never sees a partial document.
    """
    try:
        target = Path(path) if path is not None else _STATUS_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(
            json.dumps(doc, indent=2, sort_keys=False, default=str),
            encoding="utf-8",
        )
        os.replace(str(tmp), str(target))
        return str(target)
    except Exception:  # noqa: BLE001 -- a status write must not sink the supervisor
        return None


def status_path() -> str:
    """Absolute path of the supervisor status JSON the UI should read."""
    return str(_STATUS_PATH)


__all__ = ["supervisor_status", "write_status", "status_path", "render_rows"]
