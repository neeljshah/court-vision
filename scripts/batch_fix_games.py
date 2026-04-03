#!/usr/bin/env python3
"""
batch_fix_games.py — Fix all games with efficient postprocessing.

Issues fixed:
1. Add player_name to tracking_data.csv (from jersey_name_map.json + jersey_number)
2. Recompute nearest_opponent in features.csv
3. Regenerate features.csv with corrected data
4. Add missing shot_log.csv for partial games (needs video re-run)

Usage:
    python scripts/batch_fix_games.py --add-names      # Add player_name to tracking
    python scripts/batch_fix_games.py --fix-features   # Recompute features
    python scripts/batch_fix_games.py --all            # Do all fixes (full pipeline)
    python scripts/batch_fix_games.py --status         # Check which games need what
"""

import json
import pandas as pd
import sys
import argparse
from pathlib import Path
from typing import Dict, Optional
import subprocess

# Force UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
GAMES_DIR = DATA_DIR / "games"

def load_jersey_map(game_id: str) -> Dict[int, str]:
    """Load jersey_name_map.json for a game."""
    map_file = GAMES_DIR / game_id / "jersey_name_map.json"
    if map_file.exists():
        try:
            with open(map_file) as f:
                data = json.load(f)
                # Convert string keys to ints
                return {int(k): v for k, v in data.items()}
        except:
            pass
    return {}

def add_player_names_to_tracking(game_id: str) -> bool:
    """Add player_name column to tracking_data.csv using jersey_name_map."""
    game_path = GAMES_DIR / game_id
    tracking_file = game_path / "tracking_data.csv"

    if not tracking_file.exists():
        return False

    try:
        df = pd.read_csv(tracking_file)

        # Skip if already has player_name
        if "player_name" in df.columns and df["player_name"].notna().sum() > len(df) * 0.5:
            return False

        # Load jersey mapping
        jersey_map = load_jersey_map(game_id)
        if not jersey_map:
            return False

        # Join player names
        df["jersey_number"] = pd.to_numeric(df.get("jersey_number", ""), errors="coerce").fillna(-1)
        df["player_name"] = df["jersey_number"].map(jersey_map).fillna("")

        # Save back with UTF-8 encoding
        df.to_csv(tracking_file, index=False, encoding="utf-8")
        print(f"  Added player_name to {game_id}: {(df['player_name'] != '').sum()} rows filled")
        return True

    except Exception as e:
        print(f"  ERROR {game_id}: {str(e)[:100]}")
        return False

def regenerate_features(game_id: str) -> bool:
    """Regenerate features.csv for a game (must have tracking + jersey names)."""
    try:
        from src.features.feature_engineering import run

        game_path = GAMES_DIR / game_id
        output_dir = str(game_path)

        # Run feature engineering on this game's data
        run(output_dir=output_dir)
        print(f"  Regenerated features for {game_id}")
        return True

    except Exception as e:
        print(f"  ERROR {game_id}: {str(e)[:100]}")
        return False

def check_game_status(game_id: str) -> Dict[str, bool]:
    """Check what a game needs."""
    game_path = GAMES_DIR / game_id
    return {
        'has_tracking': (game_path / 'tracking_data.csv').exists(),
        'has_player_names': False,  # Check this separately
        'has_shots': (game_path / 'shot_log.csv').exists(),
        'has_features': (game_path / 'features.csv').exists(),
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--add-names', action='store_true', help='Add player_name to tracking CSVs')
    parser.add_argument('--fix-features', action='store_true', help='Regenerate features.csv files')
    parser.add_argument('--all', action='store_true', help='Do all fixes in sequence')
    parser.add_argument('--status', action='store_true', help='Check status only')
    parser.add_argument('--game-id', type=str, help='Only process one game')
    args = parser.parse_args()

    games = [args.game_id] if args.game_id else sorted([d.name for d in GAMES_DIR.iterdir() if d.is_dir()])

    if args.status:
        print(f"\n=== STATUS CHECK ({len(games)} games) ===\n")
        for game_id in games[:10]:  # Sample first 10
            game_path = GAMES_DIR / game_id
            tracking = game_path / 'tracking_data.csv'

            if tracking.exists():
                df = pd.read_csv(tracking, nrows=100)
                has_pnames = 'player_name' in df.columns and df['player_name'].notna().sum() > 0
                pct_filled = df['player_name'].notna().sum() / len(df) * 100 if 'player_name' in df.columns else 0
            else:
                has_pnames = False
                pct_filled = 0

            has_shots = (game_path / 'shot_log.csv').exists()
            has_features = (game_path / 'features.csv').exists()

            print(f"{game_id}: names={pct_filled:.0f}%, shots={has_shots}, features={has_features}")
        return 0

    # Run fixes
    if args.add_names or args.all:
        print(f"\n=== ADDING PLAYER NAMES ({len(games)} games) ===\n")
        fixed = 0
        for i, game_id in enumerate(games, 1):
            print(f"[{i}/{len(games)}] {game_id}...")
            if add_player_names_to_tracking(game_id):
                fixed += 1
        print(f"\nFixed {fixed} games with player names")

    if args.fix_features or args.all:
        print(f"\n=== REGENERATING FEATURES ({len(games)} games) ===\n")
        fixed = 0
        for i, game_id in enumerate(games, 1):
            print(f"[{i}/{len(games)}] {game_id}...")
            if regenerate_features(game_id):
                fixed += 1
        print(f"\nRegenerated features for {fixed} games")

    return 0

if __name__ == '__main__':
    sys.exit(main())
