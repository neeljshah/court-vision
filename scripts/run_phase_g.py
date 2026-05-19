"""
run_phase_g.py -- Phase G: Batch-process existing game videos, no recording needed.

Scans data/videos/full_games/ (game-ID-named) and data/videos/ (team-named),
runs the full tracker pipeline on each unprocessed game, saves per-game outputs
to data/tracking/{game_id}/, and logs tracker quality metrics.

Usage:
    conda activate basketball_ai

    # Process all unprocessed games (default: first 10 min of each game)
    python scripts/run_phase_g.py

    # Process a specific number of frames per game (e.g. 5 min at 30fps = 9000)
    python scripts/run_phase_g.py --frames 9000

    # Process full games (slow -- use for final validation)
    python scripts/run_phase_g.py --full

    # Re-process already-done games
    python scripts/run_phase_g.py --reprocess

    # Download + process (requires fetch_games.py run first, or add --download)
    python scripts/run_phase_g.py --download --count 5
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

_file_lock = threading.Lock()  # guards phase_g_processed.txt + metrics CSV writes
_completed_count = 0  # total games marked done this run (for incremental rsync)

_GAME_TIMEOUT = int(os.environ.get("PHASE_G_GAME_TIMEOUT", "10800"))  # per-game timeout: 3h for full games

try:
    import cv2 as _cv2
except ImportError:
    _cv2 = None  # cv2 unavailable -- FPS detection will be skipped

# Force UTF-8 output on Windows (cp1252 default chokes on Unicode video filenames)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

DATA_DIR      = PROJECT_DIR / "data"
VIDEOS_DIR    = DATA_DIR / "videos"
FULL_GAMES    = Path(os.environ.get("PHASE_G_VIDEO_DIR", VIDEOS_DIR / "full_games"))
TRACKING_DIR  = DATA_DIR / "tracking"
DONE_LOG      = DATA_DIR / "phase_g_processed.txt"
FAILED_LOG    = DATA_DIR / "phase_g_failed.txt"
METRICS_LOG   = DATA_DIR / "phase_g_metrics.csv"
VAULT_LOG     = PROJECT_DIR / "vault" / "Improvements" / "Tracker Improvements Log.md"

# Frames to process per game in quick mode (10 min @ 30fps)
DEFAULT_FRAMES = 18_000


# -- helpers -------------------------------------------------------------------

def _game_hash(key: str, video_path: Path) -> str:
    """SHA256 hash of (game_key, resolved video path) for dedup."""
    raw = f"{key}|{video_path.resolve()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _done_set() -> set[str]:
    """Return set of done keys AND their hashes."""
    if DONE_LOG.exists():
        return set(DONE_LOG.read_text().splitlines())
    return set()


def _done_hashes() -> set[str]:
    """Return set of hash tokens already in the done log (prefix 'hash:')."""
    if not DONE_LOG.exists():
        return set()
    return {ln[5:] for ln in DONE_LOG.read_text().splitlines()
            if ln.startswith("hash:")}


def _try_rsync() -> None:
    """Non-blocking incremental rsync of data/tracking/ to SYNC_TARGET."""
    sync_target = os.environ.get("SYNC_TARGET", "")
    if not sync_target:
        print("  [rsync] SYNC_TARGET not set — skipping incremental sync", flush=True)
        return
    ssh_key = os.environ.get("SSH_KEY", "")
    port    = os.environ.get("PORT", "")
    if ssh_key and port:
        ssh_opt = f"ssh -i {ssh_key} -p {port}"
        cmd = ["rsync", "-az", "--timeout=60", "-e", ssh_opt, "data/tracking/", sync_target]
    elif port:
        cmd = ["rsync", "-az", "--timeout=60", "-e", f"ssh -p {port}", "data/tracking/", sync_target]
    else:
        cmd = ["rsync", "-az", "--timeout=60", "data/tracking/", sync_target]
    try:
        r = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=90, cwd=str(PROJECT_DIR),
        )
        if r.returncode == 0:
            print(f"  [rsync] incremental sync OK -> {sync_target}", flush=True)
        else:
            print(f"  [rsync] sync failed (rc={r.returncode}): {r.stderr[:200]}", flush=True)
    except Exception as e:
        print(f"  [rsync] sync error (non-blocking): {e}", flush=True)


def _mark_done(key: str, video_path: Optional[Path] = None):
    global _completed_count
    # Atomic write — write full content to .tmp then os.replace
    with _file_lock:
        existing = DONE_LOG.read_text().splitlines() if DONE_LOG.exists() else []
        existing.append(key)
        if video_path is not None:
            existing.append(f"hash:{_game_hash(key, video_path)}")
        _tmp = DONE_LOG.with_suffix(".tmp")
        _tmp.write_text("\n".join(existing) + "\n")
        os.replace(str(_tmp), str(DONE_LOG))
        _completed_count += 1
        _count = _completed_count
    # Incremental rsync every 10 completed games when running on RunPod
    if _count % 10 == 0 and os.environ.get("RUNPOD_POD_ID"):
        _try_rsync()


def _mark_failed(key: str, stderr_tail: str) -> None:
    """Append game_key + error snippet to phase_g_failed.txt (non-blocking)."""
    try:
        with _file_lock:
            entry = f"{datetime.now().isoformat(timespec='seconds')} {key}: {stderr_tail[:300]}\n"
            with open(FAILED_LOG, "a", encoding="utf-8", errors="replace") as f:
                f.write(entry)
    except Exception:
        pass


def _quality_label(ball_valid_pct: float) -> str:
    """Fix 5: classify game tracking quality by ball detection rate."""
    if ball_valid_pct >= 80.0:
        return "high"
    if ball_valid_pct >= 65.0:
        return "medium"
    return "low"


_METRICS_FIELDNAMES = ["timestamp", "game_key", "game_id", "frames", "stability",
                       "id_switches", "ball_valid_pct", "quality", "duration_s"]


def _repair_metrics_header():
    """Rewrite phase_g_metrics.csv header in-place if it doesn't match _METRICS_FIELDNAMES."""
    if not METRICS_LOG.exists():
        return
    with open(METRICS_LOG, newline="") as f:
        reader = csv.DictReader(f)
        existing_fields = reader.fieldnames or []
        rows = list(reader)
    if list(existing_fields) == _METRICS_FIELDNAMES:
        return  # header already correct
    with open(METRICS_LOG, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_METRICS_FIELDNAMES, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"  [metrics] Repaired header: {existing_fields} -> {_METRICS_FIELDNAMES}")


