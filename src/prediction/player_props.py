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
from typing import Optional

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
    if _cache_fresh:
        with open(cache_path) as f:
            rows = json.load(f)
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

    result = {
        "pts_roll":  _avg("PTS", recent),
        "reb_roll":  _avg("REB", recent),
        "ast_roll":  _avg("AST", recent),
        "min_roll":  sum(_to_min(r.get("MIN", 0)) for r in recent) / ng,
        "fg3m_roll": _avg("FG3M", recent),
        "stl_roll":  _avg("STL", recent),
        "blk_roll":  _avg("BLK", recent),
        "tov_roll":  _avg("TOV", recent),
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

    try:
        from nba_api.stats.endpoints import playerdashboardbyopponent
        time.sleep(0.6)
        dfs = playerdashboardbyopponent.PlayerDashboardByOpponent(
            player_id=player_id, season=season
        ).get_data_frames()
        # Index 4 = OpponentTeamDashboard (varies by API version — search by key)
        opp_df = None
        for df in dfs:
            if "OPPONENT_TEAM_ABBREVIATION" in df.columns or "OPP_TEAM_ABBREVIATION" in df.columns:
                opp_df = df
                break
        if opp_df is None or len(opp_df) == 0:
            return None

        team_col = "OPPONENT_TEAM_ABBREVIATION" if "OPPONENT_TEAM_ABBREVIATION" in opp_df.columns else "OPP_TEAM_ABBREVIATION"
        cache = {}
        for _, row in opp_df.iterrows():
            abbrev = str(row.get(team_col, ""))
            gp = max(int(row.get("GP", 1)), 1)
            cache[abbrev] = {
                "pts_vs_opp": float(row.get("PTS", 0)) / gp,
                "reb_vs_opp": float(row.get("REB", 0)) / gp,
                "ast_vs_opp": float(row.get("AST", 0)) / gp,
            }
        os.makedirs(_NBA_CACHE, exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(cache, f)
        return cache.get(opp_team)
    except Exception as e:
        print(f"  [props] opp dashboard fetch failed: {e}")
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


# ── Feature builder ────────────────────────────────────────────────────────────

def _build_player_features(
    player_name: str,
    opp_team: str,
    season: str,
    n_games: int = 10,
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

    return feats


# Per-session cache: (home_team, away_team, season) → blowout_prob
_blowout_cache: dict = {}


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
    season: str = "2024-25",
    n_games: int = 10,
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
          "confidence": str,   # "model" | "rolling" | "season" | "default"
          "features":  dict,
        }
    """
    feats = _build_player_features(player_name, opp_team, season, n_games)
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

    # ── Injury adjustment ─────────────────────────────────────────────────────
    player_id       = feats.get("player_id")
    injury_status   = _injury_monitor.get_status(player_id) if player_id else "Unknown"
    injury_mult     = _injury_monitor.get_impact_multiplier(player_id) if player_id else 1.0

    if injury_mult != 1.0:
        for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
            if stat in predictions:
                predictions[stat] = round(predictions[stat] * injury_mult, 1)

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
]

# Stats modelled by XGBoost (each model excludes its own season_{stat} feature)
_PROP_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")


def _predict_with_models(feats: dict) -> tuple:
    """
    Try loading trained XGBoost models for each of 7 prop stats.
    Falls back to Bayesian rolling avg, then season avg.

    Returns (predictions_dict, confidence_str).
    """
    import numpy as np

    predictions = {}
    any_model = False

    for stat in _PROP_STATS:
        # Drop season_{stat} from features — it IS the training label
        stat_feat_order = [c for c in _ALL_FEATS if c != f"season_{stat}"]
        X = np.array([[feats.get(k, 0.0) for k in stat_feat_order]])
        model_path = os.path.join(_MODEL_DIR, f"props_{stat}.json")

        val = None
        if os.path.exists(model_path):
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

    confidence = "model" if any_model else "rolling"
    return predictions, confidence


# ── Training ───────────────────────────────────────────────────────────────────

def train_props(seasons: list = None, force: bool = False) -> dict:
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

    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    os.makedirs(_MODEL_DIR, exist_ok=True)

    # Check if already trained
    if not force and all(
        os.path.exists(os.path.join(_MODEL_DIR, f"props_{s}.json"))
        for s in _PROP_STATS
    ):
        print("[props] Models already trained. Use force=True to retrain.")
        return {}

    # Gather cross-season player data
    all_rows = []
    for season in seasons:
        print(f"  [props] Fetching {season} player stats...")
        avgs = _get_all_player_avgs(season)
        for row in avgs:
            row["season"] = season
            all_rows.append(row)
        time.sleep(0.5)

    if len(all_rows) < 100:
        print(f"  [props] Not enough data ({len(all_rows)} rows). Skipping training.")
        return {}

    import pandas as pd
    df = pd.DataFrame(all_rows)

    feat_cols = list(_ALL_FEATS)  # full feature set

    # Simulate rolling-vs-season divergence with calibrated noise.
    # Without noise roll == season exactly → trivial identity model.
    import numpy as np
    _rng_form = np.random.default_rng(0)
    for col, scale in [
        ("pts", 0.15), ("reb", 0.12), ("ast", 0.20), ("min", 0.12),
        ("fg3m", 0.25), ("stl", 0.30), ("blk", 0.30), ("tov", 0.20),
    ]:
        noise = _rng_form.normal(0.0, scale, size=len(df))
        df[f"{col}_roll"] = (df[f"season_{col}"] * (1.0 + noise)).clip(lower=0.0)
        # Bayesian-shrunk version (use n=10 games as constant during training)
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

    results = {}
    train_seasons = seasons[:-1]
    test_season   = seasons[-1]
    train_df = df[df["season"].isin(train_seasons)]
    test_df  = df[df["season"] == test_season]

    for stat in _PROP_STATS:
        # Drop season_{stat} to prevent label leakage
        stat_feat_cols = [c for c in feat_cols if c != f"season_{stat}"]
        # Fill missing columns with 0 for robustness
        for col in stat_feat_cols:
            if col not in df.columns:
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

        m = xgb.XGBRegressor(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
        )
        m.fit(X_train, y_train)
        preds = m.predict(X_test)
        mae = mean_absolute_error(y_test, preds)
        r2  = r2_score(y_test, preds)

        model_path = os.path.join(_MODEL_DIR, f"props_{stat}.json")
        m.save_model(model_path)
        results[stat] = {"mae": round(mae, 3), "r2": round(r2, 3)}
        print(f"  [props] {stat.upper()} — MAE: {mae:.2f}  R²: {r2:.3f}  → saved {model_path}")

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
        })
    return rows


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="NBA Player Prop Prediction")
    ap.add_argument("--player", type=str, help="Player full name")
    ap.add_argument("--opp",    type=str, help="Opponent abbreviation")
    ap.add_argument("--season", default="2024-25")
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
