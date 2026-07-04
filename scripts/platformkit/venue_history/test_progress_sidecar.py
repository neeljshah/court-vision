"""Tests for scripts.platformkit.venue_history.progress_sidecar."""
from __future__ import annotations

from pathlib import Path

from scripts.platformkit.venue_history import progress_sidecar as ps


def test_load_missing_returns_empty(tmp_path: Path) -> None:
    assert ps.load_progress(tmp_path / "nope.json") == {}


def test_save_then_load_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "progress.json"
    doc = {"cursor": "ABC", "n": 3}
    ps.save_progress(path, doc)
    assert path.is_file()
    assert ps.load_progress(path) == doc


def test_save_is_atomic_no_leftover_tmp(tmp_path: Path) -> None:
    path = tmp_path / "progress.json"
    ps.save_progress(path, {"a": 1})
    assert not (tmp_path / "progress.json.tmp").exists()
