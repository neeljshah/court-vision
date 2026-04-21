"""SQLite connection helper with WAL mode and schema migrations."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Optional

_DB_PATH: Optional[Path] = None
_lock = threading.local()
_init_lock = threading.Lock()

SCHEMA_SQL = Path(__file__).with_name("schema.sql")
DEFAULT_DB = Path(__file__).parents[2] / "data" / "ingest" / "queue.db"


def set_db_path(path: Optional[Path]) -> None:
    global _DB_PATH
    _DB_PATH = Path(path) if path is not None else None


def get_db_path() -> Path:
    return _DB_PATH if _DB_PATH is not None else DEFAULT_DB


def connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Return a WAL-mode connection. Thread-safe initialization via lock."""
    path = Path(db_path) if db_path else get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _init_lock:
        conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-20000")       # 20 MB per connection
        conn.execute("PRAGMA wal_autocheckpoint=1000") # checkpoint every ~4 MB
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    """Apply schema.sql idempotently."""
    sql = SCHEMA_SQL.read_text()
    conn.executescript(sql)
    conn.commit()
