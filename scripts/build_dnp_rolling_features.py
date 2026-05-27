"""
Build DNP-derived rolling team-availability and player-DNP-rate features.

Outputs:
  data/cache/dnp_features_team.parquet
      (game_id, team_abbreviation, game_date,
       dnp_count_in_game, dnp_count_l5_avg, dnp_count_l10_avg, prior_game_dnp_count)
  data/cache/dnp_features_player.parquet
      (player_id, game_date, player_dnp_rate_l20)

Leak-free: all rolling features use shift(1) before rolling window.
"""

import os
import pandas as pd

DATA_DIR = "data"
CACHE_DIR = "data/cache"


def load_schedule() -> pd.DataFrame:
    """
    Return (game_id, team_abbreviation, game_date) for all known team-game combos.
    rest_travel.parquet covers 2021-22 through 2025-26 — same date range as DNP rows.
    """
    rt_path = os.path.join(DATA_DIR, "rest_travel.parquet")
    rt = pd.read_parquet(rt_path, columns=["game_id", "team_abbreviation", "game_date"])
    rt["game_date"] = pd.to_datetime(rt["game_date"])
    return rt


def build_team_features(dnp: pd.DataFrame, schedule: pd.DataFrame) -> pd.DataFrame:
    """
    For each (team_abbreviation, game_id) in schedule:
      - dnp_count_in_game:    how many DNPs that team had
      - dnp_count_l5_avg:     shift(1).rolling(5) mean of dnp_count_in_game
      - dnp_count_l10_avg:    shift(1).rolling(10) mean
      - prior_game_dnp_count: shift(1) of dnp_count_in_game
    """
    # Count DNPs per team per game
    dnp_counts = (
        dnp.groupby(["game_id", "team"])
        .size()
        .reset_index(name="dnp_count_in_game")
        .rename(columns={"team": "team_abbreviation"})
    )

    # Merge with full schedule so teams with 0 DNPs get a row too
    merged = schedule.merge(dnp_counts, on=["game_id", "team_abbreviation"], how="left")
    merged["dnp_count_in_game"] = merged["dnp_count_in_game"].fillna(0).astype(int)

    # Sort for rolling; ensure each team's games are in chronological order
    merged = merged.sort_values(["team_abbreviation", "game_date"]).reset_index(drop=True)

    def _rolling(grp: pd.DataFrame) -> pd.DataFrame:
        shifted = grp["dnp_count_in_game"].shift(1)
        grp["prior_game_dnp_count"] = shifted
        grp["dnp_count_l5_avg"] = shifted.rolling(5, min_periods=1).mean()
        grp["dnp_count_l10_avg"] = shifted.rolling(10, min_periods=1).mean()
        return grp

    result = merged.groupby("team_abbreviation", group_keys=False).apply(_rolling)

    cols = [
        "game_id",
        "team_abbreviation",
        "game_date",
        "dnp_count_in_game",
        "dnp_count_l5_avg",
        "dnp_count_l10_avg",
        "prior_game_dnp_count",
    ]
    return result[cols].reset_index(drop=True)


def build_player_features(dnp: pd.DataFrame, schedule: pd.DataFrame) -> pd.DataFrame:
    """
    For each (player_id, game_date) across all schedule dates:
      player_dnp_rate_l20: shift(1).rolling(20) mean of was_dnp indicator.

    We expand the full cross of (player_id x team game-dates) using the set of
    games each player's team played, then compute rolling DNP rate.
    """
    # Map player -> team (use most-recent team if player changed teams)
    player_team = (
        dnp[["player_id", "player", "team", "game_date"]]
        .sort_values("game_date")
        .groupby("player_id")
        .last()[["team"]]
        .reset_index()
        .rename(columns={"team": "team_abbreviation"})
    )

    # All games per team from schedule
    team_games = schedule[["team_abbreviation", "game_id", "game_date"]].copy()

    # Expand: each player gets a row for every game their team played
    player_schedule = player_team.merge(team_games, on="team_abbreviation", how="left")

    # Flag DNP games
    dnp_flags = dnp[["player_id", "game_id"]].copy()
    dnp_flags["was_dnp"] = 1
    player_schedule = player_schedule.merge(
        dnp_flags, on=["player_id", "game_id"], how="left"
    )
    player_schedule["was_dnp"] = player_schedule["was_dnp"].fillna(0).astype(int)

    player_schedule = player_schedule.sort_values(
        ["player_id", "game_date"]
    ).reset_index(drop=True)

    def _player_rolling(grp: pd.DataFrame) -> pd.DataFrame:
        shifted = grp["was_dnp"].shift(1)
        grp["player_dnp_rate_l20"] = shifted.rolling(20, min_periods=5).mean()
        return grp

    result = player_schedule.groupby("player_id", group_keys=False).apply(
        _player_rolling
    )

    cols = ["player_id", "game_date", "player_dnp_rate_l20"]
    return result[cols].reset_index(drop=True)


def null_rate(df: pd.DataFrame) -> dict:
    n = len(df)
    return {c: f"{df[c].isnull().sum() / n:.2%}" for c in df.columns}


def main() -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)

    print("Loading DNP rows …")
    dnp = pd.read_parquet(os.path.join(DATA_DIR, "dnp_rows.parquet"))
    dnp["game_date"] = pd.to_datetime(dnp["game_date"])

    print("Loading schedule …")
    schedule = load_schedule()

    # ------------------------------------------------------------------ #
    # Team-level features
    # ------------------------------------------------------------------ #
    print("Building team-level features …")
    team_feats = build_team_features(dnp, schedule)

    out_team = os.path.join(CACHE_DIR, "dnp_features_team.parquet")
    team_feats.to_parquet(out_team, index=False)

    print(f"\n[team-level] rows={len(team_feats):,}")
    print("  null rates:", null_rate(team_feats))

    # Top-5 teams by avg dnp_count_l10_avg
    top5 = (
        team_feats.groupby("team_abbreviation")["dnp_count_l10_avg"]
        .mean()
        .sort_values(ascending=False)
        .head(5)
    )
    print("\n  Top-5 teams by mean dnp_count_l10_avg:")
    for team, val in top5.items():
        print(f"    {team}: {val:.3f}")

    # ------------------------------------------------------------------ #
    # Player-level features
    # ------------------------------------------------------------------ #
    print("\nBuilding player-level features …")
    player_feats = build_player_features(dnp, schedule)

    out_player = os.path.join(CACHE_DIR, "dnp_features_player.parquet")
    player_feats.to_parquet(out_player, index=False)

    print(f"\n[player-level] rows={len(player_feats):,}")
    print("  null rates:", null_rate(player_feats))

    print("\nDone.")
    print(f"  team   → {out_team}")
    print(f"  player → {out_player}")


if __name__ == "__main__":
    main()
