"""
v3_prop_features.py — Full feature row builder for v3 prop retraining.

Merges 12 new feature modules with the existing v2 rolling-stat core.
Every external call is wrapped in try/except so a broken module never
crashes the training pipeline.  Missing values default to the league-
average stub listed inline.

Public API
----------
    build_v3_features(player_id, game_date, season,
                      team_id, opp_team_id,
                      home_team, away_team,
                      is_home,
                      prior_games)            -> dict
"""
from __future__ import annotations

import os
import sys
from typing import List, Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")


# ── Tiny helpers ──────────────────────────────────────────────────────────────

def _avg(key: str, rows: List[dict]) -> float:
    vals = [float(r.get(key, 0) or 0) for r in rows]
    return sum(vals) / len(vals) if vals else 0.0


def _safe(fn, default=0.0):
    """Call fn(); return default on any exception."""
    try:
        result = fn()
        return result if result is not None else default
    except Exception:
        return default


# ── V2 rolling core (mirrors retrain_props_v2._build_row) ─────────────────────

def _build_v2_core(prior: List[dict]) -> dict:
    """Compute the baseline v2 feature set from a list of prior game rows."""
    n_all  = len(prior)
    _ROLL_N = 10
    _BAYES_K = 15
    n_roll = min(_ROLL_N, n_all)
    roll   = prior[-n_roll:] if n_roll > 0 else []

    def _bayes(rv: float, sv: float) -> float:
        n = float(n_roll)
        return round(n / (n + _BAYES_K) * rv + _BAYES_K / (n + _BAYES_K) * sv, 4)

    s = {k: _avg(k, prior) for k in _STATS + ("min",)}
    r = {k: _avg(k, roll)  for k in _STATS + ("min",)}

    fga_sum = sum(float(x.get("fga", 0) or 0) for x in prior)
    fgm_sum = sum(float(x.get("fgm", 0) or 0) for x in prior)
    fg_pct  = fgm_sum / fga_sum if fga_sum > 0 else 0.44

    home_g = [x for x in roll if "@" not in str(x.get("matchup", ""))]
    away_g = [x for x in roll if "@" in str(x.get("matchup", ""))]

    r_oreb = _avg("oreb", roll); r_dreb = _avg("dreb", roll)
    r_pf   = _avg("pf",   roll)
    r_fga  = _avg("fga",  roll); r_fg3a = _avg("fg3a", roll)
    r_fta  = _avg("fta",  roll)
    r_pm   = _avg("plus_minus", roll)
    min_vals  = [float(x.get("min", 0) or 0) for x in roll]
    min_var   = float(np.var(min_vals)) if len(min_vals) > 1 else 0.0
    fga_vals  = [float(x.get("fga", 0) or 0) for x in roll]
    fga_trend = (fga_vals[-1] - fga_vals[0]) / max(len(fga_vals) - 1, 1) if len(fga_vals) > 1 else 0.0
    dd_rate   = sum(
        1 for x in roll
        if float(x.get("pts", 0) or 0) >= 10 and float(x.get("reb", 0) or 0) >= 10
    ) / max(n_roll, 1)

    _min_r = max(r["min"], 1.0)
    stl_vals = [float(x.get("stl", 0) or 0) for x in roll]
    stl_consistency = float(np.var(stl_vals)) if len(stl_vals) > 1 else 0.0

    return {
        "season_pts": s["pts"], "season_reb": s["reb"], "season_ast": s["ast"],
        "season_min": s["min"], "season_fg3m": s["fg3m"], "season_stl": s["stl"],
        "season_blk": s["blk"], "season_tov": s["tov"],
        "pts_roll": r["pts"],   "reb_roll": r["reb"],
        "ast_roll": r["ast"],   "min_roll": r["min"],
        "stl_roll": r["stl"],   "blk_roll": r["blk"],
        "stl_per_min":       round(r["stl"] / _min_r * 36, 4),
        "def_activity_rate": round((r["stl"] + r["blk"]) / _min_r, 4),
        "stl_consistency":   stl_consistency,
        "pts_bayes":  _bayes(r["pts"],  s["pts"]),
        "reb_bayes":  _bayes(r["reb"],  s["reb"]),
        "ast_bayes":  _bayes(r["ast"],  s["ast"]),
        "fg3m_bayes": _bayes(r["fg3m"], s["fg3m"]),
        "stl_bayes":  _bayes(r["stl"],  s["stl"]),
        "blk_bayes":  _bayes(r["blk"],  s["blk"]),
        "tov_bayes":  _bayes(r["tov"],  s["tov"]),
        "fg_pct": fg_pct,
        "home_pts_avg": _avg("pts", home_g) if home_g else s["pts"],
        "away_pts_avg": _avg("pts", away_g) if away_g else s["pts"],
        "home_reb_avg": _avg("reb", home_g) if home_g else s["reb"],
        "away_reb_avg": _avg("reb", away_g) if away_g else s["reb"],
        "home_ast_avg": _avg("ast", home_g) if home_g else s["ast"],
        "away_ast_avg": _avg("ast", away_g) if away_g else s["ast"],
        "pts_vs_opp": s["pts"], "reb_vs_opp": s["reb"], "ast_vs_opp": s["ast"],
        "oreb_roll": r_oreb, "dreb_roll": r_dreb, "pf_roll": r_pf,
        "fga_roll": r_fga,  "fg3a_roll": r_fg3a, "fta_roll": r_fta,
        "plus_minus_roll": r_pm, "min_variance": min_var,
        "fga_trend": fga_trend, "double_double_rate": dd_rate,
        # defaults for opp context (overwritten by caller)
        "opp_tov_pct": 0.145, "opp_pace": 100.0, "opp_stl_rate": 0.080,
    }


