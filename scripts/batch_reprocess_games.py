#!/usr/bin/env python3
"""
batch_reprocess_games.py — Efficiently reprocess all games with latest tracking pipeline.

Handles:
- Jersey number extraction via OCR
- Player name resolution via jersey_name_map.json
- Spatial feature recomputation
- Shot detection regeneration
- Batch processing with progress tracking

Usage:
    # Quick test: 5 min per game
    python scripts/batch_reprocess_games.py --frames 9000 --games 0022400430 0022400537

    # Full batch: all games with 10 min footage per game
    python scripts/batch_reprocess_games.py --frames 18000

    # Dry run: show what would happen
    python scripts/batch_reprocess_games.py --dry-run --count 3
"""

import json
import subprocess
import sys
import argparse
from pathlib import Path
from datetime import datetime
import time

# Force UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_DIR = Path(__file__).resolve().parent.parent
GAMES_DIR = PROJECT_DIR / "data" / "games"
VIDEOS_DIR = PROJECT_DIR / "data" / "videos" / "full_games"
VAULT_DIR = PROJECT_DIR / "vault" / "Sessions"

def get_available_videos():
    """List all available game videos."""
    if not VIDEOS_DIR.exists():
        return []
    return sorted([f.stem for f in VIDEOS_DIR.glob("*.mp4")])

def get_processed_games():
    """List games that have been fully processed."""
    result = []
    for game_dir in sorted(GAMES_DIR.iterdir()):
        if game_dir.is_dir():
            has_all = all([
                (game_dir / "tracking_data.csv").exists(),
                (game_dir / "shot_log.csv").exists(),
                (game_dir / "possessions.csv").exists(),
                (game_dir / "features.csv").exists(),
            ])
            if has_all:
                result.append(game_dir.name)
    return result

def needs_reprocess(game_id: str) -> bool:
    """Check if game needs reprocessing (no jersey_number or player_name)."""
    game_dir = GAMES_DIR / game_id
    tracking_file = game_dir / "tracking_data.csv"

    if not tracking_file.exists():
        return True

    try:
        import pandas as pd
        df = pd.read_csv(tracking_file, nrows=100)

        has_jersey = "jersey_number" in df.columns and df["jersey_number"].notna().sum() > 0
        has_names = "player_name" in df.columns and df["player_name"].notna().sum() > 0

        # Needs reprocess if missing jersey OR missing player names
        return not (has_jersey and has_names)

    except:
        return True

def reprocess_game(game_id: str, frames: int = 18000, dry_run: bool = False) -> bool:
    """Reprocess single game using run_phase_g.py."""
    cmd = [
        sys.executable,
        "scripts/run_phase_g.py",
        "--game-ids", game_id,
        "--frames", str(frames),
        "--reprocess",
    ]

    if dry_run:
        print(f"  DRY RUN: Would run: {' '.join(cmd)}")
        return True

    print(f"  Running: {' '.join(cmd[:4])}...")
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=600, text=True)
        if result.returncode == 0:
            return True
        else:
            print(f"    ERROR (exit {result.returncode}): {result.stderr[:200]}")
            return False
    except subprocess.TimeoutExpired:
        print(f"    ERROR: Timeout (>600s)")
        return False
    except Exception as e:
        print(f"    ERROR: {str(e)[:100]}")
        return False

def log_session(games_done: list, games_failed: list):
    """Log reprocessing results to vault."""
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    log_file = VAULT_DIR / f"Reprocessing_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.md"

    content = f"""# Batch Reprocessing Session {datetime.now().isoformat()}

## Summary
- Games completed: {len(games_done)}
- Games failed: {len(games_failed)}
- Total: {len(games_done) + len(games_failed)}

## Completed
```
{chr(10).join(games_done)}
```

## Failed
```
{chr(10).join(games_failed) if games_failed else 'None'}
```

## Next Steps
- Validate output with `batch_validate_games.py`
- Audit data quality on 5 games
- Expand batch if all good
"""

    log_file.write_text(content)
    print(f"\nLogged to: {log_file}")

def main():
    parser = argparse.ArgumentParser(description="Batch reprocess NBA games")
    parser.add_argument("--games", nargs="+", help="Specific games to reprocess")
    parser.add_argument("--count", type=int, help="Limit number of games")
    parser.add_argument("--frames", type=int, default=18000, help="Frames per game (18000 = 10 min @ 30fps)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without executing")
    args = parser.parse_args()

    # Determine which games to process
    if args.games:
        games_todo = args.games
    else:
        all_games = get_processed_games()
        games_todo = [g for g in all_games if needs_reprocess(g)]

    if args.count:
        games_todo = games_todo[:args.count]

    if not games_todo:
        print("No games need reprocessing!")
        return 0

    print(f"=== BATCH REPROCESSING ({len(games_todo)} games) ===\n")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'EXECUTE'}")
    print(f"Frames per game: {args.frames} (~{args.frames/900:.1f} min @ 30fps)")
    print(f"Est. time: ~{len(games_todo) * args.frames / 900 / 60:.0f} hours\n")

    games_done = []
    games_failed = []

    for i, game_id in enumerate(games_todo, 1):
        print(f"[{i}/{len(games_todo)}] {game_id}...")
        if reprocess_game(game_id, frames=args.frames, dry_run=args.dry_run):
            games_done.append(game_id)
            print(f"  SUCCESS")
        else:
            games_failed.append(game_id)
            print(f"  FAILED (skip to next)")

    print(f"\n=== SUMMARY ===")
    print(f"Completed: {len(games_done)}/{len(games_todo)}")
    if games_failed:
        print(f"Failed: {games_failed}")

    if not args.dry_run:
        log_session(games_done, games_failed)

    return 0 if len(games_failed) == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
