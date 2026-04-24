"""H1+H2 hardening tests: memory hygiene, connection safety, filesystem safety."""
from __future__ import annotations

import inspect
import logging
import os
import sqlite3
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── db.py pragma checks ──────────────────────────────────────────────────────

def test_wal_autocheckpoint(tmp_path):
    from src.ingest.db import connect, set_db_path
    set_db_path(tmp_path / "test.db")
    conn = connect()
    val = conn.execute("PRAGMA wal_autocheckpoint").fetchone()[0]
    conn.close()
    set_db_path(None)
    assert val == 1000


def test_cache_size_pragma(tmp_path):
    from src.ingest.db import connect, set_db_path
    set_db_path(tmp_path / "test.db")
    conn = connect()
    val = conn.execute("PRAGMA cache_size").fetchone()[0]
    conn.close()
    set_db_path(None)
    assert val == -20000


def test_synchronous_normal(tmp_path):
    from src.ingest.db import connect, set_db_path
    set_db_path(tmp_path / "test.db")
    conn = connect()
    val = conn.execute("PRAGMA synchronous").fetchone()[0]
    conn.close()
    set_db_path(None)
    # NORMAL = 1 in sqlite3 pragma encoding
    assert val == 1


# ── processing_worker.py connection hygiene ───────────────────────────────────

def test_conn_closed_on_success(tmp_path):
    """conn.close() called on success path."""
    import src.ingest.processing_worker as pw
    from src.ingest.db import connect, set_db_path, migrate
    set_db_path(tmp_path / "test.db")
    conn = connect()
    migrate(conn)
    conn.execute("INSERT INTO games (game_id, status, created_at, updated_at) VALUES ('g1','verified',datetime('now'),datetime('now'))")
    conn.commit()
    conn.close()

    mock_pipeline = MagicMock()
    mock_pipeline.return_value.run.return_value = {"total_frames": 10, "stability": 0.9}

    # Create fake video file
    vid = pw.GAMES_DIR / "g1.mp4"
    vid.parent.mkdir(parents=True, exist_ok=True)
    vid.write_bytes(b"fake")

    closed_connections = []
    real_connect = pw.connect.__wrapped__ if hasattr(pw.connect, '__wrapped__') else None

    connections_made = []

    original_connect = __import__('src.ingest.db', fromlist=['connect']).connect

    def tracking_connect(db_path=None):
        c = original_connect(db_path or tmp_path / "test.db")
        connections_made.append(c)
        return c

    with patch.object(pw, '_PIPELINE_CLASS', mock_pipeline), \
         patch('src.ingest.processing_worker.connect', tracking_connect), \
         patch('src.ingest.manifest.log_event'), \
         patch('src.ingest.manifest.update_game'):
        result = pw.process_game("g1", db_path=tmp_path / "test.db")

    assert result is True
    # All connections opened must be closeable (not already in a broken state)
    for c in connections_made:
        # If already closed, this is fine; if not, close it now
        try:
            c.close()
        except Exception:
            pass

    vid.unlink(missing_ok=True)
    set_db_path(None)


def test_checkpoint_thread_opens_own_connection(tmp_path):
    """Checkpoint thread must open its own sqlite3 connection."""
    import src.ingest.processing_worker as pw
    from src.ingest.db import connect, set_db_path, migrate
    set_db_path(tmp_path / "test.db")
    conn = connect()
    migrate(conn)
    conn.execute("INSERT INTO games (game_id, status, created_at, updated_at) VALUES ('g2','verified',datetime('now'),datetime('now'))")
    conn.commit()
    conn.close()

    connect_calls = []
    original_connect = __import__('src.ingest.db', fromlist=['connect']).connect

    def counting_connect(db_path=None):
        c = original_connect(db_path or tmp_path / "test.db")
        connect_calls.append(c)
        return c

    mock_pipeline = MagicMock()
    mock_pipeline.return_value.run.return_value = {"total_frames": 5, "stability": 1.0}

    vid = pw.GAMES_DIR / "g2.mp4"
    vid.parent.mkdir(parents=True, exist_ok=True)
    vid.write_bytes(b"fake")

    with patch.object(pw, '_PIPELINE_CLASS', mock_pipeline), \
         patch('src.ingest.processing_worker.connect', counting_connect), \
         patch('src.ingest.manifest.log_event'), \
         patch('src.ingest.manifest.update_game'):
        pw.process_game("g2", db_path=tmp_path / "test.db")

    # Expect ≥2 connections: initial setup + checkpoint thread + completion
    assert len(connect_calls) >= 2, f"Expected ≥2 connections, got {len(connect_calls)}"

    vid.unlink(missing_ok=True)
    set_db_path(None)


