#!/usr/bin/env python3
"""ingest_one_game.py — End-to-end per-game ingest orchestrator.

Drives the pod via SSH to:
  1. Download video on pod (yt-dlp via scripts/fetch_games.py)
  2. Run unified pipeline on pod (scripts/run_clip)
  3. Pull outputs to local nba-data-backup/tracking/<game_id>/
  4. Delete the pod-side .mp4 (and pod tracking dir if --cleanup-pod)
  5. Log the result to nba-data-backup/.ingest_log.csv

Designed for the 100-game push: idempotent, resumable, logs everything.

Usage:
    # Process one game end-to-end (downloads if missing)
    python scripts/ingest_one_game.py 0022500279

    # Process a list from a file (one game_id per line)
    python scripts/ingest_one_game.py --batch games.txt

    # Process the next N from the NBA schedule (auto-discover)
    python scripts/ingest_one_game.py --auto 5

    # Short test mode (6k frames instead of full game)
    python scripts/ingest_one_game.py 0022500279 --short

    # Keep pod tracking dir after sync (for debugging)
    python scripts/ingest_one_game.py 0022500279 --keep-pod-tracking
"""
from __future__ import annotations

import argparse
import csv
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# --- Pod config ---
POD_IP   = "213.192.2.86"
POD_PORT = "40045"
POD_USER = "root"
POD_REPO = "/workspace/nba-ai-system"
POD_VIDEO_DIR = "/root/nba_videos"

# --- Local config ---
LOCAL_BACKUP = Path(r"C:\Users\neelj\nba-data-backup")
LOCAL_TRACKING = LOCAL_BACKUP / "tracking"
INGEST_LOG = LOCAL_BACKUP / ".ingest_log.csv"

SSH_OPTS = ["-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=15",
            "-o", "ServerAliveInterval=60"]


def _ssh(cmd: str, timeout: int = 60) -> tuple[int, str, str]:
    """Run a command on the pod via SSH. Returns (rc, stdout, stderr)."""
    full = ["ssh", "-p", POD_PORT, *SSH_OPTS, f"{POD_USER}@{POD_IP}", cmd]
    r = subprocess.run(full, capture_output=True, text=True, timeout=timeout,
                       encoding="utf-8", errors="replace")
    return r.returncode, r.stdout, r.stderr


def _scp_from_pod(remote_path: str, local_path: Path, recursive: bool = False) -> bool:
    """SCP a file or dir from pod to local. Returns True on success."""
    local_path.parent.mkdir(parents=True, exist_ok=True)
    flags = ["-r"] if recursive else []
    cmd = ["scp", "-P", POD_PORT, *SSH_OPTS, *flags,
           f"{POD_USER}@{POD_IP}:{remote_path}", str(local_path)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                       encoding="utf-8", errors="replace")
    return r.returncode == 0


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _log_result(game_id: str, status: str, message: str, t_total: float):
    """Append one row to the ingest log."""
    INGEST_LOG.parent.mkdir(parents=True, exist_ok=True)
    is_new = not INGEST_LOG.exists()
    with open(INGEST_LOG, "a", newline="") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["timestamp", "game_id", "status", "wall_seconds",
                       "message"])
        w.writerow([_ts(), game_id, status, f"{t_total:.1f}", message])


def _check_pod_alive() -> bool:
    rc, _, _ = _ssh("echo alive", timeout=10)
    return rc == 0


def _ensure_pod_video(game_id: str, full_game: bool = True,
                      verbose: bool = True) -> bool:
    """Make sure the video exists at /root/nba_videos/<game_id>.mp4.
    Downloads via fetch_games.py if missing."""
    check = f"test -s {POD_VIDEO_DIR}/{game_id}.mp4 && echo EXISTS || echo MISSING"
    rc, out, _ = _ssh(check)
    if "EXISTS" in out:
        if verbose:
            print(f"   [ok] video already on pod")
        return True

    if verbose:
        print(f"   [download] fetching {game_id} via yt-dlp...")

    full_flag = "--full" if full_game else ""
    dl_cmd = (
        f"cd {POD_REPO} && "
        f"python3 scripts/fetch_games.py {full_flag} --game-id {game_id} "
        f"--out-dir {POD_VIDEO_DIR} 2>&1 | tail -20"
    )
    rc, out, err = _ssh(dl_cmd, timeout=900)  # 15 min for download
    if verbose:
        if out.strip():
            print(f"   [download] tail: ...{out.strip()[-200:]}")
    rc2, out2, _ = _ssh(check)
    if "EXISTS" in out2:
        return True
    if verbose:
        print(f"   [fail] download did not produce video on pod")
    return False


