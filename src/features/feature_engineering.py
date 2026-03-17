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
    df = pd.read_csv(path)
    for col in ("frame", "player_id"):
        if col in df.columns:
            df[col] = df[col].astype(int)
    for col in ("x_position", "y_position", "velocity", "acceleration",
                "distance_to_ball", "nearest_opponent", "nearest_teammate",
                "team_spacing", "team_centroid_x", "team_centroid_y",
                "handler_isolation", "ball_x2d", "ball_y2d",
                "distance_to_basket", "vel_toward_basket", "ball_velocity",
                "possession_duration"):
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
        DataFrame identical to input except referee rows have NaN values in all
        spatial metric columns. The referee rows themselves are retained.
    """
    _SPATIAL = [
        "team_spacing",
        "nearest_opponent",
        "nearest_teammate",
        "paint_count_own",
        "paint_count_opp",
    ]

    if "team" not in df.columns:
        return df

    df = df.copy()
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

    df = df.sort_values(["player_id", "frame"]).copy()
    grp = df.groupby("player_id", group_keys=False)

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


def add_momentum_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Team-level momentum proxy features per frame.

    New columns:
      team_velocity_mean   — average velocity of all teammates this frame
      opp_velocity_mean    — average velocity of opponents this frame
      spacing_advantage    — own team_spacing minus opponent team_spacing
    """
    frame_team = df.groupby(["frame", "team"]).agg(
        team_vel_mean=("velocity", "mean"),
        team_spacing_val=("team_spacing", "first"),
    ).reset_index()

    rows = []
    for frame, grp in frame_team.groupby("frame"):
        teams = grp[grp["team"] != "referee"]
        for _, row in teams.iterrows():
            opp = teams[teams["team"] != row["team"]]
            opp_vel  = opp["team_vel_mean"].mean() if len(opp) else np.nan
            opp_spc  = opp["team_spacing_val"].mean() if len(opp) else np.nan
            rows.append({
                "frame":             frame,
                "team":              row["team"],
                "team_velocity_mean": round(row["team_vel_mean"], 2),
                "opp_velocity_mean":  round(opp_vel, 2) if not np.isnan(opp_vel) else np.nan,
                "spacing_advantage":  round(
                    row["team_spacing_val"] - opp_spc, 1
                ) if not np.isnan(opp_spc) else np.nan,
            })

    momentum_df = pd.DataFrame(rows)
    df = df.merge(momentum_df, on=["frame", "team"], how="left")
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

    df = df.sort_values(["player_id", "frame"]).copy()
    grp = df.groupby("player_id", group_keys=False)

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

    # ── Shot quality proxy ─────────────────────────────────────────────────
    _zone_weight = {
        "paint":     1.00,
        "corner_3":  0.85,
        "3pt_arc":   0.75,
        "mid_range": 0.55,
        "backcourt": 0.05,
    }
    if "court_zone" in df.columns and "nearest_opponent" in df.columns:
        shot_mask = df.get("event", pd.Series("none", index=df.index)) == "shot"
        zone_w    = df["court_zone"].map(_zone_weight).fillna(0.5)
        opp_d     = pd.to_numeric(df["nearest_opponent"], errors="coerce").fillna(50.0)
        spacing   = pd.to_numeric(df.get("team_spacing", 0), errors="coerce").fillna(0.0)
        spacing_n = (spacing / (spacing.max() + 1e-6)).clip(0.0, 1.0)
        sq_proxy  = (zone_w * (1.0 / (1.0 + opp_d / 50.0)) * (0.5 + 0.5 * spacing_n)).round(3)
        df["shot_quality_proxy"] = np.where(shot_mask, sq_proxy, 0.0)
    else:
        df["shot_quality_proxy"] = 0.0

    # ── Pick-roll proxy ────────────────────────────────────────────────────
    pr_list = []
    for frame_id, fgrp in df.groupby("frame"):
        handler = fgrp[fgrp["ball_possession"] == 1]
        if len(handler) == 0:
            pr_list.append({"frame": frame_id, "pick_roll_proxy": 0})
            continue
        hx     = handler.iloc[0]["x_position"]
        hy     = handler.iloc[0]["y_position"]
        h_team = handler.iloc[0]["team"]
        mates  = fgrp[(fgrp["team"] == h_team) & (fgrp["ball_possession"] == 0)]
        near   = int((np.hypot(mates["x_position"] - hx, mates["y_position"] - hy) < 80).sum())
        pr_list.append({"frame": frame_id, "pick_roll_proxy": int(near >= 2)})
    pr_df = pd.DataFrame(pr_list)

    # ── Merge all frame-level features back ───────────────────────────────
    keep = ["frame", "turnover_flag", "pace_30"]
    df = df.merge(frame_poss[keep], on="frame", how="left")
    df["turnover_flag"] = df["turnover_flag"].fillna(0).astype(int)
    df["pace_30"]       = df["pace_30"].fillna(0.0)
    df = df.merge(pr_df, on="frame", how="left")
    df["pick_roll_proxy"] = df["pick_roll_proxy"].fillna(0).astype(int)
    return df


def run(input_path: str = None, output_path: str = None) -> pd.DataFrame:
    """
    Full feature engineering pipeline.

    Reads tracking_data.csv, adds all feature groups, writes features.csv.
    Returns the feature DataFrame.
    """
    df = load_tracking(input_path)
    print(f"Loaded {len(df)} rows, {df['frame'].nunique()} frames, "
          f"{df['player_id'].nunique()} players")

    df = compute_spatial_features(df)
    df = add_rolling_features(df)
    df = add_event_features(df)
    df = add_momentum_features(df)
    df = add_basket_features(df)
    df = add_game_flow_features(df)
    df = df.sort_values(["frame", "player_id"]).reset_index(drop=True)

    if output_path is None:
        output_path = os.path.join(_DATA_DIR, "features.csv")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Features → {output_path}  ({len(df)} rows, {len(df.columns)} cols)")
    return df


if __name__ == "__main__":
    run()