# ── Public API ────────────────────────────────────────────────────────────────

def build_v3_features(
    player_id: int,
    game_date: str,
    season: str,
    team_id: int,
    opp_team_id: int,
    home_team: str,
    away_team: str,
    is_home: bool,
    prior_games: Optional[List[dict]] = None,
) -> dict:
    """
    Build the full v3 feature row for a prop prediction.

    Parameters
    ----------
    player_id   : NBA player ID (integer)
    game_date   : ISO date string "YYYY-MM-DD" — features must only use data
                  strictly BEFORE this date (no future leak)
    season      : NBA season string e.g. "2024-25"
    team_id     : NBA team ID for the player's team (integer)
    opp_team_id : Opposing team NBA team ID
    home_team   : Home team abbreviation e.g. "LAL"
    away_team   : Away team abbreviation e.g. "GSW"
    is_home     : True when the player's team is playing at home
    prior_games : Pre-filtered list of prior same-season game dicts
                  (from retrain_props_v2._build_dataset logic).
                  Each dict has keys: pts, reb, ast, min, fg3m, stl, blk,
                  tov, matchup, fga, fgm, oreb, dreb, pf, fg3a, fta,
                  plus_minus, _dt, _season.

    Returns
    -------
    dict — flat feature row, ~50+ keys, all values are float.
    """
    if prior_games is None:
        prior_games = []

    # --- 1. V2 rolling core --------------------------------------------------
    row: dict = _build_v2_core(prior_games)
    row["is_home"] = 1.0 if is_home else 0.0

    # Derive player team abbreviation from home/away context
    player_team = (home_team or "").strip().upper() or "UNK"
    opp_team    = (away_team if is_home else home_team or "").strip().upper() or "UNK"
    # Normalise: take last word (handles "LAL vs. GSW" → "GSW" edge cases)
    if len(player_team) > 3:
        player_team = player_team.split()[-1][:3]
    if len(opp_team) > 3:
        opp_team = opp_team.split()[-1][:3]

    # --- 2. Garbage-time-adjusted rolling L10 --------------------------------
    for stat in _STATS:
        try:
            from src.features.clean_stats import get_clean_features
            cf = get_clean_features(player_id, season, game_date, n_games=10)
            row[f"clean_{stat}_l10"] = float(cf.get(f"clean_{stat}_avg", row.get(f"{stat}_roll", 0.0)) or 0.0)
            # variance of clean stats
            row[f"clean_{stat}_var"] = float(cf.get(f"{stat}_var", 0.0) or 0.0)
            break  # get_clean_features returns all stats at once
        except Exception:
            for s2 in _STATS:
                row[f"clean_{s2}_l10"] = row.get(f"{s2}_roll", 0.0)
                row[f"clean_{s2}_var"]  = 0.0
            break

    # --- 3. Position-prior shrinkage -----------------------------------------
    try:
        from src.features.position_priors import get_position, get_position_prior
        position = _safe(lambda: get_position(player_id), "G")
        for stat in _STATS:
            prior_mean, prior_K = _safe(
                lambda: get_position_prior(stat, position, season),
                (row.get(f"season_{stat}", 0.0), 15),
            )
            n_roll = min(10, len(prior_games))
            roll_val = row.get(f"{stat}_roll", 0.0)
            shrunk = n_roll / (n_roll + prior_K) * roll_val + prior_K / (n_roll + prior_K) * prior_mean
            row[f"pos_prior_{stat}_mean"]     = float(prior_mean)
            row[f"pos_prior_{stat}_K"]        = float(prior_K)
            row[f"pos_prior_{stat}_shrunk"]   = round(shrunk, 4)
            row[f"pos_residual_{stat}"]       = round(roll_val - prior_mean, 4)
        row["position_code"] = {"G": 0.0, "F": 1.0, "C": 2.0, "GF": 0.5, "FC": 1.5}.get(position, 0.0)
    except Exception:
        for stat in _STATS:
            row[f"pos_prior_{stat}_mean"]   = row.get(f"season_{stat}", 0.0)
            row[f"pos_prior_{stat}_K"]      = 15.0
            row[f"pos_prior_{stat}_shrunk"] = row.get(f"{stat}_roll", 0.0)
            row[f"pos_residual_{stat}"]     = 0.0
        row["position_code"] = 0.0

    # --- 4. Trajectory features ----------------------------------------------
    try:
        from src.features.player_trajectory import get_trajectory_features
        traj = _safe(lambda: get_trajectory_features(player_id, season, game_date), {})
        row["traj_hot_flag"]         = float(traj.get("hot_flag",          0.0))
        row["traj_cold_flag"]        = float(traj.get("cold_flag",         0.0))
        row["traj_z_score_l5"]       = float(traj.get("z_score_l5",        0.0))
        row["traj_momentum"]         = float(traj.get("momentum",          0.0))
        row["traj_regression_signal"]= float(traj.get("regression_signal", 0.0))
        row["traj_breakout_score"]   = float(traj.get("breakout_score",    0.0))
    except Exception:
        row["traj_hot_flag"]          = 0.0
        row["traj_cold_flag"]         = 0.0
        row["traj_z_score_l5"]        = 0.0
        row["traj_momentum"]          = 0.0
        row["traj_regression_signal"] = 0.0
        row["traj_breakout_score"]    = 0.0

    # --- 5. Minutes distribution ---------------------------------------------
    try:
        from src.prediction.minutes_predictor import MinutesPredictor
        _mp = MinutesPredictor()
        game_context = {
            "player_id":    player_id,
            "season":       season,
            "game_date":    game_date,
            "is_home":      is_home,
            "min_l10":      row.get("min_roll", 24.0),
        }
        md = _safe(lambda: _mp.predict_minutes_distribution(player_id, game_context), {})
        row["mp_expected_min"]  = float(md.get("expected_minutes",   row.get("min_roll", 24.0)))
        row["mp_p_dnp"]         = float(md.get("p_dnp",              0.03))
        row["mp_p_load_mgmt"]   = float(md.get("p_load_management",  0.05))
        row["mp_minutes_std"]   = float(md.get("minutes_std",        4.0))
    except Exception:
        row["mp_expected_min"] = row.get("min_roll", 24.0)
        row["mp_p_dnp"]        = 0.03
        row["mp_p_load_mgmt"]  = 0.05
        row["mp_minutes_std"]  = 4.0

    # --- 6. Schedule pressure ------------------------------------------------
    # Pass the team abbreviation directly (avoids team_id=0 fallback to API)
    try:
        from src.features.schedule_pressure import get_team_schedule_features, _ARENA_GEO
        # Only call if we have a valid team abbreviation with schedule cache
        _valid_team = player_team in _ARENA_GEO
        if _valid_team:
            sp = _safe(lambda: get_team_schedule_features(team_id, game_date, season), {})
        else:
            sp = {}
        row["sched_games_l7"]   = float(sp.get("games_l7",     3.0))
        row["sched_b2b"]        = float(sp.get("is_b2b",       0.0))
        row["sched_miles_l7"]   = float(sp.get("miles_l7",     0.0))
        row["sched_tz_crossed"] = float(sp.get("tz_crossed",   0.0))
        row["sched_4in6"]       = float(sp.get("is_4in6",      0.0))
        row["sched_5in7"]       = float(sp.get("is_5in7",      0.0))
    except Exception:
        row["sched_games_l7"]   = 3.0
        row["sched_b2b"]        = 0.0
        row["sched_miles_l7"]   = 0.0
        row["sched_tz_crossed"] = 0.0
        row["sched_4in6"]       = 0.0
        row["sched_5in7"]       = 0.0

    # --- 7. Team form --------------------------------------------------------
    try:
        from src.features.team_form import get_team_form_features
        import inspect as _inspect
        _tf_sig = _inspect.signature(get_team_form_features)
        _tf_kwargs = {"window": 10} if "window" in _tf_sig.parameters else {}
        tf = _safe(lambda: get_team_form_features(player_team, game_date, season, **_tf_kwargs), {})
        row["form_win_pct_l10"]  = float(tf.get("win_pct_l10",  0.5))
        row["form_qow_l10"]      = float(tf.get("qow_l10",      0.0))
        row["form_sos_l10"]      = float(tf.get("sos_l10",      0.0))
        row["form_clutch_l10"]   = float(tf.get("clutch_win_pct_l10", 0.5))
        row["form_net_rtg_l10"]  = float(tf.get("net_rtg_l10",  0.0))
    except Exception:
        row["form_win_pct_l10"] = 0.5
        row["form_qow_l10"]     = 0.0
        row["form_sos_l10"]     = 0.0
        row["form_clutch_l10"]  = 0.5
        row["form_net_rtg_l10"] = 0.0

    # --- 8. Coach features ---------------------------------------------------
    try:
        from src.features.coach_features import get_coach_features
        cf = _safe(lambda: get_coach_features(home_team, away_team, season, game_date), {})
        player_prefix = "home" if is_home else "away"
        row["coach_pace"]               = float(cf.get(f"{player_prefix}_coach_pace",          100.0))
        row["coach_oe"]                 = float(cf.get(f"{player_prefix}_coach_off_rtg",        112.0))
        row["coach_de"]                 = float(cf.get(f"{player_prefix}_coach_def_rtg",        112.0))
        row["coach_rotation_depth"]     = float(cf.get(f"{player_prefix}_coach_rotation_depth", 8.0))
        row["coach_late_close_win_pct"] = float(cf.get(f"{player_prefix}_coach_clutch_win_pct", 0.5))
    except Exception:
        row["coach_pace"]               = 100.0
        row["coach_oe"]                 = 112.0
        row["coach_de"]                 = 112.0
        row["coach_rotation_depth"]     = 8.0
        row["coach_late_close_win_pct"] = 0.5

    # --- 9. News features ----------------------------------------------------
    # NOTE: build_news_features fetches live data (injury report, rosters).
    # During historical training (game_date < today - 1 day) we skip the live
    # call and return zeros.  At inference time the caller should pass
    # live_news=True to enable the live fetch.
    import datetime as _dt
    _today = _dt.date.today()
    try:
        _gd = _dt.date.fromisoformat(game_date[:10])
    except Exception:
        _gd = _today
    _is_historical = (_today - _gd).days > 1

    if not _is_historical:
        try:
            from src.data.news_features import build_news_features
            nf = _safe(lambda: build_news_features(home_team, away_team, game_date), {})
            row["news_inactives_count"]    = float(nf.get("inactives_count",    0.0))
            row["news_star_out_flag"]      = float(nf.get("star_out_flag",      0.0))
            row["news_questionable_count"] = float(nf.get("questionable_count", 0.0))
        except Exception:
            row["news_inactives_count"]    = 0.0
            row["news_star_out_flag"]      = 0.0
            row["news_questionable_count"] = 0.0
    else:
        # Historical training: no live news available
        row["news_inactives_count"]    = 0.0
        row["news_star_out_flag"]      = 0.0
        row["news_questionable_count"] = 0.0

    # --- 10. Rampup multiplier -----------------------------------------------
    try:
        from src.features.injury_rampup import get_rampup_multiplier, days_since_last_game
        dsgl = _safe(lambda: days_since_last_game(player_id, game_date), 2)
        row["days_since_last_game"] = float(dsgl)
        for stat in _STATS:
            mult = _safe(lambda s=stat: get_rampup_multiplier(player_id, s, game_date), 1.0)
            row[f"rampup_mult_{stat}"] = float(mult)
    except Exception:
        row["days_since_last_game"] = 2.0
        for stat in _STATS:
            row[f"rampup_mult_{stat}"] = 1.0

    # --- 11. B2B multiplier --------------------------------------------------
    try:
        from src.features.back_to_back_impact import get_b2b_multiplier, is_back_to_back
        b2b_flag = _safe(lambda: is_back_to_back(player_id, game_date), False)
        row["is_b2b"] = 1.0 if b2b_flag else 0.0
        # Age proxy: use birthdate if available, else 26 (mean NBA age)
        _age = 26
        try:
            _age_path = os.path.join(PROJECT_DIR, "data", "nba", "player_ages.json")
            if os.path.exists(_age_path):
                import json
                _ages = json.load(open(_age_path))
                _age = int(_ages.get(str(player_id), 26))
        except Exception:
            pass
        for stat in _STATS:
            mult = _safe(lambda s=stat, a=_age: get_b2b_multiplier(player_id, s, a), 1.0)
            row[f"b2b_mult_{stat}"] = float(mult)
    except Exception:
        row["is_b2b"] = 0.0
        for stat in _STATS:
            row[f"b2b_mult_{stat}"] = 1.0

    # --- 12. Referee features ------------------------------------------------
    # NOTE: get_ref_crew_features makes live NBA API calls to look up officials.
    # Skip for historical training dates to avoid 90-second timeouts per row.
    if not _is_historical:
        try:
            from src.features.referee_features import get_ref_crew_features
            rf = _safe(lambda: get_ref_crew_features(None, game_date), {})
            row["ref_fouls_pg_v3"]  = float(rf.get("crew_fouls_per_game", 44.0))
            row["ref_home_wp_v3"]   = float(rf.get("home_win_pct",        0.60))
            row["ref_pace_v3"]      = float(rf.get("avg_pace",            100.0))
            row["ref_fta_rate_v3"]  = float(rf.get("fta_rate",            0.25))
        except Exception:
            row["ref_fouls_pg_v3"]  = 44.0
            row["ref_home_wp_v3"]   = 0.60
            row["ref_pace_v3"]      = 100.0
            row["ref_fta_rate_v3"]  = 0.25
    else:
        # Historical training: referee lookup requires live API — use league averages
        row["ref_fouls_pg_v3"]  = 44.0
        row["ref_home_wp_v3"]   = 0.60
        row["ref_pace_v3"]      = 100.0
        row["ref_fta_rate_v3"]  = 0.25

    # --- Ensure all values are finite floats --------------------------------
    for k, v in list(row.items()):
        try:
            f = float(v)
            row[k] = 0.0 if (f != f or abs(f) > 1e8) else f  # NaN / inf guard
        except (TypeError, ValueError):
            row[k] = 0.0

    return row
