"""scripts.platformkit.omni.lineup_possessions -- P5 lineup-at-possession join.

The spine unlock: sim2_possessions.parquet (per-possession, NBA game_id) has
no lineup columns; SPINE-2 proved team-grain saturates. This module does NOT
re-walk raw substitutions -- data/cache/team_system/lineups/stints_2024_25.parquet
already exists (built by domains/basketball_nba/lineups/pbp_lineups.py, same
substitution-walk + box-score-starter-seed method already tested in
domains/basketball_nba/lineups/test_pbp_lineups.py), covering the full 2024-25
season (1230 games, NBA-stats game_id -- same id space as sim2_possessions,
no ESPN crosswalk needed). This module: (1) independently re-validates the
5-on-floor invariant per game (quarantine, don't trust the upstream `quality`
string blindly), (2) resolves each team_id's home/away side via
player_boxscores.parquet (a lineup_key's first player -> is_home), (3) joins
stints to sim2_possessions via pd.merge_asof on elapsed-seconds within
(game_id, period, team_id), (4) ledgers structural claims.

OUTPUT: data/omni/lineups/possession_lineups_2024_25.parquet
  game_id, possession_key, off_team, def_team, off_lineup_ids, def_lineup_ids
  (lineup_ids = comma-joined sorted NBA player ids, per stints convention).

CLI: python -m scripts.platformkit.omni.lineup_possessions
Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_lineup_possessions.py -q
"""
from __future__ import annotations

import pathlib

import pandas as pd

from scripts.platformkit.omni import claims_ledger as cl

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
STINTS_PATH = REPO_ROOT / "data" / "cache" / "team_system" / "lineups" / "stints_2024_25.parquet"
POSSESSIONS_PATH = REPO_ROOT / "data" / "cache" / "ingame" / "sim2_possessions.parquet"
BOXSCORES_PATH = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
OUT_PATH = REPO_ROOT / "data" / "omni" / "lineups" / "possession_lineups_2024_25.parquet"
SEASON = "2024-25"


def _period_length_s(period: int) -> float:
    return 720.0 if period <= 4 else 300.0  # ponytail: OT=300s fixed, same assumption as pbp_lineups.py


def validate_stints(stints_df: pd.DataFrame) -> tuple[set, set, float]:
    """Independent 5-on-floor check (does not trust upstream `quality` col).
    Returns (valid_game_ids, quarantined_game_ids, pass_rate)."""
    bad_games = set(stints_df.loc[stints_df["n_on_court"] != 5, "game_id"])
    all_games = set(stints_df["game_id"])
    valid_games = all_games - bad_games
    pass_rate = len(valid_games) / len(all_games) if all_games else 0.0
    return valid_games, bad_games, pass_rate


def build_team_is_home(stints_df: pd.DataFrame, box_df: pd.DataFrame) -> pd.DataFrame:
    """(game_id, team_id) -> is_home, resolved via the lineup_key's first
    player id looked up in player_boxscores (game_id, player_id) -> is_home."""
    first_player = (
        stints_df.sort_values(["game_id", "team_id", "period", "start_s"])
        .groupby(["game_id", "team_id"])["lineup_key"].first()
        .str.split(",").str[0].astype("int64")
        .reset_index(name="player_id")
    )
    box_home = box_df[["game_id", "player_id", "is_home"]].drop_duplicates(["game_id", "player_id"])
    merged = first_player.merge(box_home, on=["game_id", "player_id"], how="left")
    merged["is_home"] = merged["is_home"].astype("boolean")
    return merged[["game_id", "team_id", "is_home"]]


