"""Keep the seven footage-bridge lane workers running, without a long-lived parent.

WHY THIS EXISTS instead of bridge_supervisor.

bridge_supervisor is a long-lived process that owns its lane workers. On
2026-09-02 every instance of it died silently inside ``main()`` within minutes,
under four different launch methods (nohup, PowerShell Start-Process, Windows
Task Scheduler, and the agent harness background runner). It was not a crash: a
``BaseException`` handler wrapped around ``main()`` printed nothing, so no Python
exception was raised. It was not the Task Scheduler policy (MultipleInstances is
IgnoreNew, ExecutionTimeLimit PT72H), and it was not memory (3.83 GB free of
15.12 GB, largest python process 56 MB). The cause was never identified.

What WAS established, repeatedly and by observation: **the lane workers survive
their parent.** Every time a supervisor died it left its workers running as
orphans -- seven of them at a time, and once seventeen after repeated restarts.

So this keeper inverts the dependency. It is SHORT-LIVED: it starts whatever is
missing and exits immediately. There is no long-lived process to die, and a
scheduled task that re-runs it every few minutes is the whole recovery mechanism.
It is idempotent, so re-running it while everything is healthy does nothing --
which is what makes the accumulation bug impossible: the supervisor produced
duplicate workers because a blocked heartbeat made a healthy supervisor look
dead, and there is now no heartbeat to block.

Run:  python -m scripts.platformkit.bridge_keeper            (start what is missing)
      python -m scripts.platformkit.bridge_keeper --status   (report only)
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from scripts.platformkit.bridge_supervisor import DATA_DIR, LANES, LOG_DIR

# One expander pass per keeper run, at most, and only for a lane that is short.
# The supervisor used to do this inline with subprocess.run(timeout=1800), which
# blocked its poll loop behind a network call for as long as yt-dlp took.
REFILL_THRESHOLD = 6


def running_lane_names() -> set:
    """Lane names that already have a live worker, from the OS process table.

    footage_bridge has no ``--lane`` flag: bridge_supervisor.spawn identifies a
    lane purely by which queue files it passes. So the lane is recovered the same
    way, by looking for that lane's queue filenames on the command line.

    Matching is on the queue filename rather than the module name because a
    command line that merely MENTIONS the bridge -- this check itself, an
    operator's ssh, a grep -- would otherwise match and report a phantom worker.
    track_daemon.py:38-44 documents that exact trap for the pod daemon.
    """
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
        "Where-Object { $_.CommandLine -like '*platformkit.footage_bridge*' } | "
        "ForEach-Object { $_.CommandLine }"
    )
    try:
        result = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                                capture_output=True, text=True, timeout=120)
    except (subprocess.SubprocessError, OSError):
        return set()
    live = set()
    for line in result.stdout.splitlines():
        for name, queues in LANES:
            if any(queue in line for queue in queues):
                live.add(name)
    return live


def start_lane(name: str, queues: list, per_lane: int) -> int | None:
    """Launch one detached lane worker and return its pid.

    Detached deliberately: the caller exits straight afterwards and the worker
    must outlive it. Workers have been observed surviving their parent, which is
    the property this whole module is built on.
    """
    log = LOG_DIR / ("bridge_%s.log" % name)
    # Mirrors bridge_supervisor.spawn exactly, so a worker started here is
    # indistinguishable from one the supervisor would have started.
    command = [sys.executable, "-m", "scripts.platformkit.footage_bridge",
               "--limit", str(per_lane), "--forever", "--sleep", "45",
               "--decouple"]
    for queue in queues:
        command += ["--queue", str(DATA_DIR / queue)]
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        handle = log.open("a", encoding="utf-8")
        process = subprocess.Popen(
            command, stdout=handle, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        return process.pid
    except (subprocess.SubprocessError, OSError) as exc:
        print("lane %s failed to start: %s" % (name, exc))
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure footage bridge lanes are running")
    parser.add_argument("--per-lane", type=int, default=2)
    parser.add_argument("--status", action="store_true", help="report only, start nothing")
    args = parser.parse_args()

    live = running_lane_names()
    lanes = [(n, [q for q in qs if (DATA_DIR / q).is_file()]) for n, qs in LANES]
    lanes = [(n, qs) for n, qs in lanes if qs]

    missing = [(n, qs) for n, qs in lanes if n not in live]
    print("lanes=%d live=%d missing=%d" % (len(lanes), len(live), len(missing)))
    for name, _ in lanes:
        print("  %-18s %s" % (name, "UP" if name in live else "down"))
    if args.status:
        return 0 if not missing else 1

    for name, queues in missing:
        pid = start_lane(name, queues, args.per_lane)
        print("started %s pid=%s" % (name, pid))
    return 0


if __name__ == "__main__":
    sys.exit(main())
