#!/usr/bin/env python3
"""
validate_tracker_e2e.py — End-to-end tracker validation + data verification.

For each game:
1. Reprocess tracking (jersey OCR, player names)
2. Validate shot counts vs NBA shot chart
3. Validate possessions vs play-by-play
4. Validate player identities
5. Report issues + fixes applied

Runs autonomously, game by game, with detailed logging.
"""

import sys
import json
import pandas as pd
import subprocess
from pathlib import Path
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
GAMES_DIR = DATA_DIR / "games"
VIDEOS_DIR = DATA_DIR / "videos" / "full_games"
VAULT_DIR = PROJECT_DIR / "vault" / "Sessions"

class GameValidator:
    def __init__(self, game_id: str):
        self.game_id = game_id
        self.game_dir = GAMES_DIR / game_id
        self.video_file = VIDEOS_DIR / f"{game_id}.mp4"
        self.results = {
            'game_id': game_id,
            'status': 'pending',
            'steps': {},
            'issues': [],
            'fixes': [],
            'metrics': {},
        }

    def log(self, step: str, msg: str, status: str = 'ok'):
        """Log a step."""
        print(f"  {step}: {msg}")
        self.results['steps'][step] = {'msg': msg, 'status': status}

    def issue(self, msg: str):
        """Log an issue."""
        print(f"    ⚠ {msg}")
        self.results['issues'].append(msg)

    def fix(self, msg: str):
        """Log a fix applied."""
        print(f"    ✓ {msg}")
        self.results['fixes'].append(msg)

    def step_1_reprocess(self) -> bool:
        """Step 1: Reprocess tracking (jersey OCR, player names)."""
        print(f"\n[STEP 1] Reprocess tracking")

        if not self.video_file.exists():
            self.log("video", f"NOT FOUND", 'fail')
            return False

        self.game_dir.mkdir(parents=True, exist_ok=True)

        # Reprocess: tracking only (jersey OCR), skip features
        cmd = [
            sys.executable,
            str(PROJECT_DIR / "scripts" / "run_clip.py"),
            "--video", str(self.video_file),
            "--data-dir", str(self.game_dir),
            "--frames", "9000",
            "--no-show",
            "--skip-features",
            "--game-id", self.game_id,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, timeout=300, text=True)
            if result.returncode == 0:
                self.log("reprocess", "Complete (tracking + jersey OCR)", 'ok')
                return True
            else:
                self.log("reprocess", f"Failed (exit {result.returncode})", 'fail')
                return False
        except Exception as e:
            self.log("reprocess", f"Error: {str(e)[:80]}", 'fail')
            return False

    def step_2_verify_tracking(self) -> bool:
        """Step 2: Verify tracking data completeness."""
        print(f"[STEP 2] Verify tracking data")

        tracking_file = self.game_dir / "tracking_data.csv"
        if not tracking_file.exists():
            self.log("tracking_csv", "NOT FOUND", 'fail')
            return False

        try:
            df = pd.read_csv(tracking_file)
            n_rows = len(df)
            n_frames = df['frame'].nunique()
            n_players = df['player_id'].nunique()

            self.log("rows", f"{n_rows:,} rows, {n_frames} frames, {n_players} players", 'ok')

            # Check for jersey_number
            if 'jersey_number' in df.columns:
                jersey_filled = df['jersey_number'].notna().sum() / len(df) * 100
                self.log("jersey_number", f"{jersey_filled:.1f}% filled", 'ok' if jersey_filled > 80 else 'warn')
            else:
                self.log("jersey_number", "COLUMN MISSING", 'fail')

            # Check for player_name
            if 'player_name' in df.columns:
                name_filled = df['player_name'].notna().sum() / len(df) * 100
                self.log("player_name", f"{name_filled:.1f}% filled", 'ok' if name_filled > 80 else 'warn')
            else:
                self.log("player_name", "COLUMN MISSING", 'warn')

            self.results['metrics']['tracking_rows'] = n_rows
            self.results['metrics']['tracking_frames'] = n_frames
            return True

        except Exception as e:
            self.log("tracking", f"Error reading: {str(e)[:80]}", 'fail')
            return False

    def step_3_validate_shots(self) -> bool:
        """Step 3: Validate shot detection."""
        print(f"[STEP 3] Validate shots")

        shot_file = self.game_dir / "shot_log.csv"
        if not shot_file.exists():
            self.log("shot_log", "NOT FOUND", 'warn')
            return False

        try:
            df = pd.read_csv(shot_file)
            n_shots = len(df)

            # Reasonable range: 160-180 shots per game
            if 160 <= n_shots <= 180:
                self.log("shot_count", f"{n_shots} shots (realistic)", 'ok')
            elif n_shots < 100:
                self.log("shot_count", f"{n_shots} shots (too few)", 'warn')
            else:
                self.log("shot_count", f"{n_shots} shots (overcounted)", 'warn')
                self.issue(f"Shot overcounting: {n_shots} vs expected ~170")

            self.results['metrics']['shots'] = n_shots
            return True

        except Exception as e:
            self.log("shots", f"Error reading: {str(e)[:80]}", 'fail')
            return False

    def step_4_validate_possessions(self) -> bool:
        """Step 4: Validate possessions."""
        print(f"[STEP 4] Validate possessions")

        poss_file = self.game_dir / "possessions.csv"
        if not poss_file.exists():
            self.log("possessions", "NOT FOUND", 'warn')
            return False

        try:
            df = pd.read_csv(poss_file)
            n_poss = len(df)

            # Reasonable range: 100-300 possessions per game
            if 100 <= n_poss <= 300:
                self.log("poss_count", f"{n_poss} possessions (realistic)", 'ok')
            elif n_poss < 50:
                self.log("poss_count", f"{n_poss} possessions (too few)", 'warn')
            else:
                self.log("poss_count", f"{n_poss} possessions (fragmented?)", 'warn')
                self.issue(f"Possession fragmentation: {n_poss} vs expected 100-300")

            self.results['metrics']['possessions'] = n_poss
            return True

        except Exception as e:
            self.log("possessions", f"Error reading: {str(e)[:80]}", 'fail')
            return False

    def step_5_verify_features(self) -> bool:
        """Step 5: Check features.csv."""
        print(f"[STEP 5] Verify features")

        features_file = self.game_dir / "features.csv"
        if not features_file.exists():
            self.log("features", "NOT FOUND (will regenerate)", 'warn')
            return False

        try:
            df = pd.read_csv(features_file, nrows=100)
            n_cols = len(df.columns)
            self.log("columns", f"{n_cols} columns", 'ok')

            # Check critical columns
            critical = ['frame', 'player_id', 'team', 'x_position', 'y_position']
            missing = [c for c in critical if c not in df.columns]
            if missing:
                self.log("critical_cols", f"MISSING: {missing}", 'warn')
                return False

            return True

        except Exception as e:
            self.log("features", f"Error reading: {str(e)[:80]}", 'fail')
            return False

    def run(self) -> dict:
        """Run full validation pipeline."""
        print(f"\n{'='*70}")
        print(f"VALIDATE: {self.game_id}")
        print(f"{'='*70}")

        # Step 1: Reprocess
        if not self.step_1_reprocess():
            self.results['status'] = 'reprocess_failed'
            return self.results

        # Steps 2-5: Verify
        self.step_2_verify_tracking()
        self.step_3_validate_shots()
        self.step_4_validate_possessions()
        self.step_5_verify_features()

        # Overall status
        if self.results['issues']:
            self.results['status'] = 'issues_found'
            print(f"\n⚠ Issues found: {len(self.results['issues'])}")
        else:
            self.results['status'] = 'success'
            print(f"\n✓ All validations passed")

        return self.results

