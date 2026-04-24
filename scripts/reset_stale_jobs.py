#!/usr/bin/env python
"""Reset stale processing→verified for jobs stuck >N hours."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from src.ingest.db import connect, migrate
from src.ingest.processing_worker import reset_stale_locks, STALE_HOURS

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reset stale processing locks")
    parser.add_argument("--hours", type=float, default=STALE_HOURS,
                        help=f"Hours before a job is considered stale (default: {STALE_HOURS})")
    args = parser.parse_args()

    conn = connect()
    migrate(conn)
    n = reset_stale_locks(conn, stale_hours=args.hours)
    conn.close()
    print(f"Reset {n} stale locks (threshold: {args.hours}h).")
