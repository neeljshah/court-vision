#!/usr/bin/env python
"""Reset stale processing→verified for jobs stuck >2h."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from src.ingest.db import connect, migrate
from src.ingest.processing_worker import reset_stale_locks

if __name__ == "__main__":
    conn = connect()
    migrate(conn)
    n = reset_stale_locks(conn)
    conn.close()
    print(f"Reset {n} stale locks.")
