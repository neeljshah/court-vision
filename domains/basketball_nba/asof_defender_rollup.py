"""domains.basketball_nba.asof_defender_rollup -- LEAK-FREE team roll-up of the
already-as-of per-defender matchup layer.

DATA RECLAIM (ONDISK_RECLAIM_TARGETS.md row #11): the ``_states`` file built by
``ingest_defender_matchup_states.py`` (37,395 defender-game rows,
``data/domains/basketball_nba/defender_matchup_states.parquet``) is ALREADY as-of
(snapshot-before-update, shift1 prior-N per defender) but is PLAYER-level. Per the
audit row: "needs roll-up to team pre-game." This module performs ONLY that roll-up
-- no new aggregation of raw data, no new leak surface: it averages already-leak-free
``def_priorN_*_asof`` values across a team's defenders fielded in a given game, then
pivots vs ``games.parquet`` home/away into ``home_/away_/diff_*_asof`` columns
matching ``asof_team_adv.py``'s convention exactly.

LEAK-NOTE (inherited, not re-derived):
- Every ``def_priorN_*_asof`` value going into the mean is ALREADY a strict shift1
  over that defender's PRIOR games (built by ingest_defender_matchup_states.py); this
  module reads them as fixed inputs and takes a same-game cross-sectional mean across
  defenders -- a pure aggregation of already-leak-free values, so no row can depend on
  its own game's realized outcome.
- Defenders with ``def_n_prior == 0`` (their first tracked matchup; NaN as-of) are
  EXCLUDED from the mean (their as-of value carries no signal, not a false zero).
- ``realized_*`` diagnostic columns from the source file are NEVER read here -- they
  are the label surface, not usable as a feature (mirrors the source module's own
  invariant).
- home/away side + chronological order come from ``games.parquet`` (authoritative
  date/home/away), never any per-row string on the defender file, matching
  ``asof_team_adv.py``'s ``_attach_date`` discipline.

Input ``defender_matchup_states`` columns consumed:
  game_id, def_team_tricode, def_priorN_fg_pct_allowed_asof,
  def_priorN_fg3_pct_allowed_asof, def_priorN_pts_allowed_per36_asof,
  def_priorN_blocks_per_game_asof, def_priorN_switches_per_game_asof,
  def_priorN_matchup_min_asof, def_n_prior.
Input ``games`` columns consumed: game_id, date, home_team, away_team.

Output -> ``data/domains/basketball_nba/asof_defender_rollup.parquet`` keyed game_id:
  game_id,
  home_def_fg_pct_allowed_asof, away_def_fg_pct_allowed_asof, def_fg_pct_allowed_diff_asof,
  home_def_fg3_pct_allowed_asof, away_def_fg3_pct_allowed_asof, def_fg3_pct_allowed_diff_asof,
  home_def_pts_allowed_per36_asof, away_def_pts_allowed_per36_asof, def_pts_allowed_per36_diff_asof,
  home_def_blocks_per_game_asof, away_def_blocks_per_game_asof, def_blocks_per_game_diff_asof,
  home_def_switches_per_game_asof, away_def_switches_per_game_asof, def_switches_per_game_diff_asof,
  home_def_matchup_min_asof, away_def_matchup_min_asof, def_matchup_min_diff_asof,
  home_n_prior, away_n_prior  -- support count = number of that side's defenders whose
  as-of value was non-NaN and folded into the mean (the gate's coverage floor).
  diff_asof = home - away throughout.

HONEST EXPECTED VERDICT: likely REJECT for the close (same prior as every sibling
reclaim dim -- efficient market). A truthfully-reported REJECT is a SUCCESS. NO $
field anywhere; DATA RECLAIM only -- this module does not fit or gate anything.

PRIVATE: ``data/domains/basketball_nba/`` is never tracked. F5: no domains.mlb /
domains.tennis / domains.soccer / src.* / kernel.* imports. <=300 LOC, ASCII stdout.

CLI: python -m domains.basketball_nba.asof_defender_rollup
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_IN = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "defender_matchup_states.parquet"
_DEFAULT_GAMES = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "games.parquet"
_DEFAULT_OUT = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "asof_defender_rollup.parquet"

# Per-defender as-of columns (already leak-free) -> the team-level stat name they roll up to.
_STAT_MAP: Dict[str, str] = {
    "def_priorN_fg_pct_allowed_asof": "def_fg_pct_allowed",
    "def_priorN_fg3_pct_allowed_asof": "def_fg3_pct_allowed",
    "def_priorN_pts_allowed_per36_asof": "def_pts_allowed_per36",
    "def_priorN_blocks_per_game_asof": "def_blocks_per_game",
    "def_priorN_switches_per_game_asof": "def_switches_per_game",
    "def_priorN_matchup_min_asof": "def_matchup_min",
}
_STATS = tuple(_STAT_MAP.values())

_TRIPLES: List[str] = []
for _s in _STATS:
    _TRIPLES.extend([f"home_{_s}_asof", f"away_{_s}_asof", f"{_s}_diff_asof"])
OUTPUT_COLS = ("game_id",) + tuple(_TRIPLES) + ("home_n_prior", "away_n_prior")


def _team_game_means(defenders: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional mean of each already-as-of stat across a team's fielded
    defenders in a game, EXCLUDING defenders whose value is NaN (def_n_prior == 0).

    One output row per (game_id, def_team_tricode). ``n_prior`` = count of defenders
    whose as-of value was folded into the mean (0 if the whole side lacked coverage,
    e.g. every fielded defender was in their first tracked matchup).
    """
    df = defenders.copy()
    df["game_id"] = df["game_id"].astype(str)
    df["def_team_tricode"] = df["def_team_tricode"].astype(str)

    src_cols = list(_STAT_MAP.keys())
    grouped = df.groupby(["game_id", "def_team_tricode"], sort=False)[src_cols].mean()
    grouped = grouped.rename(columns=_STAT_MAP).reset_index()

    n_prior = (
        df[src_cols].notna().any(axis=1).astype(int)
        .groupby([df["game_id"], df["def_team_tricode"]], sort=False)
        .sum()
        .rename("n_prior")
        .reset_index()
    )
    out = grouped.merge(n_prior, on=["game_id", "def_team_tricode"], how="left")
    out["n_prior"] = out["n_prior"].fillna(0).astype("int64")
    return out


