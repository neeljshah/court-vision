"""Iterates the registry-backed builders in player/team/lineup_attributes.py,
writes the 3 SHARED-SCHEMA parquets, prints per-attribute coverage.

CLI: python -m domains.basketball_nba.profiles.build_profiles
NETWORK: zero.
"""
from __future__ import annotations

import argparse

import pandas as pd

from domains.basketball_nba.profiles.lineup_attributes import build_all_lineup_rows
from domains.basketball_nba.profiles.player_attributes import build_all_player_rows
from domains.basketball_nba.profiles.player_defense_zones import build_all_player_defense_zone_rows
from domains.basketball_nba.profiles.player_fouls import build_all_player_fouls_rows
from domains.basketball_nba.profiles.player_rebounding import build_all_player_rebounding_rows
from domains.basketball_nba.profiles.profile_compute import REPO_ROOT
from domains.basketball_nba.profiles.team_attributes import build_all_team_rows
from domains.basketball_nba.profiles.team_box_splits import build_all_team_box_split_rows
from domains.basketball_nba.profiles.team_clutch import build_all_team_clutch_rows
from domains.basketball_nba.profiles.team_expansion import build_all_team_expansion_rows

SEASONS = ["2023_24", "2024_25", "2025_26"]
_OUT_DIR = REPO_ROOT / "data" / "cache" / "profiles"

_SCHEMA_COLS = [
    "entity_id", "entity_name", "window", "attribute", "raw_value", "percentile",
    "rating_2k", "n", "ingredients", "status", "sources",
]


def _to_frame(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=_SCHEMA_COLS)
    df = pd.DataFrame(rows)
    for c in _SCHEMA_COLS:
        if c not in df.columns:
            df[c] = None
    return df[_SCHEMA_COLS]


def _print_coverage(label: str, df: pd.DataFrame) -> None:
    print(f"\n{label}: {len(df)} rows")
    if df.empty:
        print("  (no rows)")
        return
    for (attribute, window), g in df.groupby(["attribute", "window"]):
        n_entities = g["entity_id"].nunique()
        print(f"  {attribute:32s} {window:16s} n_entities={n_entities:5d} status={g['status'].iloc[0]}")


def build(seasons: list[str] = SEASONS, out_dir=_OUT_DIR) -> dict[str, pd.DataFrame]:
    player_rows = (
        build_all_player_rows(seasons) + build_all_player_defense_zone_rows(seasons)
        + build_all_player_rebounding_rows(seasons) + build_all_player_fouls_rows(seasons)
    )
    team_rows = (
        build_all_team_rows(seasons) + build_all_team_expansion_rows(seasons)
        + build_all_team_clutch_rows(seasons) + build_all_team_box_split_rows(seasons)
    )
    player_df = _to_frame(player_rows)
    team_df = _to_frame(team_rows)
    lineup_df = _to_frame(build_all_lineup_rows(seasons))

    out_dir.mkdir(parents=True, exist_ok=True)
    player_df.to_parquet(out_dir / "nba_player_profiles.parquet", index=False)
    team_df.to_parquet(out_dir / "nba_team_profiles.parquet", index=False)
    lineup_df.to_parquet(out_dir / "nba_lineup_profiles.parquet", index=False)
    return {"player": player_df, "team": team_df, "lineup": lineup_df}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build NBA player/team/lineup attribute profiles")
    parser.add_argument("--season", type=str, default="all", choices=[*SEASONS, "all"])
    args = parser.parse_args(argv)
    seasons = SEASONS if args.season == "all" else [args.season]

    frames = build(seasons)
    print("PRESENTATION NOTE: rating_2k/percentile are presentation-only -- gates/fits must read raw_value.")
    _print_coverage("PLAYER", frames["player"])
    _print_coverage("TEAM", frames["team"])
    _print_coverage("LINEUP", frames["lineup"])
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
