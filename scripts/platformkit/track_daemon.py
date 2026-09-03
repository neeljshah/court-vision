"""Consume atomically staged videos with concurrent, pod-side tracking.

The bridge writes ``<sport>__<game_id>.mp4.part`` then atomically renames it.
Only plain ``.mp4`` files are complete uploads; never add size-stability polling.
Run: ``python -m scripts.platformkit.track_daemon --workers 12 --forever``.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from scripts.platformkit.track_daemon_done import (
    adjudicate,
    read_adjudicated,
    retain,
    tracking_rows,
    write_adjudicated,
)
from scripts.platformkit.track_daemon_ledger import corrupt_entry
from scripts.platformkit.track_daemon_sources import (
    claimable as _claimable_sources,
    reap_orphans as _reap_orphans,
    sibling_paths,
)
from scripts.platformkit.tracking.source_timebase import probe_source, stamp_tracking_csv

STAGE = Path("data/footage_bridge")
# Where a tracked video goes instead of being deleted. Re-staging one game is
# then `cp data/footage_corpus/<sport>__<game>.mp4 data/footage_bridge/`, which
# is the whole cost of re-measuring a fix against the corpus it targets.
CORPUS = Path("data/footage_corpus")
QUARANTINE = Path("data/footage_quarantine")
# Retained only for old external probes; completion never reads this report path.
REPORTS = Path("data/tracking_reports")
# A watchdog cannot use pgrep to tell whether this is alive: any command line
# mentioning the daemon (including the watchdog's own check, or an operator's
# ssh diagnostic) self-matches, so the check reports "up" precisely because it
# ran. The daemon publishes its pid instead and the watchdog uses kill -0.
PID_FILE = Path("/workspace/track_daemon.pid")
LEDGER = Path("data/tracking/track_daemon_ledger.jsonl")
TRACKING = Path("data/tracking")
# A completed upload is not automatically a video. Smallest real staged game
# measured 29.3 MB; this floor is two orders of magnitude below that.
MIN_VIDEO_BYTES = 1_000_000
# TEMPORARY: 12,000 s is roughly 1.37x the largest healthy 8,773 s pre-budget
# completion and will be replaced by a per-clip frame-derived budget once G56
# has denominator-bearing ledger rows.
JOB_TIMEOUT_SECONDS = 12_000
# The basketball path needs its own budget because its output is QUANTIZED.
# unified_pipeline checkpoints tracking_data.csv every _CHECKPOINT_INTERVAL
# (2000) frames and never flushes the residual, so a run_clip job is worth
# nothing at all until it crosses frame 2000 and worth ~2700 rows the moment it
# does. Killing one at frame 1999 yields the four rows from the frame-0
# checkpoint -- which is exactly the "completes, reports success, writes only
# frame 0" signature seen across 28 basketball jobs.
# MEASURED on the pod, four concurrent NCAA jobs at 2185s elapsed:
#   IB-_u4gW3ds   frame 2109  0.97 f/s  -> crossed 2000 at ~2062s, 2709 rows
#   tiUvyvWOCxo   frame 1794  0.82 f/s  -> crosses at ~2439s
#   sRtHQbywiTE   frame 1704  0.78 f/s  -> crosses at ~2564s
#   zqBCKovJCQU   frame 1209  0.55 f/s  -> crosses at ~3610s
# The slowest misses a 3600s deadline by ten seconds and loses everything. That
# is a cliff, not a budget. 5400s clears the measured spread with margin; a slot
# held 50% longer to return 2700 rows beats one freed on time to return four.
CLIP_JOB_TIMEOUT_SECONDS = 5400
SPORT_ADAPTER = {"tennis": "tennis", "soccer": "soccer", "npb": "baseball",
                 "kbo": "baseball", "mlb": "baseball", "baseball": "baseball"}
# These go through run_clip.py, which the adapter registry does not cover.
CLIP_SPORTS = {"wnba", "basketball", "ncaa_basketball", "nba"}
# A fivefold density move is operationally conspicuous without changing any
# harness bar. The marker is diagnostic only; completion remains G15b's verdict.
ROW_DENSITY_STEP_FACTOR = 5.0
ADJUDICATION_TIMEOUT_SECONDS = 1800
_UNSET = object()


def build_command(sport: str, video: Path, game_id: str) -> list:
    """The tracking command for a sport. Mirrors footage_bridge's routing."""
    if sport in CLIP_SPORTS:
        # 3000, not 18000. run_clip.py is the full production pipeline, not a
        # light adapter, and at this concurrency an 18000-frame job was measured
        # still running after 18216 seconds (5.06 hours). Every such job would
        # now simply hit JOB_TIMEOUT_SECONDS and yield NOTHING, burning a slot
        # for 45 minutes each. A shorter clip that actually finishes is worth
        # more than a long one that never does.
        # --data-dir is not optional. Without it run_clip defaults data_dir to
        # <repo>/data (scripts/run_clip.py:302) and writes data/tracking_data.csv
        # -- a path tracking_rows() never reads. Four completed 3000-frame jobs
        # were graded "thin rows=0" while their own logs printed run_clip's
        # success summary, and all four wrote the SAME repo-root file at once.
        # footage_cycle.py:142 has always passed it; this caller just omitted it.
        return [sys.executable, "scripts/run_clip.py", "--video", str(video),
                "--game-id", game_id, "--no-show", "--frames", "3000",
                "--data-dir", str(TRACKING / game_id)]
    adapter = SPORT_ADAPTER.get(sport, sport)
    return [sys.executable, "-m", "scripts.platformkit.adapter_run",
            adapter, str(video), game_id]


