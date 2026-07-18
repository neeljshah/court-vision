"""scripts.platformkit.tip_capture.schedule -- pure capture-pass scheduling math.

No I/O here (fully unit-testable without mocking time/network): given a tip
time and "now", which capture passes (T-60/T-30/T-5 minutes before tip) are
due, and how long should the daemon sleep before the next one is due. See
daemon.py's module docstring for the full tip_capture design.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# Capture passes: minutes before tip. TOLERANCE_MIN absorbs daemon-loop jitter
# (schedule-driven sleep aims to land exactly here; slack covers a slow tick).
PASS_OFFSETS_MIN: Dict[str, int] = {"T60": 60, "T30": 30, "T5": 5}
TOLERANCE_MIN = 5.0

MAX_SLEEP_SEC = 900.0   # ceiling: re-check the slate at least every 15 min
MIN_SLEEP_SEC = 5.0


def parse_iso(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def minutes_until(tip: datetime, now: datetime) -> float:
    return (tip - now).total_seconds() / 60.0


def due_passes(tip: datetime, now: datetime, captured: Iterable[str] = (),
               *, offsets: Dict[str, int] = PASS_OFFSETS_MIN,
               tolerance_min: float = TOLERANCE_MIN) -> List[str]:
    """Pass names due for capture right now: within tolerance of their target
    minutes-before-tip, and not already captured. Order follows *offsets*."""
    mins = minutes_until(tip, now)
    done = set(captured)
    return [name for name, off in offsets.items()
            if name not in done and abs(mins - off) <= tolerance_min]


def next_wake_seconds(games: Sequence[Tuple[datetime, Iterable[str]]], now: datetime,
                       *, offsets: Dict[str, int] = PASS_OFFSETS_MIN,
                       max_sleep: float = MAX_SLEEP_SEC,
                       min_sleep: float = MIN_SLEEP_SEC) -> float:
    """Seconds until the next not-yet-captured pass across *games*, bounded to
    [min_sleep, max_sleep] so the slate/heartbeat still refreshes periodically."""
    candidates: List[float] = []
    for tip, captured in games:
        done = set(captured)
        for name, off in offsets.items():
            if name in done:
                continue
            delta = (tip - timedelta(minutes=off) - now).total_seconds()
            candidates.append(max(0.0, delta))
    if not candidates:
        return max_sleep
    return max(min_sleep, min(max_sleep, min(candidates)))


__all__ = [
    "PASS_OFFSETS_MIN", "TOLERANCE_MIN", "MAX_SLEEP_SEC", "MIN_SLEEP_SEC",
    "parse_iso", "minutes_until", "due_passes", "next_wake_seconds",
]
