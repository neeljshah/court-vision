#!/usr/bin/env python3
"""Fetch NBA game videos LOCALLY (laptop) and push to RunPod.

Workaround for YouTube datacenter-IP block on the pod: your home IP isn't
blocked, so yt-dlp works locally. We pick the next queued YouTube URL from
the pod's queue.db, download here, scp to the pod's ingest/tmp/ directory
(no extension — the auto-loop's convention), and mark the game as
'downloaded' so it's not re-picked.

The pod's auto_ingest_track_loop.sh then sees the file appear in tmp/,
moves it to /root/nba_videos/<gid>.mp4, and spawns a tracker. No code
changes needed on the pod side.

Usage:
    python scripts/fetch_local.py                    # fetch 1 game
    python scripts/fetch_local.py --count 5          # fetch 5
    python scripts/fetch_local.py --loop --interval 60  # forever, 60s between batches
    python scripts/fetch_local.py --game-id 0022500300  # specific game
    python scripts/fetch_local.py --dry-run          # show what would happen

Requirements (local machine):
    - yt-dlp on PATH
    - ffmpeg on PATH
    - ssh + scp on PATH (Windows: OpenSSH client built-in)
    - YouTube cookies at C:/Users/neelj/Downloads/cookies.txt (or set --cookies)
"""
from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# ─── Defaults ──────────────────────────────────────────────────────────────
POD_SSH_HOST = "root@213.192.2.86"
POD_SSH_PORT = "40045"
POD_INGEST_TMP = "/workspace/nba-ai-system/data/ingest/tmp"
POD_QUEUE_DB = "/workspace/nba-ai-system/data/ingest/queue.db"
LOCAL_COOKIES = r"C:\Users\neelj\Downloads\cookies.txt"
MIN_VIDEO_SIZE_MB = 100  # auto-loop's threshold for valid mp4


def ssh(cmd: str, *, capture: bool = True) -> str:
    """Run a command on the pod over ssh. Returns stdout."""
    full = ["ssh", "-p", POD_SSH_PORT, "-o", "StrictHostKeyChecking=no",
            POD_SSH_HOST, cmd]
    r = subprocess.run(full, capture_output=capture, text=True, check=False)
    if r.returncode != 0:
        raise RuntimeError(f"ssh failed (exit {r.returncode}): {r.stderr.strip()}")
    return r.stdout.strip()


def scp_to_pod(local: Path, remote: str) -> None:
    """scp a file to the pod."""
    full = ["scp", "-P", POD_SSH_PORT, "-o", "StrictHostKeyChecking=no",
            str(local), f"{POD_SSH_HOST}:{remote}"]
    r = subprocess.run(full, capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise RuntimeError(f"scp failed (exit {r.returncode}): {r.stderr.strip()}")


def pick_next_games(count: int) -> list[tuple[str, str]]:
    """Query pod's queue.db for next N queued/failed YouTube games."""
    # Prefer 'failed' (those that got blocked by YT) then 'queued'
    py = (
        "import sqlite3; "
        f"c=sqlite3.connect('{POD_QUEUE_DB}'); "
        "rows=c.execute(\"SELECT game_id, source_url FROM games WHERE "
        "source='youtube' AND status IN ('failed','queued') "
        "AND source_url IS NOT NULL "
        f"ORDER BY CASE status WHEN 'failed' THEN 0 ELSE 1 END, game_id LIMIT {count}\").fetchall(); "
        "[print(r[0]+'|'+r[1]) for r in rows]"
    )
    out = ssh(f"python3 -c {shlex.quote(py)}")
    return [tuple(line.split("|", 1)) for line in out.splitlines() if "|" in line]


def already_pushed(gid: str) -> bool:
    """Check if the gid is already on pod (in tmp, /root/nba_videos, archive, or tracked)."""
    cmd = (
        f"test -e {POD_INGEST_TMP}/{gid} || "
        f"test -e /root/nba_videos/{gid}.mp4 || "
        f"test -e /workspace/nba_videos_archive/{gid}.mp4 || "
        f"test -s /workspace/nba-ai-system/data/tracking/{gid}/tracking_data.csv"
    )
    r = subprocess.run(
        ["ssh", "-p", POD_SSH_PORT, "-o", "StrictHostKeyChecking=no",
         POD_SSH_HOST, cmd],
        capture_output=True, text=True, check=False,
    )
    return r.returncode == 0


def mark_downloaded(gid: str) -> None:
    """UPDATE queue.db: status='downloaded' so we don't re-pick."""
    py = (
        "import sqlite3; "
        f"c=sqlite3.connect('{POD_QUEUE_DB}'); "
        f"c.execute(\"UPDATE games SET status='downloaded', updated_at=datetime('now') "
        f"WHERE game_id='{gid}'\"); "
        "c.commit()"
    )
    ssh(f"python3 -c {shlex.quote(py)}")


def download_one(url: str, gid: str, dest_dir: Path, cookies: Path) -> Path | None:
    """yt-dlp the URL to dest_dir/<gid>.mp4."""
    out_template = str(dest_dir / f"{gid}.%(ext)s")
    cmd = [
        "yt-dlp",
        "--no-warnings",
        "--format", "bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--no-playlist",
        "--cookies", str(cookies),
        "--retries", "3",
        "--fragment-retries", "3",
        "--output", out_template,
        url,
    ]
    print(f"  [yt-dlp] {url}")
    start = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, check=False)
    elapsed = time.time() - start
    if r.returncode != 0:
        tail = (r.stderr or "")[-400:]
        print(f"  [yt-dlp FAIL in {elapsed:.0f}s] {tail}")
        return None
    # Find the produced file
    mp4 = dest_dir / f"{gid}.mp4"
    if not mp4.exists():
        candidates = list(dest_dir.glob(f"{gid}*"))
        if candidates:
            candidates[0].rename(mp4)
        else:
            print(f"  [yt-dlp] no output file produced for {gid}")
            return None
    size_mb = mp4.stat().st_size / (1024 * 1024)
    if size_mb < MIN_VIDEO_SIZE_MB:
        print(f"  [yt-dlp] file too small ({size_mb:.0f} MB < {MIN_VIDEO_SIZE_MB}) — skipping")
        mp4.unlink(missing_ok=True)
        return None
    print(f"  [yt-dlp OK in {elapsed:.0f}s] {size_mb:.0f} MB")
    return mp4


