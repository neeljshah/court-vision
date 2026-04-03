"""
consolidate_game_data.py — Merge data/games/ into data/tracking/ as single canonical location.

Rules:
  1. data/tracking/{game} is canonical output dir (current pipeline standard)
  2. For games only in data/games/ → copy entire folder to data/tracking/
  3. For games in both → copy any files MISSING from tracking/ (never overwrite)
  4. For tracking_data.csv specifically → keep whichever has MORE rows
  5. Named clips (lal_sas_2025 etc.) → only copy if not already in tracking/
  6. Never delete anything — data/games/ stays intact as backup

Run:
    python scripts/consolidate_game_data.py [--dry-run]
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
TRACKING_DIR = PROJECT_DIR / "data" / "tracking"
GAMES_DIR    = PROJECT_DIR / "data" / "games"

KEY_FILES = [
    "tracking_data.csv",
    "ball_tracking.csv",
    "features.csv",
    "possessions.csv",
    "possessions_enriched.csv",
    "shot_log.csv",
    "shot_log_enriched.csv",
    "player_clip_stats.csv",
    "events_log.csv",
    "jersey_name_map.json",
    "team_colors.json",
    "manifest.json",
]


def row_count(path: Path) -> int:
    """Fast line count minus header."""
    if not path.exists():
        return 0
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f) - 1
    except Exception:
        return 0


def consolidate(dry_run: bool = False):
    copied = 0
    skipped = 0
    upgraded = 0

    # Collect all unique game dirs across both locations
    game_ids: set[str] = set()
    for d in GAMES_DIR.iterdir():
        if d.is_dir():
            game_ids.add(d.name)

    print(f"Found {len(game_ids)} game dirs in data/games/")
    print(f"{'DRY RUN — no changes written' if dry_run else 'LIVE RUN — copying files'}")
    print()

    for gid in sorted(game_ids, key=lambda x: (not x.startswith("00224"), x)):
        g_path = GAMES_DIR / gid
        t_path = TRACKING_DIR / gid

        g_files = {f.name: f for f in g_path.iterdir() if f.is_file()} if g_path.exists() else {}
        t_files = {f.name: f for f in t_path.iterdir() if f.is_file()} if t_path.exists() else {}

        if not g_files:
            continue

        actions: list[str] = []

        for fname in KEY_FILES:
            g_file = g_path / fname
            t_file = t_path / fname

            if not g_file.exists():
                continue  # source doesn't have it either

            if not t_file.exists():
                # File missing in tracking/ — copy it
                actions.append(f"  COPY  {fname}")
                if not dry_run:
                    t_path.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(g_file, t_file)
                copied += 1

            elif fname == "tracking_data.csv":
                # Special: keep version with more rows
                t_rows = row_count(t_file)
                g_rows = row_count(g_file)
                if g_rows > t_rows:
                    actions.append(f"  UPGRADE tracking_data.csv  ({t_rows} -> {g_rows} rows)")
                    if not dry_run:
                        # Back up old file first
                        bak = t_path / "tracking_data.csv.games_bak"
                        if not bak.exists():
                            shutil.copy2(t_file, bak)
                        shutil.copy2(g_file, t_file)
                    upgraded += 1
                else:
                    skipped += 1
            else:
                skipped += 1  # already exists in tracking/, skip

        if actions:
            print(f"{gid}")
            for a in actions:
                print(a)
        else:
            print(f"{gid}  — already complete")

    print()
    print(f"Done — copied={copied}  upgraded={upgraded}  skipped={skipped}")
    if dry_run:
        print("(dry run — rerun without --dry-run to apply)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Consolidate data/games/ into data/tracking/")
    ap.add_argument("--dry-run", action="store_true", help="Show what would be done without writing")
    args = ap.parse_args()
    consolidate(dry_run=args.dry_run)
