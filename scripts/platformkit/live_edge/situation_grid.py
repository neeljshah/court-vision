"""scripts.platformkit.live_edge.situation_grid -- B1 situation ontology as DATA.

Grid axes (possession-grain, from data/cache/ingame/sim2_possessions.parquet --
780,166 rows / 3,652 games, seasons 2023-24..2025-26; premise-checked
2026-07-14: no situation_grid/grid_sweep module or data/omni/live_edge/ tree
existed before this lane):

  margin_bucket    -- off_margin bucketed into 7 bands (down20plus..up20plus,
                       tied). IN-GAME.
  period_band      -- period x clock_start tercile (Q1..Q4 x early/mid/late;
                       period>4 collapses to "OT"). IN-GAME.
  pace_regime      -- game-level mean possession duration, tertile
                       (slow/med/fast), broadcast back to every possession in
                       that game. IN-GAME (only knowable once the game is
                       under way).
  rest_bucket      -- team-game rest days (b2b/rest1/rest2plus/unknown),
                       computed from the team-game calendar in
                       nba_player_box_rate__career_to_date_snapshot.parquet.
                       PREGAME-KNOWABLE (schedule is known before tip).
  blowout_flag     -- bool, |margin|>=25 anywhere, or |margin|>=20 in Q4+.
                       IN-GAME.
  close_late_flag  -- bool, "clutch": |margin|<=5 AND period>=4 AND
                       clock_start<=300. IN-GAME.
  foul_state       -- DATA-ABSENT. sim2_possessions carries no per-possession
                       team-foul count. data/cache/ingame/pbp_foul_states_
                       2024_25.parquet DOES have home_fouls/away_fouls/
                       foul_diff, but it keys on ESPN `event_id` at ~9
                       game-checkpoints per game (a different grain), with no
                       on-disk crosswalk to sim2_possessions' NBA `game_id`.
                       Axis is declared, held constant "DATA_ABSENT", never
                       grouped on. Upgrade path: build the event_id<->game_id
                       crosswalk, then re-derive per-possession foul counts
                       from the same PBP source pbp_foul_states was built
                       from.
  lineup_on_floor  -- off_lineup_ids/def_lineup_ids, joined from
                       data/omni/lineups/possession_lineups_<season>.parquet.
                       Covers 2024-25 and 2025-26 ONLY (2023-24 has no stint
                       store on disk); join keyed on (game_id, possession_key)
                       where possession_key is reconstructed identically to
                       lineup_possessions.join_possessions() (game_id +
                       per-game_id row-order cumcount -- invariant to which
                       OTHER games are present, so recomputing it on the full
                       sim2_possessions frame reproduces the stored key
                       exactly for any game the lineup store covers).

Grid CELLS are enumerated as DATA via groupby() over the actual possession
log -- distinct combinations that occur, never a synthetic full cross
product coded as branches.

Player-grain: DATA-ABSENT. sim2_possessions has no per-possession scorer/
player_id column (team-offense grain only); box-score stores are per-GAME
aggregates with no situational tag. No on-disk store lets a player stat be
conditioned on a situation cell -- see grid_sweep.py's module docstring for
the same caveat restated at the mining layer.

Reserve discipline: no per-possession date column exists to cut over
mid-season the way k_sweep_nba does, so the reserve unit here is a whole
SEASON: reserve = 2025-26, discovery = 2023-24 + 2024-25.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
POSSESSIONS_PATH = REPO_ROOT / "data" / "cache" / "ingame" / "sim2_possessions.parquet"
BOX_RATE_PATH = REPO_ROOT / "data" / "cache" / "intel_claims" / (
    "nba_player_box_rate__career_to_date_snapshot.parquet"
)
LINEUP_SEASONS = ("2024-25", "2025-26")

RESERVE_SEASON = "2025-26"

GROUP_COLS = ["margin_bucket", "period_band", "pace_regime", "rest_bucket",
              "blowout_flag", "close_late_flag"]

_MARGIN_LABELS = ["down20plus", "down10to19", "down1to9", "tied",
                   "up1to9", "up10to19", "up20plus"]


def load_possessions(source=None) -> pd.DataFrame:
    if isinstance(source, pd.DataFrame):
        return source.copy()
    return pd.read_parquet(source if source is not None else POSSESSIONS_PATH)


def load_box_rate(source=None) -> pd.DataFrame:
    cols = ["game_id", "date", "team", "is_home"]
    if isinstance(source, pd.DataFrame):
        return source[cols].copy()
    return pd.read_parquet(source if source is not None else BOX_RATE_PATH, columns=cols)


def split_discovery_reserve(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    return df[df["season"] != RESERVE_SEASON].copy(), df[df["season"] == RESERVE_SEASON].copy()


def bucket_margin(margin: pd.Series) -> pd.Series:
    m = margin.to_numpy()
    conditions = [m <= -20, (m > -20) & (m <= -10), (m > -10) & (m < 0), m == 0,
                  (m > 0) & (m < 10), (m >= 10) & (m < 20), m >= 20]
    return pd.Series(np.select(conditions, _MARGIN_LABELS, default="unknown"),
                      index=margin.index, dtype="object")


def bucket_period_clock(period: pd.Series, clock_start: pd.Series) -> pd.Series:
    reg = period <= 4
    band = np.select([clock_start > 480, clock_start > 180], ["early", "mid"], default="late")
    label = "Q" + period.astype(str) + "_" + band
    return pd.Series(np.where(reg, label, "OT"), index=period.index, dtype="object")


def pace_regime(df: pd.DataFrame) -> pd.Series:
    game_mean = df.groupby("game_id")["duration"].transform("mean")
    try:
        return pd.qcut(game_mean, 3, labels=["slow", "med", "fast"], duplicates="drop").astype("object")
    except ValueError:
        return pd.Series("med", index=df.index, dtype="object")


def blowout_flag(margin: pd.Series, period: pd.Series) -> pd.Series:
    absm = margin.abs()
    return (absm >= 25) | ((period >= 4) & (absm >= 20))


def close_late_flag(margin: pd.Series, period: pd.Series, clock_start: pd.Series) -> pd.Series:
    return (margin.abs() <= 5) & (period >= 4) & (clock_start <= 300)


def _team_map(box_df: pd.DataFrame) -> pd.DataFrame:
    """(game_id, is_home) -> team, one row per side per game."""
    return box_df.drop_duplicates(["game_id", "is_home"])[["game_id", "is_home", "team"]]


def _rest_lookup(box_df: pd.DataFrame) -> pd.DataFrame:
    """(game_id, team) -> rest_bucket, from each team's own game-date calendar."""
    cal = box_df.drop_duplicates(["team", "game_id", "date"]).sort_values(["team", "date"])
    cal["rest_days"] = cal.groupby("team")["date"].diff().dt.days - 1
    bins = [-1, 0, 1, 999]
    cal["rest_bucket"] = pd.cut(cal["rest_days"], bins=bins,
                                 labels=["b2b", "rest1", "rest2plus"]).astype("object")
    cal["rest_bucket"] = cal["rest_bucket"].fillna("unknown")
    return cal[["game_id", "team", "rest_bucket"]]


