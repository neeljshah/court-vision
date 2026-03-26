"""
db.py — Database connection helper for the NBA AI system.

Returns a psycopg2 connection when DATABASE_URL is set (PostgreSQL).
Falls back to a SQLite adapter (data/nba_ai.db) when DATABASE_URL is not set.
Both expose the same cursor interface — callers need no changes.

Usage (PostgreSQL):
    export DATABASE_URL="postgresql://postgres:password@localhost:5432/nba_ai"
    conn = get_connection()

Usage (SQLite fallback — no setup required):
    # Just call get_connection() — creates data/nba_ai.db automatically
    conn = get_connection()

As context manager (both backends):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
"""
from __future__ import annotations

import os
import re
import sqlite3
from typing import Optional

_ENV_VAR    = "DATABASE_URL"
_SQLITE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "nba_ai.db",
)

# ── SQL translation helpers ───────────────────────────────────────────────────

_CAST_RE = re.compile(
    r"::(uuid|text|integer|bigint|boolean|real|float|smallint|varchar(?:\(\d+\))?)",
    re.IGNORECASE,
)
_NAMED_PARAM_RE = re.compile(r"%\((\w+)\)s")


def _to_sqlite(sql: str) -> str:
    """Translate PostgreSQL SQL to SQLite-compatible SQL."""
    sql = _CAST_RE.sub("", sql)
    sql = _NAMED_PARAM_RE.sub(r":\1", sql)
    # ON CONFLICT DO NOTHING → INSERT OR IGNORE
    if re.search(r"\bON CONFLICT DO NOTHING\b", sql, re.IGNORECASE):
        sql = re.sub(r"\bON CONFLICT DO NOTHING\b", "", sql, flags=re.IGNORECASE)
        sql = re.sub(r"\bINSERT INTO\b", "INSERT OR IGNORE INTO", sql, flags=re.IGNORECASE)
    return sql


# ── SQLite adapter ────────────────────────────────────────────────────────────

class _SQLiteCursor:
    """Wraps sqlite3.Cursor to look like a psycopg2 cursor."""

    def __init__(self, cur: sqlite3.Cursor) -> None:
        self._cur = cur

    def execute(self, sql: str, params=None):
        sql = _to_sqlite(sql)
        self._cur.execute(sql) if params is None else self._cur.execute(sql, params)
        return self

    def executemany(self, sql: str, params_seq):
        self._cur.executemany(_to_sqlite(sql), params_seq)
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def fetchmany(self, size: int = 100):
        return self._cur.fetchmany(size)

    def close(self):
        self._cur.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    @property
    def rowcount(self) -> int:
        return self._cur.rowcount


class _SQLiteConnection:
    """Wraps sqlite3.Connection to look like a psycopg2 connection."""

    def __init__(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=OFF")   # relax FKs for partial data
        # Ensure cv_features and scoreboard_log tables always exist (Phase 5).
        # Full schema is in migrations.py; these are the tables most likely to be
        # new when upgrading an existing DB that was created before Phase 5.
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS cv_features (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id      TEXT NOT NULL,
                player_id    INTEGER NOT NULL,
                feature_name TEXT NOT NULL,
                feature_value REAL,
                created_at   TEXT DEFAULT (datetime('now')),
                UNIQUE (game_id, player_id, feature_name)
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS scoreboard_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id    TEXT,
                frame      INTEGER,
                game_clock TEXT,
                shot_clock REAL,
                home_score INTEGER,
                away_score INTEGER,
                period     INTEGER,
                confidence REAL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        self._conn.commit()

    def cursor(self) -> _SQLiteCursor:
        return _SQLiteCursor(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()


# ── Public API ────────────────────────────────────────────────────────────────

def get_connection(db_url: Optional[str] = None):
    """
    Return a database connection.

    Uses PostgreSQL (psycopg2) when DATABASE_URL is set.
    Falls back to SQLite (data/nba_ai.db) when DATABASE_URL is not set.

    Args:
        db_url: Explicit PostgreSQL URL. If None, reads DATABASE_URL env var.
                Pass db_url='' to force SQLite even if DATABASE_URL is set.

    Returns:
        psycopg2 connection or _SQLiteConnection — same cursor interface.
    """
    url = db_url if db_url is not None else os.environ.get(_ENV_VAR)
    if url:
        import psycopg2
        import psycopg2.extras  # noqa: F401 — ensure extras available
        return psycopg2.connect(url)
    return _SQLiteConnection(_SQLITE_PATH)


def is_postgres(conn=None) -> bool:
    """Return True if the active backend is PostgreSQL."""
    if conn is not None:
        return not isinstance(conn, _SQLiteConnection)
    return bool(os.environ.get(_ENV_VAR))


def execute_batch(cur, sql: str, params_list, page_size: int = 500) -> None:
    """
    Batch insert helper.

    Uses psycopg2.extras.execute_batch for PostgreSQL,
    executemany for SQLite.
    """
    if isinstance(cur, _SQLiteCursor):
        cur.executemany(sql, params_list)
    else:
        import psycopg2.extras
        psycopg2.extras.execute_batch(cur, sql, params_list, page_size=page_size)


if __name__ == "__main__":
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
        print("DB connection OK —", "PostgreSQL" if is_postgres(conn) else f"SQLite ({_SQLITE_PATH})")
    conn.close()
