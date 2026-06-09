"""build_cv_coverage_interactions.py — INT-60 D3: CV × Coverage Interaction Features.

Formula (centered + smooth-gated):
    interaction = (cv_feature - league_avg_cv_feature) * sigmoid((n_cv_games - 5) / 2)

Where league_avg = shift(1).expanding().mean() per season (NO leakage).
sigmoid → ~0 at n=0, ~0.5 at n=5, ~0.88 at n=8.

Selected CV features: avg_defender_distance, avg_shot_clock_at_shot, shot_zone_paint_pct
  — chosen as the recipe's likely candidates; no prior WF signal exists in this codebase
  (INT-51 confirms potential_assists and AST CV corr = negative; INT-50 confirms defender_distance
   is inverted due to Bug 1).  Script still builds the parquet; validate script runs the WF gate.

Output schema:
    player_id, game_date,
    avg_defender_distance_x_coverage,
    avg_shot_clock_at_shot_x_coverage,
    shot_zone_paint_pct_x_coverage
"""
from __future__ import annotations

import json
import glob
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

SELECTED_FEATURES = [
    "avg_defender_distance",
    "avg_shot_clock_at_shot",
    "shot_zone_paint_pct",
]


def _sigmoid(x: np.ndarray) -> np.ndarray:
    """Numerically stable sigmoid."""
    return 1.0 / (1.0 + np.exp(-np.clip(x, -20, 20)))


def load_cv_wide() -> pd.DataFrame:
    """Load cv_features table, pivot to wide, attach game_date."""
    conn = sqlite3.connect(ROOT / "data" / "nba_ai.db")
    df_long = pd.read_sql(
        "SELECT game_id, player_id, feature_name, feature_value FROM cv_features", conn
    )
    conn.close()

    df_wide = df_long.pivot_table(
        index=["game_id", "player_id"],
        columns="feature_name",
        values="feature_value",
        aggfunc="first",
    ).reset_index()

    # Map game_id -> game_date via season_games
    game_dates: dict[str, str] = {}
    for f in sorted(glob.glob(str(ROOT / "data" / "nba" / "season_games*.json"))):
        with open(f) as fh:
            data = json.load(fh)
        for g in data.get("rows", []):
            gid = str(g.get("game_id", ""))
            gdate = str(g.get("game_date", ""))
            if gid and gdate:
                game_dates[gid] = gdate

    df_wide["game_date"] = df_wide["game_id"].map(game_dates)
    df_wide = df_wide.dropna(subset=["game_date"])
    df_wide["game_date"] = pd.to_datetime(df_wide["game_date"])
    df_wide = df_wide.sort_values(["player_id", "game_date"]).reset_index(drop=True)
    return df_wide


def build_interactions(
    df: pd.DataFrame,
    features: list[str] = SELECTED_FEATURES,
    n_cv_col: str = "n_prior_cv_games",
    random_coverage: bool = False,
    zero_features: bool = False,
    permute_player: bool = False,
    seed: int = 42,
) -> pd.DataFrame:
    """Compute interaction features.

    Args:
        df: wide CV dataframe with columns: player_id, game_date, <features>
        features: list of CV feature names to gate
        n_cv_col: column name for prior CV game count (or computed internally)
        random_coverage: NULL-A control — replace n_cv with Uniform(0,20)
        zero_features: NULL-B control — set CV features to 0 before interaction
        permute_player: NULL-C control — shuffle player_id on output before join
        seed: RNG seed for reproducibility
    """
    rng = np.random.default_rng(seed)
    out_rows = []

    for player_id, grp in df.groupby("player_id", sort=True):
        grp = grp.sort_values("game_date").reset_index(drop=True)

        for feat in features:
            if feat not in grp.columns:
                grp[feat] = np.nan

        # n_cv_games = number of PRIOR CV observations (cumcount = 0 for first appearance)
        n_cv = np.arange(len(grp), dtype=float)  # 0-indexed prior count

        if random_coverage:
            rng_local = np.random.RandomState(seed)
            n_cv = rng_local.uniform(0, 20, size=len(grp))

        gate = _sigmoid((n_cv - 5.0) / 2.0)

        for i, row in grp.iterrows():
            feat_vals = {}
            for feat in features:
                raw_val = row.get(feat, np.nan) if not zero_features else 0.0
                if pd.isna(raw_val):
                    raw_val = np.nan

                # league_avg: expanding mean of all PRIOR rows for this feature
                # Use shift(1) semantics — rows 0..i-1 relative to this player's series
                prior_vals = grp.iloc[:grp.index.get_loc(i)][feat].dropna().values
                if len(prior_vals) >= 1:
                    league_avg = float(np.mean(prior_vals))
                else:
                    league_avg = np.nan

                if pd.isna(raw_val) or pd.isna(league_avg):
                    interaction = np.nan
                else:
                    residual = raw_val - league_avg
                    idx_in_grp = grp.index.get_loc(i)
                    g = gate[idx_in_grp]
                    interaction = residual * g

                feat_vals[f"{feat}_x_coverage"] = interaction

            out_rows.append({
                "player_id": player_id,
                "game_date": row["game_date"],
                **feat_vals,
            })

    result = pd.DataFrame(out_rows)

    if permute_player:
        rng_local = np.random.RandomState(seed)
        result["player_id"] = rng_local.permutation(result["player_id"].values)

    return result


