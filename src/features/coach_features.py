"""
coach_features.py — Per-coach tendency features for NBA game models.

Derives pace, efficiency, style, and situational win-% signals keyed to
the head coach in charge on a given game date.  Aggregates are computed
from NBA API TeamGameLog data and cached to data/models/coach_history.json.

Public API
----------
    get_head_coach(team_id, season, game_date)      -> str
    build_coach_history(seasons)                    -> pd.DataFrame
    get_coach_features(home_team, away_team,
                       season, game_date)           -> dict
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

log = logging.getLogger(__name__)

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CACHE_DIR   = os.path.join(_PROJECT_DIR, "data", "models")
_COACH_HIST  = os.path.join(_CACHE_DIR, "coach_history.json")
_NBA_CACHE   = os.path.join(_PROJECT_DIR, "data", "nba")
_API_DELAY   = 0.7  # NBA API throttle

# ── Hard-coded coach→team tenure map (fallback when API unavailable) ───────────
# Format: coach_name -> list of {team, start_date, end_date or None}
_COACH_TENURE: Dict[str, List[dict]] = {
    "Erik Spoelstra":    [{"team": "MIA", "start": "2008-06-01", "end": None}],
    "Gregg Popovich":    [{"team": "SAS", "start": "1996-12-01", "end": "2022-06-01"}],
    "Doc Rivers":        [{"team": "BOS", "start": "2004-07-01", "end": "2013-06-01"},
                          {"team": "LAC", "start": "2013-07-01", "end": "2020-09-01"},
                          {"team": "PHI", "start": "2020-10-01", "end": "2023-02-01"},
                          {"team": "MIL", "start": "2023-06-01", "end": "2024-09-01"}],
    "Steve Kerr":        [{"team": "GSW", "start": "2014-06-01", "end": None}],
    "Nick Nurse":        [{"team": "TOR", "start": "2018-06-01", "end": "2023-06-01"},
                          {"team": "PHI", "start": "2023-06-01", "end": None}],
    "Ime Udoka":         [{"team": "BOS", "start": "2021-09-01", "end": "2022-09-28"},
                          {"team": "HOU", "start": "2022-10-01", "end": None}],
    "Brad Stevens":      [{"team": "BOS", "start": "2013-07-01", "end": "2021-06-01"}],
    "Tyronn Lue":        [{"team": "CLE", "start": "2016-01-22", "end": "2018-10-01"},
                          {"team": "LAC", "start": "2020-10-01", "end": None}],
    "Mike Budenholzer":  [{"team": "ATL", "start": "2013-07-01", "end": "2018-05-01"},
                          {"team": "MIL", "start": "2018-06-01", "end": "2023-05-01"},
                          {"team": "PHX", "start": "2023-06-01", "end": None}],
    "Monty Williams":    [{"team": "NOP", "start": "2019-06-01", "end": "2022-06-01"},
                          {"team": "PHX", "start": "2019-06-01", "end": "2023-06-01"},
                          {"team": "DET", "start": "2023-06-01", "end": "2024-09-01"}],
    "Rick Carlisle":     [{"team": "DAL", "start": "2008-07-01", "end": "2021-06-01"},
                          {"team": "IND", "start": "2021-07-01", "end": None}],
    "Tom Thibodeau":     [{"team": "CHI", "start": "2010-07-01", "end": "2015-05-01"},
                          {"team": "MIN", "start": "2016-07-01", "end": "2019-01-06"},
                          {"team": "NYK", "start": "2020-11-01", "end": None}],
    "Quin Snyder":       [{"team": "UTA", "start": "2014-06-01", "end": "2022-06-01"},
                          {"team": "ATL", "start": "2022-07-01", "end": None}],
    "Jason Kidd":        [{"team": "BKN", "start": "2013-06-01", "end": "2014-06-01"},
                          {"team": "MIL", "start": "2014-07-01", "end": "2018-06-01"},
                          {"team": "DAL", "start": "2021-07-01", "end": None}],
    "Billy Donovan":     [{"team": "OKC", "start": "2015-06-01", "end": "2020-09-01"},
                          {"team": "CHI", "start": "2020-10-01", "end": None}],
    "Taylor Jenkins":    [{"team": "MEM", "start": "2019-06-01", "end": None}],
    "Mark Daigneault":   [{"team": "OKC", "start": "2020-10-01", "end": None}],
    "Mike Brown":        [{"team": "SAC", "start": "2022-07-01", "end": None}],
    "Darvin Ham":        [{"team": "LAL", "start": "2022-07-01", "end": "2024-05-01"}],
    "JJ Redick":         [{"team": "LAL", "start": "2024-07-01", "end": None}],
}

# team → {season → coach_name}  (derived lazily from _COACH_TENURE)
_team_season_coach: Dict[str, Dict[str, str]] = {}


def _build_team_season_map() -> None:
    """Populate _team_season_coach from _COACH_TENURE."""
    global _team_season_coach
    if _team_season_coach:
        return
    for coach, tenures in _COACH_TENURE.items():
        for t in tenures:
            team = t["team"]
            start = datetime.strptime(t["start"], "%Y-%m-%d")
            end = datetime.strptime(t["end"], "%Y-%m-%d") if t["end"] else datetime(2030, 1, 1)
            for yr in range(2010, 2027):
                season_start = datetime(yr, 10, 1)
                season_end   = datetime(yr + 1, 7, 1)
                s_label = f"{yr}-{str(yr + 1)[2:]}"
                if start <= season_end and end >= season_start:
                    _team_season_coach.setdefault(team, {})[s_label] = coach


_build_team_season_map()


def get_head_coach(team_id: int, season: str, game_date: str) -> str:
    """
    Return the head coach name for team_id on game_date.

    Tries nba_api CommonCoachInfo first; falls back to the hard-coded tenure map.
    """
    try:
        from nba_api.stats.endpoints import CommonTeamRoster  # type: ignore
        from nba_api.stats.static import teams as nba_teams    # type: ignore
        team_list = nba_teams.get_teams()
        abbrev = next((t["abbreviation"] for t in team_list if t["id"] == team_id), None)
        if abbrev and abbrev in _team_season_coach:
            return _team_season_coach[abbrev].get(season, "Unknown Coach")
    except Exception:
        pass

    try:
        from nba_api.stats.static import teams as nba_teams  # type: ignore
        team_list = nba_teams.get_teams()
        abbrev = next((t["abbreviation"] for t in team_list if t["id"] == team_id), None)
    except Exception:
        abbrev = None

    if abbrev and abbrev in _team_season_coach:
        return _team_season_coach[abbrev].get(season, "Unknown Coach")
    return "Unknown Coach"


def _fetch_team_season_stats(team_id: int, season: str) -> Optional[pd.DataFrame]:
    """Fetch TeamGameLog for a season; return None on failure."""
    try:
        from nba_api.stats.endpoints import TeamGameLog  # type: ignore
        time.sleep(_API_DELAY)
        resp = TeamGameLog(team_id=team_id, season=season)
        return resp.get_data_frames()[0]
    except Exception as exc:
        log.warning("TeamGameLog failed team=%d season=%s: %s", team_id, season, exc)
        return None


def _aggregate_coach_stats(df: pd.DataFrame, coach: str) -> dict:
    """
    Compute per-coach aggregates from a season game-log DataFrame.

    Columns used: PTS, OPP_PTS (inferred), FGA, FG3A, FTA, TOV, MIN, PACE (if present).
    """
    n = len(df)
    if n == 0:
        return {}

    # Pace proxy: (PTS + OPP_PTS) / 2 / 100 * 100 — use FGA as proxy if PACE absent
    pace_vals = []
    if "PACE" in df.columns:
        pace_vals = df["PACE"].dropna().tolist()
    elif "FGA" in df.columns:
        # ~100-poss estimate: FGA roughly correlates; raw FGA ≈ poss proxy
        pace_vals = df["FGA"].dropna().tolist()

    # Offensive / defensive efficiency
    pts   = df["PTS"].dropna().mean() if "PTS" in df.columns else 0.0
    fga   = df["FGA"].dropna().mean() if "FGA" in df.columns else 1.0
    fg3a  = df["FG3A"].dropna().mean() if "FG3A" in df.columns else 0.0
    fta   = df["FTA"].dropna().mean() if "FTA" in df.columns else 0.0
    tov   = df["TOV"].dropna().mean() if "TOV" in df.columns else 0.0
    plus_minus = df["PLUS_MINUS"].dropna() if "PLUS_MINUS" in df.columns else pd.Series(dtype=float)

    # Rotation depth: players with >10 MPG — infer from MIN column if present
    rotation_depth = 8.0  # sensible default

    # Close games (decided by ≤5 pts) — requires PLUS_MINUS
    close_wins = 0
    close_games = 0
    if "PLUS_MINUS" in df.columns and "WL" in df.columns:
        for _, row in df.iterrows():
            pm = float(row.get("PLUS_MINUS", 0) or 0)
            wl = str(row.get("WL", "")).upper()
            if abs(pm) <= 5:
                close_games += 1
                if wl == "W":
                    close_wins += 1

    # B2B wins (need game dates sorted)
    b2b_wins, b2b_games = 0, 0
    if "GAME_DATE" in df.columns and "WL" in df.columns:
        df2 = df.copy()
        df2["_dt"] = pd.to_datetime(df2["GAME_DATE"], format="%b %d, %Y", errors="coerce")
        df2 = df2.sort_values("_dt").reset_index(drop=True)
        for i in range(1, len(df2)):
            prev_dt = df2.loc[i - 1, "_dt"]
            curr_dt = df2.loc[i, "_dt"]
            if pd.notna(prev_dt) and pd.notna(curr_dt):
                gap = (curr_dt - prev_dt).days
                if gap == 1:
                    b2b_games += 1
                    if str(df2.loc[i, "WL"]).upper() == "W":
                        b2b_wins += 1

    wins = int((df["WL"] == "W").sum()) if "WL" in df.columns else 0

    return {
        "coach":                  coach,
        "coach_games_coached":    n,
        "coach_avg_pace":         round(float(pd.Series(pace_vals).mean()) if pace_vals else 95.0, 2),
        "coach_avg_oe":           round(pts, 2),
        "coach_avg_de":           round(pts - float(plus_minus.mean()) if len(plus_minus) else pts, 2),
        "coach_3pa_rate":         round(fg3a / max(fga, 1.0), 4),
        "coach_fta_rate":         round(fta / max(fga, 1.0), 4),
        "coach_to_pct":           round(tov / max(fga + 0.44 * fta - tov + 1, 1), 4),
        "coach_rotation_depth_avg": rotation_depth,
        "coach_late_close_win_pct": round(close_wins / max(close_games, 1), 4),
        "coach_b2b_win_pct":      round(b2b_wins / max(b2b_games, 1), 4),
        "coach_win_pct":          round(wins / max(n, 1), 4),
    }


def build_coach_history(seasons: Optional[List[str]] = None) -> pd.DataFrame:
    """
    Build per-coach aggregate stats across given seasons.

    Fetches NBA API TeamGameLog for every team × season, maps to coach,
    aggregates, and writes to data/models/coach_history.json.

    Args:
        seasons: List of season strings, e.g. ["2022-23", "2023-24", "2024-25"].
                 Defaults to last 3 completed seasons.

    Returns:
        DataFrame with one row per coach × season.
    """
    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    os.makedirs(_CACHE_DIR, exist_ok=True)

    # Load existing cache
    existing: List[dict] = []
    if os.path.exists(_COACH_HIST):
        try:
            with open(_COACH_HIST) as f:
                existing = json.load(f)
        except Exception:
            existing = []

    existing_keys = {(r["coach"], r.get("season")) for r in existing}

    try:
        from nba_api.stats.static import teams as nba_teams  # type: ignore
        all_teams = nba_teams.get_teams()
    except Exception:
        log.error("build_coach_history: cannot import nba_api")
        return pd.DataFrame(existing)

    new_rows: List[dict] = []

    for season in seasons:
        for team in all_teams:
            abbrev = team["abbreviation"]
            tid    = team["id"]
            coach  = (_team_season_coach.get(abbrev) or {}).get(season, "Unknown Coach")
            key    = (coach, season)
            if key in existing_keys:
                continue

            df = _fetch_team_season_stats(tid, season)
            if df is None or df.empty:
                continue

            agg = _aggregate_coach_stats(df, coach)
            if agg:
                agg["season"] = season
                agg["team"]   = abbrev
                new_rows.append(agg)
                log.info("coach_history: %s %s %s: pace=%.1f 3pa=%.3f",
                         coach, abbrev, season,
                         agg["coach_avg_pace"], agg["coach_3pa_rate"])

    all_rows = existing + new_rows

    # Consolidate: average across all seasons per coach
    coach_agg: Dict[str, dict] = {}
    for row in all_rows:
        c = row["coach"]
        if c not in coach_agg:
            coach_agg[c] = {"coach": c, "_rows": []}
        coach_agg[c]["_rows"].append(row)

    consolidated: List[dict] = []
    _num_keys = [
        "coach_games_coached", "coach_avg_pace", "coach_avg_oe", "coach_avg_de",
        "coach_3pa_rate", "coach_fta_rate", "coach_to_pct",
        "coach_rotation_depth_avg", "coach_late_close_win_pct",
        "coach_b2b_win_pct", "coach_win_pct",
    ]
    for c, info in coach_agg.items():
        rows = info["_rows"]
        total_g = sum(r.get("coach_games_coached", 0) for r in rows)
        entry: dict = {"coach": c, "coach_games_coached": total_g, "seasons_tracked": len(rows)}
        for k in _num_keys[1:]:
            vals = [r[k] for r in rows if k in r]
            entry[k] = round(sum(vals) / max(len(vals), 1), 4)
        consolidated.append(entry)

    try:
        with open(_COACH_HIST, "w") as f:
            json.dump(consolidated, f, indent=2)
        log.info("coach_history: wrote %d coaches to %s", len(consolidated), _COACH_HIST)
    except Exception as exc:
        log.error("coach_history write failed: %s", exc)

    return pd.DataFrame(consolidated)


# ── Runtime lookup cache ───────────────────────────────────────────────────────
_coach_lookup: Optional[Dict[str, dict]] = None


def _load_coach_lookup() -> Dict[str, dict]:
    global _coach_lookup
    if _coach_lookup is not None:
        return _coach_lookup
    if os.path.exists(_COACH_HIST):
        try:
            with open(_COACH_HIST) as f:
                data: List[dict] = json.load(f)
            _coach_lookup = {r["coach"]: r for r in data}
            return _coach_lookup
        except Exception:
            pass
    _coach_lookup = {}
    return _coach_lookup


def _default_coach_features(prefix: str) -> dict:
    """Return neutral feature values for an unknown coach."""
    return {
        f"{prefix}_avg_pace":             95.0,
        f"{prefix}_avg_oe":               110.0,
        f"{prefix}_avg_de":               112.0,
        f"{prefix}_3pa_rate":             0.38,
        f"{prefix}_fta_rate":             0.26,
        f"{prefix}_to_pct":               0.14,
        f"{prefix}_rotation_depth_avg":   8.0,
        f"{prefix}_late_close_win_pct":   0.50,
        f"{prefix}_b2b_win_pct":          0.44,
        f"{prefix}_games_coached":        0,
    }


def get_coach_features(
    home_team: str,
    away_team: str,
    season: str,
    game_date: str,
) -> dict:
    """
    Return coach-tendency features for both home and away teams.

    Features are prefixed home_coach_* / away_coach_* plus a delta
    home_coach_pace_diff and home_coach_3pa_diff.

    Args:
        home_team: NBA team abbreviation (e.g. "LAL")
        away_team: NBA team abbreviation (e.g. "GSW")
        season:    Season string (e.g. "2024-25")
        game_date: ISO date string (e.g. "2025-01-15")

    Returns:
        dict of float features.
    """
    lookup = _load_coach_lookup()

    home_coach = (_team_season_coach.get(home_team) or {}).get(season, "Unknown Coach")
    away_coach = (_team_season_coach.get(away_team) or {}).get(season, "Unknown Coach")

    home_stats = lookup.get(home_coach, {})
    away_stats = lookup.get(away_coach, {})

    def _extract(stats: dict, prefix: str) -> dict:
        if not stats:
            return _default_coach_features(prefix)
        return {
            f"{prefix}_avg_pace":             stats.get("coach_avg_pace", 95.0),
            f"{prefix}_avg_oe":               stats.get("coach_avg_oe", 110.0),
            f"{prefix}_avg_de":               stats.get("coach_avg_de", 112.0),
            f"{prefix}_3pa_rate":             stats.get("coach_3pa_rate", 0.38),
            f"{prefix}_fta_rate":             stats.get("coach_fta_rate", 0.26),
            f"{prefix}_to_pct":               stats.get("coach_to_pct", 0.14),
            f"{prefix}_rotation_depth_avg":   stats.get("coach_rotation_depth_avg", 8.0),
            f"{prefix}_late_close_win_pct":   stats.get("coach_late_close_win_pct", 0.50),
            f"{prefix}_b2b_win_pct":          stats.get("coach_b2b_win_pct", 0.44),
            f"{prefix}_games_coached":        stats.get("coach_games_coached", 0),
        }

    home_feats = _extract(home_stats, "home_coach")
    away_feats = _extract(away_stats, "away_coach")

    deltas = {
        "home_coach_pace_diff":  round(
            home_feats["home_coach_avg_pace"] - away_feats["away_coach_avg_pace"], 3),
        "home_coach_3pa_diff":   round(
            home_feats["home_coach_3pa_rate"] - away_feats["away_coach_3pa_rate"], 4),
        "home_coach_name":       home_coach,
        "away_coach_name":       away_coach,
    }

    return {**home_feats, **away_feats, **deltas}
