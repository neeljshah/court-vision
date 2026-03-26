"""
migrations.py -- Phase C1: Apply PostgreSQL schema + migrations on first run.

Run this once to create all tables. Safe to run multiple times (IF NOT EXISTS / IF NOT EXISTS).

Usage:
    conda activate basketball_ai
    export DATABASE_URL="postgresql://postgres:password@localhost:5432/nba_ai"
    python src/data/migrations.py

    # Or from Python:
    from src.data.migrations import run_migrations
    run_migrations()
"""

from __future__ import annotations

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_SCHEMA_PATH  = os.path.join(PROJECT_DIR, "database", "schema.sql")
_MIGRATIONS_DIR = os.path.join(PROJECT_DIR, "database", "migrations")


def _get_applied_migrations(cur) -> set:
    """Return set of already-applied migration filenames."""
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id         SERIAL PRIMARY KEY,
                filename   VARCHAR(200) UNIQUE NOT NULL,
                applied_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("SELECT filename FROM schema_migrations")
        return {row[0] for row in cur.fetchall()}
    except Exception:
        return set()


def run_migrations(db_url: str | None = None, verbose: bool = True) -> bool:
    """
    Apply base schema + all pending migrations to the database.

    Routes to SQLite when DATABASE_URL is not set (no PostgreSQL needed).

    Args:
        db_url: PostgreSQL connection string. Reads DATABASE_URL env var if None.
                Omit to use SQLite fallback automatically.
        verbose: Print progress.

    Returns:
        True on success, False on error.
    """
    import os as _os
    url = db_url or _os.environ.get("DATABASE_URL")
    if not url:
        return run_sqlite_migrations(verbose=verbose)

    try:
        from src.data.db import get_connection
        conn = get_connection(db_url)
    except Exception as e:
        print(f"[migrations] Cannot connect to database: {e}")
        print("[migrations] Set DATABASE_URL env var or pass db_url parameter.")
        return False

    try:
        with conn:
            with conn.cursor() as cur:
                # 1. Apply base schema
                if os.path.exists(_SCHEMA_PATH):
                    if verbose:
                        print(f"[migrations] Applying base schema: {_SCHEMA_PATH}")
                    with open(_SCHEMA_PATH, encoding="utf-8") as f:
                        sql = f.read()
                    try:
                        cur.execute(sql)
                        if verbose:
                            print("[migrations] Base schema applied.")
                    except Exception as e:
                        print(f"[migrations] Schema error (may be harmless if tables exist): {e}")

                # 2. Apply incremental migrations
                applied = _get_applied_migrations(cur)

                migration_files = sorted(
                    f for f in os.listdir(_MIGRATIONS_DIR)
                    if f.endswith(".sql") and f not in applied
                )

                for fname in migration_files:
                    fpath = os.path.join(_MIGRATIONS_DIR, fname)
                    if verbose:
                        print(f"[migrations] Applying: {fname}")
                    with open(fpath, encoding="utf-8") as f:
                        sql = f.read()
                    try:
                        cur.execute(sql)
                        cur.execute(
                            "INSERT INTO schema_migrations (filename) VALUES (%s) ON CONFLICT DO NOTHING",
                            (fname,),
                        )
                        if verbose:
                            print(f"[migrations] Applied: {fname}")
                    except Exception as e:
                        print(f"[migrations] ERROR applying {fname}: {e}")
                        conn.rollback()
                        return False

        if verbose:
            print("[migrations] All migrations complete.")
        return True

    except Exception as e:
        print(f"[migrations] Unexpected error: {e}")
        return False
    finally:
        conn.close()


_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    game_id         TEXT PRIMARY KEY,
    season          TEXT NOT NULL DEFAULT '',
    game_date       TEXT NOT NULL DEFAULT '',
    home_team_id    INTEGER,
    away_team_id    INTEGER,
    home_score      INTEGER,
    away_score      INTEGER,
    home_won        INTEGER,
    status          TEXT DEFAULT 'scheduled',
    arena_city      TEXT,
    home_rest_days  INTEGER, away_rest_days INTEGER,
    home_back_to_back INTEGER DEFAULT 0, away_back_to_back INTEGER DEFAULT 0,
    home_travel_miles REAL, away_travel_miles REAL,
    model_home_win_prob REAL, model_spread REAL, model_total REAL,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tracking_frames (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id             TEXT,
    clip_id             TEXT,
    frame_number        INTEGER,
    timestamp_sec       REAL,
    player_id           INTEGER,
    tracker_player_id   INTEGER,
    team_id             INTEGER,
    x_pos               REAL,
    y_pos               REAL,
    speed               REAL,
    acceleration        REAL,
    ball_possession     INTEGER DEFAULT 0,
    event               TEXT,
    confidence          REAL,
    team_spacing        REAL,
    paint_count_own     INTEGER,
    paint_count_opp     INTEGER,
    tracker_version     TEXT,
    created_at          TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_frames_game   ON tracking_frames(game_id);
CREATE INDEX IF NOT EXISTS idx_frames_clip   ON tracking_frames(clip_id);
CREATE INDEX IF NOT EXISTS idx_frames_player ON tracking_frames(player_id);

CREATE TABLE IF NOT EXISTS possessions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id             TEXT,
    possession_id       INTEGER,
    clip_id             TEXT,
    team_id             INTEGER,
    start_frame         INTEGER,
    end_frame           INTEGER,
    duration_sec        REAL,
    avg_spacing         REAL,
    defensive_pressure  REAL,
    drive_attempts      INTEGER DEFAULT 0,
    shot_attempted      INTEGER DEFAULT 0,
    fast_break          INTEGER DEFAULT 0,
    result              TEXT,
    outcome_score       INTEGER DEFAULT 0,
    vtb                 REAL,
    created_at          TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_possessions_game ON possessions(game_id);

CREATE TABLE IF NOT EXISTS shots (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id             TEXT,
    possession_id       INTEGER,
    player_id           INTEGER,
    tracker_player_id   INTEGER,
    team_id             INTEGER,
    shot_x              REAL,
    shot_y              REAL,
    court_zone          TEXT,
    defender_distance   REAL,
    team_spacing        REAL,
    shot_quality        REAL,
    made                INTEGER,
    shot_type           TEXT,
    period              INTEGER,
    game_clock_sec      REAL,
    created_at          TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_shots_game   ON shots(game_id);
CREATE INDEX IF NOT EXISTS idx_shots_player ON shots(player_id);

CREATE TABLE IF NOT EXISTS player_identity_map (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id         TEXT,
    clip_id         TEXT,
    tracker_slot    INTEGER,
    jersey_number   INTEGER,
    player_id       INTEGER,
    confirmed_frame INTEGER,
    confidence      REAL,
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE (game_id, clip_id, tracker_slot)
);
CREATE INDEX IF NOT EXISTS idx_identity_game ON player_identity_map(game_id);

CREATE TABLE IF NOT EXISTS predictions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id         TEXT,
    model_name      TEXT NOT NULL,
    model_version   TEXT,
    prediction_type TEXT NOT NULL,
    player_id       INTEGER,
    prop_market     TEXT,
    value           REAL NOT NULL,
    confidence_lo   REAL,
    confidence_hi   REAL,
    edge            REAL,
    star_rating     INTEGER,
    predicted_at    TEXT DEFAULT (datetime('now')),
    resolved_at     TEXT,
    actual_value    REAL,
    correct         INTEGER
);
CREATE INDEX IF NOT EXISTS idx_predictions_game   ON predictions(game_id);
CREATE INDEX IF NOT EXISTS idx_predictions_player ON predictions(player_id);

CREATE TABLE IF NOT EXISTS model_versions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name      TEXT NOT NULL,
    version         TEXT NOT NULL,
    trained_at      TEXT DEFAULT (datetime('now')),
    metrics         TEXT,
    is_active       INTEGER DEFAULT 1,
    UNIQUE (model_name, version)
);