def job_timeout(sport: str) -> int:
    """Seconds this sport's job may hold a slot before it is killed."""
    return CLIP_JOB_TIMEOUT_SECONDS if sport in CLIP_SPORTS else JOB_TIMEOUT_SECONDS


def claimable(active: dict) -> list:
    """Return complete staged videos, one longest source per sibling group."""
    return _claimable_sources(STAGE, active, MIN_VIDEO_BYTES, QUARANTINE,
                              retain, _record_loudly, corrupt_entry)


def verdict(sport: str, game_id: str, video: Path, *, publish: bool = True) -> dict | None:
    """Publish the frozen-harness verdict for a nonempty emitted CSV."""
    return adjudicate(video, sport, game_id, TRACKING, publish=publish)


def _write_probe(directory: Path, name: str) -> None:
    """Write, fsync, read, and remove one small local durability probe."""
    probe = directory / (".%s_write_probe_%d" % (name, os.getpid()))
    data = b"track-daemon-write-probe\n"
    try:
        with probe.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if probe.read_bytes() != data:
            raise OSError("ledger write probe readback mismatch")
    except OSError as exc:
        raise RuntimeError("ledger write probe failed for %s: %s" %
                           (LEDGER.parent, exc)) from exc
    finally:
        try:
            probe.unlink(missing_ok=True)
        except OSError:
            pass


def _record(entry: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    _write_probe(LEDGER.parent, "track_daemon")
    try:
        with LEDGER.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise RuntimeError("ledger append failed for %s: %s" % (LEDGER, exc)) from exc


def _fresh_solve_summary(game_id: str) -> tuple[int | None, int | None]:
    """Read the adapter's per-frame solve counter without inferring from rows."""
    path = TRACKING / game_id / "frame_manifest.csv"
    try:
        with path.open(newline="", encoding="utf-8", errors="replace") as handle:
            manifest = list(csv.DictReader(handle))
    except (OSError, csv.Error):
        return None, None
    values = []
    for row in manifest:
        try:
            values.append(int(row.get("fresh_solve_count", "")))
        except (TypeError, ValueError):
            continue
    return len(manifest), max(values) if values else None


def _previous_sport_entry(sport: str) -> dict | None:
    """Return the immediately preceding readable ledger row for this sport."""
    try:
        lines = LEDGER.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict) and entry.get("sport") == sport:
            return entry
    return None


def _record_loudly(entry: dict) -> bool:
    """Append a ledger row, reporting a write failure instead of propagating it.

    G151 made a failed append RAISE, which is right: a silent quota failure once
    froze the ledger at exactly 427 rows for a 200-second watch with no error
    anywhere. But `_record` is called from `_finish` -- BEFORE `retain` moves the
    source to the corpus and before the log is unlinked -- and from `claimable`'s
    scan, both inside `tick`, which the main loop runs with no exception handler.
    So a PERSISTENT failure such as the quota exhaustion the guard exists for
    would kill the daemon mid-reap, drop every other in-flight job's bookkeeping
    with it, and leave the source in STAGE because `retain` sits downstream of
    the raise. The keeper restarts 60 seconds later with no backoff, re-claims
    the same video, and re-tracks it -- adding disk pressure on every cycle to
    the very volume that was already full.

    Loud in the log is loud enough. The verdict sidecar is already durable, so a
    lost row costs bookkeeping, not the game. `_record` keeps raising, so G151's
    contract and its test are unchanged; only these two callers absorb it.
    """
    try:
        _record(entry)
        return True
    except (RuntimeError, OSError) as exc:
        print("LEDGER APPEND FAILED for %s: %s -- row lost, job still finished"
              % (entry.get("game_id"), exc), flush=True)
        return False


