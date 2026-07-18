"""Player shooting intelligence -- computed strictly from raw per-game rows.

DATA SOURCE (read-only, never rebuilt here):
    data/domains/basketball_nba/player_boxscores.parquet
    columns used: game_id, date, season, player_id, player_name, min,
    fgm, fga, fg3m, fg3a, ftm, fta, pts.
Coverage on disk as of 2026-07-04 (verified by inventory, not assumed):
    season '2024-25': 26186 player-game rows, 2024-10-22 .. 2025-04-13 (full season).
    season '2025-26': 1630 player-game rows, 2025-10-21 .. 2026-01-19 (partial,
        in-progress season -- 74 games worth of team-slates ingested so far).
No other season is present on disk. Any "current form" claim about 2025-26 is
therefore a PARTIAL-SEASON claim and must say so.

PRE-DECLARED RANKING CRITERIA (fixed before any computation ran):
  1. PRIMARY ("best shooter") composite = weighted blend of the three efficiency
     legs, each z-free (no in-sample standardization -- literal weighted average
     of rates so the number stays human-checkable):
         composite = 0.55 * TS%  + 0.30 * eFG%  + 0.15 * FT%
     Rationale: TS% is the best single overall-efficiency proxy (folds in 3s +
     FTs), eFG% isolates field-goal shot-making, FT% is a pure touch/skill
     signal with a smaller weight because it is a smaller share of a "shooter"
     evaluation. Weights are declared, not fit -- no target leakage possible.
  2. Floors (sample-size gates), applied BEFORE ranking:
         min_games   = 20   (per window)
         min_fga_pg  = 5.0  (avg FGA/game -- excludes garbage-time/rare shooters)
         min_fg3a_pg = 1.0  (avg 3PA/game -- excludes non-shooters from the
                              "best shooter" conversation entirely)
     Any player below ANY floor is EXCLUDED from the composite ranking and
     counted in n_excluded_below_floor. They may still appear in single-metric
     tables if they clear that table's own floor (see below).
  3. Single-metric rankings (3P%, TS%, eFG%) are ALSO emitted separately, each
     with its own stated floor, so the composite is never a black box:
         3P%:  min_fg3a_pg = 4.0  (real high-volume 3-point shooters)
         TS%:  min_fga_pg  = 5.0
         eFG%: min_fga_pg  = 5.0
  4. Windows: 'season_2024-25' (full, most reliable), 'season_2025-26'
     (partial -- fewer games, wider variance, LABELLED as partial in every
     output), and 'last_20' (recency-weighted current form = most recent 20
     games played by that player across the two seasons on disk, equally
     weighted, not exponentially decayed -- kept mechanical/transparent).
  5. direction = desc for every metric here (higher is better).

Zero numbers in this module come from anything except the parquet rows loaded
below. No player is added, renamed, or estimated from model memory.
"""
from __future__ import annotations

import pandas as pd

BOXSCORE_PATH = "data/domains/basketball_nba/player_boxscores.parquet"

# ---- declared floors (see module docstring for rationale) -----------------
MIN_GAMES_COMPOSITE = 20
MIN_FGA_PG_COMPOSITE = 5.0
MIN_FG3A_PG_COMPOSITE = 1.0

MIN_FG3A_PG_3PT_TABLE = 4.0
MIN_FGA_PG_EFF_TABLE = 5.0
# per-game RATE floors alone let a 1-game sample qualify (5 fga in one game
# passes fga_pg>=5.0); single-metric tables now also require the same games
# floor the composite always declared, and it is DECLARED in min_sample so
# the validator enforces the identical thing.
MIN_GAMES_SINGLE_METRIC = MIN_GAMES_COMPOSITE

COMPOSITE_WEIGHTS = {"ts_pct": 0.55, "efg_pct": 0.30, "ft_pct": 0.15}

LAST_N_GAMES = 20


def load_boxscores(path: str = BOXSCORE_PATH) -> pd.DataFrame:
    """Load raw per-player-per-game rows. Read-only substrate, no mutation."""
    df = pd.read_parquet(path)
    needed = [
        "game_id", "date", "season", "player_id", "player_name",
        "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "pts",
    ]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise ValueError(f"player_boxscores.parquet missing columns: {missing}")
    return df[needed].copy()


