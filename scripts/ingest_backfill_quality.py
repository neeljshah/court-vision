#!/usr/bin/env python
"""Re-score all processed games with quality gate. Idempotent."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from src.ingest.db import connect, migrate
from src.ingest.manifest import update_game
from src.ingest.quality import score

LOG_DIR = ROOT / "data" / "ingest" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "p4_backfill.log"),
    ],
)
logger = logging.getLogger("ingest_backfill_quality")


def main() -> None:
    conn = connect()
    migrate(conn)

    rows = conn.execute(
        "SELECT game_id FROM games WHERE status IN ('processed','legacy_import')"
        " OR (status='processed')"
    ).fetchall()

    # Also score any game that has tracking output but no tier
    unscored = conn.execute(
        "SELECT game_id FROM games WHERE status='processed'"
    ).fetchall()

    game_ids = [r["game_id"] for r in unscored]
    logger.info("Scoring %d processed games", len(game_ids))

    counts: dict = {"CLEAN": 0, "PARTIAL": 0, "REJECT": 0, "skip": 0}
    for gid in game_ids:
        tier, reason, metrics = score(gid)
        update_game(conn, gid, quality_tier=tier, reject_reason=reason)
        counts[tier] += 1
        logger.info("%s -> %s | ball=%.1f%% homo=%.1f%% cont=%.3f events=%d",
                    gid, tier,
                    metrics.get("ball_valid_pct", 0),
                    metrics.get("homography_valid_pct", 0),
                    metrics.get("player_track_continuity", 0),
                    metrics.get("event_count", 0))

    conn.close()
    logger.info("Done: %s", counts)


if __name__ == "__main__":
    main()
