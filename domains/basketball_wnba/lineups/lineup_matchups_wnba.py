"""WNBA lineup-vs-lineup matchup segments -- thin adapter over
domains.basketball_nba.lineups.lineup_matchups: intersect_stints (used inside
build_game_matchups)/build_game_matchups/aggregate_matchups/sanity_check are
pure over any stints dataframe with the shared schema and are reused
UNMODIFIED. Two seams differ:

  1. period length -- lineup_matchups.py defines its OWN local
     _period_length_s (720/300), used only by sanity_check's invariant.
     Patched the same way as pbp_lineups._period_length_s (module-level
     monkeypatch, restored after use).
  2. game_date -- NBA's main() hardcodes reading games.parquet for the date
     attach, with no CLI override; WNBA has no games.parquet, but
     player_boxscores.parquet already carries game_date per row, so
     aggregate_matchups() is called directly here with a WNBA games_df built
     from that column, instead of going through NBA's main().

OUTPUT: data/cache/team_system/lineups/lineup_matchups_wnba_2026.parquet

NETWORK: zero. CLI: python -m domains.basketball_wnba.lineups.lineup_matchups_wnba
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

import domains.basketball_nba.lineups.lineup_matchups as nba_matchups
from domains.basketball_wnba.lineups.pbp_lineups_wnba import _BOX_SRC, _OUT_PATH as _STINTS_DEFAULT, _wnba_period_length_s

REPO_ROOT = Path(__file__).resolve().parents[3]
_OUT_PATH = REPO_ROOT / "data" / "cache" / "team_system" / "lineups" / "lineup_matchups_wnba_2026.parquet"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build WNBA lineup-vs-lineup matchup segments from stint tables")
    parser.add_argument("--stints", type=str, default=str(_STINTS_DEFAULT))
    parser.add_argument("--out", type=str, default=str(_OUT_PATH))
    args = parser.parse_args(argv)

    stints_df = pd.read_parquet(args.stints)
    box_df = pd.read_parquet(_BOX_SRC)
    games_df = box_df[["game_id", "game_date"]].drop_duplicates().rename(columns={"game_date": "date"})
    games_df["game_id"] = games_df["game_id"].astype(str)

    orig_period_len = nba_matchups._period_length_s
    nba_matchups._period_length_s = _wnba_period_length_s
    try:
        seg_df = nba_matchups.build_game_matchups(stints_df)
        result = nba_matchups.aggregate_matchups(seg_df, games_df)
        invariant_df = nba_matchups.sanity_check(seg_df, stints_df)
    finally:
        nba_matchups._period_length_s = orig_period_len

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(out_path, index=False)

    n_games = int(invariant_df["game_id"].nunique()) if not invariant_df.empty else 0
    flagged = invariant_df[invariant_df["pct_diff"].abs() > 0.10] if not invariant_df.empty else invariant_df
    print(f"games={n_games} matchup_rows={len(result)} -> {out_path}")
    if not invariant_df.empty:
        print(
            f"overlap/game-length invariant: mean_pct_diff={invariant_df['pct_diff'].mean():.4f} "
            f"median={invariant_df['pct_diff'].median():.4f} flagged(>10pct)={len(flagged)}/{n_games}"
        )
        for _, row in flagged.head(20).iterrows():
            print(f"  FLAG game_id={row['game_id']} overlap_s={row['overlap_total_s']} expected_s={row['expected_s']} pct_diff={row['pct_diff']}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
