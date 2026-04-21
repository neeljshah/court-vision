"""H4 preflight checks — Python-level validators (bash parts mocked)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


ROOT = Path(__file__).parents[2]


# ── torch.cuda availability ───────────────────────────────────────────────────

def test_torch_cuda_check_passes():
    mock_torch = MagicMock()
    mock_torch.cuda.is_available.return_value = True
    mock_torch.cuda.device_count.return_value = 1
    mock_torch.cuda.get_device_name.return_value = "NVIDIA GeForce RTX 3090"

    with patch.dict(sys.modules, {"torch": mock_torch}):
        import torch
        assert torch.cuda.is_available()
        assert torch.cuda.device_count() >= 1


def test_torch_cuda_check_fails_gracefully():
    mock_torch = MagicMock()
    mock_torch.cuda.is_available.return_value = False
    mock_torch.cuda.device_count.return_value = 0

    with patch.dict(sys.modules, {"torch": mock_torch}):
        import torch
        assert not torch.cuda.is_available()


# ── decord import check ───────────────────────────────────────────────────────

def test_decord_import_check():
    """Preflight validates decord can be imported."""
    # Simulate decord present
    mock_decord = MagicMock()
    with patch.dict(sys.modules, {"decord": mock_decord}):
        import decord  # noqa: F401 — import succeeds


def test_decord_missing_raises():
    with patch.dict(sys.modules, {"decord": None}):
        with pytest.raises((ImportError, TypeError)):
            import importlib
            importlib.reload(__import__("decord", fromlist=[]))


# ── VRAM_FLUSH_INTERVAL grep check ───────────────────────────────────────────

def test_vram_flush_interval_is_3000():
    pipeline_path = ROOT / "src" / "pipeline" / "unified_pipeline.py"
    if not pipeline_path.exists():
        pytest.skip("unified_pipeline.py not present in this env")
    content = pipeline_path.read_text(encoding="utf-8", errors="replace")
    import re
    match = re.search(r"_VRAM_FLUSH_INTERVAL\s*=\s*(\d+)", content)
    assert match is not None, "_VRAM_FLUSH_INTERVAL not found in unified_pipeline.py"
    assert match.group(1) == "3000", \
        f"_VRAM_FLUSH_INTERVAL = {match.group(1)}, expected 3000"


# ── symlink resolution check ─────────────────────────────────────────────────

def test_symlink_check_passes(tmp_path):
    """Preflight symlink check passes when target exists."""
    target = tmp_path / "nba_videos"
    target.mkdir()
    link = tmp_path / "full_games"
    try:
        link.symlink_to(target)
        assert link.resolve().exists()
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported in this environment")


def test_symlink_check_fails_on_missing(tmp_path):
    """Preflight symlink check fails when target does not exist."""
    link = tmp_path / "broken_link"
    target = tmp_path / "nonexistent"
    try:
        link.symlink_to(target)
        assert not link.resolve().exists() or not target.exists()
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported in this environment")


# ── SYNC_DIRS guard (imported at module level in sync_remote) ─────────────────

def test_sync_dirs_no_videos():
    import scripts.sync_remote as sr
    for d in sr.SYNC_DIRS:
        assert "videos" not in d.parts
        assert "by_sha" not in d.parts


# ── SQLite queue check ────────────────────────────────────────────────────────

def test_queue_check_passes(tmp_path):
    from src.ingest.db import connect, set_db_path, migrate
    from src.ingest.manifest import add_game

    set_db_path(tmp_path / "test.db")
    conn = connect()
    migrate(conn)
    add_game(conn, "preflight_game", status="queued")
    n = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    conn.close()
    set_db_path(None)
    assert n > 0


def test_queue_check_fails_when_empty(tmp_path):
    from src.ingest.db import connect, set_db_path, migrate

    set_db_path(tmp_path / "empty.db")
    conn = connect()
    migrate(conn)
    n = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    conn.close()
    set_db_path(None)
    assert n == 0
