#!/usr/bin/env python3
"""
batch_enrich_player_names.py — Add player_name to all games via jersey lookup.

Uses jersey_number in tracking_data.csv to lookup player names from:
1. jersey_name_map.json (if exists in game dir)
2. NBA API CommonTeamRoster (as fallback)

Then updates:
- tracking_data.csv with new player_name column
- features.csv with player_name column

Usage:
    python scripts/batch_enrich_player_names.py             # Process all games
    python scripts/batch_enrich_player_names.py --game-id 0022400430
    python scripts/batch_enrich_player_names.py --dry-run   # Preview only
"""

import json
import pandas as pd
import sys
import time
from pathlib import Path
from typing import Dict, Optional
import argparse

# Force UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_DIR = Path(__file__).resolve().parent.parent
GAMES_DIR = PROJECT_DIR / "data" / "games"

def get_jersey_map(game_id: str) -> Dict[int, str]:
    """Load or fetch jersey -> player_name mapping."""
    game_dir = GAMES_DIR / game_id

    # Try loading from jersey_name_map.json
    map_file = game_dir / "jersey_name_map.json"
    if map_file.exists():
        try:
            with open(map_file, encoding="utf-8") as f:
                data = json.load(f)
                return {int(k) if isinstance(k, str) and k.isdigit() else k: v for k, v in data.items()}
        except:
            pass

    # Fallback: fetch from NBA API
    try:
        from nba_api.stats.endpoints import boxscoretraditionalv2, commonteamroster
    except:
        return {}

    result = {}
    try:
        # Get box score to find team IDs
        box = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=game_id)
        teams_df = box.get_data_frames()[1]
        team_ids = list(teams_df["TEAM_ID"].unique()) if "TEAM_ID" in teams_df.columns else []

        # Fetch roster for each team
        for tid in team_ids:
            time.sleep(0.5)
            roster = commonteamroster.CommonTeamRoster(team_id=int(tid), season="2024-25").get_data_frames()[0]
            for _, row in roster.iterrows():
                jersey = int(row.get("NUM", 0) or 0)
                name = str(row.get("PLAYER", "") or "").strip()
                if jersey > 0 and name:
                    result[jersey] = name

        # Cache result
        if result:
            with open(map_file, "w", encoding="utf-8") as f:
                json.dump({str(k): v for k, v in result.items()}, f, indent=2)
    except Exception as e:
        pass

    return result

def enrich_game(game_id: str, dry_run: bool = False) -> int:
    """Add player_name to game's tracking and features CSVs. Returns rows filled."""
    game_dir = GAMES_DIR / game_id
    tracking_file = game_dir / "tracking_data.csv"
    features_file = game_dir / "features.csv"

    if not tracking_file.exists():
        return 0

    # Load data
    tracking_df = pd.read_csv(tracking_file, low_memory=False)

    # Get jersey mapping
    jersey_map = get_jersey_map(game_id)
    if not jersey_map:
        return 0

    # Add player_name via jersey number
    if "jersey_number" not in tracking_df.columns:
        return 0

    tracking_df["jersey_number"] = pd.to_numeric(tracking_df["jersey_number"], errors="coerce")
    tracking_df["player_name"] = tracking_df["jersey_number"].map(jersey_map).fillna("")

    filled = (tracking_df["player_name"] != "").sum()

    if filled == 0:
        return 0

    # Save updated tracking
    if not dry_run:
        tracking_df.to_csv(tracking_file, index=False, encoding="utf-8")

    # Update features if it exists
    if features_file.exists():
        features_df = pd.read_csv(features_file, low_memory=False)

        # Merge player_name from tracking
        if "frame" in features_df.columns and "frame" in tracking_df.columns and "player_id" in features_df.columns:
            # Get unique player_name per player_id from tracking
            player_names = tracking_df[tracking_df["player_name"] != ""].groupby("player_id")["player_name"].first()
            features_df["player_name"] = features_df["player_id"].map(player_names).fillna("")

            if not dry_run:
                features_df.to_csv(features_file, index=False, encoding="utf-8")

    return filled

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-id", type=str, help="Process single game")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    games = [args.game_id] if args.game_id else sorted([d.name for d in GAMES_DIR.iterdir() if d.is_dir()])

    print(f"Enriching {len(games)} games with player names...\n")

    total_filled = 0
    for i, game_id in enumerate(games, 1):
        filled = enrich_game(game_id, dry_run=args.dry_run)
        if filled > 0:
            print(f"[{i:2d}] {game_id}: {filled:6d} rows filled")
            total_filled += filled
        elif i <= 5 or i % 10 == 0:
            print(f"[{i:2d}] {game_id}: skip (no jersey map)")

    print(f"\nTotal rows enriched: {total_filled:,}")
    if args.dry_run:
        print("(dry-run mode — no files modified)")

    return 0

if __name__ == "__main__":
    sys.exit(main())