CREATE TABLE IF NOT EXISTS outcomes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id         TEXT,
    player_id       INTEGER,
    prop_market     TEXT,
    actual_value    REAL,
    recorded_at     TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS clv_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id         TEXT,
    bet_type        TEXT,
    open_line       REAL,
    close_line      REAL,
    clv             REAL,
    recorded_at     TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    filename    TEXT UNIQUE NOT NULL,
    applied_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scoreboard_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id     TEXT,
    frame       INTEGER,
    game_clock  TEXT,
    shot_clock  REAL,
    home_score  INTEGER,
    away_score  INTEGER,
    period      INTEGER,
    confidence  REAL,
    created_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_scoreboard_game ON scoreboard_log(game_id);

CREATE TABLE IF NOT EXISTS cv_features (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id         TEXT NOT NULL,
    player_id       INTEGER NOT NULL,
    feature_name    TEXT NOT NULL,
    feature_value   REAL,
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE (game_id, player_id, feature_name)
);
CREATE INDEX IF NOT EXISTS idx_cv_features_game   ON cv_features(game_id);
CREATE INDEX IF NOT EXISTS idx_cv_features_player ON cv_features(player_id);
"""


def run_sqlite_migrations(verbose: bool = True) -> bool:
    """Create SQLite schema at data/nba_ai.db. Safe to run multiple times."""
    from src.data.db import get_connection, _SQLITE_PATH
    try:
        conn = get_connection()
        with conn:
            with conn.cursor() as cur:
                for stmt in _SQLITE_SCHEMA.split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        try:
                            cur.execute(stmt)
                        except Exception as e:
                            print(f"[migrations] SQLite stmt error (may be harmless): {e}")
        if verbose:
            print(f"[migrations] SQLite schema ready at {_SQLITE_PATH}")
        conn.close()
        return True
    except Exception as e:
        print(f"[migrations] SQLite error: {e}")
        return False


def check_schema(db_url: str | None = None) -> dict:
    """
    Check which tables exist in the database.

    Returns:
        {"tables": [str], "missing": [str], "ok": bool}
    """
    expected = [
        "teams", "players", "games", "tracking_frames", "possessions",
        "shots", "lineups", "odds", "predictions", "player_season_stats",
        "team_season_stats", "player_identity_map",
        "model_versions", "features", "outcomes", "clv_log",
    ]

    try:
        from src.data.db import get_connection
        with get_connection(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT tablename FROM pg_tables
                    WHERE schemaname = 'public'
                    ORDER BY tablename
                """)
                existing = {row[0] for row in cur.fetchall()}
    except Exception as e:
        return {"error": str(e), "ok": False}

    missing = [t for t in expected if t not in existing]
    return {
        "tables":  sorted(existing),
        "expected": expected,
        "missing":  missing,
        "ok":       len(missing) == 0,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Apply NBA AI database migrations")
    parser.add_argument("--check", action="store_true", help="Check schema without applying")
    parser.add_argument("--url",   help="PostgreSQL URL (overrides DATABASE_URL env var)")
    args = parser.parse_args()

    if args.check:
        result = check_schema(args.url)
        if "error" in result:
            print(f"[migrations] Cannot connect: {result['error']}")
        else:
            print(f"[migrations] Tables found: {len(result['tables'])}")
            for t in result["tables"]:
                print(f"  [OK] {t}")
            if result["missing"]:
                print(f"\n[migrations] Missing tables:")
                for t in result["missing"]:
                    print(f"  [MISSING] {t}")
            else:
                print("\n[migrations] All expected tables present.")
    else:
        run_migrations(args.url)
