"""ingest_closing_lines.py — Import a day's final line snapshot into nba_data.db.

Run at the END of each game day after the last lines are captured.
Marks those rows as is_closing=1 in prop_lines so run_gate1.py can query them.

Usage:
    # Mark today's last DK snapshot as closing lines:
    python scripts/ingest_closing_lines.py --date 2026-10-22 --book dk

    # Or pass a specific CSV file:
    python scripts/ingest_closing_lines.py --file data/lines/snapshots/2026-10-22_2300.csv

Schema of input CSV (from fetch_live_prop_lines.py):
    player, stat, line, over_odds, under_odds
    -- or --
    captured_at, book, game_id, player_id, player_name, team, stat, line, over_odds, under_odds, market_status
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import sqlite3
import sys
from datetime import date as _date
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

DEFAULT_DB = PROJECT_DIR / "data" / "nba" / "nba_data.db"
SNAPSHOTS_DIR = PROJECT_DIR / "data" / "lines" / "snapshots"

STAT_TO_MARKET = {
    "pts":  "player_points",
    "reb":  "player_rebounds",
    "ast":  "player_assists",
    "fg3m": "player_threes",
    "stl":  "player_steals",
    "blk":  "player_blocks",
    "tov":  "player_turnovers",
}


def _find_latest_snapshot(date_str: str, book: str = "dk") -> str | None:
    pattern = str(SNAPSHOTS_DIR / f"{date_str}_*.csv")
    files = sorted(glob.glob(pattern))
    if not files:
        return None
    return files[-1]  # lexically latest = latest time


def ingest_csv(conn: sqlite3.Connection, csv_path: str, book: str,
               date_str: str) -> tuple[int, int]:
    inserted = 0
    skipped = 0

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    for row in rows:
        player_name = (row.get("player_name") or row.get("player", "")).strip()
        stat = (row.get("stat") or "").strip()
        market = STAT_TO_MARKET.get(stat)
        if not player_name or not market:
            skipped += 1
            continue

        try:
            line = float(row.get("line") or 0)
            over_odds = int(float(row.get("over_odds") or -110))
            under_odds = int(float(row.get("under_odds") or -110))
        except (ValueError, TypeError):
            skipped += 1
            continue

        game_id = str(row.get("game_id") or "")
        try:
            player_id = int(row.get("player_id") or 0)
        except (ValueError, TypeError):
            player_id = 0

        captured_at = row.get("captured_at") or date_str
        bookmaker = book

        conn.execute(
            """INSERT OR REPLACE INTO prop_lines
               (game_id, player_id, player_name, market, bookmaker, line,
                over_odds, under_odds, is_closing, captured_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
            (game_id, player_id, player_name, market, bookmaker, line,
             over_odds, under_odds, captured_at),
        )
        inserted += 1

    conn.commit()
    return inserted, skipped


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest closing prop lines into nba_data.db")
    ap.add_argument("--date", default=_date.today().isoformat(),
                    help="Game date YYYY-MM-DD (default: today)")
    ap.add_argument("--book", default="dk", help="Bookmaker tag (dk, fd, pinnacle)")
    ap.add_argument("--file", default=None, help="Explicit CSV path (overrides --date)")
    ap.add_argument("--db", default=str(DEFAULT_DB), help="SQLite path")
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"[warn] DB not found at {db_path}. Run build_prop_lines_db.py first.")
        sys.exit(1)

    csv_path = args.file or _find_latest_snapshot(args.date, args.book)
    if not csv_path or not os.path.exists(str(csv_path)):
        print(f"[warn] No snapshot found for {args.date} ({args.book}). "
              f"Run fetch_live_prop_lines.py during the game day first.")
        sys.exit(0)

    conn = sqlite3.connect(str(db_path))
    inserted, skipped = ingest_csv(conn, str(csv_path), args.book, args.date)
    conn.close()

    total_closing = sqlite3.connect(str(db_path)).execute(
        "SELECT COUNT(*) FROM prop_lines WHERE is_closing=1"
    ).fetchone()[0]

    print(f"Ingested {inserted} closing lines from {csv_path}")
    print(f"  Skipped: {skipped}  |  Total closing lines in DB: {total_closing:,}")
    if total_closing >= 50:
        print()
        print("  Gate 1 ready: python scripts/run_gate1.py")


if __name__ == "__main__":
    main()
