#!/usr/bin/env python3
"""
run_features_efficient.py — Generate features with memory efficiency for large games.

For games >100K rows, skips expensive advanced features (A-1 to A-14) to prevent OOM.

Usage:
    python scripts/run_features_efficient.py --game-id 0022400430
    python scripts/run_features_efficient.py --game-id 0022400430 --full  # include advanced features
"""

import sys
from pathlib import Path
import argparse

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-id", type=str, required=True, help="Game ID (e.g. 0022400430)")
    parser.add_argument("--full", action="store_true", help="Include advanced features (slower)")
    args = parser.parse_args()

    from src.features.feature_engineering import run
    import pandas as pd

    game_dir = PROJECT_DIR / "data" / "games" / args.game_id
    tracking_file = game_dir / "tracking_data.csv"
    features_file = game_dir / "features.csv"

    if not tracking_file.exists():
        print(f"ERROR: {tracking_file} not found")
        return 1

    # Check game size
    df_peek = pd.read_csv(tracking_file, nrows=1)
    total_rows = len(pd.read_csv(tracking_file, usecols=['frame']))

    skip_advanced = total_rows > 100000 and not args.full

    if skip_advanced:
        print(f"Large game detected ({total_rows:,} rows). Skipping advanced features for speed/memory.")
    else:
        print(f"Processing game ({total_rows:,} rows). Including all features.")

    print(f"Generating features: {tracking_file} -> {features_file}")

    try:
        run(input_path=str(tracking_file), output_path=str(features_file), skip_advanced=skip_advanced)
        print(f"SUCCESS: {features_file}")
        return 0
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
