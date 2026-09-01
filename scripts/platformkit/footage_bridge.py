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
# yt-dlp writes per-stream files like game.f137.mp4 (video-only) and
# game.f299.mp4 (audio-only) before merging them. If the merge fails these
# survive, and picking the largest would ship a video-only or audio-only
# stream to the tracker as if it were the game.
_FORMAT_PART = re.compile(r"\.f\d{2,4}\.")
# A real tracked game has thousands of rows. Anything under this is a failed
# detection pass wearing a successful exit code.
MIN_TRACKING_ROWS = 500
SPORT_ADAPTER = {"tennis": "tennis", "soccer": "soccer", "npb": "baseball",
                 "kbo": "baseball", "mlb": "baseball", "baseball": "baseball"}
# yt-dlp rungs, cheapest first. The pod cannot use any of them; the local IP can.
FORMAT_RUNGS = [
    "bv*[height<=1080][vcodec^=avc1]+ba/b[height<=1080]",
    "bv*[height<=720][vcodec^=avc1]+ba/b[height<=720]",
    "b[height<=720]",
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
    last_error = "no attempt made"
    # Cookies LAST, not first. With cookies yt-dlp picks the tv client and gets
    # HLS (format 96, ~1100 fragments, very slow); without them it gets clean
    # DASH (137+251). The residential IP is not bot-blocked, so cookies are only
    # a fallback for the occasional video that demands them.
    for rung, use_cookies in [(r, c) for c in (False, True) for r in rungs]:
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
        command += ["-o", str(destination), item["url"]]
        try:
            subprocess.run(command, check=True, timeout=7200,
                           capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            last_error = _error_tail(exc.stderr, exc.stdout)
            continue
        except subprocess.TimeoutExpired:
            last_error = "yt-dlp timeout"
            continue
        produced = _resolve_download(destination)
        if produced is not None:
            return produced
        last_error = "yt-dlp reported success but produced no file"
    raise RuntimeError("download failed: %s" % last_error)


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
            track = ("cd %s && PYTHONPATH=%s python scripts/run_clip.py --video %s "
                     "--game-id %s --no-show --frames 18000"
                     % (POD_ROOT, POD_ROOT, remote, game_id))
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


def keep_reference(local: Path, sport: str) -> bool:
    """Retain ONE clip per sport for re-measurement; return True if kept.

    Everything else is still deleted from both disks. Without this, no footage
    survives a run and tracking changes cannot be measured before/after.
    """
    try:
        REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
        if any(REFERENCE_DIR.glob(sport + ".*")):
            return False
        local.replace(REFERENCE_DIR / (sport + local.suffix))
        print("kept reference clip for %s" % sport, flush=True)
        return True
    except OSError as exc:
        print("reference keep failed for %s: %s" % (sport, exc), flush=True)
        return False


def _record(entry: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def run_queue(queue_path: Path, limit: int) -> int:
    """Process up to `limit` untracked items. Returns how many were newly tracked."""
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
            status = push_and_track(local, item)
        except Exception as exc:  # one bad item must never stop the run
            status = "failed: %s" % str(exc)[:200]
        finally:
            if local is not None:
                if not (status.startswith("tracked")
                        and keep_reference(local, item.get("sport", "unknown"))):
                    for leftover in LOCAL_STAGE.glob(local.stem + "*"):
                        leftover.unlink(missing_ok=True)
        print("%s %s %s" % (game_id, item.get("sport"), status), flush=True)
        _record({"game_id": game_id, "sport": item.get("sport"), "status": status})
        done += 1
        tracked += int(status.startswith("tracked"))
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
                run_queue(queue_path, args.limit)
            except Exception as exc:  # a bad queue must never end the night
                print("queue pass failed %s: %s" % (queue_path, exc), flush=True)
        if not args.forever:
            return 0
        time.sleep(args.sleep)


if __name__ == "__main__":
    sys.exit(main())
