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
                        ).round(1)
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
        "possession_duration_sec", "off_ball_distance", "shot_clock_est",
    ]
    _int_cols = [
        "scoreboard_score_diff", "scoreboard_period", "paint_touches",
    ]
    _str_cols = ["possession_type", "play_type"]

    for col in _float_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in _int_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    for col in _str_cols:
        if col in df.columns:
            df[col] = df[col].fillna("unknown").astype(str)

    # Forward-fill scoreboard values within each frame group — they are
    # written once per 30-frame OCR window, so non-OCR frames are empty.
    for col in _float_cols + _int_cols:
        if col in df.columns:
            df[col] = df[col].ffill().bfill()

    return df


def add_external_player_features(
    df: pd.DataFrame,
    season: str = "2024-25",
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
    on_off_lookup: dict = {}
    try:
        from src.data.nba_tracking_stats import get_on_off_splits
        on_off = get_on_off_splits(season)
        for r in on_off:
            name = r.get("player_name", "").lower()
            if name:
                on_off_lookup[name] = r
    except Exception:
        pass

    # ── Synergy Play Types ──────────────────────────────────────────────────
    synergy_lookup: dict = {}
    try:
        import os as _os
        import json as _json
        for pt in ("offensive_Isolation", "offensive_PRBallHandler", "offensive_Spotup"):
            key = f"synergy_offensive_{pt.split('_', 1)[1]}_*" if "_" in pt else pt
            cache_dir = _os.path.join(_DATA_DIR, "..", "data", "nba")
            # Try loading cached synergy files directly
            for s_key in [f"synergy_offensive_{pt.split('_')[1]}_{season.replace('-', '_')}"]:
                s_path = _os.path.join(cache_dir, f"{s_key}.json")
                if _os.path.exists(s_path):
                    with open(s_path) as _f:
                        for r in _json.load(_f):
                            pname = r.get("player_name", "").lower()
                            play  = r.get("play_type", "").lower()
                            synergy_lookup.setdefault(pname, {})[play] = r.get("ppp", 0.0)
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

    # ── Build per-player feature rows ────────────────────────────────────────
    def _ext_features(player_name: str) -> dict:
        key = (player_name or "").lower()
        bb  = bbref_lookup.get(key, {})
        hu  = hustle_lookup.get(key, {})
        oo  = on_off_lookup.get(key, {})
        syn = synergy_lookup.get(key, {})
        con = contract_lookup.get(key, {})
        sd  = shot_dash_lookup.get(key, {})

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
            "synergy_pnr_ppp":       float(syn.get("prbballhandler", 0.0) or 0.0),
            "synergy_spotup_ppp":    float(syn.get("spotup", 0.0) or 0.0),
            # Injury
            "injury_status_multiplier": float(injury_lookup.get(key, 1.0)),
            # Contract
            "contract_year_flag":    int(bool(con.get("contract_year", False))),
            "cap_hit_pct":           float(con.get("cap_hit_pct", 0.0) or 0.0),
            # Shot dashboard
            "contested_shot_pct":    float(sd.get("contested_pct", 0.0) or 0.0),
            "catch_and_shoot_pct":   float(sd.get("catch_and_shoot_pct", 0.0) or 0.0),
            "pull_up_pct":           float(sd.get("pull_up_pct", 0.0) or 0.0),
            "avg_defender_dist":     float(sd.get("avg_defender_dist_contested", 0.0) or 0.0),
        }

    # Vectorized: build feature df and merge
    feature_rows = [_ext_features(n) for n in df["player_name"]]
    feat_df = pd.DataFrame(feature_rows, index=df.index)

    # Attach columns
    for col in feat_df.columns:
        df[col] = feat_df[col]

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
    df = add_per100_features(df)
    df = add_context_features(df)
    df = add_external_player_features(df)
    df = df.sort_values(["frame", "player_id"]).reset_index(drop=True)

    if output_path is None:
        output_path = os.path.join(_DATA_DIR, "features.csv")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Features → {output_path}  ({len(df)} rows, {len(df.columns)} cols)")
    return df


if __name__ == "__main__":
    run()
