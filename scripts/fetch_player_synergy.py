"""fetch_player_synergy.py — per-PLAYER synergy play-type frequencies (loop 5 cycle 1).

The audit (cycle 1 A1) showed all 9 pt_*_freq features are zero-variance because
data/playtypes.parquet is missing. The existing fetch_missing_nba_data.py fetches
TEAM-level synergy; prop_pergame needs PLAYER-level (one row per player_id ×
season × play_type).

Pulls SynergyPlayTypes(PlayerOrTeam='P') for each (play_type, season) and writes
data/playtypes.parquet keyed by (player_id, season, play_type).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import List

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.data import nba_api_headers_patch  # noqa: F401, E402

_OUT_PATH = os.path.join(PROJECT_DIR, "data", "playtypes.parquet")
_CACHE_DIR = os.path.join(PROJECT_DIR, "data", "nba")

# Same 9 play types the model reads via feature_columns() (_PLAY_TYPES in
# prop_pergame.py). NOT 10 — Putbacks is team-only.
_PLAY_TYPES = ["Isolation", "PRBallHandler", "PRRollMan", "Postup",
               "Spotup", "Handoff", "Transition", "Cut", "OffScreen"]

_DEFAULT_SEASONS = ["2022-23", "2023-24", "2024-25", "2025-26"]


def fetch(season: str, play_type: str) -> list:
    """Pull per-player synergy for one (season, play_type). Returns rows."""
    from nba_api.stats.endpoints import synergyplaytypes
    cache_path = os.path.join(
        _CACHE_DIR, f"synergy_player_{play_type}_{season}.json"
    )
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f)
    try:
        df = synergyplaytypes.SynergyPlayTypes(
            season=season, season_type_all_star="Regular Season",
            play_type_nullable=play_type, type_grouping_nullable="offensive",
            player_or_team_abbreviation="P",
            per_mode_simple="PerGame",
        ).get_data_frames()[0]
    except Exception as e:
        print(f"  [warn] synergy_player/{play_type}/{season}: {e}")
        return []
    rows = []
    for _, r in df.iterrows():
        d = {k.lower(): v for k, v in r.to_dict().items()}
        d["play_type"] = play_type
        d["season"] = season
        rows.append(d)
    with open(cache_path, "w") as f:
        json.dump(rows, f)
    print(f"  wrote {len(rows)} rows -> synergy_player_{play_type}_{season}.json")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="+", default=_DEFAULT_SEASONS)
    ap.add_argument("--play-types", nargs="+", default=_PLAY_TYPES,
                    help="Restrict scrape to specific play types (default: all 9).")
    args = ap.parse_args()

    all_rows: list = []
    for season in args.seasons:
        for play_type in args.play_types:
            time.sleep(0.5)
            all_rows.extend(fetch(season, play_type))
        print(f"[synergy_player {season}] cumulative rows={len(all_rows)}")

    # Persist as parquet keyed for prop_pergame.build_playtypes consumption.
    # The reader expects columns: player_id, season, play_type, freq_pct.
    # Also retain ppp (points per possession) so feature builders can read
    # per-player PPP directly from parquet without re-loading the JSON.
    import pandas as pd
    out_rows = []
    for r in all_rows:
        pid = r.get("player_id")
        # Player synergy returns "poss_pct" (share of player's possessions
        # on this play type); team synergy returns "freq_pct". Accept either.
        freq = r.get("poss_pct") or r.get("freq_pct") or r.get("freq")
        if pid is None or freq is None:
            continue
        ppp_val = r.get("ppp")
        out_rows.append({
            "player_id": int(pid),
            "season": str(r["season"]),
            "play_type": str(r["play_type"]),
            "freq_pct": float(freq),
            "ppp": float(ppp_val) if ppp_val is not None else 0.0,
        })
    df = pd.DataFrame(out_rows)
    df.to_parquet(_OUT_PATH, index=False)
    print(f"\n[done] {len(df)} (player, season, play_type) rows -> {_OUT_PATH}")
    print(f"        unique players: {df['player_id'].nunique()}, "
          f"seasons: {sorted(df['season'].unique())}")


if __name__ == "__main__":
    main()
