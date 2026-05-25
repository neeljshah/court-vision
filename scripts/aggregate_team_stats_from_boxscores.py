"""aggregate_team_stats_from_boxscores.py — per-game team advanced stats.

Cycle 99e (loop 5) — T-A team_advanced_stats parquet.

Reads every cached data/nba/boxscore_adv_*.json (teams entry — 2 teams per
game) and writes data/team_advanced_stats.parquet keyed on
(game_id, team_tricode, game_date) with the per-team advanced metrics:

    off_rtg, def_rtg, pace, oreb_pct, dreb_pct, ast_pct,
    efg_pct, ts_pct, tov_ratio

Companion script to build_team_reb_context.py (cycle 90d) — that script
only persisted oreb/dreb. This one captures the full advanced row so
build_pergame_dataset can derive rolling-5 prior opp-context features
(opp_def_pts_l5, opp_def_reb_l5, ...) keyed on (opp_tricode, date).

Game-date join: pulled from data/nba/season_games_<season>.json
(game_id -> game_date). Skipped rows lack a date or teams array.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from typing import Dict

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_OUT_PATH = os.path.join(PROJECT_DIR, "data", "team_advanced_stats.parquet")


# Map output column -> source key in boxscore_adv teams entry.
_TEAM_COLS = {
    "off_rtg":  "offensiverating",
    "def_rtg":  "defensiverating",
    "pace":     "pace",
    "oreb_pct": "offensivereboundpercentage",
    "dreb_pct": "defensivereboundpercentage",
    "ast_pct":  "assistpercentage",
    "efg_pct":  "effectivefieldgoalpercentage",
    "ts_pct":   "trueshootingpercentage",
    "tov_ratio": "turnoverratio",
}


def build_game_date_lookup() -> Dict[str, str]:
    """Map game_id -> game_date by scanning cached season_games files."""
    lookup: Dict[str, str] = {}
    for path in glob.glob(os.path.join(_NBA_CACHE, "season_games_*.json")):
        try:
            payload = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        rows = payload["rows"] if isinstance(payload, dict) and "rows" in payload else payload
        for g in rows or []:
            gid = str(g.get("game_id", "")).zfill(10)
            if gid:
                lookup[gid] = str(g.get("game_date", ""))
    return lookup


def main():
    date_lookup = build_game_date_lookup()
    print(f"[team-adv] game_date lookup: {len(date_lookup)} entries")

    files = sorted(glob.glob(os.path.join(_NBA_CACHE, "boxscore_adv_*.json")))
    print(f"[team-adv] reading {len(files)} adv boxscore files")

    rows = []
    skipped_no_date = 0
    skipped_no_teams = 0
    for path in files:
        try:
            data = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        gid = str(data.get("game_id", "")).zfill(10)
        gdate = date_lookup.get(gid)
        if not gdate:
            skipped_no_date += 1
            continue
        teams = data.get("teams", [])
        if not teams or len(teams) < 2:
            skipped_no_teams += 1
            continue
        for t in teams:
            tricode = str(t.get("teamtricode", "")).strip()
            if not tricode:
                continue
            entry = {
                "game_id":      gid,
                "game_date":    gdate,
                "team_tricode": tricode,
            }
            ok = True
            for out_col, src in _TEAM_COLS.items():
                v = t.get(src)
                try:
                    entry[out_col] = float(v) if v is not None else 0.0
                except (TypeError, ValueError):
                    entry[out_col] = 0.0
                    ok = False
            rows.append(entry)

    import pandas as pd  # noqa: PLC0415
    df = pd.DataFrame(rows)
    print(f"[team-adv] {len(df)} team-game rows; "
          f"skipped {skipped_no_date} (no date), {skipped_no_teams} (no teams)")
    if df.empty:
        print("[team-adv] no rows; aborting parquet write")
        return
    print(f"[team-adv] unique teams: {df['team_tricode'].nunique()}")
    print(f"[team-adv] date range: {df['game_date'].min()} -> {df['game_date'].max()}")
    df = df.sort_values(["team_tricode", "game_date"]).reset_index(drop=True)
    df.to_parquet(_OUT_PATH, index=False)
    print(f"[team-adv] wrote {_OUT_PATH}")


if __name__ == "__main__":
    main()
