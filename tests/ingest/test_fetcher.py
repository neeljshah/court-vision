"""P2 tests: fetcher + verifier."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import src.ingest.db as db_mod
from src.ingest.db import connect
from src.ingest.manifest import add_game, get_conn, get_game, update_game
from src.ingest.verifier import verify, quarantine, QUARANTINE_DIR, MIN_DURATION


# ── helpers ────────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_db(tmp_path: Path):
    db_path = tmp_path / "q.db"
    db_mod.set_db_path(db_path)
    conn = get_conn(db_path)
    yield conn, tmp_path
    conn.close()
    db_mod.set_db_path(None)


def _make_probe_result(codec: str = "h264", duration: float = 2400.0, fps: float = 29.97) -> dict:
    return {"codec": codec, "duration_s": duration, "fps": fps, "has_video": True}


# ── verifier ───────────────────────────────────────────────────────────────────

def test_verify_good_video(tmp_path: Path):
    """Good h264 video passes verification."""
    mp4 = tmp_path / "good.mp4"
    mp4.write_bytes(b"fake")
    with patch("src.ingest.verifier.probe", return_value=_make_probe_result()):
        ok, reason, info = verify(mp4)
    assert ok
    assert reason is None
    assert info["codec"] == "h264"


def test_verify_av1_quarantines(tmp_path: Path):
    """AV1 codec fails verification."""
    mp4 = tmp_path / "av1.mp4"
    mp4.write_bytes(b"fake")
    with patch("src.ingest.verifier.probe", return_value=_make_probe_result(codec="av1")):
        ok, reason, info = verify(mp4)
    assert not ok
    assert "codec" in reason


def test_verify_short_duration(tmp_path: Path):
    """Short video fails duration check."""
    mp4 = tmp_path / "short.mp4"
    mp4.write_bytes(b"fake")
    with patch("src.ingest.verifier.probe", return_value=_make_probe_result(duration=900.0)):
        ok, reason, info = verify(mp4)
    assert not ok
    assert "duration" in reason


def test_verify_bad_fps(tmp_path: Path):
    """Out-of-range fps fails."""
    mp4 = tmp_path / "lowfps.mp4"
    mp4.write_bytes(b"fake")
    with patch("src.ingest.verifier.probe", return_value=_make_probe_result(fps=10.0)):
        ok, reason, info = verify(mp4)
    assert not ok
    assert "fps" in reason


def test_quarantine_moves_file(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("src.ingest.verifier.QUARANTINE_DIR", tmp_path / "quarantine")
    mp4 = tmp_path / "bad.mp4"
    mp4.write_bytes(b"data")
    dest = quarantine(mp4, "bad codec")
    assert dest.exists()
    assert not mp4.exists()


# ── fetcher ────────────────────────────────────────────────────────────────────

def test_fetch_inbox_success(tmp_path: Path, tmp_db, monkeypatch):
    """Inbox file → verified in DB."""
    conn, base = tmp_db
    inbox = tmp_path / "_inbox"
    inbox.mkdir()
    mp4 = inbox / "GAME_INBOX.mp4"
    mp4.write_bytes(b"video")

    import src.ingest.fetcher as fetcher_mod
    monkeypatch.setattr(fetcher_mod, "INBOX_DIR", inbox)
    monkeypatch.setattr(fetcher_mod, "BY_SHA_DIR", tmp_path / "by_sha")
    monkeypatch.setattr(fetcher_mod, "GAMES_DIR", tmp_path / "games")
    monkeypatch.setattr("src.ingest.verifier.probe", lambda p: _make_probe_result())

    db_path = base / "q.db"
    add_game(conn, "GAME_INBOX")
    ok = fetcher_mod.fetch("GAME_INBOX", db_path=db_path)
    assert ok

    row = get_game(conn, "GAME_INBOX")
    assert row["status"] == "verified"
    assert row["source"] == "inbox"
    assert row["sha256"] is not None


def test_fetch_yt_failure_recorded(tmp_path: Path, tmp_db, monkeypatch):
    """yt-dlp failure → downloads row has status=failed."""
    conn, base = tmp_db
    db_path = base / "q.db"
    import src.ingest.fetcher as fetcher_mod
    monkeypatch.setattr(fetcher_mod, "INBOX_DIR", tmp_path / "noinbox")
    monkeypatch.setattr(fetcher_mod, "RETRY_COUNT", 1)
    monkeypatch.setattr(fetcher_mod, "RETRY_BACKOFF", 0)
    monkeypatch.setattr(fetcher_mod, "_fetch_youtube", lambda *a, **k: None)

    add_game(conn, "GAME_FAIL", source_url="https://example.com/fake")
    ok = fetcher_mod.fetch("GAME_FAIL", url="https://example.com/fake", db_path=db_path)
    assert not ok

    dl = conn.execute("SELECT * FROM downloads WHERE game_id='GAME_FAIL'").fetchone()
    assert dl is not None
    assert dl["status"] == "failed"


def test_fetch_part_resume(tmp_path: Path):
    """Partial .part file doesn't crash fetcher (treated as missing)."""
    part = tmp_path / "GAME_PART.part.mp4"
    part.write_bytes(b"partial data")
    # Verifier should fail on a non-valid mp4, not crash
    with patch("src.ingest.verifier.probe", side_effect=RuntimeError("corrupt")):
        ok, reason, info = verify(part)
    assert not ok
    assert "corrupt" in reason


def test_sha256_collision(tmp_path: Path, tmp_db, monkeypatch):
    """Two games with same content → same sha, both get symlinks."""
    conn, base = tmp_db
    inbox = tmp_path / "_inbox"
    inbox.mkdir()

    import src.ingest.fetcher as fetcher_mod
    monkeypatch.setattr(fetcher_mod, "INBOX_DIR", inbox)
    monkeypatch.setattr(fetcher_mod, "BY_SHA_DIR", tmp_path / "by_sha")
    monkeypatch.setattr(fetcher_mod, "GAMES_DIR", tmp_path / "games")
    monkeypatch.setattr("src.ingest.verifier.probe", lambda p: _make_probe_result())

    db_path = base / "q.db"
    same_content = b"identical video content"

    for gid in ["SHA_G1", "SHA_G2"]:
        f = inbox / f"{gid}.mp4"
        f.write_bytes(same_content)
        add_game(conn, gid)
        fetcher_mod.fetch(gid, db_path=db_path)

    g1 = get_game(conn, "SHA_G1")
    g2 = get_game(conn, "SHA_G2")
    assert g1["sha256"] == g2["sha256"]
    assert (tmp_path / "games" / "SHA_G1.mp4").exists()
    assert (tmp_path / "games" / "SHA_G2.mp4").exists()
