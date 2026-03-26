"""
rebuild_shot_dashboard_combined.py -- Rebuild combined shot_dashboard JSONs from individual files.

Use when the combined files are corrupt or incomplete due to a race condition.
Reads all shot_dashboard_{player_id}_{season}.json individual files and merges
them into shot_dashboard_all_{season}.json.
"""
from __future__ import annotations

import glob
import json
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_SEASONS = ["2022-23", "2023-24", "2024-25"]


def rebuild_season(season: str) -> int:
    pattern = os.path.join(_NBA_CACHE, f"shot_dashboard_*_{season}.json")
    # Exclude the combined file itself
    combined_path = os.path.join(_NBA_CACHE, f"shot_dashboard_all_{season}.json")
    files = [f for f in glob.glob(pattern) if "shot_dashboard_all_" not in f]

    combined: dict = {}
    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data.get("player_id"):
                pid_str = str(int(data["player_id"]))
                combined[pid_str] = data
        except Exception as e:
            print(f"  skip {os.path.basename(path)}: {e}")

    with open(combined_path, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2)

    populated = sum(1 for v in combined.values() if v.get("contested_pct", 0) > 0)
    print(f"  {season}: {populated}/{len(combined)} populated → {os.path.basename(combined_path)}")
    return len(combined)


def main() -> None:
    total = 0
    for season in _SEASONS:
        total += rebuild_season(season)
    print(f"\nDone. {total} total player-season entries across all combined files.")


if __name__ == "__main__":
    main()
