"""compute_ref_stats.py — derive per-ref tendencies from officials + season cache.

Once scripts/fetch_officials.py has populated data/nba/officials/officials_{s}.json
(per-game ref-crew lists), this script computes per-ref aggregate stats:

  - games_officiated     int
  - home_wins            int (home team won that ref's game)
  - home_win_rate        float (home_wins / games_officiated)
  - avg_total_fouls      float (if PF available in gamelog)
  - avg_total_fta        float (if FTA available)

Writes data/nba/officials/ref_stats_{season}.json:
  {ref_name: {games_officiated, home_wins, home_win_rate, avg_total_fouls,
              avg_total_fta}}

Then we have everything we need to fill the model's three currently-constant
ref features (ref_avg_fouls, ref_home_win_pct, ref_fta_tendency) with the
mean across the actual ref crew per game.

Run:
    python scripts/compute_ref_stats.py 2021-22 2022-23 2023-24 2024-25
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from typing import Dict, List

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.data import nba_api_headers_patch  # noqa: F401, E402

_NBA_CACHE     = os.path.join(PROJECT_DIR, "data", "nba")
_OFFICIALS_DIR = os.path.join(_NBA_CACHE, "officials")


def _load_json(path):
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _per_team_game_stats(season: str):
    """Return {(game_id, team_abbr): {pf: float, fta: float}} for the season.

    Pulls leaguegamelog (cached fast — single request). PF + FTA are
    team-level box-score fields; for ref tendencies we sum across the two
    teams in each game.
    """
    from nba_api.stats.endpoints import leaguegamelog
    time.sleep(0.6)
    try:
        df = leaguegamelog.LeagueGameLog(
            season=season, season_type_all_star="Regular Season",
            player_or_team_abbreviation="T",
        ).get_data_frames()[0]
    except Exception as e:
        print(f"  [warn] gamelog {season}: {e}")
        return {}
    out: dict = {}
    for _, r in df.iterrows():
        out[(str(r["GAME_ID"]), str(r["TEAM_ABBREVIATION"]))] = {
            "pf":  float(r.get("PF", 0) or 0),
            "fta": float(r.get("FTA", 0) or 0),
        }
    return out


def compute_for_season(season: str) -> int:
    officials_path = os.path.join(_OFFICIALS_DIR, f"officials_{season}.json")
    games_path     = os.path.join(_NBA_CACHE, f"season_games_{season}.json")
    out_path       = os.path.join(_OFFICIALS_DIR, f"ref_stats_{season}.json")

    officials = _load_json(officials_path)
    if not officials:
        print(f"  [{season}] no officials cache at {officials_path}")
        return 0
    games_payload = _load_json(games_path)
    if not games_payload:
        print(f"  [{season}] no season_games cache")
        return 0
    games = games_payload["rows"] if isinstance(games_payload, dict) else games_payload
    by_gid = {str(g["game_id"]): g for g in games}

    print(f"  [{season}] fetching team-game PF/FTA stats...", flush=True)
    tg_stats = _per_team_game_stats(season)
    print(f"  [{season}] got {len(tg_stats)} team-game stat rows", flush=True)

    # Aggregate per ref
    ref_agg = defaultdict(lambda: {"games": 0, "home_wins": 0,
                                   "total_pf": 0.0, "total_fta": 0.0})
    for gid, refs in officials.items():
        if not refs or gid not in by_gid:
            continue
        g = by_gid[gid]
        home_win = int(g.get("home_win", 0))
        h_team   = str(g.get("home_team", ""))
        a_team   = str(g.get("away_team", ""))
        h_box    = tg_stats.get((gid, h_team), {"pf": 0.0, "fta": 0.0})
        a_box    = tg_stats.get((gid, a_team), {"pf": 0.0, "fta": 0.0})
        total_pf  = h_box["pf"]  + a_box["pf"]
        total_fta = h_box["fta"] + a_box["fta"]
        for ref in refs:
            r = ref_agg[ref]
            r["games"]      += 1
            r["home_wins"]  += home_win
            r["total_pf"]   += total_pf
            r["total_fta"]  += total_fta

    out = {}
    for ref, r in ref_agg.items():
        if r["games"] < 5:
            continue  # skip refs with too-thin sample; row builder falls back
        out[ref] = {
            "games_officiated": r["games"],
            "home_wins":        r["home_wins"],
            "home_win_rate":    round(r["home_wins"] / r["games"], 4),
            "avg_total_fouls":  round(r["total_pf"]  / r["games"], 2),
            "avg_total_fta":    round(r["total_fta"] / r["games"], 2),
        }
    with open(out_path, "w") as f:
        json.dump(out, f)
    print(f"  [{season}] wrote {len(out)} ref stats -> {out_path}", flush=True)
    return len(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("seasons", nargs="+")
    args = ap.parse_args()
    print(f"Ref-stats computer for {args.seasons}\n")
    for s in args.seasons:
        print(f"=== {s} ===", flush=True)
        compute_for_season(s)
    print("\nDONE")


if __name__ == "__main__":
    main()
