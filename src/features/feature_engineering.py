"""
feature_engineering.py — Transform raw tracking_data.csv into ML-ready features.

Input:  data/tracking_data.csv  (per-player per-frame, output of unified_pipeline)
Output: data/features.csv       (all original columns + engineered features)

Feature groups:
  1. Rolling  — windows 30/90/150 frames: velocity stats, distance, possession time
  2. Event    — shot/pass/dribble counts over rolling windows
  3. Momentum — possession run length, scoring run indicators

Usage:
    python -m src.features.feature_engineering
    — or —
    from src.features.feature_engineering import run
    df = run()
"""

import os
from typing import List, Optional

import numpy as np
import pandas as pd

try:
    from scipy.spatial import ConvexHull as _ConvexHull
    _SCIPY = True
except ImportError:
    _SCIPY = False

# Advanced feature modules (A-1 to A-14 — Pre-Season Accuracy Plan)
try:
    from src.features.advanced_features import (
        add_acceleration_features,
        add_fatigue_features,
        add_defender_features,
        add_off_ball_features,
        add_paint_pressure_features,
        add_slump_features,
        add_ewma_features,
        add_interaction_features,
        compute_regression_weight,
        get_elo_features,
        get_opp_def_trend,
        get_home_away_splits,
        get_drive_outcomes,
    )
    _HAS_ADVANCED = True
except ImportError:
    _HAS_ADVANCED = False

    def compute_regression_weight(games_played: int) -> float:  # noqa: F811
        return min(float(games_played) / 50.0, 1.0)

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")

# Rolling window sizes in frames (~1 s / 3 s / 5 s at 30 fps)
_WINDOWS = [30, 90, 150]

# Event window for shot/pass rate (frames)
_EVENT_WINDOW = 90   # ~3 seconds


# ── public API ────────────────────────────────────────────────────────────────