def push_one(local_mp4: Path, gid: str) -> bool:
    """Upload to pod's ingest/tmp/<gid> (no extension — auto-loop convention)."""
    # Stream to a temp name first, then rename atomically on pod so the auto-loop
    # doesn't pick up a partial file.
    remote_tmp = f"{POD_INGEST_TMP}/.{gid}.partial"
    remote_final = f"{POD_INGEST_TMP}/{gid}"
    print(f"  [scp] {local_mp4.name} -> pod:{remote_final}")
    start = time.time()
    try:
        scp_to_pod(local_mp4, remote_tmp)
        ssh(f"mv {remote_tmp} {remote_final}")
    except RuntimeError as e:
        print(f"  [scp FAIL] {e}")
        return False
    elapsed = time.time() - start
    print(f"  [scp OK in {elapsed:.0f}s]")
    return True


def fetch_round(count: int, cookies: Path, tmp_dir: Path, *, dry_run: bool,
                only_gid: str | None) -> int:
    """One round: pick → download → push → mark. Returns success count."""
    if only_gid:
        # Direct fetch for one specific game
        py = (
            "import sqlite3; "
            f"c=sqlite3.connect('{POD_QUEUE_DB}'); "
            f"r=c.execute(\"SELECT source_url FROM games WHERE game_id='{only_gid}'\").fetchone(); "
            "print(r[0] if r else '')"
        )
        url = ssh(f"python3 -c {shlex.quote(py)}").strip()
        if not url:
            print(f"  no URL in queue.db for {only_gid}")
            return 0
        pairs = [(only_gid, url)]
    else:
        pairs = pick_next_games(count)

    if not pairs:
        print("  queue empty — no games to fetch")
        return 0

    n_ok = 0
    for gid, url in pairs:
        print(f"\n=== {gid}  {url} ===")
        if already_pushed(gid):
            print("  already on pod — skipping")
            if not dry_run:
                mark_downloaded(gid)
            continue
        if dry_run:
            print("  [DRY RUN] would download + push")
            continue
        mp4 = download_one(url, gid, tmp_dir, cookies)
        if not mp4:
            continue
        try:
            if push_one(mp4, gid):
                mark_downloaded(gid)
                n_ok += 1
        finally:
            mp4.unlink(missing_ok=True)  # clean local copy
    return n_ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=1, help="games per round")
    ap.add_argument("--loop", action="store_true", help="run forever")
    ap.add_argument("--interval", type=int, default=60, help="seconds between rounds when looping")
    ap.add_argument("--game-id", help="fetch one specific game (overrides --count)")
    ap.add_argument("--cookies", default=LOCAL_COOKIES, help="cookies.txt path")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cookies = Path(args.cookies)
    if not cookies.exists():
        print(f"ERROR: cookies file not found: {cookies}", file=sys.stderr)
        return 1

    for tool in ("yt-dlp", "scp", "ssh"):
        if shutil.which(tool) is None:
            print(f"ERROR: {tool} not on PATH", file=sys.stderr)
            return 1

    tmp = Path(tempfile.mkdtemp(prefix="fetch_local_"))
    print(f"Using temp dir: {tmp}")

    try:
        round_n = 0
        total_ok = 0
        while True:
            round_n += 1
            print(f"\n========== round {round_n} ==========")
            n_ok = fetch_round(args.count, cookies, tmp,
                               dry_run=args.dry_run, only_gid=args.game_id)
            total_ok += n_ok
            print(f"\nround {round_n}: {n_ok} pushed   (total {total_ok})")
            if not args.loop or args.game_id:
                break
            print(f"\nsleeping {args.interval}s before next round...")
            time.sleep(args.interval)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
