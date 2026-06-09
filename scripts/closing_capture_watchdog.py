"""closing_capture_watchdog.py - lightweight guardian for capture_closing_lines.py.

Why this exists
---------------
``capture_closing_lines.py`` is a single long-sleep Python process. If that PID
dies (OOM, accidental kill, transient OS hiccup, machine sleep without
WakeToRun on the schtask), we silently lose the closing-line snapshot and
Gate-1 CLV stays blocked another day. The watchdog adds a second, much lighter
process that polls a heartbeat file and respawns the capture daemon if it
appears dead.

Detection logic (every --interval seconds, default 300)
-------------------------------------------------------
1. Read ``data/cache/closing_capture_heartbeat.txt``.
2. If file missing OR last-stamp older than --stale-after seconds (default 600)
   AND we are still BEFORE the configured capture deadline (default
   ``--deadline-utc 2026-05-27T00:34:00``) AND no other capture_closing_lines
   process is currently running --> respawn it with the same scheduled args.
3. Otherwise just log and loop.

We deliberately do NOT kill a healthy process: we only spawn when no live
capture PID is detected. This prevents thrashing if the heartbeat write lags
during a long scrape.

CLI
---
Typical (matches the live daemon's schedule for WCF G5):
    python scripts/closing_capture_watchdog.py \
        --game-id 0042500315 \
        --at-utc 2026-05-27T00:30:00 \
        --then-at-utc 2026-05-27T00:34:00 \
        --deadline-utc 2026-05-27T00:34:00

Run in the background:
    Start-Process -WindowStyle Hidden python -ArgumentList @(
        "-u", "scripts/closing_capture_watchdog.py",
        "--game-id", "0042500315",
        "--at-utc", "2026-05-27T00:30:00",
        "--then-at-utc", "2026-05-27T00:34:00",
        "--deadline-utc", "2026-05-27T00:34:00"
    )
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_HEARTBEAT_PATH = _ROOT / "data" / "cache" / "closing_capture_heartbeat.txt"
_WATCHDOG_LOG = _ROOT / "data" / "cache" / "closing_capture_watchdog.log"
_CAPTURE_SCRIPT = _HERE / "capture_closing_lines.py"


def _log(msg: str) -> None:
    line = f"[{datetime.now(timezone.utc).isoformat()}] {msg}"
    print(line, flush=True)
    try:
        _WATCHDOG_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _WATCHDOG_LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:  # noqa: BLE001
        pass


def _heartbeat_age_seconds() -> Optional[float]:
    """Return how many seconds old the heartbeat is, or None if missing /
    unreadable. We parse the timestamp from the file body (not mtime) because
    file mtime on Windows can lag a few seconds after write."""
    if not _HEARTBEAT_PATH.exists():
        return None
    try:
        text = _HEARTBEAT_PATH.read_text(encoding="utf-8").strip()
        if not text:
            return None
        ts_str = text.split("\t", 1)[0]
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds()
    except Exception as exc:  # noqa: BLE001
        _log(f"heartbeat parse failed: {exc}")
        return None


def _capture_pids() -> List[int]:
    """Return PIDs of any running python.exe whose command-line references
    capture_closing_lines.py. Uses WMIC (works on Win10+ without extras).
    """
    pids: List[int] = []
    try:
        # WMIC is deprecated but still on Win10/11; falls back to powershell if missing.
        out = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "Get-WmiObject Win32_Process -Filter \"Name='python.exe'\" "
                    "| Where-Object { $_.CommandLine -like '*capture_closing_lines.py*' } "
                    "| Select-Object -ExpandProperty ProcessId"
                ),
            ],
            stderr=subprocess.STDOUT,
            timeout=20,
        ).decode(errors="ignore")
        for line in out.splitlines():
            line = line.strip()
            if line.isdigit():
                pids.append(int(line))
    except Exception as exc:  # noqa: BLE001
        _log(f"pid lookup failed: {exc}")
    return pids


def _spawn_capture(game_id: str, at_utc: str, then_at_utc: Optional[str]) -> Optional[int]:
    """Spawn a new capture_closing_lines.py daemon detached from this process.
    Returns the new PID (or None on failure)."""
    py = sys.executable or "python"
    cmd = [py, "-u", str(_CAPTURE_SCRIPT), "--game-id", game_id, "--at-utc", at_utc]
    if then_at_utc:
        cmd += ["--then-at-utc", then_at_utc]
    try:
        # DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP so it survives this watchdog.
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        creationflags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        proc = subprocess.Popen(
            cmd,
            cwd=str(_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            close_fds=True,
            creationflags=creationflags,
        )
        _log(f"respawned capture daemon: pid={proc.pid} cmd={' '.join(cmd)}")
        return proc.pid
    except Exception as exc:  # noqa: BLE001
        _log(f"spawn failed: {exc}")
        return None


def _parse_utc(s: str) -> datetime:
    s = s.strip().rstrip("Z")
    fmts = ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")
    for f in fmts:
        try:
            return datetime.strptime(s, f).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"unparseable utc value: {s!r}")


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-id", required=True)
    ap.add_argument("--at-utc", required=True,
                    help="First capture time (matches the live daemon's --at-utc)")
    ap.add_argument("--then-at-utc", default=None,
                    help="Optional second capture time")
    ap.add_argument("--deadline-utc", required=True,
                    help="After this UTC time, stop watching (the capture has either "
                         "fired or it's too late to matter)")
    ap.add_argument("--interval", type=int, default=300,
                    help="Poll interval seconds (default 300 = 5 min)")
    ap.add_argument("--stale-after", type=int, default=600,
                    help="Heartbeat staleness threshold in seconds (default 600 = 10 min)")
    args = ap.parse_args(argv)

    deadline = _parse_utc(args.deadline_utc)
    # Add a small grace window past the deadline so we keep watching during the
    # actual scrape (which can run 30-60s).
    hard_stop = deadline.timestamp() + 300

    _log(f"watchdog starting: pid={os.getpid()} game={args.game_id} "
         f"at_utc={args.at_utc} then={args.then_at_utc} deadline={args.deadline_utc} "
         f"interval={args.interval}s stale_after={args.stale_after}s")

    while True:
        now_utc = datetime.now(timezone.utc)
        if now_utc.timestamp() > hard_stop:
            _log("past deadline + 5min grace window — watchdog exiting cleanly.")
            return 0

        pids = _capture_pids()
        age = _heartbeat_age_seconds()
        if pids:
            _log(f"healthy: capture pids={pids} heartbeat_age={age}")
        else:
            if age is None:
                _log("ALERT: no capture process AND no heartbeat — respawning.")
                _spawn_capture(args.game_id, args.at_utc, args.then_at_utc)
            elif age > args.stale_after:
                _log(f"ALERT: no capture process AND heartbeat stale ({age:.0f}s > "
                     f"{args.stale_after}s) — respawning.")
                _spawn_capture(args.game_id, args.at_utc, args.then_at_utc)
            else:
                # Heartbeat fresh but no PID found -- maybe the WMIC query lost it.
                # Be conservative: log and re-check next tick.
                _log(f"WARN: no capture pid found but heartbeat age={age:.0f}s "
                     f"is still fresh — not respawning yet.")

        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
