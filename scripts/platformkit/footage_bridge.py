"""Download footage on the local (residential) IP, track it on the pod, delete both copies.

Why this exists: YouTube blocks the pod datacenter IP ("Sign in to confirm
you are not a bot") for every league, while the same cookies work from the local
machine. The pod has the GPU. So the local box is used ONLY as a network hop:
download -> scp -> track on pod -> delete local AND remote copies immediately.
Neither disk ever accumulates video.

Two landmines this module is built around:
  1. Remote staging lives in data/footage_bridge/, NOT data/footage/. The pod
     track_staged loop scans data/footage/ and deletes what it finds, which
     raced this bridge and deleted a video mid-transfer ("video not found").
     A private directory means there is exactly one writer per file.
  2. Success is a row-count check, never `test -s`. A 103-row CSV is non-empty
     and still useless; the non-empty test reported it as "tracked".

Run: python -m scripts.platformkit.footage_bridge --queue data/footage_queue_tennis.json --limit 3
     python -m scripts.platformkit.footage_bridge --all --forever
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from scripts.platformkit import footage_content_gate

from scripts.platformkit.section_fallback import (
    MIN_SECTION_HEIGHT,
    cut_full_download,
    video_height,
)

POD = ["-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=30", "-p", "40048",
       "root@213.192.2.83"]
POD_HOST = "root@213.192.2.83"
POD_ROOT = "/workspace/nba-ai-system"
REMOTE_STAGE = POD_ROOT + "/data/footage_bridge"
LOCAL_STAGE = Path("data/videos/bridge")
COOKIES = Path("data/videos/youtube_cookies.txt")
LEDGER = Path("data/tracking/footage_bridge_ledger.jsonl")
# ONE reference clip per sport is kept permanently so tracking work can be
# re-measured. Deleting every copy is right for disk, but it left the
# homography investigation unable to produce a before/after because no footage
# survived. Gitignored under data/, capped at one file per sport.
REFERENCE_DIR = Path("data/videos/reference")
TRACKING_REPORT_DIR = Path("data/tracking_reports")
TRACKING_DIR = Path("data/tracking")
# yt-dlp writes per-stream files like game.f137.mp4 (video-only) and
# game.f299.mp4 (audio-only) before merging them. If the merge fails these
# survive, and picking the largest would ship a video-only or audio-only
# stream to the tracker as if it were the game.
_FORMAT_PART = re.compile(r"\.f\d{2,4}\.")
# A real tracked game has thousands of rows. Anything under this is a failed
# detection pass wearing a successful exit code.
MIN_TRACKING_ROWS = 500
# The pod tracks ~24 games at once. Downloading past that just fills pod disk
# and, locally, piles up yt-dlp processes -- this box has crashed twice from
# concurrent unbounded load. Since section downloads made fetching ~12x cheaper,
# downloads now comfortably outrun tracking, so the producer needs backpressure.
MAX_POD_BACKLOG = 24
SPORT_ADAPTER = {"tennis": "tennis", "soccer": "soccer", "npb": "baseball",
                 "kbo": "baseball", "mlb": "baseball", "baseball": "baseball"}
# yt-dlp rungs, cheapest first. The pod cannot use any of them; the local IP can.
# 720p FIRST, deliberately. Upload to the pod was measured at 88.6 Mbps
# aggregate and is the pipeline ceiling -- the GPU sits at 11%. A 1080p game is
# ~850 MB and a 720p one is roughly half that, so this doubles games/hour.
# CORRECTION 2026-09-01: an earlier note here said the detector-resolution arm
# "came back a NULL -- recall is gated by homography eligibility, not by
# pixels". A controlled re-run refutes that. Same match, same section offset,
# same 36 seconds, differing only in resolution
# (docs/evidence/tracking/tennis_resolution_controlled_2026-09-01.md):
#   frames reaching the court's five-line gate   5.0% -> 18.7%
#   severe line under-detection (1-2 clusters)  36.7% ->  8.5%
# Resolution matters a great deal to LINE DETECTION. It does not by itself fix
# registration -- the bottleneck moves to cluster selection -- but "pixels do
# not matter here" is not true and should not be repeated.
#
# THE FIRST RUNG EXISTS BECAUSE OF THAT. Section downloads force
# player_client=web (see SECTION_CLIENT), and that client exposes exactly ONE
# non-storyboard format: itag 18, 640x360. So every section download has been
# 360p. With --cookies, YouTube offers HLS formats 300 (1280x720) and 301
# (1920x1080), and a SECTION of an HLS stream only fetches the segments it
# needs: measured at 5.58 MiB in 2 seconds for a 20s slice. The old warning
# that "cookies get HLS, ~1100 fragments, very slow" was about fetching a WHOLE
# video that way; it does not apply to a section.
FORMAT_RUNGS = [
    "b[height<=1080][height>=720]",
    "bv*[height<=720][vcodec^=avc1]+ba/b[height<=720]",
    "b[height<=720]",
    "bv*[height<=1080][vcodec^=avc1]+ba/b[height<=1080]",
]


def _ssh(command: str, timeout: int = 7200) -> subprocess.CompletedProcess:
    """Run one pod command. A hung ssh returns a failure, it never raises.

    This runs unattended overnight: an uncaught TimeoutExpired here would kill
    the whole bridge and leave the GPU idle until a human noticed.
    """
    try:
        return subprocess.run(["ssh", *POD, command], capture_output=True,
                              text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return subprocess.CompletedProcess(command, 255, stdout="",
                                           stderr="ssh failed: %s" % exc)


def tracking_rows(game_id: str) -> int:
    """Row count of the pod-side tracking CSV, or 0 when absent."""
    probe = _ssh("wc -l < %s/data/tracking/%s/tracking_data.csv 2>/dev/null || echo 0"
                 % (POD_ROOT, game_id), timeout=120)
    try:
        return int((probe.stdout or "0").strip().split()[0])
    except (ValueError, IndexError):
        return 0


def tracked_row_counts() -> dict:
    """Row count for every pod-side tracking CSV in ONE ssh round trip.

    Probing per item cost one ssh each: a 22-item queue spent ~40s of round
    trips before the first download, every pass, forever.
    """
    probe = _ssh("cd %s/data/tracking 2>/dev/null && wc -l */tracking_data.csv "
                 "2>/dev/null || true" % POD_ROOT, timeout=300)
    counts = {}
    for line in (probe.stdout or "").splitlines():
        parts = line.split()
        if len(parts) != 2 or "/" not in parts[1]:
            continue  # skips the "total" line and any stray output
        try:
            counts[parts[1].split("/")[0]] = int(parts[0])
        except ValueError:
            continue
    return counts


def _error_tail(stderr: str, stdout: str = "") -> str:
    """Extract the line that actually says what went wrong.

    yt-dlp opens stderr with a Python-version deprecation warning. Naively
    keeping the last N characters returned that warning for every failure and
    hid the real cause, which made every lane failure look identical.
    """
    text = (stderr or "") + "\n" + (stdout or "")
    errors = [line.strip() for line in text.splitlines()
              if "ERROR" in line or "Unsupported" in line or "Unable" in line]
    if errors:
        return errors[-1][:220]
    meaningful = [line.strip() for line in text.splitlines()
                  if line.strip() and "Deprecated Feature" not in line
                  and "update to Python" not in line]
    return (meaningful[-1][:220] if meaningful else "no diagnostic output")


def _is_direct_media(url: str) -> bool:
    """True for a plain media file URL rather than a site yt-dlp must extract."""
    path = str(url or "").split("?")[0].lower()
    return path.endswith((".mp4", ".m4v", ".mov", ".mkv", ".webm", ".ts"))


def _resolve_download(destination: Path):
    """Find what yt-dlp actually wrote; it falls back to .mkv/.webm on merge failure."""
    if destination.exists():
        return destination
    produced = sorted(
        (path for path in destination.parent.glob(destination.stem + "*")
         if path.is_file() and not path.name.endswith((".part", ".ytdl"))
         and "-Frag" not in path.name and not _FORMAT_PART.search(path.name)),
        key=lambda path: path.stat().st_size, reverse=True)
    return produced[0] if produced else None


# We track at most 30,000 frames (~16 min at 30fps), but were downloading and
# uploading the whole 85-minute game to do it. Measured on a real handball
# broadcast: the full 720p game is ~1.17 GB, while the 16-minute slice we
# actually use is 69.9 MB fetched in 18 seconds -- about 12x less data on a
# link whose 88.6 Mbps upload was the pipeline ceiling.
SECTION_MINUTES = 16
# ffmpeg does the cutting, and the default player client hands it a URL that
# returns 403 to anything but yt-dlp itself. The web client's URL works, but
# can expose only 360p. A successful section must therefore be measured before
# it is accepted; otherwise we use a native full download and cut locally.
SECTION_CLIENT = ["--extractor-args", "youtube:player_client=web"]


def _hhmmss(seconds: int) -> str:
    return "%02d:%02d:%02d" % (seconds // 3600, (seconds % 3600) // 60, seconds % 60)


def plan_section(duration: float) -> str:
    """The slice worth downloading, or None to take the whole file.

    Returns None for anything short enough that the slice would be most of the
    video anyway, and for unknown durations -- a section that starts past the
    end of a highlight reel downloads nothing at all.
    """
    if not duration or duration <= (SECTION_MINUTES + 4) * 60:
        return None
    start = min(600, int(duration * 0.15))
    return "*%s-%s" % (_hhmmss(start), _hhmmss(start + SECTION_MINUTES * 60))


def probe_duration(url: str) -> float:
    """Video length in seconds, or 0.0 when it cannot be determined."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--skip-download", "--no-playlist", "--print", "duration", url],
            capture_output=True, text=True, timeout=180)
        return float((result.stdout or "").strip().splitlines()[-1])
    except (subprocess.SubprocessError, OSError, ValueError, IndexError):
        return 0.0


