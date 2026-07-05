"""domains.basketball_nba.asof_team_adv -- LEAK-FREE walk-forward as-of team ADVANCED stats.

DATA RECLAIM (GAP#6, matrix line 192): ``data/team_advanced_stats.parquet`` (7370 rows,
one row per (game_id, team_tricode), 2022-25) sits unreclaimed -- the existing asof_*
builders only cover box (player_boxscores.parquet, 2024-26).  This module reclaims the
advanced-stats sidecar into a leak-free prior-only trailing-mean feature table using the
IDENTICAL snapshot-before-update discipline as asof_features.py / asof_box_extra.py /
asof_runvar.py: for each team-game, we record the team's trailing per-game mean over
STRICTLY prior games (date < game date, via games.parquet as the authoritative date axis
-- NOT the sidecar's own game_date string), THEN fold the current game's row into history.

This is a DATA RECLAIM step only -- no gate fit runs here (prereg amendment + K spend come
later).  No edge is claimed.  Output enables a 2ND, higher-power, non-overlapping-window
corpus (2022-25) alongside the existing 2024-26 box corpus for future honest gating.

LEAK-NOTE:
- Feature for game *i* uses ONLY the team's OTHER games with date < date_i (games.parquet
  date, joined on game_id -- never the sidecar's own game_date column).
- Snapshot-BEFORE-update: record trailing mean, THEN accumulate the current game's stats.
- NaN when n_prior == 0 (team's first game in this corpus).
- team_advanced_stats.parquet already carries exactly 2 rows per game_id (one per side);
  no player-level aggregation step is needed (unlike asof_features.py/asof_box_extra.py).
- Coverage: 2022-25 seasons present in team_advanced_stats.parquet; games absent from that
  sidecar simply do not appear in the output (honest NaN via outer-join semantics is not
  needed here since input rows ARE the team-games; missing games are simply absent rows).

Input ``team_adv`` columns consumed (team_advanced_stats.parquet):
  game_id, team_tricode, off_rtg, def_rtg, pace, oreb_pct, dreb_pct, ast_pct, efg_pct,
  ts_pct, tov_ratio.
Input ``games`` columns consumed (games.parquet, authoritative date + home/away):
  game_id, date, home_team, away_team.

Output -> ``data/domains/basketball_nba/asof_team_adv.parquet`` keyed game_id:
  game_id,
  home_off_rtg_asof, away_off_rtg_asof, off_rtg_diff_asof,
  home_def_rtg_asof, away_def_rtg_asof, def_rtg_diff_asof,
  home_pace_asof,    away_pace_asof,    pace_diff_asof,
  home_oreb_pct_asof, away_oreb_pct_asof, oreb_pct_diff_asof,
  home_dreb_pct_asof, away_dreb_pct_asof, dreb_pct_diff_asof,
  home_ast_pct_asof,  away_ast_pct_asof,  ast_pct_diff_asof,
  home_efg_pct_asof,  away_efg_pct_asof,  efg_pct_diff_asof,
  home_ts_pct_asof,   away_ts_pct_asof,   ts_pct_diff_asof,
  home_tov_ratio_asof, away_tov_ratio_asof, tov_ratio_diff_asof,
  home_n_prior, away_n_prior.
  diff_asof = home - away throughout (matches asof_box_extra.py convention).

PRIVATE: ``data/domains/basketball_nba/`` is never tracked.  No src.* / kernel.* /
other-domain imports (falsifier F5 compliance).  NO gate fit in this module -- DATA
reclaim only; prereg amendment + honest gating is a separate future step.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_IN = _REPO_ROOT / "data" / "team_advanced_stats.parquet"
_DEFAULT_GAMES = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "games.parquet"
_DEFAULT_OUT = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "asof_team_adv.parquet"

# Advanced-stat columns tracked as leak-free prior-only trailing means.
_STATS = (
    "off_rtg", "def_rtg", "pace", "oreb_pct", "dreb_pct",
    "ast_pct", "efg_pct", "ts_pct", "tov_ratio",
)

# OUTPUT_COLS is (home, away, diff) triples per stat, matching asof_box_extra.py's
# column-ordering convention.
_TRIPLES: List[str] = []
for _s in _STATS:
    _TRIPLES.extend([f"home_{_s}_asof", f"away_{_s}_asof", f"{_s}_diff_asof"])
OUTPUT_COLS = ("game_id",) + tuple(_TRIPLES) + ("home_n_prior", "away_n_prior")


def _attach_date(team_adv: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """Join the authoritative games.parquet date onto each team-game row.

    Uses games.parquet's ``date`` (never the sidecar's own ``game_date`` string) so the
    walk-forward sort order and any future truncation test share one date axis with every
    other asof_* builder.  Rows whose game_id is absent from games.parquet are dropped
    (cannot place them on the shared date axis; team_advanced_stats.parquet had 0 such
    rows at build time, verified live).
    """
    ta = team_adv.copy()
    ta["game_id"] = ta["game_id"].astype(str)
    ta["team_tricode"] = ta["team_tricode"].astype(str)

    g = games[["game_id", "date", "home_team", "away_team"]].copy()
    g["game_id"] = g["game_id"].astype(str)
    g["date"] = pd.to_datetime(g["date"])

    merged = ta.merge(g, on="game_id", how="inner")
    merged["is_home"] = merged["team_tricode"] == merged["home_team"]
    return merged


def _walk_forward_team(tg: pd.DataFrame) -> pd.DataFrame:
    """Per-team prior-only trailing means (snapshot-before-update).

    Sort all team-games by (date, game_id), then replay.  For each row, BEFORE updating,
    record the team's trailing per-game mean over all strictly-prior games.  Then
    accumulate the current game.  NaN when no prior games exist (n_prior == 0).
    """
    tg = tg.sort_values(["date", "game_id"], kind="mergesort").reset_index(drop=True)

    n: Dict[str, int] = {}
    sums: Dict[str, Dict[str, float]] = {s: {} for s in _STATS}

    rows_out: Dict[str, List] = {f"{s}_asof": [] for s in _STATS}
    n_prior_list: List[int] = []

    for _, r in tg.iterrows():
        t = r["team_tricode"]
        cnt = n.get(t, 0)

        # --- SNAPSHOT (pre-update): trailing mean over strictly-prior games only ---
        if cnt == 0:
            for s in _STATS:
                rows_out[f"{s}_asof"].append(float("nan"))
        else:
            for s in _STATS:
                rows_out[f"{s}_asof"].append(sums[s].get(t, 0.0) / cnt)
        n_prior_list.append(cnt)

        # --- UPDATE (post-snapshot): fold current game's row into history ---
        n[t] = cnt + 1
        for s in _STATS:
            sums[s][t] = sums[s].get(t, 0.0) + float(r[s])

    for s in _STATS:
        tg[f"{s}_asof"] = rows_out[f"{s}_asof"]
    tg["n_prior"] = n_prior_list
    return tg


_ASOF_SIDE_COLS = [f"{s}_asof" for s in _STATS]


def _pivot_to_games(tg: pd.DataFrame) -> pd.DataFrame:
    """Two team-rows per game -> one game_id row with home/away/diff columns."""
    home = tg[tg["is_home"]]
    away = tg[~tg["is_home"]]

    side_cols = _ASOF_SIDE_COLS + ["n_prior"]
    h = home[["game_id"] + side_cols].rename(columns={c: f"home_{c}" for c in side_cols})
    a = away[["game_id"] + side_cols].rename(columns={c: f"away_{c}" for c in side_cols})

    out = h.merge(a, on="game_id", how="outer")
    for s in _STATS:
        out[f"{s}_diff_asof"] = out[f"home_{s}_asof"] - out[f"away_{s}_asof"]
    for side in ("home_n_prior", "away_n_prior"):
        out[side] = pd.to_numeric(out[side], errors="coerce").fillna(0).astype("int64")
    out = out.reindex(columns=list(OUTPUT_COLS))
    out = out.sort_values("game_id", kind="mergesort").reset_index(drop=True)
    return out


def build_asof_team_adv(
    team_adv: Optional[pd.DataFrame] = None,
    games: Optional[pd.DataFrame] = None,
    out_path: Optional[str] = None,
) -> Path:
    """Build leak-free walk-forward as-of team ADVANCED-stat features.

    Parameters
    ----------
    team_adv:
        Team-game advanced-stat DataFrame (team_advanced_stats.parquet: one row per
        (game_id, team_tricode)).  If None, reads the default sidecar.
    games:
        games.parquet (authoritative date + home_team/away_team).  If None, reads the
        default.  Used ONLY for date + home/away side; never trusts the sidecar's own
        game_date column.
    out_path:
        Output parquet path.  If None, uses the default asof_team_adv.parquet.

    Returns
    -------
    Path
        Parquet path written (one row per game_id; see OUTPUT_COLS).  NaN as-of values
        where n_prior == 0.  NO gate fit runs here -- data reclaim only.
    """
    dest = Path(out_path) if out_path is not None else _DEFAULT_OUT
    if team_adv is None:
        if not _DEFAULT_IN.exists():
            raise FileNotFoundError(f"team_advanced_stats.parquet not found at {_DEFAULT_IN}.")
        team_adv = pd.read_parquet(_DEFAULT_IN)
    if games is None:
        if not _DEFAULT_GAMES.exists():
            raise FileNotFoundError(f"games.parquet not found at {_DEFAULT_GAMES}.")
        games = pd.read_parquet(_DEFAULT_GAMES)

    if len(team_adv) == 0:
        out = pd.DataFrame(columns=list(OUTPUT_COLS))
    else:
        tg = _attach_date(team_adv, games)
        if len(tg) == 0:
            out = pd.DataFrame(columns=list(OUTPUT_COLS))
        else:
            tg = _walk_forward_team(tg)
            out = _pivot_to_games(tg)

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    out.to_parquet(str(tmp), index=False)
    tmp.replace(dest)
    return dest


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description="team_advanced_stats.parquet -> leak-free as-of advanced-stat features")
    ap.add_argument("--in", dest="inp", default=None, help="team_advanced_stats.parquet (optional)")
    ap.add_argument("--games", default=None, help="games.parquet (optional)")
    ap.add_argument("--out", default=None, help="Output parquet path (optional)")
    args = ap.parse_args()

    _ta = pd.read_parquet(args.inp) if args.inp else None
    _g = pd.read_parquet(args.games) if args.games else None
    path = build_asof_team_adv(team_adv=_ta, games=_g, out_path=args.out)
    df = pd.read_parquet(str(path))
    print("LEAK-FREE walk-forward as-of team ADVANCED stats (prior-only; snapshot-before-update).")
    print("DATA RECLAIM only -- NO gate fit run; NOT a market edge.")
    print(f"Wrote {path}  ({len(df)} game rows)")
    if len(df):
        dmin = df["game_id"].min()
        dmax = df["game_id"].max()
        print(f"game_id range: {dmin} .. {dmax}")
        cov = int((df["home_n_prior"] > 0).sum() + (df["away_n_prior"] > 0).sum())
        print(f"Team-sides with >=1 prior game: {cov} / {2 * len(df)}")
        print("Sample (3 rows):")
        print(df.head(3).to_string())
