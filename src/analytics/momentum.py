"""
momentum.py — Per-frame momentum scoring for each team.

Momentum captures which team has the game's initiative at any moment.
Higher score = team is in a more dominant stretch of play.

Factors (all rolling over configurable windows):
  - Possession run length  — sustained control
  - Shot attempt rate      — offensive activity
  - Velocity advantage     — team moving faster than opponent
  - Spacing advantage      — offense more spread out than defense

Output: data/momentum.csv  (one row per frame, columns: frame, team, momentum)

Usage:
    python -m src.analytics.momentum
    — or —
    from src.analytics.momentum import run
    df = run()
"""

import os

import numpy as np
import pandas as pd

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")

# Scoring weights
_W_POSSESSION = 0.35
_W_SHOTS      = 0.25
_W_VELOCITY   = 0.20
_W_SPACING    = 0.20

# Smoothing window for final momentum signal (frames)
_SMOOTH_WINDOW = 30

# Normalisation ceilings
_MAX_RUN          = 200   # possession run above this → full score
_MAX_SHOT_RATE    = 5     # shots per _SHOT_WINDOW frames at which score = 1.0
_SHOT_WINDOW      = 90    # frames over which to count shots


def run(input_path: str = None, output_path: str = None) -> pd.DataFrame:
    """
    Compute per-frame momentum for each team.

    Returns DataFrame with columns: frame, team, momentum (0–1).
    """
    if input_path is None:
        input_path = os.path.join(_DATA_DIR, "features.csv")
    if output_path is None:
        output_path = os.path.join(_DATA_DIR, "momentum.csv")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    df = pd.read_csv(input_path)
    for col in ("velocity", "team_spacing", "possession_run"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Build per-frame per-team summary
    non_ref = df[df["team"] != "referee"] if "team" in df.columns else df
    frame_team = (
        non_ref
        .groupby(["frame", "team"])
        .agg(
            avg_vel=("velocity", "mean"),
            spacing=("team_spacing", "first"),
            possession_run=("possession_run", "first"),
        )
        .reset_index()
    )

    # has_ball: 1 for the team that currently holds the ball, 0 for the defender.
    # Without this, both teams share the same possession_run value every frame,
    # making the highest-weighted component (_W_POSSESSION=0.35) non-differentiating.
    if "ball_possession" in non_ref.columns:
        has_ball = (
            non_ref.groupby(["frame", "team"])["ball_possession"]
            .max()
            .reset_index(name="has_ball")
        )
        frame_team = frame_team.merge(has_ball, on=["frame", "team"], how="left")
        frame_team["has_ball"] = frame_team["has_ball"].fillna(0).astype(int)
    else:
        frame_team["has_ball"] = 0

    # Shot rate per team per frame
    if "event" in df.columns:
        shots_per_frame = (
            df[df["event"] == "shot"]
            .groupby(["frame", "team"])
            .size()
            .reset_index(name="shot_flag")
        )
        frame_team = frame_team.merge(shots_per_frame, on=["frame", "team"], how="left")
        frame_team["shot_flag"] = frame_team["shot_flag"].fillna(0).astype(int)
    else:
        frame_team["shot_flag"] = 0

    rows = []
    for team, grp in frame_team.groupby("team"):
        if team == "referee":
            continue
        grp = grp.sort_values("frame").copy()

        # Get opponent averages at each frame for relative scoring
        opp = frame_team[frame_team["team"] != team].groupby("frame").agg(
            opp_vel=("avg_vel", "mean"),
            opp_spacing=("spacing", "mean"),
        ).reset_index()
        grp = grp.merge(opp, on="frame", how="left")
        grp["opp_vel"]     = grp["opp_vel"].fillna(grp["avg_vel"])
        grp["opp_spacing"] = grp["opp_spacing"].fillna(grp["spacing"])

        # Component scores
        # Only the team holding the ball earns possession-run credit.
        grp["s_possession"] = np.clip(grp["possession_run"] / _MAX_RUN, 0, 1) * grp["has_ball"]

        shot_rolling = grp["shot_flag"].rolling(_SHOT_WINDOW, min_periods=1).sum()
        grp["s_shots"] = np.clip(shot_rolling / _MAX_SHOT_RATE, 0, 1)

        max_vel = max(grp[["avg_vel", "opp_vel"]].max().max(), 1.0)
        grp["s_velocity"] = np.clip(
            (grp["avg_vel"] - grp["opp_vel"]) / max_vel * 0.5 + 0.5, 0, 1
        )

        max_spc = max(grp[["spacing", "opp_spacing"]].max().max(), 1.0)
        grp["s_spacing"] = np.clip(
            (grp["spacing"] - grp["opp_spacing"]) / max_spc * 0.5 + 0.5, 0, 1
        )

        grp["momentum_raw"] = (
            _W_POSSESSION * grp["s_possession"]
            + _W_SHOTS     * grp["s_shots"]
            + _W_VELOCITY  * grp["s_velocity"]
            + _W_SPACING   * grp["s_spacing"]
        )

        # Smooth final signal
        grp["momentum"] = (
            grp["momentum_raw"]
            .rolling(_SMOOTH_WINDOW, min_periods=1)
            .mean()
            .round(4)
        )

        rows.append(grp[["frame", "team", "momentum"]])

    if not rows:
        print("No team data found — run feature_engineering first.")
        return pd.DataFrame()

    out = pd.concat(rows).sort_values(["frame", "team"]).reset_index(drop=True)
    out.to_csv(output_path, index=False)
    print(f"Momentum      → {output_path}  ({len(out)} rows)")
    return out


def scoring_run_length(scored_teams: list[str]) -> int:
    """
    Length of the current consecutive scoring run by one team.

    Args:
        scored_teams: Ordered list of team labels that scored on each possession
                      (e.g. ["A","A","B","A","A","A"]).  Non-scoring possessions
                      should be omitted or handled upstream.

    Returns:
        Length of the trailing consecutive run by the same team.
        0 if the list is empty.
    """
    if not scored_teams:
        return 0
    current = scored_teams[-1]
    run = 0
    for t in reversed(scored_teams):
        if t == current:
            run += 1
        else:
            break
    return run


def momentum_shift_flag(
    scores_a: list[int],
    scores_b: list[int],
    window: int = 10,
    swing_threshold: int = 5,
) -> int:
    """
    Return 1 when a 5+ point swing has occurred within the last `window` possessions.

    Compares cumulative score of team A vs team B across the last `window`
    entries; if |Δ(cumA - cumB)| >= swing_threshold the flag is set.

    Args:
        scores_a:        List of points scored by team A per possession (0 or 2/3).
        scores_b:        List of points scored by team B per possession (0 or 2/3).
        window:          Lookback possession count (default 10).
        swing_threshold: Point swing that triggers the flag (default 5).

    Returns:
        1 if swing occurred, 0 otherwise.
    """
    if not scores_a or not scores_b:
        return 0
    # Use the last `window` entries from both lists
    recent_a = scores_a[-window:]
    recent_b = scores_b[-window:]
    swing = abs(sum(recent_a) - sum(recent_b))
    return 1 if swing >= swing_threshold else 0


def pressure_trend(
    pressure_values: list[float],
    window: int = 30,
) -> float:
    """
    Rolling slope of defensive pressure values over the last `window` frames.

    A positive slope means pressure is rising; negative means easing.

    Args:
        pressure_values: Ordered list of defensive pressure scores (0–1).
        window:          Lookback window in frames (default 30).

    Returns:
        Slope (float) of the linear trend across the window.
        0.0 if fewer than 2 data points are available.
    """
    if not pressure_values or len(pressure_values) < 2:
        return 0.0
    recent = pressure_values[-window:]
    if len(recent) < 2:
        return 0.0
    n = len(recent)
    x = np.arange(n, dtype=float)
    y = np.array(recent, dtype=float)
    # Slope via least-squares formula: (n*Σxy - Σx*Σy) / (n*Σx² - (Σx)²)
    sx = x.sum()
    sy = y.sum()
    sxy = (x * y).sum()
    sx2 = (x ** 2).sum()
    denom = n * sx2 - sx ** 2
    if denom == 0:
        return 0.0
    return float((n * sxy - sx * sy) / denom)


if __name__ == "__main__":
    run()
