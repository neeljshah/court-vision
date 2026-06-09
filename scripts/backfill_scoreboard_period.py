"""P4 (2026-05-29): backfill scoreboard_period in tracking_data.csv for historical games.

The scoreboard OCR returns -1 / "" for period on most broadcasts, so
tracking_data.csv has `scoreboard_period` ~100% empty. Downstream signals
(INT-65 fatigue trajectories, INT-70 F1 Q1 extrapolation, INT-72 F3 Consumer A)
DEFER on this gap.

Frame-percentile fallback:
    quarter = max(1, min(4, int(frame / max_frame * 4) + 1))

Preserves any OCR-confirmed values; only fills empty cells.

Usage:
  python scripts/backfill_scoreboard_period.py
  python scripts/backfill_scoreboard_period.py --game-id 0022400909
  python scripts/backfill_scoreboard_period.py --dry-run
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path
from typing import Tuple

ROOT = Path(__file__).resolve().parent.parent

TRACKING_DIR = ROOT / "data" / "tracking"
GAMES_DIR = ROOT / "data" / "games"


def backfill_game(game_dir: str, dry_run: bool) -> Tuple[int, int, int]:
    """Return (filled, preserved, total). Negative values on read error."""
    path = os.path.join(game_dir, "tracking_data.csv")
    if not os.path.exists(path):
        return 0, 0, 0
    try:
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            fieldnames = list(reader.fieldnames or [])
            if "scoreboard_period" not in fieldnames or "frame" not in fieldnames:
                return 0, 0, 0
            rows = list(reader)
    except Exception:
        return -1, -1, -1

    if not rows:
        return 0, 0, 0

    max_frame = 1
    for row in rows:
        try:
            f_val = row.get("frame", "")
            if f_val and f_val not in ("nan", ""):
                f_int = int(float(f_val))
                if f_int > max_frame:
                    max_frame = f_int
        except (ValueError, TypeError):
            pass

    filled = 0
    preserved = 0
    for row in rows:
        cur = row.get("scoreboard_period", "")
        if cur not in ("", None, "nan"):
            preserved += 1
            continue
        try:
            f_int = int(float(row.get("frame", "") or 0))
            q = max(1, min(4, int(f_int / max_frame * 4) + 1))
            row["scoreboard_period"] = str(q)
            filled += 1
        except (ValueError, TypeError):
            pass

    if not dry_run and filled > 0:
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
        except Exception:
            return -1, -1, -1

    return filled, preserved, len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    targets = []
    if args.game_id:
        for base in (TRACKING_DIR, GAMES_DIR):
            d = base / args.game_id
            if d.is_dir():
                targets.append((args.game_id, str(d)))
    else:
        for base in (TRACKING_DIR, GAMES_DIR):
            if not base.is_dir():
                continue
            for d in sorted(base.iterdir()):
                if not d.is_dir() or d.name.startswith("_"):
                    continue
                targets.append((d.name, str(d)))

    if not targets:
        print("No tracking directories found.")
        return 1

    print(f"Backfilling scoreboard_period in {len(targets)} game dirs (dry_run={args.dry_run})")

    games_done = 0
    games_skipped = 0
    games_errored = 0
    total_filled = 0
    total_preserved = 0
    total_rows = 0

    for game_id, game_dir in targets:
        if args.limit and games_done >= args.limit:
            break
        filled, preserved, total = backfill_game(game_dir, args.dry_run)
        if filled == -1:
            games_errored += 1
            print(f"  {game_id}: ERROR")
            continue
        if total == 0:
            games_skipped += 1
            continue
        games_done += 1
        total_filled += filled
        total_preserved += preserved
        total_rows += total
        if games_done <= 20 or games_done % 50 == 0:
            pct = (filled / total * 100) if total else 0
            print(
                f"  {game_id}: filled {filled}/{total} ({pct:.0f}%) "
                f"preserved {preserved} OCR vals"
            )

    print()
    print("=" * 60)
    print(f"games processed   : {games_done}")
    print(f"games skipped     : {games_skipped} (no scoreboard_period column)")
    print(f"games errored     : {games_errored}")
    print(f"total rows        : {total_rows}")
    print(f"rows filled       : {total_filled}")
    print(f"rows preserved    : {total_preserved} (OCR-confirmed)")
    if total_rows:
        print(f"coverage after    : {(total_filled + total_preserved) / total_rows * 100:.1f}%")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
