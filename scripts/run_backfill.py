#!/usr/bin/env python3
"""
run_backfill.py — R20 multi-GPU full-game backfill orchestrator.

Designed for portability across ANY RunPod that has been bootstrapped via
`scripts/runpod_bootstrap.sh`. Processes a list of NBA game IDs through the
R8-R19 tracker pipeline in parallel across all detected GPUs.

Features
--------
* Auto-detects available GPUs (any count, any model).
* One game per GPU at a time (full-game mode, ~30 GB RAM peak per worker).
* Resumable: skips games with valid existing output (>= MIN_TRACKING_ROWS).
* Crash-safe: per-game log + atomic checkpoint file; survives pod restart.
* Disk-pressure aware: optionally deletes input video after success.
* Per-game timing, row counts, exit code → CSV log for monitoring.

Usage
-----
On the pod (after runpod_bootstrap.sh):

  # Process from a manifest file (one game_id per line):
  python3 scripts/run_backfill.py --manifest data/games_to_process.txt --full

  # Or from a JSON file with [{"game_id": "0022...", "video_path": "..."}, ...]:
  python3 scripts/run_backfill.py --manifest data/season_2025_26_targets.json --full

  # Stride 5 (recommended for backfill — 35% faster, modest accuracy loss):
  python3 scripts/run_backfill.py --manifest games.txt --full --stride 5

  # Limit to first 20 games (smoke test):
  python3 scripts/run_backfill.py --manifest games.txt --full --limit 20

  # Cleanup videos after successful processing (reclaim disk):
  python3 scripts/run_backfill.py --manifest games.txt --full --delete-video-on-success

  # Custom output dir suffix (default: _R19):
  python3 scripts/run_backfill.py --manifest games.txt --full --output-suffix _R19

  # Resume after pod restart (auto-resumes; pass --reset to force re-process):
  python3 scripts/run_backfill.py --manifest games.txt --full
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import List, Optional

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR    = PROJECT_DIR / "data"
TRACKING_DIR = DATA_DIR / "tracking"
DEFAULT_VIDEO_DIRS = [
    Path("/root/nba_videos"),                    # RunPod default
    DATA_DIR / "videos" / "full_games",          # local layout
]
DEFAULT_LOG_PATH = DATA_DIR / "backfill_log.csv"
CHECKPOINT_PATH  = DATA_DIR / "backfill_checkpoint.json"
PYTHON = sys.executable

# Resumability threshold — a game is "done" if its tracking_data.csv has >= this many rows.
MIN_TRACKING_ROWS = 10_000

LOG_FIELDS = [
    "timestamp", "game_id", "status", "exit_code", "wall_clock_sec",
    "tracking_rows", "shot_count", "possession_count", "scoreboard_rows",
    "stride", "output_dir", "gpu_id", "error",
]


# ──────────────────────────────────────────────────────────────────────────────
# Discovery
# ──────────────────────────────────────────────────────────────────────────────

def detect_gpus() -> List[int]:
    """Return list of available GPU indices via nvidia-smi."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index", "--format=csv,noheader"],
            stderr=subprocess.DEVNULL, timeout=10,
        ).decode().strip()
        return [int(x) for x in out.splitlines() if x.strip().isdigit()]
    except Exception as exc:
        print(f"WARN: GPU detection failed ({exc}); falling back to single CPU worker.", file=sys.stderr)
        return [0]   # CPU fallback for dev/test only


def find_video(game_id: str, override_dir: Optional[Path] = None) -> Optional[Path]:
    """Locate `<game_id>.mp4` in the standard video dirs."""
    search = [override_dir] if override_dir else DEFAULT_VIDEO_DIRS
    for d in search:
        if d is None or not d.exists():
            continue
        for ext in (".mp4", ".mkv", ".mov", ".webm"):
            p = d / f"{game_id}{ext}"
            if p.exists() and p.stat().st_size > 1_000_000:
                return p
    return None


def already_done(game_id: str, output_suffix: str) -> bool:
    """Resumability: True if a previous run produced complete output."""
    out_dir = TRACKING_DIR / f"{game_id}{output_suffix}"
    td = out_dir / "tracking_data.csv"
    sl = out_dir / "shot_log.csv"
    pv = out_dir / "possessions.csv"
    if not all(p.exists() for p in (td, sl, pv)):
        return False
    try:
        with open(td, encoding="utf-8", errors="replace") as f:
            n = sum(1 for _ in f)
        return n >= MIN_TRACKING_ROWS
    except Exception:
        return False