def _attach_side(team_game: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """Join games.parquet's authoritative home/away label onto each team-game row.

    Rows whose game_id is absent from games.parquet are dropped (no shared date/side
    axis to place them on), matching asof_team_adv.py's join discipline.
    """
    tg = team_game.copy()
    g = games[["game_id", "home_team", "away_team"]].copy()
    g["game_id"] = g["game_id"].astype(str)
    merged = tg.merge(g, on="game_id", how="inner")
    merged["is_home"] = merged["def_team_tricode"] == merged["home_team"]
    return merged


def _pivot_to_games(tg: pd.DataFrame) -> pd.DataFrame:
    """Two team-rows per game -> one game_id row with home/away/diff columns."""
    home = tg[tg["is_home"]]
    away = tg[~tg["is_home"]]

    side_cols = list(_STATS) + ["n_prior"]
    h_cols = {c: f"home_{c}" for c in side_cols}
    a_cols = {c: f"away_{c}" for c in side_cols}
    h = home[["game_id"] + side_cols].rename(columns=h_cols)
    a = away[["game_id"] + side_cols].rename(columns=a_cols)

    out = h.merge(a, on="game_id", how="outer")
    for s in _STATS:
        hcol, acol = f"home_{s}", f"away_{s}"
        out[f"{s}_diff_asof"] = out[hcol] - out[acol]
        out = out.rename(columns={hcol: f"{hcol}_asof", acol: f"{acol}_asof"})
    for side in ("home_n_prior", "away_n_prior"):
        out[side] = pd.to_numeric(out[side], errors="coerce").fillna(0).astype("int64")
    out = out.reindex(columns=list(OUTPUT_COLS))
    out = out.sort_values("game_id", kind="mergesort").reset_index(drop=True)
    return out


def build_asof_defender_rollup(
    defenders: Optional[pd.DataFrame] = None,
    games: Optional[pd.DataFrame] = None,
    out_path: Optional[str] = None,
) -> Path:
    """Build the leak-free team-level roll-up of the already-as-of defender layer.

    Parameters
    ----------
    defenders:
        defender_matchup_states.parquet (player-game as-of rows). If None, reads the
        default on-disk file.
    games:
        games.parquet (authoritative home/away). If None, reads the default.
    out_path:
        Output parquet path. If None, uses the default asof_defender_rollup.parquet.

    Returns
    -------
    Path
        Parquet path written (atomic tmp+replace). One row per game_id present in
        BOTH inputs; see OUTPUT_COLS. NaN as-of where a side had zero covered
        defenders. NO gate fit runs here -- data reclaim only.
    """
    dest = Path(out_path) if out_path is not None else _DEFAULT_OUT
    if defenders is None:
        if not _DEFAULT_IN.exists():
            raise FileNotFoundError(f"defender_matchup_states.parquet not found at {_DEFAULT_IN}.")
        defenders = pd.read_parquet(_DEFAULT_IN)
    if games is None:
        if not _DEFAULT_GAMES.exists():
            raise FileNotFoundError(f"games.parquet not found at {_DEFAULT_GAMES}.")
        games = pd.read_parquet(_DEFAULT_GAMES)

    if len(defenders) == 0:
        out = pd.DataFrame(columns=list(OUTPUT_COLS))
    else:
        team_game = _team_game_means(defenders)
        tg = _attach_side(team_game, games)
        out = pd.DataFrame(columns=list(OUTPUT_COLS)) if len(tg) == 0 else _pivot_to_games(tg)

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    out.to_parquet(str(tmp), index=False)
    tmp.replace(dest)
    return dest


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description="defender_matchup_states.parquet -> leak-free team-rollup as-of features")
    ap.add_argument("--in", dest="inp", default=None, help="defender_matchup_states.parquet (optional)")
    ap.add_argument("--games", default=None, help="games.parquet (optional)")
    ap.add_argument("--out", default=None, help="Output parquet path (optional)")
    args = ap.parse_args()

    _def = pd.read_parquet(args.inp) if args.inp else None
    _g = pd.read_parquet(args.games) if args.games else None
    path = build_asof_defender_rollup(defenders=_def, games=_g, out_path=args.out)
    df = pd.read_parquet(str(path))
    print("LEAK-FREE team roll-up of the already-as-of DEFENDER-matchup layer.")
    print("DATA RECLAIM only -- NO gate fit run; NOT a market edge.")
    print(f"Wrote {path}  ({len(df)} game rows)")
    if len(df):
        cov = int((df["home_n_prior"] > 0).sum() + (df["away_n_prior"] > 0).sum())
        print(f"Team-sides with >=1 covered defender: {cov} / {2 * len(df)}")
        print("Sample (3 rows):")
        print(df.head(3).to_string())
