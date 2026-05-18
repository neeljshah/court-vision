"""CRUD + migration CLI for the ingest manifest database."""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.ingest.db import connect, migrate

PROCESSED_TXT = Path(__file__).parents[2] / "data" / "phase_g_processed.txt"
METRICS_CSV   = Path(__file__).parents[2] / "data" / "phase_g_metrics.csv"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── low-level helpers ──────────────────────────────────────────────────────────

def get_conn(db_path: Optional[Path] = None) -> sqlite3.Connection:
    conn = connect(db_path)
    migrate(conn)
    return conn


def add_game(conn: sqlite3.Connection, game_id: str, **kwargs: Any) -> None:
    now = _now()
    fields = {"game_id": game_id, "status": "queued", "attempts": 0,
               "created_at": now, "updated_at": now, **kwargs}
    cols = ", ".join(fields.keys())
    placeholders = ", ".join(["?"] * len(fields))
    conn.execute(
        f"INSERT OR REPLACE INTO games ({cols}) VALUES ({placeholders})",
        list(fields.values()),
    )
    conn.commit()


def get_game(conn: sqlite3.Connection, game_id: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM games WHERE game_id=?", (game_id,)).fetchone()


def update_game(conn: sqlite3.Connection, game_id: str, **kwargs: Any) -> None:
    kwargs["updated_at"] = _now()
    sets = ", ".join(f"{k}=?" for k in kwargs)
    conn.execute(f"UPDATE games SET {sets} WHERE game_id=?", [*kwargs.values(), game_id])
    conn.commit()


def log_event(conn: sqlite3.Connection, game_id: str, stage: str,
              level: str, payload: Any) -> None:
    conn.execute(
        "INSERT INTO events (game_id, stage, level, payload_json, ts) VALUES (?,?,?,?,?)",
        (game_id, stage, level, json.dumps(payload), _now()),
    )
    conn.commit()


def list_games(conn: sqlite3.Connection, status: Optional[str] = None) -> List[sqlite3.Row]:
    if status:
        return conn.execute("SELECT * FROM games WHERE status=? ORDER BY created_at", (status,)).fetchall()
    return conn.execute("SELECT * FROM games ORDER BY created_at").fetchall()


# ── migration ─────────────────────────────────────────────────────────────────

def migrate_legacy(conn: sqlite3.Connection) -> int:
    """Import phase_g_processed.txt + phase_g_metrics.csv -> games table. Idempotent."""
    inserted = 0
    now = _now()

    metrics: Dict[str, Dict] = {}
    if METRICS_CSV.exists():
        with METRICS_CSV.open(newline="") as fh:
            for row in csv.DictReader(fh):
                gid = row.get("game_id") or row.get("game_key", "")
                if gid:
                    metrics[gid] = row

    if PROCESSED_TXT.exists():
        for line in PROCESSED_TXT.read_text().splitlines():
            game_id = line.strip()
            if not game_id:
                continue
            existing = get_game(conn, game_id)
            if existing:
                continue
            m = metrics.get(game_id, {})
            tier = m.get("quality") or None
            dur  = float(m.get("duration_s") or 0) or None
            conn.execute(
                """INSERT OR IGNORE INTO games
                   (game_id, status, quality_tier, duration_s, source, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (game_id, "processed", tier, dur, "legacy_import", now, now),
            )
            inserted += 1

    conn.commit()
    return inserted


# ── status display ────────────────────────────────────────────────────────────

def print_status(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT status, COUNT(*) as n FROM games GROUP BY status ORDER BY status"
    ).fetchall()
    tier_rows = conn.execute(
        "SELECT quality_tier, COUNT(*) as n FROM games GROUP BY quality_tier ORDER BY quality_tier"
    ).fetchall()

    print("=== Ingest Manifest Status ===")
    print("\nBy status:")
    total = 0
    for r in rows:
        print(f"  {r['status']:15s} {r['n']:5d}")
        total += r["n"]
    print(f"  {'TOTAL':15s} {total:5d}")

    print("\nBy quality tier:")
    for r in tier_rows:
        tier = r["quality_tier"] or "(none)"
        print(f"  {tier:15s} {r['n']:5d}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest manifest CLI")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("migrate",    help="Migrate legacy txt/csv into DB")
    sub.add_parser("status",     help="Print counts by status + tier")
    sub.add_parser("reset-locks",help="Reset processing->verified for stale jobs")

    add_p = sub.add_parser("add", help="Add a game to the queue")
    add_p.add_argument("game_id")
    add_p.add_argument("--source", default="manual")

    get_p = sub.add_parser("get", help="Show a game record")
    get_p.add_argument("game_id")

    list_p = sub.add_parser("list", help="List games")
    list_p.add_argument("--status", default=None)

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        sys.exit(0)

    conn = get_conn()

    if args.cmd == "migrate":
        n = migrate_legacy(conn)
        print(f"Migrated {n} new games from legacy files.")
        print_status(conn)

    elif args.cmd == "status":
        print_status(conn)

    elif args.cmd == "reset-locks":
        conn.execute(
            "UPDATE games SET status='verified', updated_at=? WHERE status='processing'",
            (_now(),),
        )
        conn.commit()
        print(f"Reset {conn.execute('SELECT changes()').fetchone()[0]} stale locks.")

    elif args.cmd == "add":
        add_game(conn, args.game_id, source=args.source)
        print(f"Added {args.game_id}")

    elif args.cmd == "get":
        row = get_game(conn, args.game_id)
        if row:
            print(dict(row))
        else:
            print("Not found.", file=sys.stderr)
            sys.exit(1)

    elif args.cmd == "list":
        for r in list_games(conn, args.status):
            print(f"{r['game_id']:15s}  {r['status']:12s}  {r['quality_tier'] or '':8s}  {r['source'] or ''}")


if __name__ == "__main__":
    main()