def join_possessions(
    possessions_df: pd.DataFrame, stints_df: pd.DataFrame, team_is_home: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    """Join stints onto possessions by elapsed-seconds within (game_id, period,
    team_id) via merge_asof. Returns (possession_lineups_df, stats)."""
    poss = possessions_df.reset_index(drop=True).copy()
    poss["poss_row"] = range(len(poss))
    poss["elapsed"] = poss["period"].map(_period_length_s) - poss["clock_start"]
    poss["possession_key"] = (
        poss["game_id"].astype(str) + ":" + poss.groupby("game_id").cumcount().astype(str)
    )

    home_map = team_is_home[team_is_home["is_home"] == True][["game_id", "team_id"]]  # noqa: E712
    away_map = team_is_home[team_is_home["is_home"] == False][["game_id", "team_id"]]  # noqa: E712
    poss = poss.merge(home_map.rename(columns={"team_id": "home_team_id"}), on="game_id", how="left")
    poss = poss.merge(away_map.rename(columns={"team_id": "away_team_id"}), on="game_id", how="left")
    poss["off_team_id"] = poss["home_team_id"].where(poss["off_is_home"], poss["away_team_id"])
    poss["def_team_id"] = poss["away_team_id"].where(poss["off_is_home"], poss["home_team_id"])

    # drop zero-duration stints (period-boundary bookkeeping rows in the
    # source, start_s==end_s): they carry no possession-time span and their
    # tied elapsed=0 key otherwise beats the real first segment in merge_asof.
    non_degenerate = stints_df[stints_df["start_s"] < stints_df["end_s"]]
    stints_asof = non_degenerate.rename(columns={"start_s": "elapsed"})[
        ["game_id", "team_id", "period", "elapsed", "end_s", "lineup_key"]
    ].sort_values("elapsed")
    stints_asof["team_id"] = stints_asof["team_id"].astype("Int64")

    def _attach(side_team_col: str) -> pd.Series:
        side = poss[["poss_row", "game_id", "period", "elapsed", side_team_col]].rename(
            columns={side_team_col: "team_id"}
        ).sort_values("elapsed")
        side["team_id"] = side["team_id"].astype("Int64")
        merged = pd.merge_asof(
            side, stints_asof, on="elapsed", by=["game_id", "period", "team_id"], direction="backward",
        )
        merged["lineup_key"] = merged["lineup_key"].where(merged["elapsed"] <= merged["end_s"] + 1e-6)
        return merged.set_index("poss_row")["lineup_key"]

    poss["off_lineup_ids"] = poss["poss_row"].map(_attach("off_team_id"))
    poss["def_lineup_ids"] = poss["poss_row"].map(_attach("def_team_id"))

    n_total = len(poss)
    matched = poss["off_lineup_ids"].notna() & poss["def_lineup_ids"].notna()
    n_matched = int(matched.sum())
    out = poss.loc[matched, [
        "game_id", "possession_key", "off_team_id", "def_team_id", "off_lineup_ids", "def_lineup_ids",
    ]].rename(columns={"off_team_id": "off_team", "def_team_id": "def_team"})
    out["off_team"] = out["off_team"].astype("Int64")
    out["def_team"] = out["def_team"].astype("Int64")
    stats = {
        "n_total_possessions": n_total,
        "n_matched": n_matched,
        "join_rate": n_matched / n_total if n_total else 0.0,
    }
    return out, stats


def main() -> int:
    stints_df = pd.read_parquet(STINTS_PATH)
    possessions_df = pd.read_parquet(POSSESSIONS_PATH)
    possessions_df = possessions_df[possessions_df["season"] == SEASON].copy()
    box_df = pd.read_parquet(BOXSCORES_PATH)
    box_df = box_df[box_df["season"] == SEASON][["game_id", "player_id", "is_home"]].copy()
    box_df["is_home"] = box_df["is_home"].astype(bool)

    valid_games, quarantined_games, pass_rate = validate_stints(stints_df)
    stints_valid = stints_df[stints_df["game_id"].isin(valid_games)]
    possessions_valid = possessions_df[possessions_df["game_id"].isin(valid_games)]

    team_is_home = build_team_is_home(stints_valid, box_df)
    out_df, stats = join_possessions(possessions_valid, stints_valid, team_is_home)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(OUT_PATH, index=False)

    claims = [
        {
            "statement": (
                f"NBA possession-lineup store exists for {SEASON}: "
                f"{len(out_df)} possession-lineup rows across {out_df['game_id'].nunique()} games."
            ),
            "type": "structural",
            "scope": {"sport": "nba", "seasons": [SEASON]},
            "topic": "lineup_possession_store",
        },
        {
            "statement": (
                f"NBA lineup-stint validation pass rate {SEASON}: "
                f"{pass_rate:.4f} ({len(valid_games)}/{len(valid_games) + len(quarantined_games)} games clean)."
            ),
            "type": "structural",
            "scope": {"sport": "nba", "seasons": [SEASON]},
            "topic": "lineup_stint_validation",
        },
        {
            "statement": (
                f"NBA stint-to-possession join rate {SEASON}: "
                f"{stats['join_rate']:.4f} ({stats['n_matched']}/{stats['n_total_possessions']})."
            ),
            "type": "structural",
            "scope": {"sport": "nba", "seasons": [SEASON]},
            "topic": "lineup_possession_join",
        },
    ]
    added, _ = cl.add_claims_batch(claims)

    print(f"stint_validation_pass_rate={pass_rate:.4f} "
          f"valid_games={len(valid_games)} quarantined_games={sorted(quarantined_games)}")
    print(f"join_rate={stats['join_rate']:.4f} "
          f"n_matched={stats['n_matched']} n_total={stats['n_total_possessions']}")
    print(f"wrote {len(out_df)} rows -> {OUT_PATH}")
    print(f"claims_added={added}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
