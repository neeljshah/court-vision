"""Build per-(lineup x game) CV features from per-frame tracking data.

Reads tracking_data.csv (per-frame, per-player CV signals) and the
homography-corrected tracking_data_corrected.csv for each game in
C:/Users/neelj/nba-data-backup/tracking/<game_id>/, aggregates per-frame
CV signals (spacing, velocity, defender distance proxy, paint pressure, etc.)
into per (game_id, team_abbrev, lineup) rows where lineup is the sorted set
of player_names visible together on the same team across frames.

Output: data/lineup_cv_features.parquet

Notes:
- The single features.csv that exists locally (only 1 game has it) is NOT
  the actual source — features at scale live in tracking_data.csv. The
  cvb_* style signals come from these raw columns:
    velocity, team_spacing, distance_to_ball, off_ball_distance,
    dist_to_basket_ft, paint_count_own, paint_count_opp,
    handler_isolation, vel_toward_basket, drive_flag
- dist_to_basket_ft_fixed from tracking_data_corrected.csv is preferred
  (homography drift fix per Open Issues #13) — joined on (frame, player_id).
- Lineup identity uses sorted player_name set per team per frame. tracker
  player_id (column 3) is per-game ephemeral so player_name is more stable.
- Skips lineups with n_frames < 100 (~3.3s of game time at 30fps).
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

import numpy as np
import pandas as pd


TRACKING_ROOT = Path(r"C:/Users/neelj/nba-data-backup/tracking")
OUTPUT_PATH = Path(r"C:/Users/neelj/nba-ai-system/data/lineup_cv_features.parquet")
MIN_FRAMES = 100

# Per-frame per-player numeric signals we will mean/max-aggregate per lineup
NUMERIC_SIGNALS = [
    "velocity",
    "acceleration",
    "team_spacing",
    "spacing_hull_area",
    "distance_to_ball",
    "off_ball_distance",
    "dist_to_basket_ft",
    "paint_count_own",
    "paint_count_opp",
    "handler_isolation",
    "vel_toward_basket",
    "drive_flag",
    "fast_break_flag",
    "paint_touches",
]


def _safe_read_tracking(game_dir: Path) -> pd.DataFrame | None:
    """Load tracking_data.csv (optionally joined with corrected) or return None."""
    tdata = game_dir / "tracking_data.csv"
    if not tdata.exists():
        return None
    try:
        df = pd.read_csv(tdata, low_memory=False)
    except Exception as exc:
        print(f"  read_csv tracking_data.csv failed: {exc}", file=sys.stderr)
        return None

    needed = {"frame", "player_id", "player_name", "team_abbrev"}
    if not needed.issubset(df.columns):
        missing = needed - set(df.columns)
        print(f"  missing required cols {missing}; skipping", file=sys.stderr)
        return None

    # Drop frames with missing player_name or team_abbrev (can't form lineup)
    df = df.dropna(subset=["player_name", "team_abbrev", "frame"]).copy()
    if df.empty:
        return None

    # Try to merge homography-corrected file for dist_to_basket_ft_fixed
    corrected = game_dir / "tracking_data_corrected.csv"
    if corrected.exists():
        try:
            cdf = pd.read_csv(corrected, low_memory=False)
            keep = ["frame", "player_id"]
            for c in ("dist_to_basket_ft_fixed", "paint_pressure_90_fixed",
                      "paint_pressure_own_90_fixed", "paint_pressure_opp_90_fixed",
                      "in_paint_fixed", "near_basket_fixed"):
                if c in cdf.columns:
                    keep.append(c)
            cdf = cdf[keep].drop_duplicates(subset=["frame", "player_id"])
            df = df.merge(cdf, on=["frame", "player_id"], how="left")
        except Exception as exc:
            print(f"  corrected merge failed (non-fatal): {exc}", file=sys.stderr)

    # Prefer fixed dist if available; null sentinel 200.0 stripped
    if "dist_to_basket_ft_fixed" in df.columns:
        # 200.0 is a known sentinel (Open Issues #22) — treat as NaN
        df.loc[df["dist_to_basket_ft_fixed"] >= 200.0, "dist_to_basket_ft_fixed"] = np.nan
        # Use fixed where present
        df["dist_to_basket_ft"] = df["dist_to_basket_ft_fixed"].combine_first(
            df.get("dist_to_basket_ft", pd.Series(np.nan, index=df.index))
        )

    # Coerce numeric signals; missing cols -> NaN column for uniformity
    for col in NUMERIC_SIGNALS:
        if col not in df.columns:
            df[col] = np.nan
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def _aggregate_game(df: pd.DataFrame, game_id: str) -> pd.DataFrame:
    """Aggregate one game's per-frame data into per-lineup rows.

    Definition of a "lineup frame": the set of unique player_names belonging
    to the same team_abbrev seen in that frame. Empirically frames have 1-9
    players visible; many partial. We treat each (frame, team_abbrev)'s
    visible-player-set as the lineup for that frame, requiring at least 3
    distinct players visible to call it a meaningful sample.
    """
    # Per (frame, team_abbrev): set of player_names
    frame_team = (
        df.groupby(["frame", "team_abbrev"])["player_name"]
        .agg(lambda s: tuple(sorted(set(s.dropna().astype(str)))))
        .reset_index(name="lineup_tuple")
    )
    # Require >=3 distinct visible players per side per frame (noise floor)
    frame_team = frame_team[frame_team["lineup_tuple"].apply(len) >= 3]
    if frame_team.empty:
        return pd.DataFrame()

    frame_team["lineup_str"] = frame_team["lineup_tuple"].apply(lambda t: "-".join(t))

    # Merge back so each (frame, team_abbrev) per-player row gets its lineup_str
    merged = df.merge(
        frame_team[["frame", "team_abbrev", "lineup_str"]],
        on=["frame", "team_abbrev"],
        how="inner",
    )

    # Aggregate numeric signals per (team_abbrev, lineup_str) — across all rows,
    # which means we average per-player per-frame signals within the lineup window.
    agg_map: dict[str, tuple[str, str]] = {}
    for col in NUMERIC_SIGNALS:
        agg_map[f"{col}_mean"] = (col, "mean")
    # A few useful max/sum variants
    agg_map["velocity_max"] = ("velocity", "max")
    agg_map["paint_count_opp_mean_max"] = ("paint_count_opp", "max")
    if "paint_pressure_90_fixed" in merged.columns:
        agg_map["paint_pressure_90_fixed_mean"] = ("paint_pressure_90_fixed", "mean")
    if "paint_pressure_opp_90_fixed" in merged.columns:
        agg_map["paint_pressure_opp_90_fixed_mean"] = ("paint_pressure_opp_90_fixed", "mean")

    grouped = merged.groupby(["team_abbrev", "lineup_str"]).agg(**agg_map).reset_index()

    # n_frames = distinct frames the lineup appeared in (not per-player rows)
    nframes = (
        merged.drop_duplicates(["team_abbrev", "lineup_str", "frame"])
        .groupby(["team_abbrev", "lineup_str"])
        .size()
        .rename("n_frames")
        .reset_index()
    )
    grouped = grouped.merge(nframes, on=["team_abbrev", "lineup_str"], how="left")

    # Pace proxy: frames per possession (if possession_id exists)
    if "possession_id" in df.columns:
        merged2 = merged.copy()
        merged2["possession_id"] = pd.to_numeric(merged2["possession_id"], errors="coerce")
        npos = (
            merged2.dropna(subset=["possession_id"])
            .drop_duplicates(["team_abbrev", "lineup_str", "possession_id"])
            .groupby(["team_abbrev", "lineup_str"])
            .size()
            .rename("n_possessions")
            .reset_index()
        )
        grouped = grouped.merge(npos, on=["team_abbrev", "lineup_str"], how="left")
        grouped["pace_proxy_frames_per_poss"] = grouped["n_frames"] / grouped[
            "n_possessions"
        ].replace(0, np.nan)
    else:
        grouped["n_possessions"] = np.nan
        grouped["pace_proxy_frames_per_poss"] = np.nan

    # Filter noise floor
    grouped = grouped[grouped["n_frames"] >= MIN_FRAMES].copy()
    if grouped.empty:
        return pd.DataFrame()

    grouped.insert(0, "game_id", game_id)
    # Stable lineup_id = team_abbrev + lineup_str
    grouped["lineup_id"] = grouped["team_abbrev"] + "::" + grouped["lineup_str"]
    # Reorder for readability
    front = ["game_id", "team_abbrev", "lineup_id", "lineup_str", "n_frames",
             "n_possessions", "pace_proxy_frames_per_poss"]
    rest = [c for c in grouped.columns if c not in front]
    grouped = grouped[front + rest]
    return grouped


def main() -> int:
    t_start = time.time()
    game_dirs = sorted([p for p in TRACKING_ROOT.iterdir() if p.is_dir()])
    print(f"Found {len(game_dirs)} game dirs under {TRACKING_ROOT}")

    all_rows: list[pd.DataFrame] = []
    n_ok = 0
    n_skip = 0
    n_fail = 0
    for gd in game_dirs:
        game_id = gd.name
        try:
            df = _safe_read_tracking(gd)
            if df is None:
                n_skip += 1
                print(f"  [{game_id}] skip (no tracking_data.csv or bad schema)")
                continue
            agg = _aggregate_game(df, game_id)
            if agg.empty:
                n_skip += 1
                print(f"  [{game_id}] skip (no lineup met n_frames>={MIN_FRAMES})")
                continue
            all_rows.append(agg)
            n_ok += 1
            print(f"  [{game_id}] OK rows={len(agg)} median_n_frames={agg['n_frames'].median():.0f}")
        except Exception as exc:
            n_fail += 1
            print(f"  [{game_id}] FAIL: {exc}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

    if not all_rows:
        print("No lineup rows produced. Aborting.")
        return 1

    out_df = pd.concat(all_rows, ignore_index=True)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(OUTPUT_PATH, index=False)

    elapsed = time.time() - t_start
    print("\n========== SUMMARY ==========")
    print(f"games ok / skip / fail = {n_ok} / {n_skip} / {n_fail}")
    print(f"total lineup rows: {len(out_df)}")
    print(f"unique lineups   : {out_df['lineup_id'].nunique()}")
    print(f"median n_frames  : {out_df['n_frames'].median():.0f}")
    print(f"output parquet   : {OUTPUT_PATH}")
    print(f"runtime          : {elapsed:.1f}s")
    print("\nSample 5 rows:")
    sample_cols = [
        "game_id", "team_abbrev", "lineup_str", "n_frames",
        "team_spacing_mean", "distance_to_ball_mean",
        "dist_to_basket_ft_mean", "velocity_mean", "paint_count_opp_mean",
        "pace_proxy_frames_per_poss",
    ]
    sample_cols = [c for c in sample_cols if c in out_df.columns]
    print(out_df.sample(min(5, len(out_df)), random_state=42)[sample_cols].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