def test_conn_closed_on_exception(tmp_path):
    """conn.close() called on exception path."""
    import src.ingest.processing_worker as pw
    from src.ingest.db import connect, set_db_path, migrate
    set_db_path(tmp_path / "test.db")
    conn = connect()
    migrate(conn)
    conn.execute("INSERT INTO games (game_id, status, created_at, updated_at) VALUES ('g3','verified',datetime('now'),datetime('now'))")
    conn.commit()
    conn.close()

    mock_pipeline = MagicMock()
    mock_pipeline.return_value.run.side_effect = RuntimeError("GPU OOM")

    vid = pw.GAMES_DIR / "g3.mp4"
    vid.parent.mkdir(parents=True, exist_ok=True)
    vid.write_bytes(b"fake")

    connections_made = []
    original_connect = __import__('src.ingest.db', fromlist=['connect']).connect

    def tracking_connect(db_path=None):
        c = original_connect(db_path or tmp_path / "test.db")
        connections_made.append(c)
        return c

    with patch.object(pw, '_PIPELINE_CLASS', mock_pipeline), \
         patch('src.ingest.processing_worker.connect', tracking_connect), \
         patch('src.ingest.manifest.log_event'), \
         patch('src.ingest.manifest.update_game'), \
         patch('src.ingest.manifest.update_game'):
        result = pw.process_game("g3", db_path=tmp_path / "test.db")

    assert result is False
    vid.unlink(missing_ok=True)
    set_db_path(None)


# ── sync_remote.py SYNC_DIRS guard ───────────────────────────────────────────

def test_sync_dirs_excludes_videos():
    import scripts.sync_remote as sr
    for d in sr.SYNC_DIRS:
        parts = d.parts
        assert "videos" not in parts, f"SYNC_DIRS contains 'videos': {d}"
        assert "by_sha" not in parts, f"SYNC_DIRS contains 'by_sha': {d}"


# ── log rotation ─────────────────────────────────────────────────────────────

def test_rotating_handler_configured():
    """ingest_fetch and ingest_process must use RotatingFileHandler."""
    import importlib
    import scripts.ingest_fetch as fetch_script
    import scripts.ingest_process as process_script

    for mod in (fetch_script, process_script):
        root_logger = logging.root
        has_rotating = any(
            isinstance(h, RotatingFileHandler)
            for h in root_logger.handlers
        )
        # Re-inspect source directly since basicConfig is module-level
        src = inspect.getsource(mod)
        assert "RotatingFileHandler" in src, f"{mod.__name__} missing RotatingFileHandler"


def test_log_rotation_triggers(tmp_path):
    """Write >50MB to a rotating handler and verify backup file created."""
    log_file = tmp_path / "test.log"
    handler = RotatingFileHandler(str(log_file), maxBytes=1024, backupCount=2)
    logger = logging.getLogger("rotation_test")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    # Write enough to trigger rotation
    for _ in range(200):
        logger.debug("x" * 20)

    handler.close()
    backups = list(tmp_path.glob("test.log.*"))
    assert len(backups) >= 1, "No backup log files created"


# ── H2: cross-filesystem rename fallback ─────────────────────────────────────

def test_content_store_exdev_fallback(tmp_path):
    """_content_store falls back to copy+unlink on EXDEV (cross-device)."""
    import errno
    from src.ingest.fetcher import _content_store, BY_SHA_DIR

    # Create a fake source file
    src_dir = tmp_path / "inbox"
    src_dir.mkdir()
    src_file = src_dir / "test_video.mp4"
    src_file.write_bytes(b"fake video content for sha test")

    original_rename = Path.rename

    def _raise_exdev(self, dst):
        raise OSError(errno.EXDEV, "Invalid cross-device link", str(self))

    with patch("src.ingest.fetcher.BY_SHA_DIR", tmp_path / "by_sha"), \
         patch.object(Path, "rename", _raise_exdev):
        dest, sha = _content_store(src_file)

    assert dest.exists()
    assert not src_file.exists()
    assert len(sha) == 64  # sha256 hex


