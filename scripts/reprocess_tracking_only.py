#!/usr/bin/env python3
"""
reprocess_tracking_only.py — Fast reprocessing: tracking only, no features.

Adds jersey_number + player_name to existing games without memory bloat.
Skips expensive feature regeneration.

Usage:
    python scripts/reprocess_tracking_only.py --games 0022400430 0022400537
    python scripts/reprocess_tracking_only.py  # All games
"""

import sys
import argparse
import subprocess
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_DIR = Path(__file__).resolve().parent.parent
GAMES_DIR = PROJECT_DIR / "data" / "games"
VIDEOS_DIR = PROJECT_DIR / "data" / "videos" / "full_games"

def get_games_needing_reprocess():
    """Find games without jersey_number in tracking."""
    import pandas as pd

    result = []
    for game_dir in sorted(GAMES_DIR.iterdir()):
        if not game_dir.is_dir():
            continue
        tracking_file = game_dir / "tracking_data.csv"
        if not tracking_file.exists():
            continue

        try:
            df = pd.read_csv(tracking_file, nrows=100)
            has_jersey = "jersey_number" in df.columns
            if has_jersey:
                full_df = pd.read_csv(tracking_file)
                filled = full_df["jersey_number"].notna().sum() / len(full_df) * 100
                if filled > 50:
                    continue  # Already has jersey data
        except:
            pass

        result.append(game_dir.name)

    return result

def reprocess_game(game_id: str, frames: int = 9000) -> bool:
    """Run run_clip.py to reprocess tracking only (skip features)."""
    video_file = VIDEOS_DIR / f"{game_id}.mp4"

    if not video_file.exists():
        print(f"  SKIP: No video {video_file.name}")
        return False

    game_dir = GAMES_DIR / game_id
    game_dir.mkdir(parents=True, exist_ok=True)

    # Call run_clip.py with --skip-features (tracking only, no memory bloat)
    cmd = [
        sys.executable,
        str(PROJECT_DIR / "scripts" / "run_clip.py"),
        "--video", str(video_file),
        "--data-dir", str(game_dir),
        "--frames", str(frames),
        "--start-frame", "0",
        "--no-show",
        "--skip-features",  # KEY: Skip expensive feature engineering
        "--game-id", game_id,
    ]

    print(f"  Running: {game_id} ({frames} frames)...")
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=600, text=True)
        if result.returncode == 0:
            print(f"    ✓ Tracking complete")
            return True
        else:
            print(f"    ✗ Exit {result.returncode}")
            if result.stderr:
                print(f"      {result.stderr[:100]}")
            return False
    except subprocess.TimeoutExpired:
        print(f"    ✗ Timeout")
        return False
    except Exception as e:
        print(f"    ✗ Error: {str(e)[:100]}")
        return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", nargs="+", help="Specific games to process")
    parser.add_argument("--frames", type=int, default=9000, help="Frames per game")
    parser.add_argument("--count", type=int, help="Limit number of games")
    args = parser.parse_args()

    if args.games:
        games = args.games
    else:
        games = get_games_needing_reprocess()

    if args.count:
        games = games[:args.count]

    if not games:
        print("No games need reprocessing!")
        return 0

    print(f"\n=== TRACKING-ONLY REPROCESSING ({len(games)} games) ===\n")
    print(f"Frames per game: {args.frames} (~{args.frames/900:.1f} min @ 30fps)")
    print(f"Est. time: ~{len(games) * args.frames / 900 / 60:.0f} minutes\n")

    done = 0
    failed = 0

    for i, game_id in enumerate(games, 1):
        print(f"[{i}/{len(games)}] {game_id}")
        if reprocess_game(game_id, args.frames):
            done += 1
        else:
            failed += 1

    print(f"\n=== SUMMARY ===")
    print(f"Completed: {done}/{len(games)}")
    if failed > 0:
        print(f"Failed: {failed}")

    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
