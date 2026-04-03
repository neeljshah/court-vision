"""
backfill_player_names.py — Retroactively fill player_name in tracking_data.csv
and shot_log.csv for all processed game directories.

Uses jersey_name_map.json (per-game directory) as primary source.
Falls back to NBA API roster lookup when jersey_name_map is missing.

Usage:
    conda activate basketball_ai
    python scripts/backfill_player_names.py                  # all game dirs
    python scripts/backfill_player_names.py --game-id 0022401183
    python scripts/backfill_player_names.py --dry-run        # preview without writing
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
from pathlib import Path
from typing import Optional

_TRACKING_DIR = Path(__file__).parent.parent / "data" / "tracking"
_TARGET_FILES = ("tracking_data.csv", "shot_log.csv")


def _load_jersey_map(game_dir: Path) -> dict:
    """Load jersey_name_map.json from game directory. Returns {} if missing."""
    path = game_dir / "jersey_name_map.json"
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  [warn] jersey_name_map.json load failed: {e}")
        return {}


def _fetch_roster_from_api(game_id: str) -> dict:
    """Fetch jersey -> player_name mapping via NBA API (CommonTeamRoster).

    Strategy:
    1. BoxScoreTraditionalV2 to get both team IDs.
    2. CommonTeamRoster for each team (always has the NUM column).
    """
    try:
        from nba_api.stats.endpoints import boxscoretraditionalv2, commonteamroster
    except ImportError:
        return {}
    time.sleep(0.6)
    try:
        box = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=game_id)
        teams_df = box.get_data_frames()[1]
        team_ids = list(teams_df["TEAM_ID"].unique()) if "TEAM_ID" in teams_df.columns else []
    except Exception as e:
        print(f"  [warn] BoxScore team lookup failed: {e}")
        return {}

    result = {}
    for tid in team_ids:
        time.sleep(0.6)
        try:
            roster = commonteamroster.CommonTeamRoster(
                team_id=int(tid), season="2024-25"
            ).get_data_frames()[0]
            for _, row in roster.iterrows():
                jersey = str(row.get("NUM", "") or "").strip()
                name = str(row.get("PLAYER", "") or "").strip()
                if jersey and name:
                    result[jersey] = name
        except Exception as e:
            print(f"  [warn] CommonTeamRoster failed for team {tid}: {e}")
            continue

    if result:
        # Save as jersey_name_map.json for future runs
        jmap_path = _TRACKING_DIR / game_id / "jersey_name_map.json"
        try:
            with open(jmap_path, "w", encoding="utf-8") as f:
                import json as _json
                _json.dump(result, f, indent=2)
            print(f"  Saved jersey_name_map.json ({len(result)} entries)")
        except Exception:
            pass

    return result


def backfill_game(game_dir: Path, game_id: Optional[str], dry_run: bool = False) -> dict:
    """Fill player_name in all CSV files for one game directory.

    Returns dict of {filename: rows_updated}.
    """
    jersey_map = _load_jersey_map(game_dir)
    if not jersey_map and game_id:
        print(f"  No jersey_name_map.json — trying NBA API for {game_id}")
        jersey_map = _fetch_roster_from_api(game_id)

    if not jersey_map:
        print(f"  [skip] No jersey map available for {game_dir.name}")
        return {}

    results = {}
    for fname in _TARGET_FILES:
        fpath = game_dir / fname
        if not fpath.exists():
            continue

        try:
            with open(fpath, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                if "player_name" not in (reader.fieldnames or []):
                    continue
                rows = list(reader)
                fields = list(reader.fieldnames)
        except Exception as e:
            print(f"  [error] read {fname}: {e}")
            continue

        # Check how many rows need filling
        blank = sum(1 for r in rows if not r.get("player_name", "").strip())
        if blank == 0:
            print(f"  {fname}: already fully filled ({len(rows)} rows)")
            results[fname] = 0
            continue

        updated = 0
        for row in rows:
            if row.get("player_name", "").strip():
                continue
            jersey_raw = str(row.get("jersey_number", "")).strip()
            if jersey_raw and jersey_raw != "nan":
                name = jersey_map.get(jersey_raw, "")
                if name:
                    row["player_name"] = name
                    updated += 1

        if dry_run:
            print(f"  [dry-run] {fname}: would fill {updated}/{blank} blank rows")
        else:
            try:
                with open(fpath, "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
                    w.writeheader()
                    w.writerows(rows)
                print(f"  {fname}: filled {updated}/{blank} blank rows -> {fpath}")
            except Exception as e:
                print(f"  [error] write {fname}: {e}")
        results[fname] = updated

    return results


def main():
    ap = argparse.ArgumentParser(description="Retroactively fill player_name in tracking CSVs")
    ap.add_argument("--game-id", default=None,
                    help="Process only this game ID (e.g. 0022401183)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Preview changes without writing")
    args = ap.parse_args()

    if args.game_id:
        game_dirs = [(_TRACKING_DIR / args.game_id, args.game_id)]
    else:
        # Auto-discover: directories that look like NBA game IDs (10-digit numbers)
        game_dirs = []
        for d in sorted(_TRACKING_DIR.iterdir()):
            if d.is_dir() and d.name.isdigit() and len(d.name) == 10:
                game_dirs.append((d, d.name))

    if not game_dirs:
        print("No game directories found.")
        return

    total_updated = 0
    for game_dir, game_id in game_dirs:
        print(f"\n{game_id} ({game_dir})")
        res = backfill_game(game_dir, game_id, dry_run=args.dry_run)
        for fname, n in res.items():
            total_updated += n

    print(f"\nTotal rows updated: {total_updated}")


if __name__ == "__main__":
    main()
