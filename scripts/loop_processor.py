"""
loop_processor.py -- Recurring NBA clip processing loop.

Discovers unprocessed clips in data/videos/, runs the full tracking
pipeline via run_clip.py, and logs results. Repeats every 3 minutes.

Usage:
    conda run -n basketball_ai python scripts/loop_processor.py
    conda run -n basketball_ai python scripts/loop_processor.py --once
    conda run -n basketball_ai python scripts/loop_processor.py --download

Notes:
    --once      Run a single pass then exit.
    --download  Download up to 5 clips from CURATED_CLIPS before processing.

    This script does NOT pass --game-id to run_clip.py, so shot_log_enriched
    will not be populated automatically. To enrich shots, run manually:
        python run_clip.py --video data/videos/<clip>.mp4 --game-id <ID>
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Set

# Windows cp1252 can't print unicode filenames — force utf-8 stdout
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

# ── Paths ──────────────────────────────────────────────────────────────────────

PROJECT_DIR    = Path(__file__).resolve().parent.parent
VIDEOS_DIR     = PROJECT_DIR / "data" / "videos"
DATA_DIR       = PROJECT_DIR / "data"
LOG_FILE       = DATA_DIR / "loop_log.jsonl"
PROCESSED_FILE = DATA_DIR / "processed_clips.json"
LOOP_INTERVAL  = 180  # seconds (3 minutes)
VIDEO_EXTS     = {".mp4", ".mkv", ".webm"}


# ── State helpers ──────────────────────────────────────────────────────────────

def load_processed() -> Set[str]:
    """Load the set of already-processed clip filenames from disk."""
    if not PROCESSED_FILE.exists():
        return set()
    try:
        with open(PROCESSED_FILE) as f:
            data = json.load(f)
        return set(data) if isinstance(data, list) else set()
    except (json.JSONDecodeError, OSError):
        return set()


def save_processed(processed: Set[str]) -> None:
    """Persist the processed-clips set to disk."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(PROCESSED_FILE, "w") as f:
        json.dump(sorted(processed), f, indent=2)


# ── Discovery ──────────────────────────────────────────────────────────────────

def discover_clips() -> List[Path]:
    """Return unprocessed video files in VIDEOS_DIR, oldest first."""
    if not VIDEOS_DIR.exists():
        return []
    processed = load_processed()
    clips = [
        p for p in VIDEOS_DIR.iterdir()
        if p.suffix.lower() in VIDEO_EXTS and p.name not in processed
    ]
    # Oldest mtime first — process in acquisition order
    clips.sort(key=lambda p: p.stat().st_mtime)
    return clips


# ── Processing ────────────────────────────────────────────────────────────────

def process_clip(clip_path: Path) -> dict:
    """
    Run the full tracking pipeline on a single clip.

    Calls run_clip.py via subprocess (conda env). Limits to 300 frames
    to keep resource usage low. No --game-id passed here; enrichment
    requires a manual run with a known NBA game ID.

    Args:
        clip_path: Absolute path to the video file.

    Returns:
        dict with keys: clip, success, stdout, stderr, ts
    """
    cmd = [
        "conda", "run", "--no-capture-output", "-n", "basketball_ai",
        "python", str(PROJECT_DIR / "run_clip.py"),
        "--video", str(clip_path),
        "--frames", "300",
    ]
    ts = datetime.utcnow().isoformat()
    print(f"[loop] Processing: {clip_path.name}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        success = result.returncode == 0
        return {
            "clip":    clip_path.name,
            "success": success,
            "stdout":  result.stdout[-500:],
            "stderr":  result.stderr[-200:],
            "ts":      ts,
        }
    except subprocess.TimeoutExpired:
        print(f"[loop] TIMEOUT: {clip_path.name} exceeded 600s")
        return {
            "clip":    clip_path.name,
            "success": False,
            "stdout":  "",
            "stderr":  "Timed out after 600s",
            "ts":      ts,
        }


# ── Logging ───────────────────────────────────────────────────────────────────

def log_result(result: dict) -> None:
    """Append a single JSON line to the loop log file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(result) + "\n")


# ── Main loop ─────────────────────────────────────────────────────────────────

def run_loop(once: bool = False, download_first: bool = False) -> None:
    """
    Main processing loop.

    Args:
        once:           If True, run one pass and exit. Otherwise loop forever.
        download_first: If True, call download_batch() before first pass.
    """
    if download_first:
        print("[loop] Downloading clips from CURATED_CLIPS...")
        try:
            # Import lazily so the script still works if src path needs setup
            sys.path.insert(0, str(PROJECT_DIR))
            from src.data.video_fetcher import download_batch
            paths = download_batch(max_clips=5)
            print(f"[loop] Downloaded {len(paths)} clips")
        except Exception as exc:
            print(f"[loop] Download error: {exc}")

    while True:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        clips = discover_clips()
        print(f"[loop] {now} -- {len(clips)} clip(s) to process")

        processed = load_processed()
        for clip_path in clips:
            result = process_clip(clip_path)
            log_result(result)
            status = "OK" if result["success"] else "FAIL"
            print(f"[loop] {clip_path.name} -> {status}")
            if result["success"]:
                processed.add(clip_path.name)
                save_processed(processed)

        if once:
            print("[loop] --once flag set, exiting.")
            break

        print(f"[loop] sleeping {LOOP_INTERVAL}s...")
        time.sleep(LOOP_INTERVAL)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    """Parse CLI arguments and start the loop."""
    parser = argparse.ArgumentParser(
        description="Recurring NBA clip processing loop (3-minute interval)."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single pass then exit.",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download up to 5 clips from CURATED_CLIPS before processing.",
    )
    args = parser.parse_args()
    run_loop(once=args.once, download_first=args.download)


if __name__ == "__main__":
    main()
