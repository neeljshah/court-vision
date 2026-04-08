"""
advanced_features.py — Extended feature engineering functions (Pre-Season Accuracy Plan).

Blocks A-1 through A-14 (all new add_* functions split from feature_engineering.py
to keep per-file line count under control).

Public API (imported by feature_engineering.py)
-----------------------------------------------
    add_acceleration_features(df, windows)
    add_fatigue_features(df)
    add_defender_features(df, windows)
    add_off_ball_features(df, windows)
    add_paint_pressure_features(df)
    add_slump_features(df)
    add_ewma_features(df, halflife_frames)
    add_interaction_features(df)
    compute_regression_weight(games_played)
    build_elo_ratings(seasons)
    get_elo_features(home_team, away_team)
    get_opp_def_trend(team_abbr, season)
    get_home_away_splits(player_name, season)
    get_drive_outcomes(player_name)
"""

from __future__ import annotations

import json
import os
from typing import List, Optional

import numpy as np
import pandas as pd

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_NBA_CACHE   = os.path.join(_PROJECT_DIR, "data", "nba")
_ELO_PATH    = os.path.join(_NBA_CACHE, "elo_ratings.json")

# ── A-1: Acceleration + velocity burst features ────────────────────────────────

def add_acceleration_features(df: pd.DataFrame, windows: List[int] = None) -> pd.DataFrame:
    """
    A-1: Per-player rolling acceleration and velocity burst statistics.

    New columns for each window W in windows:
      acceleration_mean_{W}  — rolling mean of acceleration
      velocity_std_{W}       — rolling std of velocity (burst detection)
    Plus:
      acceleration_std_90    — rolling std of acceleration (variability)
    """
    if "acceleration" not in df.columns:
        return df
    if windows is None:
        windows = [30, 90, 150]

    group_cols = ["game_id", "player_id"] if "game_id" in df.columns else ["player_id"]
    df = df.sort_values(group_cols + ["frame"]).copy()
    grp = df.groupby(group_cols, group_keys=False)

    for w in windows:
        df[f"acceleration_mean_{w}"] = grp["acceleration"].transform(
            lambda s, _w=w: s.rolling(_w, min_periods=1).mean().round(3)
        )
        if "velocity" in df.columns:
            df[f"velocity_std_{w}"] = grp["velocity"].transform(
                lambda s, _w=w: s.rolling(_w, min_periods=1).std().fillna(0.0).round(3)
            )

    df["acceleration_std_90"] = grp["acceleration"].transform(
        lambda s: s.rolling(90, min_periods=1).std().fillna(0.0).round(3)
    )
    return df


# ── A-2: Fatigue index ─────────────────────────────────────────────────────────

