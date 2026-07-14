"""scripts.platformkit.omni.lineup_possessions -- P5 lineup-at-possession join
(SPINE-3: extended to 2025-26 + lineup/player-identity rate fitting).

The spine unlock: sim2_possessions.parquet (per-possession, NBA game_id) has
no lineup columns; SPINE-2 proved team-grain saturates. This module does NOT
re-walk raw substitutions -- data/cache/team_system/lineups/stints_<season>.parquet
already exists (built by domains/basketball_nba/lineups/pbp_lineups.py, same
substitution-walk + box-score-starter-seed method already tested in
domains/basketball_nba/lineups/test_pbp_lineups.py). This module: (1)
independently re-validates the 5-on-floor invariant per game (quarantine,
don't trust the upstream `quality` string blindly), (2) resolves each
team_id's home/away side via player_boxscores.parquet, (3) joins stints to
sim2_possessions via pd.merge_asof on elapsed-seconds within
(game_id, period, team_id), (4) ledgers structural claims, (5, SPINE-3) fits
possession-count-shrunk offense/defense rates per lineup + per player on the
2024-25 DISCOVERY season only, with a lineup -> player-average -> team-mean
fallback ladder for spine_nba's v2 feature frame.

OUTPUT: data/omni/lineups/possession_lineups_<season>.parquet (2024-25, 2025-26)
  game_id, possession_key, off_team, def_team, off_lineup_ids, def_lineup_ids
  (lineup_ids = comma-joined sorted NBA player ids, per stints convention).

CLI: python -m scripts.platformkit.omni.lineup_possessions
Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_lineup_possessions.py -q
"""
from __future__ import annotations

import pathlib
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.omni import claims_ledger as cl

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
POSSESSIONS_PATH = REPO_ROOT / "data" / "cache" / "ingame" / "sim2_possessions.parquet"
BOXSCORES_PATH = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
SEASONS = ("2024-25", "2025-26")   # v1 built 2024-25 only; SPINE-3 adds 2025-26
FIT_SEASON = "2024-25"             # rating fits below use this season ONLY
K_SHRINK = 200.0  # ponytail: fixed prior-strength (~200 possessions, roughly
# 2-3 games of lineup floor time) shared by both lineup- and player-rate
# shrinkage -- a per-lineup/per-player empirical-Bayes constant, not tuned.


def _stints_path(season: str) -> pathlib.Path:
    return REPO_ROOT / "data" / "cache" / "team_system" / "lineups" / f"stints_{season.replace('-', '_')}.parquet"


def _out_path(season: str) -> pathlib.Path:
    return REPO_ROOT / "data" / "omni" / "lineups" / f"possession_lineups_{season.replace('-', '_')}.parquet"


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


def build_for_season(season: str, possessions_all: pd.DataFrame, box_all: pd.DataFrame
                     ) -> tuple[pd.DataFrame, dict, set, set, float]:
    """Build the possession-lineup store for one season. Returns
    (out_df, stats, valid_games, quarantined_games, stint_pass_rate)."""
    stints_df = pd.read_parquet(_stints_path(season))
    possessions_df = possessions_all[possessions_all["season"] == season].copy()
    box_df = box_all[box_all["season"] == season][["game_id", "player_id", "is_home"]].copy()
    box_df["is_home"] = box_df["is_home"].astype(bool)

    valid_games, quarantined_games, pass_rate = validate_stints(stints_df)
    stints_valid = stints_df[stints_df["game_id"].isin(valid_games)]
    possessions_valid = possessions_df[possessions_df["game_id"].isin(valid_games)]

    team_is_home = build_team_is_home(stints_valid, box_df)
    out_df, stats = join_possessions(possessions_valid, stints_valid, team_is_home)
    return out_df, stats, valid_games, quarantined_games, pass_rate


# ---------------------------------------------------------------------------
# SPINE-3: lineup/player rate fitting (discovery-season only) + fallback ladder
# ---------------------------------------------------------------------------

def _shrink(mean: float, n: float, prior: float) -> float:
    return (n * mean + K_SHRINK * prior) / (n + K_SHRINK)


def fit_team_rates(df: pd.DataFrame, team_col: str, points_col: str = "points") -> Dict[int, float]:
    """team_id -> mean points-per-possession, discovery-season fit."""
    return df.groupby(team_col)[points_col].mean().to_dict()


