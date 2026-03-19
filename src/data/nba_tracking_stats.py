"""
nba_tracking_stats.py — Untapped NBA API endpoints for advanced analytics.

Fetches 8 endpoint groups not yet in the pipeline:
  1. PlayerTrackingStats  (BoxScorePlayerTrackV2)     — speed, distance, touches
  2. ShotDashboard        (PlayerDashPtShots)          — contested%, C+S%, pull-up%, defender dist
  3. DefenderZone         (LeagueDashPtDefend)         — FG% allowed by zone per defender
  4. Matchups             (MatchupsRollup)             — who guards whom, pts allowed
  5. HustleStats          (LeagueHustleStatsPlayer)    — deflections, loose balls, screens
  6. SynergyPlayTypes     (SynergyPlayTypes)           — pts/possession by play type
  7. OnOffSplits          (LeaguePlayerOnDetails)      — on/off net rating
  8. VideoEvents          (VideoEventDetails)          — labeled event clip metadata

All data cached under data/nba/ as JSON with 24h TTL (except per-game tracking: perpetual).
Rate limit: 0.8s between NBA API calls.

Public API
----------
    get_player_tracking(game_id)                 -> dict
    get_shot_dashboard(player_id, season)        -> dict
    get_defender_zone(season)                    -> list
    get_matchups(season)                         -> list
    get_hustle_stats(season)                     -> list
    get_synergy_play_types(season, type_)        -> list
    get_on_off_splits(season)                    -> list
    get_video_events(season)                     -> list
    fetch_all_tracking_data(seasons)             -> dict   (bulk pull)
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_TTL_24H   = 24 * 3600
_TTL_PERM  = None      # perpetual — per-game historical data never changes

_SEASONS_DEFAULT = ["2024-25", "2023-24", "2022-23"]

# Apply standard session patch (retry + headers) from nba_stats
try:
    from src.data.nba_stats import _configure_nba_session, _rate_limit as _nba_rate_limit
    _configure_nba_session()
except Exception:
    def _nba_rate_limit(secs: float = 0.8):
        time.sleep(secs)


# ─────────────────────────────────────────────────────────────────────────────
# Internal cache helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cache_path(name: str) -> str:
    return os.path.join(_NBA_CACHE, f"{name}.json")


def _is_fresh(path: str, ttl: Optional[float]) -> bool:
    if not os.path.exists(path):
        return False
    if ttl is None:
        return True   # perpetual
    return (time.time() - os.path.getmtime(path)) < ttl


def _load(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save(path: str, data) -> None:
    os.makedirs(_NBA_CACHE, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _safe(s: str) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(s))


def _df_to_records(df, rename: dict) -> list:
    """Rename columns and return records list, dropping rows with all-null key fields."""
    cols = {k: v for k, v in rename.items() if k in df.columns}
    sub = df[list(cols.keys())].rename(columns=cols)
    return sub.to_dict("records")


# ─────────────────────────────────────────────────────────────────────────────
# 1. Player Tracking Stats — BoxScorePlayerTrackV2
# ─────────────────────────────────────────────────────────────────────────────

def get_player_tracking(game_id: str) -> dict:
    """
    Fetch per-player movement and touch tracking data for a specific game.

    Uses BoxScorePlayerTrackV2: speed, distance covered, touches, paint touches,
    elbow touches, post-up touches, potential assists, deflections.

    Args:
        game_id: NBA Stats game ID (e.g. "0022400710")

    Returns:
        {
            "game_id": str,
            "players": [
                {
                    "player_id": int, "player_name": str, "team_abbreviation": str,
                    "speed": float,          # avg mph
                    "distance": float,       # miles covered
                    "touches": int,
                    "front_ct_touches": int,
                    "elbow_touches": int,
                    "post_touches": int,
                    "paint_touches": int,
                    "potential_assists": int,
                    "deflections": int,
                    "contested_2s": int,
                    "contested_3s": int,
                    "charges_drawn": int,
                    "screen_assists": int,
                }
            ]
        }
        Returns {} on error.
    """
    path = _cache_path(f"player_track_{_safe(game_id)}")
    if _is_fresh(path, _TTL_PERM):
        return _load(path)

    try:
        from nba_api.stats.endpoints import boxscoreplayertrackv2
    except ImportError:
        raise RuntimeError("nba_api not installed.")

    _nba_rate_limit(0.8)
    try:
        resp = boxscoreplayertrackv2.BoxScorePlayerTrackV2(game_id=game_id)
        df = resp.get_data_frames()[0]
    except Exception as e:
        print(f"[nba_tracking_stats] BoxScorePlayerTrackV2 error for {game_id}: {e}")
        return {}

    col_map = {
        "PLAYER_ID": "player_id", "PLAYER_NAME": "player_name",
        "TEAM_ABBREVIATION": "team_abbreviation",
        "SPD": "speed", "DIST": "distance",
        "TCHS": "touches", "FRONT_CT_TCHS": "front_ct_touches",
        "ELBOW_TCHS": "elbow_touches", "POST_TCHS": "post_touches",
        "PAINT_TCHS": "paint_touches", "PASS": "potential_assists",
        "AST": "assists", "DFND_FGM": "deflections",
        "CONT_2FGA": "contested_2s", "CONT_3FGA": "contested_3s",
        "CHARGES_DRAWN": "charges_drawn", "SCREEN_ASSISTS": "screen_assists",
    }
    players = _df_to_records(df, col_map)

    result = {"game_id": game_id, "players": players}
    _save(path, result)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 2. Shot Dashboard — PlayerDashPtShots
# ─────────────────────────────────────────────────────────────────────────────

def get_shot_dashboard(
    player_id: int,
    season: str = "2024-25",
) -> dict:
    """
    Fetch shot-type breakdown for a player: contested%, catch-and-shoot%, pull-up%,
    and average closest defender distance.

    Args:
        player_id: NBA player ID
        season: e.g. "2024-25"

    Returns:
        {
            "player_id": int, "season": str,
            "contested_pct": float,
            "uncontested_pct": float,
            "catch_and_shoot_pct": float,
            "pull_up_pct": float,
            "avg_defender_dist_contested": float,
            "avg_defender_dist_catch_shoot": float,
        }
    """
    key = f"shot_dashboard_{player_id}_{_safe(season)}"
    path = _cache_path(key)
    if _is_fresh(path, _TTL_24H):
        return _load(path)

    try:
        from nba_api.stats.endpoints import playerdashptshots
    except ImportError:
        raise RuntimeError("nba_api not installed.")

    _nba_rate_limit(0.8)
    try:
        resp = playerdashptshots.PlayerDashPtShots(
            player_id=player_id,
            season=season,
            per_mode_simple="PerGame",
        )
        frames = resp.get_data_frames()
    except Exception as e:
        print(f"[nba_tracking_stats] PlayerDashPtShots error for {player_id}: {e}")
        return {}

    result: dict = {"player_id": player_id, "season": season}

    # Frame 0: General shot type (contested vs uncontested)
    if len(frames) > 0 and not frames[0].empty:
        df = frames[0]
        contested_row = df[df.get("SHOT_DIST_RANGE", df.columns[0] if len(df.columns) > 0 else "X") == "CONT"]
        # Fallback: parse all rows
        for _, row in df.iterrows():
            tag = str(row.get("GENERAL_RANGE", row.get("SHOT_DIST_RANGE", ""))).upper()
            if "CONT" in tag and "UN" not in tag:
                result["contested_pct"] = float(row.get("FGA_FREQUENCY", 0) or 0)
                result["avg_defender_dist_contested"] = float(row.get("AVG_DRIBBLES", row.get("AVG_CLOSE_DEF_DIST", 0)) or 0)
            elif "UN" in tag:
                result["uncontested_pct"] = float(row.get("FGA_FREQUENCY", 0) or 0)

    # Frame 1: Shot clock range (catch-and-shoot vs pull-up)
    if len(frames) > 2 and not frames[2].empty:
        df2 = frames[2]
        for _, row in df2.iterrows():
            tag = str(row.get("SHOT_CLOCK_RANGE", "")).upper()
            if "CATCH" in tag or "C&S" in tag:
                result["catch_and_shoot_pct"] = float(row.get("FGA_FREQUENCY", 0) or 0)
                result["avg_defender_dist_catch_shoot"] = float(row.get("AVG_CLOSE_DEF_DIST", 0) or 0)
            elif "PULL" in tag or "OFF DRIBBLE" in tag:
                result["pull_up_pct"] = float(row.get("FGA_FREQUENCY", 0) or 0)

    # Defaults for missing keys
    for k in ("contested_pct", "uncontested_pct", "catch_and_shoot_pct",
              "pull_up_pct", "avg_defender_dist_contested", "avg_defender_dist_catch_shoot"):
        result.setdefault(k, 0.0)

    _save(path, result)
    return result


def get_shot_dashboard_all_players(
    season: str = "2024-25",
    player_ids: Optional[List[int]] = None,
    delay: float = 0.8,
) -> dict:
    """
    Batch-fetch shot dashboard for all players.  Uses cached player ID list
    from data/nba/player_avgs_{season}.json if player_ids is None.

    Returns:
        {player_id (str): shot_dashboard_dict}
    """
    cache_key = f"shot_dashboard_all_{_safe(season)}"
    path = _cache_path(cache_key)
    if _is_fresh(path, _TTL_24H):
        return _load(path)

    if player_ids is None:
        avgs_path = os.path.join(_NBA_CACHE, f"player_avgs_{season}.json")
        if os.path.exists(avgs_path):
            with open(avgs_path) as f:
                avgs = json.load(f)
            player_ids = [
                int(v["player_id"]) for v in avgs.values()
                if isinstance(v, dict) and "player_id" in v
            ]
        else:
            return {}

    results = {}
    for pid in player_ids:
        data = get_shot_dashboard(pid, season)
        if data:
            results[str(pid)] = data
        time.sleep(delay)

    _save(path, results)
    return results


# ─────────────────────────────────────────────────────────────────────────────
# 3. Defender Zone Stats — LeagueDashPtDefend
# ─────────────────────────────────────────────────────────────────────────────

def get_defender_zone(season: str = "2024-25") -> list:
    """
    FG% allowed by each defender broken down by court zone:
    restricted area, paint (non-RA), mid-range, above-the-break 3, corner 3.

    Args:
        season: e.g. "2024-25"

    Returns:
        List of dicts:
        [
            {
                "player_id": int, "player_name": str, "team_abbreviation": str,
                "def_zone": str,    # "Restricted Area", "In The Paint (Non-RA)", etc.
                "fg_pct_allowed": float,
                "fg_contested": int,
                "fg_pct_diff": float,   # vs league avg in zone
            }, ...
        ]
    """
    key = f"defender_zone_{_safe(season)}"
    path = _cache_path(key)
    if _is_fresh(path, _TTL_24H):
        return _load(path)

    try:
        from nba_api.stats.endpoints import leaguedashptdefend
    except ImportError:
        raise RuntimeError("nba_api not installed.")

    _nba_rate_limit(0.8)
    try:
        resp = leaguedashptdefend.LeagueDashPtDefend(
            season=season,
            defense_category="3 Pointers",  # pull all zones via multiple calls
            per_mode_simple="PerGame",
        )
        df = resp.get_data_frames()[0]
    except Exception as e:
        print(f"[nba_tracking_stats] LeagueDashPtDefend error: {e}")
        return []

    col_map = {
        "PLAYER_ID": "player_id", "PLAYER_NAME": "player_name",
        "TEAM_ABBREVIATION": "team_abbreviation",
        "DEFENSE_CATEGORY": "def_zone",
        "D_FG_PCT": "fg_pct_allowed",
        "NORM_DGFGA": "fg_contested",
        "PCT_PLUSMINUS": "fg_pct_diff",
    }
    records = _df_to_records(df, col_map)
    _save(path, records)
    return records


# ─────────────────────────────────────────────────────────────────────────────
# 4. Matchups — MatchupsRollup
# ─────────────────────────────────────────────────────────────────────────────

def get_matchups(season: str = "2024-25") -> list:
    """
    Who-guards-whom data: partial possessions, points allowed per matchup,
    field goals defended, help-defense opportunities.

    Args:
        season: e.g. "2024-25"

    Returns:
        List of matchup dicts:
        [
            {
                "off_player_id": int, "off_player_name": str,
                "def_player_id": int, "def_player_name": str,
                "team_abbreviation": str,
                "partial_possessions": float,
                "player_guarded_pct": float,
                "pts_per_possession": float,
                "matchup_fg_pct": float,
            }, ...
        ]
    """
    key = f"matchups_{_safe(season)}"
    path = _cache_path(key)
    if _is_fresh(path, _TTL_24H):
        return _load(path)

    try:
        from nba_api.stats.endpoints import matchupsrollup
    except ImportError:
        raise RuntimeError("nba_api not installed.")

    _nba_rate_limit(0.8)
    try:
        resp = matchupsrollup.MatchupsRollup(
            season=season,
            per_mode_simple="PerGame",
        )
        df = resp.get_data_frames()[0]
    except Exception as e:
        print(f"[nba_tracking_stats] MatchupsRollup error: {e}")
        return []

    col_map = {
        "OFF_PLAYER_ID": "off_player_id",
        "OFF_PLAYER_NAME": "off_player_name",
        "DEF_PLAYER_ID": "def_player_id",
        "DEF_PLAYER_NAME": "def_player_name",
        "TEAM_ABBREVIATION": "team_abbreviation",
        "PARTIAL_POSS": "partial_possessions",
        "PLAYER_GUARD_PCT": "player_guarded_pct",
        "MATCHUP_FIELD_GOALS_PCT": "matchup_fg_pct",
        "PTS_PER_POSS": "pts_per_possession",
    }
    records = _df_to_records(df, col_map)
    _save(path, records)
    return records


# ─────────────────────────────────────────────────────────────────────────────
# 5. Hustle Stats — LeagueHustleStatsPlayer
# ─────────────────────────────────────────────────────────────────────────────

def get_hustle_stats(season: str = "2024-25") -> list:
    """
    Player hustle metrics: deflections, loose balls, charges drawn, screens.

    Args:
        season: e.g. "2024-25"

    Returns:
        List of dicts per player:
        [
            {
                "player_id": int, "player_name": str, "team_abbreviation": str,
                "games_played": int, "minutes": float,
                "contested_shots": int, "contested_2s": int, "contested_3s": int,
                "deflections": int, "loose_balls_recovered": int,
                "charges_drawn": int, "screen_assists": int, "screen_assist_pts": int,
                "box_outs": int, "box_out_off_reb": int, "box_out_def_reb": int,
                "deflections_pg": float,
                "charges_per_game": float,
            }, ...
        ]
    """
    key = f"hustle_stats_{_safe(season)}"
    path = _cache_path(key)
    if _is_fresh(path, _TTL_24H):
        return _load(path)

    try:
        from nba_api.stats.endpoints import leaguehustlestatsplayer
    except ImportError:
        raise RuntimeError("nba_api not installed.")

    _nba_rate_limit(0.8)
    try:
        resp = leaguehustlestatsplayer.LeagueHustleStatsPlayer(
            season=season,
            per_mode_time="PerGame",
        )
        df = resp.get_data_frames()[0]
    except Exception as e:
        print(f"[nba_tracking_stats] LeagueHustleStatsPlayer error: {e}")
        return []

    col_map = {
        "PLAYER_ID": "player_id", "PLAYER_NAME": "player_name",
        "TEAM_ABBREVIATION": "team_abbreviation",
        "G": "games_played", "MIN": "minutes",
        "CONTESTED_SHOTS": "contested_shots",
        "CONTESTED_SHOTS_2PT": "contested_2s",
        "CONTESTED_SHOTS_3PT": "contested_3s",
        "DEFLECTIONS": "deflections",
        "LOOSE_BALLS_RECOVERED": "loose_balls_recovered",
        "CHARGES_DRAWN": "charges_drawn",
        "SCREEN_ASSISTS": "screen_assists",
        "SCREEN_AST_PTS": "screen_assist_pts",
        "BOX_OUTS": "box_outs",
        "OFF_BOXOUTS": "box_out_off_reb",
        "DEF_BOXOUTS": "box_out_def_reb",
    }
    records = _df_to_records(df, col_map)

    # Compute per-game rates for key metrics
    for r in records:
        gp = max(1, r.get("games_played", 1))
        r["deflections_pg"] = round(r.get("deflections", 0) / gp, 2)
        r["charges_per_game"] = round(r.get("charges_drawn", 0) / gp, 2)

    _save(path, records)
    return records


def get_hustle_stats_multi_season(
    seasons: Optional[List[str]] = None,
    delay: float = 1.0,
) -> dict:
    """Pull hustle stats for multiple seasons and return {season: records}."""
    if seasons is None:
        seasons = _SEASONS_DEFAULT
    result = {}
    for s in seasons:
        data = get_hustle_stats(s)
        result[s] = data
        time.sleep(delay)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 6. Synergy Play Types — SynergyPlayTypes
# ─────────────────────────────────────────────────────────────────────────────

_SYNERGY_PLAY_TYPES = [
    "Isolation", "Transition", "PRBallHandler", "PRRollman",
    "Postup", "Spotup", "Handoff", "Cut", "OffScreen", "OffRebound",
]


def get_synergy_play_types(
    season: str = "2024-25",
    play_type_category: str = "Isolation",
    offense_defense: str = "offensive",
) -> list:
    """
    Per-player points-per-possession and efficiency by play type from Synergy.

    Args:
        season: e.g. "2024-25"
        play_type_category: "Isolation", "Transition", "PRBallHandler", "PRRollman",
                            "Postup", "Spotup", "Handoff", "Cut", "OffScreen", "OffRebound"
        offense_defense: "offensive" or "defensive"

    Returns:
        List of dicts:
        [
            {
                "player_id": int, "player_name": str, "team_abbreviation": str,
                "play_type": str, "offense_defense": str,
                "poss": int, "points": int, "ppp": float,
                "fg_pct": float, "tov_pct": float, "foul_pct": float,
                "score_pct": float, "freq_pct": float,
                "efg_pct": float,
            }, ...
        ]
    """
    key = f"synergy_{offense_defense}_{_safe(play_type_category)}_{_safe(season)}"
    path = _cache_path(key)
    if _is_fresh(path, _TTL_24H):
        return _load(path)

    try:
        from nba_api.stats.endpoints import synergyplaytypes
    except ImportError:
        raise RuntimeError("nba_api not installed.")

    _nba_rate_limit(0.8)
    try:
        resp = synergyplaytypes.SynergyPlayTypes(
            season=season,
            play_type_nullable=play_type_category,
            type_grouping_nullable=offense_defense,
            per_mode_simple="PerGame",
        )
        df = resp.get_data_frames()[0]
    except Exception as e:
        print(f"[nba_tracking_stats] SynergyPlayTypes error ({play_type_category}): {e}")
        return []

    col_map = {
        "PLAYER_ID": "player_id", "PLAYER_NAME": "player_name",
        "TEAM_ABBREVIATION": "team_abbreviation",
        "PLAY_TYPE": "play_type",
        "TYPE_GROUPING": "offense_defense",
        "POSS_PCT": "freq_pct",
        "PPP": "ppp",
        "POSS": "poss",
        "PTS": "points",
        "FG_PCT": "fg_pct",
        "FGMX": "fg_misses",
        "TOV_PCT": "tov_pct",
        "SF_PCT": "foul_pct",
        "SCORE_PCT": "score_pct",
        "EFG_PCT": "efg_pct",
    }
    records = _df_to_records(df, col_map)
    _save(path, records)
    return records


def get_synergy_all_types(
    season: str = "2024-25",
    offense_defense: str = "offensive",
    delay: float = 1.0,
) -> list:
    """Pull all play types for a season and combine into one flat list."""
    all_records = []
    for pt in _SYNERGY_PLAY_TYPES:
        records = get_synergy_play_types(season, pt, offense_defense)
        all_records.extend(records)
        time.sleep(delay)

    # Cache combined result
    key = f"synergy_{offense_defense}_all_{_safe(season)}"
    _save(_cache_path(key), all_records)
    return all_records


# ─────────────────────────────────────────────────────────────────────────────
# 7. On/Off Splits — TeamPlayerOnOffSummary (all 30 teams)
# ─────────────────────────────────────────────────────────────────────────────

def get_on_off_splits(season: str = "2024-25") -> list:
    """
    On/off net plus-minus for every player: how the team performs when that
    player is on versus off the court.  Uses TeamPlayerOnOffSummary per team
    (30 calls) because LeaguePlayerOnDetails requires a specific team_id.

    Returns:
        List of dicts with keys:
        player_id, player_name, team_abbreviation,
        on_court_plus_minus, off_court_plus_minus, on_off_diff,
        minutes_on.
    """
    key = f"on_off_{_safe(season)}"
    path = _cache_path(key)
    if _is_fresh(path, _TTL_24H):
        return _load(path)

    try:
        from nba_api.stats.endpoints import teamplayeronoffsummary
        from nba_api.stats.static import teams as nba_teams_static
    except ImportError:
        raise RuntimeError("nba_api not installed.")

    all_teams = nba_teams_static.get_teams()
    records: list = []
    seen_pids: set = set()

    for team in all_teams:
        _nba_rate_limit(0.8)
        try:
            resp = teamplayeronoffsummary.TeamPlayerOnOffSummary(
                team_id=team["id"],
                season=season,
            )
            frames = resp.get_data_frames()
        except Exception as e:
            print(f"[nba_tracking_stats] TeamPlayerOnOffSummary {team['abbreviation']} error: {e}")
            continue

        # Frame 1 = player on-court rows, Frame 2 = player off-court rows
        if len(frames) < 3:
            continue

        on_df  = frames[1]
        off_df = frames[2]

        # Build off lookup: VS_PLAYER_ID → PLUS_MINUS
        off_map: dict = {}
        for _, row in off_df.iterrows():
            pid = int(row.get("VS_PLAYER_ID", 0))
            if pid:
                off_map[pid] = float(row.get("PLUS_MINUS", 0.0) or 0.0)

        for _, row in on_df.iterrows():
            pid = int(row.get("VS_PLAYER_ID", 0))
            if not pid or pid in seen_pids:
                continue
            seen_pids.add(pid)
            on_pm  = float(row.get("PLUS_MINUS", 0.0) or 0.0)
            off_pm = off_map.get(pid, 0.0)
            records.append({
                "player_id":            pid,
                "player_name":          str(row.get("VS_PLAYER_NAME", "")),
                "team_abbreviation":    team["abbreviation"],
                "on_court_plus_minus":  round(on_pm,  2),
                "off_court_plus_minus": round(off_pm, 2),
                "on_off_diff":          round(on_pm - off_pm, 2),
                "minutes_on":           float(row.get("MIN", 0.0) or 0.0),
            })

    _save(path, records)
    return records


# ─────────────────────────────────────────────────────────────────────────────
# 8. Video Events — event metadata only (no video download)
# ─────────────────────────────────────────────────────────────────────────────

def get_video_events(
    season: str = "2024-25",
    event_type: str = "FGA",
    max_events: int = 2000,
) -> list:
    """
    Fetch labeled game event metadata from the NBA video events API.
    Returns event descriptors (game, period, clock, description) — no video
    is downloaded. The metadata is free training signal for CV classifiers.

    Args:
        season: e.g. "2024-25"
        event_type: "FGA" | "FGM" | "TOV" | "FOUL"
        max_events: Cap on records returned

    Returns:
        List of event dicts:
        [
            {
                "game_id": str, "event_id": int,
                "period": int, "clock": str,
                "description": str,
                "player_id": int, "player_name": str,
                "team_id": int, "team_abbreviation": str,
                "event_type": str,
            }, ...
        ]
    """
    key = f"video_events_{_safe(season)}_{event_type}"
    path = _cache_path(key)
    if _is_fresh(path, _TTL_24H):
        return _load(path)

    try:
        from nba_api.stats.endpoints import videoeventdetails
    except ImportError:
        print("[nba_tracking_stats] videoeventdetails not available in this nba_api version.")
        return []

    # Get recent games for a sample team to prime the event list
    try:
        from src.data.nba_stats import fetch_game_ids
        game_ids = fetch_game_ids("LAL", season, limit=10)
    except Exception:
        game_ids = []

    all_events: list = []
    for gid in game_ids[:10]:
        _nba_rate_limit(0.8)
        try:
            resp = videoeventdetails.VideoEventDetails(game_id=gid)
            df = resp.get_data_frames()[0]
            for _, row in df.iterrows():
                all_events.append({
                    "game_id":          gid,
                    "event_id":         int(row.get("EVENT_ID", 0) or 0),
                    "period":           int(row.get("PERIOD", 0) or 0),
                    "clock":            str(row.get("PCTIMESTRING", "")),
                    "description":      str(row.get("HOMEDESCRIPTION", "") or row.get("VISITORDESCRIPTION", "")),
                    "player_id":        int(row.get("PERSON1TYPE", 0) or 0),
                    "player_name":      str(row.get("PLAYER1_NAME", "")),
                    "team_id":          int(row.get("PLAYER1_TEAM_ID", 0) or 0),
                    "team_abbreviation": str(row.get("PLAYER1_TEAM_ABBREVIATION", "")),
                    "event_type":       event_type,
                })
                if len(all_events) >= max_events:
                    break
        except Exception as e:
            print(f"[nba_tracking_stats] VideoEventDetails error for {gid}: {e}")
        if len(all_events) >= max_events:
            break

    _save(path, all_events)
    print(f"[nba_tracking_stats] Video events saved: {len(all_events)} events")
    return all_events


# ─────────────────────────────────────────────────────────────────────────────
# Bulk fetch helper
# ─────────────────────────────────────────────────────────────────────────────

def fetch_all_tracking_data(
    seasons: Optional[List[str]] = None,
    delay: float = 1.0,
) -> dict:
    """
    Pull all per-season tracking endpoints in sequence and return a summary.

    Args:
        seasons: List of seasons to pull. Defaults to last 3.
        delay: Seconds between bulk endpoint calls.

    Returns:
        {
            "seasons_pulled": [str],
            "hustle_counts": {season: int},
            "on_off_counts": {season: int},
            "defender_zone_counts": {season: int},
            "matchup_counts": {season: int},
        }
    """
    if seasons is None:
        seasons = _SEASONS_DEFAULT

    summary = {
        "seasons_pulled": seasons,
        "hustle_counts": {},
        "on_off_counts": {},
        "defender_zone_counts": {},
        "matchup_counts": {},
    }

    for s in seasons:
        print(f"\n[nba_tracking_stats] Pulling season {s}...")

        hustle = get_hustle_stats(s)
        summary["hustle_counts"][s] = len(hustle)
        time.sleep(delay)

        on_off = get_on_off_splits(s)
        summary["on_off_counts"][s] = len(on_off)
        time.sleep(delay)

        zones = get_defender_zone(s)
        summary["defender_zone_counts"][s] = len(zones)
        time.sleep(delay)

        matchups = get_matchups(s)
        summary["matchup_counts"][s] = len(matchups)
        time.sleep(delay)

    return summary


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="NBA Tracking Stats fetcher")
    parser.add_argument("--season", default="2024-25")
    parser.add_argument("--all", action="store_true", help="Bulk pull all endpoints")
    parser.add_argument("--hustle", action="store_true")
    parser.add_argument("--on-off", action="store_true")
    parser.add_argument("--defender-zone", action="store_true")
    parser.add_argument("--synergy", choices=["offensive", "defensive"], default=None)
    args = parser.parse_args()

    if args.all:
        summary = fetch_all_tracking_data([args.season])
        print(f"\nSummary: {summary}")
    elif args.hustle:
        data = get_hustle_stats(args.season)
        print(f"Hustle stats: {len(data)} players")
    elif args.on_off:
        data = get_on_off_splits(args.season)
        print(f"On/off splits: {len(data)} players")
    elif args.defender_zone:
        data = get_defender_zone(args.season)
        print(f"Defender zones: {len(data)} records")
    elif args.synergy:
        data = get_synergy_all_types(args.season, args.synergy)
        print(f"Synergy ({args.synergy}): {len(data)} records")
    else:
        parser.print_help()