def add_fatigue_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    A-2: Per-player fatigue index.

    fatigue_index = dist_traveled_150 / player_season_avg_dist_per_min
    where player_season_avg_dist_per_min = mean(dist_traveled_150) / 5.0 per player.
    Clipped to [0.3, 2.5]. NaN when dist_traveled_150 unavailable.
    """
    if "dist_traveled_150" not in df.columns:
        return df

    group_cols = ["game_id", "player_id"] if "game_id" in df.columns else ["player_id"]
    df = df.copy()

    # Per-player average (season proxy = global mean across all frames / 5 min window)
    avg_dist = (
        df.groupby(group_cols)["dist_traveled_150"]
        .transform("mean")
        .div(5.0)
        .clip(lower=1e-6)
    )
    df["fatigue_index"] = (df["dist_traveled_150"] / avg_dist).clip(0.3, 2.5).round(3)
    return df


# ── A-3: Defender distance rolling features ───────────────────────────────────

def add_defender_features(df: pd.DataFrame, windows: List[int] = None) -> pd.DataFrame:
    """
    A-3: Per-player rolling defender distance statistics.

    New columns:
      defender_dist_mean_{W}  — rolling mean of nearest_opponent
      defender_dist_min_90    — rolling min of nearest_opponent (90-frame)
      contested_fraction_90   — fraction of frames where nearest_opponent < 72 px
    """
    if "nearest_opponent" not in df.columns:
        return df
    if windows is None:
        windows = [30, 90, 150]

    group_cols = ["game_id", "player_id"] if "game_id" in df.columns else ["player_id"]
    df = df.sort_values(group_cols + ["frame"]).copy()
    grp = df.groupby(group_cols, group_keys=False)

    opp_col = pd.to_numeric(df["nearest_opponent"], errors="coerce")
    df["_opp_clean"] = opp_col

    for w in windows:
        df[f"defender_dist_mean_{w}"] = grp["_opp_clean"].transform(
            lambda s, _w=w: s.rolling(_w, min_periods=1).mean().round(1)
        )

    df["defender_dist_min_90"] = grp["_opp_clean"].transform(
        lambda s: s.rolling(90, min_periods=1).min().round(1)
    )

    # contested = nearest_opponent < 72 px  (~4 ft at broadcast scale)
    df["_contested"] = (opp_col < 72).astype(float)
    df["contested_fraction_90"] = grp["_contested"].transform(
        lambda s: (
            s.rolling(90, min_periods=1).sum()
            / s.rolling(90, min_periods=1).count()
        ).round(3)
    )

    df.drop(columns=["_opp_clean", "_contested"], inplace=True)
    return df


# ── A-4: Off-ball distance rolling ────────────────────────────────────────────

def add_off_ball_features(df: pd.DataFrame, windows: List[int] = None) -> pd.DataFrame:
    """
    A-4: Per-player rolling off-ball distance statistics.

    New columns:
      off_ball_dist_mean_{W}  — rolling mean of off_ball_distance
      off_ball_dist_std_90    — rolling std
    """
    if "off_ball_distance" not in df.columns:
        return df
    if windows is None:
        windows = [90, 150]

    group_cols = ["game_id", "player_id"] if "game_id" in df.columns else ["player_id"]
    df = df.sort_values(group_cols + ["frame"]).copy()
    grp = df.groupby(group_cols, group_keys=False)

    for w in windows:
        df[f"off_ball_dist_mean_{w}"] = grp["off_ball_distance"].transform(
            lambda s, _w=w: s.rolling(_w, min_periods=1).mean().round(1)
        )

    df["off_ball_dist_std_90"] = grp["off_ball_distance"].transform(
        lambda s: s.rolling(90, min_periods=1).std().fillna(0.0).round(2)
    )
    return df


# ── A-5: Paint pressure rolling ───────────────────────────────────────────────

def add_paint_pressure_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    A-5: Team paint pressure rolling features (frame-level, broadcast to all players).

    New columns:
      paint_pressure_90      — fraction of last 90 frames where paint_count_own >= 1
      paint_pressure_opp_90  — same for paint_count_opp
    """
    df = df.copy()

    for col, out_col in [("paint_count_own", "paint_pressure_90"),
                          ("paint_count_opp", "paint_pressure_opp_90")]:
        if col not in df.columns:
            continue
        # Aggregate per frame (take max across players — any player in paint counts)
        frame_paint = (
            df.groupby("frame")[col]
            .max()
            .reset_index()
            .sort_values("frame")
        )
        frame_paint["_has_paint"] = (frame_paint[col] >= 1).astype(float)
        frame_paint[out_col] = (
            frame_paint["_has_paint"].rolling(90, min_periods=1).mean().round(3)
        )
        df = df.merge(frame_paint[["frame", out_col]], on="frame", how="left")

    return df


# ── A-11: Interaction features ────────────────────────────────────────────────