def _purge_leftovers(destination: Path) -> None:
    """Delete a partial download and its yt-dlp siblings.

    yt-dlp resumes onto an existing file. When a worker is killed mid-download
    the leftover can be larger than the remote range allows, and every retry
    then dies with "HTTP Error 416: Requested range not satisfiable" -- which
    blocks that game permanently rather than transiently. Measured at 6 of the
    last 60 download attempts.
    """
    for leftover in destination.parent.glob(destination.stem + "*"):
        try:
            leftover.unlink()
        except OSError:
            pass


def verify_requested_height(video: Path, item: dict) -> None:
    """Fail closed when an explicitly requested rung did not materialize."""
    required = item.get("required_height")
    if required is None:
        return
    try:
        required = int(required)
    except (TypeError, ValueError) as exc:
        raise ValueError("required_height must be an integer") from exc
    measured = video_height(video)
    if measured != required:
        raise RuntimeError("required %dp but ffprobe measured %dp" %
                           (required, measured))


def download_local(item: dict) -> Path:
    """Download one item to the local stage, returning the merged file."""
    LOCAL_STAGE.mkdir(parents=True, exist_ok=True)
    destination = LOCAL_STAGE / (item["game_id"] + ".mp4")
    # A direct CDN file (MLB's mlb-cuts-diamond mp4s) has no formats to select.
    # Forcing "bv*+ba" at it makes yt-dlp fail with a generic-extractor error,
    # which silently killed the ONE lane that is never bot-blocked.
    if _is_direct_media(item["url"]):
        rungs = [None]
    else:
        rungs = ([item["format"]] + FORMAT_RUNGS) if item.get("format") else FORMAT_RUNGS
    # Section attempts first, full-file attempts as the fallback. A section can
    # legitimately fail (short video, no ffmpeg, an extractor that ignores it),
    # and when it does the ladder must still be able to fetch the whole game.
    section = None
    if not _is_direct_media(item["url"]):
        # An explicit "section" pins the slice. plan_section caps the start at
        # 600s, which lands inside the pregame show on a 4-hour live stream.
        section = item.get("section") or plan_section(probe_duration(item["url"]))
    last_error = "no attempt made"
    # For a bounded section, cookie-backed HLS has the needed 720p/1080p
    # pre-muxed formats and fetches only the requested fragments. Prefer it
    # before the no-cookie web client, which exposes only 360p and can force an
    # expensive full-file fallback. Whole-file downloads still prefer clean
    # DASH before cookies.
    cookie_order = (True, False) if section else (False, True)
    attempts = [(r, c, sec) for sec in ([section, None] if section else [None])
                for c in cookie_order for r in rungs]
    for rung, use_cookies, use_section in attempts:
        # Build positionally rather than splicing into the list. Inserting at
        # command[-2:-2] once landed "-f <rung>" BETWEEN "-o" and its filename,
        # so yt-dlp took "-f" as the output template and failed every YouTube
        # item with "Fixed output name but more than one file to download".
        command = ["yt-dlp", "--merge-output-format", "mp4", "--no-part",
                   "--no-playlist"]
        if use_cookies and COOKIES.is_file():
            command += ["--cookies", str(COOKIES)]
        elif use_cookies:
            continue  # no cookie file, so the cookie pass is not a real retry
        if rung is not None:
            command += ["-f", rung]
        if use_section is not None:
            command += ["--download-sections", use_section]
            # The web player client exposes ONLY itag 18 (640x360). With cookies
            # the tv client serves the HLS 720p/1080p rungs, so forcing the web
            # client here silently re-created the 360p defect on every section
            # retry (found by the v3 coach-depth audit; measured 5.0%->18.7%
            # five-line-gate gain at 720p rides on NOT doing this).
            if not (use_cookies and COOKIES.is_file()):
                command += SECTION_CLIENT
        command += ["-o", str(destination), item["url"]]
        try:
            subprocess.run(command, check=True, timeout=7200,
                           capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            last_error = _error_tail(exc.stderr, exc.stdout)
            if "416" in last_error:
                # Resume onto a stale partial. Clear it so the NEXT rung starts
                # clean instead of inheriting the same unsatisfiable range.
                _purge_leftovers(destination)
            continue
        except subprocess.TimeoutExpired:
            last_error = "yt-dlp timeout"
            continue
        produced = _resolve_download(destination)
        if produced is not None:
            try:
                verify_requested_height(produced, item)
            except RuntimeError as exc:
                last_error = str(exc)
                _purge_leftovers(destination)
                continue
            if use_section is not None and video_height(produced) < MIN_SECTION_HEIGHT:
                last_error = "section resolution below %dp" % MIN_SECTION_HEIGHT
                _purge_leftovers(destination)
                continue
            if use_section is None and section is not None:
                try:
                    return cut_full_download(produced, destination, section)
                except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                    last_error = "local section cut failed: %s" % str(exc)[:160]
                    _purge_leftovers(destination)
                    continue
            return produced
        last_error = "yt-dlp reported success but produced no file"
    raise RuntimeError("download failed: %s" % last_error)


def pod_backlog() -> int:
    """Complete games staged on the pod awaiting tracking. -1 when unknown.

    Counts only published .mp4 files; in-flight .part uploads are deliberately
    excluded so a slow transfer cannot look like backlog.
    """
    result = _ssh("ls %s/*.mp4 2>/dev/null | wc -l" % REMOTE_STAGE, timeout=120)
    try:
        return int((result.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        return -1


def wait_for_capacity(limit: int = MAX_POD_BACKLOG, sleep_seconds: int = 120,
                      attempts: int = 20) -> int:
    """Pause while the pod already has more staged games than it can track.

    Returns the last observed backlog. An UNKNOWN backlog (-1, e.g. ssh down)
    never blocks: stalling the whole night on a failed probe would be worse
    than briefly over-filling the stage. The attempt cap likewise guarantees
    this can never deadlock if the backlog stops draining.
    """
    backlog = pod_backlog()
    for _ in range(attempts):
        if backlog < 0 or backlog < limit:
            return backlog
        print("pod backlog %d >= %d -- pausing downloads" % (backlog, limit),
              flush=True)
        time.sleep(sleep_seconds)
        backlog = pod_backlog()
    return backlog


def push_and_track(local: Path, item: dict) -> str:
    """Upload to the private stage, track on the pod, then delete the remote copy."""
    game_id, sport = item["game_id"], item["sport"]
    remote = "%s/%s%s" % (REMOTE_STAGE, game_id, local.suffix)
    _ssh("mkdir -p %s" % REMOTE_STAGE, timeout=120)
    result = None
    try:
        subprocess.run(["scp", "-o", "StrictHostKeyChecking=no", "-P", "40048",
                        str(local), "%s:%s" % (POD_HOST, remote)],
                       check=True, timeout=7200, capture_output=True, text=True)
        adapter = SPORT_ADAPTER.get(sport, sport)
        if adapter in ("wnba", "basketball"):
            # Same defect as track_daemon had: without --data-dir run_clip writes
            # <repo>/data/tracking_data.csv, which tracking_rows() (above) never
            # reads, so a successful run reads back as rows=0. 3000, not 18000 --
            # an 18000-frame job was measured still running after 5.06 hours.
            track = ("cd %s && PYTHONPATH=%s python scripts/run_clip.py --video %s "
                     "--game-id %s --no-show --frames 3000 --data-dir data/tracking/%s"
                     % (POD_ROOT, POD_ROOT, remote, game_id, game_id))
        else:
            track = ("cd %s && PYTHONPATH=%s python adapter_run.py %s %s %s"
                     % (POD_ROOT, POD_ROOT, adapter, remote, game_id))
        result = _ssh(track)
    finally:
        # Always reclaim pod disk, even when tracking raised. The pod filled twice.
        _ssh("rm -f %s" % remote, timeout=300)
    rows = tracking_rows(game_id)
    if rows >= MIN_TRACKING_ROWS:
        return "tracked rows=%d %s" % (rows, grade(game_id, sport))
    tail = ""
    if result is not None:
        tail = ((result.stdout or "") + (result.stderr or ""))[-160:].replace("\n", " ")
    return "thin rows=%d %s" % (rows, tail)


def push_staged(local: Path, item: dict) -> str:
    """Upload only; the pod-side track_daemon does the tracking.

    Tracking used to run inline here, which capped pod concurrency at the lane
    count and in practice held it at one process on a 256-core box. The worker
    now returns as soon as the video is on the pod and goes back to downloading.

    The file is scp'd to <name>.mp4.part and renamed atomically, so the daemon
    never sees a partial upload. Do not "simplify" this to a direct scp.
    """
    verify_requested_height(local, item)
    game_id, sport = item["game_id"], item["sport"]
    remote = "%s/%s__%s%s" % (REMOTE_STAGE, sport, game_id, local.suffix)
    _ssh("mkdir -p %s" % REMOTE_STAGE, timeout=120)
    subprocess.run(["scp", "-o", "StrictHostKeyChecking=no", "-P", "40048",
                    str(local), "%s:%s.part" % (POD_HOST, remote)],
                   check=True, timeout=7200, capture_output=True, text=True)
    moved = _ssh("mv %s.part %s" % (remote, remote), timeout=300)
    if moved.returncode != 0:
        _ssh("rm -f %s.part" % remote, timeout=300)
        raise RuntimeError("stage rename failed: %s"
                           % (moved.stderr or "")[-160:])
    return "staged"


def grade(game_id: str, sport: str) -> str:
    """Score a tracked game with the harness and write its report on the pod.

    The adapter path grades itself, but the basketball/WNBA path goes through
    run_clip.py which does not, so those games were tracked and never graded.
    About fifteen readers of data/tracking_reports/ had no producer for them.
    """
    adapter = SPORT_ADAPTER.get(sport, sport)
    harness_sport = "basketball" if adapter in ("wnba", "basketball") else adapter
    script = (
        "import json, os, pandas as pd;"
        "from scripts.platformkit.tracking_harness import evaluate;"
        "r = evaluate(pd.read_csv('data/tracking/%s/tracking_data.csv'), '%s');"
        "os.makedirs('data/tracking_reports/%s', exist_ok=True);"
        "open('data/tracking_reports/%s/%s.json','w').write(r.to_json());"
        "print('passed' if r.passed else 'FAILED:' + ';'.join(r.failures)[:120])"
        % (game_id, harness_sport, harness_sport, harness_sport, game_id))
    result = _ssh("cd %s && PYTHONPATH=%s python -c \"%s\""
                  % (POD_ROOT, POD_ROOT, script), timeout=900)
    verdict = (result.stdout or "").strip().splitlines()
    if verdict:
        return verdict[-1]
    return "ungraded:" + (result.stderr or "")[-90:].replace("\n", " ")


def _reference_quality(local: Path, sport: str) -> Optional[dict]:
    """Measured quality of a candidate clip, or None when nothing measured it.

    In DECOUPLED mode this is usually None: keep_reference runs immediately
    after the upload, before the pod has tracked anything, and the tracking
    output lives on the pod anyway. Callers must handle None by keeping the
    clip provisionally rather than discarding it -- rejecting every unmeasured
    candidate silently retains NOTHING, which is how the reference corpus
    stayed empty.
    """
    game_id = local.stem
    report = TRACKING_REPORT_DIR / sport / (game_id + ".json")
    tracking = TRACKING_DIR / game_id / "tracking_data.csv"
    passed, evidence, rows = False, False, 0
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
        passed = bool(payload.get("passed", False))
        evidence = True
    except (OSError, ValueError, TypeError):
        pass
    try:
        with tracking.open(encoding="utf-8") as handle:
            rows = max(0, sum(1 for _ in handle) - 1)
        evidence = True
    except OSError:
        rows = 0
    return {"game_id": game_id, "rows": rows, "passed": passed} if evidence else None


def _reference_clip(sport: str) -> Optional[Path]:
    """The retained clip for a sport, excluding its JSON metadata sidecar."""
    for path in REFERENCE_DIR.glob(sport + ".*"):
        if path.is_file() and path.stem == sport and path.suffix != ".json":
            return path
    return None


def keep_reference(local: Path, sport: str) -> bool:
    """Retain the BEST known clip per sport, replacing a weaker incumbent.

    Ranked by (passed, rows), so a game that clears the harness always beats
    one that does not. The previous version kept the FIRST clip forever, which
    let a nine-row clip become a sport's permanent baseline.

    An unmeasured candidate is kept PROVISIONALLY when there is no incumbent,
    so a run always retains footage; any measured clip then outranks it.
    """
    quality = _reference_quality(local, sport)
    provisional = quality is None
    if provisional:
        quality = {"game_id": local.stem, "rows": 0, "passed": False,
                   "provisional": True}
    sidecar = REFERENCE_DIR / (sport + ".reference.json")
    candidate = REFERENCE_DIR / (sport + ".candidate" + local.suffix)
    metadata = REFERENCE_DIR / (sport + ".reference.json.new")
    try:
        REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
        incumbent = _reference_clip(sport)
        if incumbent is not None:
            if provisional:
                return False  # never displace a clip with an unmeasured one
            try:
                prior = json.loads(sidecar.read_text(encoding="utf-8"))
                prior_rank = (bool(prior["passed"]), int(prior["rows"]))
            except (OSError, ValueError, TypeError, KeyError):
                prior_rank = (False, -1)  # unreadable sidecar must not lock us out
            if (bool(quality["passed"]), int(quality["rows"])) <= prior_rank:
                return False
        local.replace(candidate)
        metadata.write_text(json.dumps(quality, sort_keys=True), encoding="utf-8")
        destination = REFERENCE_DIR / (sport + local.suffix)
        # Stage before publishing: a failed publish leaves the incumbent intact,
        # and an incumbent with a different suffix is removed only afterwards.
        candidate.replace(destination)
        metadata.replace(sidecar)
        if incumbent is not None and incumbent != destination:
            incumbent.unlink()
        print("kept reference clip for %s (rows=%d passed=%s%s)"
              % (sport, quality["rows"], quality["passed"],
                 " provisional" if provisional else ""), flush=True)
        return True
    except OSError as exc:
        candidate.unlink(missing_ok=True)
        metadata.unlink(missing_ok=True)
        print("reference keep failed for %s: %s" % (sport, exc), flush=True)
        return False


def _record(entry: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def run_queue(queue_path: Path, limit: int, decouple: bool = False) -> int:
    """Process up to `limit` untracked items. Returns how many advanced.

    With decouple=True the worker only uploads and the pod-side track_daemon
    tracks; that is the mode that actually uses the pod.
    """
    try:
        items = json.loads(queue_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("queue unreadable %s: %s" % (queue_path, exc), flush=True)
        return 0
    done = tracked = 0
    known = tracked_row_counts()
    for item in items:
        if done >= limit:
            break
        game_id = item.get("game_id")
        if not game_id or known.get(game_id, 0) >= MIN_TRACKING_ROWS:
            continue
        local = None
        try:
            local = download_local(item)
            verdict = footage_content_gate.screen_fail_open(local, item.get("sport", ""))
            if verdict.decision == "reject":
                moved = footage_content_gate.quarantine(local, verdict)
                status = "quarantined: %s (%s)" % (verdict.reason, moved.name)
                local = None  # quarantine owns the evidence; never delete it below
            else:
                push = push_staged if decouple else push_and_track
                status = push(local, item)
                if verdict.decision == "review":
                    status += " content_review"
        except Exception as exc:  # one bad item must never stop the run
            status = "failed: %s" % str(exc)[:200]
        finally:
            if local is not None:
                if not (status.startswith(("tracked", "staged"))
                        and keep_reference(local, item.get("sport", "unknown"))):
                    for leftover in LOCAL_STAGE.glob(local.stem + "*"):
                        leftover.unlink(missing_ok=True)
        print("%s %s %s" % (game_id, item.get("sport"), status), flush=True)
        _record({"game_id": game_id, "sport": item.get("sport"), "status": status})
        done += 1
        tracked += int(status.startswith(("tracked", "staged")))
    return tracked


def main() -> int:
    parser = argparse.ArgumentParser(description="Local-download / pod-track bridge")
    parser.add_argument("--queue", type=Path, action="append", default=[])
    parser.add_argument("--all", action="store_true",
                        help="every data/footage_queue_*.json")
    parser.add_argument("--limit", type=int, default=3, help="items per queue per pass")
    parser.add_argument("--forever", action="store_true",
                        help="keep cycling; the pod must never idle")
    parser.add_argument("--sleep", type=int, default=120, help="pause between passes")
    parser.add_argument("--decouple", action="store_true",
                        help="upload only; track_daemon tracks on the pod")
    args = parser.parse_args()
    queues = list(args.queue)
    if args.all or not queues:
        queues = sorted(Path("data").glob("footage_queue_*.json"))
    if not queues:
        print("no queues found", flush=True)
        return 1
    while True:
        for queue_path in queues:
            try:
                # Backpressure lives here, not inside run_queue: run_queue is
                # unit-tested and must never open an ssh connection or sleep.
                if args.decouple:
                    wait_for_capacity()
                run_queue(queue_path, args.limit, args.decouple)
            except Exception as exc:  # a bad queue must never end the night
                print("queue pass failed %s: %s" % (queue_path, exc), flush=True)
        if not args.forever:
            return 0
        time.sleep(args.sleep)


if __name__ == "__main__":
    sys.exit(main())
