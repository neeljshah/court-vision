"""
build_trajectory_features.py — Pre-compute player-trajectory features for a season.

Usage:
    python scripts/build_trajectory_features.py 2024-25

Saves: data/cache/trajectory_features_{season}.parquet
       (falls back to data/cache/trajectory_features_{season}.json.gz if parquet unavailable)

Prints summary: % hot, % cold, momentum_l10 distribution.
"""
from __future__ import annotations

import gzip
import json
import os
import sys
import time
from typing import List

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.features.player_trajectory import get_trajectory_features, _load_gamelog  # noqa: E402

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_OUT_DIR = os.path.join(PROJECT_DIR, "data", "cache")


def _all_player_ids(season: str) -> List[int]:
    """Find all player IDs with a gamelog_full file for this season."""
    import glob
    pattern = os.path.join(_NBA_CACHE, f"gamelog_full_*_{season}.json")
    files = glob.glob(pattern)
    ids = []
    for f in files:
        base = os.path.basename(f)
        # gamelog_full_{pid}_{season}.json
        parts = base.replace(".json", "").split("_")
        try:
            ids.append(int(parts[2]))
        except (IndexError, ValueError):
            pass
    return sorted(set(ids))


def _build_rows(player_id: int, season: str) -> List[dict]:
    """Build one feature row per game for the player."""
    parsed = _load_gamelog(player_id, season)
    if not parsed:
        return []

    rows = []
    for i, (game_date, game_row) in enumerate(parsed):
        if i < 3:  # need at least 3 prior games
            continue
        matchup = game_row.get("matchup", "")
        feats = get_trajectory_features(
            player_id=player_id,
            season=season,
            game_date=game_date.strftime("%Y-%m-%d"),
            current_matchup=matchup,
        )
        feats["player_id"] = player_id
        feats["season"] = season
        feats["game_date"] = game_date.isoformat()
        feats["game_id"] = game_row.get("game_id", "")
        rows.append(feats)
    return rows


def _save_parquet(records: List[dict], path: str) -> None:
    import pandas as pd
    df = pd.DataFrame(records)
    df.to_parquet(path, index=False, compression="snappy")


def _save_json_gz(records: List[dict], path: str) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(records, f)


def _print_summary(records: List[dict]) -> None:
    if not records:
        print("  No records generated.")
        return
    n = len(records)
    hot = sum(1 for r in records if r["hot_streak"] == 1)
    cold = sum(1 for r in records if r["cold_streak"] == 1)
    breakout = sum(1 for r in records if r["breakout_flag"] == 1)
    moms = [r["momentum_l10"] for r in records]
    moms.sort()
    p25 = moms[n // 4]
    p50 = moms[n // 2]
    p75 = moms[3 * n // 4]

    print(f"\n  Total rows:       {n:,}")
    print(f"  Hot streak:       {hot:,}  ({100*hot/n:.1f}%)")
    print(f"  Cold streak:      {cold:,}  ({100*cold/n:.1f}%)")
    print(f"  Breakout flag:    {breakout:,}  ({100*breakout/n:.1f}%)")
    print(f"  momentum_l10      p25={p25:.4f}  p50={p50:.4f}  p75={p75:.4f}")


def main(season: str = "2024-25") -> None:
    print(f"[trajectory] Building features for season {season}")
    t0 = time.time()

    player_ids = _all_player_ids(season)
    print(f"[trajectory] Found {len(player_ids)} players")

    os.makedirs(_OUT_DIR, exist_ok=True)

    all_records: List[dict] = []
    for i, pid in enumerate(player_ids):
        rows = _build_rows(pid, season)
        all_records.extend(rows)
        if (i + 1) % 100 == 0:
            elapsed = time.time() - t0
            print(f"  {i+1}/{len(player_ids)} players  |  {len(all_records):,} rows  |  {elapsed:.1f}s")

    print(f"[trajectory] Done — {len(all_records):,} total rows in {time.time()-t0:.1f}s")
    _print_summary(all_records)

    # Save
    parquet_path = os.path.join(_OUT_DIR, f"trajectory_features_{season}.parquet")
    json_path = os.path.join(_OUT_DIR, f"trajectory_features_{season}.json.gz")

    saved_path = None
    try:
        _save_parquet(all_records, parquet_path)
        saved_path = parquet_path
        print(f"\n  Saved parquet → {parquet_path}")
    except Exception as e:
        print(f"  Parquet unavailable ({e}), falling back to JSON.gz")
        _save_json_gz(all_records, json_path)
        saved_path = json_path
        print(f"  Saved JSON.gz → {json_path}")

    size_kb = os.path.getsize(saved_path) // 1024
    print(f"  File size: {size_kb:,} KB")


if __name__ == "__main__":
    _season = sys.argv[1] if len(sys.argv) > 1 else "2024-25"
    main(_season)
