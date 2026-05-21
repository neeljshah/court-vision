"""
tests/test_historical_odds_backfill.py — Unit tests for historical_odds_backfill.

All tests are fully offline — no network calls are made.
"""

from __future__ import annotations

import os
import re
import sqlite3
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.data.scrapers.historical_odds_backfill import (  # noqa: E402
    OddsBackfillIngester,
    fetch_season,
    parse_sportsoddshistory_table,
)

# ── Minimal DDL for the temp SQLite DB ───────────────────────────────────────

_CREATE_ODDS_LINES = """
CREATE TABLE IF NOT EXISTS odds_lines (
    id          TEXT PRIMARY KEY,
    sport       TEXT NOT NULL,
    game_id     TEXT NOT NULL,
    bookmaker   TEXT NOT NULL,
    market      TEXT NOT NULL,
    home_odds   REAL,
    away_odds   REAL,
    draw_odds   REAL,
    spread_home REAL,
    spread_away REAL,
    total_over  REAL,
    total_under REAL,
    is_opening  INTEGER DEFAULT 0,
    is_closing  INTEGER DEFAULT 0,
    recorded_at TEXT
)
"""

_CREATE_SCRAPER_RUNS = """
CREATE TABLE IF NOT EXISTS scraper_runs (
    id              TEXT PRIMARY KEY,
    sport           TEXT NOT NULL,
    source          TEXT NOT NULL,
    run_type        TEXT DEFAULT 'full',
    run_started_at  TEXT,
    run_finished_at TEXT,
    status          TEXT DEFAULT 'running',
    rows_written    INTEGER DEFAULT 0,
    last_key        TEXT,
    error_message   TEXT,
    run_config      TEXT
)
"""

_NAMED_RE = re.compile(r"%\((\w+)\)s")


class _TestCursor:
    """Thin cursor wrapper that translates %(name)s → :name for native sqlite3."""

    def __init__(self, cur: sqlite3.Cursor) -> None:
        self._cur = cur

    def _fix(self, sql: str) -> str:
        return _NAMED_RE.sub(r":\1", sql)

    def execute(self, sql: str, params=None):
        if params is None:
            self._cur.execute(self._fix(sql))
        else:
            self._cur.execute(self._fix(sql), params)
        return self

    def executemany(self, sql: str, params_seq):
        self._cur.executemany(self._fix(sql), params_seq)
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    @property
    def rowcount(self) -> int:
        return self._cur.rowcount


