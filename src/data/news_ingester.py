"""
news_ingester.py — Persist RotoWire news items to the news_items SQLite table.

Public API
----------
    NewsIngester(db_path)   class with .ingest() -> int
    ingest_all(db_path)     module-level convenience wrapper
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_DB = os.path.join(PROJECT_DIR, "data", "nba", "nba_data.db")

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS news_items (
    id          TEXT PRIMARY KEY,
    sport       TEXT NOT NULL,
    player_id   TEXT,
    team_id     TEXT,
    game_id     TEXT,
    headline    TEXT NOT NULL,
    body        TEXT,
    source      TEXT,
    url         TEXT,
    published_at TEXT,
    impact      TEXT
)
"""

_INSERT_SQL = """
INSERT OR IGNORE INTO news_items
    (id, sport, player_id, team_id, game_id, headline, body, source, url, published_at, impact)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _severity_to_impact(status_guess: str) -> str:
    """Map RotoWire status_guess to HIGH / MEDIUM / LOW impact label."""
    s = (status_guess or "").strip().lower()
    if s == "out":
        return "HIGH"
    if s in ("questionable", "doubtful"):
        return "MEDIUM"
    return "LOW"


def _make_id(source: str, player_name: str, headline: str, published_at: str) -> str:
    """Deterministic 16-char hex ID for dedup."""
    raw = f"{source}|{player_name}|{headline}|{published_at}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _parse_published(raw: str) -> str:
    """Return ISO datetime string; fall back to utcnow if unparsable."""
    if not raw:
        return datetime.utcnow().isoformat()
    # feedparser gives RFC 2822 strings like "Mon, 20 May 2024 10:00:00 +0000"
    # Try a few common formats
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(raw.strip(), fmt).isoformat()
        except ValueError:
            continue
    return datetime.utcnow().isoformat()


class NewsIngester:
    """
    Reads from RotoWire via injury_monitor.refresh_rotowire() and
    persists items to the news_items table.

    Args:
        db_path: Path to the SQLite DB file.
                 Defaults to data/nba/nba_data.db.
                 Pass ":memory:" for in-memory testing.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or _DEFAULT_DB

    # ── public ────────────────────────────────────────────────────────────────

    def ingest(self) -> int:
        """
        Fetch latest RotoWire news and insert new rows (dedup by primary key).

        Returns:
            Number of NEW rows inserted (duplicates silently skipped).
        """
        from src.data.injury_monitor import refresh_rotowire

        items = refresh_rotowire()
        if not items:
            return 0

        rows = [self._item_to_row(item) for item in items]

        con = self._connect()
        try:
            self._ensure_table(con)
            cur = con.cursor()
            before = self._row_count(cur)
            cur.executemany(_INSERT_SQL, rows)
            con.commit()
            after = self._row_count(cur)
        finally:
            con.close()

        return after - before

    # ── internal ─────────────────────────────────────────────────────────────

    def _item_to_row(self, item: dict) -> tuple:
        player_name = item.get("player_name", "")
        headline    = item.get("headline", "")
        published   = _parse_published(item.get("published", ""))
        source      = "rotowire"
        row_id      = _make_id(source, player_name, headline, published)

        return (
            row_id,
            "basketball_nba",
            None,                                   # player_id (no numeric ID in feed)
            item.get("team_abbrev") or None,
            None,                                   # game_id
            headline,
            item.get("summary") or None,
            source,
            None,                                   # url
            published,
            _severity_to_impact(item.get("status_guess", "")),
        )

    def _connect(self) -> sqlite3.Connection:
        if self.db_path != ":memory:":
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        return sqlite3.connect(self.db_path)

    @staticmethod
    def _ensure_table(con: sqlite3.Connection) -> None:
        con.execute(_CREATE_SQL)
        con.commit()

    @staticmethod
    def _row_count(cur: sqlite3.Cursor) -> int:
        cur.execute("SELECT COUNT(*) FROM news_items")
        return cur.fetchone()[0]


# ── module-level convenience ──────────────────────────────────────────────────

def ingest_all(db_path: Optional[str] = None) -> int:
    """
    Fetch and persist all RotoWire news items.

    Args:
        db_path: SQLite DB path.  Defaults to data/nba/nba_data.db.

    Returns:
        Number of new rows inserted.
    """
    return NewsIngester(db_path=db_path).ingest()
