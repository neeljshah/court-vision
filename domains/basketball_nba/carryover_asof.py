"""domains.basketball_nba.carryover_asof -- LEAK-FREE cross-game CARRYOVER
as-of panel: yesterday's realized load (heavy-minutes fatigue + rest days).

Distinct from the sibling season-to-date-mean families (asof_box_extra.py,
boxdetail_asof.py): this is LAG-1 (the team's single immediately-PRIOR game),
not an expanding/L10 mean -- the hypothesis under test is CARRYOVER from the
last game specifically, not a rolling form level.

Two attrs, both team-game diffs (home - away):
  heavy_min_load_asof -- prior game's total minutes logged by "heavy usage"
      players (>=HEAVY_MIN_THRESHOLD min that game) -- a fatigue-carryover proxy.
  rest_days_asof       -- days since the team's prior game (b2b/rest signal).

Reset per (team, season): an offseason gap carries no fatigue signal, so the
first game of each team-season is NaN, never bled in from the prior season.

Source: data/domains/basketball_nba/player_boxscores.parquet (77.7k player-
game rows spanning 2023-24..2025-26, `min` column -- W59 sidecar, same source
asof_box_extra.py already reclaims for dreb/fg3m/stl/blk).

Output -> data/domains/basketball_nba/carryover_asof.parquet keyed game_id.
Feeds the interaction_factory's nba_carryover_self_cross template (family=
carryover_asof) -- see scripts/platformkit/interaction_factory/builders_carryover.py.
Expected gate verdict: NULL/small -- b2b/rest is already heavily priced by the
market; a REJECT/NULL here is a SUCCESS, not a failure. No edge ever claimed.

PRIVATE: data/domains/basketball_nba/ is never tracked. No src.*/kernel.*/
other-domain imports (falsifier F5 compliance). ASCII only. <=300 LOC.
CLI: python -m domains.basketball_nba.carryover_asof
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_IN = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
_DEFAULT_OUT = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "carryover_asof.parquet"

HEAVY_MIN_THRESHOLD = 30.0  # minutes played THIS game to count as "heavy usage"

_SIDE_COLS = ["heavy_min_load_asof", "rest_days_asof", "n_prior"]
OUTPUT_COLS = [
    "game_id", "season",
    "home_heavy_min_load_asof", "away_heavy_min_load_asof", "heavy_min_load_diff_asof",
    "home_rest_days_asof", "away_rest_days_asof", "rest_days_diff_asof",
    "home_n_prior", "away_n_prior",
]


def _aggregate_team_games(player_box: pd.DataFrame) -> pd.DataFrame:
    """Players -> one row per (game_id, team): heavy-usage minute load THIS game."""
    pb = player_box.copy()
    pb["game_id"] = pb["game_id"].astype(str)
    pb["team"] = pb["team"].astype(str)
    pb["min"] = pd.to_numeric(pb.get("min"), errors="coerce").fillna(0.0)
    pb["_heavy_min"] = pb["min"].where(pb["min"] >= HEAVY_MIN_THRESHOLD, 0.0)
    tg = pb.groupby(["game_id", "team"], as_index=False, sort=False).agg(
        heavy_min_load=("_heavy_min", "sum"),
        date=("date", "first"), season=("season", "first"), is_home=("is_home", "first"),
    )
    return tg


def _walk_forward_lag1(tg: pd.DataFrame) -> pd.DataFrame:
    """LAG-1 carryover per (team, season): this game's feature = the team's
    IMMEDIATELY PRIOR game's heavy_min_load + days since that prior game.
    Grouped by (team, season) so a season boundary always resets to NaN --
    never a value carried in from an offseason gap."""
    tg = tg.copy()
    tg["date"] = pd.to_datetime(tg["date"])
    tg = tg.sort_values(["team", "season", "date", "game_id"], kind="mergesort").reset_index(drop=True)
    g = tg.groupby(["team", "season"], sort=False)
    tg["heavy_min_load_asof"] = g["heavy_min_load"].shift(1)
    prior_date = g["date"].shift(1)
    tg["rest_days_asof"] = (tg["date"] - prior_date).dt.days.astype(float)
    tg["n_prior"] = g.cumcount()
    return tg


def _pivot_to_games(tg: pd.DataFrame) -> pd.DataFrame:
    """Two team-rows per game -> one game_id row with home/away/diff columns."""
    is_home = tg["is_home"].apply(lambda v: bool(v) if pd.notna(v) else False)
    home, away = tg[is_home], tg[~is_home]

    h = home[["game_id", "season"] + _SIDE_COLS].rename(columns={c: f"home_{c}" for c in _SIDE_COLS})
    a = away[["game_id"] + _SIDE_COLS].rename(columns={c: f"away_{c}" for c in _SIDE_COLS})
    out = h.merge(a, on="game_id", how="outer")

    out["heavy_min_load_diff_asof"] = out["home_heavy_min_load_asof"] - out["away_heavy_min_load_asof"]
    out["rest_days_diff_asof"] = out["home_rest_days_asof"] - out["away_rest_days_asof"]
    for side in ("home_n_prior", "away_n_prior"):
        out[side] = pd.to_numeric(out[side], errors="coerce").fillna(0).astype("int64")

    out = out.reindex(columns=OUTPUT_COLS)
    return out.sort_values("game_id", kind="mergesort").reset_index(drop=True)


def build_carryover_asof(
    player_box: Optional[pd.DataFrame] = None,
    out_path: Optional[str] = None,
) -> Path:
    """Build the leak-free LAG-1 carryover as-of parquet (heavy_min_load, rest_days).

    Parameters
    ----------
    player_box: player_boxscores.parquet-shaped DataFrame (game_id, date, season,
        team, opp, is_home, min). If None, reads the default on-disk parquet.
    out_path: output parquet path. If None, uses the default carryover_asof.parquet.

    Returns
    -------
    Path written (one row per game_id; see OUTPUT_COLS). NaN as-of values on a
    team's first game of a season (n_prior == 0).
    """
    dest = Path(out_path) if out_path is not None else _DEFAULT_OUT
    if player_box is None:
        if not _DEFAULT_IN.exists():
            raise FileNotFoundError(f"player_boxscores.parquet not found at {_DEFAULT_IN}.")
        player_box = pd.read_parquet(_DEFAULT_IN)

    if len(player_box) == 0:
        out = pd.DataFrame(columns=OUTPUT_COLS)
    else:
        tg = _aggregate_team_games(player_box)
        tg = _walk_forward_lag1(tg)
        out = _pivot_to_games(tg)

    dest.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(str(dest), index=False)
    return dest


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description="player_boxscores.parquet -> leak-free LAG-1 carryover as-of "
                    "(heavy_min_load, rest_days; reset per team-season)")
    ap.add_argument("--in", dest="inp", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    _pb = pd.read_parquet(args.inp) if args.inp else None
    path = build_carryover_asof(player_box=_pb, out_path=args.out)
    df = pd.read_parquet(str(path))
    print("LEAK-FREE cross-game carryover as-of (LAG-1 heavy_min_load + rest_days; per team-season reset).")
    print("NOT a market edge. b2b/rest is heavily priced -- expect NULL/small. Gate decides honestly next.")
    print(f"Wrote {path}  ({len(df)} game rows)")
    if len(df):
        print(df.dropna(subset=["heavy_min_load_diff_asof"]).head(3).to_string())
