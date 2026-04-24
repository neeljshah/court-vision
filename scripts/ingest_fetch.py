#!/usr/bin/env python
"""CLI wrapper: fetch N games for a season from the manifest queue."""
from __future__ import annotations

import argparse
import logging
from logging.handlers import RotatingFileHandler
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from src.ingest.db import connect, migrate
from src.ingest.fetcher import fetch
from src.ingest.manifest import list_games

LOG_DIR = ROOT / "data" / "ingest" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(LOG_DIR / "p2_fetch.log", maxBytes=50 * 1024 * 1024, backupCount=3),
    ],
)
logger = logging.getLogger("ingest_fetch")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch queued games")
    parser.add_argument("--count", type=int, default=1, help="Max games to fetch")
    parser.add_argument("--season", type=str, default="2024", help="NBA season (unused placeholder)")
    parser.add_argument("--dry-run", action="store_true", help="Print jobs without downloading")
    parser.add_argument("--game-id", help="Fetch a specific game_id")
    parser.add_argument("--url", help="Override source URL for --game-id")
    args = parser.parse_args()

    conn = connect()
    migrate(conn)

    if args.game_id:
        games_to_fetch = [{"game_id": args.game_id, "source_url": args.url}]
    else:
        rows = conn.execute(
            "SELECT game_id, source_url FROM games WHERE status='queued' ORDER BY created_at LIMIT ?",
            (args.count,),
        ).fetchall()
        games_to_fetch = [dict(r) for r in rows]

    conn.close()

    if not games_to_fetch:
        logger.info("No queued games found.")
        return

    for g in games_to_fetch:
        game_id = g["game_id"]
        url = g.get("source_url")
        if args.dry_run:
            logger.info("DRY-RUN: would fetch %s url=%s", game_id, url)
            continue
        logger.info("Fetching %s ...", game_id)
        ok = fetch(game_id, url=url)
        logger.info("%s → %s", game_id, "verified" if ok else "FAILED")


if __name__ == "__main__":
    main()
