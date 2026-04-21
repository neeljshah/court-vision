"""P5 tests: sync_remote — rclone flags, db snapshot, missing-bucket error."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# Ensure we can import the script as a module
ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT))


def _import_sync():
    import importlib
    import scripts.sync_remote as sr
    importlib.reload(sr)
    return sr


# ── rclone not installed ───────────────────────────────────────────────────────

def test_check_rclone_missing_exits(monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "which", lambda x: None)
    sr = _import_sync()
    with pytest.raises(SystemExit) as exc:
        sr._check_rclone()
    assert exc.value.code == 2


# ── missing env vars → clean error ────────────────────────────────────────────

def test_missing_env_vars_exits(monkeypatch, tmp_path):
    monkeypatch.setenv("B2_BUCKET", "")
    monkeypatch.setenv("B2_KEY_ID", "")
    monkeypatch.setenv("B2_APP_KEY", "")

    # Patch load_dotenv to no-op
    with patch("dotenv.load_dotenv", return_value=None):
        sr = _import_sync()
        with pytest.raises(SystemExit) as exc:
            sr._load_env()
        assert exc.value.code == 1


# ── db snapshot uses .backup() ────────────────────────────────────────────────

def test_db_snapshot_creates_valid_sqlite(tmp_path: Path):
    db = tmp_path / "queue.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (42)")
    conn.commit()
    conn.close()

    sr = _import_sync()
    snap = sr._backup_db(db)
    try:
        snap_conn = sqlite3.connect(str(snap))
        val = snap_conn.execute("SELECT x FROM t").fetchone()[0]
        snap_conn.close()
        assert val == 42
    finally:
        snap.unlink(missing_ok=True)


# ── rclone push: correct flags ─────────────────────────────────────────────────

def test_push_calls_rclone_sync(tmp_path: Path, monkeypatch):
    """push() calls rclone sync for each existing dir."""
    calls_made = []

    def mock_run(cmd, **kwargs):
        calls_made.append(cmd)
        result = MagicMock()
        result.returncode = 0
        result.stderr = ""
        return result

    sr = _import_sync()
    tracking = tmp_path / "tracking"
    tracking.mkdir()
    monkeypatch.setattr(sr, "SYNC_DIRS", [tracking])
    monkeypatch.setattr(sr, "DB_PATH", tmp_path / "nodb.db")

    with patch("subprocess.run", side_effect=mock_run):
        sr.push("rclone", ":b2,account=K,key=A", "mybucket", dry_run=False)

    sync_calls = [c for c in calls_made if "sync" in c]
    assert len(sync_calls) >= 1
    assert any("mybucket" in " ".join(c) for c in sync_calls)


# ── dummy bucket name gives clear error ───────────────────────────────────────

def test_push_bad_bucket_logs_error(tmp_path: Path, monkeypatch, caplog):
    """rclone non-zero exit → logs error, does not raise."""
    import logging

    def mock_run(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 1
        result.stderr = "b2: bucket not found"
        return result

    sr = _import_sync()
    tracking = tmp_path / "tracking"
    tracking.mkdir()
    monkeypatch.setattr(sr, "SYNC_DIRS", [tracking])
    monkeypatch.setattr(sr, "DB_PATH", tmp_path / "nodb.db")
    monkeypatch.setattr(sr, "RETRY_COUNT", 1)
    monkeypatch.setattr(sr, "RETRY_DELAY", 0)

    with patch("subprocess.run", side_effect=mock_run):
        with caplog.at_level(logging.ERROR, logger="sync_remote"):
            sr.push("rclone", ":b2,account=BAD,key=BAD", "fakebucket")
    assert any("failed" in r.message.lower() or "error" in r.message.lower()
                for r in caplog.records)
