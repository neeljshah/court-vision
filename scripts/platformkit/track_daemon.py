"""Track everything the footage bridge stages on the pod, many games at once.

Why this exists: the pod has 256 cores, 1TB of RAM and a 3090, but the bridge
ran tracking INLINE inside each download worker (download -> scp -> track ->
next). Concurrency was therefore capped at the lane count, and because all
lanes start by downloading it sat at ONE tracking process with the GPU at 11%.

A single adapter run is video-decode bound: about one core and ~350 MiB of
VRAM. Nothing about this box justifies running one at a time. This daemon is
the consumer half of the split -- workers now only download and upload.

The upload race is closed by naming, not by guessing: the bridge scp's to
<sport>__<game_id>.mp4.part and renames atomically, so any file this daemon
sees with a plain .mp4 suffix is complete. Never add size-stability polling
here; that is the heuristic that once handed a half-transferred video to the
tracker.

Run on the pod:
    python -m scripts.platformkit.track_daemon --workers 12 --forever
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

STAGE = Path("data/footage_bridge")
REPORTS = Path("data/tracking_reports")
# A watchdog cannot use pgrep to tell whether this is alive: any command line
# mentioning the daemon (including the watchdog's own check, or an operator's
# ssh diagnostic) self-matches, so the check reports "up" precisely because it
# ran. The daemon publishes its pid instead and the watchdog uses kill -0.
PID_FILE = Path("/workspace/track_daemon.pid")
LEDGER = Path("data/tracking/track_daemon_ledger.jsonl")
TRACKING = Path("data/tracking")
# Matches footage_bridge: a real tracked game has thousands of rows, and a
# non-empty CSV is not evidence of anything.
MIN_TRACKING_ROWS = 500
# No single game may hold a worker slot forever. Sport adapters finish in 1-4
# minutes (that was BEFORE concurrency was raised); the basketball path
# (scripts/run_clip.py) is the full production
# pipeline and was measured at 18216 seconds -- 5.06 HOURS -- still running.
# Two of those pinned two slots while 22 wnba/ncaa games queued behind them and
# jammed the stage against the bridge's backlog cap. A slot freed after 45
# minutes is worth far more than one game tracked in five hours.
JOB_TIMEOUT_SECONDS = 3600
SPORT_ADAPTER = {"tennis": "tennis", "soccer": "soccer", "npb": "baseball",
                 "kbo": "baseball", "mlb": "baseball", "baseball": "baseball"}
# These go through run_clip.py, which the adapter registry does not cover.
CLIP_SPORTS = {"wnba", "basketball", "ncaa_basketball", "nba"}


def parse_name(path: Path) -> tuple:
    """Split <sport>__<game_id>.mp4. Returns (sport, game_id) or (None, None)."""
    stem = path.stem
    if "__" not in stem:
        return None, None
    sport, _, game_id = stem.partition("__")
    if not sport or not game_id:
        return None, None
    return sport, game_id


def tracking_rows(game_id: str) -> int:
    """Row count of a tracked game, excluding the header. 0 when absent."""
    csv_path = TRACKING / game_id / "tracking_data.csv"
    try:
        with csv_path.open("r", encoding="utf-8", errors="replace") as handle:
            return max(0, sum(1 for _ in handle) - 1)
    except OSError:
        return 0


def build_command(sport: str, video: Path, game_id: str) -> list:
    """The tracking command for a sport. Mirrors footage_bridge's routing."""
    if sport in CLIP_SPORTS:
        # 3000, not 18000. run_clip.py is the full production pipeline, not a
        # light adapter, and at this concurrency an 18000-frame job was measured
        # still running after 18216 seconds (5.06 hours). Every such job would
        # now simply hit JOB_TIMEOUT_SECONDS and yield NOTHING, burning a slot
        # for 45 minutes each. A shorter clip that actually finishes is worth
        # more than a long one that never does.
        return [sys.executable, "scripts/run_clip.py", "--video", str(video),
                "--game-id", game_id, "--no-show", "--frames", "3000"]
    adapter = SPORT_ADAPTER.get(sport, sport)
    return [sys.executable, "-m", "scripts.platformkit.adapter_run",
            adapter, str(video), game_id]


def claimable(active: dict) -> list:
    """Complete staged videos not already being tracked.

    `.part` files are in-flight uploads and are invisible to glob('*.mp4'),
    which is the whole point of the atomic-rename protocol.
    """
    ready = []
    for path in sorted(STAGE.glob("*.mp4")):
        if path.name in active:
            continue
        sport, game_id = parse_name(path)
        if sport is None:
            continue
        ready.append((path, sport, game_id))
    return ready


def verdict(sport: str, game_id: str) -> dict:
    """Harness verdict for a finished game: {"passed": bool, "failures": [...]}.

    Row count alone is NOT quality. The baseball adapter can now emit 4000+ rows
    whose coordinates are untrustworthy (oob 0.65), which by row count is
    indistinguishable from a good 38,000-row tennis game. The ledger has to
    carry the verdict or "tracked" silently comes to mean "big".

    adapter_run writes this report itself; run_clip.py does not, so the
    basketball family is graded here instead of going unscored.
    """
    harness_sport = "basketball" if sport in CLIP_SPORTS else SPORT_ADAPTER.get(sport, sport)
    report_path = REPORTS / harness_sport / ("%s.json" % game_id)
    csv_path = TRACKING / game_id / "tracking_data.csv"
    # Only trust a report NEWER than the tracking output it claims to describe.
    # A re-tracked game keeps its old report when adapter_run fails to rewrite
    # it, and this returned an hour-stale verdict of "empty" for a game that had
    # just produced 18,736 rows -- corrupting the one signal the ledger carries.
    try:
        report_mtime = report_path.stat().st_mtime
        try:
            fresh = report_mtime >= csv_path.stat().st_mtime
        except OSError:
            fresh = True  # no tracking output to be stale against
        if fresh:
            return json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    try:
        import pandas as pd

        from scripts.platformkit.tracking_harness import evaluate

        report = evaluate(pd.read_csv(TRACKING / game_id / "tracking_data.csv"),
                          harness_sport)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report.to_json(), encoding="utf-8")
        return json.loads(report.to_json())
    except Exception as exc:  # grading must never kill the daemon
        return {"passed": None, "failures": ["ungraded: %s" % str(exc)[:120]]}


