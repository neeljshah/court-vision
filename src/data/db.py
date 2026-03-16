"""
db.py — PostgreSQL connection helper for the NBA AI system.

Reads DATABASE_URL from environment or accepts explicit URL.
Uses psycopg2 (synchronous) — sufficient for batch processing in Phase 2-4.
asyncpg (async) will be added in Phase 7 (FastAPI backend).

Usage:
    export DATABASE_URL="postgresql://postgres:password@localhost:5432/nba_ai"
    conn = get_connection()
    conn.close()

Or as context manager:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
"""
from __future__ import annotations

import os
from typing import Optional

import psycopg2
import psycopg2.extras


_ENV_VAR = "DATABASE_URL"


def get_connection(db_url: Optional[str] = None) -> psycopg2.extensions.connection:
    """
    Return a live psycopg2 connection.

    Args:
        db_url: Connection string e.g. 'postgresql://user:pass@host:5432/db'.
                If None, reads DATABASE_URL from environment.

    Returns:
        psycopg2 connection (caller must close or use as context manager).

    Raises:
        ValueError: if db_url is None and DATABASE_URL not set.
        psycopg2.OperationalError: if connection fails.
    """
    url = db_url or os.environ.get(_ENV_VAR)
    if not url:
        raise ValueError(
            f"{_ENV_VAR} not set. "
            "Export it: export DATABASE_URL='postgresql://user:pass@host:5432/nba_ai'"
        )
    return psycopg2.connect(url)


if __name__ == "__main__":
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT version()")
        print(cur.fetchone()[0])
    conn.close()
