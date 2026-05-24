"""patch_season_games_pit.py — patch leaked features in cached season_games files.

Replaces the season-FINAL home_/away_off_rtg/def_rtg/net_rtg/pace/efg_pct/
ts_pct/tov_pct values (and derived pace_diff, elo_pace_interaction) with
season-to-date expanding-window values from _compute_season_to_date_team_stats.

Sim features and L10 rolling values are preserved from the existing cache —
sim is per-matchup (independent of game date in the simulator) and the L10
rollings were already shift(1) point-in-time. This avoids the 7-min cold
PossessionSimulator recompute and gets us an honest walk-forward in seconds.

Output: rewrites data/nba/season_games_<season>.json with v=_SEASON_GAMES_VERSION.
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
    _NBA_CACHE, _SEASON_GAMES_VERSION,
    _compute_season_to_date_team_stats,
)


# NBA TEAM_ABBREVIATION -> TEAM_ID mapping
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

_DEF = {"off_rtg": 112.0, "def_rtg": 112.0, "net_rtg": 0.0,
        "pace": 99.0, "efg_pct": 0.53, "ts_pct": 0.57, "tov_pct": 0.13}

_LEAK_KEYS = ("off_rtg", "def_rtg", "net_rtg", "pace", "efg_pct", "ts_pct", "tov_pct")


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
        print(f"  [skip] {season}: empty")
        return

    gl = _fetch_gamelog(season)
    std_lookup = _compute_season_to_date_team_stats(gl)
    if not std_lookup:
        print(f"  [skip] {season}: std_lookup empty (missing gamelog columns)")
        return

    patched = 0
    for r in rows:
        gid = str(r.get("game_id", "")).zfill(10)
        h_id = _TEAM_ABBR_TO_ID.get(r.get("home_team"))
        a_id = _TEAM_ABBR_TO_ID.get(r.get("away_team"))
        if h_id is None or a_id is None:
            continue
        ht = std_lookup.get((h_id, gid), _DEF)
        at = std_lookup.get((a_id, gid), _DEF)
        for k in _LEAK_KEYS:
            r[f"home_{k}"] = ht[k]
            r[f"away_{k}"] = at[k]
        r["pace_diff"] = round(ht["pace"] - at["pace"], 2)
        # elo_pace_interaction uses ELO × pace; ELO is already point-in-time
        # so only the pace half changes.
        home_elo = r.get("home_elo", 1500.0)
        away_elo = r.get("away_elo", 1500.0)
        r["elo_pace_interaction"] = round(
            home_elo * ht["pace"] - away_elo * at["pace"], 2
        )
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