def attach_team_and_rest(df: pd.DataFrame, box_df: pd.DataFrame) -> pd.DataFrame:
    tm = _team_map(box_df)
    home = tm[tm["is_home"] == 1.0][["game_id", "team"]].rename(columns={"team": "home_team"})
    away = tm[tm["is_home"] == 0.0][["game_id", "team"]].rename(columns={"team": "away_team"})
    out = df.merge(home, on="game_id", how="left").merge(away, on="game_id", how="left")
    out["off_team"] = out["home_team"].where(out["off_is_home"], out["away_team"])
    out["def_team"] = out["away_team"].where(out["off_is_home"], out["home_team"])
    rest = _rest_lookup(box_df).rename(columns={"team": "off_team"})
    out = out.merge(rest, on=["game_id", "off_team"], how="left")
    out["rest_bucket"] = out["rest_bucket"].fillna("unknown")
    return out.drop(columns=["home_team", "away_team"])


def attach_possession_key(df: pd.DataFrame) -> pd.DataFrame:
    """Reconstruct possession_key identically to lineup_possessions.join_
    possessions(): per game_id row-order cumcount. Safe to compute globally --
    a game's own cumcount doesn't depend on which OTHER games are present."""
    out = df.copy()
    out["possession_key"] = out["game_id"].astype(str) + ":" + out.groupby("game_id").cumcount().astype(str)
    return out


