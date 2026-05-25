"""scripts/build_opp_l5_per_stat.py -- R5-E opponent allowed rates builder.

For each (game_id, team_abbreviation) in player_quarter_stats, computes the
opponent's total pts/reb/ast/fg3m/stl/blk/tov allowed in that game, then
computes rolling L5 means (walk-forward, shift(1)) per team per game_date.

Output: data/opp_l5_per_stat.parquet
Columns: team_abbreviation, game_date, opp_l5_{pts,reb,ast,fg3m,stl,blk,tov}_allowed

Join strategy:
  - player_quarter_stats.parquet has: game_id, player_id, period, stats (no team/date)
  - player_pf.parquet has: game_id, player_id, team_abbreviation, game_date
  - Use player_pf to build game_id -> {team_abbrev -> game_date} and
    game_id -> {team_abbrev -> opponent_abbrev}

Usage:
    python scripts/build_opp_l5_per_stat.py
"""
from __future__ import annotations

import os
import sys
from typing import Dict, Tuple

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
OUT_PATH = os.path.join(PROJECT_DIR, "data", "opp_l5_per_stat.parquet")

QSTATS_PATH = os.path.join(PROJECT_DIR, "data", "player_quarter_stats.parquet")
PF_PATH     = os.path.join(PROJECT_DIR, "data", "player_pf.parquet")


def main() -> int:
    print("  loading player_quarter_stats ...", flush=True)
    qstats = pd.read_parquet(QSTATS_PATH)
    print(f"  qstats shape: {qstats.shape}")

    print("  loading player_pf for team/date join ...", flush=True)
    pf = pd.read_parquet(PF_PATH, columns=["game_id", "player_id", "team_abbreviation", "game_date"])

    # Build player_id -> (game_id, team_abbreviation, game_date) via player_pf.
    # Drop duplicates: one row per (player_id, game_id).
    pf_unique = pf.drop_duplicates(subset=["player_id", "game_id"])

    # Merge team info into qstats using (player_id, game_id)
    qstats_merged = qstats.merge(
        pf_unique[["game_id", "player_id", "team_abbreviation", "game_date"]],
        on=["game_id", "player_id"],
        how="inner",
    )
    n_merged = len(qstats_merged)
    n_total  = len(qstats)
    print(f"  merged {n_merged}/{n_total} qstats rows with team/date info")

    # Step 1: Sum per-stat totals by (game_id, team_abbreviation) across all periods.
    team_game_totals = (
        qstats_merged
        .groupby(["game_id", "team_abbreviation", "game_date"], as_index=False)
        [list(STATS)]
        .sum()
    )
    print(f"  team-game totals: {len(team_game_totals)} rows")

    # Step 2: For each game_id, derive the opponent team.
    # Each game has exactly 2 teams; the opponent of team T is the other team.
    game_teams = (
        team_game_totals[["game_id", "team_abbreviation"]]
        .copy()
        .rename(columns={"team_abbreviation": "opp_team_abbreviation"})
    )
    # Self-join on game_id to pair each team with the other
    opp_join = team_game_totals.merge(game_teams, on="game_id", how="inner")
    # Remove same-team rows
    opp_join = opp_join[opp_join["team_abbreviation"] != opp_join["opp_team_abbreviation"]]

    # Sanity check: each (game_id, team_abbreviation) should have exactly one opponent
    dup_check = opp_join.groupby(["game_id", "team_abbreviation"]).size()
    if (dup_check > 1).any():
        bad = dup_check[dup_check > 1]
        print(f"  WARN: {len(bad)} (game_id, team) pairs have >1 opponent, dropping extras")
        opp_join = opp_join.drop_duplicates(subset=["game_id", "team_abbreviation"])

    # The "allowed" stat for team T is what the OPP scored AGAINST T.
    # Merge in opp's totals: join opp_team_abbreviation back as team_abbreviation.
    opp_stats = team_game_totals.rename(
        columns={s: f"opp_allowed_{s}" for s in STATS}
    ).rename(columns={"team_abbreviation": "opp_team_abbreviation"})

    # Merge: for each (game_id, team_abbreviation, game_date), attach what OPP scored
    allowed = opp_join[["game_id", "team_abbreviation", "game_date", "opp_team_abbreviation"]].merge(
        opp_stats[["game_id", "opp_team_abbreviation"] + [f"opp_allowed_{s}" for s in STATS]],
        on=["game_id", "opp_team_abbreviation"],
        how="inner",
    )
    print(f"  allowed rows: {len(allowed)}")

    # Step 3: Walk-forward L5 rolling mean per (team_abbreviation, game_date).
    # Sort chronologically per team, then shift(1).rolling(5).mean().
    allowed["game_date"] = pd.to_datetime(allowed["game_date"])
    allowed = allowed.sort_values(["team_abbreviation", "game_date"]).reset_index(drop=True)

    result_rows = []
    for team, grp in allowed.groupby("team_abbreviation"):
        grp = grp.sort_values("game_date").reset_index(drop=True)
        for s in STATS:
            col = f"opp_allowed_{s}"
            grp[f"opp_l5_{s}_allowed"] = (
                grp[col].shift(1).rolling(5, min_periods=1).mean()
            )
        result_rows.append(grp)

    out_df = pd.concat(result_rows, ignore_index=True)
    out_cols = (
        ["team_abbreviation", "game_date"]
        + [f"opp_l5_{s}_allowed" for s in STATS]
    )
    out_df = out_df[out_cols].copy()

    # Drop rows where all L5 features are NaN (no prior games)
    l5_cols = [f"opp_l5_{s}_allowed" for s in STATS]
    out_df = out_df.dropna(subset=l5_cols, how="all").reset_index(drop=True)
    out_df["game_date"] = out_df["game_date"].dt.strftime("%Y-%m-%d")

    print(f"  output rows: {len(out_df)}")
    print(f"  sample:\n{out_df.head(5).to_string()}")

    out_df.to_parquet(OUT_PATH, index=False)
    print(f"\n  saved -> {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
