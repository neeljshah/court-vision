"""patch_season_games_opp_adj.py — patch home_/away_off_rtg_vs_top_def in cached season_games.

Cycle-10 (loop 5) fixes the secondary leak in `_compute_opp_adjusted_rolling`:
the top-10 def team set is now picked per-game-date from each team's
expanding-window def_rtg, not from season-FINAL leaguedashteamstats. The
existing cached season_games_*.json files (v=9, patched by cycle 3) carry
the OLD leaked values for the 2 opp-adjusted features; this script rewrites
those two fields without doing the slow _fetch_team_stats / sim recompute.
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
from src.prediction.win_probability import (  # noqa: E402
    _NBA_CACHE, _SEASON_GAMES_VERSION, _compute_opp_adjusted_rolling,
)


_TEAM_ABBR_TO_ID = {
    "ATL": 1610612737, "BOS": 1610612738, "BKN": 1610612751, "CHA": 1610612766,
    "CHI": 1610612741, "CLE": 1610612739, "DAL": 1610612742, "DEN": 1610612743,
    "DET": 1610612765, "GSW": 1610612744, "HOU": 1610612745, "IND": 1610612754,
    "LAC": 1610612746, "LAL": 1610612747, "MEM": 1610612763, "MIA": 1610612748,
    "MIL": 1610612749, "MIN": 1610612750, "NOP": 1610612740, "NYK": 1610612752,
    "OKC": 1610612760, "ORL": 1610612753, "PHI": 1610612755, "PHX": 1610612756,
    "POR": 1610612757, "SAC": 1610612758, "SAS": 1610612759, "TOR": 1610612761,
    "UTA": 1610612762, "WAS": 1610612764,
}


def _fetch_gamelog(season: str):
    from nba_api.stats.endpoints import leaguegamelog
    time.sleep(0.5)
    return leaguegamelog.LeagueGameLog(
        season=season, season_type_all_star="Regular Season",
        player_or_team_abbreviation="T",
    ).get_data_frames()[0]


def patch_season(season: str) -> None:
    cache_path = os.path.join(_NBA_CACHE, f"season_games_{season}.json")
    if not os.path.exists(cache_path):
        print(f"  [skip] no cached file for {season}")
        return
    with open(cache_path, encoding="utf-8") as f:
        payload = json.load(f)
    rows = payload["rows"] if isinstance(payload, dict) else payload
    if not rows:
        return

    gl = _fetch_gamelog(season)
    # team_stats arg is unused after cycle-10 fix.
    lookup = _compute_opp_adjusted_rolling(gl, {})

    patched = 0
    for r in rows:
        gid = str(r.get("game_id", "")).zfill(10)
        h_id = _TEAM_ABBR_TO_ID.get(r.get("home_team"))
        a_id = _TEAM_ABBR_TO_ID.get(r.get("away_team"))
        if h_id is None or a_id is None:
            continue
        new_home = lookup.get((h_id, gid))
        new_away = lookup.get((a_id, gid))
        if new_home is not None:
            r["home_off_rtg_vs_top_def"] = float(new_home)
        if new_away is not None:
            r["away_off_rtg_vs_top_def"] = float(new_away)
        patched += 1

    out = {"v": _SEASON_GAMES_VERSION, "rows": rows}
    with open(cache_path, "w") as f:
        json.dump(out, f)
    print(f"  [{season}] patched {patched}/{len(rows)} rows -> v={_SEASON_GAMES_VERSION}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="+", default=["2022-23", "2023-24", "2024-25"])
    args = ap.parse_args()
    for s in args.seasons:
        patch_season(s)
    print("[done]")


if __name__ == "__main__":
    main()