def add_interaction_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    A-11: Multiplicative interaction terms.

    Produces columns only when both inputs are non-null:
      b2b_road_combined    = b2b_flag * is_road
      foul_ref_tendency    = ref_fta_tendency * foul_draw_rate (if both present)

    TODO (post-props-retrain):
      b2b_usage            = b2b_flag * usage_rate_season
      contract_hot_streak  = contract_year_flag * hot_streak_score
      playoff_clutch       = playoff_push_flag * clutch_score
      pace_uncertainty     = team_pace_variance * (1 - model_confidence)
    """
    df = df.copy()

    if "b2b_flag" in df.columns and "is_road" in df.columns:
        df["b2b_road_combined"] = (
            pd.to_numeric(df["b2b_flag"], errors="coerce").fillna(0)
            * pd.to_numeric(df["is_road"], errors="coerce").fillna(0)
        ).astype(float)

    if "ref_fta_tendency" in df.columns and "foul_draw_rate" in df.columns:
        df["foul_ref_tendency"] = (
            pd.to_numeric(df["ref_fta_tendency"], errors="coerce").fillna(0)
            * pd.to_numeric(df["foul_draw_rate"], errors="coerce").fillna(0)
        ).round(4)

    return df


# ── A-12: Dynamic regression weighting ────────────────────────────────────────

def compute_regression_weight(games_played: int) -> float:
    """
    A-12: Season vs career regression weight.

    Returns season_weight = min(games_played / 50.0, 1.0).
    Use as: blended = season_weight * season_avg + (1 - season_weight) * career_avg
    """
    return min(float(games_played) / 50.0, 1.0)


# ── A-13: Slump type detection ────────────────────────────────────────────────

def add_slump_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    A-13: Shot selection shift via KL divergence.

    Requires 'court_zone' column and 'event' column.
    Computes shot_selection_shift = KL(current 10-shot zone distribution ||
                                       career zone distribution) per player.
    No-op if court_zone absent.
    """
    if "court_zone" not in df.columns or "event" not in df.columns:
        return df

    try:
        from scipy.stats import entropy as _entropy
    except ImportError:
        return df

    df = df.copy()
    _ZONES = ["paint", "mid_range", "3pt_arc", "corner_3", "backcourt", "other"]

    shot_df = df[df["event"] == "shot"].copy()
    if shot_df.empty:
        df["shot_selection_shift"] = 0.0
        return df

    group_cols = ["game_id", "player_id"] if "game_id" in df.columns else ["player_id"]

    # Career (full-game) distribution per player
    career_dist: dict = {}
    for keys, grp in shot_df.groupby(group_cols):
        counts = grp["court_zone"].value_counts()
        dist = np.array([counts.get(z, 0) for z in _ZONES], dtype=float) + 1e-9
        dist /= dist.sum()
        key = keys if isinstance(keys, tuple) else (keys,)
        career_dist[key] = dist

    # Current 10-shot rolling distribution — computed on shot rows, broadcast back
    def _kl_rolling(sub: pd.DataFrame) -> pd.Series:
        key = tuple(sub[group_cols].iloc[0])
        career = career_dist.get(key, np.ones(len(_ZONES)) / len(_ZONES))
        result = pd.Series(0.0, index=sub.index)
        zone_enc = sub["court_zone"].fillna("other")
        for i, idx in enumerate(sub.index):
            window = zone_enc.iloc[max(0, i - 9): i + 1]
            counts = pd.Series({z: (window == z).sum() for z in _ZONES}).values.astype(float)
            counts += 1e-9
            counts /= counts.sum()
            result.at[idx] = float(_entropy(counts, career))
        return result

    kl_series = pd.Series(np.nan, index=df.index)
    for keys, grp in shot_df.groupby(group_cols):
        kl_series.loc[grp.index] = _kl_rolling(grp).values

    df["shot_selection_shift"] = kl_series.fillna(0.0).round(4)
    return df


# ── A-14: Exponential time decay (EWMA) features ─────────────────────────────

def add_ewma_features(df: pd.DataFrame, halflife_frames: int = 450) -> pd.DataFrame:
    """
    A-14: Per-player EWMA of velocity and distance.

    halflife_frames=450 ≈ 15 game-minutes at 30fps.

    New columns:
      velocity_ewma   — exponentially weighted moving average of velocity
      dist_ewma       — EWMA of dist_traveled_150 (cumulative run load proxy)
    """
    if "velocity" not in df.columns:
        return df

    group_cols = ["game_id", "player_id"] if "game_id" in df.columns else ["player_id"]
    df = df.sort_values(group_cols + ["frame"]).copy()
    grp = df.groupby(group_cols, group_keys=False)

    df["velocity_ewma"] = grp["velocity"].transform(
        lambda s: s.ewm(halflife=halflife_frames, min_periods=1).mean().round(3)
    )

    if "dist_traveled_150" in df.columns:
        df["dist_ewma"] = grp["dist_traveled_150"].transform(
            lambda s: s.ewm(halflife=halflife_frames, min_periods=1).mean().round(2)
        )
    return df


# ── A-7: ELO rating features ───────────────────────────────────────────────────

