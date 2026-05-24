"""fetch_player_tracking.py — pull per-player season-level tracking stats.

leaguedashptstats per (season, PtMeasureType) gives one season-aggregate row
per player for: Drives, Passing, CatchShoot, PullUpShot, Defense, Possessions,
Touches, etc. We pull Drives + Passing + CatchShoot for 4 seasons (2021-22
through 2024-25) and write data/player_tracking.parquet keyed by
(player_id, season).

prop_pergame consumes this via a PRIOR-SEASON lookup: for a 2024-25 game,
features come from 2023-24 tracking — strictly point-in-time at season start,
no leak. Rookies (no prior season) get neutral defaults.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.data import nba_api_headers_patch  # noqa: F401, E402

_OUT_PATH = os.path.join(PROJECT_DIR, "data", "player_tracking.parquet")
_CACHE_DIR = os.path.join(PROJECT_DIR, "data", "nba")

_DEFAULT_SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25"]
_MEASURES = ["Drives", "Passing", "CatchShoot"]


def fetch_one(season: str, measure: str) -> list:
    """Returns list of player-row dicts for one (season, measure)."""
    from nba_api.stats.endpoints import leaguedashptstats
    cache_path = os.path.join(
        _CACHE_DIR, f"player_tracking_{measure}_{season}.json"
    )
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f)
    try:
        df = leaguedashptstats.LeagueDashPtStats(
            season=season, season_type_all_star="Regular Season",
            pt_measure_type=measure, player_or_team="Player",
            per_mode_simple="PerGame",
        ).get_data_frames()[0]
    except Exception as e:
        print(f"  [warn] {measure}/{season}: {e}")
        return []
    rows = []
    for _, r in df.iterrows():
        d = {k.lower(): v for k, v in r.to_dict().items()}
        d["_season"] = season
        d["_measure"] = measure
        rows.append(d)
    with open(cache_path, "w") as f:
        json.dump(rows, f, default=str)
    print(f"  wrote {len(rows)} rows -> {os.path.basename(cache_path)}")
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="+", default=_DEFAULT_SEASONS)
    args = ap.parse_args()

    all_rows: dict = {}
    for season in args.seasons:
        for measure in _MEASURES:
            time.sleep(0.5)
            rows = fetch_one(season, measure)
            for r in rows:
                pid = r.get("player_id")
                if pid is None:
                    continue
                key = (int(pid), season)
                merged = all_rows.setdefault(key, {
                    "player_id": int(pid), "season": season,
                })
                # Take a curated subset of useful columns per measure type.
                if measure == "Drives":
                    for c in ("drives", "drive_pts", "drive_fg_pct",
                              "drive_passes", "drive_ast", "drive_tov_pct"):
                        merged[f"trk_drv_{c.replace('drive_','').replace('drives','count')}"] = float(r.get(c, 0.0) or 0.0)
                elif measure == "Passing":
                    for c in ("passes_made", "passes_received",
                              "potential_ast", "ast_points_created",
                              "secondary_ast", "ft_ast"):
                        merged[f"trk_pas_{c}"] = float(r.get(c, 0.0) or 0.0)
                elif measure == "CatchShoot":
                    for c in ("catch_shoot_fga", "catch_shoot_fg_pct",
                              "catch_shoot_efg_pct", "catch_shoot_pts"):
                        merged[f"trk_cs_{c.replace('catch_shoot_','')}"] = float(r.get(c, 0.0) or 0.0)
        print(f"[tracking {season}] merged: {sum(1 for k in all_rows if k[1]==season)} players")

    import pandas as pd
    df = pd.DataFrame(list(all_rows.values()))
    if df.empty:
        print("[fail] no rows collected")
        return
    df.to_parquet(_OUT_PATH, index=False)
    print(f"\n[done] {len(df)} (player, season) rows -> {_OUT_PATH}")
    print(f"        cols: {list(df.columns)}")


if __name__ == "__main__":
    main()