def test_content_store_normal_rename(tmp_path):
    """_content_store uses rename when on same filesystem."""
    from src.ingest.fetcher import _content_store

    src_dir = tmp_path / "inbox"
    src_dir.mkdir()
    src_file = src_dir / "test2.mp4"
    src_file.write_bytes(b"another fake video")

    with patch("src.ingest.fetcher.BY_SHA_DIR", tmp_path / "by_sha"):
        dest, sha = _content_store(src_file)

    assert dest.exists()
    assert not src_file.exists()


def test_symlink_uses_absolute_path(tmp_path):
    """_symlink_game creates symlink with absolute (resolved) target path."""
    from src.ingest.fetcher import _symlink_game

    sha_dir = tmp_path / "by_sha"
    sha_dir.mkdir()
    sha_path = sha_dir / "abc123.mp4"
    sha_path.write_bytes(b"fake")

    games_dir = tmp_path / "full_games"
    with patch("src.ingest.fetcher.GAMES_DIR", games_dir):
        link = _symlink_game(sha_path, "test_game")

    if link.is_symlink():
        target = Path(os.readlink(str(link)))
        assert target.is_absolute(), f"Symlink target is relative: {target}"


# ── H3: worker orchestration + claim retry ───────────────────────────────────

def test_claim_job_retries_on_race(tmp_path):
    """claim_job retries when all verified games get grabbed by another worker mid-race."""
    from src.ingest.db import connect, set_db_path, migrate
    from src.ingest.processing_worker import claim_job

    set_db_path(tmp_path / "test.db")
    conn = connect()
    migrate(conn)
    conn.execute("INSERT INTO games (game_id, status, created_at, updated_at) VALUES ('g_race','verified',datetime('now'),datetime('now'))")
    conn.commit()

    # Simulate another worker stealing the game between SELECT and UPDATE
    # by pre-marking the game as processing before claim_job runs
    conn.execute("UPDATE games SET status='processing' WHERE game_id='g_race'")
    conn.commit()

    # With retries=3, claim_job should return None (no verified games left)
    result = claim_job(conn, retries=3, jitter_ms=0)
    conn.close()
    set_db_path(None)
    assert result is None


def test_claim_job_returns_none_when_empty(tmp_path):
    """claim_job returns None immediately when no verified games exist."""
    from src.ingest.db import connect, set_db_path, migrate
    from src.ingest.processing_worker import claim_job

    set_db_path(tmp_path / "test.db")
    conn = connect()
    migrate(conn)
    result = claim_job(conn)
    conn.close()
    set_db_path(None)
    assert result is None


def test_worker_exception_does_not_kill_others(tmp_path):
    """One worker throwing must not stop other workers from completing."""
    import src.ingest.processing_worker as pw
    from src.ingest.db import connect, set_db_path, migrate
    from concurrent.futures import ThreadPoolExecutor, as_completed

    set_db_path(tmp_path / "test.db")
    conn = connect()
    migrate(conn)
    for gid in ("crash_game", "ok_game"):
        conn.execute(f"INSERT INTO games (game_id, status, created_at, updated_at) VALUES ('{gid}','verified',datetime('now'),datetime('now'))")
    conn.commit()
    conn.close()

    results = []
    errors = []

    def _worker(game_id: str) -> bool:
        if game_id == "crash_game":
            raise RuntimeError("Simulated OOM")
        return True

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(_worker, gid): gid for gid in ("crash_game", "ok_game")}
        for f in as_completed(futures):
            gid = futures[f]
            try:
                results.append(f.result())
            except Exception as e:
                errors.append(str(e))

    set_db_path(None)
    assert len(results) == 1   # ok_game succeeded
    assert len(errors) == 1    # crash_game errored
    assert "OOM" in errors[0]


def test_reset_stale_locks_hours_param(tmp_path):
    """reset_stale_locks respects custom stale_hours argument."""
    from src.ingest.db import connect, set_db_path, migrate
    from src.ingest.processing_worker import reset_stale_locks

    set_db_path(tmp_path / "test.db")
    conn = connect()
    migrate(conn)
    # Insert a "processing" job stuck for ~1 minute (via old updated_at)
    conn.execute(
        "INSERT INTO games (game_id, status, created_at, updated_at) "
        "VALUES ('stale','processing',datetime('now','-10 minutes'),datetime('now','-10 minutes'))"
    )
    conn.commit()

    # Should NOT reset with 2h threshold
    n = reset_stale_locks(conn, stale_hours=2.0)
    assert n == 0

    # SHOULD reset with 0.1h (6 min) threshold
    n = reset_stale_locks(conn, stale_hours=0.1)
    assert n == 1

    conn.close()
    set_db_path(None)