def _run_pipeline(game_id: str, short: bool = False, verbose: bool = True) -> bool:
    """Run the unified pipeline on the pod. Returns True on success."""
    out_dir = f"{POD_REPO}/data/tracking/{game_id}"
    video_path = f"{POD_VIDEO_DIR}/{game_id}.mp4"

    # Build the run_clip command
    extra = ""
    if short:
        extra = "--frames 6000 --start-frame 8000"

    # Mode: short bypasses preflight (sampling early frames often hits low-person
    # commercial/intro segments) via COURTV_NO_OCR=1; full-game mode keeps
    # preflight + real OCR for jersey -> player_name resolution.
    env = (
        "OMP_NUM_THREADS=12 MKL_NUM_THREADS=12 "
        "OPENBLAS_NUM_THREADS=12 NUMEXPR_NUM_THREADS=12 "
        "PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True "
        "MALLOC_ARENA_MAX=1"
    )
    if short:
        env += " COURTV_NO_OCR=1"
    cmd = (
        f"cd {POD_REPO} && mkdir -p {out_dir} && "
        f"env {env} timeout 7200 python3 -m scripts.run_clip "
        f"--video {video_path} --game-id {game_id} "
        f"--no-show --data-dir {out_dir} {extra}"
    )
    if verbose:
        print(f"   [pipeline] starting on pod...")
    t0 = time.time()
    # Run in foreground with long timeout — pipeline can take 30-90 min for full game
    rc, out, err = _ssh(cmd, timeout=8000)
    elapsed = time.time() - t0
    # Verify outputs exist
    check_cmd = (
        f"for f in tracking_data.csv possessions.csv shot_log.csv; do "
        f"  test -s {out_dir}/$f && echo OK_$f || echo MISS_$f; "
        f"done"
    )
    rc2, out2, _ = _ssh(check_cmd)
    missing = [line for line in out2.splitlines() if line.startswith("MISS_")]
    if verbose:
        print(f"   [pipeline] done in {elapsed:.0f}s, outputs: {out2.strip()}")
    return rc == 0 and not missing


def _sync_to_local(game_id: str, verbose: bool = True) -> bool:
    """Pull pod tracking dir to local backup. Excludes .mp4/.npy."""
    local_dir = LOCAL_TRACKING / game_id
    local_dir.mkdir(parents=True, exist_ok=True)

    # Use tar through SSH for efficient multi-file pull
    tar_cmd = (
        f"cd {POD_REPO}/data/tracking/{game_id} && "
        "tar c --exclude='*.mp4' --exclude='*.npy' --exclude='__pycache__' "
        "--exclude='*.bak_*' "
        "*.csv *.log *.json 2>/dev/null || true"
    )
    full = ["ssh", "-p", POD_PORT, *SSH_OPTS,
            f"{POD_USER}@{POD_IP}", tar_cmd]
    extract = ["tar", "x", "-C", str(local_dir)]

    p1 = subprocess.Popen(full, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL)
    p2 = subprocess.Popen(extract, stdin=p1.stdout,
                          stderr=subprocess.DEVNULL)
    p1.stdout.close()
    rc2 = p2.wait(timeout=300)
    rc1 = p1.wait(timeout=10)

    # Verify
    expected = ["tracking_data.csv", "possessions.csv", "shot_log.csv"]
    missing = [f for f in expected if not (local_dir / f).exists()]
    if verbose:
        n_files = sum(1 for _ in local_dir.rglob("*") if _.is_file())
        size_mb = sum(f.stat().st_size for f in local_dir.rglob("*")
                      if f.is_file()) / 1024 / 1024
        print(f"   [sync] {n_files} files, {size_mb:.1f} MB pulled to {local_dir}")
        if missing:
            print(f"   [sync] WARN missing expected files: {missing}")
    return not missing


def _cleanup_pod_video(game_id: str, verbose: bool = True) -> bool:
    """Delete the source video on the pod."""
    rm_cmd = f"rm -f {POD_VIDEO_DIR}/{game_id}.mp4"
    rc, _, _ = _ssh(rm_cmd)
    if verbose:
        print(f"   [cleanup] removed pod video {game_id}.mp4")
    return rc == 0


