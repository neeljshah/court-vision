"""domains.basketball_nba.asof_player_adv -- LEAK-FREE walk-forward as-of PLAYER
advanced-box trailing form.

DATA RECLAIM (ONDISK_RECLAIM_TARGETS.md row #12): ``data/player_adv_stats.parquet``
(77,728 rows, one row per (player_id, game_id), 2022-10-18..2025-04-13) sits
unreclaimed -- no existing asof_* builder reads it (verified: grep for
"player_adv_stats" across domains/basketball_nba/*.py hits only this module).
Unlike asof_team_adv.py (2 rows/game, home/away pivot), this is PLAYER-level and
is a PROP-layer reclaim, not a win-prob-gate reclaim: usage/on-off ratings/PIE/
possessions are trailing PLAYER FORM inputs for prop_pergame, not a team-diff
feature for the Elo win-prob gate.

Uses the IDENTICAL snapshot-before-update discipline as asof_team_adv.py: for each
player-game, record the player's trailing per-game mean over STRICTLY PRIOR games
(date < game date, via games.parquet as the authoritative date axis -- never the
sidecar's own game_date string), THEN fold the current game's row into history.

This is a DATA RECLAIM step only -- no gate fit runs here. Per
ONDISK_RECLAIM_TARGETS.md, this source has no recorded win-prob-gate bar (it is
explicitly the prop layer); a prop-lane gate/prereg amendment is a separate future
step. No edge is claimed.

LEAK-NOTE:
- Feature for player-game *i* uses ONLY that player's OTHER games with
  date < date_i (games.parquet date, joined on game_id -- never the sidecar's own
  game_date column).
- Snapshot-BEFORE-update: record trailing mean, THEN accumulate the current game's
  stats.
- NaN when n_prior == 0 (player's first game in this corpus).
- One row per (player_id, game_id) in the sidecar already (verified: 0 duplicate
  (player_id, game_id) pairs at build time) -- no aggregation step needed.

Input ``player_adv`` columns consumed (player_adv_stats.parquet):
  player_id, game_id, usagepercentage, offensiverating, defensiverating, pie,
  possessions.
Input ``games`` columns consumed (games.parquet, authoritative date):
  game_id, date.

Output -> ``data/domains/basketball_nba/asof_player_adv.parquet`` keyed
(player_id, game_id):
  player_id, game_id, date,
  usagepercentage_asof, offensiverating_asof, defensiverating_asof, pie_asof,
  possessions_asof, n_prior.

PRIVATE: ``data/domains/basketball_nba/`` is never tracked. No src.* / kernel.* /
other-domain imports (falsifier F5 compliance). NO gate fit in this module -- data
reclaim only; prop-lane gate/prereg amendment is a separate future step.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_IN = _REPO_ROOT / "data" / "player_adv_stats.parquet"
_DEFAULT_GAMES = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "games.parquet"
_DEFAULT_OUT = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "asof_player_adv.parquet"

# Advanced-box columns tracked as leak-free prior-only trailing means.
_STATS = ("usagepercentage", "offensiverating", "defensiverating", "pie", "possessions")

OUTPUT_COLS = (
    ("player_id", "game_id", "date")
    + tuple(f"{s}_asof" for s in _STATS)
    + ("n_prior",)
)


def _attach_date(player_adv: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """Join the authoritative games.parquet date onto each player-game row.

    Uses games.parquet's ``date`` (never the sidecar's own ``game_date`` string) so
    the walk-forward sort order shares one date axis with every other asof_*
    builder. Rows whose game_id is absent from games.parquet are dropped (cannot
    place them on the shared date axis).
    """
    pa = player_adv.copy()
    pa["player_id"] = pa["player_id"].astype(str)
    pa["game_id"] = pa["game_id"].astype(str)

    g = games[["game_id", "date"]].copy()
    g["game_id"] = g["game_id"].astype(str)
    g["date"] = pd.to_datetime(g["date"])

    return pa.merge(g, on="game_id", how="inner")


def _walk_forward_player(pg: pd.DataFrame) -> pd.DataFrame:
    """Per-player prior-only trailing means (snapshot-before-update).

    Sort all player-games by (date, game_id, player_id), then replay. For each
    row, BEFORE updating, record the player's trailing per-game mean over all
    strictly-prior games. Then accumulate the current game. NaN when no prior
    games exist (n_prior == 0).
    """
    pg = pg.sort_values(["date", "game_id", "player_id"], kind="mergesort").reset_index(drop=True)

    n: Dict[str, int] = {}
    sums: Dict[str, Dict[str, float]] = {s: {} for s in _STATS}

    rows_out: Dict[str, List] = {f"{s}_asof": [] for s in _STATS}
    n_prior_list: List[int] = []

    for _, r in pg.iterrows():
        p = r["player_id"]
        cnt = n.get(p, 0)

        # --- SNAPSHOT (pre-update): trailing mean over strictly-prior games only ---
        if cnt == 0:
            for s in _STATS:
                rows_out[f"{s}_asof"].append(float("nan"))
        else:
            for s in _STATS:
                rows_out[f"{s}_asof"].append(sums[s].get(p, 0.0) / cnt)
        n_prior_list.append(cnt)

        # --- UPDATE (post-snapshot): fold current game's row into history ---
        n[p] = cnt + 1
        for s in _STATS:
            sums[s][p] = sums[s].get(p, 0.0) + float(r[s])

    for s in _STATS:
        pg[f"{s}_asof"] = rows_out[f"{s}_asof"]
    pg["n_prior"] = n_prior_list
    return pg.reindex(columns=list(OUTPUT_COLS))


def build_asof_player_adv(
    player_adv: Optional[pd.DataFrame] = None,
    games: Optional[pd.DataFrame] = None,
    out_path: Optional[str] = None,
) -> Path:
    """Build leak-free walk-forward as-of PLAYER advanced-box trailing features.

    Parameters
    ----------
    player_adv:
        Player-game advanced-box DataFrame (player_adv_stats.parquet: one row per
        (player_id, game_id)). If None, reads the default sidecar.
    games:
        games.parquet (authoritative date). If None, reads the default. Used ONLY
        for date; never trusts the sidecar's own game_date column.
    out_path:
        Output parquet path. If None, uses the default asof_player_adv.parquet.

    Returns
    -------
    Path
        Parquet path written (one row per (player_id, game_id); see OUTPUT_COLS).
        NaN as-of values where n_prior == 0. NO gate fit runs here -- data reclaim
        only.
    """
    dest = Path(out_path) if out_path is not None else _DEFAULT_OUT
    if player_adv is None:
        if not _DEFAULT_IN.exists():
            raise FileNotFoundError(f"player_adv_stats.parquet not found at {_DEFAULT_IN}.")
        player_adv = pd.read_parquet(_DEFAULT_IN)
    if games is None:
        if not _DEFAULT_GAMES.exists():
            raise FileNotFoundError(f"games.parquet not found at {_DEFAULT_GAMES}.")
        games = pd.read_parquet(_DEFAULT_GAMES)

    if len(player_adv) == 0:
        out = pd.DataFrame(columns=list(OUTPUT_COLS))
    else:
        pg = _attach_date(player_adv, games)
        if len(pg) == 0:
            out = pd.DataFrame(columns=list(OUTPUT_COLS))
        else:
            out = _walk_forward_player(pg)
            out = out.sort_values(["game_id", "player_id"], kind="mergesort").reset_index(drop=True)

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    out.to_parquet(str(tmp), index=False)
    tmp.replace(dest)
    return dest


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description="player_adv_stats.parquet -> leak-free as-of player advanced-box features")
    ap.add_argument("--in", dest="inp", default=None, help="player_adv_stats.parquet (optional)")
    ap.add_argument("--games", default=None, help="games.parquet (optional)")
    ap.add_argument("--out", default=None, help="Output parquet path (optional)")
    args = ap.parse_args()

    _pa = pd.read_parquet(args.inp) if args.inp else None
    _g = pd.read_parquet(args.games) if args.games else None
    path = build_asof_player_adv(player_adv=_pa, games=_g, out_path=args.out)
    df = pd.read_parquet(str(path))
    print("LEAK-FREE walk-forward as-of PLAYER advanced-box features (prior-only; "
          "snapshot-before-update).")
    print("DATA RECLAIM only -- NO gate fit run; NOT a market edge; prop-layer, not win-prob.")
    print(f"Wrote {path}  ({len(df)} player-game rows)")
    if len(df):
        print(f"unique players: {df['player_id'].nunique()}  unique games: {df['game_id'].nunique()}")
        print(f"date range: {df['date'].min()} .. {df['date'].max()}")
        cov = int((df["n_prior"] > 0).sum())
        print(f"player-games with >=1 prior game: {cov} / {len(df)} ({100.0 * cov / len(df):.1f}%)")
        print("Sample (3 rows):")
        print(df.head(3).to_string())