def fit_lineup_rates(df: pd.DataFrame, lineup_col: str, team_col: str,
                      points_col: str = "points") -> Tuple[Dict[str, float], Dict[int, float], float]:
    """lineup_ids -> possession-count-shrunk PPP, shrunk to the lineup's OWN
    team mean by possession count. Returns (lineup_rates, team_rates, league_mean)."""
    team_rates = fit_team_rates(df, team_col, points_col)
    league_mean = float(df[points_col].mean())
    grp = df.groupby([lineup_col, team_col])[points_col].agg(["mean", "count"])
    out: Dict[str, float] = {}
    for (lineup_ids, team), row in grp.iterrows():
        prior = team_rates.get(team, league_mean)
        out[lineup_ids] = _shrink(row["mean"], row["count"], prior)
    return out, team_rates, league_mean


def fit_player_rates(df: pd.DataFrame, lineup_col: str, team_col: str,
                      points_col: str = "points") -> Tuple[Dict[Tuple[str, int], float], Dict[int, float], float]:
    """(player_id, team_id) -> possession-count-shrunk PPP, "fit the same way"
    as fit_lineup_rates: expand each lineup's 5 comma-joined ids to long rows,
    shrink each player's mean to their team's mean by possession count."""
    ids = df[lineup_col].str.split(",")
    long_df = pd.DataFrame({
        "player_id": np.concatenate(ids.to_numpy()),
        "team": np.repeat(df[team_col].to_numpy(), ids.str.len().to_numpy()),
        "points": np.repeat(df[points_col].to_numpy(), ids.str.len().to_numpy()),
    })
    team_rates = fit_team_rates(long_df, "team", "points")
    league_mean = float(long_df["points"].mean())
    grp = long_df.groupby(["player_id", "team"])["points"].agg(["mean", "count"])
    out: Dict[Tuple[str, int], float] = {}
    for (pid, team), row in grp.iterrows():
        prior = team_rates.get(team, league_mean)
        out[(pid, team)] = _shrink(row["mean"], row["count"], prior)
    return out, team_rates, league_mean


def lookup_rate(lineup_ids: Optional[str], team: int,
                 lineup_table: Dict[str, float], player_table: Dict[Tuple[str, int], float],
                 team_rates: Dict[int, float], league_mean: float) -> Tuple[float, str]:
    """Fallback ladder: lineup hit -> mean of the 5 players' individual rates
    (team mean fills any one unseen player) -> team mean (lineup missing
    entirely, or all 5 players unseen). Returns (rate, tier)."""
    team_mean = team_rates.get(team, league_mean)
    if lineup_ids is None or (isinstance(lineup_ids, float) and pd.isna(lineup_ids)):
        return team_mean, "team"
    if lineup_ids in lineup_table:
        return lineup_table[lineup_ids], "lineup"
    pids = lineup_ids.split(",")
    known = [player_table.get((pid, team)) for pid in pids]
    if all(v is None for v in known):
        return team_mean, "team"
    filled = [v if v is not None else team_mean for v in known]
    return float(np.mean(filled)), "player"


def main() -> int:
    possessions_all = pd.read_parquet(POSSESSIONS_PATH)
    box_all = pd.read_parquet(BOXSCORES_PATH)
    claims = []
    for season in SEASONS:
        out_df, stats, valid_games, quarantined_games, pass_rate = build_for_season(
            season, possessions_all, box_all)
        out_path = _out_path(season)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_df.to_parquet(out_path, index=False)
        print(f"[{season}] stint_validation_pass_rate={pass_rate:.4f} "
              f"valid_games={len(valid_games)} quarantined_games={sorted(quarantined_games)}")
        print(f"[{season}] join_rate={stats['join_rate']:.4f} "
              f"n_matched={stats['n_matched']} n_total={stats['n_total_possessions']}")
        print(f"[{season}] wrote {len(out_df)} rows -> {out_path}")
        claims += [
            {"statement": (f"NBA possession-lineup store exists for {season}: "
                           f"{len(out_df)} possession-lineup rows across {out_df['game_id'].nunique()} games."),
             "type": "structural", "scope": {"sport": "nba", "seasons": [season]},
             "topic": "lineup_possession_store"},
            {"statement": (f"NBA lineup-stint validation pass rate {season}: "
                           f"{pass_rate:.4f} ({len(valid_games)}/{len(valid_games) + len(quarantined_games)} games clean)."),
             "type": "structural", "scope": {"sport": "nba", "seasons": [season]},
             "topic": "lineup_stint_validation"},
            {"statement": (f"NBA stint-to-possession join rate {season}: "
                           f"{stats['join_rate']:.4f} ({stats['n_matched']}/{stats['n_total_possessions']})."),
             "type": "structural", "scope": {"sport": "nba", "seasons": [season]},
             "topic": "lineup_possession_join"},
        ]
    added, _ = cl.add_claims_batch(claims)
    print(f"claims_added={added}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
