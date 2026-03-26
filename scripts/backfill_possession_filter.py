"""
backfill_possession_filter.py — Remove <2s noise possessions from existing CSVs.

Reads each data/tracking/{game_id}/possessions.csv, removes rows where
duration_sec < 2.0 (sub-2-second noise from ball-detection flickers), and
writes back in-place.

Usage:
    conda activate basketball_ai
    python scripts/backfill_possession_filter.py
"""

import csv
import os
import sys
from pathlib import Path

PROJECT_DIR  = Path(__file__).resolve().parent.parent
TRACKING_DIR = PROJECT_DIR / "data" / "tracking"

MIN_DURATION_SEC = 2.0


def filter_game(game_dir: Path) -> tuple:
    """Filter possessions.csv for one game. Returns (before, after, dropped)."""
    poss_path = game_dir / "possessions.csv"
    if not poss_path.exists():
        return 0, 0, 0

    with open(poss_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    before = len(rows)
    kept   = [r for r in rows if _keep(r)]
    after  = len(kept)
    dropped = before - after

    if dropped > 0:
        with open(poss_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            w.writerows(kept)

    return before, after, dropped


def _keep(row: dict) -> bool:
    val = row.get("duration_sec", "")
    if val is None or val == "":
        return True  # keep rows with missing duration (safe default)
    try:
        return float(val) >= MIN_DURATION_SEC
    except (ValueError, TypeError):
        return True  # keep rows with unparseable duration


def main():
    if not TRACKING_DIR.exists():
        print(f"Tracking directory not found: {TRACKING_DIR}")
        sys.exit(1)

    game_dirs = sorted(p for p in TRACKING_DIR.iterdir() if p.is_dir())
    if not game_dirs:
        print("No game directories found.")
        return

    total_before = total_after = total_dropped = 0
    for game_dir in game_dirs:
        before, after, dropped = filter_game(game_dir)
        if before == 0:
            continue
        total_before  += before
        total_after   += after
        total_dropped += dropped
        print(f"  {game_dir.name}: {before} → {after} rows  ({dropped} dropped)")

    print(f"\nTotal: {total_before} → {total_after} rows  ({total_dropped} dropped)")
    print("Done. Re-run nba_enricher --backfill to re-enrich the filtered possessions.")


if __name__ == "__main__":
    main()
