"""
download_locally_and_upload.py — Local-to-RunPod NBA video download pipeline.

RunPod datacenter IPs are bot-detected by YouTube (HTTP 403).
This script downloads on the local residential IP, then scp's to RunPod.

Usage:
    conda activate basketball_ai

    # Download and upload 3 games (default)
    python scripts/download_locally_and_upload.py

    # Custom date range
    python scripts/download_locally_and_upload.py --from 2026-04-18 --to 2026-05-28

    # Specific game IDs
    python scripts/download_locally_and_upload.py --game-ids 0042500201,0042500211

    # Dry run — show plan without downloading
    python scripts/download_locally_and_upload.py --dry-run

    # Limit count
    python scripts/download_locally_and_upload.py --count 1
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# Force UTF-8 stdout on Windows (avoids cp1252 UnicodeEncodeError)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── Paths ────────────────────────────────────────────────────────────────────
PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

COOKIES_FILE    = Path("C:/Users/neelj/AppData/Local/Temp/yt_cookies_5.txt")
LOCAL_DL_DIR    = Path("C:/Users/neelj/AppData/Local/Temp/nba_dl")
LOG_FILE        = PROJECT_DIR / "scripts" / "_local_dl_log.csv"
CONDA_BIN       = Path("C:/Users/neelj/anaconda3/envs/basketball_ai")
FFMPEG_DIR      = CONDA_BIN / "Library" / "bin"

# ── RunPod SSH details ────────────────────────────────────────────────────────
RUNPOD_HOST     = "213.192.2.121"
RUNPOD_PORT     = "40094"
RUNPOD_USER     = "root"
RUNPOD_DEST_DIR = "/root/nba_videos"
SSH_KEY         = Path("C:/Users/neelj/.ssh/id_rsa")

# yt-dlp format: H.264 mp4 ≤720p, never AV1/VP9 (OpenCV can't decode them)
YT_FORMAT = (
    "bestvideo[height<=720][vcodec^=avc1]+bestaudio[ext=m4a]"
    "/bestvideo[height<=720][vcodec!*=av01][vcodec!*=vp9][ext=mp4]+bestaudio[ext=m4a]"
    "/best[height<=720][vcodec!*=av01][vcodec!*=vp9][ext=mp4]"
    "/best[height<=720]"
)

# Minimum size to consider a download valid (30 MB)
MIN_VALID_BYTES = 30_000_000


# ── Helpers ──────────────────────────────────────────────────────────────────

def _ssh_cmd(remote_cmd: str) -> list[str]:
    return [
        "ssh",
        "-i", str(SSH_KEY),
        "-p", RUNPOD_PORT,
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
        f"{RUNPOD_USER}@{RUNPOD_HOST}",
        remote_cmd,
    ]


def _scp_cmd(local_path: Path, remote_path: str) -> list[str]:
    return [
        "scp",
        "-i", str(SSH_KEY),
        "-P", RUNPOD_PORT,
        "-o", "StrictHostKeyChecking=no",
        str(local_path),
        f"{RUNPOD_USER}@{RUNPOD_HOST}:{remote_path}",
    ]


def _remote_game_ids() -> set[str]:
    """Return set of game_ids already present as .mp4 on RunPod (size > 30 MB)."""
    result = subprocess.run(
        _ssh_cmd(
            f"find {RUNPOD_DEST_DIR} -name '*.mp4' -size +30M "
            f"-exec basename {{}} .mp4 \\; 2>/dev/null"
        ),
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        print(f"[WARN] Could not list RunPod videos: {result.stderr.strip()[:200]}")
        return set()
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def _log_result(game_id: str, status: str, size_mb: float, duration_sec: float) -> None:
    write_header = not LOG_FILE.exists()
    with LOG_FILE.open("a", newline="") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["timestamp", "game_id", "status", "size_mb", "duration_sec"])
        w.writerow([
            datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            game_id, status, f"{size_mb:.1f}", f"{duration_sec:.1f}",
        ])


def _build_ytdlp_cmd(game: dict, out_path: Path) -> list[str]:
    """Build yt-dlp search+download command for a game."""
    date_obj  = datetime.strptime(game["date"], "%Y-%m-%d")
    date_str  = date_obj.strftime("%B %d %Y")
    away      = game["away"]
    home      = game["home"]

    # Import team name helpers from fetch_games without running main()
    from scripts.fetch_games import _team_full, _team_city, _current_nba_season
    away_full = _team_full(away)
    home_full = _team_full(home)
    season    = _current_nba_season()

    query = f"ytsearch3:NBA full game {away_full} vs {home_full} {date_str} replay {season}"

    cmd = ["yt-dlp"]

    # ffmpeg location (conda env)
    if (FFMPEG_DIR / "ffmpeg.exe").exists():
        cmd += ["--ffmpeg-location", str(FFMPEG_DIR)]

    if COOKIES_FILE.exists():
        cmd += ["--cookies", str(COOKIES_FILE)]

    cmd += [
        "--no-playlist",
        "--format", YT_FORMAT,
        "--merge-output-format", "mp4",
        "--output", str(out_path),
        "--no-warnings",
        "--no-abort-on-error",
        "--match-filter", "duration > 300",  # reject shorts < 5 min
        query,
    ]
    return cmd


def _download_game(game: dict, dry_run: bool) -> tuple[bool, float, float]:
    """Download a game locally. Returns (success, size_mb, duration_sec)."""
    game_id = game["game_id"]
    LOCAL_DL_DIR.mkdir(parents=True, exist_ok=True)
    out_path = LOCAL_DL_DIR / f"{game_id}.mp4"

    # Clean up any previous partial download
    if out_path.exists():
        out_path.unlink()

    cmd = _build_ytdlp_cmd(game, out_path)
    print(f"  [yt-dlp] {' '.join(cmd[:6])} ...")

    if dry_run:
        print("  [dry-run] would run yt-dlp")
        return False, 0.0, 0.0

    t0 = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        print("  [ERROR] yt-dlp timed out after 600s")
        return False, 0.0, time.time() - t0
    except Exception as e:
        print(f"  [ERROR] yt-dlp exception: {e}")
        return False, 0.0, time.time() - t0

    elapsed = time.time() - t0

    if not out_path.exists():
        print(f"  [ERROR] Output file not created. stderr: {proc.stderr[-300:]}")
        return False, 0.0, elapsed

    size = out_path.stat().st_size
    size_mb = size / 1024 / 1024

    if size < MIN_VALID_BYTES:
        print(f"  [ERROR] File too small ({size_mb:.1f} MB) — likely failed download")
        try:
            out_path.unlink()
        except Exception:
            pass
        return False, size_mb, elapsed

    print(f"  [OK] Downloaded {size_mb:.1f} MB in {elapsed:.0f}s")
    return True, size_mb, elapsed


def _upload_game(game_id: str, dry_run: bool) -> bool:
    """SCP local file to RunPod. Returns True on success."""
    local_path = LOCAL_DL_DIR / f"{game_id}.mp4"
    remote_path = f"{RUNPOD_DEST_DIR}/{game_id}.mp4"

    if dry_run:
        print(f"  [dry-run] would scp {local_path} → {remote_path}")
        return False

    print(f"  [scp] Uploading {local_path.stat().st_size // 1024 // 1024} MB to RunPod ...")
    t0 = time.time()
    try:
        proc = subprocess.run(
            _scp_cmd(local_path, remote_path),
            capture_output=True, text=True, timeout=900,
        )
    except subprocess.TimeoutExpired:
        print("  [ERROR] scp timed out after 900s")
        return False
    except Exception as e:
        print(f"  [ERROR] scp exception: {e}")
        return False

    if proc.returncode != 0:
        print(f"  [ERROR] scp failed (rc={proc.returncode}): {proc.stderr.strip()[:200]}")
        return False

    elapsed = time.time() - t0
    print(f"  [OK] Uploaded in {elapsed:.0f}s")
    return True


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Download NBA clips locally + upload to RunPod (bypasses YT bot detection)"
    )
    ap.add_argument("--count",     type=int, default=3,
                    help="Max games to process per run (default 3)")
    ap.add_argument("--from",      dest="from_date", default="2026-04-18",
                    help="Start date YYYY-MM-DD (default 2026-04-18)")
    ap.add_argument("--to",        dest="to_date",   default="2026-05-28",
                    help="End date YYYY-MM-DD (default 2026-05-28)")
    ap.add_argument("--game-ids",  dest="game_ids",  default=None,
                    help="Comma-separated game IDs to force (bypasses NBA API)")
    ap.add_argument("--dry-run",   action="store_true",
                    help="Show plan without downloading or uploading")
    args = ap.parse_args()

    # ── Step 1: Identify candidate games ────────────────────────────────────
    if args.game_ids:
        # Manual override — look up matchup from NBA API for display
        from scripts.fetch_games import _get_recent_games
        forced_ids = [g.strip() for g in args.game_ids.split(",") if g.strip()]
        all_games = _get_recent_games(
            count=10000, from_date="2025-10-01", to_date="2026-06-30"
        )
        id_to_game = {g["game_id"]: g for g in all_games}
        candidates = []
        for gid in forced_ids:
            if gid in id_to_game:
                candidates.append(id_to_game[gid])
            else:
                # Construct minimal placeholder
                candidates.append({
                    "game_id": gid, "date": "2026-05-01",
                    "away": "???", "home": "???",
                })
    else:
        from scripts.fetch_games import _get_recent_games
        print(f"Fetching playoff games {args.from_date} to {args.to_date} ...")
        candidates = _get_recent_games(
            count=args.count * 4,  # fetch extra, filter below
            from_date=args.from_date,
            to_date=args.to_date,
        )

    if not candidates:
        print("[ERROR] No games found from NBA API.")
        sys.exit(1)

    # ── Step 2: Filter out games already on RunPod ───────────────────────────
    print("Checking RunPod for already-uploaded games ...")
    remote_ids = set() if args.dry_run else _remote_game_ids()
    print(f"  {len(remote_ids)} games already on RunPod: {sorted(remote_ids)}")

    pending = [g for g in candidates if g["game_id"] not in remote_ids]
    pending = pending[: args.count]

    if not pending:
        print("All candidate games already on RunPod. Nothing to do.")
        return

    print(f"\nPlan: {len(pending)} game(s) to download + upload:")
    for g in pending:
        print(f"  {g['game_id']}  {g.get('away','?')} @ {g.get('home','?')}  {g.get('date','?')}")

    if args.dry_run:
        print("\n[dry-run] Stopping here.")
        return

    # ── Step 3: Download + Upload each game ──────────────────────────────────
    results: list[dict] = []
    for game in pending:
        gid = game["game_id"]
        print(f"\n-- {gid}  {game.get('away','?')} @ {game.get('home','?')}  {game.get('date','?')}")

        # Download locally
        ok_dl, size_mb, dur_s = _download_game(game, dry_run=False)
        if not ok_dl:
            _log_result(gid, "DOWNLOAD_FAIL", size_mb, dur_s)
            results.append({"game_id": gid, "status": "DOWNLOAD_FAIL"})
            continue

        # Upload to RunPod
        ok_up = _upload_game(gid, dry_run=False)
        local_path = LOCAL_DL_DIR / f"{gid}.mp4"

        if ok_up:
            # Delete local copy to save disk
            try:
                local_path.unlink()
                print(f"  [cleanup] Deleted local copy")
            except Exception as e:
                print(f"  [WARN] Could not delete local copy: {e}")
            _log_result(gid, "SUCCESS", size_mb, dur_s)
            results.append({"game_id": gid, "status": "SUCCESS", "size_mb": size_mb})
        else:
            # Keep local copy for manual retry
            _log_result(gid, "UPLOAD_FAIL", size_mb, dur_s)
            results.append({"game_id": gid, "status": "UPLOAD_FAIL", "size_mb": size_mb})
            print(f"  [INFO] Local copy retained at {local_path} for manual retry")

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n-- Summary --")
    for r in results:
        tag = "OK" if r["status"] == "SUCCESS" else "FAIL"
        mb  = r.get("size_mb", 0)
        print(f"  [{tag}] {r['game_id']}  {mb:.0f} MB  ({r['status']})")
    print(f"Log: {LOG_FILE}")




if __name__ == "__main__":
    main()
