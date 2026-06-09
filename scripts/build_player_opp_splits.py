"""build_player_opp_splits.py — INT-130 per-player historical splits vs opponent team.

Produces data/intelligence/player_opp_splits_sidecar.parquet keyed on (player_id, game_date)
with 16 columns:
  - player_opp_pts_avg_l5               rolling-5 on PTS vs this opp (strict as-of)
  - player_opp_{pts,reb,ast,fg3m,fgm,ftm,stl}_avg_career  expanding mean vs opp (shift-1)
  - player_opp_{pts,reb,ast,fg3m,fgm,ftm,stl}_diff_vs_overall  affinity vs player overall
  - player_opp_n_games_prior            gate: # of prior games vs this opp (shift-1)

All features are STRICTLY as-of (shift(1) applied) — no leakage.

Usage:
    python scripts/build_player_opp_splits.py [--out PATH]
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

GAMELOG_GLOB = str(PROJECT_DIR / "data" / "nba" / "gamelog_full_*.json")
DEFAULT_OUT = str(PROJECT_DIR / "data" / "intelligence" / "player_opp_splits_sidecar.parquet")

STATS = ["pts", "reb", "ast", "fg3m", "fgm", "ftm", "stl"]


# ---------------------------------------------------------------------------
# Parse matchup string → (player_team, opp_team)
# ---------------------------------------------------------------------------
def _parse_matchup(matchup: str) -> tuple[str, str]:
    """
    "PHX vs. DEN"  → ("PHX", "DEN")   [home team]
    "PHX @ OKC"    → ("PHX", "OKC")   [away team]
    """
    if " vs. " in matchup:
        parts = matchup.split(" vs. ")
        return parts[0].strip(), parts[1].strip()
    elif " @ " in matchup:
        parts = matchup.split(" @ ")
        return parts[0].strip(), parts[1].strip()
    else:
        return ("UNK", "UNK")


def _parse_game_date(date_str: str) -> str:
    """Parse 'Apr 06, 2023' → '2023-04-06'."""
    try:
        return pd.to_datetime(date_str, format="%b %d, %Y").strftime("%Y-%m-%d")
    except Exception:
        return str(date_str)[:10]


# ---------------------------------------------------------------------------
# Main build
# ---------------------------------------------------------------------------
def build(out_path: str = DEFAULT_OUT, verbose: bool = True) -> pd.DataFrame:
    import glob as _glob

    files = sorted(_glob.glob(GAMELOG_GLOB))
    if verbose:
        print(f"[INT-130] Loading {len(files)} gamelog files ...")

    dfs = []
    for fp in files:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                records = json.load(f)
            if records:
                dfs.append(pd.DataFrame(records))
        except Exception as e:
            if verbose:
                print(f"  WARN: could not load {fp}: {e}")

    if not dfs:
        raise RuntimeError("No gamelog files loaded!")

    df = pd.concat(dfs, ignore_index=True)
    if verbose:
        print(f"  Combined rows: {len(df):,}")

    # --- Parse matchup → player_team, opp_team ---
    parsed = df["matchup"].apply(_parse_matchup)
    df["player_team"] = parsed.apply(lambda x: x[0])
    df["opp_team"] = parsed.apply(lambda x: x[1])

    # --- Parse game_date to ISO ---
    df["game_date_iso"] = df["game_date"].apply(_parse_game_date)

    # --- Drop trade-collision rows where player_team == opp_team ---
    before = len(df)
    df = df[df["player_team"] != df["opp_team"]].copy()
    if verbose:
        print(f"  Dropped {before - len(df)} trade-collision rows (player_team == opp_team)")

    # --- Ensure numeric stats ---
    for s in STATS:
        df[s] = pd.to_numeric(df[s], errors="coerce")

    # --- Drop rows with missing player_id or game_date ---
    df["player_id"] = pd.to_numeric(df["player_id"], errors="coerce")
    before2 = len(df)
    df = df.dropna(subset=["player_id", "game_date_iso"]).copy()
    if verbose and before2 > len(df):
        print(f"  Dropped {before2 - len(df)} rows with null player_id or game_date")

    # --- Sort by (player_id, opp_team, game_date_iso) ---
    df["player_id"] = df["player_id"].astype(int)
    df = df.sort_values(["player_id", "opp_team", "game_date_iso"]).reset_index(drop=True)

    # ---------------------------------------------------------------------------
    # Per (player_id, opp_team): expanding mean shift(1) → *_avg_career
    #                            rolling-5 shift(1) on pts → pts_avg_l5
    #                            cumcount shift(1) → n_games_prior
    # ---------------------------------------------------------------------------
    if verbose:
        print("  Computing per-(player_id, opp_team) expanding features ...")

    grp = df.groupby(["player_id", "opp_team"], sort=False)

    career_cols = {}
    for s in STATS:
        career_cols[f"player_opp_{s}_avg_career"] = (
            grp[s].transform(lambda x: x.expanding().mean().shift(1))
        )

    l5_col = grp["pts"].transform(lambda x: x.rolling(5, min_periods=1).mean().shift(1))
    n_games_col = grp.cumcount()  # 0-based; after shift this is n_prior

    # ---------------------------------------------------------------------------
    # Per (player_id) only: expanding mean shift(1) → overall_baseline
    # ---------------------------------------------------------------------------
    if verbose:
        print("  Computing per-player overall baseline ...")

    # Use all-opp data sorted by date for overall baseline
    df_sorted_by_date = df.sort_values(["player_id", "game_date_iso"])
    grp2 = df_sorted_by_date.groupby("player_id", sort=False)

    overall_baselines = {}
    for s in STATS:
        overall_baselines[s] = (
            grp2[s].transform(lambda x: x.expanding().mean().shift(1))
        )

    # Reindex back to df order (df is sorted by player_id, opp_team, date)
    # We need to align the overall baseline to each row in df
    # Build a lookup: for each (player_id, game_date_iso) → overall_baseline value
    # Since a player can appear multiple times per date (two games same day is impossible in NBA)
    # we can safely merge on (player_id, game_date_iso)
    overall_df = df_sorted_by_date[["player_id", "game_date_iso"]].copy()
    for s in STATS:
        overall_df[f"overall_{s}"] = overall_baselines[s].values

    # Drop duplicate (player_id, game_date_iso) keeping first (shouldn't be any)
    overall_df = overall_df.drop_duplicates(subset=["player_id", "game_date_iso"])

    # Merge back
    df_out = df[["player_id", "game_date_iso", "opp_team", "player_team"]].copy()
    df_out["player_opp_n_games_prior"] = n_games_col.values
    df_out["player_opp_pts_avg_l5"] = l5_col.values
    for s in STATS:
        df_out[f"player_opp_{s}_avg_career"] = career_cols[f"player_opp_{s}_avg_career"].values

    # Merge overall baseline
    df_out = df_out.merge(overall_df, on=["player_id", "game_date_iso"], how="left")

    # Compute diff_vs_overall
    for s in STATS:
        career_col = f"player_opp_{s}_avg_career"
        overall_col = f"overall_{s}"
        diff_col = f"player_opp_{s}_diff_vs_overall"
        df_out[diff_col] = df_out[career_col] - df_out[overall_col]

    # ---------------------------------------------------------------------------
    # Assertion test: for any player's FIRST game vs an opp,
    # n_games_prior=0, *_career=NaN, diff=NaN
    # ---------------------------------------------------------------------------
    first_games = df_out[df_out["player_opp_n_games_prior"] == 0]
    sample = first_games.sample(min(3, len(first_games)), random_state=42)
    if verbose:
        print("\n  [ASSERTION TEST] 3 first-game-vs-opp rows (should have NaN career/diff):")
        for _, row in sample.iterrows():
            pid = row["player_id"]
            gd = row["game_date_iso"]
            opp = row["opp_team"]
            n = row["player_opp_n_games_prior"]
            career_pts = row["player_opp_pts_avg_career"]
            diff_pts = row.get("player_opp_pts_diff_vs_overall", float("nan"))
            print(f"    player_id={pid} date={gd} opp={opp} n_prior={n} "
                  f"career_pts={career_pts} diff_pts={diff_pts}")
        # Verify NaN assertion
        career_nulls = first_games["player_opp_pts_avg_career"].isna().mean()
        diff_nulls = first_games["player_opp_pts_diff_vs_overall"].isna().mean()
        assert career_nulls > 0.99, f"ASSERTION FAILED: career_pts NaN rate={career_nulls:.3f} (expected ~1.0)"
        assert diff_nulls > 0.99, f"ASSERTION FAILED: diff_pts NaN rate={diff_nulls:.3f} (expected ~1.0)"
        print(f"    [OK] career_pts NaN rate={career_nulls:.3f}, diff_pts NaN rate={diff_nulls:.3f}")

    # ---------------------------------------------------------------------------
    # Select final 16 output columns
    # ---------------------------------------------------------------------------
    keep_cols = (
        ["player_id", "game_date_iso", "player_opp_n_games_prior", "player_opp_pts_avg_l5"]
        + [f"player_opp_{s}_avg_career" for s in STATS]
        + [f"player_opp_{s}_diff_vs_overall" for s in STATS]
    )
    df_final = df_out[keep_cols].rename(columns={"game_date_iso": "game_date"})

    # ---------------------------------------------------------------------------
    # Dedup: keep one row per (player_id, game_date) — take last (shouldn't be dupes)
    # ---------------------------------------------------------------------------
    df_final = df_final.drop_duplicates(subset=["player_id", "game_date"], keep="last")

    if verbose:
        print(f"\n  Final sidecar rows: {len(df_final):,}")
        print(f"  Columns: {list(df_final.columns)}")
        n_games_dist = df_final["player_opp_n_games_prior"].describe()
        print(f"  n_games_prior distribution:\n{n_games_dist}")

    # Save
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df_final.to_parquet(out_path, index=False)
    if verbose:
        print(f"\n  Saved to: {out_path}")

    return df_final


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="INT-130: build player×opp splits sidecar")
    ap.add_argument("--out", default=DEFAULT_OUT, help="Output parquet path")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    build(out_path=args.out, verbose=not args.quiet)
