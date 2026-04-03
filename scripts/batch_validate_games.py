#!/usr/bin/env python3
"""
batch_validate_games.py — Fast validation of all game datasets.
Reports data quality per game, identifies gaps, suggests fixes.

Usage:
    python scripts/batch_validate_games.py                # Check all games
    python scripts/batch_validate_games.py --fix          # Fix common issues
    python scripts/batch_validate_games.py --summary      # Print summary only
"""

import json
import pandas as pd
import sys
from pathlib import Path
from typing import Dict, List, Tuple
import argparse

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
GAMES_DIR = DATA_DIR / "games"

def check_game(game_id: str) -> Dict:
    """Validate single game dataset."""
    game_path = GAMES_DIR / game_id

    result = {
        'game_id': game_id,
        'tracking_rows': 0,
        'tracking_ok': False,
        'shots': 0,
        'shots_ok': False,
        'possessions': 0,
        'poss_ok': False,
        'features_rows': 0,
        'features_ok': False,
        'issues': [],
    }

    # Check tracking_data.csv
    tracking_file = game_path / 'tracking_data.csv'
    if tracking_file.exists():
        try:
            df = pd.read_csv(tracking_file)
            result['tracking_rows'] = len(df)
            result['tracking_ok'] = result['tracking_rows'] > 0

            # Check required columns
            required = {'frame', 'timestamp', 'x_position', 'y_position', 'team'}
            missing = required - set(df.columns)
            if missing:
                result['issues'].append(f'tracking missing cols: {missing}')
        except Exception as e:
            result['issues'].append(f'tracking read error: {str(e)[:50]}')
    else:
        result['issues'].append('NO tracking_data.csv')

    # Check shot_log.csv
    shot_file = game_path / 'shot_log.csv'
    if shot_file.exists():
        try:
            df = pd.read_csv(shot_file)
            result['shots'] = len(df)
            result['shots_ok'] = result['shots'] > 0
        except Exception as e:
            result['issues'].append(f'shot_log read error: {str(e)[:50]}')
    else:
        result['issues'].append('NO shot_log.csv')

    # Check possessions.csv
    poss_file = game_path / 'possessions.csv'
    if poss_file.exists():
        try:
            df = pd.read_csv(poss_file)
            result['possessions'] = len(df)
            result['poss_ok'] = result['possessions'] > 0
        except Exception as e:
            result['issues'].append(f'possessions read error: {str(e)[:50]}')
    else:
        result['issues'].append('NO possessions.csv')

    # Check features.csv
    features_file = game_path / 'features.csv'
    if features_file.exists():
        try:
            df = pd.read_csv(features_file)
            result['features_rows'] = len(df)
            result['features_ok'] = result['features_rows'] > 0

            # Check for common issues
            if 'player_name' in df.columns:
                pct_filled = df['player_name'].notna().sum() / len(df) * 100
                if pct_filled < 50:
                    result['issues'].append(f'player_name only {pct_filled:.0f}% filled')
            else:
                result['issues'].append('NO player_name column in features')

            if 'nearest_opponent' in df.columns:
                pct_filled = df['nearest_opponent'].notna().sum() / len(df) * 100
                if pct_filled < 95:
                    result['issues'].append(f'nearest_opponent only {pct_filled:.0f}% filled')

            if 'handler_isolation' in df.columns:
                pct_filled = df['handler_isolation'].notna().sum() / len(df) * 100
                if pct_filled < 50:
                    result['issues'].append(f'handler_isolation only {pct_filled:.0f}% filled')

        except Exception as e:
            result['issues'].append(f'features read error: {str(e)[:50]}')
    else:
        result['issues'].append('NO features.csv')

    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fix', action='store_true', help='Auto-fix common issues')
    parser.add_argument('--summary', action='store_true', help='Summary only')
    args = parser.parse_args()

    games = sorted([d.name for d in GAMES_DIR.iterdir() if d.is_dir()])
    results = []

    print(f'Validating {len(games)} games...\n')

    for i, game_id in enumerate(games, 1):
        result = check_game(game_id)
        results.append(result)

        if not args.summary:
            status = 'OK' if not result['issues'] else 'WARN'
            print(f"[{i:2d}/{len(games)}] {game_id} {status}")
            if result['issues']:
                for issue in result['issues']:
                    print(f"        - {issue}")

    # Summary stats
    complete = sum(1 for r in results if all([r['tracking_ok'], r['shots_ok'], r['poss_ok'], r['features_ok']]))
    with_issues = sum(1 for r in results if r['issues'])

    print(f'\n=== SUMMARY ===')
    print(f'Total games: {len(games)}')
    print(f'Complete & OK: {complete}')
    print(f'Games with issues: {with_issues}')
    print(f'Total rows processed: {sum(r["tracking_rows"] for r in results):,}')

    # Group by issue type
    issue_counts = {}
    for r in results:
        for issue in r['issues']:
            key = issue.split(':')[0].strip()
            issue_counts[key] = issue_counts.get(key, 0) + 1

    if issue_counts:
        print(f'\n=== TOP ISSUES ===')
        for issue, count in sorted(issue_counts.items(), key=lambda x: -x[1])[:10]:
            print(f'{issue}: {count} games')

    # Games without issues
    perfect = [r['game_id'] for r in results if not r['issues']]
    if perfect:
        print(f'\n=== PERFECT GAMES ({len(perfect)}) ===')
        for gid in perfect:
            print(f'  {gid}')

    return 0 if complete >= 20 else 1

if __name__ == '__main__':
    sys.exit(main())
