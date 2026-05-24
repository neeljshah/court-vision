"""build_rest_travel_parquet.py — write data/rest_travel.parquet from cached schedules.

prop_pergame's _RestTravel keys on (game_date, team_abbreviation) and reads
is_b2b / is_b3b / miles_traveled / altitude_ft. The variance audit (cycle 1)
flagged all four as zero-variance because the parquet was missing.

Source: data/nba/season_games_<season>.json (already cached — game_id +
game_date + home/away teams). For each team we walk its chronological
schedule and compute:
  is_b2b: 1 if the previous game was yesterday
  is_b3b: 1 if the previous TWO games were yesterday and the day before
  miles_traveled: haversine miles from the previous game's venue to this one
  altitude_ft: this game's venue altitude (destination arena)

Re-uses _ARENA_GEO + _haversine from src.ingest.rest_travel — only the
data source is different (cached files, no API).
"""
from __future__ import annotations

import glob
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.ingest.rest_travel import _ARENA_GEO, _haversine  # noqa: E402

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_OUT_PATH = os.path.join(PROJECT_DIR, "data", "rest_travel.parquet")


def _venue(matchup_team: str, home_team: str, away_team: str) -> str:
    """The arena hosting the game is always the home team's arena."""
    return home_team


def main():
    files = sorted(glob.glob(os.path.join(_NBA_CACHE, "season_games_*.json")))
    if not files:
        print("[skip] no season_games_*.json files cached")
        return

    # team -> sorted list of (date, game_id, venue_team)
    by_team: Dict[str, List[Tuple[datetime, str, str]]] = {}
    for path in files:
        payload = json.load(open(path, encoding="utf-8"))
        rows = payload["rows"] if isinstance(payload, dict) else payload
        for r in rows:
            gid = str(r.get("game_id", "")).zfill(10)
            gdate_str = str(r.get("game_date", ""))
            try:
                gdate = datetime.fromisoformat(gdate_str)
            except ValueError:
                continue
            ht = r.get("home_team")
            at = r.get("away_team")
            if not ht or not at:
                continue
            by_team.setdefault(ht, []).append((gdate, gid, ht))  # home plays at ht
            by_team.setdefault(at, []).append((gdate, gid, ht))  # away travels to ht

    records: List[dict] = []
    for team, games in by_team.items():
        games.sort(key=lambda g: g[0])
        for i, (gdate, gid, venue) in enumerate(games):
            # is_b2b: previous game played yesterday
            is_b2b = 0
            is_b3b = 0
            if i >= 1:
                prev_date = games[i - 1][0]
                if (gdate - prev_date).days == 1:
                    is_b2b = 1
            if i >= 2:
                prev1 = games[i - 1][0]
                prev2 = games[i - 2][0]
                # 3 games in 3 nights = today, yesterday, day before
                if ((gdate - prev1).days == 1
                        and (prev1 - prev2).days == 1):
                    is_b3b = 1
            # Travel: from previous venue to this venue
            miles = 0.0
            if i >= 1:
                prev_venue = games[i - 1][2]
                if prev_venue in _ARENA_GEO and venue in _ARENA_GEO:
                    a = _ARENA_GEO[prev_venue]
                    b = _ARENA_GEO[venue]
                    miles = round(_haversine(a[0], a[1], b[0], b[1]), 1)
            alt = float(_ARENA_GEO.get(venue, (0.0, 0.0, 0))[2])
            records.append({
                "game_id":           gid,
                "team_abbreviation": team,
                "game_date":         gdate.date().isoformat(),
                "is_b2b":            float(is_b2b),
                "is_b3b":            float(is_b3b),
                "miles_traveled":    float(miles),
                "altitude_ft":       float(alt),
            })

    import pandas as pd
    df = pd.DataFrame(records)
    df.to_parquet(_OUT_PATH, index=False)
    print(f"[done] {len(df)} (team, game_date) rows -> {_OUT_PATH}")
    print(f"        teams: {df['team_abbreviation'].nunique()}, "
          f"date range: {df['game_date'].min()} -> {df['game_date'].max()}")
    print(f"        is_b2b sum: {int(df['is_b2b'].sum())}, "
          f"is_b3b sum: {int(df['is_b3b'].sum())}")
    print(f"        non-zero miles: {(df['miles_traveled'] > 0).sum()} / {len(df)}")
    print(f"        altitude unique: {sorted(df['altitude_ft'].unique())[:6]}...")


if __name__ == "__main__":
    main()