def load_tracking(path: str = None) -> pd.DataFrame:
    """Load tracking_data.csv and return a typed DataFrame."""
    if path is None:
        path = os.path.join(_DATA_DIR, "tracking_data.csv")
    df = pd.read_csv(path, low_memory=False)
    for col in ("frame", "player_id"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            df = df.dropna(subset=[col])
            df[col] = df[col].astype(int)
    for col in ("x_position", "y_position", "velocity", "acceleration",
                "distance_to_ball", "nearest_opponent", "nearest_teammate",
                "team_spacing", "team_centroid_x", "team_centroid_y",
                "handler_isolation", "ball_x2d", "ball_y2d",
                "distance_to_basket", "vel_toward_basket", "ball_velocity",
                "possession_duration",
                "ankle_x", "ankle_y", "contest_arm_angle", "jump_detected"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "event" not in df.columns:
        df["event"] = "none"
    else:
        df["event"] = df["event"].fillna("none")
    return df


def compute_spatial_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure spatial metric columns reflect only the 10 active players on court.

    Referee rows (team == 'referee') are excluded from hull/distance/paint
    calculations. Their spatial columns are set to NaN in the output so they
    do not corrupt ML features. Non-referee rows are unchanged.

    Also removes sentinel values that corrupt rolling window ML features:
      - defender_distance == 200.0  (``_ISOLATION_DEFAULT`` from unified_pipeline)
      - handler_isolation == 200.0  (same sentinel in tracking_data.csv)
      - team_spacing == 0.0         (invalid hull area: no players detected this frame)

    The spatial columns this function guards are those produced by the tracking
    pipeline (unified_pipeline.py):
        team_spacing, nearest_opponent, nearest_teammate,
        paint_count_own, paint_count_opp

    Args:
        df: Tracking DataFrame with per-player per-frame rows. Must contain a
            ``team`` column. Spatial columns are expected to already be present
            (populated by the tracking pipeline) but may be absent; if absent
            they are not added.

    Returns:
        DataFrame identical to input except referee rows and sentinel values have
        NaN in spatial metric columns.
    """
    _SPATIAL = [
        "team_spacing",
        "nearest_opponent",
        "nearest_teammate",
        "paint_count_own",
        "paint_count_opp",
    ]

    df = df.copy()

    # Sentinel filter — must run before referee mask so sentinels are cleaned
    # regardless of team.  These values corrupt rolling window stats in ML training.
    # Distance columns are now in FEET (converted by _px_to_ft in unified_pipeline).
    # Sentinel: _ISOLATION_DEFAULT was 200.0 px; changed to 99.0 ft (2026-05-26).
    # Threshold 98.5 ft catches the new 99 ft sentinel (wider than half-court = impossible).
    # Historic CSVs with old 200 px sentinel will also be caught since 200 > 98.5.
    for col in ("defender_distance", "handler_isolation", "nearest_opponent", "nearest_teammate"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            df.loc[df[col] >= 98.5, col] = np.nan   # catches 99 ft sentinel (and old 200 px)
            df.loc[df[col] <= 0, col] = np.nan       # 0.0 means "no data", not "touching"

    if "team_spacing" in df.columns:
        df["team_spacing"] = pd.to_numeric(df["team_spacing"], errors="coerce")
        df.loc[df["team_spacing"] == 0.0, "team_spacing"] = np.nan  # sentinel → NaN (lines 142-144, do NOT change)

    # BUG 2 FIX: forward-fill imputed spacing per (game_id, team) for downstream use.
    # impute_team_spacing adds team_spacing_imputed + is_spacing_imputed columns without
    # modifying the team_spacing NaN conversion above (lines 142-144 stay intact).
    df = impute_team_spacing(df)

    # Velocity clamp — tracking re-ID jumps produce physically impossible spikes
    # (p99 ~106 px/frame observed; NBA max sprint ~20 px/frame at 30fps/1294px court).
    # Cap at 60 px/frame (~3x real max) to absorb legitimate fast breaks while
    # eliminating teleportation artifacts that corrupt rolling velocity features.
    _VEL_MAX = 60.0
    for col in ("velocity", "acceleration"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").clip(upper=_VEL_MAX)

    if "team" not in df.columns:
        return df

    ref_mask = df["team"] == "referee"

    if not ref_mask.any():
        return df

    for col in _SPATIAL:
        if col in df.columns:
            df.loc[ref_mask, col] = np.nan

    return df


def add_rolling_features(df: pd.DataFrame, windows: List[int] = None) -> pd.DataFrame:
    """
    Per-player rolling window statistics.

    New columns for each window W (frames):
      velocity_mean_{W}   — mean speed
      velocity_max_{W}    — sprint peak
      dist_traveled_{W}   — total distance (sum of velocity)
      possession_pct_{W}  — fraction of frames player held ball
    """
    if windows is None:
        windows = _WINDOWS

    group_cols = ["game_id", "player_id"] if "game_id" in df.columns else ["player_id"]
    df = df.sort_values(group_cols + ["frame"]).copy()
    grp = df.groupby(group_cols, group_keys=False)

    for w in windows:
        df[f"velocity_mean_{w}"] = grp["velocity"].transform(
            lambda s, _w=w: s.rolling(_w, min_periods=1).mean().round(2)
        )
        df[f"velocity_max_{w}"] = grp["velocity"].transform(
            lambda s, _w=w: s.rolling(_w, min_periods=1).max().round(2)
        )
        df[f"dist_traveled_{w}"] = grp["velocity"].transform(
            lambda s, _w=w: s.rolling(_w, min_periods=1).sum().round(1)
        )
        df[f"possession_pct_{w}"] = grp["ball_possession"].transform(
            lambda s, _w=w: (
                s.rolling(_w, min_periods=1).sum()
                / s.rolling(_w, min_periods=1).count()
            ).round(3)
        )

    return df


def add_event_features(df: pd.DataFrame, window: int = _EVENT_WINDOW) -> pd.DataFrame:
    """
    Frame-level event rate features — same value for every player in a frame.

    New columns:
      shots_W, passes_W, dribbles_W  — event counts in last W frames
      possession_run                  — consecutive frames current attacking
                                        team (majority ball-holder) has
                                        held possession
    """
    if "event" not in df.columns:
        return df

    # Aggregate to one row per frame (take first non-none event across players)
    frame_ev = (
        df.groupby("frame")["event"]
        .agg(lambda s: next((e for e in s if e != "none"), "none"))
        .reset_index()
        .sort_values("frame")
    )
    frame_ev["is_shot"]    = (frame_ev["event"] == "shot").astype(int)
    frame_ev["is_pass"]    = (frame_ev["event"] == "pass").astype(int)
    frame_ev["is_dribble"] = (frame_ev["event"] == "dribble").astype(int)

    frame_ev[f"shots_{window}"]    = frame_ev["is_shot"].rolling(window, min_periods=1).sum().astype(int)
    frame_ev[f"passes_{window}"]   = frame_ev["is_pass"].rolling(window, min_periods=1).sum().astype(int)
    frame_ev[f"dribbles_{window}"] = frame_ev["is_dribble"].rolling(window, min_periods=1).sum().astype(int)

    # Possession run: consecutive frames the same team is dominant ball-holder
    frame_poss = (
        df[df["ball_possession"] == 1]
        .groupby("frame")["team"]
        .first()
        .reset_index()
        .rename(columns={"team": "poss_team"})
    )
    frame_ev = frame_ev.merge(frame_poss, on="frame", how="left")
    frame_ev["poss_team"] = frame_ev["poss_team"].fillna("none")

    # "none" frames (no ball possession tracked) are treated as neutral:
    # the run counter and owning team are carried forward unchanged.
    # Resetting on "none" would silently zero the highest-weighted momentum
    # component every time the ball detector misses a frame.
    runs = []
    run_len = 0
    prev_team = None
    for team in frame_ev["poss_team"]:
        if team == "none":
            # No ball detected — preserve the current run rather than breaking it
            runs.append(run_len)
            continue
        if team == prev_team:
            run_len += 1
        else:
            run_len = 1
            prev_team = team
        runs.append(run_len)
    frame_ev["possession_run"] = runs

    keep = ["frame", f"shots_{window}", f"passes_{window}",
            f"dribbles_{window}", "possession_run"]
    df = df.merge(frame_ev[keep], on="frame", how="left")
    return df


def add_ft_coordinates(df: pd.DataFrame) -> pd.DataFrame:
    """
    FIX 3: Derive real-world foot coordinates from normalized court position.

    Adds columns (no-op if ft_x already present from pipeline output):
      ft_x              — court x in feet (0=left baseline, 94=right baseline)
      ft_y              — court y in feet (0=bottom sideline, 50=top sideline)
      dist_to_basket_ft — Euclidean distance to nearest basket in feet
    """
    if "ft_x" in df.columns and "ft_y" in df.columns:
        # Already written by unified_pipeline; only recompute dist_to_basket_ft
        # if missing (old pipeline outputs).
        if "dist_to_basket_ft" not in df.columns:
            _bx_l, _by, _bx_r = 5.25, 25.0, 88.75
            _dl = np.hypot(df["ft_x"] - _bx_l, df["ft_y"] - _by)
            _dr = np.hypot(df["ft_x"] - _bx_r, df["ft_y"] - _by)
            df["dist_to_basket_ft"] = np.minimum(_dl, _dr).round(2)
        return df

    if "x_norm" not in df.columns or "y_norm" not in df.columns:
        return df

    df = df.copy()
    _xn = pd.to_numeric(df["x_norm"], errors="coerce")
    _yn = pd.to_numeric(df["y_norm"], errors="coerce")
    df["ft_x"] = (_xn * 94.0).round(2)
    df["ft_y"] = (_yn * 50.0).round(2)

    _bx_l, _by, _bx_r = 5.25, 25.0, 88.75
    _dl = np.hypot(df["ft_x"] - _bx_l, df["ft_y"] - _by)
    _dr = np.hypot(df["ft_x"] - _bx_r, df["ft_y"] - _by)
    df["dist_to_basket_ft"] = np.minimum(_dl, _dr).round(2)
    return df


def add_momentum_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Team-level momentum proxy features per frame.

    New columns:
      team_velocity_mean   — average velocity of all teammates this frame
      opp_velocity_mean    — average velocity of opponents this frame
      spacing_advantage    — own team spacing minus opponent (ft², calibrated)
    """
    frame_team = df.groupby(["frame", "team"]).agg(
        team_vel_mean=("velocity", "mean"),
        team_spacing_val=("team_spacing", "first"),
    ).reset_index()

    # Vectorized: pivot to wide (one row per frame, one column per team),
    # compute opponent stats as the row-sum minus own-team value, then melt back.
    non_ref = frame_team[frame_team["team"] != "referee"].copy()
    if non_ref.empty:
        df["team_velocity_mean"] = np.nan
        df["opp_velocity_mean"]  = np.nan
        df["spacing_advantage"]  = np.nan
        return df

    # Per-frame totals for the two non-ref teams
    frame_totals = non_ref.groupby("frame").agg(
        total_vel=("team_vel_mean", "sum"),
        total_spc=("team_spacing_val", "sum"),
        n_teams=("team", "count"),
    )

    non_ref = non_ref.join(frame_totals, on="frame")
    # When n_teams==2: opp_vel = total - own;  n_teams==1: opp = NaN
    non_ref["team_velocity_mean"] = non_ref["team_vel_mean"].round(2)
    non_ref["opp_velocity_mean"] = np.where(
        non_ref["n_teams"] == 2,
        (non_ref["total_vel"] - non_ref["team_vel_mean"]).round(2),
        np.nan,
    )
    non_ref["opp_spc"] = np.where(
        non_ref["n_teams"] == 2,
        non_ref["total_spc"] - non_ref["team_spacing_val"],
        np.nan,
    )
    non_ref["spacing_advantage"] = (
        non_ref["team_spacing_val"] - non_ref["opp_spc"]
    ).clip(-5000, 5000).round(1)

    momentum_df = non_ref[["frame", "team", "team_velocity_mean",
                            "opp_velocity_mean", "spacing_advantage"]]
    df = df.merge(momentum_df, on=["frame", "team"], how="left")

    # FIX 3: Recompute spacing_advantage from ft² convex hulls when ft coords
    # available.  Old CSVs may have team_spacing in raw pixel² (ISSUE-026 was
    # not backfilled everywhere), producing ±1,013,593 range.  ft-based hull
    # area is always in correct ft² units (should be roughly ±2000 ft²).
    if "ft_x" in df.columns and "ft_y" in df.columns and _SCIPY:
        _ft_rows = df[df["team"] != "referee"][["frame", "team", "ft_x", "ft_y"]].dropna()
        if not _ft_rows.empty:
            _hull_map: dict = {}
            for (fr, tm), grp in _ft_rows.groupby(["frame", "team"]):
                _pts = grp[["ft_x", "ft_y"]].values
                _area = 0.0
                if len(_pts) >= 3:
                    try:
                        _area = float(_ConvexHull(_pts).volume)
                    except Exception:
                        pass
                _hull_map[(fr, tm)] = _area
            _ft_df = pd.DataFrame(
                [{"frame": fr, "team": tm, "_ft_sp": area}
                 for (fr, tm), area in _hull_map.items()]
            )
            _ft_tot = (
                _ft_df.groupby("frame")["_ft_sp"]
                .agg(total="sum", n="count")
                .reset_index()
            )
            _ft_df = _ft_df.merge(_ft_tot, on="frame")
            _ft_df["spacing_advantage"] = np.where(
                _ft_df["n"] == 2,
                (_ft_df["_ft_sp"] - (_ft_df["total"] - _ft_df["_ft_sp"])).clip(-5000, 5000).round(1),
                np.nan,
            )
            df = df.merge(
                _ft_df[["frame", "team", "spacing_advantage"]],
                on=["frame", "team"],
                how="left",
                suffixes=("_px", ""),
            )
            if "spacing_advantage_px" in df.columns:
                df.drop(columns=["spacing_advantage_px"], inplace=True)

    return df


def add_basket_features(df: pd.DataFrame, windows: List[int] = None) -> pd.DataFrame:
    """
    Per-player rolling features on basket proximity and drive tendency.

    New columns for each window W:
      dist_to_basket_mean_{W}    — mean distance to basket
      vel_toward_basket_mean_{W} — mean velocity-toward-basket (positive = toward)
      drive_rate_{W}             — fraction of frames with drive_flag=1
    """
    if "distance_to_basket" not in df.columns:
        return df
    if windows is None:
        windows = _WINDOWS

    group_cols = ["game_id", "player_id"] if "game_id" in df.columns else ["player_id"]
    df = df.sort_values(group_cols + ["frame"]).copy()
    grp = df.groupby(group_cols, group_keys=False)

    for w in windows:
        df[f"dist_to_basket_mean_{w}"] = grp["distance_to_basket"].transform(
            lambda s, _w=w: s.rolling(_w, min_periods=1).mean().round(1)
        )
        if "vel_toward_basket" in df.columns:
            df[f"vel_toward_basket_mean_{w}"] = grp["vel_toward_basket"].transform(
                lambda s, _w=w: s.rolling(_w, min_periods=1).mean().round(2)
            )
        if "drive_flag" in df.columns:
            df[f"drive_rate_{w}"] = grp["drive_flag"].transform(
                lambda s, _w=w: (
                    s.rolling(_w, min_periods=1).sum()
                    / s.rolling(_w, min_periods=1).count()
                ).round(3)
            )
    return df


def add_game_flow_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Frame-level game flow features.

    New columns:
      turnover_flag       — 1 on frames where possession changes team
      pace_30             — shots + turnovers per 30 frames (rolling)
      shot_quality_proxy  — zone_weight × defender_factor × spacing_factor,
                            non-zero only on shot-event frames
      pick_roll_proxy     — 1 if ≥2 teammates are within 80px of the ball
                            handler this frame
    """
    # ── Turnover flag ──────────────────────────────────────────────────────
    frame_poss = (
        df[df["ball_possession"] == 1]
        .groupby("frame")["team"]
        .first()
        .reset_index()
        .sort_values("frame")
        .rename(columns={"team": "poss_team"})
    )
    frame_poss["turnover_flag"] = (
        frame_poss["poss_team"] != frame_poss["poss_team"].shift(1)
    ).astype(int)
    if len(frame_poss):
        frame_poss.iloc[0, frame_poss.columns.get_loc("turnover_flag")] = 0

    # ── Pace: shots + turnovers per 30 frames ─────────────────────────────
    if "event" in df.columns:
        frame_ev = (
            df.groupby("frame")["event"]
            .agg(lambda s: next((e for e in s if e != "none"), "none"))
            .reset_index()
            .sort_values("frame")
        )
        frame_ev["is_shot"] = (frame_ev["event"] == "shot").astype(int)
        frame_poss = frame_poss.merge(frame_ev[["frame", "is_shot"]], on="frame", how="left")
        frame_poss["is_shot"] = frame_poss["is_shot"].fillna(0).astype(int)

        # Suppress turnover_flag for possession changes that follow a shot within
        # _SHOT_SUPPRESS possession-frames: those are normal play transitions
        # (made basket / rebound), not unforced turnovers.
        _SHOT_SUPPRESS = 30
        recent_shot = (
            frame_poss["is_shot"].shift(1, fill_value=0)
            .rolling(_SHOT_SUPPRESS, min_periods=1).max()
            .astype(int)
        )
        frame_poss["turnover_flag"] = (
            frame_poss["turnover_flag"] & (recent_shot == 0)
        ).astype(int)

        frame_poss["pace_30"] = (
            (frame_poss["is_shot"] + frame_poss["turnover_flag"])
            .rolling(30, min_periods=1).sum().round(2)
        )
    else:
        frame_poss["pace_30"] = 0.0

    # ── Shot quality proxy (A-6: prefer xFG model over hand formula) ──────
    _zone_weight = {
        "paint":     1.00,
        "corner_3":  0.85,
        "3pt_arc":   0.75,
        "mid_range": 0.55,
        "backcourt": 0.05,
    }
    _xfg_model_used = False
    if "court_zone" in df.columns and "nearest_opponent" in df.columns:
        shot_mask = df.get("event", pd.Series("none", index=df.index)) == "shot"

        # A-6: Try CV stack first, then v1, then fall back to hand formula
        _xfg_model_path_stack = os.path.join(_DATA_DIR, "..", "data", "models", "xfg_cv_stack.pkl")
        _xfg_model_path_v1    = os.path.join(_DATA_DIR, "..", "data", "models", "xfg_v1.pkl")
        _chosen_model_path    = None
        for _p in (_xfg_model_path_stack, _xfg_model_path_v1):
            if os.path.exists(_p):
                _chosen_model_path = _p
                break

        if _chosen_model_path and shot_mask.any():
            try:
                from src.prediction.xfg_model import load as _xfg_load, predict_batch as _predict_batch
                _xfg_obj = _xfg_load(_chosen_model_path)
                _shot_rows = df[shot_mask].copy()
                _xfg_preds = _predict_batch(_xfg_obj, _shot_rows)
                _sq = pd.Series(0.0, index=df.index)
                _sq.loc[_shot_rows.index] = _xfg_preds.values
                df["shot_quality_proxy"] = _sq.round(3)
                _xfg_model_used = True
            except Exception:
                pass

        if not _xfg_model_used:
            zone_w    = df["court_zone"].map(_zone_weight).fillna(0.5)
            opp_d     = pd.to_numeric(df["nearest_opponent"], errors="coerce").fillna(50.0)
            # Sentinel cleanup: team_spacing == 0.0 means invalid hull (not real tight spacing).
            # Replace sentinel with median before normalising so shot_quality_proxy is not
            # artificially suppressed on the 50-79% of shots where hull detection fails.
            _ts_raw   = pd.to_numeric(df.get("team_spacing", pd.Series(dtype=float)), errors="coerce").replace(0.0, np.nan)
            _ts_med   = _ts_raw.median()
            spacing   = _ts_raw.fillna(_ts_med if not np.isnan(_ts_med) else 0.0)
            # Robust normalisation: divide by 2× the median of non-zero rows.
            # This makes a "median-spaced" player land at ~0.5 and clips any
            # outlier/sentinel value to 1.0.  Using max() as the denominator
            # allowed a single extreme frame to collapse every other row toward
            # zero; median is fully resistant to any number of outliers.
            _pos_mask = spacing > 0
            if _pos_mask.any():
                _spacing_med = float(np.median(spacing[_pos_mask]))
                _spacing_scale = max(_spacing_med * 2.0, 1.0)
            else:
                _spacing_scale = 1.0
            spacing_n = (spacing / _spacing_scale).clip(0.0, 1.0)
            sq_proxy  = (zone_w * (1.0 / (1.0 + opp_d / 50.0)) * (0.5 + 0.5 * spacing_n)).round(3)
            df["shot_quality_proxy"] = np.where(shot_mask, sq_proxy, 0.0)
    else:
        df["shot_quality_proxy"] = 0.0

    # ── Pick-roll proxy (vectorized) ───────────────────────────────────────
    # For each frame: find the ball handler (ball_possession==1), then count
    # teammates within 80px.  Implemented without a Python loop via a self-merge.
    _pos = df[["frame", "player_id", "team", "x_position",
               "y_position", "ball_possession"]].copy()
    _handlers = _pos[_pos["ball_possession"] == 1][
        ["frame", "team", "x_position", "y_position"]
    ].rename(columns={"x_position": "hx", "y_position": "hy", "team": "h_team"})
    # Keep only one handler per frame (first in index order)
    _handlers = _handlers.drop_duplicates(subset="frame")

    if len(_handlers):
        # Join every player row to its frame's handler
        _merged = _pos.merge(_handlers, on="frame", how="inner")
        # Teammates (same team, not the handler itself)
        _mates = _merged[
            (_merged["team"] == _merged["h_team"]) &
            (_merged["ball_possession"] == 0)
        ].copy()
        _mates["near"] = (
            np.hypot(_mates["x_position"] - _mates["hx"],
                     _mates["y_position"] - _mates["hy"]) < 80
        ).astype(int)
        _near_count = _mates.groupby("frame")["near"].sum().rename("near_count")
        _frame_pr = _handlers[["frame"]].join(_near_count, on="frame").fillna(0)
        _frame_pr["pick_roll_proxy"] = (_frame_pr["near_count"] >= 2).astype(int)
        pr_df = _frame_pr[["frame", "pick_roll_proxy"]]
    else:
        pr_df = pd.DataFrame({"frame": df["frame"].unique(), "pick_roll_proxy": 0})

    # ── Merge all frame-level features back ───────────────────────────────
    keep = ["frame", "turnover_flag", "pace_30"]
    df = df.merge(frame_poss[keep], on="frame", how="left")
    df["turnover_flag"] = df["turnover_flag"].fillna(0).astype(int)
    df["pace_30"]       = df["pace_30"].fillna(0.0)
    df = df.merge(pr_df, on="frame", how="left")
    df["pick_roll_proxy"] = df["pick_roll_proxy"].fillna(0).astype(int)
    return df


def add_per100_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add pace-adjusted per-100-possession normalizations.

    Uses possession_run changes to estimate possession count per frame window,
    then normalizes event counts and distance stats to per-100-possession rates.

    New columns:
      possessions_est          — cumulative possession count up to this frame
      shots_per100             — shots_90 normalized to per-100-possessions
      passes_per100            — passes_90 normalized
      dribbles_per100          — dribbles_90 normalized
      dist_per100_{W}          — dist_traveled_{W} normalized
    """
    df = df.copy()

    # Estimate possession count: each time possession_run resets to 1 = new possession.
    if "possession_run" in df.columns:
        # Aggregate to one row per frame (possession_run is frame-level)
        frame_pr = (
            df.groupby("frame")["possession_run"]
            .first()
            .reset_index()
            .sort_values("frame")
        )
        # New possession starts when possession_run == 1 (reset)
        frame_pr["new_poss"] = (frame_pr["possession_run"] == 1).astype(int)
        frame_pr["possessions_est"] = frame_pr["new_poss"].cumsum().clip(lower=1)

        poss_map = frame_pr.set_index("frame")["possessions_est"].to_dict()
        df["possessions_est"] = df["frame"].map(poss_map).fillna(1)

        # Per-100 normalized event rates (use 90-frame window cols if available)
        _event_win = 90
        for evt in ("shots", "passes", "dribbles"):
            col = f"{evt}_{_event_win}"
            if col in df.columns:
                # per-100 = (events_in_window / possessions_in_window) * 100
                # Approximate possessions in window as possessions_est rolling change
                # Use simple ratio: clip_events / total_possessions * 100
                df[f"{evt}_per100"] = (
                    (df[col] / df["possessions_est"].clip(lower=1)) * 100
                ).round(1)

        # Per-100 normalized distance traveled
        for w in _WINDOWS:
            dcol = f"dist_traveled_{w}"
            if dcol in df.columns:
                df[f"dist_per100_{w}"] = (
                    df.groupby("player_id", group_keys=False).apply(
                        lambda g: (
                            g[dcol] / g["possessions_est"].clip(lower=1) * 100
                        ).round(1),
                        include_groups=False,
                    )
                )
    return df


def add_context_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalise and propagate scoreboard / possession / play-type columns that
    are written by the unified pipeline into tracking_data.csv.

    New columns (already present if pipeline ran with the new classifiers;
    silently skipped if absent so old CSVs remain compatible):
      scoreboard_game_clock  — float, seconds remaining in period
      scoreboard_shot_clock  — float, shot clock value
      scoreboard_score_diff  — int, home minus away score
      scoreboard_period      — int, 1-4 or 5 for OT
      possession_type        — categorical string
      play_type              — categorical string
      possession_duration_sec — float
      paint_touches          — int
      off_ball_distance      — float
      shot_clock_est         — float, 24 minus possession duration

    Args:
        df: Tracking DataFrame (may or may not contain the new columns).

    Returns:
        DataFrame with context columns coerced to correct dtypes.
    """
    df = df.copy()

    _float_cols = [
        "scoreboard_game_clock", "scoreboard_shot_clock",
        "possession_duration_sec", "off_ball_distance",
        # Bug 20 fix: shot_clock_est is computed per-frame in unified_pipeline.py;
        # ffill would hold stale step-values across possession gaps.  Exclude from
        # propagation — NaN rows stay NaN and are handled downstream.
        # "shot_clock_est",  # removed from ffill group
    ]
    # Bug 20 fix: coerce shot_clock_est to numeric but do NOT ffill — it
    # is written per-frame and must decrement continuously.
    _float_coerce_only = ["shot_clock_est"]
    _int_cols = [
        "scoreboard_score_diff", "scoreboard_period", "paint_touches",
    ]
    _str_cols = ["possession_type", "play_type"]

    for col in _float_cols + _float_coerce_only:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in _int_cols:
        if col in df.columns:
            # BUG 41 FIX: do NOT fillna(0) before ffill — that turns NaN→0 which
            # blocks forward-propagation of real values.  Cast to float first so
            # NaN is preserved, then ffill/bfill, then fillna(0) for any remaining
            # gaps, then convert to int.
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in _str_cols:
        if col in df.columns:
            df[col] = df[col].fillna("unknown").astype(str)

    # Forward-fill scoreboard values within each frame group — they are
    # written once per 30-frame OCR window, so non-OCR frames are empty.
    # BUG 41 FIX: ffill BEFORE fillna so real values propagate across blank rows.
    for col in _float_cols + _int_cols:
        if col in df.columns:
            df[col] = df[col].ffill().bfill()

    # Final int coercion — only after propagation so 0 means "genuinely unknown"
    for col in _int_cols:
        if col in df.columns:
            df[col] = df[col].fillna(0).astype(int)

    return df


def load_rotowire_starters() -> dict:
    """Load today's confirmed/projected starting lineups from RotoWire cache.

    Reads ``data/cache/rotowire_lineups_parsed.json`` (produced by
    ``scripts/parse_rotowire_lineups.py``) and returns a mapping of
    ``team_abbrev -> set(lower-cased starter names)``.

    Returns:
        ``{team_abbrev: {"shai gilgeous-alexander", ...}, ...}`` — empty dict
        when the cache is missing or unreadable. Caller treats missing teams
        as "unknown starters" and emits NaN, NOT 0 (see caller).

    WALK-FORWARD CAVEAT:
        The underlying RotoWire HTML is a DAILY SNAPSHOT — overwritten each
        day. It is therefore usable ONLY for LIVE prediction on today's
        slate. Do NOT use confirmed_starter as a training feature: at train
        time the cache reflects today's slate, not the historical game date,
        which would leak / mislabel. Training pipelines should treat
        confirmed_starter as NaN so it gets imputed or dropped downstream.
    """
    import json as _json
    path = os.path.join(_DATA_DIR, "cache", "rotowire_lineups_parsed.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            parsed = _json.load(f)
    except Exception:
        return {}

    out: dict[str, set[str]] = {}
    for team_abbrev, plist in (parsed.get("teams") or {}).items():
        starters = {
            (p.get("player_name") or "").strip().lower()
            for p in plist
            if p.get("is_starter") and (p.get("player_name") or "").strip()
        }
        if starters:
            out[team_abbrev] = starters
    return out


# ─────────────────────────────────────────────────────────────────────────
# Injury features (iter 4 — NBA official injury feed)
# ─────────────────────────────────────────────────────────────────────────
_INJ_DF_CACHE: Optional[pd.DataFrame] = None  # type: ignore[assignment]


def load_injury_features() -> pd.DataFrame:
    """Load merged NBA injury parquet (built by scripts/build_injury_features.py).

    Returns one-row-per-(player_name_lower, listed_date) DataFrame with
    columns: player_name_lower, player_name, team_abbrev, status, reason,
    listed_date (pd.Timestamp, UTC-naive), source, player_id.

    Returns empty DataFrame if the parquet is missing — callers must handle.

    WALK-FORWARD SAFETY:
        The DataFrame returns ALL listed injury records (no asof filter
        applied here). It is the caller's (compute_injury_features) job to
        filter ``listed_date < asof_dt`` to prevent look-ahead leakage. A
        2026-04-15 game prediction must never see a 2026-05-02 injury
        listing — even though both rows live in the same parquet.
    """
    global _INJ_DF_CACHE
    if _INJ_DF_CACHE is not None:
        return _INJ_DF_CACHE
    path = os.path.join(_DATA_DIR, "cache", "injury_features.parquet")
    if not os.path.exists(path):
        _INJ_DF_CACHE = pd.DataFrame(columns=[
            "player_name_lower", "player_name", "team_abbrev", "status",
            "reason", "listed_date", "source", "player_id",
        ])
        return _INJ_DF_CACHE
    try:
        df = pd.read_parquet(path)
        # Force naive timestamps for safe comparison vs caller's asof_dt.
        if "listed_date" in df.columns:
            df["listed_date"] = pd.to_datetime(df["listed_date"], errors="coerce", utc=True)
            try:
                df["listed_date"] = df["listed_date"].dt.tz_convert(None)
            except (TypeError, AttributeError):
                pass
        _INJ_DF_CACHE = df
    except Exception:
        _INJ_DF_CACHE = pd.DataFrame(columns=[
            "player_name_lower", "player_name", "team_abbrev", "status",
            "reason", "listed_date", "source", "player_id",
        ])
    return _INJ_DF_CACHE


def compute_injury_features(
    player_name: str,
    team_abbrev: str,
    asof_dt,
) -> dict:
    """Compute 4 walk-forward-safe injury features for one (player, asof_dt).

    Only injury records with ``listed_date < asof_dt`` are visible. For
    the player's status we pick the MOST RECENT listing strictly before
    asof_dt (so a player listed Out 2026-05-02 and not updated since is
    still Out on 2026-05-10).

    Args:
        player_name: Player display name ("Jayson Tatum").
        team_abbrev: 3-letter team code ("BOS"). Used for team-count features.
        asof_dt: timezone-naive pd.Timestamp / datetime — the prediction time.
                 Anything in the parquet with listed_date >= asof_dt is hidden.

    Returns:
        dict with 4 keys:
          injury_status_active        : str | None
          injury_hours_since_listed   : float  (999.0 if no record)
          team_inj_count_out          : int    (Out teammates listed < asof_dt)
          team_inj_count_questionable : int    (Questionable teammates listed < asof_dt)

    FALLBACK:
        Parquet missing OR asof_dt older than earliest listed_date →
        returns (None, 999.0, 0, 0) — never raises.
    """
    default = {
        "injury_status_active":        None,
        "injury_hours_since_listed":   999.0,
        "team_inj_count_out":          0,
        "team_inj_count_questionable": 0,
    }
    df = load_injury_features()
    if df.empty:
        return default

    try:
        asof_ts = pd.to_datetime(asof_dt, utc=True, errors="coerce")
        if pd.isna(asof_ts):
            return default
        try:
            asof_ts = asof_ts.tz_convert(None)
        except (TypeError, AttributeError):
            asof_ts = asof_ts.replace(tzinfo=None) if getattr(asof_ts, "tzinfo", None) else asof_ts
    except Exception:
        return default

    # Walk-forward filter: only listings PRIOR to asof_ts are visible.
    visible = df[df["listed_date"] < asof_ts]
    if visible.empty:
        return default

    # Per-player most-recent listing
    name_lc = (player_name or "").strip().lower()
    status_active = None
    hours_since = 999.0
    if name_lc:
        player_rows = visible[visible["player_name_lower"] == name_lc]
        if not player_rows.empty:
            latest = player_rows.iloc[player_rows["listed_date"].argmax()]
            status_active = latest.get("status") or None
            try:
                delta = asof_ts - latest["listed_date"]
                hours_since = float(delta.total_seconds() / 3600.0)
                if hours_since < 0 or hours_since > 1e6:
                    hours_since = 999.0
            except Exception:
                hours_since = 999.0

    # Team-level counts: latest-status-per-teammate, then count Out / Questionable.
    team = (team_abbrev or "").strip().upper()
    team_out = 0
    team_q   = 0
    if team:
        team_rows = visible[visible["team_abbrev"] == team]
        if not team_rows.empty:
            # Keep most-recent row per teammate
            team_rows = team_rows.sort_values("listed_date").drop_duplicates(
                subset=["player_name_lower"], keep="last"
            )
            team_out = int((team_rows["status"] == "Out").sum())
            team_q   = int((team_rows["status"] == "Questionable").sum())

    return {
        "injury_status_active":        status_active,
        "injury_hours_since_listed":   hours_since,
        "team_inj_count_out":          team_out,
        "team_inj_count_questionable": team_q,
    }


def add_external_player_features(
    df: pd.DataFrame,
    season: str = "2024-25",
    home_team: str = "",
    away_team: str = "",
) -> pd.DataFrame:
    """
    Enrich per-player rows with pre-game context features from external data sources.

    Sources used (all optional — gracefully skipped if cache unavailable):
      - Basketball Reference: BPM, VORP, Win Shares (bbref_scraper)
      - NBA Tracking API: hustle stats, on/off splits (nba_tracking_stats)
      - Synergy play types: pts/possession by play type (nba_tracking_stats)
      - Injury monitor: combined ESPN + RotoWire + NBA official (injury_monitor)
      - HoopsHype contracts: contract year flag, salary tier (contracts_scraper)
      - Shot dashboard: contested%, C+S%, pull-up%, defender dist (nba_tracking_stats)

    New columns (all per-player constant within a game, merged on player_name):
      bbref_bpm, bbref_vorp, bbref_ws, bbref_ws_per_48
      hustle_deflections_pg, hustle_charges_pg, hustle_contested_shots
      on_off_diff, on_court_net_rtg
      synergy_iso_ppp, synergy_pnr_ppp, synergy_spotup_ppp
      injury_status_multiplier
      contract_year_flag, cap_hit_pct
      contested_shot_pct, catch_and_shoot_pct, pull_up_pct, avg_defender_dist

    Args:
        df: Tracking DataFrame with a ``player_name`` column.
        season: Season for cache lookups (e.g. "2024-25").

    Returns:
        DataFrame with external feature columns added. Rows without a matching
        player_name get NaN / 0 defaults.
    """
    if "player_name" not in df.columns:
        return df

    df = df.copy()
    player_names = df["player_name"].dropna().unique().tolist()

    # ── Basketball Reference: BPM / VORP / Win Shares ──────────────────────
    bbref_lookup: dict = {}
    try:
        from src.data.bbref_scraper import get_advanced_stats
        adv = get_advanced_stats(season)
        for r in adv:
            name = r.get("player_name", "").lower()
            if name:
                bbref_lookup[name] = r
    except Exception:
        pass

    # ── Hustle Stats ────────────────────────────────────────────────────────
    hustle_lookup: dict = {}
    try:
        from src.data.nba_tracking_stats import get_hustle_stats
        hustle = get_hustle_stats(season)
        for r in hustle:
            name = r.get("player_name", "").lower()
            if name:
                hustle_lookup[name] = r
    except Exception:
        pass

    # ── On/Off Splits ───────────────────────────────────────────────────────
    # NBA VS_PLAYER_NAME returns "Last, First" — tracking writes "First Last".
    # Index both formats so the per-player merge below succeeds either way.
    on_off_lookup: dict = {}
    try:
        from src.data.nba_tracking_stats import get_on_off_splits
        on_off = get_on_off_splits(season)
        for r in on_off:
            name = r.get("player_name", "").strip()
            if not name:
                continue
            on_off_lookup[name.lower()] = r
            if "," in name:
                last, first = [p.strip() for p in name.split(",", 1)]
                on_off_lookup[f"{first} {last}".lower()] = r
    except Exception:
        pass

    # ── Synergy Play Types ──────────────────────────────────────────────────
    # Prefer per-player synergy cache (one row per player × play_type with ppp).
    # Falls back to team-level cache (broadcast team ppp to all players on team)
    # when player file is missing — preserves prior behavior for unseen players.
    synergy_lookup: dict = {}
    try:
        import os as _os
        import json as _json
        cache_dir = _os.path.join(_DATA_DIR, "nba")
        # Map team_abbrev -> {play_type_lower: ppp} for fallback per season.
        _team_ppp: dict = {}
        # Iterate play-types we actually consume downstream (matches _ext_features).
        for play_type in ("Isolation", "PRBallHandler", "Spotup"):
            player_path = _os.path.join(
                cache_dir, f"synergy_player_{play_type}_{season}.json"
            )
            team_path = _os.path.join(
                cache_dir, f"synergy_offensive_{play_type}_{season}.json"
            )
            loaded_player = False
            if _os.path.exists(player_path):
                try:
                    with open(player_path, encoding="utf-8") as _f:
                        for r in _json.load(_f):
                            pname = (r.get("player_name") or "").lower()
                            if not pname:
                                continue
                            play = (r.get("play_type") or play_type).lower()
                            ppp = r.get("ppp")
                            if ppp is None:
                                continue
                            synergy_lookup.setdefault(pname, {})[play] = float(ppp)
                    loaded_player = True
                except Exception:
                    loaded_player = False
            # Build team-level fallback regardless (some rosters may miss in player file).
            if _os.path.exists(team_path):
                try:
                    with open(team_path, encoding="utf-8") as _f:
                        for r in _json.load(_f):
                            team = (r.get("team_abbreviation") or "").upper()
                            if not team:
                                continue
                            play = (r.get("play_type") or play_type).lower()
                            ppp = r.get("ppp")
                            if ppp is None:
                                continue
                            _team_ppp.setdefault(team, {})[play] = float(ppp)
                except Exception:
                    pass
            # Marker keeps lints happy
            _ = loaded_player
        # Stash team fallback on the lookup dict under a sentinel key so the
        # per-row builder below can resolve unseen players via their team.
        if _team_ppp:
            synergy_lookup["__team_fallback__"] = _team_ppp
    except Exception:
        pass

    # ── Injury Status Multipliers ───────────────────────────────────────────
    injury_lookup: dict = {}
    try:
        from src.data.injury_monitor import get_combined_injury_status
        _INJURY_MULT = {"Out": 0.0, "Doubtful": 0.0, "Questionable": 0.70,
                        "Day-To-Day": 0.85, "GTD": 0.85, "Probable": 0.95,
                        "Available": 1.0, "Unknown": 0.95}
        for name in player_names:
            if not name or name == "unknown":
                continue
            try:
                status = get_combined_injury_status(name).get("status", "Unknown")
                injury_lookup[name.lower()] = _INJURY_MULT.get(status, 0.95)
            except Exception:
                pass
    except Exception:
        pass

    # ── News Reaction Window ─────────────────────────────────────────────────
    # Issue #17 fix: anchor on game_datetime per row, not datetime.utcnow().
    # The rotowire_news.json cache is overwritten every poll, so during
    # historical training every row would otherwise pick up the same "today's"
    # news → constant feature (dead-weight). For now we expose the lookup as
    # a per-player dict of {player → most_recent_pub_dt}; the column write at
    # the bottom of this function compares against game_dt if present in the
    # row, otherwise emits NaN (training-safe — the model treats it as
    # missing rather than learning from a constant).
    news_by_player: dict = {}
    news_cache_freshness_hours = 1e9  # huge = treat as stale → NaN downstream
    try:
        import json as _json, os as _os
        _rw_cache = _os.path.join(_DATA_DIR, "external", "rotowire_news.json")
        if _os.path.exists(_rw_cache):
            with open(_rw_cache, encoding="utf-8") as _f:
                _rw_items = _json.load(_f)
            import unicodedata as _ud
            def _nn(s: str) -> str:
                return _ud.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()
            import datetime as _dtmod
            for _it in _rw_items:
                if (_it.get("status_guess", "Unknown") == "Unknown"):
                    continue
                _pkey = _nn(_it.get("player_name", ""))
                _pub_raw = _it.get("published", "")
                _pub_dt = None
                for _fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z",
                             "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                    try:
                        _parsed = _dtmod.datetime.strptime(_pub_raw.strip(), _fmt)
                        _pub_dt = _parsed.replace(tzinfo=None) if _parsed.tzinfo else _parsed
                        break
                    except (ValueError, AttributeError):
                        continue
                if _pub_dt is None:
                    continue
                if _pkey not in news_by_player or _pub_dt > news_by_player[_pkey]:
                    news_by_player[_pkey] = _pub_dt
            # Compute cache freshness: hours between max pub_dt and utcnow.
            if news_by_player:
                _max_pub = max(news_by_player.values())
                _delta = _dtmod.datetime.utcnow() - _max_pub
                news_cache_freshness_hours = float(_delta.total_seconds() / 3600.0)
    # Build the per-player news_lookup used by the column writer below.
    # Live mode (cache freshness ≤ 72h): emit (now - pub_dt) as in the
    #   original behavior — this is the right value for predicting today's slate.
    # Training mode (cache freshness > 72h): emit NaN (via float('nan')) so
    #   the model sees missing rather than a contaminated constant.
        import math as _math
        news_lookup: dict = {}
        _is_live = news_cache_freshness_hours <= 72.0
        if _is_live:
            import datetime as _dtmod
            _now_utc = _dtmod.datetime.utcnow()
            for _pkey, _dt in news_by_player.items():
                _hrs = (_now_utc - _dt).total_seconds() / 3600.0
                news_lookup[_pkey] = max(0.0, min(999.0, _hrs))
        # If not live, news_lookup stays empty → column writer hits the
        # NaN fallback at the per-row write site.
    except Exception:
        news_lookup = {}
        _is_live = False
    _news_is_live = locals().get("_is_live", False)

    # ── Contract Features ────────────────────────────────────────────────────
    contract_lookup: dict = {}
    try:
        from src.data.contracts_scraper import fetch_salary_index
        contract_lookup = fetch_salary_index(season)
    except Exception:
        pass

    # ── Shot Dashboard ───────────────────────────────────────────────────────
    shot_dash_lookup: dict = {}
    try:
        import json as _json, os as _os
        sd_all_path = _os.path.join(_DATA_DIR, "..", "data", "nba",
                                    f"shot_dashboard_all_{season.replace('-', '_')}.json")
        if _os.path.exists(sd_all_path):
            with open(sd_all_path) as _f:
                sd_all = _json.load(_f)
            for pid_str, rec in sd_all.items():
                name = None
                # We need player_name — look up from player avgs
                avgs_path = _os.path.join(_DATA_DIR, "..", "data", "nba",
                                          f"player_avgs_{season}.json")
                if _os.path.exists(avgs_path):
                    with open(avgs_path) as _f2:
                        avgs = _json.load(_f2)
                    for pname, info in avgs.items():
                        if str(info.get("player_id", "")) == pid_str:
                            name = pname.lower()
                            break
                if name:
                    shot_dash_lookup[name] = rec
    except Exception:
        pass

    # ── A-7: ELO features (game-level constants) ─────────────────────────────
    _elo_feats = {"home_elo": 1500.0, "away_elo": 1500.0, "elo_differential": 0.0}
    if _HAS_ADVANCED and (home_team or away_team):
        try:
            _elo_feats = get_elo_features(home_team or "", away_team or "")
        except Exception:
            pass

    # ── Build per-player feature rows ────────────────────────────────────────
    def _ext_features(player_name: str) -> dict:
        key = (player_name if isinstance(player_name, str) else "").lower()
        bb  = bbref_lookup.get(key, {})
        hu  = hustle_lookup.get(key, {})
        oo  = on_off_lookup.get(key, {})
        syn = synergy_lookup.get(key, {})
        con = contract_lookup.get(key, {})
        sd  = shot_dash_lookup.get(key, {})

        # A-8: Opponent defensive trajectory (uses opp_team not available here;
        # inject as 0.0 unless df has opp_team_abbrev column — wired post Phase G)
        opp_def_trend = 0.0
        if _HAS_ADVANCED:
            try:
                opp_def_trend = get_opp_def_trend("", season)  # team TBD post-Phase G
            except Exception:
                pass

        # A-9: Home/away splits
        ha_splits = {"pts_delta": 0.0, "reb_delta": 0.0, "ast_delta": 0.0}
        if _HAS_ADVANCED and isinstance(player_name, str) and player_name:
            try:
                ha_splits = get_home_away_splits(player_name, season)
            except Exception:
                pass

        # A-10: Drive outcome distribution
        drive_outcomes = {
            "drive_finish_rate": 0.35, "drive_foul_rate": 0.25,
            "drive_kickout_rate": 0.28, "drive_tov_rate": 0.12,
        }
        if _HAS_ADVANCED and isinstance(player_name, str) and player_name:
            try:
                drive_outcomes = get_drive_outcomes(player_name)
            except Exception:
                pass

        return {
            # BBRef
            "bbref_bpm":             float(bb.get("bpm", 0.0) or 0.0),
            "bbref_vorp":            float(bb.get("vorp", 0.0) or 0.0),
            "bbref_ws":              float(bb.get("win_shares", 0.0) or 0.0),
            "bbref_ws_per_48":       float(bb.get("ws_per_48", 0.0) or 0.0),
            # Hustle
            "hustle_deflections_pg": float(hu.get("deflections_pg", 0.0) or 0.0),
            "hustle_charges_pg":     float(hu.get("charges_per_game", 0.0) or 0.0),
            "hustle_contested_shots":int(hu.get("contested_shots", 0) or 0),
            # On/off
            "on_off_diff":           float(oo.get("on_off_diff", 0.0) or 0.0),
            "on_court_net_rtg":      float(oo.get("on_court_net_rtg", 0.0) or 0.0),
            # Synergy
            "synergy_iso_ppp":       float(syn.get("isolation", 0.0) or 0.0),
            "synergy_pnr_ppp":       float(syn.get("prballhandler", 0.0) or 0.0),
            "synergy_spotup_ppp":    float(syn.get("spotup", 0.0) or 0.0),
            # Injury / news
            "injury_status_multiplier":  float(injury_lookup.get(key, 1.0)),
            "news_reaction_window_hrs":  (float(news_lookup[key]) if (_news_is_live and key in news_lookup) else float("nan")),
            # Contract
            "contract_year_flag":    int(bool(con.get("contract_year", False))),
            "cap_hit_pct":           float(con.get("cap_hit_pct", 0.0) or 0.0),
            # Shot dashboard
            "contested_shot_pct":    float(sd.get("contested_pct", 0.0) or 0.0),
            "catch_and_shoot_pct":   float(sd.get("catch_and_shoot_pct", 0.0) or 0.0),
            "pull_up_pct":           float(sd.get("pull_up_pct", 0.0) or 0.0),
            "avg_defender_dist":     float(sd.get("avg_defender_dist_contested", 0.0) or 0.0),
            # A-7: ELO (game-level constants broadcast to all players)
            "elo_home":              _elo_feats["home_elo"],
            "elo_away":              _elo_feats["away_elo"],
            "elo_diff":              _elo_feats["elo_differential"],
            # A-8: Opponent defensive trajectory
            "opp_def_rtg_trend":     opp_def_trend,
            # A-9: Home/away splits
            "home_away_pts_delta":   ha_splits["pts_delta"],
            "home_away_reb_delta":   ha_splits["reb_delta"],
            "home_away_ast_delta":   ha_splits["ast_delta"],
            # A-10: Drive outcomes
            "drive_finish_rate":     drive_outcomes["drive_finish_rate"],
            "drive_foul_rate":       drive_outcomes["drive_foul_rate"],
            "drive_kickout_rate":    drive_outcomes["drive_kickout_rate"],
            "drive_tov_rate":        drive_outcomes["drive_tov_rate"],
        }

    # Vectorized: build feature df and merge
    feature_rows = [_ext_features(n) for n in df["player_name"]]
    feat_df = pd.DataFrame(feature_rows, index=df.index)

    # Attach columns
    for col in feat_df.columns:
        df[col] = feat_df[col]

    # ── confirmed_starter (RotoWire daily snapshot — LIVE-ONLY) ─────────────
    # NaN-by-default: when the cache is absent, OR the player's team isn't
    # in today's slate, this stays NaN so training pipelines drop/impute it
    # rather than learning from stale day-of labels. Only when we have a
    # known team's starter list do we emit a hard 0/1.
    rw_starters = load_rotowire_starters()
    if rw_starters and "player_name" in df.columns:
        team_col = "team_abbrev" if "team_abbrev" in df.columns else None
        names_lc = df["player_name"].fillna("").astype(str).str.lower()

        def _is_starter(name_lc: str, team: str) -> float:
            team = (team or "").upper()
            if not team or team not in rw_starters:
                return float("nan")
            return 1.0 if name_lc in rw_starters[team] else 0.0

        if team_col:
            teams = df[team_col].fillna("").astype(str)
            df["confirmed_starter"] = [
                _is_starter(n, t) for n, t in zip(names_lc, teams)
            ]
        else:
            # No team column → can't disambiguate same-name players across
            # teams. Fall back: starter if name appears in ANY team's list.
            all_starters: set[str] = set().union(*rw_starters.values())
            df["confirmed_starter"] = names_lc.map(
                lambda n: 1.0 if n in all_starters else float("nan")
            )
    else:
        df["confirmed_starter"] = float("nan")

    # ── Injury features (iter 4 — NBA official injury feed) ─────────────────
    # Walk-forward safe: only injury records with listed_date < asof_dt are
    # visible (see compute_injury_features). Fallback (None, 999.0, 0, 0) when
    # parquet missing or asof_dt precedes all listings.
    #
    # asof_dt source priority (per-row):
    #   1. df["game_date"] column (preferred — historical / training rows)
    #   2. df["asof_dt"] column   (live prediction rows already carry it)
    #   3. NOW (last-resort live fallback)
    inj_df = load_injury_features()
    if not inj_df.empty and "player_name" in df.columns:
        # Resolve per-row asof_dt
        #   Priority: game_date col (historical/training) → asof_dt col (live rows)
        #   If neither exists we have no safe time anchor and MUST skip injury
        #   enrichment — falling back to utcnow() would leak today's injury
        #   status into historical training rows (look-ahead contamination).
        if "game_date" in df.columns:
            asof_series = pd.to_datetime(df["game_date"], errors="coerce", utc=True)
        elif "asof_dt" in df.columns:
            asof_series = pd.to_datetime(df["asof_dt"], errors="coerce", utc=True)
        else:
            # No date anchor available — skip rather than leak utcnow().
            df["injury_status_active"]        = None
            df["injury_hours_since_listed"]   = 999.0
            df["team_inj_count_out"]          = 0
            df["team_inj_count_questionable"] = 0
            return df
        try:
            asof_series = asof_series.dt.tz_convert(None)
        except (TypeError, AttributeError):
            pass

        team_col = "team_abbrev" if "team_abbrev" in df.columns else (
            "team" if "team" in df.columns else None
        )

        status_col: list = []
        hours_col:  list = []
        team_out_col: list = []
        team_q_col:   list = []
        for i, name in enumerate(df["player_name"]):
            team = df[team_col].iloc[i] if team_col else ""
            asof = asof_series.iloc[i] if i < len(asof_series) else pd.NaT
            feats = compute_injury_features(name, team, asof)
            status_col.append(feats["injury_status_active"])
            hours_col.append(feats["injury_hours_since_listed"])
            team_out_col.append(feats["team_inj_count_out"])
            team_q_col.append(feats["team_inj_count_questionable"])
        df["injury_status_active"]        = status_col
        df["injury_hours_since_listed"]   = hours_col
        df["team_inj_count_out"]          = team_out_col
        df["team_inj_count_questionable"] = team_q_col
    else:
        df["injury_status_active"]        = None
        df["injury_hours_since_listed"]   = 999.0
        df["team_inj_count_out"]          = 0
        df["team_inj_count_questionable"] = 0

    return df


def add_pose_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Derive ML-ready features from pose estimation columns.

    New columns:
      contest_arm_mean_30   — rolling 30-frame mean of contest_arm_angle per player
                              (0=arm low/relaxed, 1=arm fully raised above nose)
      jump_shot_flag        — 1 when event==shot AND jump_detected==1
                              (distinguishes jump shots from layups/dunks/tip-ins)
      shot_quality_pose     — shot_quality_proxy adjusted for nearest-opponent
                              contest arm angle when available; non-zero on shot frames
    """
    df = df.copy()

    # ── Rolling contest arm angle ──────────────────────────────────────────
    if "contest_arm_angle" in df.columns:
        df = df.sort_values(["player_id", "frame"])
        df["contest_arm_mean_30"] = (
            df.groupby("player_id", group_keys=False)["contest_arm_angle"]
            .transform(lambda s: s.rolling(30, min_periods=1).mean().round(3))
        )
    else:
        df["contest_arm_mean_30"] = 0.0

    # ── Jump shot flag ─────────────────────────────────────────────────────
    has_event = "event" in df.columns
    has_jump  = "jump_detected" in df.columns
    if has_event and has_jump:
        df["jump_shot_flag"] = (
            (df["event"] == "shot") & (df["jump_detected"] == 1)
        ).astype(int)
    else:
        df["jump_shot_flag"] = 0

    # ── Pose-enhanced shot quality ─────────────────────────────────────────
    # When a nearest opponent has a high contest_arm_angle, reduce shot quality.
    # Proxy: use the shooter's own contest_arm_mean_30 on shot frames
    # (high arm = shooter is contesting their own shot = defensive pressure visible).
    if "shot_quality_proxy" in df.columns and "contest_arm_angle" in df.columns:
        shot_mask = df.get("event", pd.Series("none", index=df.index)) == "shot"
        contest   = pd.to_numeric(df["contest_arm_angle"], errors="coerce").fillna(0.0)
        # Defender pressure adjustment: contest_arm_angle 0→1 reduces quality by up to 30%
        df["shot_quality_pose"] = np.where(
            shot_mask,
            (df["shot_quality_proxy"] * (1.0 - 0.30 * contest)).round(3),
            0.0,
        )
    else:
        df["shot_quality_pose"] = df.get("shot_quality_proxy", 0.0)

    return df


def fill_spatial_gaps(df: pd.DataFrame) -> pd.DataFrame:
    """
    Fix 1 & 2: Fill blank nearest_opponent and handler_isolation values by
    recomputing from frame-level position data.

    nearest_opponent: for each blank row, find minimum Euclidean distance to
    any player in the same frame with a different non-referee team label.

    handler_isolation: for each frame where a ball_possession==1 player exists
    and handler_isolation is blank, compute min distance from handler to any
    opponent (requires at least 2 opponents visible in the frame).
    """
    if "x_position" not in df.columns or "y_position" not in df.columns:
        return df
    if "team" not in df.columns:
        return df

    df = df.copy()
    x_vals = pd.to_numeric(df["x_position"], errors="coerce").values
    y_vals = pd.to_numeric(df["y_position"], errors="coerce").values
    teams  = df["team"].astype(str).values
    frames = df["frame"].values
    df_idx = df.index.values

    # ── nearest_opponent fallback ─────────────────────────────────────────────
    if "nearest_opponent" in df.columns:
        opp_vals = pd.to_numeric(df["nearest_opponent"], errors="coerce").values
        # treat 0.0 as missing — two players can't physically overlap
        need_opp = np.isnan(opp_vals) | (opp_vals <= 0)
        if need_opp.any():
            # Build per-frame index: frame → list of (x, y, team, position-in-array)
            from collections import defaultdict
            frame_entries: dict = defaultdict(list)
            for i, fr in enumerate(frames):
                if not (np.isnan(x_vals[i]) or np.isnan(y_vals[i])):
                    frame_entries[fr].append((x_vals[i], y_vals[i], teams[i], i))

            new_vals = opp_vals.copy()
            for pos, (fr, xi, yi, ti, need) in enumerate(
                zip(frames, x_vals, y_vals, teams, need_opp)
            ):
                if not need:
                    continue
                if np.isnan(xi) or np.isnan(yi):
                    continue
                entries = frame_entries.get(fr, [])
                dists = [
                    float(np.hypot(xi - ox, yi - oy))
                    for ox, oy, ot, _ in entries
                    if ot != ti and ot != "referee"
                ]
                if dists:
                    new_vals[pos] = round(min(dists), 1)
            df["nearest_opponent"] = new_vals
            filled = int(np.sum(need_opp & ~np.isnan(new_vals)))
            print(f"  [fill_spatial] nearest_opponent: filled {filled} blank rows")

    # ── handler_isolation fallback ───────────────────────────────────────────
    if "handler_isolation" in df.columns and "ball_possession" in df.columns:
        iso_vals  = pd.to_numeric(df["handler_isolation"], errors="coerce").values
        poss_vals = pd.to_numeric(df["ball_possession"],  errors="coerce").fillna(0).values
        # treat 0.0 as missing — handler can't have isolation distance of 0
        need_iso  = np.isnan(iso_vals) | (iso_vals <= 0)

        if need_iso.any():
            # Per frame: find handler, compute min opp distance if 2+ opponents visible
            frame_iso: dict = {}
            from collections import defaultdict as _dd
            frame_entries2: dict = _dd(list)
            for i, fr in enumerate(frames):
                if not (np.isnan(x_vals[i]) or np.isnan(y_vals[i])):
                    frame_entries2[fr].append((x_vals[i], y_vals[i], teams[i], bool(poss_vals[i])))

            for fr, entries in frame_entries2.items():
                handlers = [(x, y, t) for x, y, t, has_ball in entries if has_ball]
                if not handlers:
                    continue
                hx, hy, ht = handlers[0]
                opps = [(x, y) for x, y, t, _ in entries if t != ht and t != "referee"]
                if len(opps) < 2:
                    continue
                dists = [float(np.hypot(hx - ox, hy - oy)) for ox, oy in opps]
                frame_iso[fr] = round(min(dists), 1)

            if frame_iso:
                new_iso = iso_vals.copy()
                for pos, (fr, need) in enumerate(zip(frames, need_iso)):
                    if need and fr in frame_iso:
                        new_iso[pos] = frame_iso[fr]
                df["handler_isolation"] = new_iso
                filled = int(np.sum(need_iso & ~np.isnan(new_iso)))
                print(f"  [fill_spatial] handler_isolation: filled {filled} blank frames")

    return df


def impute_team_spacing(df: pd.DataFrame) -> pd.DataFrame:
    """Forward-fill team_spacing per (game_id, team) for invalid-hull frames.

    team_spacing == 0.0 is the tracker sentinel meaning "fewer than 3 players
    visible — convex hull undefined".  It is NOT a real tight-spacing signal.
    This function replaces the sentinel with NaN, then forward-fills within each
    (game_id, team) group up to a 90-frame cap (~3 s at 30 fps).  Gaps longer
    than 90 frames are left as NaN to signal genuine data loss.

    Adds two new columns (additive — does not modify team_spacing in-place):
      team_spacing_imputed  — float; imputed value or NaN when no prior exists / gap > 90 frames
      is_spacing_imputed    — bool; True when forward-fill was applied (original was sentinel/NaN)

    Args:
        df: Tracking DataFrame.  Must contain ``team_spacing``.  If
            ``game_id`` and ``team`` are present they are used as group keys;
            otherwise falls back to whole-column ffill.

    Returns:
        Copy of df with the two new columns appended.
    """
    df = df.copy()

    if "team_spacing" not in df.columns:
        df["team_spacing_imputed"] = np.nan
        df["is_spacing_imputed"]   = False
        return df

    orig = pd.to_numeric(df["team_spacing"], errors="coerce").replace(0.0, np.nan)

    # Mark frames that need imputation: original value was sentinel (0.0) or NaN
    df["is_spacing_imputed"] = orig.isna()

    if "game_id" in df.columns and "team" in df.columns:
        df["_orig_spacing_tmp"] = orig
        df["team_spacing_imputed"] = (
            df.groupby(["game_id", "team"], group_keys=False)["_orig_spacing_tmp"]
              .transform(lambda s: s.ffill(limit=90))
        )
        df = df.drop(columns=["_orig_spacing_tmp"])
    else:
        df["team_spacing_imputed"] = orig.ffill(limit=90)

    return df


def run(input_path: str = None, output_path: str = None, skip_advanced: bool = False) -> pd.DataFrame:
    """
    Full feature engineering pipeline.

    Reads tracking_data.csv, adds all feature groups, writes features.csv.
    Returns the feature DataFrame.

    Args:
        skip_advanced: If True, skip expensive advanced features (A-1 to A-14) for memory efficiency
    """
    import gc

    df = load_tracking(input_path)
    print(f"Loaded {len(df)} rows, {df['frame'].nunique()} frames, "
          f"{df['player_id'].nunique()} players")

    df = compute_spatial_features(df)
    df = fill_spatial_gaps(df)        # Fix 1 & 2: nearest_opponent / handler_isolation fallback
    df = add_ft_coordinates(df)       # FIX 3: ft_x / ft_y / dist_to_basket_ft

    # A-1 to A-14: advanced features (pre-season accuracy plan)
    # Skip on large games (>100K rows) to prevent memory bloat
    if _HAS_ADVANCED and not skip_advanced:
        if len(df) < 100000:
            try:
                df = add_acceleration_features(df)
                gc.collect()
                df = add_fatigue_features(df)
                gc.collect()
                df = add_defender_features(df)
                gc.collect()
                df = add_off_ball_features(df)
                gc.collect()
                df = add_paint_pressure_features(df)
                gc.collect()
                df = add_slump_features(df)
                gc.collect()
                df = add_ewma_features(df)
                gc.collect()
                df = add_interaction_features(df)
                gc.collect()
            except Exception as e:
                print(f"  [skip] advanced features error: {str(e)[:80]}")
        else:
            print(f"  [skip] advanced features (large game: {len(df):,} rows)")

    df = add_rolling_features(df)
    gc.collect()
    df = add_event_features(df)
    gc.collect()
    df = add_momentum_features(df)
    gc.collect()
    df = add_basket_features(df)
    gc.collect()
    df = add_game_flow_features(df)   # A-6: xFG model call inside
    gc.collect()
    df = add_per100_features(df)
    gc.collect()
    df = add_context_features(df)
    gc.collect()
    df = add_pose_features(df)
    gc.collect()
    df = add_external_player_features(df)  # A-7/8/9/10 wired inside
    gc.collect()

    # FIX 7: add team_abbrev from team_colors.json when available.
    # The JSON lives alongside tracking_data.csv in data/tracking/{game_id}/.
    if "team_abbrev" not in df.columns or df["team_abbrev"].fillna("").eq("").all():
        _tc_json = None
        if input_path:
            _tc_json = os.path.join(os.path.dirname(input_path), "team_colors.json")
        else:
            # Default path: data/tracking/ siblings
            _tc_json = os.path.join(_DATA_DIR, "tracking", "team_colors.json")
        if _tc_json and os.path.exists(_tc_json):
            try:
                import json as _json
                with open(_tc_json) as _f:
                    _color_map = _json.load(_f)
                if "team" in df.columns:
                    df["team_abbrev"] = df["team"].map(_color_map).fillna("")
                    print(f"  team_abbrev applied from {_tc_json}")
            except Exception as _e:
                print(f"  [team_abbrev] JSON load failed: {_e}")

    # Backfill player_name from jersey_name_map.json when column is blank.
    # jersey_name_map.json lives in the same directory as tracking_data.csv.
    if "player_name" in df.columns and "jersey_number" in df.columns:
        blank_name = df["player_name"].fillna("") == ""
        if blank_name.any():
            _jnm_path = None
            if input_path:
                _jnm_path = os.path.join(os.path.dirname(input_path), "jersey_name_map.json")
            if _jnm_path and os.path.exists(_jnm_path):
                try:
                    import json as _json2
                    with open(_jnm_path) as _jf:
                        _jmap = _json2.load(_jf)
                    # jersey_name_map: {"jersey_str": "Player Name"}
                    def _lookup_name(row):
                        _pn = str(row.get("player_name", "") or "").strip()
                        if _pn and _pn.lower() not in ("nan", "none", ""):
                            return row["player_name"]
                        _jraw = row.get("jersey_number", "")
                        try:
                            # Float jersey numbers (e.g. 8.0) → "8" to match JSON keys
                            jersey = str(int(float(_jraw)))
                        except (ValueError, TypeError):
                            jersey = str(_jraw).strip()
                        if jersey and jersey not in ("nan", "None", ""):
                            return _jmap.get(jersey, "")
                        return ""
                    df["player_name"] = df.apply(_lookup_name, axis=1)
                    filled = (df["player_name"].fillna("") != "").sum() - (~blank_name).sum()
                    print(f"  player_name: filled {max(0, filled)} rows from jersey_name_map.json")
                except Exception as _jne:
                    print(f"  [player_name] jersey_name_map.json lookup failed: {_jne}")

    df = df.sort_values(["frame", "player_id"]).reset_index(drop=True)

    if output_path is None:
        output_path = os.path.join(_DATA_DIR, "features.csv")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Features -> {output_path}  ({len(df)} rows, {len(df.columns)} cols)")
    return df


if __name__ == "__main__":
    run()
