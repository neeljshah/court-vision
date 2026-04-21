"""Fetcher: download videos from sources, content-addressed storage."""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple

from src.ingest.db import connect, migrate
from src.ingest.manifest import add_game, get_game, log_event, update_game
from src.ingest.sources import SourceRegistry
from src.ingest.verifier import probe, quarantine, verify

logger = logging.getLogger(__name__)

BY_SHA_DIR    = Path(__file__).parents[2] / "data" / "videos" / "by_sha"
GAMES_DIR     = Path(__file__).parents[2] / "data" / "videos" / "full_games"
INBOX_DIR     = Path(__file__).parents[2] / "data" / "videos" / "_inbox"
TIMEOUT_S     = 30 * 60   # 30 min per attempt
RETRY_COUNT   = 3
RETRY_BACKOFF = 60        # seconds


def _sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            buf = fh.read(chunk)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def _content_store(src: Path) -> Tuple[Path, str]:
    """Hash, move to by_sha/<sha>.mp4, return (final_path, sha256)."""
    sha = _sha256(src)
    BY_SHA_DIR.mkdir(parents=True, exist_ok=True)
    dest = BY_SHA_DIR / f"{sha}.mp4"
    if not dest.exists():
        try:
            src.rename(dest)
            logger.debug("_content_store: renamed %s → %s", src, dest)
        except OSError as exc:
            import errno
            if exc.errno == errno.EXDEV:
                # Cross-device link (e.g. overlayFS /root → /workspace mfs on pod)
                logger.info("_content_store: cross-device rename, falling back to copy+unlink")
                shutil.copy2(src, dest)
                src.unlink(missing_ok=True)
            else:
                raise
    else:
        src.unlink(missing_ok=True)
    return dest, sha


def _symlink_game(sha_path: Path, game_id: str) -> Path:
    """Create data/videos/full_games/<game_id>.mp4 → sha_path symlink."""
    GAMES_DIR.mkdir(parents=True, exist_ok=True)
    link = GAMES_DIR / f"{game_id}.mp4"
    if link.exists() or link.is_symlink():
        link.unlink()
    try:
        link.symlink_to(sha_path.resolve())
    except (OSError, NotImplementedError):
        # Windows without Developer Mode: fall back to copy
        shutil.copy2(sha_path, link)
    return link


def _fetch_youtube(game_id: str, url: str, dest_dir: Path, reg: SourceRegistry) -> Optional[Path]:
    part = dest_dir / f"{game_id}.mp4"
    cmd = [
        "yt-dlp",
        "--format", "bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--output", str(part.with_suffix("")),
        "--merge-output-format", "mp4",
        "--no-playlist",
        *reg.youtube_flags(),
        url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S)
        if result.returncode == 0:
            mp4 = dest_dir / f"{game_id}.mp4"
            if not mp4.exists():
                # yt-dlp may emit a different filename — find it
                candidates = list(dest_dir.glob(f"{game_id}*.mp4"))
                if candidates:
                    candidates[0].rename(mp4)
                else:
                    return None
            return mp4
        logger.warning("yt-dlp failed: %s", result.stderr[-500:])
    except subprocess.TimeoutExpired:
        logger.error("yt-dlp timeout for %s", game_id)
    return None


def _fetch_inbox(game_id: str) -> Optional[Path]:
    """Check inbox for a pre-staged file matching game_id."""
    if not INBOX_DIR.exists():
        return None
    for f in INBOX_DIR.glob(f"{game_id}*.mp4"):
        return f
    return None


def fetch(game_id: str, url: Optional[str] = None, db_path: Optional[Path] = None) -> bool:
    """
    Attempt to fetch video for game_id from all sources.
    Returns True if a verified file is now in place.
    """
    conn = connect(db_path)
    migrate(conn)

    game = get_game(conn, game_id)
    if game is None:
        add_game(conn, game_id, status="queued")
        game = get_game(conn, game_id)

    dest_dir = Path(os.environ.get("INGEST_TMP_DIR", str(Path(__file__).parents[2] / "data" / "ingest" / "tmp")))
    dest_dir.mkdir(parents=True, exist_ok=True)

    reg = SourceRegistry()
    existing_link = GAMES_DIR / f"{game_id}.mp4"

    # inbox fast-path (no download needed)
    inbox_file = _fetch_inbox(game_id)
    if inbox_file:
        logger.info("Found %s in inbox", game_id)
        ok, reason, info = verify(inbox_file)
        if ok:
            sha_path, sha = _content_store(inbox_file)
            _symlink_game(sha_path, game_id)
            update_game(conn, game_id, status="verified", sha256=sha,
                        duration_s=info["duration_s"], codec=info["codec"],
                        fps=info["fps"], source="inbox")
            log_event(conn, game_id, "fetch", "info", {"source": "inbox", "sha": sha})
            conn.close()
            return True
        else:
            update_game(conn, game_id, status="quarantined", reject_reason=reason)
            log_event(conn, game_id, "fetch", "warn", {"source": "inbox", "reason": reason})
            conn.close()
            return False

    if url is None:
        logger.warning("No URL and no inbox file for %s", game_id)
        conn.close()
        return False

    sources_to_try = ["youtube", "archive_org"]
    for src_name in sources_to_try:
        for attempt in range(1, RETRY_COUNT + 1):
            conn.execute(
                "INSERT INTO downloads (game_id, source, attempt, status, started_at) VALUES (?,?,?,?,datetime('now'))",
                (game_id, src_name, attempt, "started"),
            )
            conn.commit()
            dl_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            try:
                part = dest_dir / f"{game_id}.part.mp4"
                downloaded: Optional[Path] = None

                if src_name == "youtube":
                    downloaded = _fetch_youtube(game_id, url, dest_dir, reg)
                elif src_name == "archive_org":
                    downloaded = _fetch_youtube(game_id, url, dest_dir, reg)

                if downloaded is None:
                    raise RuntimeError(f"{src_name} returned no file")

                ok, reason, info = verify(downloaded)
                if not ok:
                    quarantine(downloaded, reason)
                    raise RuntimeError(f"Verify failed: {reason}")

                sha_path, sha = _content_store(downloaded)
                _symlink_game(sha_path, game_id)

                update_game(conn, game_id, status="verified", sha256=sha,
                            duration_s=info["duration_s"], codec=info["codec"],
                            fps=info["fps"], source=src_name, source_url=url)
                conn.execute(
                    "UPDATE downloads SET status='success', finished_at=datetime('now') WHERE id=?",
                    (dl_id,)
                )
                conn.commit()
                reg.record(src_name, True)
                log_event(conn, game_id, "fetch", "info", {"source": src_name, "sha": sha, "attempt": attempt})
                conn.close()
                return True

            except Exception as exc:
                err = str(exc)[:500]
                conn.execute(
                    "UPDATE downloads SET status='failed', error=?, finished_at=datetime('now') WHERE id=?",
                    (err, dl_id),
                )
                conn.commit()
                reg.record(src_name, False)
                update_game(conn, game_id, status="queued",
                            attempts=(game["attempts"] or 0) + attempt)
                log_event(conn, game_id, "fetch", "error",
                          {"source": src_name, "attempt": attempt, "error": err})

                if attempt < RETRY_COUNT:
                    time.sleep(RETRY_BACKOFF * (2 ** (attempt - 1)))

    update_game(conn, game_id, status="failed")
    conn.close()
    return False
