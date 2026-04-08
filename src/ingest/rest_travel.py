"""
Ingest: rest days, back-to-back/back-to-3, travel miles, altitude from schedule.

Uses nba_api LeagueGameLog to build a per-team game schedule, then derives:
  - days_rest (0 = B2B)
  - is_b2b, is_b3b
  - miles_traveled (haversine, city coords)
  - altitude_ft (destination city)

No external deps beyond nba_api + pandas. Caches to data/rest_travel.parquet.
"""
from __future__ import annotations

import logging
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

log = logging.getLogger(__name__)

_CACHE_PATH = Path("data/rest_travel.parquet")
_SLEEP_S    = 0.6

# (lat, lon, altitude_ft) for NBA arenas by team abbreviation
_ARENA_GEO: Dict[str, Tuple[float, float, int]] = {
    "ATL": (33.7573, -84.3963, 1050),
    "BOS": (42.3662, -71.0621,   20),
    "BKN": (40.6826, -73.9754,   20),
    "CHA": (35.2251, -80.8392,  748),
    "CHI": (41.8807, -87.6742,  597),
    "CLE": (41.4965, -81.6882,  653),
    "DAL": (32.7905, -96.8103,  430),
    "DEN": (39.7487, -105.0077, 5183),
    "DET": (42.3410, -83.0553,  600),
    "GSW": (37.7679, -122.3874,   20),
    "HOU": (29.7508, -95.3621,   43),
    "IND": (39.7639, -86.1555,  715),
    "LAC": (34.0430, -118.2673,  285),
    "LAL": (34.0430, -118.2673,  285),
    "MEM": (35.1382, -90.0505,  337),
    "MIA": (25.7814, -80.1870,    8),
    "MIL": (43.0451, -87.9168,  617),
    "MIN": (44.9795, -93.2760,  815),
    "NOP": (29.9490, -90.0812,    3),
    "NYK": (40.7505, -73.9934,   56),
    "OKC": (35.4634, -97.5151, 1201),
    "ORL": (28.5392, -81.3837,  100),
    "PHI": (39.9012, -75.1720,   39),
    "PHX": (33.4457, -112.0712, 1086),
    "POR": (45.5316, -122.6668,   50),
    "SAC": (38.5802, -121.4996,   30),
    "SAS": (29.4270, -98.4375,  650),
    "TOR": (43.6435, -79.3791,  249),
    "UTA": (40.7683, -111.9011, 4327),
    "WAS": (38.8981, -77.0209,   25),
}


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in miles."""
    R = 3958.8
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _compute_travel(prev_abbrev: Optional[str], curr_abbrev: str) -> Tuple[float, int]:
    """Return (miles, altitude_ft) for team arriving at curr_abbrev."""
    if curr_abbrev not in _ARENA_GEO:
        return 0.0, 0
    dst = _ARENA_GEO[curr_abbrev]
    altitude = dst[2]
    if prev_abbrev is None or prev_abbrev not in _ARENA_GEO:
        return 0.0, altitude
    src = _ARENA_GEO[prev_abbrev]
    miles = _haversine(src[0], src[1], dst[0], dst[1])
    return round(miles, 1), altitude


def _fetch_league_game_log(season: str, team_id: int) -> Optional[pd.DataFrame]:
    """Fetch per-team game log for a season."""
    try:
        from nba_api.stats.endpoints import TeamGameLog  # type: ignore
        resp = TeamGameLog(team_id=team_id, season=season)
        df   = resp.get_data_frames()[0]
        return df
    except Exception as exc:
        log.warning("TeamGameLog failed team=%s season=%s: %s", team_id, season, exc)
        return None


def _fetch_all_teams() -> List[dict]:
    try:
        from nba_api.stats.static import teams as nba_teams  # type: ignore
        return nba_teams.get_teams()
    except Exception as exc:
        log.warning("nba_teams fetch failed: %s", exc)
        return []


def compute_rest_travel(
    game_schedule: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute rest/travel features from a schedule DataFrame.

    Args:
        game_schedule: Must have columns: game_id, team_abbreviation, game_date (YYYY-MM-DD),
                       matchup (e.g. "LAL vs. GSW" or "LAL @ GSW").
    Returns:
        DataFrame with added: days_rest, is_b2b, is_b3b, miles_traveled, altitude_ft.
    """
    df = game_schedule.copy()
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.sort_values(["team_abbreviation", "game_date"]).reset_index(drop=True)

    records = []
    for team, grp in df.groupby("team_abbreviation"):
        grp = grp.sort_values("game_date").reset_index(drop=True)
        prev_date: Optional[datetime] = None
        prev_venue: Optional[str]     = None

        for i, row in grp.iterrows():
            # Rest days
            if prev_date is None:
                rest = 7   # assume at least a week before first game in dataset
            else:
                rest = (row["game_date"] - prev_date).days - 1

            matchup = str(row.get("matchup", ""))
            is_home = "vs." in matchup
            home_abbrev = str(team)
            away_abbrev = matchup.split(" @ ")[-1].strip() if " @ " in matchup else str(team)
            # current venue is home team's city
            curr_venue = home_abbrev if is_home else away_abbrev

            miles, alt = _compute_travel(prev_venue, curr_venue)

            records.append({
                "game_id":          str(row["game_id"]),
                "team_abbreviation": str(team),
                "game_date":        row["game_date"].date().isoformat(),
                "days_rest":        rest,
                "is_b2b":           int(rest == 0),
                "is_b3b":           int(rest <= 1 and i >= 2 and grp.loc[max(0, i-2), "game_date"] >= row["game_date"] - pd.Timedelta(days=2)),
                "miles_traveled":   miles,
                "altitude_ft":      alt,
            })

            prev_date  = row["game_date"]
            prev_venue = curr_venue

    return pd.DataFrame(records)


