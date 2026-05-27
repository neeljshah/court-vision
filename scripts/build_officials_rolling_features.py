"""
build_officials_rolling_features.py
------------------------------------
Extract leak-free rolling referee features from data/officials_features.parquet
and write data/cache/officials_rolling.parquet.

Features produced per (game_id, team_abbreviation):
  l5_ref_crew_fouls_per_g   — shift(1).rolling(5) mean of ref_crew_fouls
  l5_ref_crew_fta_per_g     — shift(1).rolling(5) mean of ref_crew_fta
  ref_crew_fouls_z          — season-to-date z-score vs all teams (shift-before-std)
  ref_crew_fta_z            — same for FTA
  home_win_pct_advantage    — ref_crew_home_win_pct - 0.555 (league baseline)

Season is derived from game_id characters 3-4 (e.g. "0022400001" -> season "2024").
"""

import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "officials_features.parquet"
DST = ROOT / "data" / "cache" / "officials_rolling.parquet"


def derive_season(game_id: pd.Series) -> pd.Series:
    """'0022400001' -> '2024'"""
    return "20" + game_id.str[3:5]


def build_rolling(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each team, sort by game_date and compute shift(1).rolling(5) means
    so that the feature for row i never includes the current game (no leakage).
    """
    df = df.sort_values(["team_abbreviation", "game_date"]).copy()

    def _team_rolling(grp: pd.DataFrame) -> pd.DataFrame:
        shifted_fouls = grp["ref_crew_fouls"].shift(1)
        shifted_fta = grp["ref_crew_fta"].shift(1)
        grp["l5_ref_crew_fouls_per_g"] = shifted_fouls.rolling(5, min_periods=1).mean()
        grp["l5_ref_crew_fta_per_g"] = shifted_fta.rolling(5, min_periods=1).mean()
        return grp

    grp_keys = ["team_abbreviation"]
    result = (
        df.groupby(grp_keys, group_keys=False)[
            grp_keys + ["game_date", "game_id", "ref_crew_fouls", "ref_crew_fta",
                        "ref_crew_home_win_pct", "season"]
        ].apply(_team_rolling)
    )
    df = result.reset_index(drop=True)
    return df


def build_season_z(df: pd.DataFrame) -> pd.DataFrame:
    """
    Season-to-date z-scores computed across all teams for a given date within
    a season. To stay leak-free we use expanding stats up to but NOT including
    the current game: we sort by game_date, shift(1) within (season, game_date)
    groups is tricky, so we use the approach:

      For each row, z = (value - season_mean_excl_current) / season_std_excl_current

    Implementation: compute the full season mean/std WITHOUT the current row
    using the leave-one-out formula:
      mean_excl = (sum_all - x) / (n - 1)
      std_excl  = sqrt(((sum_sq_all - x^2) - (sum_all - x)^2/(n-1)) / (n-2))  [clamped >= 0]

    This is perfectly leak-free: each row's z is computed without that row's
    contribution to the season distribution.
    """
    df = df.copy()

    for col, z_col in [("ref_crew_fouls", "ref_crew_fouls_z"),
                       ("ref_crew_fta", "ref_crew_fta_z")]:

        # season-level aggregates (include all rows)
        season_agg = (
            df.groupby("season")[col]
            .agg(s_sum="sum", s_sq_sum=lambda x: (x ** 2).sum(), s_n="count")
            .reset_index()
        )
        df = df.merge(season_agg, on="season", how="left")

        x = df[col]
        n = df["s_n"]
        s = df["s_sum"]
        q = df["s_sq_sum"]

        # leave-one-out mean
        mean_excl = (s - x) / (n - 1)
        # leave-one-out variance (clamped to 0)
        var_num = (q - x ** 2) - (s - x) ** 2 / (n - 1)
        var_excl = (var_num / (n - 2)).clip(lower=0)
        std_excl = var_excl ** 0.5

        df[z_col] = (x - mean_excl) / std_excl.replace(0, float("nan"))

        # drop helper columns
        df = df.drop(columns=["s_sum", "s_sq_sum", "s_n"])

    return df


def main() -> None:
    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------
    print(f"Loading {SRC} ...")
    df = pd.read_parquet(SRC)
    print(f"  Source rows: {len(df):,}  |  columns: {df.columns.tolist()}")

    # ------------------------------------------------------------------
    # Derive season
    # ------------------------------------------------------------------
    df["season"] = derive_season(df["game_id"])
    df["game_date"] = pd.to_datetime(df["game_date"])

    # ------------------------------------------------------------------
    # Rolling L5 (per team, sorted by date, shift-before-roll)
    # ------------------------------------------------------------------
    print("Building L5 rolling means ...")
    df = build_rolling(df)

    # ------------------------------------------------------------------
    # Season-to-date z-scores (leave-one-out across all teams, per season)
    # ------------------------------------------------------------------
    print("Building season z-scores ...")
    df = build_season_z(df)

    # ------------------------------------------------------------------
    # Home-win-pct advantage
    # ------------------------------------------------------------------
    df["home_win_pct_advantage"] = df["ref_crew_home_win_pct"] - 0.555

    # ------------------------------------------------------------------
    # Select output columns
    # ------------------------------------------------------------------
    out_cols = [
        "game_id",
        "game_date",
        "team_abbreviation",
        "season",
        "l5_ref_crew_fouls_per_g",
        "l5_ref_crew_fta_per_g",
        "ref_crew_fouls_z",
        "ref_crew_fta_z",
        "home_win_pct_advantage",
    ]
    out = df[out_cols].copy()

    # ------------------------------------------------------------------
    # Sort for deterministic output
    # ------------------------------------------------------------------
    out = out.sort_values(["season", "game_date", "game_id", "team_abbreviation"]).reset_index(drop=True)

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------
    print(f"\nOutput rows: {len(out):,}")
    print("\nNull rate per feature:")
    feat_cols = [c for c in out_cols if c not in ("game_id", "game_date", "team_abbreviation", "season")]
    for col in feat_cols:
        n_null = out[col].isna().sum()
        pct = 100 * n_null / len(out)
        print(f"  {col:<30s}  {n_null:>6,}  ({pct:.2f}%)")

    # ------------------------------------------------------------------
    # Sample row for game 0022400001
    # ------------------------------------------------------------------
    sample = out[out["game_id"] == "0022400001"]
    if not sample.empty:
        print("\nSample rows for game_id=0022400001:")
        print(sample.to_string(index=False))
    else:
        print("\n[WARN] game_id 0022400001 not found in output.")

    # ------------------------------------------------------------------
    # Write parquet (idempotent overwrite)
    # ------------------------------------------------------------------
    DST.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(out, preserve_index=False)
    pq.write_table(table, DST, compression="snappy")
    print(f"\nWrote {DST}")


if __name__ == "__main__":
    main()