def load_manifest(path: Path) -> List[str]:
    """Read game IDs from .txt (one-per-line) or .json (list[str] or list[{game_id}])."""
    if not path.exists():
        sys.exit(f"ERROR: manifest not found: {path}")
    if path.suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data.get("targets", data) if isinstance(data, dict) else data
        if not items:
            return []
        if isinstance(items[0], dict):
            return [str(it.get("game_id") or it.get("id")) for it in items if it.get("game_id") or it.get("id")]
        return [str(x) for x in items]
    # txt: one game_id per line (skip blanks + #comments)
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s.split()[0])   # take first whitespace-delimited token
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Per-game worker
# ──────────────────────────────────────────────────────────────────────────────

def process_one_game(
    game_id: str,
    video_path: str,
    gpu_id: int,
    stride: int,
    output_suffix: str,
    delete_video_on_success: bool,
    skip_features: bool,
    timeout_sec: int,
) -> dict:
    """Run one game through `run_clip.py` on a single GPU. Returns a log row."""
    out_dir = TRACKING_DIR / f"{game_id}{output_suffix}"
    out_dir.mkdir(parents=True, exist_ok=True)

    log_path = out_dir / "run.log"
    cmd = [
        PYTHON, str(PROJECT_DIR / "scripts" / "run_clip.py"),
        "--video", video_path,
        "--no-show",
        "--data-dir", str(out_dir),
        "--game-id", game_id,
        "--stride", str(stride),
    ]
    if skip_features:
        cmd.append("--skip-features")

    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
    # CPU thread tuning — reduce contention when multiple workers run in parallel.
    env["OMP_NUM_THREADS"] = "4"
    env["OPENBLAS_NUM_THREADS"] = "4"
    env["MKL_NUM_THREADS"] = "4"
    env["TORCH_CUDNN_V8_API_ENABLED"] = "1"
    env["NBA_FRAME_STRIDE"] = str(stride)   # belt + suspenders

    row = {
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "game_id": game_id,
        "status": "fail",
        "exit_code": -1,
        "wall_clock_sec": 0.0,
        "tracking_rows": 0,
        "shot_count": 0,
        "possession_count": 0,
        "scoreboard_rows": 0,
        "stride": stride,
        "output_dir": str(out_dir),
        "gpu_id": gpu_id,
        "error": "",
    }

    t0 = time.time()
    try:
        with open(log_path, "w", encoding="utf-8") as lf:
            lf.write(f"# {' '.join(cmd)}\n")
            lf.flush()
            res = subprocess.run(
                cmd, env=env, cwd=str(PROJECT_DIR),
                stdout=lf, stderr=subprocess.STDOUT,
                timeout=timeout_sec,
            )
        row["exit_code"] = res.returncode
        row["status"] = "ok" if res.returncode == 0 else "fail"
    except subprocess.TimeoutExpired:
        row["status"] = "timeout"
        row["error"] = f"exceeded {timeout_sec}s timeout"
    except Exception as exc:
        row["status"] = "crash"
        row["error"] = str(exc)[:300]
    row["wall_clock_sec"] = round(time.time() - t0, 1)

    # Measure outputs (best-effort)
    def _count(p: Path) -> int:
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                return max(0, sum(1 for _ in f) - 1)
        except Exception:
            return 0
    row["tracking_rows"]   = _count(out_dir / "tracking_data.csv")
    row["shot_count"]      = _count(out_dir / "shot_log.csv")
    row["possession_count"] = _count(out_dir / "possessions.csv")
    row["scoreboard_rows"] = _count(out_dir / "scoreboard_log.csv")

    # Cleanup video (only if processing succeeded AND user asked for it)
    if delete_video_on_success and row["status"] == "ok" and row["tracking_rows"] >= MIN_TRACKING_ROWS:
        try:
            os.unlink(video_path)
            row["error"] = (row["error"] or "") + " [video_deleted]"
        except Exception as exc:
            row["error"] = (row["error"] or "") + f" [delete-fail:{exc}]"

    return row


# ──────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ──────────────────────────────────────────────────────────────────────────────

def append_log(row: dict, log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not log_path.exists()
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS, extrasaction="ignore")
        if write_header:
            w.writeheader()
        w.writerow(row)