def ingest_rest_travel(
    game_ids: List[str],
    season: str = "2024-25",
    cache_path: Path = _CACHE_PATH,
) -> pd.DataFrame:
    """
    Build rest/travel features for given game_ids.

    Fetches schedules via NBA API if not cached. Logs + continues on failure.
    """
    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    if cache_path.exists():
        try:
            cached = pd.read_parquet(cache_path)
            missing = set(map(str, game_ids)) - set(cached["game_id"].astype(str))
            if not missing:
                log.info("rest_travel: all %d games cached", len(game_ids))
                return cached
        except Exception as exc:
            log.warning("rest_travel cache read failed: %s", exc)
            cached = pd.DataFrame()
    else:
        cached = pd.DataFrame()

    all_teams = _fetch_all_teams()
    if not all_teams:
        log.error("rest_travel: could not fetch team list; aborting")
        return cached

    schedule_rows: List[dict] = []
    for team in all_teams:
        df = _fetch_league_game_log(season, team["id"])
        if df is None or df.empty:
            continue
        df["team_abbreviation"] = team["abbreviation"]
        schedule_rows.extend(df.to_dict("records"))
        time.sleep(_SLEEP_S)

    if not schedule_rows:
        log.error("rest_travel: no schedule data fetched")
        return cached

    sched_df  = pd.DataFrame(schedule_rows)
    sched_df.columns = [c.lower() for c in sched_df.columns]
    result_df = compute_rest_travel(sched_df)

    # Filter to requested game_ids + merge with cache
    result_df = result_df[result_df["game_id"].isin(map(str, game_ids))]
    if not cached.empty:
        result_df = pd.concat([cached, result_df]).drop_duplicates("game_id")

    try:
        result_df.to_parquet(cache_path, index=False)
        log.info("rest_travel: saved %d rows to %s", len(result_df), cache_path)
    except Exception as exc:
        log.error("rest_travel cache write failed: %s", exc)

    return result_df
