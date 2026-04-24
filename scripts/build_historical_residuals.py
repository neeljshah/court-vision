"""
build_historical_residuals.py — Phase 14.1: Bootstrap prop_residuals.json from cached gamelogs.

For each player gamelog (2023-24, 2024-25), computes rolling 10-game averages as
"predictions" and records (pred, actual) pairs for all 7 prop stats.

Usage:
    python scripts/build_historical_residuals.py [--seasons 2023-24,2024-25] [--min-games 5]

Output:
    data/models/prop_residuals.json  — list of {player_id, player_name, game_date,
                                        stat, predicted, actual, line, season}
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_NBA_DIR    = os.path.join(PROJECT_DIR, "data", "nba")
_MODELS_DIR = os.path.join(PROJECT_DIR, "data", "models")
_RESIDUALS  = os.path.join(_MODELS_DIR, "prop_residuals.json")

STATS       = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
STAT_COLS   = {"pts": "PTS", "reb": "REB", "ast": "AST",
               "fg3m": "FG3M", "stl": "STL", "blk": "BLK", "tov": "TOV"}
ROLL_N      = 10   # rolling window for prediction


def _parse_date(s: str) -> datetime:
    for fmt in ("%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {s!r}")


def _build_player_name_map(seasons: list[str]) -> dict[int, str]:
    """Build player_id → name map from player_avgs cache files."""
    id_to_name: dict[int, str] = {}
    for season in seasons:
        path = os.path.join(_NBA_DIR, f"player_avgs_{season}.json")
        if not os.path.exists(path):
            continue
        try:
            avgs = json.load(open(path, encoding="utf-8"))
            for name, info in avgs.items():
                pid = info.get("player_id")
                if pid:
                    id_to_name[int(pid)] = name
        except Exception:
            pass
    return id_to_name


def _process_gamelog(player_id: int, player_name: str, season: str,
                     rows: list[dict], min_games: int) -> list[dict]:
    """Compute rolling-avg predictions for one player's gamelog."""
    # Sort ascending so rows[:i] is history before game i
    try:
        rows_sorted = sorted(rows, key=lambda r: _parse_date(r["GAME_DATE"]))
    except Exception:
        return []

    results = []
    for i, game in enumerate(rows_sorted):
        if i < min_games:
            continue  # not enough history

        history = rows_sorted[max(0, i - ROLL_N): i]
        for stat, col in STAT_COLS.items():
            vals = [float(h[col]) for h in history if col in h and h[col] is not None]
            if not vals:
                continue
            predicted = sum(vals) / len(vals)
            actual_raw = game.get(col)
            if actual_raw is None:
                continue
            actual = float(actual_raw)
            results.append({
                "player_id":   player_id,
                "player_name": player_name,
                "game_date":   game["GAME_DATE"],
                "season":      season,
                "stat":        stat,
                "predicted":   round(predicted, 4),
                "actual":      actual,
                "line":        round(predicted, 4),  # no book line in historical logs
            })
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap prop_residuals.json from gamelog cache")
    parser.add_argument("--seasons", default="2023-24,2024-25",
                        help="Comma-separated seasons to include")
    parser.add_argument("--min-games", type=int, default=5,
                        help="Minimum prior games required to record a prediction")
    parser.add_argument("--append", action="store_true",
                        help="Append to existing prop_residuals.json instead of overwriting")
    args = parser.parse_args()

    seasons = [s.strip() for s in args.seasons.split(",")]
    print(f"Building historical residuals for seasons: {seasons}")

    id_to_name = _build_player_name_map(seasons)
    print(f"  Player name map: {len(id_to_name)} players")

    # Collect gamelog files
    gamelog_pattern = re.compile(r"gamelog_(\d+)_(\d{4}-\d{2})\.json$")
    all_files: list[tuple[int, str, str]] = []  # (player_id, season, path)
    for fname in os.listdir(_NBA_DIR):
        m = gamelog_pattern.match(fname)
        if not m:
            continue
        pid, season = int(m.group(1)), m.group(2)
        if season not in seasons:
            continue
        all_files.append((pid, season, os.path.join(_NBA_DIR, fname)))

    print(f"  Gamelog files to process: {len(all_files)}")

    # Load existing residuals if appending
    existing: list[dict] = []
    existing_keys: set[tuple] = set()
    if args.append and os.path.exists(_RESIDUALS):
        try:
            existing = json.load(open(_RESIDUALS, encoding="utf-8"))
            existing_keys = {
                (r["player_id"], r.get("season", ""), r["game_date"], r["stat"])
                for r in existing
            }
            print(f"  Loaded {len(existing)} existing residuals")
        except Exception as e:
            print(f"  Warning: could not load existing residuals: {e}")

    new_records: list[dict] = []
    skipped = 0
    for player_id, season, path in all_files:
        try:
            rows = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not rows:
            continue

        player_name = id_to_name.get(player_id, f"player_{player_id}")
        records = _process_gamelog(player_id, player_name, season, rows, args.min_games)

        for r in records:
            key = (r["player_id"], r["season"], r["game_date"], r["stat"])
            if key in existing_keys:
                skipped += 1
                continue
            new_records.append(r)
            existing_keys.add(key)

    all_records = existing + new_records
    os.makedirs(_MODELS_DIR, exist_ok=True)
    with open(_RESIDUALS, "w", encoding="utf-8") as f:
        json.dump(all_records, f)

    # Summary by stat
    stat_counts: dict[str, int] = defaultdict(int)
    for r in all_records:
        stat_counts[r["stat"]] += 1

    print(f"\nResiduals written: {len(all_records)} total ({len(new_records)} new, {skipped} deduped)")
    print("\nRows per stat:")
    for stat in STATS:
        n = stat_counts.get(stat, 0)
        ok = "✓" if n >= 10_000 else "⚠ (need 10K+)"
        print(f"  {stat:6s}: {n:>7,d}  {ok}")
    print(f"\nOutput: {_RESIDUALS}")


if __name__ == "__main__":
    main()
