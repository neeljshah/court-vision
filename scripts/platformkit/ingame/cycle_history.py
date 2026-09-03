"""Append-only, fail-open history for in-game capture-cycle counters."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_HISTORY_DIR = _REPO_ROOT / "data" / "cache" / "ingame_cycle_history"
MAX_BYTES_PER_DAY = 50 * 1024 * 1024

_COUNTER_KEYS = (
    "n_live", "n_pairs", "n_bets", "n_requests_total", "n_429_total",
    "cycle_duration_sec",
)


def _utc(now: Optional[datetime]) -> datetime:
    value = now if now is not None else datetime.now(timezone.utc)
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _record(heartbeat: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    ts = heartbeat.get("as_of")
    if not isinstance(ts, str) or not ts:
        ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    record = {"ts": ts}
    record.update({key: heartbeat.get(key) for key in _COUNTER_KEYS})
    failures = heartbeat.get("grade_write_fail_by_reason")
    record["grade_write_fail_by_reason"] = dict(failures) if isinstance(failures, dict) else {}
    return record


def append_cycle_row(heartbeat: Dict[str, Any], now: Optional[datetime] = None,
                     history_dir: Optional[Path] = None) -> int:
    """Append one compact cycle record, returning 1 on success and 0 on any failure.

    The heartbeat remains the current snapshot. This separate store preserves the
    counters and failure-reason map for every completed cycle. It is append-only,
    bounded per UTC day, and fail-open so observability never interrupts a poll.
    """
    try:
        nowdt = _utc(now)
        base = Path(history_dir) if history_dir is not None else DEFAULT_HISTORY_DIR
        path = base / (nowdt.strftime("%Y-%m-%d") + ".jsonl")
        line = json.dumps(_record(heartbeat, nowdt), ensure_ascii=True, separators=(",", ":"))
        path.parent.mkdir(parents=True, exist_ok=True)
        size = path.stat().st_size if path.is_file() else 0
        if size + len(line.encode("utf-8")) + 1 > MAX_BYTES_PER_DAY:
            logger.warning("cycle_history: %s over size bound; dropping cycle", path)
            return 0
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return 1
    except Exception as exc:  # noqa: BLE001 -- history must never sink a capture cycle
        logger.warning("cycle_history: append failed: %s", exc)
        return 0


__all__ = ["append_cycle_row", "DEFAULT_HISTORY_DIR", "MAX_BYTES_PER_DAY"]
