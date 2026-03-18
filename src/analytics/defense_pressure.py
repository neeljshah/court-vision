"""
defense_pressure.py — Per-frame defensive pressure scoring.

Measures how much defensive pressure the ball-handler and overall offense
is under at each moment.

Factors:
  - Handler isolation (nearest defender distance) — primary signal
  - Paint occupancy by defense                   — help defense presence
  - Team spacing of offense                       — available relief valves
  - Number of offensive players covered           — overall defensive coverage

Extra metrics (callable independently):
  - help_rotation_latency(drive_frames, help_frames)
      Frames elapsed between a drive event and a help defender arriving.
  - coverage_completeness(drives_df, help_spots=3)
      Fraction of drives where all `help_spots` help positions were filled.

Output: data/defense_pressure.csv
        (one row per frame: frame, attacking_team, defending_team, pressure)

Usage:
    python -m src.analytics.defense_pressure
    — or —
    from src.analytics.defense_pressure import run
    df = run()
"""

import os

import numpy as np
import pandas as pd

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")

# Scoring weights
_W_ISOLATION = 0.40   # closest defender to ball handler
_W_PAINT     = 0.25   # how many defenders are in the paint
_W_COVERAGE  = 0.20   # fraction of offensive players with a close defender
_W_SPACING   = 0.15   # lower offense spacing → harder to escape pressure

# Distance thresholds (2D map px)
_TIGHT_COVER_DIST = 80   # defender within this = player is "covered"
_MAX_ISO_DIST     = 200  # isolation above this → no pressure (score 0)

# Smoothing window (frames)
_SMOOTH_WINDOW = 20


def run(input_path: str = None, output_path: str = None) -> pd.DataFrame:
    """
    Compute per-frame defensive pressure.

    Returns DataFrame: frame, attacking_team, defending_team, pressure (0–1).
    """
    if input_path is None:
        input_path = os.path.join(_DATA_DIR, "features.csv")
    if output_path is None:
        output_path = os.path.join(_DATA_DIR, "defense_pressure.csv")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    df = pd.read_csv(input_path)
    for col in ("x_position", "y_position", "handler_isolation",
                "team_spacing", "paint_count_opp", "nearest_opponent"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    rows = []
    last_attacker: str | None = None   # carry forward across tracking gaps
    for frame, fgrp in df.groupby("frame"):
        non_ref = fgrp[fgrp["team"] != "referee"]
        teams   = [t for t in non_ref["team"].unique()]
        if len(teams) < 2:
            continue

        # Determine attacking team = team with ball possession
        attacker = None
        for _, row in non_ref.iterrows():
            if row.get("ball_possession", 0):
                attacker = row["team"]
                break
        if attacker is None:
            # Carry forward the last known attacker instead of picking teams[0]
            # (teams[0] order is arbitrary — always picking the same team when
            # ball detection misses creates systematic pressure attribution bias)
            attacker = last_attacker if last_attacker in teams else teams[0]
        else:
            last_attacker = attacker
        defender = next(t for t in teams if t != attacker)

        att_grp = non_ref[non_ref["team"] == attacker]
        def_grp = non_ref[non_ref["team"] == defender]

        # 1. Handler isolation score (0 = wide open, 1 = fully pressured)
        iso_raw = att_grp[att_grp["ball_possession"] == 1]["handler_isolation"]
        iso_val = float(iso_raw.iloc[0]) if len(iso_raw) > 0 else _MAX_ISO_DIST
        iso_score = float(np.clip(1.0 - iso_val / _MAX_ISO_DIST, 0, 1))

        # 2. Paint pressure — defenders in paint
        paint_def = float(fgrp[fgrp["team"] == attacker]["paint_count_opp"].max())
        paint_score = float(np.clip(paint_def / 3, 0, 1))  # 3+ defenders = max

        # 3. Coverage — fraction of attackers with a close defender
        att_pts = att_grp[["x_position", "y_position"]].values
        def_pts = def_grp[["x_position", "y_position"]].values
        if len(att_pts) > 0 and len(def_pts) > 0:
            covered = 0
            for ap in att_pts:
                dists = np.hypot(def_pts[:, 0] - ap[0], def_pts[:, 1] - ap[1])
                if dists.min() <= _TIGHT_COVER_DIST:
                    covered += 1
            cov_score = covered / len(att_pts)
        else:
            cov_score = 0.0

        # 4. Spacing score — low offensive spacing → harder to relieve pressure
        spc = att_grp["team_spacing"].max() if "team_spacing" in att_grp.columns else 0
        spc_score = float(np.clip(1.0 - spc / 80_000, 0, 1))

        pressure = (
            _W_ISOLATION * iso_score
            + _W_PAINT     * paint_score
            + _W_COVERAGE  * cov_score
            + _W_SPACING   * spc_score
        )

        rows.append({
            "frame":          frame,
            "attacking_team": attacker,
            "defending_team": defender,
            "pressure":       round(pressure, 4),
        })

    if not rows:
        print("No frame data found — run feature_engineering first.")
        return pd.DataFrame()

    out = pd.DataFrame(rows).sort_values("frame").reset_index(drop=True)

    # Smooth
    out["pressure"] = out["pressure"].rolling(_SMOOTH_WINDOW, min_periods=1).mean().round(4)

    out.to_csv(output_path, index=False)
    print(f"Defense pressure → {output_path}  ({len(out)} frames)")
    return out


def help_rotation_latency(
    drive_frames: list[int],
    help_arrival_frames: list[int],
) -> float:
    """
    Compute average frames elapsed from a drive start to help defender arrival.

    Args:
        drive_frames:        Frame numbers when each drive was detected.
        help_arrival_frames: Frame numbers when the help defender first arrived
                             in the help zone for the corresponding drive.
                             Must be the same length as drive_frames.
                             Use None or a negative value for drives where help
                             never arrived (those drives are excluded).

    Returns:
        Mean latency in frames across paired drives, or 0.0 if no valid pairs.
    """
    if not drive_frames or not help_arrival_frames:
        return 0.0

    latencies = []
    for d, h in zip(drive_frames, help_arrival_frames):
        if h is None or h < 0:
            continue
        diff = h - d
        if diff >= 0:
            latencies.append(diff)
    return float(np.mean(latencies)) if latencies else 0.0


def coverage_completeness(
    drives_df: "pd.DataFrame",
    help_spots: int = 3,
    help_col: str = "help_defenders_present",
) -> float:
    """
    Fraction of drives where all `help_spots` help positions were filled.

    Args:
        drives_df:   DataFrame with one row per drive; must contain a column
                     `help_col` (int) counting how many help defenders were
                     present during the drive.
        help_spots:  Number of help spots that constitute full coverage (default 3).
        help_col:    Column name for help defender count (default 'help_defenders_present').

    Returns:
        Fraction [0.0, 1.0].  0.0 if drives_df is empty or column is missing.
    """
    if drives_df is None or len(drives_df) == 0:
        return 0.0
    if help_col not in drives_df.columns:
        return 0.0
    total = len(drives_df)
    fully_covered = int((drives_df[help_col] >= help_spots).sum())
    return fully_covered / total


if __name__ == "__main__":
    run()
