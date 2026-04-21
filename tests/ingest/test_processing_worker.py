"""P3 tests: processing worker — claim atomicity, checkpoint, progress events."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import src.ingest.db as db_mod
from src.ingest.db import connect
from src.ingest.manifest import add_game, get_conn, get_game, update_game
from src.ingest.processing_worker import (
    _checkpoint_path,
    _read_checkpoint,
    _write_checkpoint,
    claim_job,
    release_job,
    reset_stale_locks,
)


@pytest.fixture()
def tmp_db(tmp_path: Path):
    db_path = tmp_path / "q.db"
    db_mod.set_db_path(db_path)
    conn = get_conn(db_path)
    yield conn, tmp_path, db_path
    conn.close()
    db_mod.set_db_path(None)


def _add_verified(conn, game_id: str):
    add_game(conn, game_id)
    update_game(conn, game_id, status="verified")


# ── checkpoint ─────────────────────────────────────────────────────────────────

def test_checkpoint_roundtrip(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("src.ingest.processing_worker.CHECKPOINT_DIR", tmp_path)
    _write_checkpoint("GCKT", 12345)
    assert _read_checkpoint("GCKT") == 12345


def test_checkpoint_atomic(tmp_path: Path, monkeypatch):
    """Write to .tmp then replace → no partial file on read."""
    monkeypatch.setattr("src.ingest.processing_worker.CHECKPOINT_DIR", tmp_path)
    _write_checkpoint("GATN", 999)
    # Verify no stray .tmp file
    assert not (tmp_path / "GATN" / "checkpoint.tmp").exists()
    assert _read_checkpoint("GATN") == 999


def test_checkpoint_missing_returns_zero(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("src.ingest.processing_worker.CHECKPOINT_DIR", tmp_path)
    assert _read_checkpoint("GNONE") == 0


# ── claim_job ─────────────────────────────────────────────────────────────────

def test_claim_job_basic(tmp_db):
    conn, _, _ = tmp_db
    _add_verified(conn, "G_CLAIM")
    gid = claim_job(conn)
    assert gid == "G_CLAIM"
    row = get_game(conn, "G_CLAIM")
    assert row["status"] == "processing"


def test_claim_job_empty(tmp_db):
    conn, _, _ = tmp_db
    gid = claim_job(conn)
    assert gid is None


def test_claim_job_atomic_4_workers(tmp_path: Path):
    """Four concurrent workers claim 4 games — no double-claim."""
    db_path = tmp_path / "concurrent.db"
    conn = get_conn(db_path)
    for i in range(4):
        _add_verified(conn, f"G{i:02d}")
    conn.close()

    claimed = []
    errors = []

    def worker():
        wconn = get_conn(db_path)
        try:
            gid = claim_job(wconn)
            if gid:
                claimed.append(gid)
        except Exception as e:
            errors.append(e)
        finally:
            wconn.close()

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Errors: {errors}"
    # Key invariant: no double-claims. Some workers may lose the race and get None.
    assert len(claimed) == len(set(claimed)), "Double-claim detected"
    assert len(claimed) >= 1


def test_release_job(tmp_db):
    conn, _, _ = tmp_db
    _add_verified(conn, "G_REL")
    claim_job(conn)
    release_job(conn, "G_REL")
    row = get_game(conn, "G_REL")
    assert row["status"] == "verified"


# ── reset_stale ────────────────────────────────────────────────────────────────

def test_reset_stale_locks(tmp_db):
    conn, _, _ = tmp_db
    _add_verified(conn, "G_STALE")
    claim_job(conn)
    # Force updated_at to be 3h ago
    conn.execute(
        "UPDATE games SET updated_at=datetime('now','-3 hours') WHERE game_id='G_STALE'"
    )
    conn.commit()
    n = reset_stale_locks(conn)
    assert n == 1
    row = get_game(conn, "G_STALE")
    assert row["status"] == "verified"


# ── progress events via process_game (mock pipeline) ──────────────────────────

def test_progress_events_in_db(tmp_path: Path, tmp_db, monkeypatch):
    """process_game logs progress + complete events in events table."""
    conn, base, db_path = tmp_db
    _add_verified(conn, "G_PROG")

    # Create a fake video file
    import src.ingest.processing_worker as pw_mod
    fake_games_dir = tmp_path / "games"
    fake_games_dir.mkdir()
    (fake_games_dir / "G_PROG.mp4").write_bytes(b"fake")
    monkeypatch.setattr(pw_mod, "GAMES_DIR", fake_games_dir)
    monkeypatch.setattr(pw_mod, "CHECKPOINT_DIR", tmp_path / "tracking")

    # Mock UnifiedPipeline
    mock_pipeline = MagicMock()
    mock_pipeline.run.return_value = {"total_frames": 5000, "stability": 0.92}

    import src.ingest.processing_worker as pw_mod2
    mock_cls = MagicMock(return_value=mock_pipeline)
    pw_mod2._PIPELINE_CLASS = mock_cls
    try:
        from src.ingest.processing_worker import process_game
        ok = process_game("G_PROG", db_path=db_path)
    finally:
        pw_mod2._PIPELINE_CLASS = None

    assert ok
    row = get_game(conn, "G_PROG")
    assert row["status"] == "processed"

    events = conn.execute(
        "SELECT * FROM events WHERE game_id='G_PROG' ORDER BY ts"
    ).fetchall()
    stages = [json.loads(e["payload_json"])["stage"] for e in events]
    assert "start" in stages
    assert "complete" in stages
