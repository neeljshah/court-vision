"""Processing worker: claim + run UnifiedPipeline with checkpointing."""
from __future__ import annotations

import json
import logging
import os
import signal
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.ingest.db import connect, migrate
from src.ingest.manifest import log_event, update_game

logger = logging.getLogger(__name__)

# Overridable in tests — set to a mock class to avoid importing heavy GPU deps
_PIPELINE_CLASS = None

CHECKPOINT_DIR = Path(__file__).parents[2] / "data" / "tracking"
GAMES_DIR      = Path(__file__).parents[2] / "data" / "videos" / "full_games"
CHECKPOINT_INTERVAL = 3000   # frames between checkpoint writes
PROGRESS_INTERVAL   = 1000   # frames between progress log events
STALE_HOURS         = 2


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _checkpoint_path(game_id: str) -> Path:
    d = CHECKPOINT_DIR / game_id
    d.mkdir(parents=True, exist_ok=True)
    return d / "checkpoint.json"


def _write_checkpoint(game_id: str, frame_idx: int) -> None:
    path = _checkpoint_path(game_id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"game_id": game_id, "frame_idx": frame_idx, "ts": _now()}))
    tmp.replace(path)


def _read_checkpoint(game_id: str) -> int:
    path = _checkpoint_path(game_id)
    if path.exists():
        try:
            data = json.loads(path.read_text())
            return int(data.get("frame_idx", 0))
        except (json.JSONDecodeError, ValueError):
            pass
    return 0


def claim_job(conn: sqlite3.Connection, retries: int = 3, jitter_ms: int = 100) -> Optional[str]:
    """Atomically claim one verified game. Returns game_id or None.

    Retries up to `retries` times with random jitter on UPDATE rowcount=0 races.
    """
    for attempt in range(retries):
        row = conn.execute(
            "SELECT game_id FROM games WHERE status='verified' ORDER BY created_at LIMIT 1"
        ).fetchone()
        if row is None:
            return None  # genuinely no work available
        game_id = row["game_id"]
        updated = conn.execute(
            "UPDATE games SET status='processing', updated_at=? "
            "WHERE game_id=? AND status='verified'",
            (_now(), game_id),
        ).rowcount
        conn.commit()
        if updated > 0:
            return game_id
        # Race: another worker grabbed it — wait with jitter then retry
        if attempt < retries - 1:
            import random
            time.sleep(random.uniform(0, jitter_ms / 1000))
    return None


def release_job(conn: sqlite3.Connection, game_id: str) -> None:
    """Revert processing → verified (on crash/interrupt)."""
    conn.execute(
        "UPDATE games SET status='verified', updated_at=? WHERE game_id=?",
        (_now(), game_id),
    )
    conn.commit()


def process_game(
    game_id: str,
    db_path: Optional[Path] = None,
    data_dir: Optional[str] = None,
) -> bool:
    """
    Run UnifiedPipeline for one game with checkpointing + SIGTERM handling.
    Returns True on success.
    """
    conn = connect(db_path)
    migrate(conn)

    video_path = GAMES_DIR / f"{game_id}.mp4"
    if not video_path.exists():
        logger.error("Video not found: %s", video_path)
        update_game(conn, game_id, status="failed", reject_reason="video_missing")
        conn.close()
        return False

    resume_frame = _read_checkpoint(game_id)
    if resume_frame > 0:
        logger.info("Resuming %s from frame %d", game_id, resume_frame)

    _interrupted = threading.Event()   # set only on SIGTERM
    _stop_ckpt   = threading.Event()   # set when run() finishes (normal or interrupted)
    _original_sigterm = signal.getsignal(signal.SIGTERM)

    def _handle_sigterm(signum, frame):
        logger.warning("SIGTERM received — checkpointing %s", game_id)
        _interrupted.set()
        _stop_ckpt.set()
        # Own connection: main conn will be closed before pipeline runs
        _sig_conn = connect(db_path)
        release_job(_sig_conn, game_id)
        _sig_conn.close()
        signal.signal(signal.SIGTERM, _original_sigterm)

    signal.signal(signal.SIGTERM, _handle_sigterm)

    log_event(conn, game_id, "process", "info",
              {"stage": "start", "resume_frame": resume_frame})
    conn.close()  # release before long pipeline.run() so other workers can write

    try:
        if _PIPELINE_CLASS is not None:
            PipelineCls = _PIPELINE_CLASS
        else:
            from src.pipeline.unified_pipeline import UnifiedPipeline as PipelineCls

        tracking_out = str(CHECKPOINT_DIR / game_id)
        pipeline = PipelineCls(
            video_path=str(video_path),
            game_id=game_id,
            start_frame=resume_frame,
            show=False,
            data_dir=data_dir or tracking_out,
        )

        _orig_run = pipeline.run

        def _instrumented_run():
            start_t = time.time()
            _frames_done = [0]

            def _checkpoint_thread():
                # Own connection — sqlite3 connections are not thread-safe for writes
                ckpt_conn = connect(db_path)
                last_ckpt = 0
                try:
                    while not _stop_ckpt.wait(timeout=10):
                        if _frames_done[0] > last_ckpt + PROGRESS_INTERVAL:
                            _write_checkpoint(game_id, _frames_done[0] + resume_frame)
                            last_ckpt = _frames_done[0]
                            log_event(ckpt_conn, game_id, "process", "info",
                                      {"stage": "progress", "frames": _frames_done[0],
                                       "elapsed_s": round(time.time() - start_t, 1)})
                finally:
                    ckpt_conn.close()

            ckpt_t = threading.Thread(target=_checkpoint_thread, daemon=True)
            ckpt_t.start()

            result = None
            if not _interrupted.is_set():
                result = _orig_run()

            _stop_ckpt.set()
            ckpt_t.join(timeout=5)
            return result

        pipeline.run = _instrumented_run
        result = pipeline.run()

        if _interrupted.is_set():
            logger.warning("Pipeline interrupted for %s", game_id)
            return False

        total_frames = result.get("total_frames", 0) if result else 0
        done_conn = connect(db_path)
        log_event(done_conn, game_id, "process", "info",
                  {"stage": "complete", "total_frames": total_frames,
                   "stability": result.get("stability") if result else None})
        update_game(done_conn, game_id, status="processed")
        done_conn.close()

        cp = _checkpoint_path(game_id)
        if cp.exists():
            cp.unlink()

        return True

    except Exception as exc:
        logger.exception("Pipeline failed for %s: %s", game_id, exc)
        err_conn = connect(db_path)
        log_event(err_conn, game_id, "process", "error", {"error": str(exc)[:500]})
        release_job(err_conn, game_id)
        err_conn.close()
        return False
    finally:
        signal.signal(signal.SIGTERM, _original_sigterm)


def reset_stale_locks(conn: sqlite3.Connection, stale_hours: float = STALE_HOURS) -> int:
    """Reset processing→verified for jobs stuck >stale_hours hours."""
    conn.execute(
        """UPDATE games SET status='verified', updated_at=datetime('now')
           WHERE status='processing'
           AND (julianday('now') - julianday(updated_at)) * 24 > ?""",
        (stale_hours,),
    )
    conn.commit()
    return conn.execute("SELECT changes()").fetchone()[0]
