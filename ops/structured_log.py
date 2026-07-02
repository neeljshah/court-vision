"""ops.structured_log -- atomic structured-log substrate.

Writes one ASCII JSON line per event to logs/events.jsonl.  Never raises.
Provides a tail helper for reading events since a given epoch timestamp.

Public API
----------
log_event(component, level, msg, **fields)
    Append one JSON line to logs/events.jsonl. Fire-and-forget; never raises.
    Fields: ts (epoch float), component (str), level (str), msg (str), **fields.

read_events(since=None, path=None) -> list[dict]
    Return events from the log file with ts >= since (epoch float).
    Missing file -> []. Corrupt lines are silently skipped.

Per-file test:
    python -m pytest tests/ops/test_liveness.py -q
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# ---------------------------------------------------------------------------
# Repo root + default log path
# ---------------------------------------------------------------------------

def _find_repo_root() -> Path:
    candidate = Path(__file__).resolve()
    for _ in range(8):
        candidate = candidate.parent
        if (candidate / "CLAUDE.md").exists():
            return candidate
    return Path(__file__).resolve().parents[2]


_REPO_ROOT: Path = _find_repo_root()
_DEFAULT_LOG_PATH: Path = _REPO_ROOT / "logs" / "events.jsonl"

# Thread lock: one writer at a time per process (cross-process safety via O_APPEND).
_write_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def log_event(
    component: str,
    level: str,
    msg: str,
    *,
    path: Optional[Union[str, Path]] = None,
    _now: Optional[float] = None,
    **fields: Any,
) -> None:
    """Append one ASCII JSON event line to the log.  Never raises."""
    try:
        log_path = Path(path) if path is not None else _DEFAULT_LOG_PATH
        ts = _now if _now is not None else time.time()
        record: Dict[str, Any] = {
            "ts": round(ts, 3),
            "component": str(component),
            "level": str(level).upper(),
            "msg": str(msg),
        }
        record.update({str(k): v for k, v in fields.items()})
        line = json.dumps(record, ensure_ascii=True, default=str) + "\n"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with _write_lock:
            # O_APPEND is atomic at the OS level for reasonably-sized lines.
            with open(log_path, "a", encoding="ascii", errors="replace") as fh:
                fh.write(line)
    except Exception:  # noqa: BLE001 -- observability must never crash the caller
        pass


def read_events(
    since: Optional[float] = None,
    *,
    path: Optional[Union[str, Path]] = None,
) -> List[Dict[str, Any]]:
    """Return events with ts >= since from the log file.

    Missing file -> []. Corrupt lines are skipped silently.
    """
    log_path = Path(path) if path is not None else _DEFAULT_LOG_PATH
    if not log_path.exists():
        return []
    results: List[Dict[str, Any]] = []
    try:
        with open(log_path, "r", encoding="ascii", errors="replace") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rec, dict):
                    continue
                if since is not None:
                    try:
                        if float(rec.get("ts", 0.0)) < since:
                            continue
                    except (TypeError, ValueError):
                        continue
                results.append(rec)
    except OSError:
        pass
    return results


__all__ = ["log_event", "read_events"]
