"""build_team_reb_context.py — per-game team OREB%/DREB% from boxscore_adv.

Reads every cached data/nba/boxscore_adv_*.json (teams entry — 2 teams per
game, with per-game offensivereboundpercentage / defensivereboundpercentage
computed by NBA Stats API from the play-by-play). Writes
data/team_reb_context.parquet keyed on (game_id, team_tricode, game_date)
for downstream rolling-5 prior-game aggregation in prop_pergame.

Cycle 90d (loop 5) — T1-E REB OREB-context feature.
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
_OUT_PATH = os.path.join(PROJECT_DIR, "data", "team_reb_context.parquet")


def build_game_date_lookup() -> Dict[str, str]:
    """Map game_id -> game_date by scanning cached season_games files."""
    lookup: Dict[str, str] = {}
    for path in glob.glob(os.path.join(_NBA_CACHE, "season_games_*.json")):
        try:
            payload = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        rows = payload["rows"] if isinstance(payload, dict) and "rows" in payload else payload
        for g in rows:
            gid = str(g.get("game_id", "")).zfill(10)
            if gid:
                lookup[gid] = str(g.get("game_date", ""))
    return lookup


def main():
    date_lookup = build_game_date_lookup()
    print(f"[reb-context] game_date lookup: {len(date_lookup)} entries")

    files = sorted(glob.glob(os.path.join(_NBA_CACHE, "boxscore_adv_*.json")))
    print(f"[reb-context] reading {len(files)} adv boxscore files")

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
            try:
                oreb_pct = float(t.get("offensivereboundpercentage") or 0.0)
                dreb_pct = float(t.get("defensivereboundpercentage") or 0.0)
                possessions = float(t.get("possessions") or 0.0)
            except (TypeError, ValueError):
                continue
            rows.append({
                "game_id": gid,
                "game_date": gdate,
                "team_tricode": tricode,
                "oreb_pct": oreb_pct,
                "dreb_pct": dreb_pct,
                "possessions": possessions,
            })

    import pandas as pd
    df = pd.DataFrame(rows)
    print(f"[reb-context] {len(df)} team-game rows; "
          f"skipped {skipped_no_date} (no date), {skipped_no_teams} (no teams)")
    print(f"[reb-context] unique teams: {df['team_tricode'].nunique()}")
    print(f"[reb-context] date range: {df['game_date'].min()} -> {df['game_date'].max()}")
    df = df.sort_values(["team_tricode", "game_date"]).reset_index(drop=True)
    df.to_parquet(_OUT_PATH, index=False)
    print(f"[reb-context] wrote {_OUT_PATH}")


if __name__ == "__main__":
    main()
