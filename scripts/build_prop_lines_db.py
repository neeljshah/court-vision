"""build_prop_lines_db.py — Initialise nba_data.db and backfill prop_outcomes.

Creates the SQLite database that run_gate1.py queries and backfills the
prop_outcomes table from local boxscore JSON files (4500+ games).

The prop_lines table stays empty until real sportsbook lines are collected
via fetch_live_prop_lines.py during the season.  Gate 1 (CLV vs Pinnacle)
will run automatically once prop_lines has >= 50 rows for a given stat.

Usage:
    python scripts/build_prop_lines_db.py
    python scripts/build_prop_lines_db.py --db data/nba/nba_data.db
    python scripts/build_prop_lines_db.py --check   # just show counts
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sqlite3
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

DEFAULT_DB = PROJECT_DIR / "data" / "nba" / "nba_data.db"
BOXSCORE_GLOB = str(PROJECT_DIR / "data" / "nba" / "boxscore_*.json")

STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS prop_lines (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id       TEXT    NOT NULL,
    player_id     INTEGER NOT NULL,
    player_name   TEXT    NOT NULL,
    market        TEXT    NOT NULL,
    sport         TEXT    NOT NULL DEFAULT 'basketball_nba',
    bookmaker     TEXT    NOT NULL,
    line          REAL    NOT NULL,
    over_odds     INTEGER,
    under_odds    INTEGER,
    is_closing    INTEGER NOT NULL DEFAULT 0,
    captured_at   TEXT,
    UNIQUE(game_id, player_id, market, bookmaker, is_closing)
);

CREATE TABLE IF NOT EXISTS prop_outcomes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id       TEXT    NOT NULL,
    player_id     INTEGER NOT NULL,
    player_name   TEXT    NOT NULL,
    market        TEXT    NOT NULL,
    sport         TEXT    NOT NULL DEFAULT 'basketball_nba',
    actual_value  REAL    NOT NULL,
    result        TEXT,
    UNIQUE(game_id, player_id, market)
);

CREATE INDEX IF NOT EXISTS idx_prop_lines_closing
    ON prop_lines(bookmaker, is_closing, sport);
CREATE INDEX IF NOT EXISTS idx_prop_outcomes_game
    ON prop_outcomes(game_id, player_id);
"""

STAT_TO_MARKET = {
    "pts":  "player_points",
    "reb":  "player_rebounds",
    "ast":  "player_assists",
    "fg3m": "player_threes",
    "stl":  "player_steals",
    "blk":  "player_blocks",
    "tov":  "player_turnovers",
}


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def backfill_outcomes(conn: sqlite3.Connection) -> int:
    """Load all boxscore_*.json and insert player stats as prop_outcomes rows."""
    files = sorted(glob.glob(BOXSCORE_GLOB))
    inserted = 0
    skipped = 0

    for path in files:
        try:
            data = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue

        game_id = str(data.get("game_id", ""))
        if not game_id:
            continue

        players = data.get("players", [])
        rows = []
        for p in players:
            pid = p.get("player_id")
            pname = p.get("player_name", "")
            if not pid or not pname:
                continue
            for stat, market in STAT_TO_MARKET.items():
                val = p.get(stat)
                if val is None:
                    continue
                actual = float(val)
                rows.append((game_id, int(pid), pname, market, actual))

        if rows:
            conn.executemany(
                """INSERT OR IGNORE INTO prop_outcomes
                   (game_id, player_id, player_name, market, actual_value)
                   VALUES (?, ?, ?, ?, ?)""",
                rows,
            )
            inserted += conn.execute("SELECT changes()").fetchone()[0]

    conn.commit()
    return inserted


def show_counts(conn: sqlite3.Connection) -> None:
    lines = conn.execute("SELECT COUNT(*) FROM prop_lines").fetchone()[0]
    outcomes = conn.execute("SELECT COUNT(*) FROM prop_outcomes").fetchone()[0]
    closing = conn.execute(
        "SELECT COUNT(*) FROM prop_lines WHERE is_closing=1"
    ).fetchone()[0]
    print(f"  prop_lines:    {lines:>8,}  (closing: {closing:,})")
    print(f"  prop_outcomes: {outcomes:>8,}")
    if lines > 0:
        joinable = conn.execute("""
            SELECT COUNT(*) FROM prop_lines pl
            JOIN prop_outcomes po
              ON pl.game_id=po.game_id AND pl.player_id=po.player_id
             AND pl.market=po.market
            WHERE pl.is_closing=1
        """).fetchone()[0]
        print(f"  joinable (lines+outcomes): {joinable:,}")
        print()
        print("  Gate 1 is READY to run once you have >= 50 closing lines.")
    else:
        print()
        print("  No closing lines yet. Run fetch_live_prop_lines.py during the season.")
        print("  Then mark closing rows: UPDATE prop_lines SET is_closing=1")
        print("  WHERE captured_at = (SELECT MAX(captured_at) FROM prop_lines WHERE ...)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Build/backfill nba_data.db")
    ap.add_argument("--db", default=str(DEFAULT_DB), help="SQLite path")
    ap.add_argument("--check", action="store_true", help="Show counts only")
    args = ap.parse_args()

    db_path = Path(args.db)
    conn = init_db(db_path)
    print(f"DB: {db_path}")

    if args.check:
        show_counts(conn)
        return

    print("Backfilling prop_outcomes from boxscore files...")
    n = backfill_outcomes(conn)
    print(f"  Inserted {n:,} new outcome rows")
    print()
    show_counts(conn)
    conn.close()


if __name__ == "__main__":
    main()