def _save_metrics(game_key: str, game_id: Optional[str], metrics: dict):
    METRICS_LOG.parent.mkdir(parents=True, exist_ok=True)
    quality = metrics.pop("quality", None) or _quality_label(float(metrics.get("ball_valid_pct", 0)))
    fieldnames = _METRICS_FIELDNAMES
    with _file_lock:
        exists = METRICS_LOG.exists()
        with open(METRICS_LOG, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            if not exists:
                w.writeheader()
            w.writerow({
                "timestamp":     datetime.now().isoformat(timespec="seconds"),
                "game_key":      game_key,
                "game_id":       game_id or "",
                "quality":       quality,
                **metrics,
            })
    if quality == "low":
        print(f"  WARNING: {game_key} ball_valid={metrics.get('ball_valid_pct', 0):.1f}% "
              f"-- LOW QUALITY, exclude from training")


def _log_to_vault(entries: list[str]):
    if not VAULT_LOG.exists():
        return
    header = f"\n## Phase G -- {datetime.now().strftime('%Y-%m-%d')}\n"
    with _file_lock, open(VAULT_LOG, "a", encoding="utf-8") as f:
        f.write(header)
        for line in entries:
            f.write(f"- {line}\n")


def _is_complete(out_dir: Path) -> bool:
    """Return True iff the output directory has all required CSVs with > 0 rows.

    If a required CSV exists but has 0 data rows, deletes it so the game
    can be retried cleanly on next --resume run.
    """
    required = ["tracking_data.csv"]
    for name in required:
        p = out_dir / name
        if not p.exists():
            return False
        try:
            with open(p) as f:
                reader = csv.reader(f)
                next(reader)  # header
                next(reader)  # at least one data row
        except StopIteration:
            # Zero-row output — delete it so --resume can retry this game
            try:
                p.unlink()
                print(f"  [cleanup] Deleted zero-row output: {p}")
            except Exception:
                pass
            return False
        except Exception:
            return False
    return True


def _recompute_ball_valid(ball_csv: Path) -> Optional[float]:
    """Recompute ball_valid_pct using live-frame denominator if column exists.

    For CSVs that have the `live` column: detected.sum() / live.sum().
    For old CSVs without `live`: apply a streak-based heuristic -- any stretch
    of 90+ consecutive detected=0 frames is classified as non-live (replay /
    halftime / ad-break) and excluded from the denominator.
    """
    if not ball_csv.exists():
        return None
    try:
        detected_flags: list = []
        live_flags: list     = []
        has_live = False
        with open(ball_csv) as bf:
            for row in csv.DictReader(bf):
                d = int(str(row.get("detected", "0")) == "1")
                detected_flags.append(d)
                if "live" in row:
                    has_live = True
                    live_flags.append(int(str(row["live"]) == "1"))

        if not detected_flags:
            return None

        if has_live and live_flags:
            detected  = sum(detected_flags)
            live_total = sum(live_flags)
            denom = live_total if live_total > 0 else len(detected_flags)
            return round(detected / denom * 100, 1)

        # Heuristic for old CSVs (no live column): mark 90+-frame zero-detection
        # stretches as non-live.  30fps / stride=3 -> 10 effective fps; 90 frames
        # = 9 real seconds -- long enough to span replays and halftime sequences.
        _STREAK_MIN = 90
        heuristic_live = [1] * len(detected_flags)
        streak_start = None
        for i, d in enumerate(detected_flags):
            if d == 0:
                if streak_start is None:
                    streak_start = i
            else:
                if streak_start is not None and (i - streak_start) >= _STREAK_MIN:
                    for j in range(streak_start, i):
                        heuristic_live[j] = 0
                streak_start = None
        # Handle trailing streak
        if streak_start is not None and (len(detected_flags) - streak_start) >= _STREAK_MIN:
            for j in range(streak_start, len(detected_flags)):
                heuristic_live[j] = 0

        detected   = sum(detected_flags)
        live_total = sum(heuristic_live)
        denom = live_total if live_total > 0 else len(detected_flags)
        return round(detected / denom * 100, 1)
    except Exception:
        pass
    return None


def _collect_videos() -> list[tuple[str, Path, Optional[str]]]:
    """Return list of (display_key, video_path, game_id_or_None)."""
    videos = []

    # full_games/*.mp4 -- filename IS the game ID
    if FULL_GAMES.exists():
        for p in sorted(FULL_GAMES.glob("*.mp4")):
            gid = p.stem  # e.g. "0022400625"
            videos.append((gid, p, gid))

    # data/videos/*.mp4 -- team-named clips, no game ID
    for p in sorted(VIDEOS_DIR.glob("*.mp4")):
        key = p.stem
        videos.append((key, p, None))

    return videos


def _backfill_live_pct():
    """Recompute ball_valid_pct for all processed games using live-frame denominator.

    Reads each game's ball_tracking.csv from data/tracking/{game_id}/ and updates
    the ball_valid_pct column in phase_g_metrics.csv.  Games whose CSVs lack the
    `live` column fall back to the existing detected/total computation.
    """
    if not METRICS_LOG.exists():
        print("phase_g_metrics.csv not found -- nothing to backfill.")
        return

    rows = []
    with open(METRICS_LOG, newline="") as f:
        rows = list(csv.DictReader(f))

    updated = 0
    for row in rows:
        game_key = row.get("game_key", "")
        ball_csv = TRACKING_DIR / game_key / "ball_tracking.csv"
        pct = _recompute_ball_valid(ball_csv)
        if pct is not None:
            old_pct = row.get("ball_valid_pct", "")
            row["ball_valid_pct"] = str(pct)
            row["quality"] = _quality_label(pct)   # Fix 5: backfill quality label
            if old_pct != str(pct):
                print(f"  {game_key}: ball_valid_pct  {old_pct} -> {pct}  quality={row['quality']}")
                updated += 1

    if not rows:
        print("No rows to update.")
        return

    # Ensure quality column is present in fieldnames (older CSVs won't have it)
    fieldnames = list(rows[0].keys())
    if "quality" not in fieldnames:
        # Insert after ball_valid_pct
        idx = fieldnames.index("ball_valid_pct") + 1 if "ball_valid_pct" in fieldnames else len(fieldnames)
        fieldnames.insert(idx, "quality")
    with _file_lock:
        with open(METRICS_LOG, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)

    print(f"Backfill complete -- {updated} game(s) updated in {METRICS_LOG.name}")


def _remove_zero_frame_processed() -> None:
    """Remove game IDs with frames==0 from phase_g_processed.txt so --resume retries them."""
    if not METRICS_LOG.exists() or not DONE_LOG.exists():
        return
    zero_ids: set[str] = set()
    with open(METRICS_LOG, newline="") as f:
        for row in csv.DictReader(f):
            try:
                if int(row.get("frames", "1") or "1") == 0:
                    gid = row.get("game_id", "").strip()
                    if gid:
                        zero_ids.add(gid)
            except (ValueError, TypeError):
                pass
    if not zero_ids:
        return
    lines = DONE_LOG.read_text().splitlines()
    cleaned = [ln for ln in lines if ln.strip() not in zero_ids]
    if len(cleaned) < len(lines):
        removed = set(lines) - set(cleaned)
        _tmp = DONE_LOG.with_suffix(".tmp")
        _tmp.write_text("\n".join(cleaned) + ("\n" if cleaned else ""))
        os.replace(str(_tmp), str(DONE_LOG))
        print(f"  [processed] Removed {len(removed)} zero-frame game(s) from done log: "
              f"{', '.join(sorted(removed))}")


def _fps_adjusted_frames(video: Path, target_frames: int) -> int:
    """Scale target_frames so we always cover ~10 min regardless of video FPS.

    target_frames is calibrated for 30fps (18000 = 10 min).  For 60fps clips,
    we double the budget so both get the same real-time window of footage.
    """
    try:
        if _cv2 is None:
            return target_frames
        cap = _cv2.VideoCapture(str(video))
        fps = cap.get(_cv2.CAP_PROP_FPS) or 30.0
        cap.release()
        if fps > 45:   # 60fps clip
            return int(target_frames * fps / 30.0)
    except Exception:
        pass
    return target_frames


def _run_clip(video: Path, game_id: Optional[str], frames: Optional[int],
              out_dir: Path, start_frame: int = 0, skip_tracking: bool = False,
              game_key: Optional[str] = None, gpu_id: Optional[int] = None) -> dict:
    """Run run_clip.py and capture metrics. Returns metrics dict."""
    out_dir.mkdir(parents=True, exist_ok=True)

    # Auto-scale frame budget for high-FPS (60fps) videos so we always cover
    # the same real-time window regardless of video frame rate.
    if frames is not None and not skip_tracking:
        frames = _fps_adjusted_frames(video, frames)

    cmd = [
        sys.executable, str(PROJECT_DIR / "scripts" / "run_clip.py"),
        "--video", str(video),
        "--no-show",
        "--data-dir", str(out_dir),   # Fix 2: write directly to per-game dir
        "--skip-features",            # Phase G only needs tracking metrics, not features
    ]
    if frames and not skip_tracking:
        cmd += ["--frames", str(frames)]
    if start_frame:
        cmd += ["--start-frame", str(start_frame)]
    if game_id:
        cmd += ["--game-id", game_id]  # period auto-detected via ball_tracking.csv duration
    if skip_tracking:
        cmd += ["--skip-tracking"]

    t0 = time.time()

    # Stream stdout live so the terminal shows progress instead of going silent
    # for the full duration of the run.  Metrics are parsed from lines as they arrive.
    metrics = {"duration_s": 0.0, "frames": 0,
               "stability": 0.0, "id_switches": 0, "ball_valid_pct": 0.0}
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    def _parse_metric_line(line: str) -> None:
        if ("Frames processed" in line or
                (line.strip().startswith("Frames") and ":" in line and "@" in line)):
            try:
                metrics["frames"] = int(line.split(":")[1].strip().split()[0])
            except (ValueError, IndexError):
                pass
        elif "Track stability" in line:
            try:
                metrics["stability"] = float(line.split(":")[-1].strip())
            except ValueError:
                pass
        elif "Est. ID switches" in line:
            try:
                metrics["id_switches"] = int(line.split(":")[-1].strip())
            except ValueError:
                pass
        elif "ball_valid" in line.lower() or "ball valid" in line.lower():
            try:
                pct = float(line.split()[-1].rstrip("%"))
                metrics["ball_valid_pct"] = pct
            except (ValueError, IndexError):
                pass

    # Per-worker GPU assignment: when gpu_id is set, pin this subprocess to a
    # single GPU via CUDA_VISIBLE_DEVICES.  With N GPUs and N workers, each
    # worker gets exclusive VRAM — no contention, no fragmentation.
    _env = os.environ.copy()
    if gpu_id is not None:
        _env["CUDA_VISIBLE_DEVICES"] = str(gpu_id)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(PROJECT_DIR),
        bufsize=1,  # line-buffered
        env=_env,
    )

    # Fix 1: per-game timeout — kill process tree after GAME_TIMEOUT seconds.
    _game_label = game_key or game_id or video.stem
    _timeout_info: dict = {"fired": False}

    def _timeout_kill():
        _timeout_info["fired"] = True
        print(f"\n  [TIMEOUT] {_game_label} exceeded {_GAME_TIMEOUT}s — killing process",
              flush=True)
        try:
            if sys.platform != "win32":
                import signal as _sig
                os.killpg(os.getpgid(proc.pid), _sig.SIGKILL)
            else:
                proc.kill()
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    _timer = threading.Timer(_GAME_TIMEOUT, _timeout_kill)
    _timer.daemon = True
    _timer.start()

    # Drain stderr in a background thread so it never deadlocks the stdout read.
    def _drain_stderr():
        for line in proc.stderr:
            stderr_lines.append(line)
    _stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    _stderr_thread.start()

    for raw_line in proc.stdout:
        line = raw_line.rstrip("\n")
        stdout_lines.append(line)
        _parse_metric_line(line)
        # Print live -- suppress \r Frame lines to avoid terminal spam; show all others
        if not line.startswith("\r") and line.strip():
            print(f"    {line}", flush=True)
        elif line.startswith("\r"):
            # Show a condensed progress ticker
            print(f"    {line.strip()}", end="\r", flush=True)

    proc.wait()
    _timer.cancel()
    _stderr_thread.join(timeout=5)
    elapsed = time.time() - t0
    metrics["duration_s"] = round(elapsed, 1)
    if _timeout_info["fired"]:
        metrics["_timed_out"] = True
    returncode = proc.returncode
    metrics["_rc"] = returncode  # propagate to caller for failure handling

    # Save run log
    (out_dir / "run.log").write_text(
        "\n".join(stdout_lines) + "\n--- STDERR ---\n" + "".join(stderr_lines),
        encoding="utf-8",
    )

    # Compute ball_valid_pct from ball_tracking.csv if not parsed from stdout
    if metrics["ball_valid_pct"] == 0.0:
        ball_csv = out_dir / "ball_tracking.csv"
        if ball_csv.exists():
            try:
                import csv as _csv
                detected = live_total = total = 0
                has_live = False
                with open(ball_csv, encoding="utf-8", errors="replace") as bf:
                    for row in _csv.DictReader(bf):
                        total += 1
                        if str(row.get("detected", "0")) == "1":
                            detected += 1
                        if "live" in row:
                            has_live = True
                            if str(row["live"]) == "1":
                                live_total += 1
                denom = live_total if (has_live and live_total > 0) else total
                if denom > 0:
                    metrics["ball_valid_pct"] = round(detected / denom * 100, 1)
            except Exception:
                pass

    if returncode == 3:
        print(f"  [WARN] run_clip.py exited 3 -- Stage 1 produced 0 rows (no gameplay detected)")
        print("         Video may need manual review or different start frame.")
        # Handled in _process_one -- do NOT save/mark_done here
    elif returncode == 4:
        print(f"  [PREFLIGHT FAIL] run_clip.py exited 4 -- non-broadcast video detected")
        print("         Median person count below threshold. Download a real broadcast clip.")
        metrics["ball_valid_pct"] = 0.0
        metrics["frames"] = 0
        metrics["stability"] = 0.0
        _gk = game_key or game_id or video.stem
        _save_metrics(_gk, game_id, {**metrics, "quality": "PREFLIGHT_FAIL"})
        _mark_done(_gk)  # plain key so skip-check matches on re-run
    elif returncode not in (0, 2):  # 2 = short clip warning, still ok
        print(f"  [WARN] run_clip.py exited {returncode}")
        stderr_tail = "".join(stderr_lines)
        if stderr_tail:
            print(stderr_tail[-500:])

    return metrics


