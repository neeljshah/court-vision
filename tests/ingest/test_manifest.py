"""P1 tests: manifest DB — schema, CRUD, migration idempotency, concurrency."""
from __future__ import annotations

import csv
import tempfile
import threading
from pathlib import Path

import pytest

import src.ingest.db as db_mod
from src.ingest.db import connect, migrate
from src.ingest.manifest import (
    add_game,
    get_game,
    get_conn,
    list_games,
    log_event,
    migrate_legacy,
    update_game,
)


@pytest.fixture()
def tmp_db(tmp_path: Path):
    db_path = tmp_path / "test_queue.db"
    db_mod.set_db_path(db_path)
    conn = get_conn(db_path)
    yield conn, tmp_path
    conn.close()
    db_mod.set_db_path(None)  # reset


# ── schema ─────────────────────────────────────────────────────────────────────

def test_schema_creates_cleanly(tmp_path: Path):
    db_path = tmp_path / "fresh.db"
    conn = connect(db_path)
    migrate(conn)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"games", "downloads", "events"} <= tables
    conn.close()


# ── CRUD ───────────────────────────────────────────────────────────────────────

def test_add_get_roundtrip(tmp_db):
    conn, _ = tmp_db
    add_game(conn, "GAME001", source="youtube", quality_tier="high")
    row = get_game(conn, "GAME001")
    assert row is not None
    assert row["game_id"] == "GAME001"
    assert row["status"] == "queued"
    assert row["source"] == "youtube"
    assert row["quality_tier"] == "high"


def test_update_game(tmp_db):
    conn, _ = tmp_db
    add_game(conn, "GAME002")
    update_game(conn, "GAME002", status="processing", attempts=1)
    row = get_game(conn, "GAME002")
    assert row["status"] == "processing"
    assert row["attempts"] == 1


def test_list_games_filter(tmp_db):
    conn, _ = tmp_db
    add_game(conn, "G1", status="queued")
    add_game(conn, "G2", status="processed")
    add_game(conn, "G3", status="queued")
    queued = list_games(conn, "queued")
    assert len(queued) == 2
    all_games = list_games(conn)
    assert len(all_games) == 3


def test_log_event(tmp_db):
    conn, _ = tmp_db
    add_game(conn, "GEVT")
    log_event(conn, "GEVT", "fetch", "info", {"msg": "started"})
    row = conn.execute("SELECT * FROM events WHERE game_id='GEVT'").fetchone()
    assert row is not None
    assert row["stage"] == "fetch"


# ── migration ──────────────────────────────────────────────────────────────────

def _make_legacy_files(tmp_path: Path):
    proc = tmp_path / "phase_g_processed.txt"
    proc.write_text("AAA001\nBBB002\nCCC003\n")

    csv_path = tmp_path / "phase_g_metrics.csv"
    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["timestamp","game_key","game_id","frames","stability","id_switches","ball_valid_pct","quality","duration_s"])
        writer.writeheader()
        writer.writerow({"timestamp":"2026-01-01T00:00:00","game_key":"AAA001","game_id":"AAA001","frames":"5000","stability":"0.9","id_switches":"2","ball_valid_pct":"75.0","quality":"high","duration_s":"2400"})
        writer.writerow({"timestamp":"2026-01-01T01:00:00","game_key":"BBB002","game_id":"BBB002","frames":"3000","stability":"0.6","id_switches":"10","ball_valid_pct":"35.0","quality":"low","duration_s":"1900"})
    return proc, csv_path


def test_migration_idempotent(tmp_path: Path, monkeypatch):
    proc, csv_path = _make_legacy_files(tmp_path)
    monkeypatch.setattr("src.ingest.manifest.PROCESSED_TXT", proc)
    monkeypatch.setattr("src.ingest.manifest.METRICS_CSV", csv_path)

    db_path = tmp_path / "q.db"
    conn = get_conn(db_path)

    n1 = migrate_legacy(conn)
    assert n1 == 3

    n2 = migrate_legacy(conn)
    assert n2 == 0  # idempotent

    rows = list_games(conn)
    assert len(rows) == 3
    aaa = get_game(conn, "AAA001")
    assert aaa["status"] == "processed"
    assert aaa["quality_tier"] == "high"
    conn.close()


def test_migration_missing_files(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("src.ingest.manifest.PROCESSED_TXT", tmp_path / "nope.txt")
    monkeypatch.setattr("src.ingest.manifest.METRICS_CSV",   tmp_path / "nope.csv")
    db_path = tmp_path / "q2.db"
    conn = get_conn(db_path)
    n = migrate_legacy(conn)
    assert n == 0
    conn.close()


# ── concurrency ────────────────────────────────────────────────────────────────

def test_concurrent_inserts(tmp_path: Path):
    db_path = tmp_path / "concurrent.db"
    errors: list = []

    def worker(thread_id: int):
        conn = get_conn(db_path)
        try:
            for i in range(100):
                gid = f"T{thread_id}_{i:03d}"
                add_game(conn, gid, source="test")
        except Exception as e:
            errors.append(e)
        finally:
            conn.close()

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Concurrency errors: {errors}"
    conn = get_conn(db_path)
    count = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    assert count == 200
    conn.close()