def _step_change(previous: dict | None, entry: dict) -> dict | None:
    """Describe a material row-density move against the previous same-sport row."""
    if previous is None:
        return None
    try:
        prior_density = int(previous["rows"]) / int(previous["decoded_frames"])
        density = int(entry["rows"]) / int(entry["decoded_frames"])
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None
    if prior_density <= 0 or density <= 0:
        return None
    factor = max(density / prior_density, prior_density / density)
    if factor <= ROW_DENSITY_STEP_FACTOR:
        return None
    return {"previous_game_id": previous.get("game_id"),
            "direction": "increase" if density > prior_density else "decrease",
            "factor": round(factor, 3)}


def _prepare_adjudication(job: dict) -> None:
    """Do completion-side CSV preparation before its background verdict."""
    rows = tracking_rows(TRACKING, job["game_id"])
    source = job.get("source")
    if source:
        stamp_tracking_csv(TRACKING / job["game_id"] / "tracking_data.csv", source)
    if rows and job["sport"] in CLIP_SPORTS:
        from scripts.platformkit.adapter_run import BALL_TELEMETRY_AVAILABLE as _BALL
        from scripts.platformkit.tracking_schema import write_ball_telemetry_declaration
        write_ball_telemetry_declaration(TRACKING / job["game_id"] / "tracking_data.csv",
                                         job["sport"], _BALL[job["sport"]])


def _begin_adjudication(job: dict) -> None:
    """Run the unchanged verdict off the poll loop and retain the claim."""
    _prepare_adjudication(job)
    job["adjudication_started"] = time.monotonic()

    def run() -> None:
        try:
            graded = verdict(job["sport"], job["game_id"], job["video"], publish=False)
            if not job.get("adjudication_timed_out"):
                job["graded"] = graded
        except Exception as exc:
            if not job.get("adjudication_timed_out"):
                job["adjudication_error"] = exc

    thread = threading.Thread(target=run, name="adjudicate-%s" % job["game_id"], daemon=True)
    job["adjudication"] = thread
    thread.start()


def _finish(name: str, job: dict, timed_out: bool = False,
            adjudication_timed_out: bool = False, graded: object = _UNSET,
            prepared: bool = False) -> None:
    """Record a finished job; only a durable verdict is a done game."""
    rows = tracking_rows(TRACKING, job["game_id"])
    source = job.get("source")
    if not prepared:
        _prepare_adjudication(job)
    if timed_out or adjudication_timed_out:
        graded = None
    elif graded is _UNSET:
        graded = verdict(job["sport"], job["game_id"], job["video"], publish=False)
    if graded is not None:
        write_adjudicated(TRACKING, job["game_id"], graded)
    status = "timeout" if timed_out else "tracked" if graded is not None else "thin"
    # finished_at, because without it the ledger cannot be read. Diagnosing this
    # file meant guessing whether a "timeout at 2707s" predated the current
    # 3600s budget, and a stale entry is indistinguishable from a fresh one.
    # An append-only log whose rows carry no time is a log you have to date by
    # inference.
    finished = time.time()
    entry = {"game_id": job["game_id"], "sport": job["sport"],
              "status": status, "adjudicated": graded is not None, "rows": rows,
              # `status` remains the daemon lifecycle state for compatibility.
              # This additive terminal verdict makes a killed process
              # distinguishable from an honest empty or thin result by ledger
              # inspection alone.
              "verdict": ("TIMEOUT" if timed_out else
                          "ADJUDICATION_TIMEOUT" if adjudication_timed_out else None),
              "adjudication_timed_out": adjudication_timed_out,
              "passed": graded.get("passed") if graded else None,
              "failure_heads": (graded or {}).get("failure_heads", [])[:4],
              "failures": (graded or {}).get("failure_heads", [])[:4],
              "coverage_pct": (graded or {}).get("coverage_pct"),
              "harness_coverage_pct": (graded or {}).get("harness_coverage_pct"),
              "coordinate_space": (graded or {}).get("coordinate_space"),
              "rung": (graded or {}).get("rung"),
              "evaluated_at": (graded or {}).get("evaluated_at"),
              "seconds": int(finished - job["started"]),
              "finished_at": int(finished)}
    if source:
        entry.update(source_fps=source["source_fps"], source_height=source["source_height"],
                     source_duration=source["source_duration"],
                     source_variants=job.get("source_variants", []))
    if status != "tracked":
        # Without the tail, every failure looks identical in the ledger.
        try:
            output = job["log"].read_text(encoding="utf-8", errors="replace")
            entry["tail"] = output[-300:].replace("\n", " ")
        except OSError:
            entry["tail"] = "no log"
    manifest_frames, fresh_solves = _fresh_solve_summary(job["game_id"])
    entry.update(decoded_frames=(graded or {}).get("decoded_frames", manifest_frames),
                 evaluated_frames=(graded or {}).get("evaluated_frames"),
                 stride=(graded or {}).get("stride"),
                 source_resolution=(source or {}).get("source_resolution"),
                 fresh_solves=fresh_solves)
    entry["rows_per_decoded_frame_step_change"] = _step_change(
        _previous_sport_entry(job["sport"]), entry)
    _record_loudly(entry)
    print("%s %s %s rows=%d passed=%s %s"
          % (job["game_id"], job["sport"], status, rows, entry["passed"],
             ";".join(entry["failure_heads"])[:90]), flush=True)
    for video in job.get("retained_videos", [job["video"]]):
        retain(video, CORPUS, lambda message: print(message, flush=True))
    try:
        job["log"].unlink(missing_ok=True)
    except OSError as exc:
        print("cleanup failed %s: %s" % (job["log"], exc), flush=True)
