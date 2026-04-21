#!/usr/bin/env python
"""CLI: claim + process verified games from the manifest queue."""
from __future__ import annotations

import argparse
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from src.ingest.db import connect, migrate
from src.ingest.processing_worker import claim_job, process_game, reset_stale_locks

LOG_DIR = ROOT / "data" / "ingest" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(LOG_DIR / "p3_process.log", maxBytes=50 * 1024 * 1024, backupCount=3),
    ],
)
logger = logging.getLogger("ingest_process")


def main() -> None:
    parser = argparse.ArgumentParser(description="Process verified games through pipeline")
    parser.add_argument("--max-games", type=int, default=1, help="Max games to process")
    parser.add_argument("--parallel", type=int, default=1, help="Worker threads")
    parser.add_argument("--dry-run", action="store_true", help="Print jobs without processing")
    parser.add_argument("--reset-stale", action="store_true",
                        help="Reset stale processing locks before starting")
    args = parser.parse_args()

    conn = connect()
    migrate(conn)

    if args.reset_stale:
        n = reset_stale_locks(conn)
        logger.info("Reset %d stale locks", n)

    verified = conn.execute(
        "SELECT COUNT(*) FROM games WHERE status='verified'"
    ).fetchone()[0]
    logger.info("%d verified games available", verified)
    conn.close()

    if args.dry_run:
        conn2 = connect()
        rows = conn2.execute(
            "SELECT game_id FROM games WHERE status='verified' LIMIT ?",
            (args.max_games,)
        ).fetchall()
        for r in rows:
            logger.info("DRY-RUN: would process %s", r["game_id"])
        conn2.close()
        return

    games_done = 0

    def _worker(idx: int) -> bool:
        nonlocal games_done
        os.environ["INGEST_WORKER_IDX"] = str(idx)
        wconn = connect()
        game_id = claim_job(wconn)
        wconn.close()
        if game_id is None:
            return False
        logger.info("Worker[%d] pid=%d processing %s", idx, os.getpid(), game_id)
        ok = process_game(game_id)
        logger.info("Worker[%d] %s → %s", idx, game_id, "done" if ok else "FAILED")
        return ok

    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        futures = {pool.submit(_worker, i): i for i in range(args.max_games)}
        for f in as_completed(futures):
            worker_idx = futures[f]
            try:
                f.result()
                games_done += 1
            except Exception as e:
                logger.error("Worker[%d] unhandled exception: %s", worker_idx, e)

    logger.info("Done: %d jobs submitted", games_done)


if __name__ == "__main__":
    main()