def _aggregate(rows: pd.DataFrame) -> pd.DataFrame:
    """Sum raw box counts per player over the given row-set, then derive rates.

    All rate formulas are the standard, machine-checkable NBA definitions:
        eFG%  = (FGM + 0.5*FG3M) / FGA
        TS%   = PTS / (2 * (FGA + 0.44*FTA))
        FT%   = FTM / FTA
        3P%   = FG3M / FG3A
    """
    # group_by player_id ONLY -- the claims contract declares aggregate.group_by
    # = "player_id" and the independent validator recomputes on that key alone.
    # Grouping by (player_id, player_name) here silently SPLIT a player whose
    # name appears under two spellings in the parquet (e.g. with/without
    # diacritics) into separate rows, letting a 1-game splinter pass the
    # per-game rate floors and top a ranking the validator then MISMATCHed.
    g = rows.groupby("player_id", as_index=False).agg(
        player_name=("player_name", "last"),
        games=("game_id", "nunique"),
        fgm=("fgm", "sum"),
        fga=("fga", "sum"),
        fg3m=("fg3m", "sum"),
        fg3a=("fg3a", "sum"),
        ftm=("ftm", "sum"),
        fta=("fta", "sum"),
        pts=("pts", "sum"),
    )
    g["fga_pg"] = g["fga"] / g["games"]
    g["fg3a_pg"] = g["fg3a"] / g["games"]
    g["efg_pct"] = (g["fgm"] + 0.5 * g["fg3m"]) / g["fga"].replace(0, pd.NA)
    g["ts_pct"] = g["pts"] / (2 * (g["fga"] + 0.44 * g["fta"])).replace(0, pd.NA)
    g["ft_pct"] = g["ftm"] / g["fta"].replace(0, pd.NA)
    g["fg3_pct"] = g["fg3m"] / g["fg3a"].replace(0, pd.NA)
    g["composite"] = (
        COMPOSITE_WEIGHTS["ts_pct"] * g["ts_pct"]
        + COMPOSITE_WEIGHTS["efg_pct"] * g["efg_pct"]
        + COMPOSITE_WEIGHTS["ft_pct"] * g["ft_pct"]
    )
    return g


def window_rows(df: pd.DataFrame, window: str) -> pd.DataFrame:
    """Slice raw rows for a declared window: 'season_YYYY-YY' or 'last_20'."""
    if window == "last_20":
        # recency-weighted current form: most recent LAST_N_GAMES *games played*
        # per player, taken from the full multi-season row-set.
        out = (
            df.sort_values("date")
            .groupby("player_id", group_keys=False)
            .tail(LAST_N_GAMES)
        )
        return out
    if window.startswith("season_"):
        season = window[len("season_"):]
        return df[df["season"] == season]
    raise ValueError(f"unknown window: {window}")


def compute_window_table(df: pd.DataFrame, window: str) -> pd.DataFrame:
    """Aggregate + derive rate stats for one declared window."""
    rows = window_rows(df, window)
    return _aggregate(rows)


def rank_composite(table: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Apply composite floors, return (ranked_survivors, n_excluded_below_floor)."""
    floor_mask = (
        (table["games"] >= MIN_GAMES_COMPOSITE)
        & (table["fga_pg"] >= MIN_FGA_PG_COMPOSITE)
        & (table["fg3a_pg"] >= MIN_FG3A_PG_COMPOSITE)
    )
    survivors = table[floor_mask].copy()
    excluded = int((~floor_mask).sum())
    survivors = survivors.sort_values("composite", ascending=False).reset_index(drop=True)
    return survivors, excluded


def rank_single_metric(table: pd.DataFrame, metric: str) -> tuple[pd.DataFrame, int]:
    """Apply that metric's declared floor, return (ranked_survivors, n_excluded)."""
    if metric == "fg3_pct":
        mask = table["fg3a_pg"] >= MIN_FG3A_PG_3PT_TABLE
    elif metric in ("ts_pct", "efg_pct"):
        mask = table["fga_pg"] >= MIN_FGA_PG_EFF_TABLE
    else:
        raise ValueError(f"unsupported single metric: {metric}")
    mask = mask & (table["games"] >= MIN_GAMES_SINGLE_METRIC)
    survivors = table[mask].copy()
    excluded = int((~mask).sum())
    survivors = survivors.sort_values(metric, ascending=False).reset_index(drop=True)
    return survivors, excluded
