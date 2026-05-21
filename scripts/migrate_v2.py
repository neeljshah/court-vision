"""
migrate_v2.py — Apply the multi-sport data lake schema (schema_v2.sql).

Reads database/schema_v2.sql and executes every DDL statement against the
active database backend:
  - PostgreSQL when DATABASE_URL env var is set.
  - SQLite fallback (data/nba_ai.db) otherwise.

Re-run safe: all statements use CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS.

Usage:
    python scripts/migrate_v2.py
    python scripts/migrate_v2.py --sql-file path/to/other.sql
    python scripts/migrate_v2.py --help
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import List, Tuple

# ── Bootstrap sys.path so src.data.db is importable ──────────────────────────
PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from src.data.db import get_connection, is_postgres  # noqa: E402

# ── Paths ─────────────────────────────────────────────────────────────────────
DEFAULT_SQL_FILE = PROJECT_DIR / "database" / "schema_v2.sql"

# ── Expected new tables (used for summary reporting) ──────────────────────────
EXPECTED_TABLES: List[str] = [
    "sports",
    "box_scores",
    "play_by_play",
    "odds_lines",
    "prop_lines",
    "prop_outcomes",
    "injuries",
    "news_items",
    "scraper_runs",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="migrate_v2",
        description=(
            "Apply the multi-sport data lake schema (schema_v2.sql) to the "
            "active database. Safe to re-run — all DDL uses IF NOT EXISTS."
        ),
    )
    parser.add_argument(
        "--sql-file",
        type=Path,
        default=DEFAULT_SQL_FILE,
        metavar="PATH",
        help=f"Path to the SQL file to apply (default: {DEFAULT_SQL_FILE})",
    )
    return parser.parse_args()


def load_sql(sql_file: Path) -> str:
    """Read and return raw SQL text; raise FileNotFoundError with a clear message."""
    if not sql_file.exists():
        raise FileNotFoundError(
            f"SQL file not found: {sql_file}\n"
            "Make sure you are running from the project root or pass --sql-file."
        )
    return sql_file.read_text(encoding="utf-8")


def split_statements(sql_text: str) -> List[str]:
    """
    Split a SQL file into individual statements on semicolons,
    stripping blank lines and comment-only blocks.
    """
    # Remove single-line comments (-- ...) before splitting
    cleaned = re.sub(r"--[^\n]*", "", sql_text)
    raw_stmts = cleaned.split(";")
    stmts: List[str] = []
    for stmt in raw_stmts:
        stripped = stmt.strip()
        if stripped:
            stmts.append(stripped)
    return stmts


def extract_table_names(statements: List[str]) -> List[str]:
    """Return table names from CREATE TABLE IF NOT EXISTS statements."""
    names: List[str] = []
    pattern = re.compile(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)", re.IGNORECASE
    )
    for stmt in statements:
        m = pattern.search(stmt)
        if m:
            names.append(m.group(1))
    return names


def detect_backend(conn) -> str:
    """Return 'postgres' or 'sqlite'."""
    return "postgres" if is_postgres(conn) else "sqlite"


def run_migration(sql_file: Path) -> Tuple[int, int, List[str], str]:
    """
    Apply every statement from sql_file via get_connection().

    Returns:
        (applied_count, skipped_count, table_names_created, backend_name)
    """
    sql_text = load_sql(sql_file)
    statements = split_statements(sql_text)
    table_names = extract_table_names(statements)

    conn = get_connection()
    backend = detect_backend(conn)
    applied = 0
    skipped = 0

    try:
        with conn.cursor() as cur:
            for stmt in statements:
                if not stmt.strip():
                    skipped += 1
                    continue

                # schema_v2.sql is portable DDL — applies as-is on both backends
                exec_stmt = stmt

                try:
                    cur.execute(exec_stmt)
                    applied += 1

                    # Report table creations as they happen
                    m = re.search(
                        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)",
                        exec_stmt,
                        re.IGNORECASE,
                    )
                    if m:
                        print(f"  [ok] table  {m.group(1)}")

                    # Report index creations
                    mi = re.search(
                        r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS\s+(\w+)",
                        exec_stmt,
                        re.IGNORECASE,
                    )
                    if mi:
                        print(f"  [ok] index  {mi.group(1)}")

                except Exception as exc:  # noqa: BLE001
                    # On SQLite, a few PostgreSQL-isms may slip through;
                    # report them but keep going so idempotency isn't broken.
                    print(f"  [warn] statement skipped: {exc}", file=sys.stderr)
                    print(f"         statement: {exec_stmt[:120]}...", file=sys.stderr)
                    skipped += 1

        conn.commit()
    finally:
        conn.close()

    return applied, skipped, table_names, backend


def verify_tables(table_names: List[str], backend: str) -> List[str]:
    """
    Re-open a fresh connection and confirm every expected table exists.
    Returns list of confirmed table names.
    """
    conn = get_connection()
    confirmed: List[str] = []
    try:
        with conn.cursor() as cur:
            if backend == "postgres":
                cur.execute(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                )
                existing = {row[0] for row in cur.fetchall()}
            else:
                cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                existing = {row[0] for row in cur.fetchall()}

        for name in table_names:
            if name in existing:
                confirmed.append(name)
    finally:
        conn.close()
    return confirmed


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()
    sql_file: Path = args.sql_file

    print(f"\nmigrate_v2 - applying {sql_file.name}")
    print(f"  sql file : {sql_file}")
    print()

    try:
        applied, skipped, table_names, backend = run_migration(sql_file)
    except FileNotFoundError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"[error] unexpected failure: {exc}", file=sys.stderr)
        sys.exit(1)

    # Verify tables are present
    confirmed = verify_tables(table_names, backend)
    missing = [t for t in EXPECTED_TABLES if t not in confirmed]

    print()
    print("-" * 60)
    print(f"  backend  : {backend.upper()}")
    print(f"  sql file : {sql_file.name}")
    print(f"  applied  : {applied} statement(s)")
    print(f"  skipped  : {skipped} statement(s)")
    print(f"  tables   : {len(confirmed)} confirmed - {', '.join(sorted(confirmed))}")

    if missing:
        print(f"  MISSING  : {', '.join(missing)}", file=sys.stderr)
        print("\n[FAIL] some expected tables were not created.", file=sys.stderr)
        sys.exit(1)
    else:
        print()
        print("  All 9 data lake tables verified. Migration complete.")
        print()


if __name__ == "__main__":
    main()
