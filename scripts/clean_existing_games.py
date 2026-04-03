"""
clean_existing_games.py — Retroactively clean all existing game directories.

Runs TrackingCleaner + QualityValidator on every game in data/games/ and
data/tracking/, then writes a summary report to data/cleaning_report.csv.

Usage:
    conda activate basketball_ai
    python scripts/clean_existing_games.py
    python scripts/clean_existing_games.py --dry-run   # report only, no writes
    python scripts/clean_existing_games.py --game-id 0022401175
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from src.data.tracking_cleaner import TrackingCleaner
from src.data.quality_validator import QualityValidator

DATA_DIR = PROJECT_DIR / "data"
REPORT_PATH = DATA_DIR / "cleaning_report.csv"
REPORT_FIELDS = [
    "game_id", "tracking_rows", "possession_count", "median_poss_sec",
    "shot_count", "feature_rows", "grade",
    "sentinel_pct", "player_name_pct", "team_abbrev_pct", "homography_pct",
]


def _find_game_dirs() -> list[Path]:
    """Return canonical game dirs. data/tracking/ is authoritative; fall back to data/games/.
    Deduplicates: if a game ID exists in both, only the data/tracking/ copy is returned."""
    seen: set[str] = set()
    dirs: list[Path] = []
    # data/tracking/ is the canonical location written by run_phase_g / nba_enricher
    for parent in (DATA_DIR / "tracking", DATA_DIR / "games"):
        if not parent.exists():
            continue
        for d in sorted(parent.iterdir()):
            if d.is_dir() and (d / "tracking_data.csv").exists():
                if d.name not in seen:
                    seen.add(d.name)
                    dirs.append(d)
    return dirs


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean all existing game directories")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate only — do not write cleaned files")
    parser.add_argument("--game-id", default=None,
                        help="Process a single game ID only")
    args = parser.parse_args()

    game_dirs = _find_game_dirs()
    if args.game_id:
        game_dirs = [d for d in game_dirs if d.name == args.game_id]
        if not game_dirs:
            print(f"ERROR: game {args.game_id} not found in data/games/ or data/tracking/")
            sys.exit(1)

    print(f"Found {len(game_dirs)} game directories")
    if args.dry_run:
        print("DRY RUN — validation only, no files written\n")

    rows = []
    for game_dir in game_dirs:
        gid = game_dir.name
        print(f"\n--- {gid} ---")

        if not args.dry_run:
            try:
                cleaner = TrackingCleaner(str(game_dir))
                clean_report = cleaner.clean_all()
                print(f"  Cleaned: {clean_report}")
            except Exception as e:
                print(f"  ERROR during cleaning: {e}")

        try:
            validator = QualityValidator(str(game_dir))
            val_report = validator.validate()
            grade = validator.grade()
        except Exception as e:
            print(f"  ERROR during validation: {e}")
            grade = "F"
            val_report = {}

        row = {"game_id": gid, "grade": grade}
        for key in ("tracking_rows", "possession_count", "feature_rows", "shot_count", "median_poss_sec"):
            row[key] = val_report.get(key, {}).get("value", "")  # type: ignore[call-overload]

        for key in ("sentinel_pct", "player_name_pct", "team_abbrev_pct", "homography_pct"):
            row[key] = val_report.get(key, {}).get("value", "")  # type: ignore[call-overload]

        passed = [k for k, v in val_report.items()
                  if isinstance(v, dict) and v.get("passed")]
        failed = [k for k, v in val_report.items()
                  if isinstance(v, dict) and not v.get("passed")]
        print(f"  Grade: {grade}  |  passed: {passed}  |  failed: {failed}")
        rows.append(row)

    # Write report
    if not args.dry_run:
        with open(REPORT_PATH, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=REPORT_FIELDS, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        print(f"\nReport written to {REPORT_PATH}")

    # Summary table
    print(f"\n{'Game':<16} {'Grade':>5} {'Rows':>8} {'Poss':>6} {'Med(s)':>7} {'Shots':>6}")
    print("-" * 55)
    for r in rows:
        print(f"{r['game_id']:<16} {r['grade']:>5} {str(r.get('tracking_rows','')):>8} "
              f"{str(r.get('possession_count','')):>6} "
              f"{str(r.get('median_poss_sec','')):>7} "
              f"{str(r.get('shot_count','')):>6}")


if __name__ == "__main__":
    main()