def _cleanup_pod_tracking(game_id: str, verbose: bool = True) -> bool:
    """Delete the pod-side tracking dir (after sync). Keeps disk free."""
    rm_cmd = f"rm -rf {POD_REPO}/data/tracking/{game_id}"
    rc, _, _ = _ssh(rm_cmd)
    if verbose:
        print(f"   [cleanup] removed pod tracking dir")
    return rc == 0


def _cleanup_local_video(game_id: str, verbose: bool = True) -> bool:
    """Delete any local-staged copy of the video."""
    candidates = [
        Path.home() / "nba-ai-system" / "data" / "videos" / "full_games" / f"{game_id}.mp4",
        Path.home() / "nba-videos" / f"{game_id}.mp4",
    ]
    n = 0
    for p in candidates:
        if p.exists():
            try:
                p.unlink()
                n += 1
                if verbose:
                    print(f"   [cleanup] removed local video {p}")
            except Exception as e:
                if verbose:
                    print(f"   [cleanup] failed to delete {p}: {e}")
    return True


def process_one(game_id: str, short: bool = False,
                cleanup_pod: bool = True,
                keep_pod_tracking: bool = False,
                full_game: bool = True) -> bool:
    """End-to-end pipeline for one game. Returns True on success."""
    print(f"\n{'='*70}\n[{_ts()}] GAME {game_id} (short={short}, cleanup={cleanup_pod})\n{'='*70}")
    t0 = time.time()

    if not _check_pod_alive():
        msg = "pod unreachable"
        print(f"   [fatal] {msg}")
        _log_result(game_id, "FAIL", msg, time.time() - t0)
        return False

    # Step 1: video on pod?
    print(f"\n[1/4] Video acquisition")
    if not _ensure_pod_video(game_id, full_game=full_game):
        msg = "video download failed"
        _log_result(game_id, "FAIL", msg, time.time() - t0)
        return False

    # Step 2: pipeline
    print(f"\n[2/4] Pipeline (track + enrich + features)")
    if not _run_pipeline(game_id, short=short):
        msg = "pipeline run failed or missing outputs"
        _log_result(game_id, "FAIL", msg, time.time() - t0)
        return False

    # Step 3: sync to local
    print(f"\n[3/4] Sync to local backup")
    if not _sync_to_local(game_id):
        msg = "local sync failed or missing required files"
        _log_result(game_id, "FAIL", msg, time.time() - t0)
        return False

    # Step 4: cleanup
    print(f"\n[4/4] Cleanup")
    if cleanup_pod:
        _cleanup_pod_video(game_id)
        if not keep_pod_tracking:
            _cleanup_pod_tracking(game_id)
    _cleanup_local_video(game_id)

    t_total = time.time() - t0
    print(f"\n[{_ts()}] DONE {game_id} in {t_total:.0f}s")
    _log_result(game_id, "OK", "end-to-end success", t_total)
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("game_id", nargs="?", help="Single game ID to process")
    ap.add_argument("--batch", type=Path,
                    help="File with one game_id per line")
    ap.add_argument("--auto", type=int, default=0,
                    help="Auto-discover N next games from NBA schedule")
    ap.add_argument("--short", action="store_true",
                    help="Process only 6000 frames (for testing)")
    ap.add_argument("--keep-video", action="store_true",
                    help="Do NOT delete the pod video after success")
    ap.add_argument("--keep-pod-tracking", action="store_true",
                    help="Do NOT delete the pod tracking dir after sync")
    ap.add_argument("--no-full-game", action="store_true",
                    help="Download a 15-min clip instead of full game (debug)")
    args = ap.parse_args()

    cleanup = not args.keep_video
    full = not args.no_full_game

    if args.batch:
        ids = [l.strip() for l in args.batch.read_text().splitlines() if l.strip()]
    elif args.auto:
        print("Auto-discover mode not yet wired — pass game_id or --batch instead",
              file=sys.stderr)
        return 1
    elif args.game_id:
        ids = [args.game_id]
    else:
        ap.print_help()
        return 1

    print(f"\nWill process {len(ids)} game(s): {ids}")
    n_ok = 0
    n_fail = 0
    for gid in ids:
        ok = process_one(gid, short=args.short, cleanup_pod=cleanup,
                        keep_pod_tracking=args.keep_pod_tracking,
                        full_game=full)
        if ok:
            n_ok += 1
        else:
            n_fail += 1
    print(f"\n{'='*70}\nFINAL: {n_ok} ok, {n_fail} failed (of {len(ids)})\n{'='*70}")
    return 0 if n_fail == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
