"""Leak-free AS-OF opponent-defensive-strength helper (context-shooting axis 1).

MISSION: every player shooting number is context-blind unless split by the
strength of the defense faced. This module computes, for every player-game
row, how good that game's OPPONENT's defense had been AS OF that date --
using strictly PRIOR games only (no same-date, no future) -- then classifies
each row into a tough/mid/weak-defense tercile so a downstream claims
producer can split a player's TS%/FG3% by matchup difficulty and compute a
defense-adjusted TS% (actual minus opponent-quality-weighted expected).

PREREGISTERED FLOORS (declared BEFORE any scoring code below):
  MIN_PRIOR_GAMES   = 5   -- a team's def_allowed_asof is null until it has
                             played >=5 prior games (reliability floor on the
                             opponent-strength signal itself).
  MIN_GAMES         = 20  -- player-season qualifying floor (same standard as
                             quality_indices.QUALIFY_MIN_GAMES).
  MIN_FGA           = 200 -- player-season qualifying floor (same standard as
                             quality_indices.QUALIFY_MIN_FGA).
  MIN_GAMES_TERCILE = 5   -- min games in EACH of the tough/weak tercile
                             groups for a tercile-gap claim to consider a
                             player.
  MIN_FG3A_TERCILE  = 15  -- min 3PA in EACH of the tough/weak tercile groups
                             for the FG3%-gap claim.

LEAK-FREE DESIGN: def_allowed_asof for team T's game G = the mean TS% T
allowed in ALL of T's games strictly before G's date (pandas
`.expanding().mean().shift(1)`, sorted by date -- shift(1) drops the current
row from its own expanding window). This is computed across ALL seasons in
one continuous timeline (not reset at each season boundary) -- a team's
defensive identity does not reset on Oct 1, and early-season dates in a new
season still get a meaningful opponent-strength read from the tail of the
prior season. This is opponent-side information, never the target player's
own future, so it introduces no leak into that player's own forward outcome
-- documented here rather than silently assumed.

Tercile cutpoints (pandas.qcut, 3 bins) are computed ONCE globally across all
non-null player-game rows (not resliced per season) -- a single, stable
definition of "tough" vs "weak" defense for the whole corpus.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from domains.basketball_nba.quality_indices import QUALIFY_MIN_FGA, QUALIFY_MIN_GAMES

REPO_ROOT = Path(__file__).resolve().parents[3]
BOXSCORE_PATH = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"

RAW_COLUMNS = ["game_id", "date", "season", "team", "opp", "player_id", "player_name",
               "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "pts"]

MIN_PRIOR_GAMES = 5
MIN_GAMES = QUALIFY_MIN_GAMES
MIN_FGA = QUALIFY_MIN_FGA
MIN_GAMES_TERCILE = 5
MIN_FG3A_TERCILE = 15


def load_raw_boxscores(path: Path | str = BOXSCORE_PATH) -> pd.DataFrame:
    df = pd.read_parquet(path)
    missing = [c for c in RAW_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"player_boxscores.parquet missing columns: {missing}")
    df = df[RAW_COLUMNS].copy()
    df["date"] = pd.to_datetime(df["date"])
    return df


def name_lookup(box: pd.DataFrame) -> dict[int, str]:
    """player_id -> most-recently-seen player_name, for stores (atlas files)
    that carry player_id only."""
    last = box.sort_values(["player_id", "date"]).groupby("player_id")["player_name"].last()
    return {int(pid): str(name) for pid, name in last.items()}


def _team_game_table(box: pd.DataFrame) -> pd.DataFrame:
    """One row per (game_id, team): that team's OWN box totals in that game
    -- which is exactly what the opposing team ALLOWED."""
    g = box.groupby(["game_id", "date", "season", "team"], as_index=False).agg(
        pts=("pts", "sum"), fga=("fga", "sum"), fta=("fta", "sum"),
        fg3m=("fg3m", "sum"), fg3a=("fg3a", "sum"),
    )
    g["ts_pct"] = g["pts"] / (2 * (g["fga"] + 0.44 * g["fta"])).replace(0, pd.NA)
    return g


def _opp_def_strength_asof(team_game: pd.DataFrame, min_prior_games: int = MIN_PRIOR_GAMES) -> pd.DataFrame:
    """Per (game_id, team): def_allowed_asof = mean TS% that team allowed in
    ALL games strictly before this one (shift(1) on the expanding mean, so
    the current game never contributes to its own opponent-strength read)."""
    tg = team_game.sort_values(["team", "date", "game_id"]).copy()
    grp = tg.groupby("team")["ts_pct"]
    tg["def_allowed_asof"] = grp.transform(lambda s: s.expanding().mean().shift(1))
    tg["prior_games"] = grp.cumcount()
    tg.loc[tg["prior_games"] < min_prior_games, "def_allowed_asof"] = pd.NA
    return tg[["game_id", "team", "def_allowed_asof", "prior_games"]]


def attach_opp_strength(box: pd.DataFrame) -> pd.DataFrame:
    """Every player-game row + its opponent's def_allowed_asof/prior_games,
    joined on (game_id, opp==defensive team)."""
    team_game = _team_game_table(box)
    opp_strength = _opp_def_strength_asof(team_game)
    opp_strength = opp_strength.rename(
        columns={"team": "opp", "def_allowed_asof": "opp_def_strength_asof", "prior_games": "opp_prior_games"}
    )
    return box.merge(opp_strength, on=["game_id", "opp"], how="left")


def assign_tercile(rows: pd.DataFrame) -> pd.DataFrame:
    """defense_tier in {"tough","mid","weak"} from a global qcut(3) on
    opp_def_strength_asof (low allowed-TS% = tough D; high = weak D). Rows
    with a null opp_def_strength_asof (below MIN_PRIOR_GAMES) stay null."""
    out = rows.copy()
    out["defense_tier"] = pd.Series(pd.NA, index=out.index, dtype="object")
    valid = out["opp_def_strength_asof"].notna()
    if int(valid.sum()) >= 3:
        # duplicates="drop" can collapse bin count below 3 on low-cardinality
        # data (e.g. a small synthetic fixture); derive labels from the
        # resulting bin COUNT rather than a fixed 3-label list, so a
        # collapsed cut never raises instead of degrading gracefully.
        cats = pd.qcut(out.loc[valid, "opp_def_strength_asof"], 3, duplicates="drop")
        n_bins = len(cats.cat.categories)
        codes = cats.cat.codes
        if n_bins >= 3:
            label_map = {0: "tough", n_bins - 1: "weak"}
            mapped = codes.map(lambda c: label_map.get(c, "mid"))
        elif n_bins == 2:
            mapped = codes.map({0: "tough", 1: "weak"})
        else:
            mapped = codes.map({0: "mid"})
        out.loc[valid, "defense_tier"] = mapped.astype(str)
    return out


def build_player_game_rows(box: pd.DataFrame | None = None) -> pd.DataFrame:
    """Entry point: raw player-game rows with opp_def_strength_asof +
    defense_tier attached, leak-free by construction (see module docstring)."""
    if box is None:
        box = load_raw_boxscores()
    rows = attach_opp_strength(box)
    return assign_tercile(rows)
