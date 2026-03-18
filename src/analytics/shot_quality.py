"""
shot_quality.py — Per-shot quality scoring from tracking features.

Reads data/features.csv, extracts shot events, and scores each shot 0–1
based on court zone, defender proximity, team spacing, and possession depth.

Output: data/shot_quality.csv  (one row per shot)
        data/shot_heatmap.json (per-zone count + avg quality)

Usage:
    python -m src.analytics.shot_quality
    — or —
    from src.analytics.shot_quality import run
    df = run()
"""

import json
import os

import numpy as np
import pandas as pd

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")

# Scoring weights (sum to 1.0)
_W_ZONE       = 0.35
_W_DEFENDER   = 0.30
_W_SPACING    = 0.20
_W_POSSESSION = 0.15

# Zone quality priors — normalised NBA eFG% by zone
_ZONE_QUALITY = {
    "paint":      0.85,
    "corner_3":   0.80,
    "3pt_arc":    0.55,
    "mid_range":  0.35,
    "backcourt":  0.05,
}

_OPEN_DIST      = 150    # 2D map px — fully open
_CONTESTED_DIST = 40     # 2D map px — fully contested
_MAX_SPACING    = 80_000 # convex hull area (px²) at which spacing score = 1.0


def score_shot(
    zone: str,
    handler_isolation: float,
    team_spacing: float,
    possession_run: int,
    max_possession_run: int = 150,
) -> float:
    """
    Compute shot quality in [0, 1]. Higher = better look.

    Args:
        zone:               Court zone from _ZONE_QUALITY keys.
        handler_isolation:  Distance to nearest defender (2D map px).
        team_spacing:       Convex hull area of offensive team (px²).
        possession_run:     Consecutive frames team has held the ball.
        max_possession_run: Normalisation ceiling for possession depth.
    """
    z_score = _ZONE_QUALITY.get(zone, 0.3)

    iso     = max(0.0, float(handler_isolation or 0))
    d_score = float(np.clip(
        (iso - _CONTESTED_DIST) / max(1, _OPEN_DIST - _CONTESTED_DIST),
        0.0, 1.0,
    ))

    sp      = max(0.0, float(team_spacing or 0))
    s_score = float(np.clip(sp / _MAX_SPACING, 0.0, 1.0))

    # Deep into possession → defense is set → penalise slightly
    p_raw   = float(np.clip(possession_run / max(1, max_possession_run), 0.0, 1.0))
    p_score = 1.0 - p_raw

    return round(
        _W_ZONE * z_score
        + _W_DEFENDER * d_score
        + _W_SPACING * s_score
        + _W_POSSESSION * p_score,
        4,
    )


def run(input_path: str = None, output_dir: str = None) -> pd.DataFrame:
    """
    Score all shots in features.csv. Writes shot_quality.csv and
    shot_heatmap.json. Returns the scored DataFrame.
    """
    if input_path is None:
        input_path = os.path.join(_DATA_DIR, "features.csv")
    if output_dir is None:
        output_dir = _DATA_DIR
    os.makedirs(output_dir, exist_ok=True)

    df = pd.read_csv(input_path)
    for col in ("handler_isolation", "team_spacing", "possession_run"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Referee rows (team == 'referee') are excluded before scoring to prevent
    # misclassified referee events from inflating shot counts or skewing
    # defender-distance scores.
    if "event" in df.columns:
        event_mask = df["event"] == "shot"
        ref_mask = df["team"] != "referee" if "team" in df.columns else pd.Series(True, index=df.index)
        shots = df[event_mask & ref_mask].copy()
    else:
        shots = pd.DataFrame()
    if shots.empty:
        print("No shot events found — run the tracker first.")
        return shots

    max_run = int(df["possession_run"].max()) if "possession_run" in df.columns else 150

    shots["shot_quality"] = shots.apply(
        lambda r: score_shot(
            zone=str(r.get("court_zone", "backcourt")),
            handler_isolation=r.get("handler_isolation", 0),
            team_spacing=r.get("team_spacing", 0),
            possession_run=int(r.get("possession_run", 0)),
            max_possession_run=max_run,
        ),
        axis=1,
    )

    keep = [
        "frame", "timestamp", "player_id", "team",
        "x_position", "y_position", "court_zone",
        "handler_isolation", "team_spacing", "possession_run",
        "shot_quality",
    ]
    out = shots[[c for c in keep if c in shots.columns]].reset_index(drop=True)

    csv_path = os.path.join(output_dir, "shot_quality.csv")
    out.to_csv(csv_path, index=False)
    print(f"Shot quality  → {csv_path}  ({len(out)} shots)")

    _write_heatmap(out, output_dir)
    return out


def shot_clock_pressure_score(
    possession_run: int,
    max_possession_run: int = 150,
) -> float:
    """
    Quality decay metric as possession_run grows (shot-clock pressure proxy).

    Returns a score in [0, 1]:
      - 1.0 at possession_run == 0  (fresh possession, plenty of clock)
      - 0.0 at possession_run >= max_possession_run  (possession near expiry)

    Args:
        possession_run:     Consecutive frames team has held the ball.
        max_possession_run: Frame count corresponding to shot-clock expiry (default 150).
    """
    run_clamped = max(0, min(int(possession_run or 0), max_possession_run))
    return round(1.0 - run_clamped / max(1, max_possession_run), 4)


def fatigue_penalty(
    velocity_mean_90: float,
    velocity_mean_150: float,
    base_score: float,
) -> float:
    """
    Reduce shot quality score when recent velocity is well below the longer window.

    A player whose average speed over the last 90 frames is below 80 % of their
    150-frame average is considered fatigued; their shot quality is penalised.

    Args:
        velocity_mean_90:  Mean velocity over last 90 frames (court px/frame).
        velocity_mean_150: Mean velocity over last 150 frames (court px/frame).
        base_score:        Shot quality score before fatigue adjustment.

    Returns:
        Adjusted score in [0, 1].
    """
    threshold = 0.8
    if velocity_mean_150 <= 0:
        return round(float(np.clip(base_score, 0.0, 1.0)), 4)
    ratio = velocity_mean_90 / velocity_mean_150
    if ratio < threshold:
        # Linear penalty: at ratio=0 → full 20% reduction; at ratio=0.8 → no reduction
        penalty_fraction = (threshold - ratio) / threshold   # 0..1
        adjusted = base_score * (1.0 - 0.20 * penalty_fraction)
        return round(float(np.clip(adjusted, 0.0, 1.0)), 4)
    return round(float(np.clip(base_score, 0.0, 1.0)), 4)


def _write_heatmap(shots: pd.DataFrame, output_dir: str) -> None:
    """Write shot_heatmap.json — per-zone frequency and avg quality."""
    if "court_zone" not in shots.columns:
        return
    heatmap = {}
    for zone, grp in shots.groupby("court_zone"):
        heatmap[zone] = {
            "count":       int(len(grp)),
            "avg_quality": round(float(grp["shot_quality"].mean()), 4),
            "per_team": {
                team: {
                    "count":       int(len(tg)),
                    "avg_quality": round(float(tg["shot_quality"].mean()), 4),
                }
                for team, tg in grp.groupby("team")
                if team != "referee"
            } if "team" in grp.columns else {},
        }
    path = os.path.join(output_dir, "shot_heatmap.json")
    with open(path, "w") as f:
        json.dump(heatmap, f, indent=2)
    print(f"Shot heatmap  → {path}")


if __name__ == "__main__":
    run()