def build_interactions_fast(
    df: pd.DataFrame,
    features: list[str] = SELECTED_FEATURES,
    random_coverage: bool = False,
    zero_features: bool = False,
    permute_player: bool = False,
    seed: int = 42,
) -> pd.DataFrame:
    """Vectorised version — much faster than row-by-row."""
    rng_state = np.random.RandomState(seed)

    all_parts = []

    for player_id, grp in df.groupby("player_id", sort=True):
        grp = grp.sort_values("game_date").copy().reset_index(drop=True)
        n = len(grp)

        # n_cv: prior game count (0 for first game, 1 for second, etc.)
        n_cv = np.arange(n, dtype=float)
        if random_coverage:
            n_cv = rng_state.uniform(0, 20, size=n)

        gate = _sigmoid((n_cv - 5.0) / 2.0)

        row_data = {"player_id": player_id, "game_date": grp["game_date"].values}

        for feat in features:
            if feat not in grp.columns:
                vals = np.full(n, np.nan)
            else:
                vals = grp[feat].values.astype(float)

            if zero_features:
                vals = np.zeros(n)

            # Expanding mean of prior rows (shift-1 semantics)
            # league_avg[i] = mean(vals[0..i-1])
            cumsum = np.nancumsum(np.where(np.isnan(vals), 0, vals))
            cumcount = np.cumsum(~np.isnan(vals))
            # Shift by 1: at position i, use cumsum/cumcount from position i-1
            league_avg = np.full(n, np.nan)
            league_avg[1:] = np.where(
                cumcount[:-1] > 0,
                cumsum[:-1] / cumcount[:-1],
                np.nan,
            )

            residual = vals - league_avg  # nan if either is nan
            interaction = residual * gate

            row_data[f"{feat}_x_coverage"] = interaction

        part = pd.DataFrame(row_data)
        all_parts.append(part)

    result = pd.concat(all_parts, ignore_index=True)

    if permute_player:
        result["player_id"] = rng_state.permutation(result["player_id"].values)

    return result


def main() -> None:
    print("INT-60: Building CV × Coverage Interaction Features")
    print(f"ROOT: {ROOT}")

    df = load_cv_wide()
    print(f"CV wide: {len(df)} rows, {df['player_id'].nunique()} players, "
          f"{df['game_date'].min().date()} to {df['game_date'].max().date()}")

    # Check feature coverage
    for feat in SELECTED_FEATURES:
        if feat in df.columns:
            non_null = df[feat].notna().sum()
            print(f"  {feat}: {non_null}/{len(df)} non-null ({100*non_null/len(df):.1f}%)")
        else:
            print(f"  {feat}: MISSING from cv_features")

    result = build_interactions_fast(df, features=SELECTED_FEATURES)

    # Summary
    print(f"\nInteraction parquet: {len(result)} rows")
    for feat in SELECTED_FEATURES:
        col = f"{feat}_x_coverage"
        if col in result.columns:
            non_null = result[col].notna().sum()
            print(f"  {col}: {non_null} non-null ({100*non_null/len(result):.1f}%)")

    out_dir = ROOT / "data" / "intelligence"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "cv_coverage_interactions.parquet"
    result.to_parquet(out_path, index=False)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