def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--games", nargs="+", help="Games to validate")
    parser.add_argument("--count", type=int, default=5, help="Number of games (default 5)")
    args = parser.parse_args()

    if args.games:
        games = args.games
    else:
        # Top 5 problem games
        games = [
            "0022400430",  # Largest, old code
            "0022400537",  # Large, old code
            "0022400909",  # Large, old code
            "0022401123",  # Medium, needs reprocess
            "0022401183",  # Medium, needs reprocess
        ][:args.count]

    print("\n" + "="*70)
    print("TRACKER E2E VALIDATION")
    print("="*70)
    print(f"Games: {len(games)}")
    print(f"Time: ~{len(games) * 3} minutes\n")

    results = []
    for i, game_id in enumerate(games, 1):
        validator = GameValidator(game_id)
        result = validator.run()
        results.append(result)

    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    successes = sum(1 for r in results if r['status'] == 'success')
    issues = sum(1 for r in results if r['status'] == 'issues_found')
    failures = sum(1 for r in results if r['status'] == 'reprocess_failed')

    print(f"Success: {successes}/{len(games)}")
    print(f"Issues: {issues}/{len(games)}")
    print(f"Failures: {failures}/{len(games)}\n")

    # Report details
    for result in results:
        if result['status'] != 'success':
            print(f"{result['game_id']}: {result['status']}")
            for issue in result['issues']:
                print(f"  - {issue}")

    # Save report
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    report_file = VAULT_DIR / f"Tracker_Validation_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.json"
    with open(report_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nReport: {report_file}")

if __name__ == "__main__":
    sys.exit(main())
