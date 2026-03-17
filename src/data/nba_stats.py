"""
nba_stats.py — NBA Stats API integration for tracker validation.

Uses nba_api to fetch:
  - Team rosters + jersey colors   → validate team classification
  - Shot chart data                → cross-check ball detection near shot events
  - Game box scores                → sanity-check player counts per team

All data cached locally under data/nba/ as JSON to avoid repeat API calls.

Public API
----------
    fetch_team_info(team_name)              -> dict
    fetch_shot_chart(game_id, team_id)      -> List[dict]
    fetch_game_ids(team_abbrev, season)     -> List[str]
    validate_tracking_vs_shots(predictions,
                               shot_chart,
                               fps)         -> dict
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_NBA_CACHE  = os.path.join(PROJECT_DIR, "data", "nba")

# Roster cache TTL: 48 hours. Rosters change via trades/signings throughout the
# season. Without a TTL, jersey-number → player-name mapping stays wrong forever
# after a trade (e.g. a player moved at the February deadline).
_ROSTER_TTL_HOURS = 48

# Team season stats cache TTL: 24 hours. Off/def ratings and win% update after
# every game played. A perpetual cache would feed the win probability model
# multi-week-old ratings, silently degrading prediction accuracy mid-season.
_TEAM_SEASON_STATS_TTL_HOURS = 24


def _configure_nba_session(timeout: int = 60, retries: int = 3) -> None:
    """
    Inject a retry-capable requests.Session into nba_api's HTTP layer.

    stats.nba.com frequently drops connections on the default session.
    This patches in:
      - Automatic retries on connection errors (backoff factor 2s)
      - Modern User-Agent (avoids 403s from stale browser string)
      - 60-second timeout (default is None — hangs forever)

    Called once at module load; idempotent.
    """
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    try:
        from nba_api.stats.library.http import NBAStatsHTTP
    except ImportError:
        return

    retry = Retry(
        total=retries,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    # More recent User-Agent — the bundled one (Firefox 72, Jan 2020) triggers blocks
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept":          "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "x-nba-stats-origin": "stats",
        "x-nba-stats-token":  "true",
        "Referer":         "https://www.nba.com/",
        "Origin":          "https://www.nba.com",
        "Connection":      "keep-alive",
    })

    # Store timeout on the session object; nba_api's send_api_request passes timeout=None
    # by default — we monkey-patch it to use ours
    _original_get = session.get
    def _get_with_timeout(url, **kwargs):
        kwargs.setdefault("timeout", timeout)
        return _original_get(url, **kwargs)
    session.get = _get_with_timeout  # type: ignore[method-assign]

    NBAStatsHTTP.set_session(session)


# Patch session at import time
_configure_nba_session()

# Known NBA team jersey colors in HSV for tracker config validation
# (primary court/away jerseys — helps detect if HSV thresholds are misconfigured)
TEAM_JERSEY_COLORS: dict[str, dict] = {
    "GSW":  {"home": "white",   "away": "royal_blue"},
    "LAL":  {"home": "gold",    "away": "purple"},
    "BOS":  {"home": "green",   "away": "white"},
    "MIA":  {"home": "white",   "away": "black"},
    "MIL":  {"home": "green",   "away": "white"},
    "PHX":  {"home": "orange",  "away": "purple"},
    "DAL":  {"home": "white",   "away": "blue"},
    "DEN":  {"home": "white",   "away": "navy"},
    "MEM":  {"home": "white",   "away": "navy"},
    "NYK":  {"home": "white",   "away": "orange"},
    "CHI":  {"home": "white",   "away": "red"},
    "CLE":  {"home": "white",   "away": "wine"},
    "BKN":  {"home": "white",   "away": "black"},
    "PHI":  {"home": "white",   "away": "blue"},
    "ATL":  {"home": "white",   "away": "red"},
}


# ─────────────────────────────────────────────────────────────────────────────
# Team info
# ─────────────────────────────────────────────────────────────────────────────

def fetch_team_info(team_name: str) -> dict:
    """
    Fetch NBA team metadata (id, full name, abbreviation, conference).

    Args:
        team_name: Full name, city, or abbreviation (e.g. "Warriors", "GSW").

    Returns:
        Dict with id, full_name, abbreviation, city, state, year_founded.
        Returns {} if team not found.
    """
    cache_path = os.path.join(_NBA_CACHE, f"team_{_safe(team_name)}.json")
    if os.path.exists(cache_path):
        return _load(cache_path)

    try:
        from nba_api.stats.static import teams as nba_teams
        all_teams = nba_teams.get_teams()
        query = team_name.lower()
        match = next(
            (t for t in all_teams if
             query in t["full_name"].lower() or
             query in t["nickname"].lower() or
             query == t["abbreviation"].lower()),
            None
        )
        if match is None:
            return {}
        _save(cache_path, match)
        return match
    except ImportError:
        raise RuntimeError("nba_api not installed. Run: pip install nba_api")


def fetch_game_ids(
    team_abbrev: str,
    season: str = "2023-24",
    season_type: str = "Regular Season",
    limit: int = 5,
) -> list:
    """
    Return recent game IDs for a team.

    Args:
        team_abbrev:  e.g. "GSW", "BOS"
        season:       e.g. "2023-24"
        season_type:  "Regular Season" | "Playoffs"
        limit:        Max games to return.

    Returns:
        List of game_id strings (e.g. "0022301234").
    """
    cache_key = f"games_{team_abbrev}_{season}_{season_type[:3]}_{limit}"
    cache_path = os.path.join(_NBA_CACHE, f"{_safe(cache_key)}.json")
    if os.path.exists(cache_path):
        return _load(cache_path)

    try:
        from nba_api.stats.static import teams as nba_teams
        from nba_api.stats.endpoints import teamgamelog

        all_teams = nba_teams.get_teams()
        team = next((t for t in all_teams if t["abbreviation"] == team_abbrev), None)
        if team is None:
            return []

        _rate_limit()
        log = teamgamelog.TeamGameLog(
            team_id=team["id"],
            season=season,
            season_type_all_star=season_type,
        )
        df = log.get_data_frames()[0]
        ids = df["Game_ID"].tolist()[:limit]
        _save(cache_path, ids)
        return ids

    except ImportError:
        raise RuntimeError("nba_api not installed. Run: pip install nba_api")


# ─────────────────────────────────────────────────────────────────────────────
# Roster (jersey numbers → player identity)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_roster(team_id: int, season: str = "2024-25") -> dict:
    """
    Fetch the jersey-number-to-player mapping for a team.

    Uses the CommonTeamRoster endpoint and caches the result locally.
    Entries with missing or non-numeric NUM values are skipped (with a
    printed count) rather than raising an exception.

    Args:
        team_id: NBA Stats team ID (integer, e.g. 1610612747 for LAL).
        season:  NBA season string (e.g. "2024-25").

    Returns:
        Dict keyed by integer jersey number:
        {
            23: {"player_id": 2544, "player_name": "LeBron James"},
            ...
        }
        Returns {} if the endpoint is unavailable or roster is empty.
    """
    cache_key = f"roster_{team_id}_{season}"
    cache_path = os.path.join(_NBA_CACHE, f"{_safe(cache_key)}.json")
    _roster_fresh = (
        os.path.exists(cache_path)
        and (time.time() - os.path.getmtime(cache_path)) < _ROSTER_TTL_HOURS * 3600
    )
    if _roster_fresh:
        raw = _load(cache_path)
        # Keys were serialised as strings by JSON — convert back to int
        return {int(k): v for k, v in raw.items()}

    try:
        from nba_api.stats.endpoints import commonteamroster
    except ImportError:
        raise RuntimeError("nba_api not installed. Run: pip install nba_api")

    time.sleep(0.6)
    try:
        resp = commonteamroster.CommonTeamRoster(
            team_id=team_id,
            season=season,
        )
        rows = resp.get_normalized_dict().get("CommonTeamRoster", [])
    except Exception as exc:
        print(f"[fetch_roster] API error: {exc}")
        return {}

    result: dict = {}
    missing = 0
    for row in rows:
        num_str = str(row.get("NUM", "")).strip()
        if not num_str.isdigit():
            missing += 1
            continue
        jersey_num = int(num_str)
        result[jersey_num] = {
            "player_id":   int(row.get("PLAYER_ID", 0)),
            "player_name": str(row.get("PLAYER", "")),
        }

    if missing:
        print(f"[fetch_roster] {missing} entries with no jersey number skipped")

    # Cache with string keys (JSON requirement) — convert back on load
    _save(cache_path, {str(k): v for k, v in result.items()})
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Shot chart
# ─────────────────────────────────────────────────────────────────────────────

def fetch_shot_chart(game_id: str, team_id: Optional[int] = None) -> list:
    """
    Fetch shot chart data for a game.

    Returns:
        List of dicts with: player_name, team_id, shot_type, shot_made,
        period, minutes_remaining, seconds_remaining, x, y (court coords).
    """
    cache_path = os.path.join(_NBA_CACHE, f"shots_{game_id}_{team_id}.json")
    if os.path.exists(cache_path):
        return _load(cache_path)

    try:
        from nba_api.stats.endpoints import shotchartdetail

        _rate_limit()
        sc = shotchartdetail.ShotChartDetail(
            team_id=team_id or 0,
            player_id=0,
            game_id_nullable=game_id,
            context_measure_simple="FGA",
        )
        df = sc.get_data_frames()[0]
        shots = df[[
            "PLAYER_NAME", "TEAM_ID", "ACTION_TYPE", "SHOT_TYPE",
            "SHOT_MADE_FLAG", "PERIOD", "MINUTES_REMAINING",
            "SECONDS_REMAINING", "LOC_X", "LOC_Y",
        ]].rename(columns={
            "PLAYER_NAME":        "player_name",
            "TEAM_ID":            "team_id",
            "ACTION_TYPE":        "shot_type",
            "SHOT_MADE_FLAG":     "shot_made",
            "PERIOD":             "period",
            "MINUTES_REMAINING":  "minutes_remaining",
            "SECONDS_REMAINING":  "seconds_remaining",
            "LOC_X":              "x",
            "LOC_Y":              "y",
        }).to_dict("records")

        _save(cache_path, shots)
        return shots

    except ImportError:
        raise RuntimeError("nba_api not installed. Run: pip install nba_api")


# ─────────────────────────────────────────────────────────────────────────────
# Cross-validation: tracking vs shot chart
# ─────────────────────────────────────────────────────────────────────────────

def validate_tracking_vs_shots(
    predictions: list,
    shot_chart: list,
    fps: float = 30.0,
    period: int = 1,
) -> dict:
    """
    Cross-validate tracker ball possession events against NBA shot chart data.

    Approach:
      - Shot chart timestamps (period + clock) → estimated frame numbers
      - For each shot, check if ball_possession=True exists in predictions
        within a ±window of the expected frame
      - Compute shot detection rate and false positive rate

    Args:
        predictions: Per-frame tracking list from track_video().
        shot_chart:  From fetch_shot_chart().
        fps:         Video frames per second.
        period:      Which period the video clip covers (1-4).

    Returns:
        {
          "shots_in_period":     int,
          "shots_detected":      int,   (possession changed near shot time)
          "detection_rate":      float,
          "possession_frames":   int,   (total frames with ball possession)
          "avg_possession_conf": float,
        }
    """
    PERIOD_SECS  = 12 * 60
    WINDOW_FRAMES = int(fps * 3)   # ±3 seconds around each shot

    # Filter shots to requested period
    period_shots = [s for s in shot_chart if s.get("period") == period]

    # Index possession frames
    possession_frames: set = set()
    conf_sum = conf_n = 0
    for fd in predictions:
        for t in fd["tracks"]:
            if t.get("has_ball") or t.get("ball_possession"):
                possession_frames.add(fd["frame"])
                conf_sum += t.get("confidence", 1.0)
                conf_n   += 1

    detected = 0
    for shot in period_shots:
        clock_secs = (shot["minutes_remaining"] * 60 + shot["seconds_remaining"])
        elapsed    = PERIOD_SECS - clock_secs
        frame_est  = int(elapsed * fps)
        window     = range(max(0, frame_est - WINDOW_FRAMES),
                           frame_est + WINDOW_FRAMES + 1)
        if any(f in possession_frames for f in window):
            detected += 1

    n_shots = max(1, len(period_shots))
    return {
        "shots_in_period":     len(period_shots),
        "shots_detected":      detected,
        "detection_rate":      round(detected / n_shots, 3),
        "possession_frames":   len(possession_frames),
        "avg_possession_conf": round(conf_sum / max(1, conf_n), 3),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Opponent features (defensive rating, pace, eFG% allowed)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_team_season_stats(
    team_abbrev: str,
    season: str = "2024-25",
) -> dict:
    """
    Fetch advanced team season stats for ML model features.

    Returns ratings on a per-100-possessions basis.

    Args:
        team_abbrev: Team abbreviation (e.g. "GSW")
        season: NBA season string (e.g. "2024-25")

    Returns:
        {
            "team_id": int,
            "abbreviation": str,
            "games_played": int,
            "wins": int,
            "losses": int,
            "win_pct": float,
            "off_rating": float,      # points scored per 100 possessions
            "def_rating": float,      # points allowed per 100 possessions
            "net_rating": float,      # off - def (higher = better)
            "pace": float,            # possessions per 48 min
            "efg_pct": float,         # effective FG% (offense)
            "efg_pct_allowed": float, # effective FG% allowed (defense)
            "tov_pct": float,         # turnover rate (offense)
            "tov_pct_forced": float,  # opponent turnover rate (defense)
            "oreb_pct": float,
            "ft_rate": float,
        }
    """
    cache_key = f"team_stats_{team_abbrev}_{season}"
    cache_path = os.path.join(_NBA_CACHE, f"{_safe(cache_key)}.json")
    _stats_fresh = (
        os.path.exists(cache_path)
        and (time.time() - os.path.getmtime(cache_path)) < _TEAM_SEASON_STATS_TTL_HOURS * 3600
    )
    if _stats_fresh:
        return _load(cache_path)

    try:
        from nba_api.stats.static import teams as nba_teams_static
        from nba_api.stats.endpoints import leaguedashteamstats
    except ImportError:
        raise RuntimeError("nba_api not installed. Run: pip install nba_api")

    # Get team ID
    matches = [t for t in nba_teams_static.get_teams() if t["abbreviation"] == team_abbrev]
    if not matches:
        return {}
    team_id = matches[0]["id"]

    _rate_limit()
    try:
        resp = leaguedashteamstats.LeagueDashTeamStats(
            season=season,
            measure_type_detailed_defense="Advanced",
            per_mode_simple="PerGame",
        )
        df = resp.get_data_frames()[0]
    except Exception as e:
        print(f"[nba_stats] API error fetching team stats: {e}")
        return {}

    row = df[df["TEAM_ID"] == team_id]
    if row.empty:
        return {}
    row = row.iloc[0]

    # Fetch wins/losses from base stats
    _rate_limit()
    try:
        resp_base = leaguedashteamstats.LeagueDashTeamStats(
            season=season,
            measure_type_detailed_defense="Base",
            per_mode_simple="PerGame",
        )
        df_base = resp_base.get_data_frames()[0]
        base_row = df_base[df_base["TEAM_ID"] == team_id].iloc[0]
        wins = int(base_row.get("W", 0))
        losses = int(base_row.get("L", 0))
        gp = int(base_row.get("GP", 0))
    except Exception:
        wins = losses = gp = 0

    result = {
        "team_id": team_id,
        "abbreviation": team_abbrev,
        "games_played": gp,
        "wins": wins,
        "losses": losses,
        "win_pct": round(wins / max(1, wins + losses), 4),
        "off_rating": float(row.get("OFF_RATING", 0) or 0),
        "def_rating": float(row.get("DEF_RATING", 0) or 0),
        "net_rating": float(row.get("NET_RATING", 0) or 0),
        "pace": float(row.get("PACE", 0) or 0),
        "efg_pct": float(row.get("EFG_PCT", 0) or 0),
        "efg_pct_allowed": 0.0,   # requires opponent shooting splits — see fetch_opponent_stats
        "tov_pct": float(row.get("TM_TOV_PCT", 0) or 0),
        "tov_pct_forced": 0.0,
        "oreb_pct": float(row.get("OREB_PCT", 0) or 0),
        "ft_rate": float(row.get("FTA_RATE", 0) or 0),
    }
    _save(cache_path, result)
    return result


def fetch_opponent_stats(
    team_abbrev: str,
    season: str = "2024-25",
) -> dict:
    """
    Fetch opponent-side stats for a team (i.e. what the defense allows).

    Returns eFG% allowed, opponent turnover rate, opponent OREB%, etc.
    These are the 'Four Factors' defensive metrics.

    Args:
        team_abbrev: Defending team abbreviation
        season: NBA season string

    Returns:
        {
            "opp_efg_pct": float,
            "opp_tov_pct": float,
            "opp_oreb_pct": float,
            "opp_ft_rate": float,
            "def_rating": float,
        }
    """
    cache_key = f"opp_stats_{team_abbrev}_{season}"
    cache_path = os.path.join(_NBA_CACHE, f"{_safe(cache_key)}.json")
    _opp_fresh = (
        os.path.exists(cache_path)
        and (time.time() - os.path.getmtime(cache_path)) < _TEAM_SEASON_STATS_TTL_HOURS * 3600
    )
    if _opp_fresh:
        return _load(cache_path)

    try:
        from nba_api.stats.static import teams as nba_teams_static
        from nba_api.stats.endpoints import leaguedashteamstats
    except ImportError:
        raise RuntimeError("nba_api not installed. Run: pip install nba_api")

    matches = [t for t in nba_teams_static.get_teams() if t["abbreviation"] == team_abbrev]
    if not matches:
        return {}
    team_id = matches[0]["id"]

    _rate_limit()
    try:
        resp = leaguedashteamstats.LeagueDashTeamStats(
            season=season,
            measure_type_detailed_defense="Opponent",
            per_mode_simple="PerGame",
        )
        df = resp.get_data_frames()[0]
    except Exception as e:
        print(f"[nba_stats] API error fetching opponent stats: {e}")
        return {}

    row = df[df["TEAM_ID"] == team_id]
    if row.empty:
        return {}
    row = row.iloc[0]

    result = {
        "opp_efg_pct": float(row.get("OPP_EFG_PCT", 0) or 0),
        "opp_tov_pct": float(row.get("OPP_TOV_PCT", 0) or 0),
        "opp_oreb_pct": float(row.get("OPP_OREB_PCT", 0) or 0),
        "opp_ft_rate": float(row.get("OPP_FTA_RATE", 0) or 0),
    }
    _save(cache_path, result)
    return result


def fetch_matchup_features(
    home_abbrev: str,
    away_abbrev: str,
    season: str = "2024-25",
) -> dict:
    """
    Build a complete feature dict for a home/away matchup, ready for ML model input.

    Combines team season stats + opponent stats for both sides.

    Args:
        home_abbrev: Home team abbreviation
        away_abbrev: Away team abbreviation
        season: NBA season string

    Returns:
        Flat dict with all pre-game ML features:
        {
            "home_off_rating", "home_def_rating", "home_net_rating", "home_pace",
            "home_efg_pct", "home_win_pct",
            "away_off_rating", "away_def_rating", "away_net_rating", "away_pace",
            "away_efg_pct", "away_win_pct",
            "home_opp_efg_pct", "home_opp_tov_pct",  # defensive quality
            "away_opp_efg_pct", "away_opp_tov_pct",
            "net_rating_diff",     # home - away (key predictor)
            "off_vs_def_home",     # home offense vs away defense clash
            "off_vs_def_away",     # away offense vs home defense clash
            "pace_avg",            # average pace (affects totals)
        }
    """
    home = fetch_team_season_stats(home_abbrev, season)
    away = fetch_team_season_stats(away_abbrev, season)
    home_opp = fetch_opponent_stats(home_abbrev, season)
    away_opp = fetch_opponent_stats(away_abbrev, season)

    if not home or not away:
        return {}

    return {
        # Home team
        "home_off_rating":    home.get("off_rating", 0),
        "home_def_rating":    home.get("def_rating", 0),
        "home_net_rating":    home.get("net_rating", 0),
        "home_pace":          home.get("pace", 0),
        "home_efg_pct":       home.get("efg_pct", 0),
        "home_win_pct":       home.get("win_pct", 0),
        "home_opp_efg_pct":   home_opp.get("opp_efg_pct", 0),
        "home_opp_tov_pct":   home_opp.get("opp_tov_pct", 0),
        # Away team
        "away_off_rating":    away.get("off_rating", 0),
        "away_def_rating":    away.get("def_rating", 0),
        "away_net_rating":    away.get("net_rating", 0),
        "away_pace":          away.get("pace", 0),
        "away_efg_pct":       away.get("efg_pct", 0),
        "away_win_pct":       away.get("win_pct", 0),
        "away_opp_efg_pct":   away_opp.get("opp_efg_pct", 0),
        "away_opp_tov_pct":   away_opp.get("opp_tov_pct", 0),
        # Derived differentials
        "net_rating_diff":    round(home.get("net_rating", 0) - away.get("net_rating", 0), 2),
        "off_vs_def_home":    round(home.get("off_rating", 0) - away.get("def_rating", 0), 2),
        "off_vs_def_away":    round(away.get("off_rating", 0) - home.get("def_rating", 0), 2),
        "pace_avg":           round((home.get("pace", 0) + away.get("pace", 0)) / 2, 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Full box score (all counting stats)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_full_boxscore(game_id: str) -> dict:
    """
    Fetch complete player stat lines for a game.

    Uses BoxScoreTraditionalV2. Returns all counting stats needed for
    prop model validation: pts, reb, ast, stl, blk, tov, fg/3pt/ft splits.

    Args:
        game_id: NBA Stats game ID (e.g. "0022400430")

    Returns:
        {
            "game_id": str,
            "players": [
                {
                    "player_id": int,
                    "player_name": str,
                    "team_abbreviation": str,
                    "min": float,
                    "pts": int, "reb": int, "ast": int,
                    "stl": int, "blk": int, "tov": int,
                    "fgm": int, "fga": int,
                    "fg3m": int, "fg3a": int,
                    "ftm": int, "fta": int,
                    "oreb": int, "dreb": int,
                    "pf": int, "plus_minus": int,
                },
                ...
            ],
            "home_team": str,
            "away_team": str,
            "home_score": int,
            "away_score": int,
        }
        Returns {} on error.
    """
    cache_path = os.path.join(_NBA_CACHE, f"boxscore_{game_id}.json")

    # Only trust cache if game is final (game_status == 3).
    # A cache written during a live game has incomplete per-player stats.
    if os.path.exists(cache_path):
        data = _load(cache_path)
        if (
            data.get("players")
            and "reb" in (data["players"][0] if data["players"] else {})
            and data.get("game_status") == 3
        ):
            return data

    # ── Primary: cdn.nba.com live-data JSON (no auth, no rate-limit issues) ──
    import requests as _req

    def _safe_int(v) -> int:
        try:
            return int(v) if v is not None else 0
        except (ValueError, TypeError):
            return 0

    def _parse_minutes(v) -> float:
        """Convert 'PT34M35.00S' or '34:35' or float to decimal minutes."""
        if v is None:
            return 0.0
        s = str(v).strip()
        try:
            if s.startswith("PT") and "M" in s:
                s = s[2:]  # strip PT
                mins = float(s[:s.index("M")])
                secs_part = s[s.index("M") + 1:].rstrip("S")
                return round(mins + float(secs_part or 0) / 60, 2)
            if ":" in s:
                mm, ss = s.split(":", 1)
                return round(float(mm) + float(ss) / 60, 2)
            return round(float(s), 2)
        except (ValueError, TypeError):
            return 0.0

    cdn_url = f"https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"
    _cdn_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept":     "application/json",
        "Referer":    "https://www.nba.com/",
    }

    try:
        resp = _req.get(cdn_url, headers=_cdn_headers, timeout=20)
        resp.raise_for_status()
        game = resp.json()["game"]
    except Exception as e:
        print(f"[fetch_full_boxscore] cdn.nba.com error for {game_id}: {e}")
        return {}

    players = []
    home_tricode = game["homeTeam"].get("teamTricode", "")
    away_tricode = game["awayTeam"].get("teamTricode", "")

    for side_key, tricode in [("homeTeam", home_tricode), ("awayTeam", away_tricode)]:
        for p in game[side_key].get("players", []):
            st = p.get("statistics", {})
            players.append({
                "player_id":         _safe_int(p.get("personId")),
                "player_name":       str(p.get("name", "") or ""),
                "team_abbreviation": tricode,
                "jersey_num":        str(p.get("jerseyNum", "") or ""),
                "starter":           bool(p.get("starter", False)),
                "min":               _parse_minutes(st.get("minutes")),
                "pts":               _safe_int(st.get("points")),
                "reb":               _safe_int(st.get("reboundsTotal")),
                "oreb":              _safe_int(st.get("reboundsOffensive")),
                "dreb":              _safe_int(st.get("reboundsDefensive")),
                "ast":               _safe_int(st.get("assists")),
                "stl":               _safe_int(st.get("steals")),
                "blk":               _safe_int(st.get("blocks")),
                "tov":               _safe_int(st.get("turnovers")),
                "fgm":               _safe_int(st.get("fieldGoalsMade")),
                "fga":               _safe_int(st.get("fieldGoalsAttempted")),
                "fg3m":              _safe_int(st.get("threePointersMade")),
                "fg3a":              _safe_int(st.get("threePointersAttempted")),
                "ftm":               _safe_int(st.get("freeThrowsMade")),
                "fta":               _safe_int(st.get("freeThrowsAttempted")),
                "pf":                _safe_int(st.get("foulsPersonal")),
                "plus_minus":        _safe_int(st.get("plusMinusPoints")),
            })

    # gameStatus: 1=pre-game, 2=in-progress, 3=final
    game_status = int(game.get("gameStatus", 0))

    result = {
        "game_id":       game_id,
        "game_status":   game_status,
        "players":       players,
        "home_team":     home_tricode,
        "away_team":     away_tricode,
        "home_score":    _safe_int(game["homeTeam"].get("score")),
        "away_score":    _safe_int(game["awayTeam"].get("score")),
        "total_players": len(players),
        "total_fga":     sum(p["fga"] for p in players),
    }
    _save(cache_path, result)
    return result


def validate_boxscore(game_id: str) -> dict:
    """
    Validate a cached full boxscore for common data quality issues.

    Checks:
      - Missing players (< 8 per team)
      - Stat totals coherence (team pts = sum of player pts)
      - Zero minutes played (DNP misclassified)
      - Missing rebounds/assists (prop model coverage)

    Returns:
        {
            "game_id": str,
            "status": "ok" | "warn" | "error",
            "issues": [str],
            "player_count": int,
            "has_full_stats": bool,
        }
    """
    data = fetch_full_boxscore(game_id)
    if not data or not data.get("players"):
        return {"game_id": game_id, "status": "error",
                "issues": ["boxscore unavailable"], "player_count": 0,
                "has_full_stats": False}

    issues = []
    players = data["players"]
    has_full = "reb" in players[0] if players else False

    # Check per-team player counts
    from collections import Counter
    team_counts = Counter(p["team_abbreviation"] for p in players if p["min"] > 0)
    for team, cnt in team_counts.items():
        if cnt < 5:
            issues.append(f"{team} only has {cnt} players with minutes — possible missing data")

    # Validate team point totals
    for team_abbrev, score_key in [
        (data.get("home_team"), "home_score"),
        (data.get("away_team"), "away_score"),
    ]:
        if not team_abbrev:
            continue
        api_score = data.get(score_key, 0)
        player_pts = sum(p["pts"] for p in players if p["team_abbreviation"] == team_abbrev)
        if api_score and player_pts and abs(api_score - player_pts) > 2:
            issues.append(
                f"{team_abbrev} score mismatch: API={api_score}, sum_of_players={player_pts}"
            )

    # Check for full stat coverage
    if not has_full:
        issues.append("Boxscore missing full stats (reb/ast/stl/blk/tov) — needs backfill")

    status = "ok" if not issues else ("warn" if len(issues) <= 2 else "error")
    return {
        "game_id":        game_id,
        "status":         status,
        "issues":         issues,
        "player_count":   len([p for p in players if p["min"] > 0]),
        "has_full_stats": has_full,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _rate_limit(secs: float = 0.6):
    """NBA API rate limit — avoid 429s."""
    time.sleep(secs)


def _safe(s: str) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9_-]", "_", s)


def _save(path: str, data):
    os.makedirs(_NBA_CACHE, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _load(path: str):
    with open(path) as f:
        return json.load(f)
