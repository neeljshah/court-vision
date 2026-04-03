"""
batch_reprocess.py — Reprocess all games with stale tracking data.

Runs full_game_pipeline.py on each game sequentially with:
  - --max-frames 30000 (cap at ~50 min of gameplay)
  - --no-enrich --no-predictions (data-only, max speed)
  - --force --process-only (reprocess existing videos)

Validates output after each game and logs results.

Usage:
    python scripts/batch_reprocess.py
    python scripts/batch_reprocess.py --max-frames 15000   # faster, less data
    python scripts/batch_reprocess.py --game-ids 0022400430 0022400537
"""

import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON = sys.executable
GAMES_DIR = os.path.join(PROJECT_DIR, "data", "games")
VIDEOS_DIR = os.path.join(PROJECT_DIR, "data", "videos", "full_games")
LOG_PATH = os.path.join(PROJECT_DIR, "data", "batch_reprocess.log")

# Games to skip (bad video or already good)
SKIP_GAMES = {"0022401175"}  # bad video (not broadcast)


def needs_reprocess(game_id: str) -> bool:
    """Check if a game needs reprocessing (missing or stale tracking data)."""
    track_path = os.path.join(GAMES_DIR, game_id, "tracking_data.csv")
    if not os.path.exists(track_path):
        return True
    try:
        with open(track_path, newline="", errors="replace") as f:
            reader = csv.DictReader(f)
            cols = reader.fieldnames or []
            if "player_name" not in cols or len(cols) < 60:
                return True
            rows = sum(1 for _ in reader)
            return rows < 1000
    except Exception:
        return True


def validate_output(game_id: str) -> dict:
    """Validate tracking output for a game."""
    result = {"game_id": game_id, "valid": False, "rows": 0, "cols": 0, "issues": []}
    track_path = os.path.join(GAMES_DIR, game_id, "tracking_data.csv")

    if not os.path.exists(track_path):
        result["issues"].append("no_tracking_csv")
        return result

    try:
        with open(track_path, newline="", errors="replace") as f:
            reader = csv.DictReader(f)
            cols = reader.fieldnames or []
            result["cols"] = len(cols)

            if "player_name" not in cols:
                result["issues"].append("no_player_name_col")
            if "frame" not in cols:
                result["issues"].append("no_frame_col")

            rows = 0
            sentinel_dd = 0
            nan_names = 0
            for row in reader:
                rows += 1
                if row.get("defender_distance") == "200.0":
                    sentinel_dd += 1
                pn = row.get("player_name", "")
                if pn in ("nan", "", "None"):
                    nan_names += 1

            result["rows"] = rows
            if rows < 1000:
                result["issues"].append(f"low_rows={rows}")
            if sentinel_dd > 0:
                result["issues"].append(f"sentinel_dd={sentinel_dd}")
            if nan_names > rows * 0.5:
                result["issues"].append(f"nan_names={nan_names}/{rows}")

    except Exception as e:
        result["issues"].append(f"read_error={e}")

    result["valid"] = len(result["issues"]) == 0
    return result


def log(msg: str):
    """Print and append to log file."""
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-frames", type=int, default=30000)
    parser.add_argument("--game-ids", nargs="*", default=None)
    args = parser.parse_args()

    # Build queue
    if args.game_ids:
        queue = args.game_ids
    else:
        queue = []
        for vf in sorted(os.listdir(VIDEOS_DIR)):
            if not vf.endswith(".mp4"):
                continue
            gid = vf[:-4]
            if gid in SKIP_GAMES:
                continue
            size_mb = os.path.getsize(os.path.join(VIDEOS_DIR, vf)) // (1024 * 1024)
            if size_mb < 50:
                continue
            if needs_reprocess(gid):
                queue.append(gid)

    log(f"=== BATCH REPROCESS START | {len(queue)} games | max_frames={args.max_frames} ===")

    results = []
    for i, gid in enumerate(queue):
        log(f"--- [{i+1}/{len(queue)}] {gid} ---")
        t0 = time.time()

        cmd = [
            PYTHON, os.path.join(PROJECT_DIR, "scripts", "full_game_pipeline.py"),
            "--game-id", gid,
            "--process-only",
            "--no-enrich",
            "--no-predictions",
            "--force",
            "--hours", "3",
            "--max-frames", str(args.max_frames),
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=7200,  # 2hr max per game
                cwd=PROJECT_DIR,
            )
            elapsed = time.time() - t0

            # Validate
            v = validate_output(gid)
            status = "PASS" if v["valid"] else "FAIL"

            log(f"    {status} | {v['rows']}r | {v['cols']}c | {elapsed/60:.1f}min | {v['issues'] or 'ok'}")

            results.append({
                "game_id": gid,
                "status": status,
                "rows": v["rows"],
                "cols": v["cols"],
                "elapsed_min": round(elapsed / 60, 1),
                "issues": v["issues"],
            })

        except subprocess.TimeoutExpired:
            elapsed = time.time() - t0
            log(f"    TIMEOUT | {elapsed/60:.1f}min")
            results.append({"game_id": gid, "status": "TIMEOUT", "elapsed_min": round(elapsed / 60, 1)})
        except Exception as e:
            log(f"    ERROR | {e}")
            results.append({"game_id": gid, "status": "ERROR", "error": str(e)})

        # Save running results
        with open(os.path.join(PROJECT_DIR, "data", "batch_reprocess_results.json"), "w") as f:
            json.dump(results, f, indent=2)

    # Summary
    passed = sum(1 for r in results if r.get("status") == "PASS")
    failed = sum(1 for r in results if r.get("status") == "FAIL")
    total_time = sum(r.get("elapsed_min", 0) for r in results)
    log(f"=== DONE | {passed} PASS | {failed} FAIL | {total_time:.0f}min total ===")


if __name__ == "__main__":
    main()