def attach_lineups(df: pd.DataFrame, lineup_dir=None) -> pd.DataFrame:
    """Left-join off_lineup_ids/def_lineup_ids for LINEUP_SEASONS rows only;
    other seasons get NaN (lineup_available=False)."""
    base = pathlib.Path(lineup_dir) if lineup_dir is not None else REPO_ROOT / "data" / "omni" / "lineups"
    out = attach_possession_key(df)
    out["off_lineup_ids"] = pd.NA
    out["def_lineup_ids"] = pd.NA
    for season in LINEUP_SEASONS:
        path = base / f"possession_lineups_{season.replace('-', '_')}.parquet"
        if not path.is_file():
            continue
        lu = pd.read_parquet(path, columns=["game_id", "possession_key", "off_lineup_ids", "def_lineup_ids"])
        mask = out["season"] == season
        merged = out.loc[mask, ["game_id", "possession_key"]].merge(
            lu, on=["game_id", "possession_key"], how="left")
        out.loc[mask, "off_lineup_ids"] = merged["off_lineup_ids"].to_numpy()
        out.loc[mask, "def_lineup_ids"] = merged["def_lineup_ids"].to_numpy()
    out["lineup_available"] = out["off_lineup_ids"].notna()
    return out


def tag_situations(df: pd.DataFrame, box_df: pd.DataFrame, with_lineups: bool = True) -> pd.DataFrame:
    """Attach every grid axis (foul_state held constant DATA_ABSENT) to a raw
    sim2_possessions-shaped frame. Returns a new, tagged DataFrame."""
    out = attach_team_and_rest(df, box_df)
    out["margin_bucket"] = bucket_margin(out["off_margin"])
    out["period_band"] = bucket_period_clock(out["period"], out["clock_start"])
    out["pace_regime"] = pace_regime(out)
    out["blowout_flag"] = blowout_flag(out["off_margin"], out["period"])
    out["close_late_flag"] = close_late_flag(out["off_margin"], out["period"], out["clock_start"])
    out["foul_state"] = "DATA_ABSENT"
    if with_lineups:
        out = attach_lineups(out)
    return out


def enumerate_cells(tagged_df: pd.DataFrame, group_cols=None) -> pd.DataFrame:
    """Grid cells AS DATA: distinct observed combinations of *group_cols* with
    counts + mean/var of `points` -- the raw material grid_sweep.py tests."""
    cols = group_cols or GROUP_COLS
    grp = tagged_df.groupby(cols, observed=True)["points"].agg(n="size", mean="mean", var="var")
    return grp.reset_index()


__all__ = [
    "REPO_ROOT", "POSSESSIONS_PATH", "BOX_RATE_PATH", "LINEUP_SEASONS", "RESERVE_SEASON",
    "GROUP_COLS", "load_possessions", "load_box_rate", "split_discovery_reserve",
    "bucket_margin", "bucket_period_clock", "pace_regime", "blowout_flag", "close_late_flag",
    "attach_team_and_rest", "attach_possession_key", "attach_lineups", "tag_situations",
    "enumerate_cells",
]
