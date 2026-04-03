#!/usr/bin/env python3
"""
reprocess_20_games.py — Reprocess 20 games with full data (tracking + shots + features).

One game per process = guaranteed memory cleanup.
Memory-safe: skips advanced features on large games automatically.
Time: ~5 min per game = 100 min for 20 games.

Usage:
    # Test on 1 game first
    python scripts/reprocess_20_games.py --test

    # Full batch: 20 games
    python scripts/reprocess_20_games.py

    # Specific games only
    python scripts/reprocess_20_games.py --games 0022400430 0022400537 0022400909
"""

import sys
import subprocess
from pathlib import Path
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_DIR = Path(__file__).resolve().parent.parent
GAMES_DIR = PROJECT_DIR / "data" / "games"
VIDEOS_DIR = PROJECT_DIR / "data" / "videos" / "full_games"

# Top 20 games to reprocess (largest + oldest)
DEFAULT_GAMES = [
    "0022400430",   # 194K rows, old code
    "0022400537",   # 280K rows, old code
    "0022400909",   # 362K rows, old code
    "0022401123",   # 11K rows, needs reprocess
    "0022401183",   # 77K rows, needs reprocess
    "0022400625",   # 114K rows, partial
    "0022400687",   # 8K rows, partial
    "0022401185",   # 23K rows, partial
    "0022401190",   # needs reprocess
    "0022401196",   # needs reprocess
    "0022401198",   # needs reprocess
    "0022400015",   # old code
    "0022400021",   # old code
    "0022400042",   # old code
    "0022400058",   # old code
    "0022400067",   # old code
    "0022400072",   # old code
    "0022400083",   # old code
    "0022400112",   # old code
    "0022400242",   # old code
]

def reprocess_game(game_id: str, skip_features: bool = False) -> bool:
    """Reprocess single game (full: tracking + shots + features)."""
    video_file = VIDEOS_DIR / f"{game_id}.mp4"

    if not video_file.exists():
        print(f"  SKIP: Video not found")
        return False

    game_dir = GAMES_DIR / game_id
    game_dir.mkdir(parents=True, exist_ok=True)

    # Pipeline: tracking (with jersey OCR) + shot detection + optional features
    # One game per process = guaranteed memory cleanup
    cmd = [
        sys.executable,
        str(PROJECT_DIR / "scripts" / "run_clip.py"),
        "--video", str(video_file),
        "--data-dir", str(game_dir),
        "--frames", "9000",
        "--start-frame", "0",
        "--no-show",
        "--game-id", game_id,
    ]

    if skip_features:
        cmd.append("--skip-features")

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=600, text=True)
        if result.returncode == 0:
            mode = "tracking+shots" if skip_features else "full pipeline"
            time_est = "2-3 min" if skip_features else "5 min"
            print(f"  SUCCESS ({time_est}, {mode})")
            return True
        else:
            print(f"  FAILED (exit {result.returncode})")
            if "memory" in result.stderr.lower() or "oom" in result.stderr.lower():
                print(f"    Memory error — try --skip-features")
            return False
    except subprocess.TimeoutExpired:
        print(f"  FAILED (timeout >600s)")
        return False
    except Exception as e:
        print(f"  FAILED ({str(e)[:80]})")
        return False

def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Test on 1 game only")
    parser.add_argument("--games", nargs="+", help="Specific games to process")
    parser.add_argument("--count", type=int, help="Limit number of games")
    parser.add_argument("--skip-features", action="store_true", help="Skip feature engineering (faster, <500MB RAM)")
    args = parser.parse_args()

    if args.test:
        games = ["0022400430"]  # Largest game, good test
    elif args.games:
        games = args.games
    else:
        games = DEFAULT_GAMES

    if args.count:
        games = games[:args.count]

    print("\n" + "=" * 70)
    print("REPROCESS 20 GAMES — Full Pipeline (Tracking + Shot + Features)")
    print("=" * 70)
    print(f"Games: {len(games)}")
    print(f"Time: ~{len(games) * 5} minutes")
    print(f"Memory: <1GB per game (separate processes)")
    print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    done = []
    failed = []

    for i, game_id in enumerate(games, 1):
        print(f"[{i:2d}/{len(games)}] {game_id}...", end=" ", flush=True)
        if reprocess_game(game_id, skip_features=args.skip_features):
            done.append(game_id)
        else:
            failed.append(game_id)

    print("\n" + "=" * 70)
    print(f"COMPLETED: {len(done)}/{len(games)}")
    if failed:
        print(f"FAILED: {len(failed)}")
        print(f"  Games: {', '.join(failed)}")
    print(f"End: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    return 0 if len(failed) == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
