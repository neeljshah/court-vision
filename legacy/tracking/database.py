"""PostgreSQL connection factory and schema initialization for the NBA tracking system."""

import os
import pathlib

import psycopg2
from dotenv import load_dotenv

# Load .env file if present (no-op if DATABASE_URL is already set in environment)
load_dotenv()

_SCHEMA_PATH = pathlib.Path(__file__).parent / "schema.sql"
_ROOT = pathlib.Path(__file__).parent.parent
_SCHEMA_EXT_PATH = _ROOT / "features" / "schema_extensions.sql"


def get_connection():
    """Return a psycopg2 connection using the DATABASE_URL environment variable.

    Raises:
        EnvironmentError: If DATABASE_URL is not set in the environment.
        psycopg2.OperationalError: If the database cannot be reached.
    """
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise EnvironmentError(
            "DATABASE_URL environment variable is not set. "
            "Copy .env.example to .env and fill in your PostgreSQL connection string."
        )
    return psycopg2.connect(dsn)


def init_schema():
    """Create all tables defined in schema.sql if they do not already exist.

    Reads tracking/schema.sql relative to this file and executes it against the
    database specified by DATABASE_URL.  Safe to run multiple times because every
    CREATE statement uses IF NOT EXISTS.
    """
    sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    ext_sql = _SCHEMA_EXT_PATH.read_text(encoding="utf-8")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            cur.execute(ext_sql)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    print("Initializing database schema…")
    init_schema()
    print("Schema initialized successfully.")