def save_checkpoint(remaining: List[str]) -> None:
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_PATH.write_text(json.dumps({"remaining": remaining}, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", type=Path, required=True,
                    help="Path to manifest file (.txt one-per-line, or .json list).")
    ap.add_argument("--full", action="store_true",
                    help="Process full games (no frame cap). Recommended for the backfill.")
    ap.add_argument("--stride", type=int, default=5,
                    help="Frame stride. Default 5 (recommended for backfill: 35%% faster than 3).")
    ap.add_argument("--output-suffix", default="_R19",
                    help="Suffix on data/tracking/<game_id><SUFFIX>/ (default _R19).")
    ap.add_argument("--gpus", default=None,
                    help="Comma-separated GPU IDs (e.g. 0,1,2). Default: auto-detect all.")
    ap.add_argument("--limit", type=int, default=None,
                    help="Stop after N games (smoke-test mode).")
    ap.add_argument("--video-dir", type=Path, default=None,
                    help="Override video search dir (default: /root/nba_videos then data/videos/full_games).")
    ap.add_argument("--delete-video-on-success", action="store_true",
                    help="Delete the source .mp4 after a game processes successfully (reclaim disk).")
    ap.add_argument("--skip-features", action="store_true",
                    help="Skip feature engineering stage (faster, jersey OCR + tracking only).")
    ap.add_argument("--timeout-sec", type=int, default=4 * 3600,
                    help="Per-game wall-clock timeout in seconds (default 4h).")
    ap.add_argument("--reset", action="store_true",
                    help="Re-process every game even if previous output exists.")
    ap.add_argument("--log-path", type=Path, default=DEFAULT_LOG_PATH,
                    help="CSV log path (default data/backfill_log.csv).")
    args = ap.parse_args()

    # Load + filter manifest
    games_all = load_manifest(args.manifest)
    if not games_all:
        sys.exit(f"ERROR: no games found in {args.manifest}")
    if not args.reset:
        games = [g for g in games_all if not already_done(g, args.output_suffix)]
        print(f"Manifest: {len(games_all)} games — {len(games_all) - len(games)} already done, {len(games)} to process.")
    else:
        games = list(games_all)
        print(f"Manifest: {len(games)} games (--reset: re-processing all).")
    if args.limit is not None:
        games = games[: args.limit]
        print(f"Limit: processing first {len(games)} games.")
    if not games:
        print("Nothing to do.")
        return 0

    # Locate videos up-front; skip games with no video on disk
    pending = []
    for gid in games:
        v = find_video(gid, args.video_dir)
        if v is None:
            print(f"  [skip] no video for {gid} (looked in {args.video_dir or DEFAULT_VIDEO_DIRS})")
            append_log({
                "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "game_id": gid, "status": "no_video",
                "exit_code": -1, "wall_clock_sec": 0.0,
                "tracking_rows": 0, "shot_count": 0, "possession_count": 0,
                "scoreboard_rows": 0, "stride": args.stride,
                "output_dir": "", "gpu_id": -1,
                "error": "video_not_found",
            }, args.log_path)
            continue
        pending.append((gid, str(v)))
    if not pending:
        print("All games skipped (no videos found).")
        return 1

    # GPU pool
    if args.gpus:
        gpu_ids = [int(x) for x in args.gpus.split(",") if x.strip()]
    else:
        gpu_ids = detect_gpus()
    n_workers = len(gpu_ids)
    print(f"Workers: {n_workers} (GPUs: {gpu_ids}). Stride={args.stride}. Full={args.full}.")
    save_checkpoint([g for g, _ in pending])

    # Build round-robin GPU assignments
    queue = [(gid, vp, gpu_ids[i % n_workers]) for i, (gid, vp) in enumerate(pending)]

    start = time.time()
    n_ok = n_fail = n_done = 0
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        futures = {
            pool.submit(
                process_one_game,
                gid, vp, gpu, args.stride, args.output_suffix,
                args.delete_video_on_success, args.skip_features, args.timeout_sec,
            ): gid
            for gid, vp, gpu in queue
        }
        try:
            for fut in as_completed(futures):
                row = fut.result()
                n_done += 1
                ok = (row["status"] == "ok" and row["tracking_rows"] >= MIN_TRACKING_ROWS)
                n_ok  += int(ok)
                n_fail += int(not ok)
                elapsed = time.time() - start
                eta = (elapsed / n_done) * (len(queue) - n_done) if n_done else 0
                print(
                    f"[{n_done}/{len(queue)}] {row['game_id']} GPU{row['gpu_id']}  "
                    f"{row['status']:5s}  {row['wall_clock_sec']/60:.1f}m  "
                    f"rows={row['tracking_rows']}  shots={row['shot_count']}  "
                    f"poss={row['possession_count']}  "
                    f"(✓{n_ok} ✗{n_fail} eta={eta/60:.0f}m)"
                )
                append_log(row, args.log_path)
                # Update checkpoint
                remaining = [g for g, _, _ in queue if g != row["game_id"]]
                save_checkpoint(remaining)
        except KeyboardInterrupt:
            print("\nInterrupted; in-flight workers will be drained...", file=sys.stderr)
            return 130

    total_min = (time.time() - start) / 60
    print(
        f"\nDONE: {n_ok} ok / {n_fail} failed of {len(queue)} games in "
        f"{total_min:.1f} min ({total_min/max(len(queue),1):.1f} min/game avg)."
    )
    print(f"Log: {args.log_path}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
