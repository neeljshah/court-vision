"""
inject_nba_shots.py — Rebuild shot_log.csv from NBA PBP ground truth + CV spatial data.

Use when ball detection was too sparse for CV shot detection (< 30% valid).
Maps each PBP shot event to the nearest tracking frame and attaches spatial
features (defender_distance, team_spacing, court zone, etc.) from tracking_data.csv.

Usage:
    python scripts/inject_nba_shots.py --game-id 0022500002
    python scripts/inject_nba_shots.py --game-id 0022500002 --data-dir data/tracking/0022500002
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

DATA_DIR    = PROJECT_DIR / "data"
GAMES_DIR   = DATA_DIR / "games"
TRACKING_DIR = DATA_DIR / "tracking"

# Basketball court dimensions (ft)
COURT_LEN_FT = 94.0
COURT_WID_FT = 50.0
# Basket positions in ft (from left baseline, centred on width)
BASKET_LEFT  = (5.25,  25.0)
BASKET_RIGHT = (88.75, 25.0)


def _period_offset(period: int) -> int:
    """Absolute game seconds at the start of a period (NBA: 12min quarters)."""
    return (period - 1) * 720


def _load_pbp_shots(game_id: str) -> list[dict]:
    """Load all shot events from cached PBP JSON files."""
    shots = []
    for q in range(1, 5):
        p = DATA_DIR / "nba" / f"pbp_{game_id}_p{q}.json"
        if not p.exists():
            continue
        with open(p, encoding="utf-8") as f:
            events = json.load(f)
        off = _period_offset(q)
        for e in events:
            if e.get("event_type") in (1, 2):
                s = dict(e)
                s["abs_game_time"] = off + int(e.get("game_clock_sec", 0) or 0)
                s["made"] = 1 if e.get("event_type") == 1 else 0
                shots.append(s)
    return sorted(shots, key=lambda x: x["abs_game_time"])


def _calibrate_offset(data_dir: str) -> float:
    """Compute clip_start_sec: abs_game_time = tracking_ts + offset.

    Uses the tracking start timestamp and assumes it aligns with Q2 start (720s).
    Falls back to 0 if tracking_data.csv is not found.
    """
    td_path = Path(data_dir) / "tracking_data.csv"
    if not td_path.exists():
        return 0.0
    sample = pd.read_csv(td_path, usecols=["timestamp"], nrows=5, encoding="utf-8")
    ts_min = sample["timestamp"].min()
    # Primary anchor: Q2 start = 720s abs, tracking starts near Q2 begin
    offset = 720.0 - ts_min
    return round(offset, 2)


def _court_zone(ft_x: float, ft_y: float) -> str:
    """Assign court zone from ft coordinates."""
    if ft_x < 0 or ft_x > COURT_LEN_FT:
        return "backcourt"
    # Determine offensive half
    half = "left" if ft_x < COURT_LEN_FT / 2 else "right"
    basket_x = BASKET_LEFT[0] if half == "left" else BASKET_RIGHT[0]
    dist = abs(ft_x - basket_x)
    if dist < 8.0:
        return "paint"
    if dist < 16.0:
        return "mid_range"
    if dist < 23.75:
        return "mid_range"
    return "3pt_arc"


def _shot_distance_ft(ft_x: float, ft_y: float) -> float:
    """Distance to nearest basket in feet."""
    d_left  = np.hypot(ft_x - BASKET_LEFT[0],  ft_y - BASKET_LEFT[1])
    d_right = np.hypot(ft_x - BASKET_RIGHT[0], ft_y - BASKET_RIGHT[1])
    return round(min(d_left, d_right), 1)


def inject_shots(game_id: str, data_dir: str) -> Path:
    """
    Main injection function.

    Returns path to written shot_log.csv.
    """
    data_path = Path(data_dir)
    td_path   = data_path / "tracking_data.csv"
    ft_path   = data_path / "features.csv"

    if not td_path.exists():
        raise FileNotFoundError(f"tracking_data.csv not found in {data_dir}")

    # --- Load PBP shots ---
    pbp_shots = _load_pbp_shots(game_id)
    if not pbp_shots:
        raise RuntimeError(f"No PBP shots found for game {game_id}. "
                           f"Check data/nba/pbp_{game_id}_p*.json exists.")
    print(f"PBP shots loaded: {len(pbp_shots)}")

    # --- Calibrate time offset ---
    offset = _calibrate_offset(data_dir)
    print(f"Clip offset: abs_game_time = tracking_ts + {offset:.1f}s")

    # --- Load tracking data (minimal columns for speed) ---
    print("Loading tracking_data.csv …")
    td_cols = ["frame", "timestamp", "player_id", "player_name", "team", "team_abbrev",
               "x_position", "y_position", "x_norm", "y_norm", "ft_x", "ft_y",
               "ball_possession", "distance_to_ball", "nearest_opponent",
               "handler_isolation", "team_spacing", "possession_id", "court_zone",
               "dribble_count", "fast_break_flag"]
    td_cols_present = pd.read_csv(td_path, nrows=0, encoding="utf-8").columns.tolist()
    load_cols = [c for c in td_cols if c in td_cols_present]
    td = pd.read_csv(td_path, usecols=load_cols, encoding="utf-8", low_memory=False)
    # One row per frame (unique timestamps per frame across players)
    td_ts = td.drop_duplicates("timestamp")[["timestamp", "frame"]].set_index("timestamp")
    ts_values = np.array(sorted(td["timestamp"].unique()))

    print(f"Tracking rows: {len(td):,}, unique timestamps: {len(ts_values):,}")
    ts_min, ts_max = ts_values[0], ts_values[-1]

    # --- Match PBP shots to tracking frames ---
    rows = []
    matched = 0
    skipped_range = 0

    for shot in pbp_shots:
        abs_t  = shot["abs_game_time"]
        target_ts = abs_t - offset

        if target_ts < ts_min - 5.0 or target_ts > ts_max + 5.0:
            skipped_range += 1
            continue

        # Find nearest timestamp
        idx      = np.searchsorted(ts_values, target_ts)
        idx      = min(idx, len(ts_values) - 1)
        if idx > 0 and abs(ts_values[idx - 1] - target_ts) < abs(ts_values[idx] - target_ts):
            idx -= 1
        nearest_ts = ts_values[idx]
        ts_err = abs(nearest_ts - target_ts)

        # Get all players at this timestamp
        frame_rows = td[td["timestamp"] == nearest_ts]
        if frame_rows.empty:
            skipped_range += 1
            continue

        # Find shooter: player with ball_possession=True, else min distance_to_ball
        shooter = None
        if "ball_possession" in frame_rows.columns:
            with_ball = frame_rows[frame_rows["ball_possession"].astype(str).isin(["True", "1", "1.0"])]
            if not with_ball.empty:
                shooter = with_ball.iloc[0]
        if shooter is None and "distance_to_ball" in frame_rows.columns:
            valid_d = frame_rows["distance_to_ball"].dropna()
            if not valid_d.empty:
                shooter = frame_rows.loc[valid_d.idxmin()]
        if shooter is None:
            shooter = frame_rows.iloc[0]

        # Spatial features
        ft_x  = float(shooter.get("ft_x", 0) or 0)
        ft_y  = float(shooter.get("ft_y", 0) or 0)
        zone  = str(shooter.get("court_zone", "")) or _court_zone(ft_x, ft_y)
        dist  = _shot_distance_ft(ft_x, ft_y)
        def_d = shooter.get("nearest_opponent", None)
        if def_d is not None and float(def_d) >= 199.5:
            def_d = None

        row = {
            "game_id":          game_id,
            "shot_id":          len(rows) + 1,
            "frame":            int(shooter.get("frame", 0) or 0),
            "timestamp":        round(nearest_ts, 3),
            "timestamp_error_s": round(ts_err, 2),
            "player_id":        shooter.get("player_id", ""),
            "player_name":      shot.get("player_name", "") or shooter.get("player_name", ""),
            "team":             shooter.get("team", ""),
            "team_abbrev":      shot.get("team_abbrev", "") or shooter.get("team_abbrev", ""),
            "x_position":       shooter.get("x_position", ""),
            "y_position":       shooter.get("y_position", ""),
            "x_norm":           shooter.get("x_norm", ""),
            "y_norm":           shooter.get("y_norm", ""),
            "ft_x":             ft_x,
            "ft_y":             ft_y,
            "court_zone":       zone,
            "shot_distance":    dist,
            "defender_distance": def_d,
            "team_spacing":     shooter.get("team_spacing", ""),
            "possession_id":    shooter.get("possession_id", ""),
            "possession_duration": shooter.get("possession_duration_sec" if "possession_duration_sec" in frame_rows.columns else "possession_duration", ""),
            "made":             shot["made"],
            "period":           shot.get("period", ""),
            "abs_game_time":    abs_t,
            "event_desc":       shot.get("event_desc", ""),
            "fast_break":       shooter.get("fast_break_flag", 0),
            "dribble_count":    shooter.get("dribble_count", ""),
            "source":           "nba_pbp_injected",
        }
        rows.append(row)
        matched += 1

    print(f"Matched: {matched}, Skipped (out of range): {skipped_range}")

    if not rows:
        raise RuntimeError("No shots could be matched to tracking data.")

    df = pd.DataFrame(rows)

    # Back up existing shot_log and write new one
    sl_path = data_path / "shot_log.csv"
    bak_path = data_path / "shot_log.csv.bak"
    if sl_path.exists() and not bak_path.exists():
        import shutil
        shutil.copy2(sl_path, bak_path)
        print(f"Backed up original to {bak_path.name}")

    df.to_csv(sl_path, index=False, encoding="utf-8")
    print(f"Written: {sl_path}  ({len(df)} shots)")

    # Quick sanity stats
    made_pct  = df["made"].mean() * 100
    def_valid = df["defender_distance"].notna().mean() * 100
    zones     = df["court_zone"].value_counts().to_dict()
    print(f"  FG%: {made_pct:.1f}%  defender_dist valid: {def_valid:.0f}%")
    print(f"  Zones: {zones}")

    return sl_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Inject NBA PBP shots into shot_log.csv")
    ap.add_argument("--game-id", required=True, help="NBA game ID (e.g. 0022500002)")
    ap.add_argument("--data-dir", default=None,
                    help="Game data directory (default: data/tracking/<game_id>)")
    args = ap.parse_args()

    data_dir = args.data_dir
    if data_dir is None:
        for parent in (TRACKING_DIR, GAMES_DIR):
            candidate = parent / args.game_id
            if (candidate / "tracking_data.csv").exists():
                data_dir = str(candidate)
                break
    if data_dir is None:
        print(f"ERROR: tracking_data.csv not found for {args.game_id}")
        sys.exit(1)

    print(f"Game: {args.game_id}  Dir: {data_dir}")
    inject_shots(args.game_id, data_dir)


if __name__ == "__main__":
    main()
