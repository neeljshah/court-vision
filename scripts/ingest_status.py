#!/usr/bin/env python
"""One-screen ingest status: counts, source health, storage, throughput, ETA."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from src.ingest.db import connect, migrate


def _gb(path: Path) -> float:
    total = 0
    if path.exists():
        for f in path.rglob("*"):
            try:
                total += f.stat().st_size
            except OSError:
                pass
    return total / (1024 ** 3)


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main() -> None:
    conn = connect()
    migrate(conn)

    # ── counts by status ──────────────────────────────────────────────────────
    status_rows = conn.execute(
        "SELECT status, COUNT(*) n FROM games GROUP BY status ORDER BY status"
    ).fetchall()
    tier_rows = conn.execute(
        "SELECT quality_tier, COUNT(*) n FROM games "
        "WHERE quality_tier IS NOT NULL GROUP BY quality_tier ORDER BY quality_tier"
    ).fetchall()
    total = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]

    # ── source success rates (last 50 attempts) ────────────────────────────────
    source_rows = conn.execute(
        """SELECT source, COUNT(*) total,
               SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) success
           FROM downloads GROUP BY source"""
    ).fetchall()

    # ── throughput last 24h ────────────────────────────────────────────────────
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    recent = conn.execute(
        "SELECT COUNT(*) FROM games WHERE status='processed' AND updated_at > ?",
        (cutoff,),
    ).fetchone()[0]

    # ── last 5 errors ──────────────────────────────────────────────────────────
    errors = conn.execute(
        "SELECT game_id, stage, payload_json, ts FROM events "
        "WHERE level='error' ORDER BY ts DESC LIMIT 5"
    ).fetchall()

    # ── storage ───────────────────────────────────────────────────────────────
    videos_gb   = _gb(ROOT / "data" / "videos")
    tracking_gb = _gb(ROOT / "data" / "tracking")
    events_gb   = _gb(ROOT / "data" / "events")

    # ── CLEAN count + ETA ─────────────────────────────────────────────────────
    clean_count = next((r["n"] for r in tier_rows if r["quality_tier"] == "CLEAN"), 0)
    target = 80
    remaining = max(0, target - clean_count)
    rate_per_hr = recent / 24.0 if recent > 0 else None
    eta_str = "unknown"
    if rate_per_hr and rate_per_hr > 0:
        eta_hrs = remaining / rate_per_hr
        eta_str = f"~{eta_hrs:.1f}h at {rate_per_hr:.1f} games/hr"

    conn.close()

    # ── print ─────────────────────────────────────────────────────────────────
    print(f"\n{'='*55}")
    print(f"  CourtVision Ingest Status  [{_now_utc()}]")
    print(f"{'='*55}")

    print("\nGames by status:")
    for r in status_rows:
        print(f"  {r['status']:16s}  {r['n']:5d}")
    print(f"  {'TOTAL':16s}  {total:5d}")

    print("\nGames by quality tier:")
    for r in tier_rows:
        print(f"  {r['quality_tier'] or '(none)':16s}  {r['n']:5d}")

    print("\nSource success rates (all-time):")
    if source_rows:
        for r in source_rows:
            pct = 100.0 * r["success"] / r["total"] if r["total"] else 0
            print(f"  {r['source']:16s}  {r['success']:3d}/{r['total']:3d}  ({pct:.0f}%)")
    else:
        print("  (no download attempts yet)")

    print("\nStorage:")
    print(f"  videos:    {videos_gb:.2f} GB")
    print(f"  tracking:  {tracking_gb:.2f} GB")
    print(f"  events:    {events_gb:.2f} GB")

    print(f"\nThroughput (last 24h): {recent} games processed")
    print(f"ETA to {target} CLEAN games: {eta_str}  (currently {clean_count}/{target})")

    print("\nLast 5 errors:")
    if errors:
        for e in errors:
            print(f"  [{e['ts'][:19]}] {e['game_id']:15s}  {e['stage']:10s}  {e['payload_json'][:60]}")
    else:
        print("  (none)")

    print()


if __name__ == "__main__":
    main()
