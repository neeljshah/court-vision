"""domains.basketball_nba.asof_box_extra — LEAK-FREE walk-forward extra box as-of features.

Build prior-only trailing team rates for dreb, fg3m, stl, blk from the W59 sidecar
``player_boxscores.parquet``.  Uses the IDENTICAL snapshot-before-update discipline as
``asof_features.py``: for each team-game, we record the team's trailing mean BEFORE
folding the current game in.  The first game of each season-team slot has NaN.

W112 confirmed dreb/fg3m/stl/blk are present in player_boxscores.parquet but were NOT
gate-tested.  This module makes them available for the REAL honest gate (W112/W113).
Expected gate verdict: REJECT (box-derived team rates redundant with Elo; market
efficient).  A REJECT is a SUCCESS — no edge is claimed here.

LEAK-NOTE:
- Features for game *i* use ONLY each team's games with strictly prior dates.
- Snapshot-BEFORE-update: record trailing aggregates, THEN update accumulators.
- NaN when n_prior == 0 (no prior games for this team in this run).
- Seasons are pooled (same pattern as asof_features.py); per-team counters reset
  only by the absence of earlier data, not by season boundary.

Input ``player_box`` columns consumed:
  game_id, date, team, opp, is_home, dreb, fg3m, stl, blk.

Output -> ``data/domains/basketball_nba/asof_box_extra.parquet`` keyed game_id:
  game_id,
  home_dreb_pg_asof, away_dreb_pg_asof, dreb_diff_asof,
  home_fg3m_pg_asof, away_fg3m_pg_asof, fg3m_diff_asof,
  home_stl_pg_asof,  away_stl_pg_asof,  stl_diff_asof,
  home_blk_pg_asof,  away_blk_pg_asof,  blk_diff_asof,
  home_n_prior, away_n_prior.

PRIVATE: ``data/domains/basketball_nba/`` is never tracked.  No src.* / kernel.* /
other-domain imports (falsifier F5 compliance).
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_IN = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
_DEFAULT_OUT = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "asof_box_extra.parquet"

# Stats to sum to team-game totals then track as leak-free trailing means.
_STATS = ("dreb", "fg3m", "stl", "blk")

OUTPUT_COLS = (
    "game_id",
    "home_dreb_pg_asof", "away_dreb_pg_asof", "dreb_diff_asof",
    "home_fg3m_pg_asof", "away_fg3m_pg_asof", "fg3m_diff_asof",
    "home_stl_pg_asof",  "away_stl_pg_asof",  "stl_diff_asof",
    "home_blk_pg_asof",  "away_blk_pg_asof",  "blk_diff_asof",
    "home_n_prior", "away_n_prior",
)


def _aggregate_team_games(player_box: pd.DataFrame) -> pd.DataFrame:
    """Players -> one row per (game_id, team) with summed box totals."""
    pb = player_box.copy()
    pb["game_id"] = pb["game_id"].astype(str)
    pb["team"] = pb["team"].astype(str)
    for c in _STATS:
        pb[c] = pd.to_numeric(pb.get(c), errors="coerce").fillna(0.0)

    agg: Dict = {c: "sum" for c in _STATS}
    agg.update({"date": "first", "opp": "first", "is_home": "first"})
    tg = pb.groupby(["game_id", "team"], as_index=False, sort=False).agg(agg)
    tg = tg.rename(columns={c: f"team_{c}" for c in _STATS})
    return tg


def _walk_forward_team(tg: pd.DataFrame) -> pd.DataFrame:
    """Per-team prior-only trailing means (snapshot-before-update).

    Sort all team-games by (date, game_id), then replay.  For each row,
    BEFORE updating, record the team's trailing per-game means over all
    strictly-prior games.  Then accumulate the current game.  NaN when no
    prior games exist (n_prior == 0).
    """
    tg = tg.copy()
    tg["date"] = pd.to_datetime(tg["date"])
    tg = tg.sort_values(["date", "game_id"], kind="mergesort").reset_index(drop=True)

    n: Dict[str, int] = {}
    sums: Dict[str, Dict[str, float]] = {s: {} for s in _STATS}

    rows_out: Dict[str, List] = {f"{s}_pg_asof": [] for s in _STATS}
    n_prior_list: List[int] = []

    for _, r in tg.iterrows():
        t = r["team"]
        cnt = n.get(t, 0)

        # --- SNAPSHOT (pre-update) ---
        if cnt == 0:
            for s in _STATS:
                rows_out[f"{s}_pg_asof"].append(np.nan)
        else:
            for s in _STATS:
                rows_out[f"{s}_pg_asof"].append(sums[s].get(t, 0.0) / cnt)
        n_prior_list.append(cnt)

        # --- UPDATE ---
        n[t] = cnt + 1
        for s in _STATS:
            sums[s][t] = sums[s].get(t, 0.0) + float(r[f"team_{s}"])

    for s in _STATS:
        tg[f"{s}_pg_asof"] = rows_out[f"{s}_pg_asof"]
    tg["n_prior"] = n_prior_list
    return tg


_ASOF_SIDE_COLS = [f"{s}_pg_asof" for s in _STATS]


def _pivot_to_games(tg: pd.DataFrame) -> pd.DataFrame:
    """Two team-rows per game -> one game_id row with home/away/diff columns."""
    is_home = tg["is_home"].apply(lambda v: bool(v) if pd.notna(v) else False)
    home = tg[is_home]
    away = tg[~is_home]

    side_cols = _ASOF_SIDE_COLS + ["n_prior"]
    h = home[["game_id"] + side_cols].rename(columns={c: f"home_{c}" for c in side_cols})
    a = away[["game_id"] + side_cols].rename(columns={c: f"away_{c}" for c in side_cols})

    out = h.merge(a, on="game_id", how="outer")
    for s in _STATS:
        out[f"{s}_diff_asof"] = out[f"home_{s}_pg_asof"] - out[f"away_{s}_pg_asof"]
    for side in ("home_n_prior", "away_n_prior"):
        out[side] = pd.to_numeric(out[side], errors="coerce").fillna(0).astype("int64")
    out = out.reindex(columns=list(OUTPUT_COLS))
    out = out.sort_values("game_id", kind="mergesort").reset_index(drop=True)
    return out


def build_asof_box_extra(
    player_box: Optional[pd.DataFrame] = None,
    out_path: Optional[str] = None,
) -> Path:
    """Build leak-free walk-forward extra box as-of features (dreb/fg3m/stl/blk).

    Parameters
    ----------
    player_box:
        Player-level box DataFrame (the W59 sidecar).  If None, reads default
        ``player_boxscores.parquet``.  Must carry game_id, date, team, is_home
        + dreb, fg3m, stl, blk player box stats.
    out_path:
        Output parquet path.  If None, uses the default ``asof_box_extra.parquet``.

    Returns
    -------
    Path
        Parquet path written (one row per game_id; see OUTPUT_COLS).
        NaN as-of values where n_prior == 0.
    """
    dest = Path(out_path) if out_path is not None else _DEFAULT_OUT
    if player_box is None:
        if not _DEFAULT_IN.exists():
            raise FileNotFoundError(f"player_boxscores.parquet not found at {_DEFAULT_IN}.")
        player_box = pd.read_parquet(_DEFAULT_IN)

    if len(player_box) == 0:
        out = pd.DataFrame(columns=list(OUTPUT_COLS))
    else:
        tg = _aggregate_team_games(player_box)
        tg = _walk_forward_team(tg)
        out = _pivot_to_games(tg)

    dest.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(str(dest), index=False)
    return dest


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description="player_boxscores.parquet -> leak-free as-of dreb/fg3m/stl/blk")
    ap.add_argument("--in", dest="inp", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    _pb = pd.read_parquet(args.inp) if args.inp else None
    path = build_asof_box_extra(player_box=_pb, out_path=args.out)
    df = pd.read_parquet(str(path))
    print("LEAK-FREE walk-forward as-of (dreb/fg3m/stl/blk; prior-only; snapshot-before-update).")
    print("NOT a market edge.  Gate decides honestly next (expect REJECT).")
    print(f"Wrote {path}  ({len(df)} game rows)")
    if len(df):
        print(df.head(3).to_string())
