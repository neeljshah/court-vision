#!/usr/bin/env python3
"""Detect and kill stuck run_clip.py workers.

A worker is "stuck" if:
  - elapsed time > 90 minutes, AND
  - frame counter in run.log hasn't advanced in last 5 minutes (mtime > 5 min ago
    OR last "frame N" line unchanged since previous check)

We persist last-seen frame counts to /workspace/.stuck_state.json across invocations.
On confirmed stuck: send SIGTERM (then SIGKILL after 10s), and rm -rf the tracking
dir so the auto-loop can retry the game cleanly.
"""
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

STATE_PATH = Path("/workspace/.stuck_state.json")
TRACKING_ROOT = Path("/workspace/nba-ai-system/data/tracking")
ELAPSED_MIN_THRESHOLD = 90
RUNLOG_STALE_SEC = 300  # 5 min
FRAME_RE = re.compile(r"frame[s]?[\s_=:]+(\d+)", re.IGNORECASE)


def parse_etime_minutes(etime: str) -> int:
    """ps etime format: [[DD-]HH:]MM:SS"""
    if "-" in etime:
        days, rest = etime.split("-", 1)
        d = int(days)
    else:
        d, rest = 0, etime
    parts = rest.split(":")
    if len(parts) == 3:
        h, m, s = (int(x) for x in parts)
    elif len(parts) == 2:
        h, m, s = 0, int(parts[0]), int(parts[1])
    else:
        h, m, s = 0, 0, int(parts[0])
    return d * 1440 + h * 60 + m


def list_workers() -> list[dict]:
    out = subprocess.check_output(
        ["ps", "-eo", "pid,etime,args"],
        text=True,
    )
    workers = []
    for line in out.splitlines():
        m = re.match(r"\s*(\d+)\s+(\S+)\s+(.*)", line)
        if not m:
            continue
        pid, etime, args = m.group(1), m.group(2), m.group(3)
        if "/usr/bin/python3" not in args:
            continue
        if "run_clip.py --video" not in args:
            continue
        gid_m = re.search(r"--game-id\s+(\d+)", args)
        if not gid_m:
            continue
        workers.append({
            "pid": int(pid),
            "etime_min": parse_etime_minutes(etime),
            "gid": gid_m.group(1),
        })
    return workers


def last_frame_in_log(log_path: Path) -> int | None:
    if not log_path.exists():
        return None
    try:
        with open(log_path, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            chunk = min(size, 32 * 1024)
            fh.seek(size - chunk)
            tail = fh.read().decode("utf-8", errors="ignore")
    except OSError:
        return None
    matches = FRAME_RE.findall(tail)
    if not matches:
        return None
    try:
        return int(matches[-1])
    except ValueError:
        return None


def main() -> int:
    state = {}
    if STATE_PATH.exists():
        try:
            state = json.loads(STATE_PATH.read_text())
        except Exception:
            state = {}

    now = time.time()
    workers = list_workers()
    new_state = {}
    actions = []

    for w in workers:
        pid, gid, etime_min = w["pid"], w["gid"], w["etime_min"]
        key = f"{pid}_{gid}"
        log_path = TRACKING_ROOT / gid / "run.log"

        frame = last_frame_in_log(log_path)
        log_mtime = log_path.stat().st_mtime if log_path.exists() else 0
        log_age = now - log_mtime if log_mtime else 9999

        prev = state.get(key, {})
        prev_frame = prev.get("frame")
        prev_time = prev.get("t", now)

        # Decide stuck
        stuck = False
        if etime_min >= ELAPSED_MIN_THRESHOLD:
            if frame is None and log_age > RUNLOG_STALE_SEC:
                stuck = True
                reason = f"no-runlog elapsed={etime_min}min log_age={log_age:.0f}s"
            elif frame is not None and prev_frame == frame and (now - prev_time) > RUNLOG_STALE_SEC:
                stuck = True
                reason = f"frame stuck at {frame} for {now - prev_time:.0f}s, elapsed={etime_min}min"
            elif frame is not None and log_age > RUNLOG_STALE_SEC * 2:
                stuck = True
                reason = f"runlog stale {log_age:.0f}s frame={frame} elapsed={etime_min}min"

        new_state[key] = {
            "frame": frame if frame is not None else prev_frame,
            "t": prev_time if frame == prev_frame else now,
        }

        if stuck:
            actions.append(f"KILL pid={pid} gid={gid} {reason}")
            try:
                os.kill(pid, signal.SIGTERM)
                time.sleep(10)
                try:
                    os.kill(pid, 0)
                    os.kill(pid, signal.SIGKILL)
                    actions.append(f"FORCEKILL pid={pid}")
                except ProcessLookupError:
                    pass
            except ProcessLookupError:
                actions.append(f"pid {pid} already gone")

            # rm -rf tracking dir for retry
            td = TRACKING_ROOT / gid
            if td.exists():
                try:
                    subprocess.check_call(["rm", "-rf", str(td)])
                    actions.append(f"PURGED {td}")
                except subprocess.CalledProcessError as e:
                    actions.append(f"PURGE FAILED {td}: {e}")

    STATE_PATH.write_text(json.dumps(new_state, indent=2))

    for a in actions:
        print(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
