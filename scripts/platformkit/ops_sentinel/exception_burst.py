"""scripts.platformkit.ops_sentinel.exception_burst -- tails the supervised
daemons' stderr logs (logs/m*.err) and flags a daemon whose NEW tracebacks/min
since the last tick exceeds a threshold as a YELLOW row naming the daemon.

Incremental: a per-file (size, ts) state doc means each tick reads only the
newly APPENDED bytes; a shrunken file (rotation/truncate) just re-baselines.
First tick seeds state and reports nothing (rate unknown -- honest, not green).
Read-only, no restart authority.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ops_sentinel/test_exception_burst.py -q
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.ops_sentinel.status_doc import (
    GREEN, OPS_DIR, STATE_DIR, YELLOW, load_json, repo_root, write_doc,
)

COMPONENT = "ops_exception_burst"
STATUS_PATH = OPS_DIR / "exception_burst.json"
STATE_PATH = STATE_DIR / "exception_burst_state.json"
LOG_DIR = repo_root() / "logs"
_NOTE = ("exception-burst visibility only (tracebacks/min in newly appended "
         "stderr); read-only, NO restart authority. First tick seeds state "
         "and reports no rows (rate unknown).")

TRACEBACK_RE = re.compile(rb"Traceback \(most recent call last\)")
THRESHOLD_PER_MIN = 3.0   # ponytail: flat threshold; per-daemon tuning if noisy
_READ_CAP = 512 * 1024    # max appended bytes examined per file per tick
_DAEMON_ERR = re.compile(r"^m\d+\w*\.err$")


def _daemon_logs(log_dir: Path) -> List[Path]:
    try:
        return sorted(p for p in log_dir.iterdir()
                      if p.is_file() and _DAEMON_ERR.match(p.name))
    except Exception:  # noqa: BLE001
        return []


def _count_new(path: Path, prev_size: int) -> int:
    """Tracebacks in the bytes appended past *prev_size* (capped)."""
    with path.open("rb") as fh:
        fh.seek(max(0, prev_size))
        return len(TRACEBACK_RE.findall(fh.read(_READ_CAP)))


def check_all(*, now: Optional[float] = None,
              log_dir: Optional[Path] = None,
              state_path: Optional[Path] = None,
              threshold_per_min: float = THRESHOLD_PER_MIN,
              ) -> List[Dict[str, Any]]:
    """Rows ONLY for daemons with new tracebacks this interval: YELLOW above
    threshold, GREEN (informational) below. Persists state. Never raises."""
    ts = float(now) if now is not None else time.time()
    ld = Path(log_dir) if log_dir is not None else LOG_DIR
    sp = Path(state_path) if state_path is not None else STATE_PATH
    state = load_json(sp)
    files = state.get("files") if isinstance(state.get("files"), dict) else {}
    rows: List[Dict[str, Any]] = []
    new_files: Dict[str, Any] = {}
    for p in _daemon_logs(ld):
        daemon = p.stem
        try:
            size = p.stat().st_size
            prev = files.get(daemon)
            new_files[daemon] = {"size": size, "ts": ts}
            if not isinstance(prev, dict):
                continue  # first sight: baseline only
            prev_size = int(prev.get("size", 0))
            prev_ts = float(prev.get("ts", ts))
            if size < prev_size:
                continue  # rotated/truncated: re-baseline, no verdict
            count = _count_new(p, prev_size) if size > prev_size else 0
            if count <= 0:
                continue
            minutes = max((ts - prev_ts) / 60.0, 1.0 / 60.0)
            rate = count / minutes
            rows.append({
                "name": daemon, "log": str(p), "new_tracebacks": count,
                "interval_sec": round(ts - prev_ts, 1),
                "rate_per_min": round(rate, 2),
                "threshold_per_min": threshold_per_min,
                "status": YELLOW if rate > threshold_per_min else GREEN,
                "reason": "traceback_burst" if rate > threshold_per_min else None,
            })
        except Exception as exc:  # noqa: BLE001
            rows.append({"name": daemon, "status": YELLOW,
                         "reason": "error:%s" % str(exc)[:80]})
    try:
        sp.parent.mkdir(parents=True, exist_ok=True)
        tmp = sp.with_suffix(sp.suffix + ".tmp")
        tmp.write_text(json.dumps({"updated_at": ts, "files": new_files},
                                  ensure_ascii=True, sort_keys=True),
                       encoding="ascii")
        os.replace(str(tmp), str(sp))
    except Exception:  # noqa: BLE001
        pass
    return rows


def tick(*, now: Optional[float] = None,
         status_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Check -> status doc. Never raises."""
    ts = float(now) if now is not None else time.time()
    try:
        rows = check_all(now=ts)
    except Exception as exc:  # noqa: BLE001
        rows = [{"name": "exception_burst", "status": YELLOW,
                 "reason": "error:%s" % str(exc)[:80]}]
    write_doc(status_path if status_path is not None else STATUS_PATH,
              COMPONENT, rows, now=ts, honest_note=_NOTE)
    return rows


__all__ = ["COMPONENT", "STATUS_PATH", "STATE_PATH", "THRESHOLD_PER_MIN",
           "check_all", "tick"]
