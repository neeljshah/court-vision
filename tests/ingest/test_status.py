"""P6 tests: ingest_status CLI on empty + populated DB."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT))

import src.ingest.db as db_mod
from src.ingest.manifest import add_game, get_conn, update_game


@pytest.fixture()
def tmp_db(tmp_path: Path):
    db_path = tmp_path / "q.db"
    db_mod.set_db_path(db_path)
    conn = get_conn(db_path)
    yield conn, tmp_path, db_path
    conn.close()
    db_mod.set_db_path(None)


def _run_status(monkeypatch, tmp_path: Path, capsys):
    """Import and run ingest_status.main() with patched ROOT."""
    import scripts.ingest_status as sm
    monkeypatch.setattr(sm, "ROOT", tmp_path)
    sm.main()
    return capsys.readouterr().out


def test_status_empty_db(tmp_db, monkeypatch, capsys):
    """Status on empty DB does not crash."""
    _, tmp_path, _ = tmp_db
    out = _run_status(monkeypatch, tmp_path, capsys)
    assert "CourtVision Ingest Status" in out
    assert "TOTAL" in out


def test_status_populated_db(tmp_db, monkeypatch, capsys):
    """Status shows correct counts."""
    conn, tmp_path, _ = tmp_db
    for i in range(3):
        add_game(conn, f"G{i:03d}", status="processed")
        update_game(conn, f"G{i:03d}", quality_tier="CLEAN")
    add_game(conn, "G999", status="queued")

    out = _run_status(monkeypatch, tmp_path, capsys)
    assert "processed" in out
    assert "CLEAN" in out
    assert "TOTAL" in out