def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + 10.0 ** (-x / 400.0))


def build_elo_ratings(seasons: List[str] = None) -> dict:
    """
    A-7: FiveThirtyEight-style ELO ratings from season game results.

    K=20, home_advantage=100 elo points, starting elo=1500.
    Loads season_games_{season}.json from data/nba/.
    Saves to data/nba/elo_ratings.json.
    Returns {team_abbr: elo_float}.
    """
    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    elo: dict = {}
    K = 20
    HOME_ADV = 100

    all_games = []
    for season in seasons:
        path = os.path.join(_NBA_CACHE, f"season_games_{season}.json")
        if not os.path.exists(path):
            continue
        try:
            payload = json.load(open(path))
            # Handle versioned format {"v": N, "rows": [...]}
            if isinstance(payload, dict):
                payload = payload.get("rows", [])
            all_games.extend(payload)
        except Exception:
            continue

    if not all_games:
        return {}

    # Sort chronologically
    try:
        all_games.sort(key=lambda g: g.get("game_date", ""))
    except Exception:
        pass

    for game in all_games:
        home = str(game.get("home_team_abbrev") or game.get("home_team", ""))
        away = str(game.get("away_team_abbrev") or game.get("away_team", ""))
        result = game.get("home_win")
        if not home or not away or result is None:
            continue

        elo.setdefault(home, 1500.0)
        elo.setdefault(away, 1500.0)

        home_elo_adj = elo[home] + HOME_ADV
        exp_home = _sigmoid(home_elo_adj - elo[away])
        actual_home = float(result)

        delta = K * (actual_home - exp_home)
        elo[home] = round(elo[home] + delta, 2)
        elo[away] = round(elo[away] - delta, 2)

    os.makedirs(_NBA_CACHE, exist_ok=True)
    try:
        with open(_ELO_PATH, "w") as f:
            json.dump(elo, f)
    except Exception:
        pass

    return elo


def compute_game_elo_lookup(seasons: list) -> dict:
    """
    Build a game_id → {"home_elo": float, "away_elo": float} lookup.

    Runs the same K=20 / HOME_ADV=100 ELO update as build_elo_ratings, but
    snapshots BEFORE each update so each game gets the ELO that was current
    at tip-off (point-in-time, no leakage).

    Args:
        seasons: List of season strings e.g. ["2022-23", "2023-24", "2024-25"].

    Returns:
        Dict mapping str(game_id) → {"home_elo": float, "away_elo": float}.
    """
    K = 20
    HOME_ADV = 100

    all_games: list = []
    for season in seasons:
        path = os.path.join(_NBA_CACHE, f"season_games_{season}.json")
        if not os.path.exists(path):
            continue
        try:
            payload = json.load(open(path))
            if isinstance(payload, dict):
                payload = payload.get("rows", [])
            all_games.extend(payload)
        except Exception:
            continue

    if not all_games:
        return {}

    try:
        all_games.sort(key=lambda g: g.get("game_date", ""))
    except Exception:
        pass

    elo: dict = {}
    lookup: dict = {}
    for game in all_games:
        home = str(game.get("home_team_abbrev") or game.get("home_team", ""))
        away = str(game.get("away_team_abbrev") or game.get("away_team", ""))
        gid  = str(game.get("game_id", ""))
        result = game.get("home_win")
        if not home or not away or not gid:
            continue

        elo.setdefault(home, 1500.0)
        elo.setdefault(away, 1500.0)

        # Snapshot BEFORE update — this is the ELO at game time
        lookup[gid] = {"home_elo": elo[home], "away_elo": elo[away]}

        if result is None:
            continue  # future game — snapshot only, no update

        home_elo_adj = elo[home] + HOME_ADV
        exp_home = _sigmoid(home_elo_adj - elo[away])
        delta = K * (float(result) - exp_home)
        elo[home] = round(elo[home] + delta, 2)
        elo[away] = round(elo[away] - delta, 2)

    return lookup


