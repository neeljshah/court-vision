"""Keep the footage bridges running all night: many games at once, queues never dry.

One supervisor process owns everything so there is a single thing to keep alive:
  * N bridge workers in parallel, one per sport lane, each pulling its own queues
    (lanes never share a queue, so two workers cannot claim the same game).
  * Automatic restart of any worker that exits for any reason.
  * Queue refill: when a lane's queues drop below REFILL_THRESHOLD untracked
    items, the expander is run for that sport so the lane never runs dry.

Run: python -m scripts.platformkit.bridge_supervisor
     python -m scripts.platformkit.bridge_supervisor --per-lane 3
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from scripts.platformkit.footage_bridge import MIN_TRACKING_ROWS, tracked_row_counts

DATA_DIR = Path("data")
LOG_DIR = Path("logs")
STATUS_PATH = Path("data/tracking/bridge_supervisor_status.json")
PID_PATH = Path("data/tracking/bridge_supervisor.pid")
# Each lane is (name, [queue files]). Lanes are disjoint so workers never race.
LANES = [
    ("baseball", ["footage_queue_kbo.json", "footage_queue_npb.json"]),
    ("wnba", ["footage_queue_wnba.json"]),
    ("tennis", ["footage_queue_tennis.json"]),
    ("soccer", ["footage_queue_soccer.json"]),
    ("football", ["footage_queue_football.json"]),
    ("mlb", ["footage_queue_mlb.json"]),
    ("ncaa_basketball", ["footage_queue_ncaa_basketball.json"]),
]
# nhl, cricket, handball and volleyball were lanes here until 2026-09-01. They
# have no adapter in domains/ and no entry in adapter_run.ADAPTERS or
# track_daemon.CLIP_SPORTS, so every game they fetched was uploaded to the pod
# and then failed with "unknown sport". Their queue files are kept on disk; a
# lane is one line to restore once its adapter exists. test_bridge_supervisor
# now fails if a lane is ever added back without one.
REFILL_THRESHOLD = 6
POLL_SECONDS = 90
# Sports queue_expander.SOURCES can actually discover full games for. Its
# MIN_DURATION_SECONDS floors already reject clips and highlight reels.
REFILLABLE = ("tennis", "wnba", "npb", "kbo", "soccer", "football", "mlb",
              "nhl", "ncaa_basketball", "cricket", "handball", "volleyball")


def untracked_count(queue_path: Path, known: dict) -> int:
    """How many queue entries still have no usable tracking output."""
    try:
        items = json.loads(queue_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    return sum(1 for item in items
               if known.get(item.get("game_id"), 0) < MIN_TRACKING_ROWS)


def spawn(lane: str, queues: list, per_lane: int) -> subprocess.Popen:
    """Start one bridge worker for a lane, logging to its own file."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    # --decouple: the worker uploads and moves on; scripts.platformkit.track_daemon
    # tracks on the pod. Tracking inline here capped pod concurrency at the lane
    # count and in practice held it at one process on a 256-core box.
    command = [sys.executable, "-m", "scripts.platformkit.footage_bridge",
               "--limit", str(per_lane), "--forever", "--sleep", "45",
               "--decouple"]
    for queue in queues:
        command += ["--queue", str(DATA_DIR / queue)]
    handle = (LOG_DIR / ("bridge_%s.log" % lane)).open("a", encoding="utf-8")
    return subprocess.Popen(command, stdout=handle, stderr=subprocess.STDOUT)


