#!/usr/bin/env python3
"""Sync pod's tracking outputs to a local backup directory.

Pulls (in priority order, all small):
  1. data/training/*.csv               (aggregates — most important)
  2. data/tracking/<gid>/*.csv         (per-game CSV outputs)
  3. data/tracking/<gid>/run.log       (diagnostics)

Skips:
  - large intermediate files (frames/, panoramas/, etc.) — useless locally
  - The .mp4 videos themselves (already deleted from pod after CLEAN)

Uses scp + tar for one-pass efficient transfer (no rsync needed; works on
plain Windows OpenSSH). Excludes already-up-to-date local files via mtime
comparison.

Local destination defaults to a sibling of the repo:
    C:\\Users\\neelj\\nba-data-backup\\

Usage:
    python scripts/sync_tracking_to_laptop.py
    python scripts/sync_tracking_to_laptop.py --dest /custom/path
    python scripts/sync_tracking_to_laptop.py --loop --interval 1800
"""
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import time
from pathlib import Path

POD_SSH_HOST = "root@213.192.2.86"
POD_SSH_PORT = "40045"
POD_REPO = "/workspace/nba-ai-system"
DEFAULT_DEST = Path(r"C:\Users\neelj\nba-data-backup")


def ssh(cmd: str) -> str:
    full = ["ssh", "-p", POD_SSH_PORT, "-o", "StrictHostKeyChecking=no",
            POD_SSH_HOST, cmd]
    r = subprocess.run(full, capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise RuntimeError(f"ssh failed: {r.stderr.strip()}")
    return r.stdout


def sync(dest: Path) -> dict:
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "tracking").mkdir(exist_ok=True)
    (dest / "training").mkdir(exist_ok=True)

    # 1. Sync data/training/*.csv (small, always pull all)
    print("[1/2] Syncing data/training/...")
    tar_cmd = (
        f"cd {POD_REPO}/data/training && "
        "tar c --exclude='__pycache__' *.csv 2>/dev/null"
    )
    full_ssh = ["ssh", "-p", POD_SSH_PORT, "-o", "StrictHostKeyChecking=no",
                POD_SSH_HOST, tar_cmd]
    extract = ["tar", "x", "-C", str(dest / "training")]
    p1 = subprocess.Popen(full_ssh, stdout=subprocess.PIPE)
    p2 = subprocess.Popen(extract, stdin=p1.stdout)
    p1.stdout.close()
    p2.wait()
    p1.wait()
    n_training = sum(1 for _ in (dest / "training").glob("*.csv"))
    print(f"   training files synced: {n_training}")

    # 2. Sync data/tracking/<gid>/{csv,log} — find which are newer on pod than local
    print("[2/2] Syncing data/tracking/...")
    # Get list of all game dirs + their pbp_shot_context.csv mtime as a "version marker"
    list_cmd = (
        f"for d in {POD_REPO}/data/tracking/00*/; do "
        "  gid=$(basename $d); "
        "  mt=$(stat -c%Y $d 2>/dev/null || echo 0); "
        "  echo \"$gid|$mt\"; "
        "done"
    )
    out = ssh(list_cmd)
    remote_games = {}
    for line in out.strip().splitlines():
        if "|" in line:
            gid, mt = line.split("|", 1)
            try:
                remote_games[gid] = int(mt)
            except ValueError:
                pass

    n_synced = 0
    n_skipped = 0
    n_total = len(remote_games)
    for i, (gid, remote_mt) in enumerate(remote_games.items(), 1):
        local_dir = dest / "tracking" / gid
        local_marker = local_dir / ".sync_mtime"
        if local_marker.exists():
            try:
                local_mt = int(local_marker.read_text().strip())
                if local_mt >= remote_mt:
                    n_skipped += 1
                    continue
            except ValueError:
                pass
        local_dir.mkdir(parents=True, exist_ok=True)
        # tar only the small files: .csv, .log, .json
        tar_cmd = (
            f"cd {POD_REPO}/data/tracking/{gid} && "
            "tar c --exclude='*.mp4' --exclude='*.npy' --exclude='__pycache__' "
            "*.csv *.log *.json 2>/dev/null || true"
        )
        full_ssh = ["ssh", "-p", POD_SSH_PORT, "-o", "StrictHostKeyChecking=no",
                    POD_SSH_HOST, tar_cmd]
        extract = ["tar", "x", "-C", str(local_dir)]
        p1 = subprocess.Popen(full_ssh, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL)
        p2 = subprocess.Popen(extract, stdin=p1.stdout,
                              stderr=subprocess.DEVNULL)
        p1.stdout.close()
        p2.wait()
        p1.wait()
        local_marker.write_text(str(remote_mt))
        n_synced += 1
        if i % 10 == 0:
            print(f"   ...synced {i}/{n_total}")
    print(f"   tracking dirs: {n_synced} synced, {n_skipped} up-to-date "
          f"(of {n_total} total)")

    # Summary
    total_size_mb = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file()) / (1024 * 1024)
    print(f"\nLocal backup: {dest}")
    print(f"  total size: {total_size_mb:.1f} MB")
    return {"synced": n_synced, "skipped": n_skipped, "total_mb": total_size_mb}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--interval", type=int, default=1800,
                    help="seconds between sync rounds when looping (default 30 min)")
    args = ap.parse_args()

    while True:
        try:
            r = sync(args.dest)
            print(f"\nOK: sync done at {time.strftime('%H:%M:%S')}  "
                  f"({r['synced']} new, {r['skipped']} up-to-date, {r['total_mb']:.0f} MB total)")
        except Exception as e:
            print(f"\n!! sync failed: {e}")
        if not args.loop:
            break
        print(f"\nsleeping {args.interval}s before next sync...")
        time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