def get_elo_features(home_team: str, away_team: str) -> dict:
    """
    A-7: Return ELO features for a game.

    Falls back to {1500, 1500, 0.0} if elo_ratings.json missing.
    """
    _default = {"home_elo": 1500.0, "away_elo": 1500.0, "elo_differential": 0.0}
    try:
        if not os.path.exists(_ELO_PATH):
            return _default
        elo = json.load(open(_ELO_PATH))
        h = float(elo.get(home_team, 1500.0))
        a = float(elo.get(away_team, 1500.0))
        return {"home_elo": h, "away_elo": a, "elo_differential": round(h - a, 2)}
    except Exception:
        return _default


# ── A-8: Opponent defensive trajectory ────────────────────────────────────────

def get_opp_def_trend(team_abbr: str, season: str) -> float:
    """
    A-8: Compute def_rtg_last10 - def_rtg_season for a team.

    Returns 0.0 on miss. Negative = improving defense.
    """
    try:
        path = os.path.join(_NBA_CACHE, f"team_stats_{season}.json")
        if not os.path.exists(path):
            return 0.0
        stats = json.load(open(path))
        # Try to find by abbrev (team_stats files are keyed by team_id int)
        # Look up team_id via nba_api static
        from nba_api.stats.static import teams as _teams
        abbrev_to_id = {t["abbreviation"]: str(t["id"]) for t in _teams.get_teams()}
        tid = abbrev_to_id.get(team_abbr.upper(), "0")
        t_data = stats.get(tid) or stats.get(int(tid), {})
        def_rtg_season = float(t_data.get("def_rtg", 113.0))
        def_rtg_last10 = float(t_data.get("def_rtg_last10", def_rtg_season))
        return round(def_rtg_last10 - def_rtg_season, 3)
    except Exception:
        return 0.0


# ── A-9: Home/away split differential ─────────────────────────────────────────

def get_home_away_splits(player_name: str, season: str) -> dict:
    """
    A-9: Per-player home/away split differentials.

    Returns {pts_delta, reb_delta, ast_delta} (home minus away averages).
    Returns zeros on miss.
    """
    _zero = {"pts_delta": 0.0, "reb_delta": 0.0, "ast_delta": 0.0}
    try:
        # Find player_id from avgs cache
        avgs_path = os.path.join(_NBA_CACHE, f"player_avgs_{season}.json")
        if not os.path.exists(avgs_path):
            return _zero
        avgs = json.load(open(avgs_path))

        import unicodedata
        def _norm(s: str) -> str:
            return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()

        key = _norm(player_name)
        norm_avgs = {_norm(k): v for k, v in avgs.items()}
        player_info = norm_avgs.get(key)
        if not player_info:
            return _zero
        pid = player_info.get("player_id")
        if not pid:
            return _zero

        gamelog_path = os.path.join(_NBA_CACHE, f"gamelog_{pid}_{season}.json")
        if not os.path.exists(gamelog_path):
            return _zero
        rows = json.load(open(gamelog_path))

        home_rows = [r for r in rows if "@" not in str(r.get("MATCHUP", ""))]
        away_rows = [r for r in rows if "@" in str(r.get("MATCHUP", ""))]

        def _avg(lst, col):
            vals = [float(r.get(col, 0) or 0) for r in lst if r.get(col) is not None]
            return sum(vals) / len(vals) if vals else 0.0

        return {
            "pts_delta": round(_avg(home_rows, "PTS") - _avg(away_rows, "PTS"), 2),
            "reb_delta": round(_avg(home_rows, "REB") - _avg(away_rows, "REB"), 2),
            "ast_delta": round(_avg(home_rows, "AST") - _avg(away_rows, "AST"), 2),
        }
    except Exception:
        return _zero


# ── A-10: Drive outcome distribution ──────────────────────────────────────────

# Module-level cache: avoid re-parsing PBP every call
_DRIVE_CACHE: dict = {}

# Laplace priors for drive outcomes
_DRIVE_PRIORS = {"finish": 0.35, "foul": 0.25, "kickout": 0.28, "tov": 0.12}