def refill(sport: str) -> None:
    """Top a sport queue back up. Best effort: a failed refill must not stop us.

    The expander only has sources for REFILLABLE sports. For anything else we
    say so rather than running a no-op that looks like a successful refill.
    """
    if sport not in REFILLABLE:
        print("lane %s has no expander source -- queue cannot self-refill, "
              "add a source to queue_expander.SOURCES" % sport, flush=True)
        return
    try:
        # Flag is --sports (plural); --sport is silently rejected and the queue
        # would never actually refill.
        result = subprocess.run(
            [sys.executable, "-m", "scripts.platformkit.queue_expander",
             "--sports", sport, "--target", "60"],
            timeout=1800, capture_output=True, text=True)
        if result.returncode != 0:
            print("refill %s exit %d: %s"
                  % (sport, result.returncode, (result.stderr or "")[-200:]), flush=True)
    except (subprocess.SubprocessError, OSError) as exc:
        print("refill %s failed: %s" % (sport, exc), flush=True)


def active_lanes() -> list:
    """Lanes whose queue files actually exist."""
    lanes = []
    for name, queues in LANES:
        present = [q for q in queues if (DATA_DIR / q).is_file()]
        if present:
            lanes.append((name, present))
    return lanes


def write_pid(pid_path: Path = PID_PATH) -> None:
    """Publish this supervisor's pid for the liveness check."""
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text("%d\n" % os.getpid(), encoding="ascii")


def remove_own_pid(pid_path: Path = PID_PATH) -> None:
    """Remove the pid file only when it still names this process."""
    try:
        if pid_path.read_text(encoding="ascii").strip() == str(os.getpid()):
            pid_path.unlink()
    except OSError:
        pass


def write_status(status: dict, status_path: Path = STATUS_PATH) -> None:
    """Atomically publish a timestamped supervisor snapshot."""
    status["written_at"] = datetime.now(timezone.utc).isoformat()
    try:
        status_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = status_path.with_suffix(status_path.suffix + ".tmp")
        temporary.write_text(json.dumps(status, indent=2), encoding="utf-8")
        temporary.replace(status_path)
    except OSError:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Keep footage bridges alive")
    parser.add_argument("--per-lane", type=int, default=3,
                        help="games per queue per pass, per lane")
    parser.add_argument("--once", action="store_true", help="one poll then exit")
    args = parser.parse_args()

    workers: dict = {}
    warned_unrefillable: set = set()
    write_pid()
    try:
        while True:
            # Recomputed every poll: a queue created later (by a refill, or by hand)
            # must get a worker without restarting the supervisor.
            lanes = active_lanes()
            if not lanes:
                print("no queue files yet -- waiting", flush=True)
            try:
                known = tracked_row_counts()
            except Exception as exc:
                known = {}
                print("row-count probe failed: %s" % exc, flush=True)
            status = {"tracked_games": sum(1 for v in known.values()
                                           if v >= MIN_TRACKING_ROWS), "lanes": {}}
            for name, queues in lanes:
                worker = workers.get(name)
                if worker is None:
                    print("lane %s starting" % name, flush=True)
                    workers[name] = spawn(name, queues, args.per_lane)
                elif worker.poll() is not None:
                    print("lane %s died (exit %s) -- restarting"
                          % (name, worker.returncode), flush=True)
                    workers[name] = spawn(name, queues, args.per_lane)
                remaining = sum(untracked_count(DATA_DIR / q, known) for q in queues)
                if remaining < REFILL_THRESHOLD:
                    sports = [q.replace("footage_queue_", "").replace(".json", "")
                              for q in queues]
                    if any(sport in REFILLABLE for sport in sports):
                        print("lane %s down to %d untracked -- refilling"
                              % (name, remaining), flush=True)
                        for sport in sports:
                            refill(sport)
                    elif name not in warned_unrefillable:
                        # Warn ONCE. Repeating this every poll buries real failures
                        # in a log a human only skims in the morning.
                        warned_unrefillable.add(name)
                        print("lane %s has no expander source and cannot self-refill "
                              "-- add one to queue_expander.SOURCES" % name, flush=True)
                status["lanes"][name] = {"untracked": remaining,
                                         "alive": workers[name].poll() is None}
            write_status(status)
            if args.once:
                return 0
            time.sleep(POLL_SECONDS)
    finally:
        remove_own_pid()


if __name__ == "__main__":
    sys.exit(main())
