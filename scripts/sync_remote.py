#!/usr/bin/env python
"""Cloud sync: push/pull data to/from Backblaze B2 via rclone."""
from __future__ import annotations

import argparse
import logging
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

LOG_DIR = ROOT / "data" / "ingest" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(LOG_DIR / "p5_sync.log", maxBytes=50 * 1024 * 1024, backupCount=3),
    ],
)
logger = logging.getLogger("sync_remote")

DB_PATH  = ROOT / "data" / "ingest" / "queue.db"
SYNC_DIRS = [
    ROOT / "data" / "tracking",
    ROOT / "data" / "events",
    ROOT / "data" / "ingest" / "logs",
]
RETRY_COUNT  = 3
RETRY_DELAY  = 10

# Guard: never accidentally sync videos (80 GB+) or content-addressed store
_FORBIDDEN = ("videos", "by_sha")
for _d in SYNC_DIRS:
    assert not any(p in _d.parts for p in _FORBIDDEN), \
        f"SYNC_DIRS safety violation: {_d} contains forbidden path segment"

RCLONE_FLAGS = ["--buffer-size", "16M", "--transfers", "4", "--checkers", "8"]


def _check_rclone() -> str:
    rclone = shutil.which("rclone")
    if not rclone:
        logger.error(
            "rclone not found. Install: "
            "curl https://rclone.org/install.sh | sudo bash  "
            "(or: choco install rclone  on Windows)"
        )
        sys.exit(2)
    return rclone


def _load_env() -> tuple[str, str, str]:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    bucket  = os.environ.get("B2_BUCKET",  "")
    key_id  = os.environ.get("B2_KEY_ID",  "")
    app_key = os.environ.get("B2_APP_KEY", "")
    missing = [k for k, v in [("B2_BUCKET", bucket), ("B2_KEY_ID", key_id), ("B2_APP_KEY", app_key)] if not v]
    if missing:
        logger.error("Missing env vars: %s — copy .env.example to .env and fill in B2 credentials", missing)
        sys.exit(1)
    return bucket, key_id, app_key


def _rclone_remote(key_id: str, app_key: str) -> str:
    return f":b2,account={key_id},key={app_key}"


def _run_rclone(cmd: list[str], retries: int = RETRY_COUNT) -> int:
    for attempt in range(1, retries + 1):
        logger.info("rclone [attempt %d]: %s", attempt, " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            return 0
        logger.warning("rclone failed (rc=%d): %s", result.returncode, result.stderr[-300:])
        if attempt < retries:
            time.sleep(RETRY_DELAY * attempt)
    return result.returncode


def _backup_db(db_path: Path) -> Path:
    """Backup SQLite DB via .backup() to avoid locked-file upload."""
    tmp = Path(tempfile.mktemp(suffix=".queue_snapshot.db"))
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(tmp))
    src.backup(dst)
    src.close()
    dst.close()
    return tmp


def push(rclone: str, remote: str, bucket: str, dry_run: bool = False) -> None:
    flags = RCLONE_FLAGS + ["--progress"] + (["--dry-run"] if dry_run else [])

    # Sync directories
    for d in SYNC_DIRS:
        if not d.exists():
            logger.info("Skipping missing dir: %s", d)
            continue
        dest = f"{remote}/{bucket}/{d.name}/"
        rc = _run_rclone([rclone, "sync", str(d), dest] + flags)
        if rc != 0:
            logger.error("Push failed for %s (rc=%d)", d, rc)

    # DB snapshot
    if DB_PATH.exists():
        snap = _backup_db(DB_PATH)
        try:
            dest = f"{remote}/{bucket}/ingest/queue_snapshot.db"
            rc = _run_rclone([rclone, "copyto", str(snap), dest] + flags)
            if rc != 0:
                logger.error("DB snapshot push failed (rc=%d)", rc)
        finally:
            snap.unlink(missing_ok=True)


def pull(rclone: str, remote: str, bucket: str, dry_run: bool = False) -> None:
    flags = RCLONE_FLAGS + ["--progress"] + (["--dry-run"] if dry_run else [])

    for d in SYNC_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        src = f"{remote}/{bucket}/{d.name}/"
        rc = _run_rclone([rclone, "sync", src, str(d)] + flags)
        if rc != 0:
            logger.warning("Pull warning for %s (rc=%d)", d, rc)

    # Pull DB snapshot
    snap_dest = DB_PATH.parent / "queue_snapshot.db"
    src = f"{remote}/{bucket}/ingest/queue_snapshot.db"
    rc = _run_rclone([rclone, "copyto", src, str(snap_dest)] + flags)
    if rc == 0:
        logger.info("DB snapshot pulled to %s", snap_dest)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync data to/from Backblaze B2")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--push", action="store_true", help="Upload local data to bucket")
    group.add_argument("--pull", action="store_true", help="Download from bucket to local")
    group.add_argument("--loop", type=int, metavar="N", help="Push every N minutes (background mode)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    rclone = _check_rclone()
    bucket, key_id, app_key = _load_env()
    remote = _rclone_remote(key_id, app_key)

    if args.push:
        logger.info("Pushing to b2:%s ...", bucket)
        push(rclone, remote, bucket, args.dry_run)
        logger.info("Push complete.")

    elif args.pull:
        logger.info("Pulling from b2:%s ...", bucket)
        pull(rclone, remote, bucket, args.dry_run)
        logger.info("Pull complete.")

    elif args.loop:
        logger.info("Loop mode: pushing every %d minutes", args.loop)
        _shutdown = threading.Event()

        def _handle_stop(signum, frame):
            logger.info("Signal %d — shutting down loop cleanly", signum)
            _shutdown.set()

        signal.signal(signal.SIGTERM, _handle_stop)
        signal.signal(signal.SIGINT, _handle_stop)

        while not _shutdown.is_set():
            push(rclone, remote, bucket)
            _shutdown.wait(timeout=args.loop * 60)
        logger.info("Loop exited.")


if __name__ == "__main__":
    main()
