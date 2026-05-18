"""
batch_process.py -- Phase C4: Submit batch of game videos to Celery pipeline.

Scans a folder for .mp4 files, matches each to an NBA game ID via game_matcher.py,
skips already-processed games, and submits the rest to the Celery queue.

Usage:
    conda activate basketball_ai

    # Start Redis + worker first:
    #   redis-server  (or use Redis Cloud)
    #   celery -A src.pipeline.tasks worker --loglevel=info --concurrency=2

    # Submit all games in a folder:
    python scripts/batch_process.py --folder recordings/

    # Dry run (show what would be submitted without actually submitting):
    python scripts/batch_process.py --folder recordings/ --dry-run

    # Limit to N games:
    python scripts/batch_process.py --folder recordings/ --limit 10

    # Monitor at: http://localhost:5555  (Flower dashboard)
    #   celery -A src.pipeline.tasks flower

File naming convention:
    {AWAY}_{HOME}_{DATE}.mp4   e.g.  LAL_GSW_20250115.mp4
    OR any name — game_matcher.py will try to resolve via NBA API.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass

_EVENTS_DIR = os.path.join(PROJECT_DIR, "data", "events")


def _is_already_processed(game_id: str) -> bool:
    """Check if game already has output events or is in PostgreSQL."""
    events_path = os.path.join(_EVENTS_DIR, f"{game_id}_events.json")
    if os.path.exists(events_path):
        return True
    try:
        from src.data.db import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM games WHERE game_id = %s LIMIT 1", (game_id,))
                return cur.fetchone() is not None
    except Exception:
        return False


def _match_game_id(video_path: str, season: str) -> str | None:
    """
    Resolve video filename to NBA game ID.
    Tries filename convention {AWAY}_{HOME}_{DATE}.mp4 first,
    then falls back to game_matcher.match_by_teams_and_date().
    """
    name = os.path.splitext(os.path.basename(video_path))[0]
    parts = name.split("_")

    # Convention: AWAY_HOME_YYYYMMDD
    if len(parts) >= 3 and parts[2].isdigit() and len(parts[2]) == 8:
        away_team = parts[0].upper()
        home_team = parts[1].upper()
        date_str  = f"{parts[2][:4]}-{parts[2][4:6]}-{parts[2][6:8]}"
        try:
            from src.data.game_matcher import match_game
            game_id = match_game(home_team, away_team, date_str, season)
            if game_id:
                return game_id
        except Exception:
            pass

    # Fallback: filename IS the game_id
    if name.startswith("00") and len(name) == 10 and name.isdigit():
        return name

    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase C4 -- Batch game processor")
    parser.add_argument("--folder",  required=True, help="Folder containing .mp4 files")
    parser.add_argument("--season",  default="2024-25", help="NBA season (e.g. 2024-25)")
    parser.add_argument("--limit",   type=int, default=0, help="Max games to submit (0=all)")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without submitting")
    parser.add_argument("--workers", type=int, default=2, help="Celery worker concurrency hint")
    args = parser.parse_args()

    folder = os.path.abspath(args.folder)
    if not os.path.isdir(folder):
        print(f"[batch] ERROR: folder not found: {folder}")
        sys.exit(1)

    # Find all .mp4 files
    videos = sorted(
        p for p in (os.path.join(folder, f) for f in os.listdir(folder))
        if p.lower().endswith(".mp4")
    )
    if not videos:
        print(f"[batch] No .mp4 files found in {folder}")
        sys.exit(0)

    print(f"[batch] Found {len(videos)} .mp4 files in {folder}")

    # Resolve game IDs
    to_submit = []
    skipped_no_id  = 0
    skipped_done   = 0

    for vpath in videos:
        game_id = _match_game_id(vpath, args.season)
        if not game_id:
            print(f"  [SKIP no_id] {os.path.basename(vpath)}")
            skipped_no_id += 1
            continue

        if _is_already_processed(game_id):
            print(f"  [SKIP done]  {os.path.basename(vpath)}  ({game_id})")
            skipped_done += 1
            continue

        to_submit.append((vpath, game_id))
        if args.limit and len(to_submit) >= args.limit:
            break

    print(f"\n[batch] Skipped: {skipped_done} already done, {skipped_no_id} no game ID")
    print(f"[batch] To submit: {len(to_submit)} games")

    if not to_submit:
        print("[batch] Nothing to do.")
        return

    if args.dry_run:
        print("\n[batch] DRY RUN -- would submit:")
        for vpath, gid in to_submit:
            print(f"  {os.path.basename(vpath)}  ->  {gid}")
        return

    # Submit to Celery
    try:
        from src.pipeline.tasks import process_game_chain
    except ImportError:
        print("[batch] ERROR: Celery not installed. Run: pip install celery[redis]")
        sys.exit(1)

    submitted = []
    for vpath, game_id in to_submit:
        try:
            result = process_game_chain(vpath, game_id)
            submitted.append((game_id, result.id))
            print(f"  [QUEUED] {os.path.basename(vpath)}  ({game_id})  task={result.id}")
        except Exception as e:
            print(f"  [ERR]    {os.path.basename(vpath)}  ({game_id}): {e}")
        time.sleep(0.1)  # brief pause between submissions

    print(f"\n[batch] Submitted {len(submitted)} games to Celery queue")
    print("[batch] Monitor progress at http://localhost:5555 (Flower)")
    print(f"[batch] Start {args.workers} workers with:")
    print(f"        celery -A src.pipeline.tasks worker --concurrency={args.workers} --loglevel=info")


if __name__ == "__main__":
    main()
