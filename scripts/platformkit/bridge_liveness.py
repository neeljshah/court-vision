"""Check the workstation footage-bridge supervisor without touching the pod.

The bridge supervisor writes a pid and a timestamped status snapshot.  This
checker deliberately uses ``os.kill(pid, 0)`` rather than command-line search:
an invocation that mentions the target process otherwise matches itself.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from scripts.platformkit.bridge_supervisor import PID_PATH, POLL_SECONDS, STATUS_PATH


STATUS_MAX_AGE_SECONDS = POLL_SECONDS * 3 + 30


@dataclass(frozen=True)
class Liveness:
    """The supervisor state derived from a pid and timestamped snapshot."""

    state: str
    pid: int | None
    status_age_seconds: float | None
    reason: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _read_pid(path: Path) -> int | None:
    try:
        pid = int(path.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return None
    return pid if pid > 0 else None


def pid_is_alive(pid: int | None) -> bool:
    """Return whether the operating system still knows this pid."""
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _status_age(path: Path, now: datetime) -> tuple[float | None, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        written_at = payload["written_at"]
        normalized = str(written_at).replace("Z", "+00:00")
        fractional = re.match(r"^(.*\.)(\d+)([+-]\d\d:\d\d)$", normalized)
        if fractional:
            normalized = fractional.group(1) + fractional.group(2)[:6] + fractional.group(3)
        timestamp = datetime.fromisoformat(normalized)
        if timestamp.tzinfo is None:
            return None, "status written_at has no timezone"
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None, "status lacks a valid written_at"
    return max(0.0, (now - timestamp.astimezone(timezone.utc)).total_seconds()), None


def status_is_fresh(
    status_path: Path,
    max_age_seconds: int = STATUS_MAX_AGE_SECONDS,
    now: datetime | None = None,
) -> tuple[bool, float | None, str]:
    """Return freshness without treating cached lane values as current."""
    age, status_problem = _status_age(status_path, now or _now())
    if status_problem:
        return False, age, status_problem
    if age is not None and age > max_age_seconds:
        return False, age, "status older than %ds" % max_age_seconds
    return True, age, "status fresh"


def assess(
    status_path: Path = STATUS_PATH,
    pid_path: Path = PID_PATH,
    max_age_seconds: int = STATUS_MAX_AGE_SECONDS,
    now: datetime | None = None,
) -> Liveness:
    """Classify the supervisor as UP, DOWN, or UNKNOWN for stale status."""
    checked_at = now or _now()
    pid = _read_pid(pid_path)
    fresh, age, status_reason = status_is_fresh(status_path, max_age_seconds, checked_at)
    if not pid_is_alive(pid):
        return Liveness("DOWN", pid, age, "pid missing or not alive")
    if not fresh:
        return Liveness("UNKNOWN", pid, age, status_reason)
    return Liveness("UP", pid, age, "pid alive and status fresh")


def restart_if_down(
    result: Liveness,
    per_lane: int,
    start: Callable[..., subprocess.Popen] = subprocess.Popen,
) -> tuple[str, int | None]:
    """Start only a stopped local bridge supervisor; never kill any process.

    The pod track daemon and every pod process are explicitly out of scope:
    this function has no SSH, pod command, or kill path.  A live supervisor is
    a no-op, avoiding duplicate bridge workers on the same disjoint lanes.
    """
    if result.state != "DOWN":
        return "no-op", None
    process = start([sys.executable, "-m", "scripts.platformkit.bridge_supervisor",
                     "--per-lane", str(per_lane)])
    return "started", process.pid


def _format(result: Liveness, max_age_seconds: int) -> str:
    pid = "none" if result.pid is None else str(result.pid)
    age = "unknown" if result.status_age_seconds is None else "%.1f" % result.status_age_seconds
    return "state=%s pid=%s status_age_seconds=%s/%d reason=%s" % (
        result.state, pid, age, max_age_seconds, result.reason)


def main() -> int:
    """Print the current state and optionally start a missing supervisor."""
    parser = argparse.ArgumentParser(description="Check footage bridge supervisor liveness")
    parser.add_argument("--status-path", type=Path, default=STATUS_PATH)
    parser.add_argument("--pid-path", type=Path, default=PID_PATH)
    parser.add_argument("--max-age-seconds", type=int, default=STATUS_MAX_AGE_SECONDS)
    parser.add_argument("--per-lane", type=int, default=3)
    parser.add_argument("--restart-if-down", action="store_true")
    args = parser.parse_args()
    result = assess(args.status_path, args.pid_path, args.max_age_seconds)
    print(_format(result, args.max_age_seconds))
    if args.restart_if_down:
        action, pid = restart_if_down(result, args.per_lane)
        print("restart=%s%s" % (action, " pid=%d" % pid if pid else ""))
    return 0 if result.state == "UP" else 1


if __name__ == "__main__":
    raise SystemExit(main())