# -- main ----------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Phase G -- batch tracker evaluation")
    ap.add_argument("--frames",     type=int, default=DEFAULT_FRAMES,
                    help="Frames per game in quick mode (default 18000 = ~10 min)")
    ap.add_argument("--full",       action="store_true",
                    help="Process entire video, not just the first N frames")
    ap.add_argument("--reprocess",  action="store_true",
                    help="Re-run games already in done log")
    ap.add_argument("--limit",      type=int, default=None,
                    help="Max number of games to process this run")
    ap.add_argument("--game-ids",   nargs="*", default=None,
                    help="Only process specific game IDs / keys")
    ap.add_argument("--resume",     action="store_true",
                    help="Re-run games that are in done log but have incomplete output "
                         "(missing ball_tracking.csv, tracking_data.csv, or possessions.csv)")
    ap.add_argument("--download",   action="store_true",
                    help="Download missing games first via fetch_games.py")
    ap.add_argument("--count",      type=int, default=5,
                    help="Games to download when --download is set (default 5)")
    ap.add_argument("--backfill-live", action="store_true",
                    help="Recompute ball_valid_pct for all processed games using "
                         "live-frame denominator (detected/live rows) and update "
                         "phase_g_metrics.csv in place.")
    ap.add_argument("--start-frame",  type=int, default=0,
                    help="Frame index to seek to before processing (default 0). "
                         "Use to skip pre-game content in full-game downloads.")
    ap.add_argument("--parallel",     type=int, default=1,
                    help="Number of games to process simultaneously (default 1). "
                         "Use 2 on an RTX 4060 8GB -- each pipeline uses ~3GB VRAM. "
                         "Do NOT use >2 without checking VRAM headroom.")
    ap.add_argument("--skip-tracking", action="store_true",
                    help="Skip Stage 1 tracking (requires tracking_data.csv to exist). "
                         "Use for games where tracking completed but post-processing crashed.")
    ap.add_argument("--gpus",         type=int, default=None,
                    help="Number of GPUs available. Workers are assigned GPUs round-robin "
                         "(worker 0 → GPU 0, worker 1 → GPU 1, ...). "
                         "Defaults to CUDA_VISIBLE_DEVICES count or 1.")
    args = ap.parse_args()

    if args.download:
        print("==> Downloading games via fetch_games.py ...")
        subprocess.run(
            [sys.executable, str(PROJECT_DIR / "scripts" / "fetch_games.py"),
             "--count", str(args.count)],
            cwd=str(PROJECT_DIR),
        )

    _repair_metrics_header()
    _remove_zero_frame_processed()
    done = _done_set()

    # --backfill-live: recompute ball_valid_pct in-place for all processed games
    if args.backfill_live:
        _backfill_live_pct()
        return

    videos = _collect_videos()

    if args.game_ids:
        videos = [(k, p, g) for k, p, g in videos if k in args.game_ids]

    if not args.reprocess:
        videos = [(k, p, g) for k, p, g in videos if k not in done]

    # --resume: also re-run games that are in done log but have incomplete output
    if args.resume:
        # Collect all video entries (including done ones) and filter to incomplete
        all_videos = _collect_videos()
        if args.game_ids:
            all_videos = [(k, p, g) for k, p, g in all_videos if k in args.game_ids]
        incomplete = [
            (k, p, g) for k, p, g in all_videos
            if k in done and not _is_complete(TRACKING_DIR / k)
        ]
        # Merge with already-filtered list, avoiding duplicates
        existing_keys = {k for k, _, _ in videos}
        videos = videos + [(k, p, g) for k, p, g in incomplete if k not in existing_keys]
        if incomplete:
            print(f"  [resume] Found {len(incomplete)} incomplete game(s) to reprocess: "
                  f"{', '.join(k for k, _, _ in incomplete)}")

    if not videos:
        print("No unprocessed games found. Use --reprocess to re-run done games.")
        return

    if args.limit:
        videos = videos[:args.limit]

    frames_per_game = None if args.full else args.frames
    print(f"\nPhase G -- processing {len(videos)} game(s), "
          f"{'full game' if args.full else f'first {frames_per_game} frames'} each\n")

    vault_entries = []
    total_t0 = time.time()

    # Seconds to stagger each worker's startup to avoid simultaneous model
    # loading (YOLO + OSNet + PaddleOCR/EasyOCR) causing a RAM spike.
    _STARTUP_STAGGER_S: int = int(os.environ.get("PHASE_G_STAGGER_S", "60"))

    # Detect available GPUs for round-robin assignment
    _n_gpus = args.gpus
    if _n_gpus is None:
        _cvd = os.environ.get("CUDA_VISIBLE_DEVICES", "")
        if _cvd:
            _n_gpus = len(_cvd.split(","))
        else:
            try:
                import torch as _tch
                _n_gpus = _tch.cuda.device_count() or 1
            except Exception:
                _n_gpus = 1
    if _n_gpus > 1:
        print(f"  Multi-GPU: {_n_gpus} GPUs detected — assigning workers round-robin")

    # Collect hashes already in the done log for hash-based dedup
    _done_hash_set = _done_hashes()

    def _process_one(args_tuple):
        i, total, key, video_path, game_id = args_tuple
        try:
            return _process_one_inner(i, total, key, video_path, game_id)
        except Exception as exc:
            tb = traceback.format_exc()
            print(f"  [CRASH] {key}: {exc}\n{tb[-500:]}", flush=True)
            _mark_failed(key, tb)
            return key, {"frames": 0, "stability": 0.0, "id_switches": 0,
                         "ball_valid_pct": 0.0, "duration_s": 0.0,
                         "_crashed": True}

    def _process_one_inner(i, total, key, video_path, game_id):
        # Hash-based dedup: skip if (key, path) already processed even if
        # done log uses a different display key after re-staging
        h = _game_hash(key, video_path)
        if h in _done_hash_set:
            print(f"[{i}/{total}] {key}  SKIP (hash dedup — already processed)")
            return key, {"frames": 0, "stability": 0.0, "id_switches": 0,
                         "ball_valid_pct": 0.0, "duration_s": 0.0, "_deduped": True}

        # Preflight: verify video file exists before spawning a worker process
        if not video_path.exists():
            print(f"[{i}/{total}] {key}  PREFLIGHT_MISSING: video not found: {video_path}")
            return key, {"frames": 0, "stability": 0.0, "id_switches": 0,
                         "ball_valid_pct": 0.0, "duration_s": 0.0}
        # Round-robin GPU assignment: worker index (0-based) mod GPU count
        gpu_id = (i - 1) % _n_gpus if _n_gpus > 1 else None
        if n_workers > 1 and i > 1:
            delay = (i - 1) * _STARTUP_STAGGER_S
            print(f"[{i}/{total}] {key}  staggering {delay}s to avoid model-load spike...")
            time.sleep(delay)
        _gpu_tag = f"  GPU={gpu_id}" if gpu_id is not None else ""
        print(f"[{i}/{total}] {key}  video={video_path.name}  game_id={game_id or '(none)'}{_gpu_tag}")
        out_dir = TRACKING_DIR / key
        # On reprocess, clear stale tracking_data.csv so we don't append new rows
        # onto old data with potentially different column layouts.
        if args.reprocess and not args.skip_tracking:
            stale = out_dir / "tracking_data.csv"
            if stale.exists():
                stale.unlink()
        # Retry up to 2 attempts — single game crash shouldn't stop the batch
        metrics = None
        for _attempt in range(1, 3):
            metrics = _run_clip(video_path, game_id, frames_per_game, out_dir,
                                start_frame=args.start_frame,
                                skip_tracking=args.skip_tracking,
                                game_key=key, gpu_id=gpu_id)
            rc = metrics.get("_rc", 0)
            if metrics.get("_timed_out"):
                print(f"  [TIMEOUT] {key} — killed after {_GAME_TIMEOUT}s, "
                      f"{'retrying...' if _attempt < 2 else 'giving up.'}")
            elif rc in (0, 2, 3, 4):
                break  # success or known non-retryable exit
            else:
                print(f"  [RETRY] {key} attempt {_attempt} failed (rc={rc}), "
                      f"{'retrying...' if _attempt < 2 else 'giving up.'}")
            import time as _rt; _rt.sleep(5)
        rc = metrics.pop("_rc", 0)
        if rc == 3:
            # Stage 1 produced zero rows — mark done so it isn't retried forever;
            # RC3 almost always means a non-broadcast clip with no court visibility.
            _save_metrics(key, game_id, {**metrics, "quality": "RC3_ZERO_ROWS"})
            _mark_done(key, video_path)
        elif rc == 4:
            pass  # already handled inside _run_clip
        elif _is_complete(out_dir):
            _save_metrics(key, game_id, metrics)
            _mark_done(key, video_path)
        else:
            print(f"  [WARN] {key} output incomplete -- re-run with --resume to retry.")
        print(f"  [{key}] frames={metrics['frames']}  stability={metrics['stability']:.3f}"
              f"  id_sw={metrics['id_switches']}  ball={metrics['ball_valid_pct']:.1f}%"
              f"  elapsed={metrics['duration_s']:.0f}s  -> {out_dir}")
        return key, metrics

    work = [(i, len(videos), k, p, g) for i, (k, p, g) in enumerate(videos, 1)]

    n_workers = max(1, args.parallel)
    if n_workers == 1:
        results_list = [_process_one(w) for w in work]
    else:
        print(f"  Running {n_workers} games in parallel (thread pool)")
        results_list = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as pool:
            futs = {pool.submit(_process_one, w): w for w in work}
            for fut in concurrent.futures.as_completed(futs):
                try:
                    results_list.append(fut.result(timeout=3700))
                except concurrent.futures.TimeoutError:
                    w = futs[fut]
                    print(f"  [ERROR] {w[2]} future did not finish within 3700s")
                except Exception as exc:
                    w = futs[fut]
                    print(f"  [ERROR] {w[2]}: {exc}")

    for key, metrics in results_list:
        vault_entries.append(
            f"{key} -- stability={metrics['stability']:.3f} "
            f"id_sw={metrics['id_switches']} "
            f"ball={metrics['ball_valid_pct']:.1f}% "
            f"({metrics['frames']} frames, {metrics['duration_s']:.0f}s)"
        )

    total_elapsed = time.time() - total_t0
    print(f"Phase G complete -- {len(videos)} games in {total_elapsed:.0f}s")
    print(f"Metrics log : {METRICS_LOG}")

    _log_to_vault(vault_entries)

    # Print aggregate summary
    if METRICS_LOG.exists():
        import statistics
        rows = []
        with open(METRICS_LOG) as f:
            for row in csv.DictReader(f):
                try:
                    rows.append({
                        "stability":    float(row["stability"]),
                        "id_switches":  int(row["id_switches"]),
                        "ball_valid":   float(row["ball_valid_pct"]),
                    })
                except (ValueError, KeyError):
                    pass
        if rows:
            print("\n-- Aggregate across all processed games -------------")
            print(f"  stability  avg={statistics.mean(r['stability'] for r in rows):.3f}")
            print(f"  id_switches avg={statistics.mean(r['id_switches'] for r in rows):.1f}")
            print(f"  ball_valid  avg={statistics.mean(r['ball_valid'] for r in rows):.1f}%")


if __name__ == "__main__":
    main()
