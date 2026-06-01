"""
player_props.py — Player prop models: pts, reb, ast, fg3m, stl, blk, tov (Phase 3/4).

Uses Bayesian rolling averages + opponent defensive rating + home/away splits
+ historical performance vs opponent as features.
XGBoost regressor per stat category.

Public API
----------
    predict_props(player_name, opp_team, season, n_games) -> dict
    train_props(season, force)                            -> dict
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Dict, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")

from src.data.injury_monitor import InjuryMonitor as _InjuryMonitor

_injury_monitor: _InjuryMonitor = _InjuryMonitor()  # module-level singleton

# Default stat averages when lookup fails
_STAT_DEFAULTS = {"pts": 14.0, "reb": 4.5, "ast": 3.2,
                  "fg3m": 1.2, "stl": 0.9, "blk": 0.5, "tov": 1.8}

# Bayesian shrinkage prior weight (games) — pulls rolling avg toward season avg
# when sample size is small (e.g. only 3 recent games)
_BAYES_K = 15

# Player game-log cache TTL: re-fetch after 24 hours so rolling form stays current.
_GAMELOG_TTL_HOURS = 24

# Season averages cache TTL: re-fetch after 24 hours so season stats stay current.
# This is a bulk cache (all players in one API call), so 24h is a reasonable balance
# between freshness and API rate-limit costs.
_PLAYER_AVGS_TTL_HOURS = 24


def _offline_mode() -> bool:
    """NBA_OFFLINE=1 forces stale cache use + default fallbacks instead of network fetch.

    Used by batch/backtest flows where stats.nba.com throttles or blocks requests,
    causing multi-minute hangs. A stale cache is always preferable to a hang.
    """
    return os.environ.get("NBA_OFFLINE", "0") == "1"


# ── Data helpers ───────────────────────────────────────────────────────────────

def _get_player_season_avgs(player_name: str, season: str) -> Optional[dict]:
    """
    Fetch season-to-date per-game averages from LeagueDashPlayerStats.

    Returns dict with pts, reb, ast, min, ts_pct or None on failure.
    Caches to data/nba/player_avgs_{season}.json.
    """
    cache_path = os.path.join(_NBA_CACHE, f"player_avgs_{season}.json")
    _avgs_fresh = (
        os.path.exists(cache_path)
        and (time.time() - os.path.getmtime(cache_path)) < _PLAYER_AVGS_TTL_HOURS * 3600
    )
    # Offline mode: serve stale cache instead of hitting nba.com (which may block).
    if _offline_mode() and os.path.exists(cache_path):
        _avgs_fresh = True
    if _avgs_fresh:
        with open(cache_path) as f:
            cache = json.load(f)
    else:
        cache = {}

    import unicodedata
    def _norm(s: str) -> str:
        return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()

    key = _norm(player_name)
    # Build normalized lookup from cache
    norm_cache = {_norm(k): v for k, v in cache.items()}
    if key in norm_cache:
        return norm_cache[key]

    if _offline_mode():
        return None

    try:
        from nba_api.stats.endpoints import leaguedashplayerstats
        time.sleep(0.6)
        df = leaguedashplayerstats.LeagueDashPlayerStats(
            season=season, per_mode_detailed="Totals"
        ).get_data_frames()[0]
        # Populate full cache in one shot — divide totals by GP to get per-game avgs.
        # Traded players appear multiple times (per-team rows + a TOT combined row).
        # Always keep the entry with the highest GP so TOT wins over partial-season rows.
        for _, row in df.iterrows():
            gp = max(int(row.get("GP", 1)), 1)
            key_name = _norm(row["PLAYER_NAME"])
            if key_name in cache and cache[key_name].get("gp", 0) >= gp:
                continue   # existing entry has more games — keep it (TOT row wins)
            cache[key_name] = {
                "player_id":  int(row["PLAYER_ID"]),
                "team":       row.get("TEAM_ABBREVIATION", ""),
                "gp":         gp,
                "min":        float(row.get("MIN", 0)) / gp,
                "pts":        float(row.get("PTS", 0)) / gp,
                "reb":        float(row.get("REB", 0)) / gp,
                "ast":        float(row.get("AST", 0)) / gp,
                "tov":        float(row.get("TOV", 0)) / gp,
                "fg3m":       float(row.get("FG3M", 0)) / gp,
                "stl":        float(row.get("STL", 0)) / gp,
                "blk":        float(row.get("BLK", 0)) / gp,
                "fg_pct":     float(row.get("FG_PCT", 0)),
                "fg3_pct":    float(row.get("FG3_PCT", 0)),
                "ft_pct":     float(row.get("FT_PCT", 0)),
                "fta":        float(row.get("FTA", 0)) / gp,
            }
        os.makedirs(_NBA_CACHE, exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(cache, f)
        return cache.get(key)
    except Exception as e:
        print(f"  [props] player avgs fetch failed: {e}")
        return None


def _get_opp_def_rating(opp_team: str, season: str) -> float:
    """
    Return opponent's defensive rating.

    Lookup order:
    1. team_stats_{season}.json  — written by win_probability training (team_id keyed)
    2. opp_def_rtg_{season}.json — own cache keyed by team abbreviation
    3. Fetch from LeagueDashTeamStats Advanced and populate cache (2)
    4. League-average fallback (113.0)

    Lower def_rtg = better defense.
    """
    # 1. Primary: win-probability training cache (team_id keyed)
    primary = os.path.join(_NBA_CACHE, f"team_stats_{season}.json")
    if os.path.exists(primary):
        try:
            from nba_api.stats.static import teams as _teams
            with open(primary) as f:
                ts = json.load(f)
            abbrev_to_id = {t["abbreviation"]: str(t["id"]) for t in _teams.get_teams()}
            tid = abbrev_to_id.get(opp_team, "0")
            val = ts.get(tid, {}).get("def_rtg")
            if val is not None:
                return float(val)
        except Exception:
            pass

    # 2. Secondary: own abbrev-keyed cache
    secondary = os.path.join(_NBA_CACHE, f"opp_def_rtg_{season}.json")
    if os.path.exists(secondary):
        try:
            with open(secondary) as f:
                cache = json.load(f)
            if opp_team in cache:
                return float(cache[opp_team])
        except Exception:
            pass

    # 3. Fetch from NBA API and populate secondary cache
    if _offline_mode():
        return 113.0

    try:
        from nba_api.stats.endpoints import leaguedashteamstats
        time.sleep(0.6)
        df = leaguedashteamstats.LeagueDashTeamStats(
            season=season,
            measure_type_detailed_defense="Advanced",
            per_mode_simple="PerGame",
        ).get_data_frames()[0]
        cache = {}
        for _, row in df.iterrows():
            abbrev = str(row.get("TEAM_ABBREVIATION", ""))
            def_rtg = row.get("DEF_RATING")
            if abbrev and def_rtg is not None:
                cache[abbrev] = float(def_rtg)
        os.makedirs(_NBA_CACHE, exist_ok=True)
        with open(secondary, "w") as f:
            json.dump(cache, f)
        return float(cache.get(opp_team, 113.0))
    except Exception as e:
        print(f"  [props] opp def_rtg fetch failed: {e}")
        return 113.0


def _get_opp_stl_rate(opp_team: str, season: str) -> float:
    """Return opponent steals per possession from team_stats cache. Fallback: 0.08 (league avg).

    NOTE: team_stats_{season}.json (written by leaguedashteamstats) does NOT include
    stl_per_poss — this function always returns 0.08. The field would need to be added
    to the cache write in _fetch_team_stats (win_probability.py) to activate.
    Season-aggregate only; no per-date filtering needed since stl_per_poss is absent.
    """
    primary = os.path.join(_NBA_CACHE, f"team_stats_{season}.json")
    if os.path.exists(primary):
        try:
            with open(primary) as f:
                ts = json.load(f)
            from nba_api.stats.static import teams as _teams
            abbrev_to_id = {t["abbreviation"]: str(t["id"]) for t in _teams.get_teams()}
            tid = abbrev_to_id.get(opp_team, "0")
            row = ts.get(tid, {})
            if row and "stl_per_poss" in row:
                return float(row["stl_per_poss"])
        except Exception:
            pass
    return 0.08


def _get_opp_tov_stats(opp_team: str, season: str) -> dict:
    """Return opponent tov_pct and pace from team_stats cache. Fallbacks: tov_pct=0.145, pace=100.0."""
    primary = os.path.join(_NBA_CACHE, f"team_stats_{season}.json")
    if os.path.exists(primary):
        try:
            with open(primary) as f:
                ts = json.load(f)
            from nba_api.stats.static import teams as _teams
            abbrev_to_id = {t["abbreviation"]: str(t["id"]) for t in _teams.get_teams()}
            tid = abbrev_to_id.get(opp_team, "0")
            row = ts.get(tid, {})
            if row:
                return {
                    "opp_tov_pct": float(row.get("tov_pct", 0.145)),
                    "opp_pace":    float(row.get("pace",    100.0)),
                }
        except Exception:
            pass
    return {"opp_tov_pct": 0.145, "opp_pace": 100.0}


def _get_recent_form(player_id: int, season: str, n: int = 10) -> Optional[dict]:
    """
    Compute rolling n-game averages from PlayerGameLog.

    Returns dict with rolling avgs, n_games, and home/away splits, or None on failure.
    Includes: pts, reb, ast, min, fg3m, stl, blk, tov rolling averages.
    Home/away splits computed from MATCHUP column ('@' = away game).
    """
    cache_path = os.path.join(_NBA_CACHE, f"gamelog_{player_id}_{season}.json")
    _cache_fresh = (
        os.path.exists(cache_path)
        and (time.time() - os.path.getmtime(cache_path)) < _GAMELOG_TTL_HOURS * 3600
    )
    # Offline mode: serve stale cache rather than hanging on nba.com.
    if _offline_mode() and os.path.exists(cache_path):
        _cache_fresh = True
    if _cache_fresh:
        with open(cache_path) as f:
            rows = json.load(f)
    elif _offline_mode():
        return None
    else:
        try:
            from nba_api.stats.endpoints import playergamelog
            time.sleep(0.6)
            df = playergamelog.PlayerGameLog(
                player_id=player_id, season=season
            ).get_data_frames()[0]
            # MIN from PlayerGameLog is "MM:SS" string — convert to float minutes.
            def _parse_min(m) -> float:
                try:
                    if isinstance(m, str) and ":" in m:
                        parts = m.split(":")
                        return float(parts[0]) + float(parts[1]) / 60
                    return float(m)
                except (ValueError, IndexError):
                    return 0.0
            df = df.copy()
            df["MIN"] = df["MIN"].apply(_parse_min)
            keep_cols = [c for c in [
                "GAME_DATE", "MATCHUP", "PTS", "REB", "AST", "MIN",
                "FG3M", "STL", "BLK", "TOV",
            ] if c in df.columns]
            rows = df[keep_cols].to_dict("records")
            os.makedirs(_NBA_CACHE, exist_ok=True)
            with open(cache_path, "w") as f:
                json.dump(rows, f)
        except Exception as e:
            print(f"  [props] gamelog fetch failed: {e}")
            return None

    if not rows:
        return None
    # Sort by GAME_DATE descending so rows[:n] is truly the most recent games.
    if rows and "GAME_DATE" in rows[0]:
        from datetime import datetime as _dt

        def _parse_game_date(d: str):
            for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"):
                try:
                    return _dt.strptime(str(d).strip(), fmt)
                except ValueError:
                    continue
            return _dt.min

        rows = sorted(rows, key=lambda r: _parse_game_date(r["GAME_DATE"]), reverse=True)
    recent = rows[:n]

    def _to_min(m) -> float:
        try:
            if isinstance(m, str) and ":" in m:
                p = m.split(":")
                return float(p[0]) + float(p[1]) / 60
            return float(m)
        except (ValueError, IndexError):
            return 0.0

    def _avg(key: str, subset: list) -> float:
        if not subset:
            return 0.0
        return sum(float(r.get(key, 0)) for r in subset) / len(subset)

    ng = len(recent)

    # Home/away split: MATCHUP contains '@' for away games
    home_games = [r for r in recent if "@" not in str(r.get("MATCHUP", ""))]
    away_games = [r for r in recent if "@" in str(r.get("MATCHUP", ""))]

    import statistics as _stats
    stl_vals = [float(r.get("STL", 0)) for r in recent]
    stl_var = _stats.variance(stl_vals) if len(stl_vals) > 1 else 0.0

    result = {
        "pts_roll":  _avg("PTS", recent),
        "reb_roll":  _avg("REB", recent),
        "ast_roll":  _avg("AST", recent),
        "min_roll":  sum(_to_min(r.get("MIN", 0)) for r in recent) / ng,
        "fg3m_roll": _avg("FG3M", recent),
        "stl_roll":  _avg("STL", recent),
        "blk_roll":  _avg("BLK", recent),
        "tov_roll":  _avg("TOV", recent),
        "stl_consistency": stl_var,
        "n_games":   ng,
        # Home/away splits (None if no data for that split)
        "home_pts_avg": _avg("PTS", home_games) if home_games else None,
        "away_pts_avg": _avg("PTS", away_games) if away_games else None,
        "home_reb_avg": _avg("REB", home_games) if home_games else None,
        "away_reb_avg": _avg("REB", away_games) if away_games else None,
        "home_ast_avg": _avg("AST", home_games) if home_games else None,
        "away_ast_avg": _avg("AST", away_games) if away_games else None,
    }
    return result


def _get_opp_pts_vs_team(player_id: int, opp_team: str, season: str) -> Optional[dict]:
    """
    Return the player's historical per-game averages vs a specific opponent.

    Uses PlayerDashboardByOpponent (cached per player/season).
    Returns dict with pts_vs_opp, reb_vs_opp, ast_vs_opp or None on failure.
    """
    cache_path = os.path.join(_NBA_CACHE, f"opp_dashboard_{player_id}_{season}.json")
    _fresh = (
        os.path.exists(cache_path)
        and (time.time() - os.path.getmtime(cache_path)) < _PLAYER_AVGS_TTL_HOURS * 3600
    )
    if _fresh:
        try:
            with open(cache_path) as f:
                cache = json.load(f)
            row = cache.get(opp_team)
            if row:
                return row
        except Exception:
            pass

    # playerdashboardbyopponent was removed from nba_api — endpoint no longer exists.
    # This feature is optional; return None so callers use the fallback path.
    return None


def _load_clutch_stats(season: str) -> dict:
    """
    Load player clutch stats from data/nba/player_clutch_{season}.json.

    Returns dict keyed by player_id string, or {} if file absent.
    """
    path = os.path.join(_NBA_CACHE, f"player_clutch_{season}.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


# ── Phase 4.6 cache loaders ────────────────────────────────────────────────────

def _load_hustle_player(player_id: int, season: str) -> dict:
    """Load hustle stats for a single player by player_id. Returns {} on miss."""
    path = os.path.join(_NBA_CACHE, f"hustle_stats_{season}.json")
    try:
        records = json.load(open(path))
        # Records is a list of dicts with 'player_id' field (int)
        for r in records:
            if r.get("player_id") == player_id:
                return r
        return {}
    except Exception:
        return {}


def _load_on_off_player(player_id: int, season: str) -> dict:
    """Load on/off split record for a single player by player_id. Returns {} on miss."""
    path = os.path.join(_NBA_CACHE, f"on_off_{season}.json")
    try:
        records = json.load(open(path))
        for r in records:
            if r.get("player_id") == player_id:
                return r
        return {}
    except Exception:
        return {}


def _load_synergy_off(team_abbr: str, season: str) -> dict:
    """Load team offensive synergy, pivot by play_type → {team_iso_ppp, team_spotup_ppp, team_prbh_freq}.
    Returns {} on miss. Exact play_type values from cache: 'Isolation', 'Spotup', 'PRBallHandler'."""
    path = os.path.join(_NBA_CACHE, f"synergy_offensive_all_{season}.json")
    try:
        rows = json.load(open(path))
        team_rows = [r for r in rows if r.get("team_abbreviation", "").upper() == team_abbr.upper()]
        result = {}
        for r in team_rows:
            pt = r.get("play_type", "")
            if pt == "Isolation":
                result["team_iso_ppp"] = float(r.get("ppp", 0.0))
            elif pt == "Spotup":
                result["team_spotup_ppp"] = float(r.get("ppp", 0.0))
            elif pt == "PRBallHandler":
                result["team_prbh_freq"] = float(r.get("freq_pct", 0.0))
        return result
    except Exception:
        return {}


def _load_synergy_def(opp_team_abbr: str, season: str) -> dict:
    """Load opponent team defensive synergy. Returns {} on miss.
    Exact play_type values: 'Isolation', 'PRBallHandler'."""
    path = os.path.join(_NBA_CACHE, f"synergy_defensive_all_{season}.json")
    try:
        rows = json.load(open(path))
        team_rows = [r for r in rows if r.get("team_abbreviation", "").upper() == opp_team_abbr.upper()]
        result = {}
        for r in team_rows:
            pt = r.get("play_type", "")
            if pt == "Isolation":
                result["opp_def_iso_ppp"] = float(r.get("ppp", 0.0))
            elif pt == "PRBallHandler":
                result["opp_def_prbh_ppp"] = float(r.get("ppp", 0.0))
        return result
    except Exception:
        return {}


def _matchup_avg_fg(entry: dict) -> float:
    """Compute weighted average FG% from accumulated matchup entry."""
    tp = entry.get("total_poss", 0.0)
    return round(entry.get("wtd_fg_pct", 0.0) / tp, 4) if tp > 0 else 0.0


def _matchup_avg_pts(entry: dict) -> float:
    """Compute weighted average pts/poss from accumulated matchup entry."""
    tp = entry.get("total_poss", 0.0)
    return round(entry.get("wtd_pts_poss", 0.0) / tp, 4) if tp > 0 else 0.0


def _load_matchup_features(player_id: int, opp_team: str, season: str) -> dict:
    """
    Load matchup features for a player vs opponent team.
    Returns player's FG% and pts/poss when guarded, weighted by partial_possessions.
    Returns {} on miss.
    """
    path = os.path.join(_NBA_CACHE, f"matchups_{season}.json")
    try:
        rows = json.load(open(path))
        # Records where this player is the offensive player
        player_rows = [r for r in rows if r.get("off_player_id") == player_id]
        # Records where defender is from the opponent team
        opp_rows = [r for r in player_rows
                    if str(r.get("team_abbreviation", "")).upper() == opp_team.upper()]

        # Fallback to all matchups if no opp-specific data
        target = opp_rows if opp_rows else player_rows
        if not target:
            return {}

        total_poss = sum(float(r.get("partial_possessions", 1) or 1) for r in target)
        if total_poss <= 0:
            return {}

        w_fg_pct = sum(
            float(r.get("matchup_fg_pct", 0) or 0) * float(r.get("partial_possessions", 1) or 1)
            for r in target
        ) / total_poss
        w_pts_poss = sum(
            float(r.get("pts_per_possession", 0) or 0) * float(r.get("partial_possessions", 1) or 1)
            for r in target
        ) / total_poss

        return {
            "matchup_fg_pct_vs_opp":   round(w_fg_pct, 4),
            "matchup_pts_poss_vs_opp": round(w_pts_poss, 4),
        }
    except Exception:
        return {}


def _load_defender_zone_opp(opp_team: str, season: str) -> dict:
    """
    Load opponent team's average FG% allowed in restricted area and 3pt zones.
    Useful proxy for interior/perimeter defensive strength.
    Returns {} on miss.
    """
    path = os.path.join(_NBA_CACHE, f"defender_zone_{season}.json")
    try:
        rows = json.load(open(path))
        opp_rows = [r for r in rows
                    if str(r.get("team_abbreviation", "")).upper() == opp_team.upper()]
        if not opp_rows:
            return {}

        ra_pcts, three_pcts = [], []
        for r in opp_rows:
            zone = str(r.get("def_zone", "")).lower()
            fg_pct = float(r.get("fg_pct_allowed", 0) or 0)
            if "restricted" in zone:
                ra_pcts.append(fg_pct)
            elif "3" in zone or "above" in zone or "corner" in zone:
                three_pcts.append(fg_pct)

        result = {}
        if ra_pcts:
            result["opp_def_ra_fg_pct"] = round(sum(ra_pcts) / len(ra_pcts), 4)
        if three_pcts:
            result["opp_def_3pt_fg_pct"] = round(sum(three_pcts) / len(three_pcts), 4)
        return result
    except Exception:
        return {}


_LEAGUE_AVG_CONTESTED_PCT  = 0.45
_LEAGUE_AVG_DEFENDER_DIST  = 4.2

# Module-level cache: season → parsed JSON dict (loaded once per session)
_shot_dash_file_cache: dict = {}

# Group E: gamelogs_all cache — season → {player_id: [rows]}
_gamelogs_all_cache: dict = {}

# Group J: ATS data cache — season_str → {team: [cover_records]}
_ats_cache: dict = {}


def _load_shot_dashboard_player(player_id: int, season: str) -> dict:
    """
    Load shot dashboard features (A1 data): contested%, pull-up%, catch-shoot%, defender dist.
    avg_defender_dist = mean(contested_dist, catch_shoot_dist) — captures overall defensive pressure.
    Falls back to league averages when player not found (contested_pct=0.45, defender_dist=4.2).
    Returns league-average defaults if A1 pull has not completed for this season yet.
    """
    global _shot_dash_file_cache
    path = os.path.join(_NBA_CACHE, f"shot_dashboard_all_{season}.json")
    if season not in _shot_dash_file_cache:
        try:
            _shot_dash_file_cache[season] = json.load(open(path))
        except Exception:
            _shot_dash_file_cache[season] = {}
    d = _shot_dash_file_cache[season]
    row = d.get(str(player_id), {})
    if not row:
        # Player not found — use league averages so model gets real signal not zero
        return {
            "contested_pct":   _LEAGUE_AVG_CONTESTED_PCT,
            "pull_up_pct":     0.0,
            "catch_shoot_pct": 0.0,
            "avg_defender_dist": _LEAGUE_AVG_DEFENDER_DIST,
        }
    dist_contested   = float(row.get("avg_defender_dist_contested",   0.0) or 0.0)
    dist_catch_shoot = float(row.get("avg_defender_dist_catch_shoot", 0.0) or 0.0)
    # Average both distances; fall back to whichever is non-zero, then league avg
    if dist_contested > 0 and dist_catch_shoot > 0:
        avg_dist = (dist_contested + dist_catch_shoot) / 2.0
    else:
        avg_dist = dist_contested or dist_catch_shoot or _LEAGUE_AVG_DEFENDER_DIST
    return {
        "contested_pct":   float(row.get("contested_pct",         _LEAGUE_AVG_CONTESTED_PCT) or _LEAGUE_AVG_CONTESTED_PCT),
        "pull_up_pct":     float(row.get("pull_up_pct",           0.0) or 0.0),
        "catch_shoot_pct": float(row.get("catch_and_shoot_pct",   0.0) or 0.0),
        "avg_defender_dist": round(avg_dist, 3),
    }


def _load_tracking_player(player_id: int, season: str) -> dict:
    """
    Load season-level tracking features (A2 data): speed, distance, touches.
    Returns {} on miss.
    """
    path = os.path.join(_NBA_CACHE, f"player_tracking_{season}.json")
    try:
        rows = json.load(open(path))
        for r in rows:
            if r.get("player_id") == player_id:
                return {
                    "avg_speed":    float(r.get("speed", 0.0) or 0.0),
                    "dist_per_game": float(r.get("distance", 0.0) or 0.0),
                    "touches_pg":   float(r.get("touches", 0.0) or 0.0),
                }
        return {}
    except Exception:
        return {}


def _load_pbp_features(player_id: int, season: str) -> dict:
    """Load PBP-derived per-game features. Returns {} on miss."""
    path = os.path.join(_NBA_CACHE, f"pbp_features_{season}.json")
    try:
        d = json.load(open(path))
        return d.get(str(player_id), {})
    except Exception:
        return {}


def _load_shot_tendency(player_id: int) -> dict:
    """Load shot zone tendency features for a player. Returns {} on miss."""
    path = os.path.join(_NBA_CACHE, "shot_tendency_features.json")
    try:
        d = json.load(open(path))
        return d.get(str(player_id), {})
    except Exception:
        return {}


def _get_schedule_context_player(team_abbr: str, season: str) -> dict:
    """Compute rest_days and games_in_last_14 from schedule cache.
    Uses today's date as reference. Returns {rest_days: 1, games_in_last_14: 0} on miss.
    Schedule items have 'date' (ISO) and 'rest_days' (99 = season opener)."""
    import datetime
    _DEFAULT = {"rest_days": 1, "games_in_last_14": 0}
    try:
        # Try _v2 first, then plain
        for suffix in ("_v2", ""):
            path = os.path.join(_NBA_CACHE, "schedule",
                                f"schedule_{team_abbr}_{season}{suffix}.json")
            if os.path.exists(path):
                break
        else:
            return _DEFAULT

        schedule = json.load(open(path))
        if not isinstance(schedule, list):
            return _DEFAULT

        today = datetime.date.today()
        past_dates = []
        for g in schedule:
            raw_date = g.get("date", "")
            if not raw_date:
                continue
            try:
                d = datetime.date.fromisoformat(str(raw_date)[:10])
            except Exception:
                continue
            if d < today:
                past_dates.append(d)

        past_dates.sort(reverse=True)
        if not past_dates:
            return _DEFAULT

        # rest_days: days since last game (cap at 10 to match win_probability)
        raw_rest = (today - past_dates[0]).days
        rest_days = min(raw_rest, 10)

        # games_in_last_14
        cutoff = today - datetime.timedelta(days=14)
        games_in_last_14 = sum(1 for d in past_dates if d >= cutoff)

        return {"rest_days": rest_days, "games_in_last_14": games_in_last_14}
    except Exception:
        return _DEFAULT


# ── Group E helper: gamelogs_all loader ────────────────────────────────────────

def _load_gamelogs_all(season: str) -> dict:
    """Load & index gamelogs_all_{season}.json → {player_id_int: [rows]}. Cached."""
    global _gamelogs_all_cache
    if season in _gamelogs_all_cache:
        return _gamelogs_all_cache[season]
    path = os.path.join(_NBA_CACHE, f"gamelogs_all_{season}.json")
    if not os.path.exists(path):
        _gamelogs_all_cache[season] = {}
        return {}
    try:
        rows = json.load(open(path))
        index: dict = {}
        for r in rows:
            pid = int(r.get("player_id", 0))
            if pid:
                index.setdefault(pid, []).append(r)
        # Pre-sort each player's list by game_date descending
        for pid, rlist in index.items():
            index[pid] = sorted(rlist, key=lambda x: str(x.get("game_date", "")), reverse=True)
        _gamelogs_all_cache[season] = index
        return index
    except Exception:
        _gamelogs_all_cache[season] = {}
        return {}


# ── Group H helper: schedule hardship ──────────────────────────────────────────

_TEAM_TIMEZONE = {
    "ATL": "ET", "BOS": "ET", "BKN": "ET", "CHA": "ET", "CHI": "CT",
    "CLE": "ET", "DAL": "CT", "DEN": "MT", "DET": "ET", "GSW": "PT",
    "HOU": "CT", "IND": "ET", "LAC": "PT", "LAL": "PT", "MEM": "CT",
    "MIA": "ET", "MIL": "CT", "MIN": "CT", "NOP": "CT", "NYK": "ET",
    "OKC": "CT", "ORL": "ET", "PHI": "ET", "PHX": "MT", "POR": "PT",
    "SAC": "PT", "SAS": "CT", "TOR": "ET", "UTA": "MT", "WAS": "ET",
}
_TZ_OFFSET = {"ET": 0, "CT": 1, "MT": 2, "PT": 3}   # hours west of ET


def _tz_dist(team_a: str, team_b: str) -> int:
    """Return absolute timezone distance in hours between two team cities."""
    ta = _TEAM_TIMEZONE.get(team_a.upper(), "ET")
    tb = _TEAM_TIMEZONE.get(team_b.upper(), "ET")
    return abs(_TZ_OFFSET.get(ta, 0) - _TZ_OFFSET.get(tb, 0))


def _get_schedule_hardship(team_abbr: str, season: str) -> dict:
    """Compute road-trip context features. Returns defaults on miss."""
    import datetime
    _DEFAULT = {
        "road_trip_game_num": 0,
        "is_third_in_4_nights": 0,
        "cross_country_flag": 0,
        "days_since_home": 3,
    }
    try:
        for suffix in ("_v2", ""):
            path = os.path.join(_NBA_CACHE, "schedule",
                                f"schedule_{team_abbr}_{season}{suffix}.json")
            if os.path.exists(path):
                break
        else:
            return _DEFAULT

        schedule = json.load(open(path))
        if not isinstance(schedule, list):
            return _DEFAULT

        today = datetime.date.today()
        past_games = []
        for g in schedule:
            raw = g.get("date", "")
            if not raw:
                continue
            try:
                d = datetime.date.fromisoformat(str(raw)[:10])
            except Exception:
                continue
            if d < today:
                past_games.append((d, g))

        past_games.sort(key=lambda x: x[0], reverse=True)
        if not past_games:
            return _DEFAULT

        # road_trip_game_num: count consecutive away games ending at last game
        road_count = 0
        for _, g in past_games:
            matchup = str(g.get("matchup", ""))
            is_away = "@" in matchup
            if is_away:
                road_count += 1
            else:
                break

        # is_third_in_4_nights: 3 games in a 4-day window?
        if len(past_games) >= 3:
            dates = [d for d, _ in past_games[:3]]
            span = (dates[0] - dates[2]).days
            is_3in4 = 1 if span <= 4 else 0
        else:
            is_3in4 = 0

        # cross_country_flag: last game was 2+ tz zones away
        cross_country = 0
        if past_games:
            last_g = past_games[0][1]
            last_matchup = str(last_g.get("matchup", ""))
            # Extract opponent from matchup "TEAM @ OPP" or "TEAM vs. OPP"
            opp_abbr = ""
            if "@" in last_matchup:
                parts = last_matchup.split("@")
                opp_abbr = parts[-1].strip().split()[0].upper() if parts else ""
            elif "vs." in last_matchup:
                parts = last_matchup.split("vs.")
                opp_abbr = parts[-1].strip().split()[0].upper() if parts else ""
            if opp_abbr and _tz_dist(team_abbr, opp_abbr) >= 2:
                cross_country = 1

        # days_since_home: days since last home game
        days_since_home = 3
        for d, g in past_games:
            if "@" not in str(g.get("matchup", "")):
                days_since_home = (today - d).days
                break

        return {
            "road_trip_game_num":   road_count,
            "is_third_in_4_nights": is_3in4,
            "cross_country_flag":   cross_country,
            "days_since_home":      min(days_since_home, 30),
        }
    except Exception:
        return _DEFAULT


# ── Group J helper: ATS stats ───────────────────────────────────────────────────

def _load_ats_season(season_str: str) -> list:
    """Load historical_lines_{season}.json. Returns [] on miss."""
    global _ats_cache
    if season_str in _ats_cache:
        return _ats_cache[season_str]
    path = os.path.join(PROJECT_DIR, "data", "external", f"historical_lines_{season_str}.json")
    if not os.path.exists(path):
        _ats_cache[season_str] = []
        return []
    try:
        rows = json.load(open(path))
        _ats_cache[season_str] = rows
        return rows
    except Exception:
        _ats_cache[season_str] = []
        return []


def _load_cv_features_player(player_id: int, last_n: int = 5) -> dict:
    """
    Return averaged CV-derived features for a player across their last N tracked games.

    Reads from the cv_features DB table populated by cv_feature_registry.register_game().
    Falls back to all-zeros when no CV data exists (graceful degradation).

    Features returned (prefixed cv_ to avoid collision with NBA tracking stats):
      cv_avg_defender_distance   mean defender dist (pixels) at shot moment
      cv_contested_shot_rate     fraction of shots with defender < 150px
      cv_shot_zone_paint_pct     fraction of shots from paint
      cv_shot_zone_3pt_pct       fraction of shots from 3pt zones
      cv_shots_per_possession    shot creation rate
      cv_possession_duration_avg mean possession length (sec)
      cv_play_type_transition_pct fraction of team possessions in transition
      cv_n_games_cv              number of games contributing to these averages
    """
    _defaults = {
        "cv_avg_defender_distance":    0.0,
        "cv_contested_shot_rate":      0.0,
        "cv_shot_zone_paint_pct":      0.0,
        "cv_shot_zone_3pt_pct":        0.0,
        "cv_shots_per_possession":     0.0,
        "cv_possession_duration_avg":  0.0,
        "cv_play_type_transition_pct": 0.0,
        "cv_n_games_cv":               0.0,
    }
    _cv_key_map = {
        "avg_defender_distance":    "cv_avg_defender_distance",
        "contested_shot_rate":      "cv_contested_shot_rate",
        "shot_zone_paint_pct":      "cv_shot_zone_paint_pct",
        "shot_zone_3pt_pct":        "cv_shot_zone_3pt_pct",
        "shots_per_possession":     "cv_shots_per_possession",
        "possession_duration_avg":  "cv_possession_duration_avg",
        "play_type_transition_pct": "cv_play_type_transition_pct",
    }
    try:
        from src.data.db import get_connection
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT game_id FROM cv_features "
                "WHERE player_id = ? ORDER BY rowid DESC LIMIT ?",
                (player_id, last_n),
            )
            game_ids = [r[0] for r in cur.fetchall()]
        if not game_ids:
            conn.close()
            return _defaults.copy()
        # Aggregate: average each feature across the player's last N games
        accumulated: dict = {}
        counts: dict = {}
        for gid in game_ids:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT feature_name, feature_value FROM cv_features "
                    "WHERE player_id = ? AND game_id = ?",
                    (player_id, gid),
                )
                for fname, fval in cur.fetchall():
                    if fname in _cv_key_map:
                        out_key = _cv_key_map[fname]
                        accumulated[out_key] = accumulated.get(out_key, 0.0) + float(fval)
                        counts[out_key] = counts.get(out_key, 0) + 1
        conn.close()
        result = _defaults.copy()
        for key, total in accumulated.items():
            n = counts.get(key, 1)
            result[key] = round(total / n, 4)
        result["cv_n_games_cv"] = float(len(game_ids))
        return result
    except Exception:
        return _defaults.copy()


def _get_ats_stats(team: str, opp: str, season: str) -> dict:
    """
    Compute ATS cover rates for team and opponent across up to 3 seasons.
    Returns dict with team_ats_rate_l15, opp_ats_rate_l15, team_ats_as_favorite,
    line_move_direction for today's matchup.
    """
    # Build list of seasons to load
    try:
        yr1 = int(season.split("-")[0])
        seasons_to_load = [season, f"{yr1-1}-{str(yr1)[-2:]}",
                           f"{yr1-2}-{str(yr1-1)[-2:]}"]
    except Exception:
        seasons_to_load = [season]

    all_rows = []
    for s in seasons_to_load:
        all_rows.extend(_load_ats_season(s))

    def _covered_ats(row: dict, query_team: str) -> Optional[bool]:
        """Return True=covered, False=failed, None=push/skip."""
        home = str(row.get("home_team", "")).upper()
        away = str(row.get("away_team", "")).upper()
        try:
            closing = float(row.get("closing_spread", row.get("spread", 0)) or 0)
            h_score = float(row.get("home_score", 0) or 0)
            a_score = float(row.get("away_score", 0) or 0)
        except (TypeError, ValueError):
            return None
        margin = h_score - a_score
        qt = query_team.upper()
        if qt == home:
            # Home team covered if actual margin > -closing_spread
            return margin > -closing
        elif qt == away:
            return (a_score - h_score) > closing
        return None

    def _ats_rate_l15(query_team: str) -> float:
        team_rows = [r for r in all_rows
                     if str(r.get("home_team", "")).upper() == query_team
                     or str(r.get("away_team", "")).upper() == query_team]
        team_rows = sorted(team_rows, key=lambda r: str(r.get("date", "")), reverse=True)[:15]
        results = [_covered_ats(r, query_team) for r in team_rows]
        valid = [x for x in results if x is not None]
        return round(sum(valid) / len(valid), 4) if valid else 0.50

    def _ats_as_fav(query_team: str) -> float:
        team_rows = [r for r in all_rows
                     if str(r.get("home_team", "")).upper() == query_team
                     or str(r.get("away_team", "")).upper() == query_team]
        fav_rows = []
        for r in team_rows:
            try:
                spread = float(r.get("closing_spread", 0) or 0)
                home = str(r.get("home_team", "")).upper()
                # negative spread = home favored
                if query_team == home and spread < 0:
                    fav_rows.append(r)
                elif query_team != home and spread > 0:
                    fav_rows.append(r)
            except Exception:
                pass
        fav_rows = sorted(fav_rows, key=lambda r: str(r.get("date", "")), reverse=True)[:15]
        results = [_covered_ats(r, query_team) for r in fav_rows]
        valid = [x for x in results if x is not None]
        return round(sum(valid) / len(valid), 4) if valid else 0.50

    def _line_move(team: str, opp: str) -> float:
        """Find most recent matchup and return closing - open spread."""
        for r in sorted(all_rows, key=lambda x: str(x.get("date", "")), reverse=True):
            home = str(r.get("home_team", "")).upper()
            away = str(r.get("away_team", "")).upper()
            if {home, away} == {team.upper(), opp.upper()}:
                try:
                    closing = float(r.get("closing_spread", 0) or 0)
                    opening = float(r.get("open_spread", closing) or closing)
                    return round(closing - opening, 2)
                except Exception:
                    return 0.0
        return 0.0

    return {
        "team_ats_rate_l15":    _ats_rate_l15(team),
        "opp_ats_rate_l15":     _ats_rate_l15(opp),
        "team_ats_as_favorite": _ats_as_fav(team),
        "line_move_direction":  _line_move(team, opp),
    }


# ── Group I+D4 helper: pbp_features_expanded loader ────────────────────────────

def _load_pbp_features_expanded(player_id: int, season: str) -> dict:
    """Load expanded PBP features from pbp_features_expanded_{season}.json. Returns {} on miss."""
    path = os.path.join(_NBA_CACHE, f"pbp_features_expanded_{season}.json")
    try:
        d = json.load(open(path))
        return d.get(str(player_id), {})
    except Exception:
        return {}


# ── Feature builder ────────────────────────────────────────────────────────────

def _build_player_features(
    player_name: str,
    opp_team: str,
    season: str,
    n_games: int = 10,
    ref_names: Optional[list] = None,
    game_id: Optional[str] = None,
) -> Optional[dict]:
    """
    Build the feature vector for prop prediction.

    Core features (10):
      season_{pts,reb,ast,min}, {pts,reb,ast,min}_roll, opp_def_rtg, fg_pct

    Bayesian features (6):
      {pts,reb,ast,fg3m,stl,blk,tov}_bayes — Bayesian shrinkage toward season avg:
        bayes = n/(n+K) * roll + K/(n+K) * season_avg  where K=15

    Home/away splits (6):
      home_{pts,reb,ast}_avg, away_{pts,reb,ast}_avg

    Opponent-specific (3):
      pts_vs_opp, reb_vs_opp, ast_vs_opp

    Extended season averages (4):
      season_{fg3m,stl,blk,tov}
    """
    avgs = _get_player_season_avgs(player_name, season)
    if avgs is None:
        return None

    pid = avgs["player_id"]
    form = _get_recent_form(pid, season, n_games)
    opp_def = _get_opp_def_rating(opp_team, season)
    opp_hist = _get_opp_pts_vs_team(pid, opp_team, season)
    clutch = _load_clutch_stats(season).get(str(pid), {})

    # External: BBRef BPM + VORP + WS/48 (0.0 fallbacks when cache not yet populated)
    bbref_bpm = 0.0
    bbref_vorp = 0.0
    bbref_ws_per_48 = 0.0
    try:
        from src.data.bbref_scraper import get_player_bpm as _get_bpm
        _bpm_data = _get_bpm(player_name, season)
        bbref_bpm = float(_bpm_data.get("bpm", 0.0))
        bbref_vorp = float(_bpm_data.get("vorp", 0.0))
        bbref_ws_per_48 = float(_bpm_data.get("ws_per_48", 0.0))
    except Exception:
        pass

    # External: contract-year flag (0/1)
    try:
        from src.data.contracts_scraper import is_contract_year as _is_cy
        contract_year = 1.0 if _is_cy(player_name, season) else 0.0
    except Exception:
        contract_year = 0.0

    ng = form["n_games"] if form else 0
    k = _BAYES_K

    def _bayes(roll: float, season_avg: float) -> float:
        """Bayesian shrinkage: pull rolling avg toward season avg when n is small."""
        return round(ng / (ng + k) * roll + k / (ng + k) * season_avg, 2)

    feats = {
        # Player/team identity (not ML features — used for blowout_prob and injury lookups)
        "player_id": int(pid),
        "team": avgs.get("team", ""),
        # Core season averages
        "season_pts":   avgs["pts"],
        "season_reb":   avgs["reb"],
        "season_ast":   avgs["ast"],
        "season_min":   avgs["min"],
        "season_fg3m":  avgs.get("fg3m", 0.0),
        "season_stl":   avgs.get("stl", 0.0),
        "season_blk":   avgs.get("blk", 0.0),
        "season_tov":   avgs.get("tov", 0.0),
        # Raw rolling averages (kept for backward compat)
        "pts_roll":     form["pts_roll"]   if form else avgs["pts"],
        "reb_roll":     form["reb_roll"]   if form else avgs["reb"],
        "ast_roll":     form["ast_roll"]   if form else avgs["ast"],
        "min_roll":     form["min_roll"]   if form else avgs["min"],
        "stl_roll":     form["stl_roll"]   if form else avgs.get("stl", 0.0),
        "blk_roll":     form["blk_roll"]   if form else avgs.get("blk", 0.0),
        # Bayesian-shrunk rolling averages
        "pts_bayes":  _bayes(form["pts_roll"],  avgs["pts"])  if form else avgs["pts"],
        "reb_bayes":  _bayes(form["reb_roll"],  avgs["reb"])  if form else avgs["reb"],
        "ast_bayes":  _bayes(form["ast_roll"],  avgs["ast"])  if form else avgs["ast"],
        "fg3m_bayes": _bayes(form["fg3m_roll"], avgs.get("fg3m", 0.0)) if form else avgs.get("fg3m", 0.0),
        "stl_bayes":  _bayes(form["stl_roll"],  avgs.get("stl", 0.0))  if form else avgs.get("stl", 0.0),
        "blk_bayes":  _bayes(form["blk_roll"],  avgs.get("blk", 0.0))  if form else avgs.get("blk", 0.0),
        "tov_bayes":  _bayes(form["tov_roll"],  avgs.get("tov", 0.0))  if form else avgs.get("tov", 0.0),
        # Context
        "opp_def_rtg":  opp_def,
        "fg_pct":       avgs["fg_pct"],
        # Home/away splits (fall back to overall avg when not available)
        "home_pts_avg": form["home_pts_avg"] if form and form["home_pts_avg"] is not None else avgs["pts"],
        "away_pts_avg": form["away_pts_avg"] if form and form["away_pts_avg"] is not None else avgs["pts"],
        "home_reb_avg": form["home_reb_avg"] if form and form["home_reb_avg"] is not None else avgs["reb"],
        "away_reb_avg": form["away_reb_avg"] if form and form["away_reb_avg"] is not None else avgs["reb"],
        "home_ast_avg": form["home_ast_avg"] if form and form["home_ast_avg"] is not None else avgs["ast"],
        "away_ast_avg": form["away_ast_avg"] if form and form["away_ast_avg"] is not None else avgs["ast"],
        # Opponent-specific history (fall back to season avg when not available)
        "pts_vs_opp": opp_hist["pts_vs_opp"] if opp_hist else avgs["pts"],
        "reb_vs_opp": opp_hist["reb_vs_opp"] if opp_hist else avgs["reb"],
        "ast_vs_opp": opp_hist["ast_vs_opp"] if opp_hist else avgs["ast"],
        # Clutch stats (optional — fall back to 0.0 if not found for this player)
        "clutch_fg_pct":    float(clutch.get("clutch_fg_pct",   0.0)),
        "clutch_pts_pg":    float(clutch.get("clutch_pts_pg",   0.0)),
        "foul_drawn_rate":  float(clutch.get("foul_drawn_rate", 0.0)),
        # External factors
        "bbref_bpm":       bbref_bpm,
        "bbref_vorp":      bbref_vorp,
        "bbref_ws_per_48": bbref_ws_per_48,
        "contract_year":   contract_year,
        # Rolling window size (used for Bayesian weighting in predict_props)
        "n_games_form": ng,
    }

    # ── Phase 4.6: hustle stats ───────────────────────────────────────────────
    hustle = _load_hustle_player(pid, season)
    gp_hustle = max(float(hustle.get("games_played", 1) or 1), 1.0)
    # 'deflections_pg' is already per-game in cache; 'deflections' is total/game avg
    feats.update({
        "deflections_pg":       float(hustle.get("deflections_pg", 0.0) or 0.0),
        "contested_shots_pg":   float(hustle.get("contested_shots", 0.0) or 0.0),
        "screen_assists_pg":    float(hustle.get("screen_assists", 0.0) or 0.0),
        "charges_per_game":     float(hustle.get("charges_per_game", 0.0) or 0.0),
        "box_outs_pg":          float(hustle.get("box_outs", 0.0) or 0.0),
    })

    # ── STL-specific derived features ────────────────────────────────────────
    _stl_r = feats.get("stl_roll", 0.0)
    _blk_r = feats.get("blk_roll", 0.0)
    _min_r = max(feats.get("min_roll", 1.0), 1.0)
    feats["stl_per_min"]       = round(_stl_r / _min_r * 36, 4)
    feats["def_activity_rate"] = round((_stl_r + _blk_r) / _min_r, 4)
    feats["stl_consistency"]   = float(form.get("stl_consistency", 0.0)) if form else 0.0
    _opp_tov = _get_opp_tov_stats(opp_team, season)
    feats["opp_tov_pct"] = _opp_tov["opp_tov_pct"]
    feats["opp_pace"]    = _opp_tov["opp_pace"]
    feats["opp_stl_rate"] = _get_opp_stl_rate(opp_team, season)
    feats["player_pace_possessions"] = round(_min_r * _opp_tov["opp_pace"] / 48.0, 2)
    _fga_est = avgs["pts"] / max(2.0 * max(avgs["fg_pct"], 0.01), 0.01)
    feats["usg_pct"] = round(min(0.40, max(0.05, (
        _fga_est + 0.44 * avgs.get("fta", 0.0) + avgs.get("tov", 0.0)
    ) / max(_opp_tov["opp_pace"] * (_min_r / 48.0) * 5.0, 1.0))), 4)

    # ── Phase 4.6: on/off splits ─────────────────────────────────────────────
    on_off = _load_on_off_player(pid, season)
    feats.update({
        "on_off_diff":          float(on_off.get("on_off_diff", 0.0) or 0.0),
        "on_court_plus_minus":  float(on_off.get("on_court_plus_minus", 0.0) or 0.0),
    })

    # ── Phase 4.6: synergy ───────────────────────────────────────────────────
    team_abbr = avgs.get("team", "")
    syn_off = _load_synergy_off(team_abbr, season)
    syn_def = _load_synergy_def(opp_team, season)
    feats.update({
        "team_iso_ppp":     syn_off.get("team_iso_ppp",     0.0),
        "team_spotup_ppp":  syn_off.get("team_spotup_ppp",  0.0),
        "team_prbh_freq":   syn_off.get("team_prbh_freq",   0.0),
        "opp_def_iso_ppp":  syn_def.get("opp_def_iso_ppp",  0.0),
        "opp_def_prbh_ppp": syn_def.get("opp_def_prbh_ppp", 0.0),
    })

    # ── Phase B1: matchup features ───────────────────────────────────────────
    matchup = _load_matchup_features(pid, opp_team, season)
    feats.update({
        "matchup_fg_pct_vs_opp":   matchup.get("matchup_fg_pct_vs_opp",   0.0),
        "matchup_pts_poss_vs_opp": matchup.get("matchup_pts_poss_vs_opp", 0.0),
    })

    # ── Phase B1: opponent defender zone ─────────────────────────────────────
    def_zone = _load_defender_zone_opp(opp_team, season)
    feats.update({
        "opp_def_ra_fg_pct":   def_zone.get("opp_def_ra_fg_pct",   0.0),
        "opp_def_3pt_fg_pct":  def_zone.get("opp_def_3pt_fg_pct",  0.0),
    })

    # ── Phase B2: shot dashboard (A1 data — 0.0 until pull completes) ────────
    shot_dash = _load_shot_dashboard_player(pid, season)
    feats.update({
        "contested_pct":     shot_dash.get("contested_pct",     0.0),
        "pull_up_pct":       shot_dash.get("pull_up_pct",       0.0),
        "catch_shoot_pct":   shot_dash.get("catch_shoot_pct",   0.0),
        "avg_defender_dist": shot_dash.get("avg_defender_dist", 0.0),
    })

    # ── Phase B2: season tracking stats (A2 data) ─────────────────────────────
    tracking = _load_tracking_player(pid, season)
    feats.update({
        "avg_speed":     tracking.get("avg_speed",     0.0),
        "dist_per_game": tracking.get("dist_per_game", 0.0),
        "touches_pg":    tracking.get("touches_pg",    0.0),
    })

    # ── Phase 4.6: schedule context ──────────────────────────────────────────
    sched = _get_schedule_context_player(team_abbr, season)
    feats.update({
        "rest_days":        float(sched.get("rest_days", 1)),
        "games_in_last_14": float(sched.get("games_in_last_14", 0)),
    })

    # ── Pre-Phase 6: PBP features ─────────────────────────────────────────────
    pbp = _load_pbp_features(pid, season)
    feats.update({
        "q4_shot_rate":         float(pbp.get("q4_shot_rate", 0.0)),
        "q4_pts_share":         float(pbp.get("q4_pts_share", 0.0)),
        "fta_rate_pbp":         float(pbp.get("fta_rate_pbp", 0.0)),
        "foul_drawn_rate_pbp":  float(pbp.get("foul_drawn_rate_pbp", 0.0)),
        "comeback_pts_pg":      float(pbp.get("comeback_pts_pg", 0.0)),
    })

    # ── Pre-Phase 6: shot zone tendency features ──────────────────────────────
    szt = _load_shot_tendency(pid)
    feats.update({
        "paint_rate":               float(szt.get("paint_rate", 0.0)),
        "above_break_3_rate":       float(szt.get("above_break_3_rate", 0.0)),
        "corner_3_rate":            float(szt.get("corner_3_rate", 0.0)),
        "mid_rate":                 float(szt.get("mid_rate", 0.0)),
        "fg_pct_restricted_area":   float(szt.get("fg_pct_restricted_area", 0.0)),
    })

    # ── Sharp money: Pinnacle line movement ───────────────────────────────────
    pinnacle_move    = 0.0
    pinnacle_prob    = 0.5
    try:
        from src.data.pinnacle_monitor import get_prop_signal as _pinnacle
        _psig = _pinnacle(player_name, "pts")
        pinnacle_move = float(_psig.get("line_move", 0.0))
        pinnacle_prob = float(_psig.get("vig_free_prob", 0.5))
    except Exception:
        pass

    # ── Sharp money: Action Network public% / steam ───────────────────────────
    action_pub_pct   = 50.0
    action_steam     = 0.0
    try:
        from src.data.action_network import get_sharp_pct as _an
        _asig = _an(player_name, "pts")
        action_pub_pct = float(_asig.get("public_bets_pct", 50.0))
        action_steam   = 1.0 if _asig.get("steam_move", False) else 0.0
    except Exception:
        pass

    feats.update({
        "pinnacle_line_move":   pinnacle_move,   # + = over steam; - = under steam
        "pinnacle_over_prob":   pinnacle_prob,   # vig-free P(over) from Pinnacle
        "action_public_pct":    action_pub_pct,  # % public tickets on over (0–100)
        "action_steam_flag":    action_steam,    # 1 if reverse-line movement detected
    })

    # ── Beat reporter alerts ───────────────────────────────────────────────────
    beat_alert = 0.0
    try:
        from src.data.beat_reporter_monitor import has_injury_alert as _br_alert
        beat_alert = 1.0 if _br_alert(player_name, hours=3.0) else 0.0
    except Exception:
        pass

    feats["beat_reporter_alert"] = beat_alert

    # ── Referee tendency features ──────────────────────────────────────────────
    _league_avg_fouls = 44.0   # league-average total fouls per game (both teams)
    ref_fouls_pg    = _league_avg_fouls
    ref_home_wp     = 0.60
    ref_avg_pace    = 100.0
    ref_fta_adj     = 1.0

    try:
        from src.data.ref_tracker import get_ref_features as _ref_feats
        from src.data.referee_model import fetch_today_refs as _fetch_refs, get_referee_adjustments as _ref_adj

        # Resolve ref names: caller-supplied > today's game > model defaults
        _ref_names = ref_names or []
        if not _ref_names and game_id:
            _today_refs = _fetch_refs()
            _ref_names  = _today_refs.get(str(game_id), [])

        if _ref_names:
            rf = _ref_feats(_ref_names)
            if rf.get("refs_found", 0) > 0:
                ref_fouls_pg = float(rf.get("avg_fouls_per_game") or _league_avg_fouls)
                ref_home_wp  = float(rf.get("home_win_pct")       or 0.60)
                ref_avg_pace = float(rf.get("avg_pace")           or 100.0)
                ref_fta_adj  = round(ref_fouls_pg / _league_avg_fouls, 4)
    except Exception:
        pass

    feats.update({
        "ref_fouls_pg":    ref_fouls_pg,   # crew avg total fouls per game
        "ref_home_win_pct": ref_home_wp,   # crew home-team win% (0–1)
        "ref_avg_pace":    ref_avg_pace,   # crew avg pace (possessions/game)
        "ref_fta_adj":     ref_fta_adj,    # >1 = high-foul crew → more FTA → more pts
    })

    # ── Coaching rotation model ────────────────────────────────────────────────
    coach_exp_min   = feats.get("min_roll", feats.get("season_min", 24.0))
    coach_start_prob = 0.5
    coach_q4_prob   = 0.5

    try:
        from src.prediction.rotation_predictor import predict_rotation as _rot
        _blowout_p = _compute_blowout_prob(player_name, opp_team, season, feats)
        _rot_input = {
            "player_id":              feats.get("player_id", 0),
            "min_l10":                feats.get("min_roll", 24.0),
            "blowout_prob":           _blowout_p,
            "dnp_prob":               0.05,        # baseline; refined by DNP model later
            "min_reduction_foul":     0.0,
            "min_reduction_load":     feats.get("games_in_last_14", 0) * 0.3,
            "garbage_time_min_lost":  _blowout_p * 4.0,
        }
        _rot_out          = _rot(_rot_input)
        coach_exp_min     = float(_rot_out.get("expected_min",  coach_exp_min))
        coach_start_prob  = float(_rot_out.get("starter_prob",  0.5))
        coach_q4_prob     = float(_rot_out.get("q4_prob",       0.5))
    except Exception:
        pass

    feats.update({
        "coach_expected_min":  coach_exp_min,    # rotation-adjusted minutes projection
        "coach_starter_prob":  coach_start_prob, # P(player starts)
        "coach_q4_prob":       coach_q4_prob,    # P(plays in Q4 crunch time)
    })

    # ── Prop uncertainty: p25/p75 confidence intervals ────────────────────────
    try:
        from src.prediction.prop_uncertainty_estimator import predict_uncertainty as _unc
        _unc_out = _unc(feats)
        feats.update(_unc_out)  # adds pts_p25, pts_p75, reb_p25, reb_p75, etc.
    except Exception:
        for _s in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
            _base = feats.get(f"season_{_s}", 0.0)
            feats[f"{_s}_p25"] = round(max(_base * 0.6, 0.0), 2)
            feats[f"{_s}_p75"] = round(max(_base * 1.4, 0.0), 2)

    # ── Game possessions / pace ───────────────────────────────────────────────
    game_possessions = 100.0
    pace_z_score     = 0.0
    try:
        from src.prediction.game_possessions_model import predict_possessions as _poss
        _pout = _poss(feats.get("team", ""), opp_team, season, ref_names)
        game_possessions = float(_pout.get("expected_possessions", 100.0))
        pace_z_score     = float(_pout.get("pace_z_score", 0.0))
    except Exception:
        pass

    feats.update({
        "game_possessions": game_possessions,
        "pace_z_score":     pace_z_score,
    })

    # ── Foul draw rate by zone ────────────────────────────────────────────────
    foul_draw_rate_paint = 0.38
    fta_boost_vs_opp     = 0.0
    try:
        from src.prediction.foul_draw_rate_model import predict_fta_rate as _fdr
        _fdr_out = _fdr(pid, opp_team, season)
        foul_draw_rate_paint = float(_fdr_out.get("paint_fta_rate", 0.38))
        fta_boost_vs_opp     = float(_fdr_out.get("fta_boost_vs_opp", 0.0))
    except Exception:
        pass

    feats.update({
        "foul_draw_rate_paint": foul_draw_rate_paint,
        "fta_boost_vs_opp":     fta_boost_vs_opp,
    })

    # ── Usage surge detector ──────────────────────────────────────────────────
    usage_surge_prob  = 0.0
    usage_boost_est   = 0.0
    try:
        from src.prediction.usage_surge_detector import predict_surge as _surge
        _surge_out = _surge(player_name, opp_team, season)
        usage_surge_prob = float(_surge_out.get("surge_prob",       0.0))
        usage_boost_est  = float(_surge_out.get("usage_boost_est",  0.0))
    except Exception:
        pass

    feats.update({
        "usage_surge_prob": usage_surge_prob,
        "usage_boost_est":  usage_boost_est,
    })

    # ── Hot/cold streak detector ──────────────────────────────────────────────
    streak_type_hot   = 0.0
    streak_pts_delta  = 0.0
    reversion_prob    = 0.0
    try:
        from src.prediction.hot_cold_streak_detector import predict_streak as _streak
        _st_out = _streak(pid, season)
        streak_type_hot  = 1.0 if _st_out.get("streak_type") == "hot" else 0.0
        streak_pts_delta = float(_st_out.get("streak_pts_delta", 0.0))
        reversion_prob   = float(_st_out.get("reversion_prob",   0.0))
    except Exception:
        pass

    feats.update({
        "streak_type_hot":  streak_type_hot,   # 1 = player on hot streak
        "streak_pts_delta": streak_pts_delta,  # avg pts above/below season avg
        "reversion_prob":   reversion_prob,    # P(regression next game)
    })

    # ── Book bias correction ──────────────────────────────────────────────────
    book_bias_correction = 0.0
    try:
        from src.prediction.book_bias_detector import get_bias_for_player as _bias
        book_bias_correction = float(_bias(player_name, "pts", season))
    except Exception:
        pass

    feats["book_bias_correction"] = book_bias_correction

    # ── Season regression signal ──────────────────────────────────────────────
    regression_signal = 0.0
    try:
        from src.prediction.season_regression_detector import predict_regression as _reg
        _reg_out = _reg(player_name, season)
        regression_signal = float(_reg_out.get("regression_signal", 0.0))
    except Exception:
        pass

    feats["regression_signal"] = regression_signal

    # ── Possession outcome probs ──────────────────────────────────────────────
    player_shot_prob = 0.52
    player_tov_prob  = 0.14
    try:
        from src.prediction.possession_outcome_model import predict_outcome as _pout
        _po = _pout(pid, "other", "other", opp_team)
        player_shot_prob = float(_po.get("shot_prob", 0.52))
        player_tov_prob  = float(_po.get("tov_prob",  0.14))
    except Exception:
        pass

    feats.update({
        "player_shot_prob": player_shot_prob,
        "player_tov_prob":  player_tov_prob,
    })

    # ── Second half / quarter splits ──────────────────────────────────────────
    h2_pts_pct     = 0.50
    q4_pts_pct_mdl = feats.get("q4_pts_share", 0.25)  # seed from PBP features
    closer_score   = 0.0
    try:
        from src.prediction.second_half_adjustment_model import predict_half_split as _half
        _h_out = _half(pid, season)
        h2_pts_pct     = float(_h_out.get("h2_pts_pct",   0.50))
        q4_pts_pct_mdl = float(_h_out.get("q4_pts_pct",   q4_pts_pct_mdl))
        closer_score   = float(_h_out.get("closer_score",  0.0))
    except Exception:
        pass

    feats.update({
        "h2_pts_pct":       h2_pts_pct,       # fraction of pts scored in 2nd half
        "q4_pts_pct_model": q4_pts_pct_mdl,   # Q4 pts share (model-derived)
        "closer_score":     closer_score,      # 0-1; higher = late-game usage spike
    })

    # ── Playoff push intensity ────────────────────────────────────────────────
    playoff_push_prob = 0.0
    min_bonus_push    = 0.0
    try:
        from src.prediction.playoff_push_model import predict_playoff_push as _push
        _push_out = _push(feats.get("team", ""), season=season)
        playoff_push_prob = float(_push_out.get("push_prob",            0.0))
        min_bonus_push    = float(_push_out.get("expected_min_bonus",   0.0))
    except Exception:
        pass

    feats.update({
        "playoff_push_prob": playoff_push_prob,  # P(team in late playoff push)
        "min_bonus_push":    min_bonus_push,     # extra minutes from push context
    })

    # ── Defensive matchup classifier ──────────────────────────────────────────
    predicted_defender_def_rtg = feats.get("opp_def_rtg", 113.0)
    matchup_foul_rate          = 2.8
    try:
        from src.prediction.defensive_matchup_classifier import predict_defender as _def_cls
        _dc_out = _def_cls(player_name, opp_team, season)
        predicted_defender_def_rtg = float(_dc_out.get("defender_def_rtg",  predicted_defender_def_rtg))
        matchup_foul_rate          = float(_dc_out.get("defender_foul_rate", 2.8))
    except Exception:
        pass

    feats.update({
        "predicted_defender_def_rtg": predicted_defender_def_rtg,  # person-specific, not team avg
        "matchup_foul_rate":          matchup_foul_rate,            # defender fouls/game
    })

    # ── Beat reporter credibility ─────────────────────────────────────────────
    max_reporter_credibility = 0.0
    try:
        from src.prediction.beat_reporter_credibility import get_max_credibility_for_player as _cred
        max_reporter_credibility = float(_cred(player_name))
    except Exception:
        pass

    feats["max_reporter_credibility_score"] = max_reporter_credibility

    # ── Contract year quantifier ──────────────────────────────────────────────
    contract_pts_boost = 0.0
    contract_ast_boost = 0.0
    try:
        from src.prediction.contract_year_quantifier import predict_contract_boost as _cy_boost
        _cy_out = _cy_boost(player_name, season)
        contract_pts_boost = float(_cy_out.get("pts_boost", 0.0))
        contract_ast_boost = float(_cy_out.get("ast_boost", 0.0))
    except Exception:
        pass

    feats.update({
        "contract_pts_boost": contract_pts_boost,  # replaces binary contract_year
        "contract_ast_boost": contract_ast_boost,
    })

    # ── Group A: Game Context Models ──────────────────────────────────────────

    # A7: game models (must run first — game_spread_pred feeds A5)
    game_spread_pred    = 0.0
    game_total_pred     = 215.0
    game_blowout_pred   = 0.0
    game_pace_pred      = 100.0
    try:
        from src.prediction.game_models import predict as _gm_predict
        _gm_key = (team_abbr, opp_team, season)
        if _gm_key not in _game_models_cache:
            _game_models_cache[_gm_key] = _gm_predict(team_abbr, opp_team, season)
        _gm_out = _game_models_cache[_gm_key]
        game_spread_pred  = float(_gm_out.get("spread_est",   0.0))
        game_total_pred   = float(_gm_out.get("total_est",    215.0))
        game_blowout_pred = float(_gm_out.get("blowout_prob", 0.0))
        game_pace_pred    = float(_gm_out.get("pace_est",     100.0))
    except Exception:
        pass

    feats.update({
        "game_spread_pred":  game_spread_pred,
        "game_total_pred":   game_total_pred,
        "game_blowout_pred": game_blowout_pred,
        "game_pace_pred":    game_pace_pred,
    })

    # A1: back-to-back multipliers
    b2b_pts_mult = 1.0
    b2b_min_mult = 1.0
    try:
        from src.prediction.back_to_back_model import predict_b2b_mult as _b2b
        _is_b2b_val = 1 if feats.get("rest_days", 2) <= 1 else 0
        _b2b_in = dict(feats)
        _b2b_in["is_b2b"] = _is_b2b_val
        _b2b_out = _b2b(_b2b_in)
        b2b_pts_mult = float(_b2b_out.get("pts", 1.0))
        b2b_min_mult = float(_b2b_out.get("min", 1.0))
    except Exception:
        pass

    feats.update({
        "b2b_pts_mult": b2b_pts_mult,
        "b2b_min_mult": b2b_min_mult,
    })

    # A2: travel fatigue adjustment
    travel_adj = 1.0
    try:
        from src.prediction.travel_impact_model import predict_travel_adj as _travel
        _tr_out = _travel(feats)
        travel_adj = float(_tr_out.get("adj", 1.0) if isinstance(_tr_out, dict) else _tr_out)
    except Exception:
        pass

    feats["travel_adj"] = travel_adj

    # A3: altitude adjustment
    altitude_adj = 1.0
    try:
        from src.prediction.altitude_model import predict_altitude_adj as _alt
        _alt_in = dict(feats)
        _alt_in["opp_team"] = opp_team
        _alt_out = _alt(_alt_in)
        altitude_adj = float(_alt_out.get("adj", 1.0) if isinstance(_alt_out, dict) else _alt_out)
    except Exception:
        pass

    feats["altitude_adj"] = altitude_adj

    # A4: rest-day performance multiplier
    rest_day_mult = 1.0
    try:
        from src.prediction.rest_day_model import predict_rest_mult as _rest
        _rest_in = {"days_rest": feats.get("rest_days", 2)}
        _rest_out = _rest(_rest_in)
        rest_day_mult = float(_rest_out.get("mult", 1.0) if isinstance(_rest_out, dict) else _rest_out)
    except Exception:
        pass

    feats["rest_day_mult"] = rest_day_mult

    # A5: overtime probability (uses game_spread_pred set above by A7)
    ot_prob = 0.05
    try:
        from src.prediction.overtime_probability import predict_ot_prob as _ot
        _spread_mag = abs(feats.get("game_spread_pred", 5.0))
        _ot_out = _ot(_spread_mag)
        ot_prob = float(_ot_out.get("ot_prob", _ot_out) if isinstance(_ot_out, dict) else _ot_out)
    except Exception:
        pass

    feats["ot_prob"] = ot_prob

    # A6: garbage time
    garbage_time_prob     = 0.0
    garbage_time_min_lost = 0.0
    try:
        from src.prediction.garbage_time_detector import predict_garbage_time as _gt
        _gt_out = _gt(feats)
        garbage_time_prob     = float(_gt_out.get("garbage_time_prob",     0.0))
        garbage_time_min_lost = float(_gt_out.get("garbage_time_min_lost", 0.0))
    except Exception:
        pass

    feats.update({
        "garbage_time_prob":     garbage_time_prob,
        "garbage_time_min_lost": garbage_time_min_lost,
    })

    # ── Group B: Player Efficiency Models ─────────────────────────────────────

    # B1: usage rate
    usage_pct_pred = 0.20
    try:
        from src.prediction.usage_rate_model import predict_usage as _usg
        _usg_out = _usg(feats)
        usage_pct_pred = float(_usg_out.get("proj_usg_pct", 0.20))
    except Exception:
        pass

    feats["usage_pct_pred"] = usage_pct_pred

    # B2: true shooting %
    ts_pct_pred = 0.565
    try:
        from src.prediction.true_shooting_model import predict_ts as _ts
        _ts_out = _ts(feats)
        ts_pct_pred = float(_ts_out.get("proj_ts_pct", 0.565))
    except Exception:
        pass

    feats["ts_pct_pred"] = ts_pct_pred

    # B3: age discount
    age_discount = 1.0
    try:
        from src.prediction.age_curve_model import predict_age_discount as _age
        _age_out = _age(feats)
        age_discount = float(_age_out.get("discount", 1.0))
    except Exception:
        pass

    feats["age_discount"] = age_discount

    # B4: home/away boost
    ha_pts_boost = 0.0
    ha_min_boost = 0.0
    try:
        from src.prediction.home_away_model import predict_home_away as _ha
        _ha_out = _ha(feats)
        ha_pts_boost = float(_ha_out.get("pts", _ha_out.get("pts_boost", 0.0)))
        ha_min_boost = float(_ha_out.get("min", _ha_out.get("min_boost", 0.0)))
    except Exception:
        pass

    feats.update({
        "ha_pts_boost": ha_pts_boost,
        "ha_min_boost": ha_min_boost,
    })

    # B5: foul trouble
    foul_out_prob       = 0.0
    expected_foul_count = 2.5
    foul_min_reduction  = 0.0
    try:
        from src.prediction.foul_trouble_predictor import predict_foul_trouble as _ft
        _ft_out = _ft(int(pid), feats)
        foul_out_prob       = float(_ft_out.get("foul_out_prob",       0.0))
        expected_foul_count = float(_ft_out.get("expected_foul_count", 2.5))
        foul_min_reduction  = float(_ft_out.get("min_reduction",       0.0))
    except Exception:
        pass

    feats.update({
        "foul_out_prob":       foul_out_prob,
        "expected_foul_count": expected_foul_count,
        "foul_min_reduction":  foul_min_reduction,
    })

    # B6: minutes floor
    min_floor_pred = feats.get("season_min", 24.0)
    try:
        from src.prediction.minutes_floor_model import predict_minutes as _minf
        _minf_out = _minf(int(pid), feats)
        min_floor_pred = float(_minf_out.get("proj_min", feats.get("season_min", 24.0)))
    except Exception:
        pass

    feats["min_floor_pred"] = min_floor_pred

    # B7: load management probability
    load_mgmt_prob = 0.0
    try:
        from src.prediction.load_management import predict_load_management as _lm
        _lm_out = _lm(player_name, season)
        load_mgmt_prob = float(_lm_out.get("load_prob", 0.0))
    except Exception:
        pass

    feats["load_mgmt_prob"] = load_mgmt_prob

    # ── Group C: Player vs Matchup Models ─────────────────────────────────────

    # C1: matchup suppression score
    matchup_suppression_pct = 0.0
    try:
        from src.prediction.matchup_model import predict_matchup as _mm, get_defender_quality as _dq
        _def_name = feats.get("likely_defender_name", "")
        if _def_name:
            _mm_out = _mm(player_name, _def_name, season)
        else:
            _mm_out = _dq(opp_team, season)
        matchup_suppression_pct = float(_mm_out.get("pts_adj_pct", 0.0))
    except Exception:
        pass

    feats["matchup_suppression_pct"] = matchup_suppression_pct

    # C2: beneficiary cascade boost
    cascade_pts_boost = 0.0
    cascade_min_boost = 0.0
    try:
        from src.prediction.beneficiary_cascade import predict_beneficiary_boost as _bc
        _dnp_ids = []
        try:
            _inj = _injury_monitor.get_team_injuries(team_abbr)
            _dnp_ids = [
                int(p["player_id"]) for p in _inj
                if str(p.get("status", "")).lower() == "out" and p.get("player_id")
            ]
        except Exception:
            pass
        _all_ids = []
        try:
            _avgs_cache_path = os.path.join(_NBA_CACHE, f"player_avgs_{season}.json")
            if os.path.exists(_avgs_cache_path):
                with open(_avgs_cache_path) as _f:
                    _all_avgs = json.load(_f)
                _all_ids = [
                    int(v["player_id"]) for v in _all_avgs.values()
                    if v.get("team") == team_abbr and v.get("player_id")
                ]
        except Exception:
            pass
        _bc_out = _bc(team_abbr, _dnp_ids, _all_ids)
        _my_bc  = _bc_out.get(int(pid), {})
        cascade_pts_boost = float(_my_bc.get("pts_boost", 0.0))
        cascade_min_boost = float(_my_bc.get("min_boost", 0.0))
    except Exception:
        pass

    feats.update({
        "cascade_pts_boost": cascade_pts_boost,
        "cascade_min_boost": cascade_min_boost,
    })

    # ── Group D: Data Extractions ─────────────────────────────────────────────

    # D1: lineup net rating
    player_lineup_net_rtg = 0.0
    player_lineup_off_rtg = 100.0
    try:
        _lineup_path = os.path.join(_NBA_CACHE, "lineups", f"lineup_splits_{team_abbr}_{season}.json")
        if os.path.exists(_lineup_path):
            with open(_lineup_path) as _f:
                _lineups = json.load(_f)
            _pname_last = player_name.split()[-1].lower()
            _matched = [r for r in _lineups if any(_pname_last in str(p).lower() for p in r.get("lineup", []))]
            if _matched:
                _total_min = sum(float(r.get("minutes", 0)) for r in _matched)
                if _total_min > 0:
                    player_lineup_net_rtg = round(
                        sum(float(r.get("net_rating", 0)) * float(r.get("minutes", 0)) for r in _matched) / _total_min, 2
                    )
                    player_lineup_off_rtg = round(
                        sum(float(r.get("off_rating", 100)) * float(r.get("minutes", 0)) for r in _matched) / _total_min, 2
                    )
    except Exception:
        pass

    feats.update({
        "player_lineup_net_rtg": player_lineup_net_rtg,
        "player_lineup_off_rtg": player_lineup_off_rtg,
    })

    # D2: xFG luck delta
    xfg_weighted  = feats.get("fg_pct", 0.45)
    fg_luck_delta = 0.0
    try:
        _xfg_cal_path   = os.path.join(_NBA_CACHE, "xfg_calibration.json")
        _shot_tend_path = os.path.join(_NBA_CACHE, "shot_tendency_features.json")
        if os.path.exists(_xfg_cal_path) and os.path.exists(_shot_tend_path):
            with open(_xfg_cal_path) as _f:
                _xfg_cal = json.load(_f)
            with open(_shot_tend_path) as _f:
                _tend_all = json.load(_f)
            _tend = _tend_all.get(str(pid), {})
            if _tend:
                _zones = [
                    ("paint",         feats.get("paint_rate",         _tend.get("paint_rate",         0.0))),
                    ("above_break_3", feats.get("above_break_3_rate", _tend.get("above_break_3_rate", 0.0))),
                    ("corner_3",      feats.get("corner_3_rate",      _tend.get("corner_3_rate",      0.0))),
                    ("mid",           feats.get("mid_rate",           _tend.get("mid_rate",           0.0))),
                ]
                _xfg_sum = sum(
                    _rate * float(_xfg_cal.get(_zone, {}).get("pred_fg_pct", feats.get("fg_pct", 0.45)))
                    for _zone, _rate in _zones
                )
                xfg_weighted  = round(_xfg_sum, 4)
                fg_luck_delta = round(feats.get("fg_pct", xfg_weighted) - xfg_weighted, 4)
    except Exception:
        pass

    feats.update({
        "xfg_weighted":  xfg_weighted,
        "fg_luck_delta": fg_luck_delta,
    })

    # D3: opponent rolling 5-game defensive rating
    opp_def_rtg_l5 = feats.get("opp_def_rtg", 113.0)
    try:
        _scored_path = os.path.join(_NBA_CACHE, f"scored_games_{season}.json")
        if os.path.exists(_scored_path):
            with open(_scored_path) as _f:
                _games = json.load(_f)
            _opp_games = [g for g in _games if g.get("home_team") == opp_team or g.get("away_team") == opp_team]
            _opp_games = sorted(_opp_games, key=lambda g: str(g.get("game_date", "")), reverse=True)[:5]
            if _opp_games:
                _def_vals = [
                    float(g.get("home_def_rtg", feats.get("opp_def_rtg", 113.0)))
                    if g.get("home_team") == opp_team
                    else float(g.get("away_def_rtg", feats.get("opp_def_rtg", 113.0)))
                    for g in _opp_games
                ]
                opp_def_rtg_l5 = round(sum(_def_vals) / len(_def_vals), 2)
    except Exception:
        pass

    feats["opp_def_rtg_l5"] = opp_def_rtg_l5

    # ── Group E: Expanded Gamelog Features ───────────────────────────────────
    try:
        _gl_index = _load_gamelogs_all(season)
        _gl_rows = _gl_index.get(int(pid), [])[:10]  # already sorted desc
        if _gl_rows:
            def _gl_avg(key: str) -> float:
                vals = [float(r.get(key, 0) or 0) for r in _gl_rows]
                return round(sum(vals) / len(vals), 3) if vals else 0.0
            _fga_vals = [float(r.get("fga", 0) or 0) for r in _gl_rows]
            _fga_roll_val = round(sum(_fga_vals) / len(_fga_vals), 3) if _fga_vals else feats["season_pts"] / 0.47 * 0.45
            _fga5 = [float(r.get("fga", 0) or 0) for r in _gl_rows[:5]]
            _fga_trend_val = 0.0
            if len(_fga5) >= 2:
                import numpy as _np
                _xs = list(range(len(_fga5)))
                try:
                    _fga_trend_val = float(_np.polyfit(_xs, _fga5, 1)[0])
                except Exception:
                    pass
            _dd_count = sum(
                1 for r in _gl_rows
                if float(r.get("pts", 0) or 0) >= 10
                and (float(r.get("reb", 0) or 0) >= 10 or float(r.get("ast", 0) or 0) >= 10)
            )
            _min_vals = [float(r.get("min", 0) or 0) for r in _gl_rows]
            import statistics as _stats
            _min_var = round(_stats.stdev(_min_vals), 3) if len(_min_vals) >= 2 else 3.0
            feats.update({
                "oreb_roll":          _gl_avg("oreb"),
                "dreb_roll":          _gl_avg("dreb") if _gl_avg("dreb") else feats["season_reb"],
                "pf_roll":            _gl_avg("pf") if _gl_avg("pf") else 2.5,
                "fga_roll":           _fga_roll_val,
                "fg3a_roll":          _gl_avg("fg3a") if _gl_avg("fg3a") else feats.get("season_fg3m", 0) / 0.36,
                "fta_roll":           _gl_avg("fta") if _gl_avg("fta") else feats.get("fta", 3.0),
                "plus_minus_roll":    _gl_avg("plus_minus"),
                "min_variance":       _min_var,
                "fga_trend":          round(_fga_trend_val, 4),
                "double_double_rate": round(_dd_count / len(_gl_rows), 4),
            })
        else:
            feats.update({
                "oreb_roll": 0.0, "dreb_roll": feats["season_reb"],
                "pf_roll": 2.5,
                "fga_roll": feats["season_pts"] / 0.47 * 0.45,
                "fg3a_roll": feats.get("season_fg3m", 0) / max(0.36, 0.001),
                "fta_roll": feats.get("fta", 3.0),
                "plus_minus_roll": 0.0, "min_variance": 3.0,
                "fga_trend": 0.0, "double_double_rate": 0.0,
            })
    except Exception:
        feats.update({
            "oreb_roll": 0.0, "dreb_roll": feats.get("season_reb", 4.5),
            "pf_roll": 2.5, "fga_roll": 0.0, "fg3a_roll": 0.0,
            "fta_roll": 0.0, "plus_minus_roll": 0.0, "min_variance": 3.0,
            "fga_trend": 0.0, "double_double_rate": 0.0,
        })

    # ── Group F: Expanded Synergy Features ───────────────────────────────────
    try:
        def _syn_off_ppp(play_type: str) -> float:
            _path = os.path.join(_NBA_CACHE, f"synergy_offensive_all_{season}.json")
            try:
                _rows = json.load(open(_path))
                for r in _rows:
                    if (str(r.get("team_abbreviation", "")).upper() == team_abbr.upper()
                            and r.get("play_type", "") == play_type):
                        return float(r.get("ppp", 0.0))
            except Exception:
                pass
            return 0.0

        def _syn_def_ppp(play_type: str) -> float:
            _path = os.path.join(_NBA_CACHE, f"synergy_defensive_all_{season}.json")
            try:
                _rows = json.load(open(_path))
                for r in _rows:
                    if (str(r.get("team_abbreviation", "")).upper() == opp_team.upper()
                            and r.get("play_type", "") == play_type):
                        return float(r.get("ppp", 0.0))
            except Exception:
                pass
            return 0.0

        feats.update({
            "team_cut_ppp":           _syn_off_ppp("Cut")        or 1.0,
            "team_transition_ppp":    _syn_off_ppp("Transition") or 1.1,
            "team_postup_ppp":        _syn_off_ppp("Postup")     or 0.9,
            "team_handoff_ppp":       _syn_off_ppp("Handoff")    or 1.0,
            "team_rollman_ppp":       _syn_off_ppp("PRRollman")  or 1.0,
            "team_offscreen_ppp":     _syn_off_ppp("OffScreen")  or 0.9,
            "opp_def_cut_ppp":        _syn_def_ppp("Cut")        or 1.0,
            "opp_def_transition_ppp": _syn_def_ppp("Transition") or 1.1,
            "opp_def_postup_ppp":     _syn_def_ppp("Postup")     or 0.9,
            "opp_def_spotup_ppp":     _syn_def_ppp("Spotup")     or 1.0,
            "opp_def_rollman_ppp":    _syn_def_ppp("PRRollman")  or 1.0,
            "opp_def_offscreen_ppp":  _syn_def_ppp("OffScreen")  or 0.9,
        })
    except Exception:
        feats.update({
            "team_cut_ppp": 1.0, "team_transition_ppp": 1.1,
            "team_postup_ppp": 0.9, "team_handoff_ppp": 1.0,
            "team_rollman_ppp": 1.0, "team_offscreen_ppp": 0.9,
            "opp_def_cut_ppp": 1.0, "opp_def_transition_ppp": 1.1,
            "opp_def_postup_ppp": 0.9, "opp_def_spotup_ppp": 1.0,
            "opp_def_rollman_ppp": 1.0, "opp_def_offscreen_ppp": 0.9,
        })

    # ── Group G: Granular Shot Zone Features ─────────────────────────────────
    try:
        _szt2 = _load_shot_tendency(pid)
        feats.update({
            "fg_pct_left_corner_3":        float(_szt2.get("fg_pct_left_corner_3",        feats.get("fg_pct", 0.35))),
            "fg_pct_right_corner_3":       float(_szt2.get("fg_pct_right_corner_3",       feats.get("fg_pct", 0.35))),
            "fg_pct_range_less_than_8_ft": float(_szt2.get("fg_pct_range_less_than_8_ft", 0.60)),
            "fg_pct_range_8_16_ft":        float(_szt2.get("fg_pct_range_8_16_ft",        0.42)),
            "fg_pct_range_16_24_ft":       float(_szt2.get("fg_pct_range_16_24_ft",       0.40)),
            "rate_restricted_area":        float(_szt2.get("rate_restricted_area",        0.30)),
            "rate_mid_range":              float(_szt2.get("rate_mid_range",              feats.get("mid_rate", 0.20))),
        })
    except Exception:
        feats.update({
            "fg_pct_left_corner_3": feats.get("fg_pct", 0.35),
            "fg_pct_right_corner_3": feats.get("fg_pct", 0.35),
            "fg_pct_range_less_than_8_ft": 0.60,
            "fg_pct_range_8_16_ft": 0.42,
            "fg_pct_range_16_24_ft": 0.40,
            "rate_restricted_area": 0.30,
            "rate_mid_range": feats.get("mid_rate", 0.20),
        })

    # ── Group H: Schedule Hardship Features ──────────────────────────────────
    try:
        _hardship = _get_schedule_hardship(team_abbr, season)
        feats.update({
            "road_trip_game_num":   float(_hardship.get("road_trip_game_num",   0)),
            "is_third_in_4_nights": float(_hardship.get("is_third_in_4_nights", 0)),
            "cross_country_flag":   float(_hardship.get("cross_country_flag",   0)),
            "days_since_home":      float(_hardship.get("days_since_home",      3)),
        })
    except Exception:
        feats.update({
            "road_trip_game_num": 0.0, "is_third_in_4_nights": 0.0,
            "cross_country_flag": 0.0, "days_since_home": 3.0,
        })

    # ── Group I: Opponent Rolling Offensive Rating ────────────────────────────
    try:
        opp_off_rtg_l5 = feats.get("opp_def_rtg", 113.0)
        _scored_path = os.path.join(_NBA_CACHE, f"scored_games_{season}.json")
        if os.path.exists(_scored_path):
            with open(_scored_path) as _f:
                _sg = json.load(_f)
            _opp_g = [g for g in _sg if g.get("home_team") == opp_team or g.get("away_team") == opp_team]
            _opp_g = sorted(_opp_g, key=lambda g: str(g.get("game_date", "")), reverse=True)[:5]
            if _opp_g:
                _off_vals = [
                    float(g.get("home_off_rtg", feats.get("opp_def_rtg", 113.0)))
                    if g.get("home_team") == opp_team
                    else float(g.get("away_off_rtg", feats.get("opp_def_rtg", 113.0)))
                    for g in _opp_g
                ]
                opp_off_rtg_l5 = round(sum(_off_vals) / len(_off_vals), 2)
        feats["opp_off_rtg_l5"] = opp_off_rtg_l5
    except Exception:
        feats["opp_off_rtg_l5"] = feats.get("opp_def_rtg", 113.0)

    # ── Group J: Historical ATS Features ─────────────────────────────────────
    try:
        _ats = _get_ats_stats(team_abbr, opp_team, season)
        feats.update({
            "team_ats_rate_l15":    _ats.get("team_ats_rate_l15",    0.50),
            "opp_ats_rate_l15":     _ats.get("opp_ats_rate_l15",     0.50),
            "team_ats_as_favorite": _ats.get("team_ats_as_favorite", 0.50),
            "line_move_direction":  _ats.get("line_move_direction",  0.0),
        })
    except Exception:
        feats.update({
            "team_ats_rate_l15": 0.50, "opp_ats_rate_l15": 0.50,
            "team_ats_as_favorite": 0.50, "line_move_direction": 0.0,
        })

    # ── PBP Expanded Features ─────────────────────────────────────────────────
    try:
        _pbp_exp = _load_pbp_features_expanded(pid, season)
        feats.update({
            "assist_rate_pbp":       float(_pbp_exp.get("assist_rate_pbp",       0.0)),
            "paint_fg_rate_pbp":     float(_pbp_exp.get("paint_fg_rate_pbp",     0.0)),
            "fastbreak_pts_rate":    float(_pbp_exp.get("fastbreak_pts_rate",    0.0)),
            "clutch_pm_pbp":         float(_pbp_exp.get("clutch_pm_pbp",         0.0)),
            "foul_drawn_rate_pbp2":  float(_pbp_exp.get("foul_drawn_rate_pbp2",  0.0)),
        })
    except Exception:
        feats.update({
            "assist_rate_pbp": 0.0, "paint_fg_rate_pbp": 0.0,
            "fastbreak_pts_rate": 0.0, "clutch_pm_pbp": 0.0,
            "foul_drawn_rate_pbp2": 0.0,
        })

    # ── CV-derived spatial features (from broadcast tracking) ─────────────────
    # Populated once cv_feature_registry has data; zero-defaults until then.
    feats.update(_load_cv_features_player(int(pid)))
    # CSV-based spatial bridge: direct aggregate from data/features.csv
    try:
        from src.features.cv_feature_bridge import get_cv_features as _get_cv_features
        feats.update(_get_cv_features(player_name))
    except Exception:
        pass

    # ── Shot quality: xPTS_per_shot (fusion-layer feature) ────────────────────
    # Uses CV-trained ShotQualityModel; falls back to zone heuristic (conf=0.35)
    xpts_per_shot       = 0.0
    xpts_confidence     = 0.35
    try:
        from src.prediction.shot_quality import get_shot_quality_model as _sqm
        _sq = _sqm()
        _zone  = feats.get("shot_zone_primary", "mid_range")
        _ddist = feats.get("avg_defender_dist", 5.0) or 5.0
        _clk   = 12.0   # season-average; per-shot clock unavailable at prediction time
        _cs    = int(feats.get("catch_shoot_pct", 0.0) > 0.35)
        _, xpts_per_shot, xpts_confidence = _sq.predict(_zone, _ddist, _clk, _cs)
    except Exception:
        pass

    feats["xPTS_per_shot"]   = xpts_per_shot
    feats["xpts_confidence"] = xpts_confidence

    # ── CV_PROP_EXTRA_FEATURES flag: prop_line_movement + atlas features ──────
    # Gate: set CV_PROP_EXTRA_FEATURES=0 to disable; default is ON (full-send).
    # When OFF this block is completely skipped — feature assembly is byte-identical
    # to the pre-change path (proven no-op gate).
    _extra_on = os.environ.get("CV_PROP_EXTRA_FEATURES", "1").strip().lower() not in (
        "0", "false", "no", "off"
    )
    if _extra_on:
        # (a) prop_line_movement: 7 leak-safe line-drift features keyed on (player,
        #     stat, game_date, asof). On current data every call returns the neutral
        #     zero-vector (no data/lines/ CSVs overlap training dates) — a true no-op
        #     until intraday lines are captured alongside historical game dates.
        #     We wire only "pts" here because stat-split movement is not available in
        #     the current lines schema; extend later with per-stat asof loops.
        #     asof is left as None so the result is always the neutral vector
        #     (safe to wire regardless of data availability).
        try:
            from src.ingest.prop_line_movement import get_prop_line_movement as _get_plm
            _game_date = str(feats.get("game_date", ""))
            if not _game_date:
                import datetime as _datetime_mod
                _game_date = _datetime_mod.date.today().isoformat()
            # asof=None -> neutral zero vector (no leak possible; returns _NEUTRAL)
            _plm = _get_plm(player_name, "pts", _game_date, asof=None)
            for _k, _v in _plm.items():
                if _k not in feats:  # never overwrite existing columns
                    feats[_k] = float(_v)
        except Exception:
            pass

        # (b) atlas features: join leak-safe atlas_* columns using exactly the same
        #     call path as scripts/loop/eval_atlas_lift.py:_atlas_columns().
        #     We pass as_of=today (no historical row date available here) so the
        #     parquet fallback applies the row.as_of <= today guard — leak-safe.
        try:
            from src.loop.atlas_features import atlas_feature_row as _atlas_row
            import datetime as _dt_mod
            _as_of = str(feats.get("game_date", _dt_mod.date.today().isoformat()))
            _pid_int = int(feats.get("player_id", 0))
            if _pid_int:
                _atlas = _atlas_row(
                    _pid_int, _as_of,
                    entity_type="player",
                    sections=None,  # all registered player sections
                    store=None,     # process-wide store
                    prefix=True,
                )
                for _k, _v in _atlas.items():
                    # Only numeric leaves; never overwrite existing columns.
                    if _k not in feats and isinstance(_v, (int, float)):
                        feats[_k] = float(_v)
        except Exception:
            pass
    # ── end CV_PROP_EXTRA_FEATURES ─────────────────────────────────────────────

    return feats


# Per-session cache: (home_team, away_team, season) → blowout_prob
_blowout_cache: dict = {}

# Per-session cache: (home_team, away_team, season) → game_models predict() result
_game_models_cache: dict = {}


def _compute_blowout_prob(
    player_name: str,
    opp_team: str,
    season: str,
    feats: dict,
) -> float:
    """
    Estimate blowout probability using the WinProbModel.

    blowout_prob = P(home_win_prob > 0.75) + P(home_win_prob < 0.25)
    i.e. probability either team wins convincingly.

    Uses feats["team"] as home_team proxy.  Caches result per (home, away, season)
    to avoid repeated model loads during batch predictions.

    Falls back to 0.0 if the win_probability model is not found.
    """
    # Derive home/away teams: player's team vs opp.
    # Use avgs["team"] if available in feats; otherwise treat opp as away.
    home_team = feats.get("team", "")
    if not home_team:
        return 0.0

    cache_key = (home_team, opp_team, season)
    if cache_key in _blowout_cache:
        return _blowout_cache[cache_key]

    model_path = os.path.join(_MODEL_DIR, "win_probability.pkl")
    if not os.path.exists(model_path):
        _blowout_cache[cache_key] = 0.0
        return 0.0

    try:
        from src.prediction.win_probability import load as _load_wp
        wp_model = _load_wp(model_path)
        result   = wp_model.predict(home_team, opp_team, season)
        p_home   = result["home_win_prob"]
        prob     = round(float(p_home > 0.75) * p_home + float(p_home < 0.25) * (1 - p_home), 4)
        # Normalise: probability that this game becomes a blowout (either side)
        prob = round(max(p_home - 0.75, 0) + max(0.25 - p_home, 0), 4)
        _blowout_cache[cache_key] = prob
        return prob
    except Exception:
        _blowout_cache[cache_key] = 0.0
        return 0.0


# ── Prediction ─────────────────────────────────────────────────────────────────

def predict_props(
    player_name: str,
    opp_team: str,
    season: str = "2025-26",
    n_games: int = 10,
    ref_names: Optional[list] = None,
    game_id: Optional[str] = None,
) -> dict:
    """
    Predict pts, reb, ast, fg3m, stl, blk, tov for a player vs an opponent.

    Uses XGBoost models when available; falls back to Bayesian rolling averages,
    then season averages.

    Args:
        player_name: Full player name (e.g. "LeBron James").
        opp_team:    Opponent team abbreviation (e.g. "GSW").
        season:      NBA season string.
        n_games:     Rolling window for recent form.

    Returns:
        {
          "player":    str,
          "opp_team":  str,
          "pts":       float,
          "reb":       float,
          "ast":       float,
          "fg3m":      float,
          "stl":       float,
          "blk":       float,
          "tov":       float,
          "confidence": str,   # "pergame" | "season_avg_fallback" | "model" | "rolling" | "season" | "default"
          "features":  dict,
        }
    """
    feats = _build_player_features(player_name, opp_team, season, n_games,
                                    ref_names=ref_names, game_id=game_id)
    if feats is None:
        return {
            "player":    player_name,
            "opp_team":  opp_team,
            **{s: _STAT_DEFAULTS[s] for s in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")},
            "minutes_proj": None,
            "confidence": "default",
            "features":  {},
        }

    predictions, confidence = _predict_with_models(feats)

    # Prefer the per-game models — trained on real game logs (one row per
    # game, leakage-free), the honest measured task. The legacy season-average
    # models above remain the fallback when a player's gamelog is unavailable.
    _used_pergame = False
    try:
        from src.prediction.prop_pergame import predict_player_pergame
        _pid = feats.get("player_id")
        if _pid:
            _is_home = bool(feats.get("is_home", 1))
            _pg = predict_player_pergame(_pid, opp_team, season, is_home=_is_home)
            if _pg is not None:
                predictions = {s: round(max(float(_pg[s]), 0.0), 1) for s in _pg}
                confidence = "pergame"
                _used_pergame = True
    except Exception:  # noqa: BLE001 — never let the per-game path break a prediction
        pass
    confidence = _maybe_flag_fallback(_used_pergame, confidence)

    # ── Minutes-aware adjustment (PRED-19) ────────────────────────────────────
    # Scale counting-stat predictions by expected minutes / season average,
    # raised to per-stat elasticity. Rate stats untouched. Skips when the
    # player has no gamelog or season_min is unknown.
    expected_minutes_meta: Dict[str, float] = {}
    try:
        from src.prediction.minutes_aware_props import adjust_props_for_minutes  # noqa: PLC0415
        _pid = feats.get("player_id")
        _season_min = float(feats.get("season_min", 0.0) or 0.0)
        if _pid and _season_min > 0:
            _game_ctx = {
                "is_b2b": bool(feats.get("is_b2b", 0)),
                "rest_days": float(feats.get("rest_days", 2.0) or 2.0),
                "is_home": bool(feats.get("is_home", 1)),
                "opp_team": opp_team,
                "season": season,
            }
            _adjusted = adjust_props_for_minutes(
                predictions, int(_pid), _game_ctx, _season_min,
            )
            # Copy back the scaled counting stats; preserve the original confidence.
            for _stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
                if _stat in _adjusted:
                    predictions[_stat] = round(max(float(_adjusted[_stat]), 0.0), 1)
            # Surface the meta fields the post-process injected.
            for _k in ("expected_minutes", "p_dnp", "p_load_mgmt",
                       "minutes_factor", "minutes_std"):
                if _k in _adjusted:
                    expected_minutes_meta[_k] = _adjusted[_k]
    except Exception:  # noqa: BLE001 — never let minutes adjustment break a prediction
        pass

    # Bayesian minutes projection: pulls min_roll toward season_min when sample is small.
    # Same _BAYES_K constant used for all other Bayesian features.
    _min_roll   = feats.get("min_roll",    feats.get("season_min", 0.0))
    _min_season = feats.get("season_min",  0.0)
    _ng         = feats.get("n_games_form", _BAYES_K)  # falls back to K so weight splits 50/50
    minutes_proj = round(
        (_ng / (_ng + _BAYES_K)) * _min_roll
        + (_BAYES_K / (_ng + _BAYES_K)) * _min_season,
        1,
    )

    blowout_prob = _compute_blowout_prob(player_name, opp_team, season, feats)

    # ── Injury status (reporting only) ────────────────────────────────────────
    # The injury-availability dampener is applied ONCE upstream, inside
    # predict_player_pergame via apply_availability (single source of truth).
    # We surface status + multiplier as metadata here but DO NOT re-multiply the
    # predictions — doing so was a double/triple-application bug (combined
    # 0.60*0.70*0.65 ≈ 73% underestimate).
    player_id       = feats.get("player_id")
    injury_status   = _injury_monitor.get_status(player_id) if player_id else "Unknown"
    injury_mult     = _injury_monitor.get_impact_multiplier(player_id) if player_id else 1.0

    # ── DNP risk adjustment ───────────────────────────────────────────────────
    dnp_risk = 0.0
    try:
        from src.prediction.dnp_predictor import predict_dnp as _predict_dnp
        dnp_risk = _predict_dnp(player_name, season)
    except Exception:
        pass

    if dnp_risk > 0.4:
        # Scale predictions down: 30% max reduction at 100% DNP probability
        scale = 1.0 - 0.3 * dnp_risk
        for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
            if stat in predictions:
                predictions[stat] = round(predictions[stat] * scale, 1)

    return {
        "player":            player_name,
        "opp_team":          opp_team,
        **predictions,
        "minutes_proj":      minutes_proj,
        "blowout_prob":      blowout_prob,
        "dnp_risk":          round(dnp_risk, 4),
        "confidence":        confidence,
        **expected_minutes_meta,
        "injury_status":     injury_status,
        "injury_multiplier": injury_mult,
        "features":          feats,
    }


_ALL_FEATS = [
    # Core season averages
    "season_pts", "season_reb", "season_ast", "season_min",
    "season_fg3m", "season_stl", "season_blk", "season_tov",
    # Raw rolling averages
    "pts_roll", "reb_roll", "ast_roll", "min_roll",
    "stl_roll", "blk_roll",
    # STL-specific features
    "stl_per_min", "def_activity_rate", "stl_consistency",
    "opp_tov_pct", "opp_pace",
    "opp_stl_rate", "player_pace_possessions", "usg_pct",
    # Bayesian-shrunk rolling averages
    "pts_bayes", "reb_bayes", "ast_bayes",
    "fg3m_bayes", "stl_bayes", "blk_bayes", "tov_bayes",
    # Context
    "opp_def_rtg", "fg_pct",
    # Home/away splits
    "home_pts_avg", "away_pts_avg",
    "home_reb_avg", "away_reb_avg",
    "home_ast_avg", "away_ast_avg",
    # Opponent-specific history
    "pts_vs_opp", "reb_vs_opp", "ast_vs_opp",
    # Clutch stats (optional — 0.0 fallback when unavailable)
    "clutch_fg_pct", "clutch_pts_pg", "foul_drawn_rate",
    # External factors (Phase 5)
    "bbref_bpm", "bbref_vorp", "bbref_ws_per_48", "contract_year",
    # Phase 4.6: hustle stats
    "deflections_pg", "contested_shots_pg", "screen_assists_pg",
    "charges_per_game", "box_outs_pg",
    # Phase 4.6: on/off splits
    "on_off_diff", "on_court_plus_minus",
    # Phase 4.6: synergy play types
    "team_iso_ppp", "team_spotup_ppp", "team_prbh_freq",
    "opp_def_iso_ppp", "opp_def_prbh_ppp",
    # Phase 4.6: schedule context
    "rest_days", "games_in_last_14",
    # Pre-Phase 6: PBP features
    "q4_shot_rate", "q4_pts_share", "fta_rate_pbp", "foul_drawn_rate_pbp", "comeback_pts_pg",
    # Pre-Phase 6: shot zone tendency
    "paint_rate", "above_break_3_rate", "corner_3_rate", "mid_rate", "fg_pct_restricted_area",
    # Phase B1: matchup + defender zone
    "matchup_fg_pct_vs_opp", "matchup_pts_poss_vs_opp",
    "opp_def_ra_fg_pct", "opp_def_3pt_fg_pct",
    # Phase B2: shot dashboard + season tracking
    "contested_pct", "pull_up_pct", "catch_shoot_pct", "avg_defender_dist",
    "avg_speed", "dist_per_game", "touches_pg",
    # Sharp money: Pinnacle line movement + Action Network
    "pinnacle_line_move", "pinnacle_over_prob",
    "action_public_pct", "action_steam_flag",
    # Beat reporter injury alert
    "beat_reporter_alert",
    # Referee tendency
    "ref_fouls_pg", "ref_home_win_pct", "ref_avg_pace", "ref_fta_adj",
    # Coaching rotation model
    "coach_expected_min", "coach_starter_prob", "coach_q4_prob",
    # Tier A: prop uncertainty intervals (p25/p75 per stat)
    "pts_p25", "pts_p75", "reb_p25", "reb_p75", "ast_p25", "ast_p75",
    "fg3m_p25", "fg3m_p75", "stl_p25", "stl_p75", "blk_p25", "blk_p75",
    "tov_p25", "tov_p75",
    # Tier A: game possessions
    "game_possessions", "pace_z_score",
    # Tier A: foul draw rate by zone
    "foul_draw_rate_paint", "fta_boost_vs_opp",
    # Tier A: usage surge
    "usage_surge_prob", "usage_boost_est",
    # Tier A: hot/cold streak
    "streak_type_hot", "streak_pts_delta", "reversion_prob",
    # Tier B: book bias + season regression
    "book_bias_correction", "regression_signal",
    # Tier C: possession outcome probs
    "player_shot_prob", "player_tov_prob",
    # Tier C: second half splits
    "h2_pts_pct", "q4_pts_pct_model", "closer_score",
    # Tier C: playoff push
    "playoff_push_prob", "min_bonus_push",
    # Tier C: person-specific defender
    "predicted_defender_def_rtg", "matchup_foul_rate",
    # Tier D: beat reporter credibility
    "max_reporter_credibility_score",
    # Tier D: contract year quantified
    "contract_pts_boost", "contract_ast_boost",
    # Group A: game context models
    "game_spread_pred", "game_total_pred", "game_blowout_pred", "game_pace_pred",
    "b2b_pts_mult", "b2b_min_mult",
    "travel_adj",
    "altitude_adj",
    "rest_day_mult",
    "ot_prob",
    "garbage_time_prob", "garbage_time_min_lost",
    # Group B: player efficiency models
    "usage_pct_pred",
    "ts_pct_pred",
    "age_discount",
    "ha_pts_boost", "ha_min_boost",
    "foul_out_prob", "expected_foul_count", "foul_min_reduction",
    "min_floor_pred",
    "load_mgmt_prob",
    # Group C: player vs matchup models
    "matchup_suppression_pct",
    "cascade_pts_boost", "cascade_min_boost",
    # Group D: data extractions
    "player_lineup_net_rtg", "player_lineup_off_rtg",
    "xfg_weighted", "fg_luck_delta",
    "opp_def_rtg_l5",
    # Group E: expanded gamelog (10 games)
    "oreb_roll", "dreb_roll", "pf_roll", "fga_roll", "fg3a_roll", "fta_roll",
    "plus_minus_roll", "min_variance", "fga_trend", "double_double_rate",
    # Group F: expanded synergy offensive
    "team_cut_ppp", "team_transition_ppp", "team_postup_ppp",
    "team_handoff_ppp", "team_rollman_ppp", "team_offscreen_ppp",
    # Group F: expanded synergy defensive
    "opp_def_cut_ppp", "opp_def_transition_ppp", "opp_def_postup_ppp",
    "opp_def_spotup_ppp", "opp_def_rollman_ppp", "opp_def_offscreen_ppp",
    # Group G: granular shot zone FG%
    "fg_pct_left_corner_3", "fg_pct_right_corner_3",
    "fg_pct_range_less_than_8_ft", "fg_pct_range_8_16_ft", "fg_pct_range_16_24_ft",
    "rate_restricted_area", "rate_mid_range",
    # Group H: schedule hardship
    "road_trip_game_num", "is_third_in_4_nights", "cross_country_flag", "days_since_home",
    # Group I: opponent rolling offensive rating
    "opp_off_rtg_l5",
    # Group J: historical ATS
    "team_ats_rate_l15", "opp_ats_rate_l15", "team_ats_as_favorite", "line_move_direction",
    # PBP expanded
    "assist_rate_pbp", "paint_fg_rate_pbp", "fastbreak_pts_rate",
    "clutch_pm_pbp", "foul_drawn_rate_pbp2",
    # B-3: CV fatigue features (populated from features.csv when available)
    "fatigue_index_game_avg", "dist_traveled_game_total",
    # CV bridge: broadcast spatial aggregates from data/features.csv
    "cvb_avg_defender_dist", "cvb_avg_spacing", "cvb_avg_velocity",
    "cvb_fatigue_score", "cvb_paint_time_pct", "cvb_off_ball_dist",
    # CV spatial features (populated from broadcast tracking via cv_feature_registry)
    "cv_avg_defender_distance", "cv_contested_shot_rate",
    "cv_shot_zone_paint_pct", "cv_shot_zone_3pt_pct",
    "cv_shots_per_possession", "cv_possession_duration_avg",
    "cv_play_type_transition_pct",
    # Fusion layer: shot quality model (xPTS via CV-trained model + spatial prior)
    "xPTS_per_shot",
]


# ── D-5: Asymmetric loss objective (infrastructure — not active yet) ──────────
# This custom XGBoost objective penalises overconfident predictions more heavily
# than underconfident ones (alpha > 1). In betting, false edges cost more than
# missed edges. Wire as obj=_asymmetric_objective in any future retrain call.
#
# Usage:
#   from src.prediction.player_props import _asymmetric_objective
#   xgb.train(params, dtrain, obj=_asymmetric_objective)

import numpy as _np  # local alias to avoid polluting namespace


def _asymmetric_objective(y_true, y_pred, alpha: float = 1.3):
    """
    D-5: Asymmetric MSE objective for XGBoost.

    Penalises under-predictions (missed overs) by factor alpha vs over-predictions.
    alpha=1.3 means we care 30% more about false-over bets than false-under bets.

    Args:
        y_true:  Ground-truth values (numpy array).
        y_pred:  Predicted values (numpy array).
        alpha:   Asymmetry factor (>1 = penalise under-predictions more).

    Returns:
        (grad, hess) tuple for XGBoost custom objective.
    """
    residuals = y_true - y_pred
    grad = _np.where(residuals >= 0, -2.0 * alpha * residuals, -2.0 * residuals)
    hess = _np.where(residuals >= 0,  2.0 * alpha, 2.0) * _np.ones_like(grad)
    return grad, hess

# Stats modelled by XGBoost (each model excludes its own season_{stat} feature)
_PROP_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")


def _try_stacker_prediction(X, stat: str):
    """Return the multi-model stacker prediction for one stat, or None.

    Returns None when no trained stacker (``props_stacker_{stat}.pkl``) exists,
    so the caller cleanly falls back to the single XGBoost model — wiring the
    ensemble in is therefore zero-regression: it only takes effect once the
    LightGBM/CatBoost base learners and the stacker have been trained.
    """
    try:
        import numpy as np
        from src.prediction.prop_stacker import load_stacker, predict_ensemble

        if load_stacker(stat) is None:
            return None
        pred = predict_ensemble(np.asarray(X, dtype=float), stat)
        if pred is None or len(pred) == 0:
            return None
        v = float(pred[0])
        return v if np.isfinite(v) else None
    except Exception:
        return None


def _maybe_flag_fallback(used_pergame: bool, confidence: str) -> str:
    """Return 'season_avg_fallback' when the circular legacy models fired and pergame did not."""
    if not used_pergame and confidence in ("ensemble", "model"):
        return "season_avg_fallback"
    return confidence


def _predict_with_models(feats: dict) -> tuple:
    """
    Predict 7 prop stats. Prefers the trained multi-model stacker ensemble
    (XGBoost + LightGBM + CatBoost), then a single XGBoost model, then
    Bayesian rolling avg, then season avg.

    Returns (predictions_dict, confidence_str).
    """
    import numpy as np

    predictions = {}
    any_model = False
    used_stacker = False

    for stat in _PROP_STATS:
        # Drop season_{stat} from features — it IS the training label
        stat_feat_order = [c for c in _ALL_FEATS if c != f"season_{stat}"]
        X = np.array([[feats.get(k, 0.0) for k in stat_feat_order]])

        # 1. Multi-model stacker ensemble (when trained).
        val = _try_stacker_prediction(X, stat)
        if val is not None:
            any_model = True
            used_stacker = True

        # 2. Single XGBoost model (the long-standing path).
        model_path = os.path.join(_MODEL_DIR, f"props_{stat}.json")
        if val is None and os.path.exists(model_path):
            try:
                import xgboost as xgb
                m = xgb.XGBRegressor()
                m.load_model(model_path)
                val = float(m.predict(X)[0])
                any_model = True
            except Exception:
                pass

        if val is None:
            # Fallback priority: Bayesian avg → rolling avg → season avg
            for fallback_key in (f"{stat}_bayes", f"{stat}_roll", f"season_{stat}"):
                fb = feats.get(fallback_key)
                if fb is not None:
                    val = fb
                    break
            else:
                val = _STAT_DEFAULTS.get(stat, 0.0)

        predictions[stat] = round(max(val, 0.0), 1)

    confidence = "ensemble" if used_stacker else ("model" if any_model else "rolling")
    return predictions, confidence


# ── Training ───────────────────────────────────────────────────────────────────

def _build_prop_training_frame(
    seasons: list = None,
    exclude_player_ids: list = None,
) -> tuple:
    """Build (train_df, test_df, feat_cols) for prop-model training.

    Shared by every base learner (XGBoost / LightGBM / CatBoost) so each model
    trains on byte-identical data and the same temporal holdout split. Returns
    (None, None, None) when there is insufficient data (<100 rows).
    """
    import numpy as np
    import pandas as pd
    from src.prediction.prop_cv_split import (
        make_temporal_split, sort_chronologically, filter_excluded_players,
    )

    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    # Per-season fetch
    all_rows: list = []
    for season in seasons:
        print(f"  [props] Fetching {season} player stats...")
        avgs = _get_all_player_avgs(season)
        for row in avgs:
            row["season"] = season
            all_rows.append(row)
        time.sleep(0.5)

    if len(all_rows) < 100:
        print(f"  [props] Not enough data ({len(all_rows)} rows). Skipping training.")
        return (None, None, None)

    df = pd.DataFrame(all_rows)

    if exclude_player_ids:
        df = filter_excluded_players(df, exclude_player_ids)
        print(f"  [props] Excluded {len(exclude_player_ids)} player IDs from training set")

    feat_cols = list(_ALL_FEATS)

    # Simulate rolling-vs-season divergence with calibrated noise.
    # Without noise roll == season exactly → trivial identity model.
    _rng_form = np.random.default_rng(0)
    for col, scale in [
        ("pts", 0.15), ("reb", 0.12), ("ast", 0.20), ("min", 0.12),
        ("fg3m", 0.25), ("stl", 0.30), ("blk", 0.30), ("tov", 0.20),
    ]:
        noise = _rng_form.normal(0.0, scale, size=len(df))
        df[f"{col}_roll"] = (df[f"season_{col}"] * (1.0 + noise)).clip(lower=0.0)
        _n = 10.0
        df[f"{col}_bayes"] = (
            (_n / (_n + _BAYES_K)) * df[f"{col}_roll"]
            + (_BAYES_K / (_n + _BAYES_K)) * df[f"season_{col}"]
        ).round(2)

    # Home/away splits: simulate as season avg ± small noise for training
    _rng_ha = np.random.default_rng(1)
    for stat in ("pts", "reb", "ast"):
        for loc in ("home", "away"):
            noise = _rng_ha.normal(0.0, 0.08, size=len(df))
            df[f"{loc}_{stat}_avg"] = (df[f"season_{stat}"] * (1.0 + noise)).clip(lower=0.0)

    # Opp-specific: simulate as season avg ± small noise
    _rng_opp = np.random.default_rng(2)
    for stat in ("pts", "reb", "ast"):
        noise = _rng_opp.normal(0.0, 0.12, size=len(df))
        df[f"{stat}_vs_opp"] = (df[f"season_{stat}"] * (1.0 + noise)).clip(lower=0.0)

    # Sample real opponent def_rtg values
    all_def_rtgs: list = []
    for s in seasons:
        ts_path = os.path.join(_NBA_CACHE, f"team_stats_{s}.json")
        if os.path.exists(ts_path):
            with open(ts_path) as f:
                ts = json.load(f)
            all_def_rtgs.extend(
                float(v["def_rtg"]) for v in ts.values() if "def_rtg" in v
            )
    if all_def_rtgs:
        rng = np.random.default_rng(42)
        df["opp_def_rtg"] = rng.choice(all_def_rtgs, size=len(df), replace=True)
    else:
        df["opp_def_rtg"] = 113.0

    df = df.dropna(subset=["season_pts", "season_reb", "season_ast"])

    # Temporal split: sort by season ordinal, hold out last fold chronologically
    df_sorted = sort_chronologically(df, date_col="game_date")
    tscv = make_temporal_split(df_sorted, date_col="game_date", n_splits=5)
    _all_idx = np.arange(len(df_sorted))
    _splits = list(tscv.split(_all_idx))
    train_idx_final, holdout_idx_final = _splits[-1]
    train_df = df_sorted.iloc[train_idx_final].reset_index(drop=True)
    test_df  = df_sorted.iloc[holdout_idx_final].reset_index(drop=True)
    print(f"  [props] Temporal split: {len(train_df)} train rows, {len(test_df)} holdout rows")

    return (train_df, test_df, feat_cols)


def train_props(seasons: list = None, force: bool = False,
                exclude_player_ids: list = None) -> dict:
    """
    Train XGBoost regression models for pts, reb, ast props.

    Uses LeagueDashPlayerStats per season as training signal.
    Target = actual season per-game stat, features = first-half-season proxy.
    Walk-forward: train on earlier seasons, test on latest.

    Args:
        seasons: List of season strings. Defaults to ["2022-23", "2023-24", "2024-25"].
        force:   Retrain even if models already saved.

    Returns:
        {"pts": {"mae": float, "r2": float}, "reb": ..., "ast": ...}
    """
    import numpy as np
    import xgboost as xgb
    from sklearn.metrics import mean_absolute_error, r2_score
    from src.prediction.prop_cv_split import xgb_params_for_stat

    os.makedirs(_MODEL_DIR, exist_ok=True)

    # Check if already trained
    if not force and all(
        os.path.exists(os.path.join(_MODEL_DIR, f"props_{s}.json"))
        for s in _PROP_STATS
    ):
        print("[props] Models already trained. Use force=True to retrain.")
        return {}

    train_df, test_df, feat_cols = _build_prop_training_frame(seasons, exclude_player_ids)
    if train_df is None:
        print("  [props] Not enough data. Skipping training.")
        return {}

    results = {}

    for stat in _PROP_STATS:
        # Drop season_{stat} to prevent label leakage
        stat_feat_cols = [c for c in feat_cols if c != f"season_{stat}"]
        # Fill missing columns with 0 for robustness
        for col in stat_feat_cols:
            if col not in train_df.columns:
                train_df = train_df.copy()
                train_df[col] = 0.0
                test_df = test_df.copy()
                test_df[col] = 0.0

        if f"season_{stat}" not in train_df.columns:
            print(f"  [props] {stat.upper()} — no label column, skipping")
            continue

        X_train = train_df[stat_feat_cols].fillna(0.0).values
        X_test  = test_df[stat_feat_cols].fillna(0.0).values
        y_train = train_df[f"season_{stat}"].values
        y_test  = test_df[f"season_{stat}"].values

        # data_confidence as sample_weight: rows with CV data get higher weight
        if "data_confidence" in train_df.columns:
            sample_w = train_df["data_confidence"].clip(0.1, 1.0).values
        else:
            sample_w = None

        # Per-stat hyperparameters: STL/BLK use the Poisson objective AND
        # stronger regularisation — the walk-forward report (PRED-02) flagged
        # props_stl overfitting with a 0.18 train/holdout R² gap.
        m = xgb.XGBRegressor(**xgb_params_for_stat(stat))
        m.fit(X_train, y_train, sample_weight=sample_w)
        preds = m.predict(X_test)
        mae = mean_absolute_error(y_test, preds)
        r2  = r2_score(y_test, preds)

        model_path = os.path.join(_MODEL_DIR, f"props_{stat}.json")
        m.save_model(model_path)
        results[stat] = {"mae": round(mae, 3), "r2": round(r2, 3)}
        print(f"  [props] {stat.upper()} - MAE: {mae:.2f}  R2: {r2:.3f}  -> saved {model_path}")

    return results


def train_props_lightgbm(seasons: list = None, force: bool = False,
                         exclude_player_ids: list = None) -> dict:
    """Train 7 LightGBM regressors (one per prop stat) — ensemble base learner #2.

    Mirrors train_props() but uses lightgbm.LGBMRegressor. Models persist to
    data/models/props_lgb_{stat}.pkl via joblib. Returns {stat: {"mae","r2"}}.
    """
    import datetime
    import joblib
    import lightgbm as lgb
    from sklearn.metrics import mean_absolute_error, r2_score

    os.makedirs(_MODEL_DIR, exist_ok=True)

    if not force and all(
        os.path.exists(os.path.join(_MODEL_DIR, f"props_lgb_{s}.pkl"))
        for s in _PROP_STATS
    ):
        print("[props_lgb] Models already trained. Use force=True to retrain.")
        return {}

    train_df, test_df, feat_cols = _build_prop_training_frame(seasons, exclude_player_ids)
    if train_df is None:
        print("  [props_lgb] Not enough data. Skipping training.")
        return {}

    results: dict = {}

    for stat in _PROP_STATS:
        stat_feat_cols = [c for c in feat_cols if c != f"season_{stat}"]
        # Fill missing columns with 0.0 on copies to avoid chained-assignment warnings
        _train = train_df.copy()
        _test  = test_df.copy()
        for col in stat_feat_cols:
            if col not in _train.columns:
                _train[col] = 0.0
                _test[col]  = 0.0

        if f"season_{stat}" not in _train.columns:
            print(f"  [props_lgb] {stat.upper()} — no label column, skipping")
            continue

        X_train = _train[stat_feat_cols].fillna(0.0).values
        X_test  = _test[stat_feat_cols].fillna(0.0).values
        y_train = _train[f"season_{stat}"].values
        y_test  = _test[f"season_{stat}"].values

        if "data_confidence" in _train.columns:
            sample_w = _train["data_confidence"].clip(0.1, 1.0).values
        else:
            sample_w = None

        # Poisson for count stats (STL/BLK) — mirrors XGBoost rationale
        objective = "poisson" if stat in ("stl", "blk") else "regression"

        m = lgb.LGBMRegressor(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            subsample_freq=1,       # required for subsample to take effect in LightGBM
            colsample_bytree=0.8,
            random_state=42,
            objective=objective,
            n_jobs=-1,
            verbosity=-1,
        )
        m.fit(X_train, y_train, sample_weight=sample_w)
        preds = m.predict(X_test)
        mae = mean_absolute_error(y_test, preds)
        r2  = r2_score(y_test, preds)

        model_path = os.path.join(_MODEL_DIR, f"props_lgb_{stat}.pkl")
        joblib.dump(m, model_path)
        results[stat] = {"mae": round(mae, 3), "r2": round(r2, 3)}
        print(f"  [props_lgb] {stat.upper()} - MAE: {mae:.2f}  R2: {r2:.3f}  -> saved {model_path}")

    metrics_path = os.path.join(_MODEL_DIR, "props_lgb_metrics.json")
    import logging
    logging.getLogger(__name__).warning(
        "props_lgb metrics reflect a SEASON-AVERAGE CIRCULAR task — "
        "R² is not a real game-level holdout. The honest game-level model is prop_pergame."
    )
    with open(metrics_path, "w") as _f:
        json.dump(
            {
                "model": "lightgbm",
                "task": "season_aggregate_circular",
                "trained_at": datetime.datetime.now().isoformat(),
                "stats": results,
            },
            _f, indent=2,
        )

    return results


try:
    import catboost as _catboost  # noqa: F401
    _CATBOOST_AVAILABLE = True
except ImportError:
    _CATBOOST_AVAILABLE = False


def train_props_catboost(seasons: list = None, force: bool = False,
                         exclude_player_ids: list = None) -> dict:
    """Train 7 CatBoost regressors (one per prop stat) — ensemble base learner #3.

    Mirrors train_props_lightgbm() but uses catboost.CatBoostRegressor. Models
    persist to data/models/props_cb_{stat}.cbm via CatBoost's native save_model().
    Returns {stat: {"mae", "r2"}}. No-ops (returns {}) if catboost is not installed.
    """
    if not _CATBOOST_AVAILABLE:
        print("[props_cb] catboost not installed — skipping training.")
        return {}

    import datetime
    import catboost as cb
    from sklearn.metrics import mean_absolute_error, r2_score

    os.makedirs(_MODEL_DIR, exist_ok=True)

    if not force and all(
        os.path.exists(os.path.join(_MODEL_DIR, f"props_cb_{s}.cbm"))
        for s in _PROP_STATS
    ):
        print("[props_cb] Models already trained. Use force=True to retrain.")
        return {}

    train_df, test_df, feat_cols = _build_prop_training_frame(seasons, exclude_player_ids)
    if train_df is None:
        print("  [props_cb] Not enough data. Skipping training.")
        return {}

    results: dict = {}

    for stat in _PROP_STATS:
        stat_feat_cols = [c for c in feat_cols if c != f"season_{stat}"]
        _train = train_df.copy()
        _test  = test_df.copy()
        for col in stat_feat_cols:
            if col not in _train.columns:
                _train[col] = 0.0
                _test[col]  = 0.0

        if f"season_{stat}" not in _train.columns:
            print(f"  [props_cb] {stat.upper()} — no label column, skipping")
            continue

        X_train = _train[stat_feat_cols].fillna(0.0).values
        X_test  = _test[stat_feat_cols].fillna(0.0).values
        y_train = _train[f"season_{stat}"].values
        y_test  = _test[f"season_{stat}"].values

        if "data_confidence" in _train.columns:
            sample_w = _train["data_confidence"].clip(0.1, 1.0).values
        else:
            sample_w = None

        # Poisson for count stats (STL/BLK) — mirrors XGBoost/LightGBM rationale
        loss_function = "Poisson" if stat in ("stl", "blk") else "RMSE"

        m = cb.CatBoostRegressor(
            iterations=200,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            random_seed=42,
            loss_function=loss_function,
            verbose=0,
        )
        m.fit(X_train, y_train, sample_weight=sample_w)
        preds = m.predict(X_test)
        mae = mean_absolute_error(y_test, preds)
        r2  = r2_score(y_test, preds)

        model_path = os.path.join(_MODEL_DIR, f"props_cb_{stat}.cbm")
        m.save_model(model_path)
        results[stat] = {"mae": round(mae, 3), "r2": round(r2, 3)}
        print(f"  [props_cb] {stat.upper()} - MAE: {mae:.2f}  R2: {r2:.3f}  -> saved {model_path}")

    metrics_path = os.path.join(_MODEL_DIR, "props_cb_metrics.json")
    import logging
    logging.getLogger(__name__).warning(
        "props_cb metrics reflect a SEASON-AVERAGE CIRCULAR task — "
        "R² is not a real game-level holdout. The honest game-level model is prop_pergame."
    )
    with open(metrics_path, "w") as _f:
        json.dump(
            {
                "model": "catboost",
                "task": "season_aggregate_circular",
                "trained_at": datetime.datetime.now().isoformat(),
                "stats": results,
            },
            _f, indent=2,
        )

    return results


def _get_all_player_avgs(season: str) -> list:
    """
    Return list of feature dicts for all players in a season.
    Uses LeagueDashPlayerStats (cached). Phase 4.6: includes hustle, on/off, synergy.
    """
    cache_path = os.path.join(_NBA_CACHE, f"player_avgs_{season}.json")
    avgs_map = {}
    # Use the same TTL as the inference path so stale training data doesn't
    # silently bias models (the TTL was added to _get_player_season_avgs but
    # this training-path caller was missed).
    _avgs_fresh = (
        os.path.exists(cache_path)
        and (time.time() - os.path.getmtime(cache_path)) < _PLAYER_AVGS_TTL_HOURS * 3600
    )
    if _avgs_fresh:
        with open(cache_path) as f:
            avgs_map = json.load(f)
    else:
        _get_player_season_avgs("__trigger__", season)   # populates fresh cache
        if os.path.exists(cache_path):
            with open(cache_path) as f:
                avgs_map = json.load(f)

    clutch_map = _load_clutch_stats(season)

    # Phase 4.6: build lookup dicts once per season for efficiency
    hustle_path = os.path.join(_NBA_CACHE, f"hustle_stats_{season}.json")
    hustle_by_pid: dict = {}
    try:
        for r in json.load(open(hustle_path)):
            hustle_by_pid[r["player_id"]] = r
    except Exception:
        pass

    on_off_path = os.path.join(_NBA_CACHE, f"on_off_{season}.json")
    on_off_by_pid: dict = {}
    try:
        for r in json.load(open(on_off_path)):
            on_off_by_pid[r["player_id"]] = r
    except Exception:
        pass

    # Pre-Phase 6: PBP feature cache
    pbp_path = os.path.join(_NBA_CACHE, f"pbp_features_{season}.json")
    pbp_by_pid: dict = {}
    try:
        pbp_by_pid = json.load(open(pbp_path))
    except Exception:
        pass

    # Pre-Phase 6: shot zone tendency cache
    szt_all: dict = {}
    try:
        szt_all = json.load(open(os.path.join(_NBA_CACHE, "shot_tendency_features.json")))
    except Exception:
        pass

    # BBRef advanced stats: build name->record lookup
    import unicodedata as _ud
    def _norm_name(s: str) -> str:
        return _ud.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()

    bbref_by_name: dict = {}
    ext_cache = os.path.join(PROJECT_DIR, "data", "external")
    bbref_path = os.path.join(ext_cache, f"bbref_advanced_{season}.json")
    try:
        for r in json.load(open(bbref_path)):
            if isinstance(r, dict) and r.get("player_name"):
                bbref_by_name[_norm_name(r["player_name"])] = r
    except Exception:
        pass

    # Phase B1: matchup lookup by player_id
    matchup_by_pid: dict = {}
    matchup_path = os.path.join(_NBA_CACHE, f"matchups_{season}.json")
    try:
        for r in json.load(open(matchup_path)):
            pid_m = r.get("off_player_id")
            if pid_m is None:
                continue
            entry = matchup_by_pid.setdefault(pid_m, {"total_poss": 0.0, "wtd_fg_pct": 0.0, "wtd_pts_poss": 0.0})
            poss = float(r.get("partial_possessions", 1) or 1)
            entry["total_poss"] += poss
            entry["wtd_fg_pct"] += float(r.get("matchup_fg_pct", 0) or 0) * poss
            entry["wtd_pts_poss"] += float(r.get("pts_per_possession", 0) or 0) * poss
    except Exception:
        pass

    # Phase B1: defender zone by team (avg per team for training)
    def_zone_by_team: dict = {}
    dzone_path = os.path.join(_NBA_CACHE, f"defender_zone_{season}.json")
    try:
        from collections import defaultdict
        team_ra: dict = defaultdict(list)
        team_3pt: dict = defaultdict(list)
        for r in json.load(open(dzone_path)):
            t = str(r.get("team_abbreviation", "")).upper()
            zone = str(r.get("def_zone", "")).lower()
            fg = float(r.get("fg_pct_allowed", 0) or 0)
            if "restricted" in zone:
                team_ra[t].append(fg)
            elif "3" in zone or "above" in zone or "corner" in zone:
                team_3pt[t].append(fg)
        for t in set(list(team_ra.keys()) + list(team_3pt.keys())):
            def_zone_by_team[t] = {
                "opp_def_ra_fg_pct":  round(sum(team_ra[t]) / len(team_ra[t]), 4) if team_ra[t] else 0.0,
                "opp_def_3pt_fg_pct": round(sum(team_3pt[t]) / len(team_3pt[t]), 4) if team_3pt[t] else 0.0,
            }
    except Exception:
        pass

    # Phase B2: shot dashboard by player_id
    shot_dash_by_pid: dict = {}
    sdash_path = os.path.join(_NBA_CACHE, f"shot_dashboard_all_{season}.json")
    try:
        sd_data = json.load(open(sdash_path))
        shot_dash_by_pid = {int(k): v for k, v in sd_data.items() if k.isdigit()}
    except Exception:
        pass

    # Phase B2: season tracking by player_id
    tracking_by_pid: dict = {}
    track_path = os.path.join(_NBA_CACHE, f"player_tracking_{season}.json")
    try:
        for r in json.load(open(track_path)):
            if r.get("player_id"):
                tracking_by_pid[r["player_id"]] = r
    except Exception:
        pass

    # Build team→synergy lookups (team_abbr → synergy dict)
    syn_off_cache: dict = {}
    syn_def_cache: dict = {}

    rows = []
    for name, a in avgs_map.items():
        if a.get("gp", 0) < 10:
            continue
        pid = a.get("player_id")
        pid_str = str(pid) if pid else ""
        c = clutch_map.get(pid_str, {})

        # Phase 4.6: hustle
        h = hustle_by_pid.get(pid, {})
        h_gp = max(float(h.get("games_played", 1) or 1), 1.0)

        # Phase 4.6: on/off
        oo = on_off_by_pid.get(pid, {})

        # Phase 4.6: synergy (lazy per-team)
        team = a.get("team", "")
        if team and team not in syn_off_cache:
            syn_off_cache[team] = _load_synergy_off(team, season)
        if team and team not in syn_def_cache:
            # Use empty for training (no per-row opp_team during batch training)
            syn_def_cache[team] = {}
        s_off = syn_off_cache.get(team, {})

        # Pre-Phase 6: PBP + shot zone per player
        pbp_r = pbp_by_pid.get(str(pid), {})
        szt_r = szt_all.get(str(pid), {})
        bbref_r = bbref_by_name.get(_norm_name(name), {})

        rows.append({
            "season_pts":  a.get("pts", 0),
            "season_reb":  a.get("reb", 0),
            "season_ast":  a.get("ast", 0),
            "season_min":  a.get("min", 0),
            "season_fg3m": a.get("fg3m", 0),
            "season_stl":  a.get("stl", 0),
            "season_blk":  a.get("blk", 0),
            "season_tov":  a.get("tov", 0),
            "pts_roll":    a.get("pts", 0),
            "reb_roll":    a.get("reb", 0),
            "ast_roll":    a.get("ast", 0),
            "min_roll":    a.get("min", 0),
            # Bayesian and extended cols filled by train_props with noise simulation
            "opp_def_rtg":      113.0,
            "fg_pct":           a.get("fg_pct", 0.45),
            # Clutch stats (0.0 fallback when unavailable)
            "clutch_fg_pct":    float(c.get("clutch_fg_pct",   0.0)),
            "clutch_pts_pg":    float(c.get("clutch_pts_pg",   0.0)),
            "foul_drawn_rate":  float(c.get("foul_drawn_rate", 0.0)),
            # External factors (BBRef values when available, else 0.0)
            "bbref_bpm":        float(bbref_r.get("bpm", 0.0) or 0.0),
            "bbref_vorp":       float(bbref_r.get("vorp", 0.0) or 0.0),
            "bbref_ws_per_48":  float(bbref_r.get("ws_per_48", 0.0) or 0.0),
            "contract_year":    0.0,
            # Phase 4.6: hustle stats (per-game values from cache)
            "deflections_pg":       float(h.get("deflections_pg", 0.0) or 0.0),
            "contested_shots_pg":   float(h.get("contested_shots", 0.0) or 0.0),
            "screen_assists_pg":    float(h.get("screen_assists", 0.0) or 0.0),
            "charges_per_game":     float(h.get("charges_per_game", 0.0) or 0.0),
            "box_outs_pg":          float(h.get("box_outs", 0.0) or 0.0),
            # Phase 4.6: on/off splits
            "on_off_diff":          float(oo.get("on_off_diff", 0.0) or 0.0),
            "on_court_plus_minus":  float(oo.get("on_court_plus_minus", 0.0) or 0.0),
            # Phase 4.6: synergy (team offensive only; def unknown during training)
            "team_iso_ppp":         s_off.get("team_iso_ppp", 0.0),
            "team_spotup_ppp":      s_off.get("team_spotup_ppp", 0.0),
            "team_prbh_freq":       s_off.get("team_prbh_freq", 0.0),
            "opp_def_iso_ppp":      0.0,    # unknown per-row during training
            "opp_def_prbh_ppp":     0.0,
            # Phase 4.6: schedule context (0.0 during training; real values at inference)
            "rest_days":            1.0,
            "games_in_last_14":     5.0,    # mid-season neutral
            # Pre-Phase 6: PBP features (real values from pbp_features cache)
            "q4_shot_rate":         float(pbp_r.get("q4_shot_rate", 0.0)),
            "q4_pts_share":         float(pbp_r.get("q4_pts_share", 0.0)),
            "fta_rate_pbp":         float(pbp_r.get("fta_rate_pbp", 0.0)),
            "foul_drawn_rate_pbp":  float(pbp_r.get("foul_drawn_rate_pbp", 0.0)),
            "comeback_pts_pg":      float(pbp_r.get("comeback_pts_pg", 0.0)),
            # Pre-Phase 6: shot zone tendency
            "paint_rate":               float(szt_r.get("paint_rate", 0.0)),
            "above_break_3_rate":       float(szt_r.get("above_break_3_rate", 0.0)),
            "corner_3_rate":            float(szt_r.get("corner_3_rate", 0.0)),
            "mid_rate":                 float(szt_r.get("mid_rate", 0.0)),
            "fg_pct_restricted_area":   float(szt_r.get("fg_pct_restricted_area", 0.0)),
            # Phase B1: matchup features (player-level, opponent unknown during training)
            "matchup_fg_pct_vs_opp":   _matchup_avg_fg(matchup_by_pid.get(pid, {})),
            "matchup_pts_poss_vs_opp": _matchup_avg_pts(matchup_by_pid.get(pid, {})),
            # Phase B1: defender zone (own team as proxy — opp unknown during training)
            "opp_def_ra_fg_pct":   def_zone_by_team.get(team, {}).get("opp_def_ra_fg_pct",   0.0),
            "opp_def_3pt_fg_pct":  def_zone_by_team.get(team, {}).get("opp_def_3pt_fg_pct",  0.0),
            # Phase B2: shot dashboard (0.0 until A1 pull completes for that season)
            "contested_pct":     float(shot_dash_by_pid.get(pid, {}).get("contested_pct",       0.0) or 0.0),
            "pull_up_pct":       float(shot_dash_by_pid.get(pid, {}).get("pull_up_pct",         0.0) or 0.0),
            "catch_shoot_pct":   float(shot_dash_by_pid.get(pid, {}).get("catch_and_shoot_pct", 0.0) or 0.0),
            "avg_defender_dist": float(shot_dash_by_pid.get(pid, {}).get("avg_defender_dist_contested", 0.0) or 0.0),
            # Phase B2: season tracking
            "avg_speed":     float(tracking_by_pid.get(pid, {}).get("speed",    0.0) or 0.0),
            "dist_per_game": float(tracking_by_pid.get(pid, {}).get("distance", 0.0) or 0.0),
            "touches_pg":    float(tracking_by_pid.get(pid, {}).get("touches",  0.0) or 0.0),
        })

    # data_confidence: compute after rows are fully built
    try:
        from src.features.advanced_features import compute_feature_confidence as _conf_fn
        for row in rows:
            row["data_confidence"] = _conf_fn(row)
    except Exception:
        for row in rows:
            row.setdefault("data_confidence", 0.85)

    return rows


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="NBA Player Prop Prediction")
    ap.add_argument("--player", type=str, help="Player full name")
    ap.add_argument("--opp",    type=str, help="Opponent abbreviation")
    ap.add_argument("--season", default="2025-26")
    ap.add_argument("--train",  action="store_true", help="Train prop models")
    args = ap.parse_args()

    if args.train:
        results = train_props(force=True)
        print(json.dumps(results, indent=2))
    elif args.player and args.opp:
        result = predict_props(args.player, args.opp, args.season)
        print(json.dumps({k: v for k, v in result.items() if k != "features"}, indent=2))
    else:
        ap.print_help()