class _TestConnection:
    """sqlite3.Connection wrapper that returns _TestCursor and supports commit/close."""

    def __init__(self, path: str) -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

    def cursor(self) -> _TestCursor:
        return _TestCursor(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def _make_db(path: str) -> None:
    """Create temp SQLite DB with the tables needed for tests."""
    conn = sqlite3.connect(path)
    conn.execute(_CREATE_ODDS_LINES)
    conn.execute(_CREATE_SCRAPER_RUNS)
    conn.commit()
    conn.close()


# ── Test 1: parser correctness ────────────────────────────────────────────────

SAMPLE_HTML = """
<html><body>
<table>
  <tr><th>Date</th><th>Away</th><th>Home</th><th>Spread</th><th>Total</th></tr>
  <tr>
    <td>10/19/2023</td>
    <td>Lakers</td>
    <td>Nuggets</td>
    <td>+5.5</td>
    <td>O/U 227.5</td>
  </tr>
  <tr>
    <td>10/20/2023</td>
    <td>Celtics</td>
    <td>Heat</td>
    <td>-3.5</td>
    <td>OU 215.0</td>
  </tr>
</table>
</body></html>
"""


def test_parse_sportsoddshistory_table():
    records = parse_sportsoddshistory_table(SAMPLE_HTML, "2023-24")
    assert len(records) == 2, f"Expected 2 records, got {len(records)}"

    for rec in records:
        assert rec["is_closing"] is True
        assert rec["is_opening"] is False
        assert isinstance(rec["spread_home"], float)
        assert isinstance(rec["total_over"], float)

    game1, game2 = records
    assert game1["away_team"] == "Lakers"
    assert game1["home_team"] == "Nuggets"
    assert game1["spread_home"] == pytest.approx(5.5)
    assert game1["total_over"] == pytest.approx(227.5)

    assert game2["away_team"] == "Celtics"
    assert game2["home_team"] == "Heat"
    assert game2["spread_home"] == pytest.approx(-3.5)
    assert game2["total_over"] == pytest.approx(215.0)


# ── Test 2: ingester writes odds_lines rows ───────────────────────────────────

_SYNTHETIC_RECORDS = [
    {
        "game_id": "2023-24_10/19/2023_Lakers_Nuggets",
        "game_date": "10/19/2023",
        "home_team": "Nuggets",
        "away_team": "Lakers",
        "bookmaker": "consensus",
        "market": "game",
        "spread_home": 5.5,
        "total_over": 227.5,
        "is_opening": False,
        "is_closing": True,
    },
    {
        "game_id": "2023-24_10/20/2023_Celtics_Heat",
        "game_date": "10/20/2023",
        "home_team": "Heat",
        "away_team": "Celtics",
        "bookmaker": "consensus",
        "market": "game",
        "spread_home": -3.5,
        "total_over": 215.0,
        "is_opening": False,
        "is_closing": True,
    },
    {
        "game_id": "2023-24_10/21/2023_Warriors_Suns",
        "game_date": "10/21/2023",
        "home_team": "Suns",
        "away_team": "Warriors",
        "bookmaker": "consensus",
        "market": "game",
        "spread_home": -1.5,
        "total_over": 230.0,
        "is_opening": False,
        "is_closing": True,
    },
]


def test_ingester_writes_odds_lines(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_nba.db")
    _make_db(db_path)

    import src.data.scrapers.historical_odds_backfill as mod

    # Use _TestConnection so %(name)s placeholders are translated for sqlite3.
    monkeypatch.setattr(mod, "get_connection", lambda: _TestConnection(db_path))
    # execute_batch: our _TestCursor is not _SQLiteCursor so delegate to executemany.
    monkeypatch.setattr(mod, "execute_batch", lambda cur, sql, params, page_size=500: cur.executemany(sql, params))
    monkeypatch.setattr(mod, "fetch_season", lambda season, force=False: _SYNTHETIC_RECORDS)

    result = OddsBackfillIngester().backfill(["2023-24"])
    assert result["rows_written"] == 3

    # Verify DB state via raw sqlite3 (no wrapper needed for reads).
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM odds_lines").fetchall()
    assert len(rows) == 3
    for row in rows:
        assert row["is_closing"], f"Expected is_closing to be truthy, got {row['is_closing']}"

    run_rows = conn.execute(
        "SELECT * FROM scraper_runs WHERE status = 'success'"
    ).fetchall()
    assert len(run_rows) == 1
    assert run_rows[0]["rows_written"] == 3
    conn.close()


# ── Test 3: incremental skips already-processed seasons ───────────────────────


def test_incremental_resumes(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_resume.db")
    _make_db(db_path)

    # Pre-seed a completed run for "2022-23"
    import uuid as _uuid
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO scraper_runs
           (id, sport, source, run_type, run_started_at, status, last_key, rows_written)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            _uuid.uuid4().hex,
            "nba",
            "sportsoddshistory",
            "full",
            "2024-01-01T00:00:00",
            "success",
            "2022-23",
            10,
        ),
    )
    conn.commit()
    conn.close()

    import src.data.scrapers.historical_odds_backfill as mod

    # Use _TestConnection so %(name)s placeholders are translated for sqlite3.
    monkeypatch.setattr(mod, "get_connection", lambda: _TestConnection(db_path))
    monkeypatch.setattr(mod, "execute_batch", lambda cur, sql, params, page_size=500: cur.executemany(sql, params))

    called_for: list = []

    def tracking_fetch(season, force=False):
        called_for.append(season)
        return _SYNTHETIC_RECORDS[:1]  # return 1 row so the run succeeds

    monkeypatch.setattr(mod, "fetch_season", tracking_fetch)

    OddsBackfillIngester().incremental(["2022-23", "2023-24"])

    assert "2022-23" not in called_for, (
        f"fetch_season should NOT have been called for 2022-23, but called_for={called_for}"
    )
    assert "2023-24" in called_for, (
        f"fetch_season SHOULD have been called for 2023-24, but called_for={called_for}"
    )
