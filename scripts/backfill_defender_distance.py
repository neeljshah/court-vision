"""
backfill_defender_distance.py — Recompute defender_distance for existing shot_log.csv files.

For shots where defender_distance is 200.0 or blank (sentinel), finds the nearest opponent
at the shot frame in tracking_data.csv and backfills the corrected distance.

Usage:
    python scripts/backfill_defender_distance.py [--game GAME_ID ...]

If no --game flag is given, all games under data/tracking/ are processed.
"""

import argparse
import csv
import math
import sys

# Force UTF-8 stdout on Windows to handle game IDs with Unicode characters
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import os
import shutil
from collections import defaultdict

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "tracking")
SENTINEL = "200.0"


def _is_sentinel(val: str) -> bool:
    v = val.strip()
    return v == "" or v == SENTINEL or v == "200"


def _load_tracking_by_frame(tracking_csv: str) -> dict:
    """Return dict {frame_int -> [{'team', 'x', 'y'}, ...]} from tracking_data.csv."""
    by_frame = defaultdict(list)
    if not os.path.exists(tracking_csv):
        return by_frame
    with open(tracking_csv, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            team = row.get("team", "").strip()
            if team == "referee":
                continue
            try:
                frame = int(row["frame"])
                x = float(row["x_position"])
                y = float(row["y_position"])
            except (ValueError, KeyError):
                continue
            by_frame[frame].append({"team": team, "x": x, "y": y})
    return by_frame


def _nearest_opponent_dist(shooter_team: str, sx: float, sy: float,
                            frame_players: list) -> float | None:
    """Distance from (sx, sy) to nearest player not on shooter_team."""
    opp = [p for p in frame_players if p["team"] != shooter_team]
    if not opp:
        # Last resort: any other player regardless of team
        opp = [p for p in frame_players if not (p["x"] == sx and p["y"] == sy)]
    if not opp:
        return None
    return min(math.hypot(sx - p["x"], sy - p["y"]) for p in opp)


def backfill_game(game_id: str) -> dict:
    """Backfill shot_log.csv for one game. Returns stats dict."""
    game_dir = os.path.join(DATA_DIR, game_id)
    shot_csv = os.path.join(game_dir, "shot_log.csv")
    tracking_csv = os.path.join(game_dir, "tracking_data.csv")

    if not os.path.exists(shot_csv):
        print(f"  {game_id}: no shot_log.csv - skipped")
        return {}

    by_frame = _load_tracking_by_frame(tracking_csv)

    with open(shot_csv, newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print(f"  {game_id}: empty shot_log.csv - skipped")
        return {}

    fieldnames = list(rows[0].keys())
    # Ensure columns exist
    if "defender_distance" not in fieldnames:
        print(f"  {game_id}: no defender_distance column - skipped")
        return {}

    stats = {"total": len(rows), "sentinel_before": 0, "filled": 0, "still_missing": 0}

    for row in rows:
        dd = row.get("defender_distance", "")
        if not _is_sentinel(dd):
            continue
        stats["sentinel_before"] += 1

        try:
            frame = int(row["frame"])
            sx = float(row["x_position"])
            sy = float(row["y_position"])
        except (ValueError, KeyError):
            stats["still_missing"] += 1
            continue

        shooter_team = row.get("team", "").strip()
        frame_players = by_frame.get(frame, [])

        dist = _nearest_opponent_dist(shooter_team, sx, sy, frame_players)
        if dist is not None:
            row["defender_distance"] = str(round(dist, 1))
            # Recompute norm: need map_w — approximate from max x in tracking data
            # Use 1294 as default (standard court map width observed in tracking data)
            map_w = 1294
            row["defender_dist_norm"] = str(round(dist / map_w, 4))
            stats["filled"] += 1
        else:
            # Truly no opponents in tracking data for this frame — leave blank
            row["defender_distance"] = ""
            row["defender_dist_norm"] = ""
            stats["still_missing"] += 1

    # Write back (backup original first)
    backup_path = shot_csv + ".bak"
    if not os.path.exists(backup_path):
        shutil.copy2(shot_csv, backup_path)

    with open(shot_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", nargs="*", help="Game IDs to process (default: all)")
    args = parser.parse_args()

    if args.game:
        game_ids = args.game
    else:
        game_ids = sorted(
            d for d in os.listdir(DATA_DIR)
            if os.path.isdir(os.path.join(DATA_DIR, d))
        )

    print(f"Processing {len(game_ids)} game(s)...\n")
    total_sentinel = total_filled = total_missing = 0

    for gid in game_ids:
        stats = backfill_game(gid)
        if not stats:
            continue
        s = stats["sentinel_before"]
        f = stats["filled"]
        m = stats["still_missing"]
        t = stats["total"]
        sentinel_pct_before = round(100 * s / t) if t else 0
        remaining_pct = round(100 * m / t) if t else 0
        print(f"  {gid}: {t} shots | sentinel before={s} ({sentinel_pct_before}%) "
              f"| filled={f} | still missing={m} ({remaining_pct}%)")
        total_sentinel += s
        total_filled += f
        total_missing += m

    print(f"\nTotal: {total_sentinel} sentinel → {total_filled} filled, "
          f"{total_missing} still NULL (no tracking data for frame)")


if __name__ == "__main__":
    main()
