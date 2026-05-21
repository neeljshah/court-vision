"""
compute_prop_outcomes.py — CLI to populate prop_outcomes from prop_lines × box_scores.

Scans prop_lines rows that have no matching prop_outcomes entry, joins to box_scores
on (sport, game_id, player_id), calls compute_outcome(), and upserts into prop_outcomes.
Idempotent — uses ON CONFLICT DO NOTHING.

Usage:
    python scripts/compute_prop_outcomes.py [--sport nba] [--batch-size 500] [--dry-run]
"""
from __future__ import annotations

import argparse
import logging
import sys
from typing import Optional

# Allow running from repo root: src/ must be on the path.
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.data.db import get_connection, execute_batch
from src.data.derive.prop_outcomes import compute_outcome

log = logging.getLogger(__name__)

# ── SQL ───────────────────────────────────────────────────────────────────────

# Prop lines that have no outcome row yet (left-join anti-pattern)
_UNRESOLVED_SQL = """
SELECT pl.id, pl.sport, pl.game_id, pl.player_id, pl.market, pl.line
FROM   prop_lines pl
LEFT JOIN prop_outcomes po
       ON po.sport     = pl.sport
      AND po.game_id   = pl.game_id
      AND po.player_id = pl.player_id
      AND po.market    = pl.market
WHERE  po.sport IS NULL
  AND  (%(sport)s IS NULL OR pl.sport = %(sport)s)
ORDER BY pl.recorded_at
"""

# Fetch box score for a single (sport, game_id, player_id)
_BOX_SQL = """
SELECT minutes, points, rebounds, assists, steals, blocks,
       fg_made, fg3_made, ft_made
FROM   box_scores
WHERE  sport     = %(sport)s
  AND  game_id   = %(game_id)s
  AND  player_id = %(player_id)s
LIMIT  1
"""

# Insert outcome row — idempotent
_INSERT_SQL = """
INSERT INTO prop_outcomes
    (sport, game_id, player_id, market, actual_value, closing_line, result)
VALUES
    (%(sport)s, %(game_id)s, %(player_id)s, %(market)s,
     %(actual_value)s, %(closing_line)s, %(result)s)
ON CONFLICT DO NOTHING
"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def _fetch_box(cur, sport: str, game_id: str, player_id: str) -> Optional[dict]:
    """Return box_scores dict for one player-game, or None."""
    cur.execute(_BOX_SQL, {"sport": sport, "game_id": game_id, "player_id": player_id})
    row = cur.fetchone()
    if row is None:
        return None
    # sqlite3.Row / psycopg2 Row → plain dict by index
    cols = ["minutes", "points", "rebounds", "assists", "steals", "blocks",
            "fg_made", "fg3_made", "ft_made"]
    return dict(zip(cols, row))


def _box_cache_key(sport: str, game_id: str, player_id: str) -> tuple:
    return (sport, game_id, player_id)


# ── Core runner ───────────────────────────────────────────────────────────────

def compute_all(sport: Optional[str] = None, batch_size: int = 500, dry_run: bool = False) -> dict:
    """
    Resolve all outstanding prop_lines → prop_outcomes.

    Args:
        sport:      Limit to one sport (e.g. 'nba'). None = all sports.
        batch_size: Number of outcome rows to insert per DB round-trip.
        dry_run:    If True, derive outcomes but do not write to the DB.

    Returns:
        Summary dict: total_lines, resolved, voided, skipped, inserted.
    """
    conn = get_connection()
    stats = {"total_lines": 0, "resolved": 0, "voided": 0, "skipped": 0, "inserted": 0}

    # cache: avoid fetching same (sport, game_id, player_id) multiple times per run
    box_cache: dict[tuple, Optional[dict]] = {}

    try:
        cur = conn.cursor()
        cur.execute(_UNRESOLVED_SQL, {"sport": sport})
        rows = cur.fetchall()
        stats["total_lines"] = len(rows)
        log.info("found %d unresolved prop_lines rows", len(rows))

        batch: list[dict] = []

        for row in rows:
            pl_id, pl_sport, game_id, player_id, market, line = row[:6]

            # Fetch (and cache) box score
            ck = _box_cache_key(pl_sport, game_id, player_id)
            if ck not in box_cache:
                box_cache[ck] = _fetch_box(cur, pl_sport, game_id, player_id)
            box = box_cache[ck]

            # Skip unknown markets gracefully
            try:
                actual, result = compute_outcome(
                    {"market": market, "line": line}, box
                )
            except ValueError as exc:
                log.warning("skipping prop_line %s: %s", pl_id, exc)
                stats["skipped"] += 1
                continue

            if result == "void":
                stats["voided"] += 1
            else:
                stats["resolved"] += 1

            batch.append({
                "sport": pl_sport,
                "game_id": game_id,
                "player_id": player_id,
                "market": market,
                "actual_value": actual if actual is not None else 0.0,
                "closing_line": line,
                "result": result,
            })

            if len(batch) >= batch_size and not dry_run:
                execute_batch(cur, _INSERT_SQL, batch)
                conn.commit()
                stats["inserted"] += len(batch)
                log.info("inserted %d outcome rows (running total %d)", len(batch), stats["inserted"])
                batch = []

        # flush remainder
        if batch and not dry_run:
            execute_batch(cur, _INSERT_SQL, batch)
            conn.commit()
            stats["inserted"] += len(batch)
        elif dry_run:
            stats["inserted"] = len(batch) + stats["inserted"]  # count what *would* insert
            log.info("dry-run: would insert %d rows", stats["inserted"])

    finally:
        conn.close()

    log.info(
        "done — total=%d resolved=%d voided=%d skipped=%d inserted=%d",
        stats["total_lines"], stats["resolved"], stats["voided"],
        stats["skipped"], stats["inserted"],
    )
    return stats


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Populate prop_outcomes by joining prop_lines × box_scores."
    )
    p.add_argument("--sport", default=None, help="Limit to one sport (default: all)")
    p.add_argument("--batch-size", type=int, default=500, help="Insert batch size (default: 500)")
    p.add_argument("--dry-run", action="store_true", help="Derive outcomes but do not write")
    p.add_argument("--verbose", "-v", action="store_true", help="DEBUG-level logging")
    return p


def main() -> None:
    args = _build_parser().parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    result = compute_all(
        sport=args.sport,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
    )
    print(result)


if __name__ == "__main__":
    main()