def tick(active: dict, workers: int) -> None:
    """Reap finished jobs, then fill free slots. One pass, never blocking."""
    for name, job in list(active.items()):
        adjudication = job.get("adjudication")
        if adjudication is not None:
            if adjudication.is_alive():
                if time.monotonic() - job["adjudication_started"] <= ADJUDICATION_TIMEOUT_SECONDS:
                    continue
                job["adjudication_timed_out"] = True
                print("%s adjudication exceeded %ds -- recording timeout"
                      % (job["game_id"], ADJUDICATION_TIMEOUT_SECONDS), flush=True)
                _finish(name, active.pop(name), adjudication_timed_out=True, prepared=True)
                continue
            error = job.get("adjudication_error")
            if error is not None:
                print("adjudication failed %s: %s" % (job["game_id"], error), flush=True)
            _finish(name, active.pop(name), graded=job.get("graded"), prepared=True)
        elif job["proc"].poll() is not None:
            _begin_adjudication(job)
        elif time.time() - job["started"] > job_timeout(job["sport"]):
            print("%s exceeded %ds -- killing to free the slot"
                  % (job["game_id"], job_timeout(job["sport"])), flush=True)
            try:
                job["proc"].kill()
            except OSError as exc:
                print("kill failed %s: %s" % (job["game_id"], exc), flush=True)
            _finish(name, active.pop(name), timed_out=True)
    tracking_active = sum(1 for job in active.values() if "adjudication" not in job)
    for path, sport, game_id in claimable(active):
        if tracking_active >= workers:
            break
        # PASS and FAIL are both done once the frozen harness sidecar has been
        # atomically written after fsyncing a nonempty CSV.  A missing verdict
        # is never inferred from rows, so it is re-tracked rather than erased.
        if read_adjudicated(TRACKING, game_id) and (CORPUS / path.name).exists():
            print("%s already adjudicated, dropping staged duplicate"
                  % game_id, flush=True)
            for video in sibling_paths(STAGE, sport, game_id):
                retain(video, CORPUS, lambda message: print(message, flush=True))
            continue
        log_path = path.with_suffix(".log")
        try:
            handle = log_path.open("w", encoding="utf-8")
            proc = subprocess.Popen(build_command(sport, path, game_id),
                                    stdout=handle, stderr=subprocess.STDOUT)
        except OSError as exc:
            print("launch failed %s: %s" % (game_id, exc), flush=True)
            continue
        siblings = sibling_paths(STAGE, sport, game_id)
        active[path.name] = {"proc": proc, "video": path, "log": log_path,
                             "sport": sport, "game_id": game_id,
                             "started": time.time(), "source": probe_source(path),
                             "source_variants": [item.name for item in siblings if item != path],
                             "retained_videos": siblings}
        tracking_active += 1
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
    killed = _reap_orphans(subprocess.run, os.kill)
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