def get_drive_outcomes(player_name: str) -> dict:
    """
    A-10: Per-player drive outcome distribution from PBP files.

    Returns {drive_finish_rate, drive_foul_rate, drive_kickout_rate, drive_tov_rate}.
    Laplace-smoothed with league-average priors.
    Cached in module-level dict.
    """
    import glob as _glob

    _zero = {
        "drive_finish_rate": _DRIVE_PRIORS["finish"],
        "drive_foul_rate":   _DRIVE_PRIORS["foul"],
        "drive_kickout_rate": _DRIVE_PRIORS["kickout"],
        "drive_tov_rate":    _DRIVE_PRIORS["tov"],
    }
    if not player_name or not isinstance(player_name, str):
        return _zero

    key = player_name.lower().strip()
    if key in _DRIVE_CACHE:
        return _DRIVE_CACHE[key]

    counts = {"finish": 0, "foul": 0, "kickout": 0, "tov": 0, "total": 0}
    _LAPLACE = 10

    try:
        pbp_files = _glob.glob(os.path.join(_NBA_CACHE, "pbp_*.json"))[:300]
        player_key = key

        for fpath in pbp_files:
            try:
                data = json.load(open(fpath))
                events = data if isinstance(data, list) else data.get("playByPlay", data.get("plays", []))
                for ev in events:
                    if not isinstance(ev, dict):
                        continue
                    pname = str(ev.get("player1_name", ev.get("playerName", ""))).lower()
                    if player_key not in pname:
                        continue
                    desc = str(ev.get("description", ev.get("actionType", ""))).lower()
                    if "drive" not in desc and "driv" not in desc:
                        continue
                    counts["total"] += 1
                    if any(x in desc for x in ("layup", "dunk", "rim", "at the basket")):
                        counts["finish"] += 1
                    elif "foul" in desc or "free throw" in desc:
                        counts["foul"] += 1
                    elif "pass" in desc or "assist" in desc:
                        counts["kickout"] += 1
                    elif "turnover" in desc or "tov" in desc:
                        counts["tov"] += 1
            except Exception:
                continue

    except Exception:
        pass

    total = counts["total"] + _LAPLACE
    result = {
        "drive_finish_rate":  round((counts["finish"]  + _LAPLACE * _DRIVE_PRIORS["finish"])  / total, 4),
        "drive_foul_rate":    round((counts["foul"]    + _LAPLACE * _DRIVE_PRIORS["foul"])    / total, 4),
        "drive_kickout_rate": round((counts["kickout"] + _LAPLACE * _DRIVE_PRIORS["kickout"]) / total, 4),
        "drive_tov_rate":     round((counts["tov"]     + _LAPLACE * _DRIVE_PRIORS["tov"])     / total, 4),
    }
    _DRIVE_CACHE[key] = result
    return result


# ── Fusion layer adapter ───────────────────────────────────────────────────────

def wrap_with_confidence(
    feature_dict: dict,
    data_source: str = "nba_api",
) -> dict[str, "SourceValue"]:
    """
    Wrap a flat feature dict with SourceValue confidence annotations.

    Used by Phase 4 rewire: every feature that passes through advanced_features
    gets a confidence score derived from its data source.

    Returns a parallel dict: {feature_name: SourceValue}.
    Callers that don't need SourceValue can still use `feature_dict` directly.
    """
    try:
        from src.fusion.source_registry import SourceValue, SOURCE_DEFAULT_CONFIDENCE
        conf = SOURCE_DEFAULT_CONFIDENCE.get(data_source, 0.55)
        return {
            k: SourceValue(value=v, source=data_source, confidence=conf)
            for k, v in feature_dict.items()
            if v is not None
        }
    except Exception:
        return {}


def compute_feature_confidence(feature_dict: dict) -> float:
    """
    Compute an aggregate data_confidence score (0-1) for a feature row.

    CV-sourced features boost confidence; missing/zero features reduce it.
    Used as sample_weight during XGBoost training.
    """
    cv_keys = {
        "cv_avg_defender_distance", "cv_contested_shot_rate",
        "cvb_avg_defender_dist", "cvb_avg_spacing",
        "xPTS_per_shot",
    }
    has_cv = any(
        feature_dict.get(k, 0.0) not in (0.0, None)
        for k in cv_keys
    )
    n_nonzero = sum(
        1 for v in feature_dict.values()
        if isinstance(v, (int, float)) and v != 0.0
    )
    n_total = max(len(feature_dict), 1)

    base_conf = 0.85       # NBA API data
    cv_bonus  = 0.10 if has_cv else 0.0
    fill_rate = n_nonzero / n_total
    return round(min(1.0, base_conf * fill_rate + cv_bonus), 4)
