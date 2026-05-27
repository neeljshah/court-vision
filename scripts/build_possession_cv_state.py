"""Build per-possession CV state vectors from per-frame tracking data.

Aggregates per-frame CV signals into one row per (game_id x possession_id) for
downstream Monte Carlo simulation (10K possession-level sims per game).

Sister script to scripts/build_lineup_cv_features.py (which aggregates by
lineup_id). Reuses the same file-loading conventions:
- Reads tracking_data.csv from data/<game_id>/, joined with
  tracking_data_corrected.csv when present for homography-fixed columns
  (preferred per Open Issues #13).
- Strips the 200.0 sentinel from dist_to_basket_ft_fixed (Open Issues #22).

Output: data/possession_cv_state.parquet
Schema columns documented in TASK spec — one row per (game_id, possession_id).

Filtering:
- Drop possessions with n_frames < 10 (~0.33s at 30fps; tracking artifacts).
- Drop possessions where the same player appears on BOTH offense and defense
  within the same frame (data corruption from team-color mis-classification).

Offense/defense identification:
- ball_possession is a per-row binary flag — the team with the higher
  ball_possession sum within the possession window is treated as offense.
- team_abbrev preferred; fall back to the 'team' color column when blank.
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
OUTPUT_PATH = Path(r"C:/Users/neelj/nba-ai-system/data/possession_cv_state.parquet")
MIN_FRAMES = 10
FPS = 30.0

# Per-frame numeric signals to aggregate per possession.
NUMERIC_SIGNALS = [
    "velocity",
    "acceleration",
    "team_spacing",
    "off_ball_distance",
    "dist_to_basket_ft",
    "paint_count_own",
    "paint_count_opp",
    "handler_isolation",
    "vel_toward_basket",
    "drive_flag",
    "fast_break_flag",
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

    needed = {"frame", "player_id", "possession_id"}
    if not needed.issubset(df.columns):
        missing = needed - set(df.columns)
        print(f"  missing required cols {missing}; skipping", file=sys.stderr)
        return None

    df["possession_id"] = pd.to_numeric(df["possession_id"], errors="coerce")
    df = df.dropna(subset=["possession_id", "frame"]).copy()
    if df.empty:
        return None

    # Pick a stable "team key" — prefer team_abbrev (e.g. BOS/MIL),
    # fall back to the lower-level color column (e.g. green/white).
    if "team_abbrev" in df.columns and df["team_abbrev"].notna().any():
        df["_team_key"] = df["team_abbrev"].where(
            df["team_abbrev"].notna(), df.get("team", pd.Series(np.nan, index=df.index))
        )
    else:
        df["_team_key"] = df.get("team", pd.Series(np.nan, index=df.index))

    # Player identity key — prefer player_name (stable), fall back to player_id
    # (per-game ephemeral but always present).
    if "player_name" in df.columns:
        df["_player_key"] = df["player_name"].where(
            df["player_name"].notna(), df["player_id"].astype("Int64").astype(str)
        )
    else:
        df["_player_key"] = df["player_id"].astype("Int64").astype(str)

    # Try corrected file for homography-fixed columns.
    corrected = game_dir / "tracking_data_corrected.csv"
    if corrected.exists():
        try:
            cdf = pd.read_csv(corrected, low_memory=False)
            keep = ["frame", "player_id"]
            for c in (
                "dist_to_basket_ft_fixed",
                "paint_pressure_90_fixed",
                "paint_pressure_own_90_fixed",
                "paint_pressure_opp_90_fixed",
                "in_paint_fixed",
                "near_basket_fixed",
            ):
                if c in cdf.columns:
                    keep.append(c)
            cdf = cdf[keep].drop_duplicates(subset=["frame", "player_id"])
            df = df.merge(cdf, on=["frame", "player_id"], how="left")
        except Exception as exc:
            print(f"  corrected merge failed (non-fatal): {exc}", file=sys.stderr)

    # Prefer fixed dist; strip 200.0 sentinel.
    if "dist_to_basket_ft_fixed" in df.columns:
        df.loc[df["dist_to_basket_ft_fixed"] >= 200.0, "dist_to_basket_ft_fixed"] = np.nan
        df["dist_to_basket_ft"] = df["dist_to_basket_ft_fixed"].combine_first(
            df.get("dist_to_basket_ft", pd.Series(np.nan, index=df.index))
        )

    # Coerce numeric columns; absent => NaN column.
    for col in NUMERIC_SIGNALS:
        if col not in df.columns:
            df[col] = np.nan
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "ball_possession" not in df.columns:
        df["ball_possession"] = np.nan
    else:
        df["ball_possession"] = pd.to_numeric(df["ball_possession"], errors="coerce")

    return df


def _detect_cross_team_artifacts(sub: pd.DataFrame) -> set[float]:
    """Return possession_ids where same player appears on both teams in same frame."""
    # Within a possession, per (frame, _player_key): if >1 distinct _team_key -> corruption.
    grp = (
        sub.dropna(subset=["_team_key", "_player_key"])
        .groupby(["possession_id", "frame", "_player_key"])["_team_key"]
        .nunique()
    )
    bad = grp[grp > 1].reset_index()["possession_id"].unique()
    return set(bad.tolist())


def _aggregate_game(df: pd.DataFrame, game_id: str) -> pd.DataFrame:
    """Aggregate one game's per-frame data into per-possession rows."""
    if df.empty:
        return pd.DataFrame()

    # Identify offense/defense per possession via ball_possession sum.
    bp = (
        df.dropna(subset=["_team_key"])
        .groupby(["possession_id", "_team_key"])["ball_possession"]
        .sum()
        .reset_index()
    )
    # For each possession, pick offense = team with max ball_possession sum.
    bp_sorted = bp.sort_values(
        ["possession_id", "ball_possession"], ascending=[True, False]
    )
    off_by_pos = bp_sorted.drop_duplicates(subset=["possession_id"], keep="first")
    off_map = dict(zip(off_by_pos["possession_id"], off_by_pos["_team_key"]))

    # All teams per possession (need 2 to split off vs def).
    teams_per_pos = (
        df.dropna(subset=["_team_key"])
        .groupby("possession_id")["_team_key"]
        .agg(lambda s: sorted(set(s)))
    )

    # Cross-team artifact set.
    bad_pos = _detect_cross_team_artifacts(df)

    rows: list[dict] = []
    for pid, pos_df in df.groupby("possession_id"):
        n_frames = pos_df["frame"].nunique()
        if n_frames < MIN_FRAMES:
            continue
        if pid in bad_pos:
            continue

        team_off = off_map.get(pid)
        teams_seen = teams_per_pos.get(pid, [])
        team_def = None
        if team_off is not None:
            for t in teams_seen:
                if t != team_off:
                    team_def = t
                    break

        # Offense / defense subsets.
        if team_off is not None:
            off_df = pos_df[pos_df["_team_key"] == team_off]
            def_df = pos_df[pos_df["_team_key"] == team_def] if team_def is not None else pos_df.iloc[0:0]
        else:
            off_df = pos_df
            def_df = pos_df.iloc[0:0]

        start_frame = int(pos_df["frame"].min())
        end_frame = int(pos_df["frame"].max())
        duration_frames = end_frame - start_frame + 1

        row = {
            "game_id": game_id,
            "possession_id": int(pid),
            "team_off": team_off,
            "team_def": team_def,
            "n_frames": int(n_frames),
            "start_frame": start_frame,
            "end_frame": end_frame,
            "duration_frames": int(duration_frames),
            "pace_seconds": float(duration_frames) / FPS,
            "velocity_mean": float(pos_df["velocity"].mean()),
            "velocity_max": float(pos_df["velocity"].max()),
            "acceleration_mean": float(pos_df["acceleration"].mean()),
            "team_spacing_mean": float(off_df["team_spacing"].mean()) if not off_df.empty else np.nan,
            "team_spacing_def_mean": float(def_df["team_spacing"].mean()) if not def_df.empty else np.nan,
            "dist_to_basket_ft_min": float(pos_df["dist_to_basket_ft"].min()),
            "dist_to_basket_ft_mean": float(pos_df["dist_to_basket_ft"].mean()),
            "defender_dist_mean": float(pos_df["off_ball_distance"].mean()),
            "defender_dist_min": float(pos_df["off_ball_distance"].min()),
            "paint_count_own_mean": float(pos_df["paint_count_own"].mean()),
            "paint_count_opp_mean": float(pos_df["paint_count_opp"].mean()),
            "handler_isolation_mean": float(pos_df["handler_isolation"].mean()),
            "vel_toward_basket_mean": float(pos_df["vel_toward_basket"].mean()),
            "drive_flag_any": int((pos_df["drive_flag"].fillna(0) > 0).any()),
            "fast_break_flag_any": int((pos_df["fast_break_flag"].fillna(0) > 0).any()),
        }
        if "paint_pressure_90_fixed" in pos_df.columns:
            row["paint_pressure_90_fixed_mean"] = float(
                pd.to_numeric(pos_df["paint_pressure_90_fixed"], errors="coerce").mean()
            )
        rows.append(row)

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


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
                print(f"  [{game_id}] skip (no possession met n_frames>={MIN_FRAMES})")
                continue
            all_rows.append(agg)
            n_ok += 1
            print(
                f"  [{game_id}] OK npos={len(agg)} median_n_frames={agg['n_frames'].median():.0f} "
                f"median_pace={agg['pace_seconds'].median():.1f}s"
            )
        except Exception as exc:
            n_fail += 1
            print(f"  [{game_id}] FAIL: {exc}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

    if not all_rows:
        print("No possession rows produced. Aborting.")
        return 1

    out_df = pd.concat(all_rows, ignore_index=True)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(OUTPUT_PATH, index=False)

    elapsed = time.time() - t_start
    per_game = out_df.groupby("game_id").size()
    print("\n========== SUMMARY ==========")
    print(f"games ok / skip / fail = {n_ok} / {n_skip} / {n_fail}")
    print(f"total possession rows: {len(out_df)}")
    print(f"median possessions/game: {per_game.median():.0f}")
    print(f"output parquet: {OUTPUT_PATH}")
    print(f"runtime: {elapsed:.1f}s")

    print("\nSample 5 rows:")
    sample_cols = [
        "game_id", "possession_id", "team_off", "team_def", "n_frames",
        "pace_seconds", "velocity_mean", "team_spacing_mean",
        "dist_to_basket_ft_min", "handler_isolation_mean", "drive_flag_any",
    ]
    sample_cols = [c for c in sample_cols if c in out_df.columns]
    print(out_df.sample(min(5, len(out_df)), random_state=42)[sample_cols].to_string(index=False))

    # Sanity checks
    print("\n========== SANITY CHECKS ==========")
    pace_med = out_df["pace_seconds"].median()
    print(f"pace_seconds median = {pace_med:.2f}s (target 12-24s NBA range)")
    print(f"  -> {'PASS' if 12.0 <= pace_med <= 24.0 else 'WARN'}")

    vel_nonnull = out_df["velocity_mean"].notna().mean()
    print(f"velocity_mean non-null pct = {vel_nonnull * 100:.1f}% (target >= 80%)")
    print(f"  -> {'PASS' if vel_nonnull >= 0.80 else 'WARN'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
