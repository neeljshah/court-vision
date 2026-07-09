"""scripts.platformkit.ops_sentinel.heartbeat_coverage -- every HEARTBEAT-
readiness ProcSpec in the supervisor spec list must have a heartbeat file
fresher than its declared window (fresh_sec, itself already ~2x the daemon's
cadence + margin by house convention). Missing/stale -> a NAMED RED row.

Non-heartbeat specs (HTTP/TCP/NONE readiness) read NA -- never green-by-absence
(the readiness=NONE daemons are covered separately by m29 output_freshness).
READ-ONLY against supervisor state: this sentinel never restarts anything.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ops_sentinel/test_heartbeat_coverage.py -q
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from scripts.platformkit.ops_sentinel.status_doc import (
    GREEN, NA, OPS_DIR, RED, repo_root, write_doc,
)

COMPONENT = "ops_heartbeat_coverage"
STATUS_PATH = OPS_DIR / "heartbeat_coverage.json"
_NOTE = ("heartbeat-coverage visibility only; READ-ONLY against supervisor "
         "state, NO restart authority. NA = no heartbeat declared (HTTP/TCP/"
         "NONE readiness -- m29 output_freshness covers the NONE daemons).")


def _default_specs() -> Sequence[Any]:
    from supervisor.stack_specs import base_specs  # read-only import
    return base_specs()


def check_all(*, now: Optional[float] = None,
              specs_fn: Optional[Callable[[], Sequence[Any]]] = None,
              repo: Optional[Path] = None) -> List[Dict[str, Any]]:
    """One row per ProcSpec. HEARTBEAT readiness: file age vs fresh_sec ->
    GREEN/RED(missing|stale). Other readiness kinds -> NA. Never raises."""
    ts = float(now) if now is not None else time.time()
    root = Path(repo) if repo is not None else repo_root()
    try:
        specs = list((specs_fn if specs_fn is not None else _default_specs)())
    except Exception as exc:  # noqa: BLE001
        return [{"name": "spec_list", "status": RED,
                 "reason": "error:%s" % str(exc)[:80]}]
    rows: List[Dict[str, Any]] = []
    for spec in specs:
        name = getattr(spec, "name", "?")
        rd = getattr(spec, "readiness", None)
        kind = getattr(rd, "kind", "none")
        hb = getattr(rd, "heartbeat_path", None)
        row: Dict[str, Any] = {"name": name, "readiness_kind": kind}
        try:
            if kind != "heartbeat-file-fresh" or not hb:
                row.update(status=NA, age_sec=None,
                           reason="no_heartbeat_declared")
            else:
                p = Path(hb)
                if not p.is_absolute():
                    p = root / p
                fresh = float(getattr(rd, "fresh_sec", 120.0) or 120.0)
                row.update(heartbeat_path=str(p), fresh_sec=fresh)
                if not p.exists():
                    row.update(status=RED, age_sec=None, reason="missing")
                else:
                    age = max(0.0, ts - p.stat().st_mtime)
                    row["age_sec"] = round(age, 1)
                    if age > fresh:
                        row.update(status=RED, reason="stale")
                    else:
                        row.update(status=GREEN, reason=None)
        except Exception as exc:  # noqa: BLE001
            row.update(status=RED, reason="error:%s" % str(exc)[:80])
        rows.append(row)
    return rows


def tick(*, now: Optional[float] = None,
         specs_fn: Optional[Callable[[], Sequence[Any]]] = None,
         status_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Check -> status doc. Never raises."""
    ts = float(now) if now is not None else time.time()
    try:
        rows = check_all(now=ts, specs_fn=specs_fn)
    except Exception as exc:  # noqa: BLE001
        rows = [{"name": "heartbeat_coverage", "status": RED,
                 "reason": "error:%s" % str(exc)[:80]}]
    write_doc(status_path if status_path is not None else STATUS_PATH,
              COMPONENT, rows, now=ts, honest_note=_NOTE)
    return rows


__all__ = ["COMPONENT", "STATUS_PATH", "check_all", "tick"]