def _record(entry: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def _finish(name: str, job: dict, timed_out: bool = False) -> None:
    """Grade one finished job, record it, and always reclaim the disk.

    A timed-out job is recorded as "timeout" even when its partial CSV happens
    to clear the row bar: half a game is not a tracked game, and calling it one
    would put untrustworthy partial output into the usable corpus.
    """
    rows = tracking_rows(job["game_id"])
    status = "timeout" if timed_out else (
        "tracked" if rows >= MIN_TRACKING_ROWS else "thin")
    graded = verdict(job["sport"], job["game_id"]) if rows else {}
    entry = {"game_id": job["game_id"], "sport": job["sport"],
             "status": status, "rows": rows,
             "passed": graded.get("passed"),
             "failures": (graded.get("failures") or [])[:4],
             "seconds": int(time.time() - job["started"])}
    if status == "thin":
        # Without the tail, every failure looks identical in the ledger.
        try:
            output = job["log"].read_text(encoding="utf-8", errors="replace")
            entry["tail"] = output[-300:].replace("\n", " ")
        except OSError:
            entry["tail"] = "no log"
    _record(entry)
    print("%s %s %s rows=%d passed=%s %s"
          % (job["game_id"], job["sport"], status, rows, entry["passed"],
             ";".join(entry["failures"])[:90]), flush=True)
    for leftover in (job["video"], job["log"]):
        try:
            leftover.unlink(missing_ok=True)
        except OSError as exc:
            print("cleanup failed %s: %s" % (leftover, exc), flush=True)


def tick(active: dict, workers: int) -> None:
    """Reap finished jobs, then fill free slots. One pass, never blocking."""
    for name, job in list(active.items()):
        if job["proc"].poll() is not None:
            _finish(name, active.pop(name))
        elif time.time() - job["started"] > JOB_TIMEOUT_SECONDS:
            print("%s exceeded %ds -- killing to free the slot"
                  % (job["game_id"], JOB_TIMEOUT_SECONDS), flush=True)
            try:
                job["proc"].kill()
            except OSError as exc:
                print("kill failed %s: %s" % (job["game_id"], exc), flush=True)
            _finish(name, active.pop(name), timed_out=True)
    for path, sport, game_id in claimable(active):
        if len(active) >= workers:
            break
        if tracking_rows(game_id) >= MIN_TRACKING_ROWS:
            print("%s already tracked, dropping stage copy" % game_id, flush=True)
            path.unlink(missing_ok=True)
            continue
        log_path = path.with_suffix(".log")
        try:
            handle = log_path.open("w", encoding="utf-8")
            proc = subprocess.Popen(build_command(sport, path, game_id),
                                    stdout=handle, stderr=subprocess.STDOUT)
        except OSError as exc:
            print("launch failed %s: %s" % (game_id, exc), flush=True)
            continue
        active[path.name] = {"proc": proc, "video": path, "log": log_path,
                             "sport": sport, "game_id": game_id,
                             "started": time.time()}
        print("tracking %s (%s), %d active" % (game_id, sport, len(active)),
              flush=True)


def reap_orphans() -> int:
    """Kill tracking jobs left behind by a previous daemon. Returns the count.

    When a daemon dies its children are re-parented to init and keep running,
    unowned. A fresh daemon then re-claims the same staged videos, so TWO
    processes write one CSV. This happened twice tonight and had to be cleaned
    up by hand both times, once at 46 jobs against a 24 cap.

    adapter_run and run_clip are only ever daemon children, so a parent of 1
    means orphaned -- no live daemon owns it.
    """
    try:
        listing = subprocess.run(["ps", "-eo", "ppid,pid,args"],
                                 capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return 0
    killed = 0
    for line in listing.splitlines():
        fields = line.split(None, 2)
        if len(fields) < 3 or fields[0] != "1":
            continue
        if "adapter_run" not in fields[2] and "run_clip" not in fields[2]:
            continue
        try:
            os.kill(int(fields[1]), 9)
            killed += 1
        except (OSError, ValueError):
            pass
    if killed:
        print("reaped %d orphaned tracking jobs from a previous daemon" % killed,
              flush=True)
    return killed


def main(argv: list) -> int:
    parser = argparse.ArgumentParser()
    # 10, not 24. MEASURED over 210 jobs at 23-way concurrency: p50 972s,
    # p90 4165s, max 8773s, with 79 jobs past 43 minutes -- while the GPU sat at
    # 3-11% utilization. Low utilization with slow jobs is contention on a
    # serialized resource (one 3090, 23 CUDA contexts), not saturation, so
    # adding workers was buying queueing delay rather than throughput.
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--forever", action="store_true")
    parser.add_argument("--interval", type=int, default=20)
    args = parser.parse_args(argv[1:])

    STAGE.mkdir(parents=True, exist_ok=True)
    reap_orphans()
    try:
        PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    except OSError as exc:
        print("could not publish pid: %s" % exc, flush=True)
    active: dict = {}
    while True:
        tick(active, args.workers)
        if not args.forever and not active:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
