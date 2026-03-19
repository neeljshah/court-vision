"""Seed runner for historical NBA game and player records.

Run once after the database schema is initialized to populate the games and players
dimension tables with representative NBA records from 2022-23 and 2023-24 seasons.

Usage:
    python -m tracking.seed_historical

NOTE: tracking_coordinates must be populated by running the video pipeline on actual
game footage. This script only seeds the reference dimension tables (games, players).
"""

import pathlib
import sys

from legacy.tracking.database import get_connection

_SEEDS_DIR = pathlib.Path(__file__).parent.parent / "data" / "seeds"
_SEED_GAMES_SQL = _SEEDS_DIR / "seed_games.sql"
_SEED_PLAYERS_SQL = _SEEDS_DIR / "seed_players.sql"


def seed_historical() -> None:
    """Seed the games and players tables with historical NBA records.

    Reads seed_games.sql and seed_players.sql and executes them against the
    database specified by DATABASE_URL. Safe to run multiple times because every
    INSERT uses ON CONFLICT (id) DO NOTHING.

    Prints row counts for games and players after seeding.
    Prints a note reminding operators that tracking_coordinates requires real footage.
    """
    try:
        conn = get_connection()
    except EnvironmentError as exc:
        print(f"[seed_historical] Connection error: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        games_sql = _SEED_GAMES_SQL.read_text(encoding="utf-8")
        players_sql = _SEED_PLAYERS_SQL.read_text(encoding="utf-8")

        cur = conn.cursor()
        try:
            print("[seed_historical] Seeding games table…")
            cur.execute(games_sql)

            print("[seed_historical] Seeding players table…")
            cur.execute(players_sql)

            conn.commit()

            cur.execute("SELECT COUNT(*) FROM games;")
            games_count = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM players;")
            players_count = cur.fetchone()[0]

            print(f"[seed_historical] games rows:   {games_count}")
            print(f"[seed_historical] players rows: {players_count}")
            print(
                "\nNOTE: tracking_coordinates must be populated by running the "
                "video pipeline on actual game footage (plan 01-04). "
                "This script only seeds the games and players reference tables."
            )
        finally:
            cur.close()
    finally:
        conn.close()


if __name__ == "__main__":
    seed_historical()
