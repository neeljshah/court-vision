"""domains.basketball_nba.boxdetail_asof -- LEAK-FREE walk-forward box-DETAIL as-of.

Unlocks the entirely-dark ``espn_boxscores.parquet`` box-detail family (utilization
audit docs/research/utilization_matrix_2026_07_10.md, ranked-backlog item #1):
fast_break_pts, paint_pts, tov_pts (points off turnovers), largest_lead, and a
combined tech+flagrant foul_trouble count. Raw same-game values of these columns
would LEAK (they are a same-game result), so the only defensible use is each
team's TRAILING profile strictly before the game date -- same discipline as the
sibling ``asof_box_extra.py`` (dreb/fg3m/stl/blk from player_boxscores.parquet).

Two windows per stat, both prior-only / snapshot-before-update:
  - season-to-date expanding mean  (``<stat>_asof``)
  - trailing last-10-games mean    (``<stat>_l10_asof``)
NaN when a team has zero prior games WITH a non-null detail value (box-detail
columns only exist for a subset of games -- OT-truncation caveat below -- so
NaN here is expected and honest, not a bug).

OT CAUTION (carried from the in-flight parallel lane): espn_boxscores finals are
TRUNCATED for OT games (regulation tie recorded, not the final score). This
builder never reads final-score columns (home_score/away_score/margin) -- only
box-DETAIL columns (fast_break_pts, paint_pts, tov_pts, foul counts). largest_lead
is an in-game stat (not a final-score column) and is safe to use here, but is
noted as the one column closest to that caveat's boundary.

Input ``espn_box`` columns consumed (one row per game already, home_/away_
prefixed -- no team-game pivot needed, unlike player_boxscores.parquet):
  event_id, date, home_abbr, away_abbr,
  {home,away}_fast_break_pts, {home,away}_paint_pts, {home,away}_tov_pts,
  {home,away}_largest_lead, {home,away}_tech, {home,away}_flagrant.

ID BRIDGE: espn_boxscores.parquet is keyed by ESPN event_id, a different ID
space than the NBA game_id every other as-of parquet (games.parquet,
asof_features.parquet, asof_box_extra.parquet) and the gate machinery
(asof_ast_rate_eval.build_candidate_frame) key on. The on-disk
espn_nba_game_bridge.parquet (domains/basketball_nba/espn_nba_bridge.py) only
covers 2023-24/2024-25 (no linescores_2025_26.parquet exists yet), which is
BEFORE this box-detail family's own coverage window (2026-01-20 onward) --
zero overlap. This module instead does the SAME schedule-key join directly
against games.parquet: (home tricode, away tricode, calendar date), reusing
espn_nba_bridge._norm_abbr's ESPN->NBA-stats tricode normalization. No score/
outcome field participates (outcome-free, safe pregame). Unmatched rows
(~24% in the detail-era window -- playoffs/date-format edge cases outside
games.parquet's regular-season scope) are DROPPED, never fabricated.

Output -> ``data/domains/basketball_nba/boxdetail_asof.parquet`` keyed by the
real NBA game_id (bridged, see above), see OUTPUT_COLS.

LEAK-NOTE: features for game *i* use ONLY each team's games with strictly prior
dates. Snapshot-BEFORE-update: record trailing aggregates, THEN fold the current
game's values into the accumulators.

PRIVATE: ``data/domains/basketball_nba/`` is never tracked. No src.* / kernel.*
/ other-domain imports (falsifier F5 compliance). No edge claimed -- calibration
candidate only, gated honestly downstream.
"""
from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from domains.basketball_nba.espn_nba_bridge import _norm_abbr

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_IN = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "espn_boxscores.parquet"
_GAMES = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "games.parquet"
_DEFAULT_OUT = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "boxdetail_asof.parquet"

_L10_WINDOW = 10

# Raw ESPN columns feeding each stat (foul_trouble = tech + flagrant, combined
# because both are individually thin/sparse counts -- see attribute_registry.py).
_STAT_SRC_COLS: Dict[str, List[str]] = {
    "fast_break_pts": ["fast_break_pts"],
    "paint_pts": ["paint_pts"],
    "tov_pts": ["tov_pts"],
    "largest_lead": ["largest_lead"],
    "foul_trouble": ["tech", "flagrant"],
}
STATS = tuple(_STAT_SRC_COLS)

OUTPUT_COLS = ["game_id"]
for _s in STATS:
    OUTPUT_COLS += [f"home_{_s}_asof", f"away_{_s}_asof", f"{_s}_diff_asof"]
for _s in STATS:
    OUTPUT_COLS += [f"home_{_s}_l10_asof", f"away_{_s}_l10_asof", f"{_s}_l10_diff_asof"]
OUTPUT_COLS += ["home_n_prior", "away_n_prior"]


def _bridge_event_id_to_game_id(espn_box: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """Outcome-free schedule-key join: (home tricode, away tricode, date) ->
    real NBA game_id. Drops event_id and unmatched rows -- see module docstring."""
    df = espn_box.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["_home_nba"] = df["home_abbr"].map(_norm_abbr)
    df["_away_nba"] = df["away_abbr"].map(_norm_abbr)

    g = games[["game_id", "date", "home_team", "away_team"]].copy()
    g["date"] = pd.to_datetime(g["date"])

    merged = df.merge(
        g, left_on=["_home_nba", "_away_nba", "date"],
        right_on=["home_team", "away_team", "date"], how="inner",
    )
    return merged.drop(columns=["_home_nba", "_away_nba", "home_team", "away_team", "event_id"])


def _melt_to_team_games(espn_box: pd.DataFrame) -> pd.DataFrame:
    """One row per game -> two rows (home/away perspective) per team-game."""
    df = espn_box.copy()
    df["event_id"] = df["event_id"].astype(str)
    df["date"] = pd.to_datetime(df["date"])

    rows: List[Dict] = []
    for _, r in df.iterrows():
        for side, team, opp in (("home", r["home_abbr"], r["away_abbr"]),
                                 ("away", r["away_abbr"], r["home_abbr"])):
            row = {"game_id": r["event_id"], "date": r["date"],
                   "team": team, "opp": opp, "is_home": side == "home"}
            for stat, src_cols in _STAT_SRC_COLS.items():
                vals = [r.get(f"{side}_{c}") for c in src_cols]
                vals = [pd.to_numeric(v, errors="coerce") for v in vals]
                row[stat] = np.nan if any(pd.isna(v) for v in vals) else float(sum(vals))
            rows.append(row)
    return pd.DataFrame(rows)


def _walk_forward_team(tg: pd.DataFrame) -> pd.DataFrame:
    """Per-team prior-only trailing means, expanding + L10 (snapshot-before-update)."""
    tg = tg.sort_values(["date", "game_id"], kind="mergesort").reset_index(drop=True)

    n: Dict[str, int] = {}
    sums: Dict[str, Dict[str, float]] = {s: {} for s in STATS}
    windows: Dict[str, Dict[str, deque]] = {s: {} for s in STATS}

    out_cols: Dict[str, List] = {f"{s}_asof": [] for s in STATS}
    out_cols.update({f"{s}_l10_asof": [] for s in STATS})
    n_prior_list: List[int] = []

    for _, r in tg.iterrows():
        t = r["team"]
        cnt = n.get(t, 0)

        # --- SNAPSHOT (pre-update): expanding + L10 means over strictly prior games ---
        for s in STATS:
            if cnt == 0:
                out_cols[f"{s}_asof"].append(np.nan)
                out_cols[f"{s}_l10_asof"].append(np.nan)
            else:
                out_cols[f"{s}_asof"].append(sums[s].get(t, 0.0) / cnt)
                dq = windows[s].get(t)
                out_cols[f"{s}_l10_asof"].append(float(np.mean(dq)) if dq else np.nan)
        n_prior_list.append(cnt)

        # --- UPDATE: box-detail is an all-or-nothing block per game (ESPN
        # either returns the whole detail set or none of it -- verified on
        # disk, every one of the 5 stats is null/non-null in lockstep), so a
        # game only counts as a "prior game" -- for every stat, together --
        # when the WHOLE block is present. A partial row is skipped entirely
        # rather than diluting one stat's mean with a missing value. ---
        covered = all(pd.notna(r[s]) for s in STATS)
        if covered:
            n[t] = cnt + 1
            for s in STATS:
                v = float(r[s])
                sums[s][t] = sums[s].get(t, 0.0) + v
                dq = windows[s].setdefault(t, deque(maxlen=_L10_WINDOW))
                dq.append(v)

    for s in STATS:
        tg[f"{s}_asof"] = out_cols[f"{s}_asof"]
        tg[f"{s}_l10_asof"] = out_cols[f"{s}_l10_asof"]
    tg["n_prior"] = n_prior_list
    return tg


def _pivot_to_games(tg: pd.DataFrame) -> pd.DataFrame:
    """Two team-rows per game -> one game_id row with home/away/diff columns."""
    side_cols = [f"{s}_asof" for s in STATS] + [f"{s}_l10_asof" for s in STATS] + ["n_prior"]
    home = tg[tg["is_home"]]
    away = tg[~tg["is_home"]]

    h = home[["game_id"] + side_cols].rename(columns={c: f"home_{c}" for c in side_cols})
    a = away[["game_id"] + side_cols].rename(columns={c: f"away_{c}" for c in side_cols})
    out = h.merge(a, on="game_id", how="outer")

    for s in STATS:
        out[f"{s}_diff_asof"] = out[f"home_{s}_asof"] - out[f"away_{s}_asof"]
        out[f"{s}_l10_diff_asof"] = out[f"home_{s}_l10_asof"] - out[f"away_{s}_l10_asof"]
    for side in ("home_n_prior", "away_n_prior"):
        out[side] = pd.to_numeric(out[side], errors="coerce").fillna(0).astype("int64")

    out = out.reindex(columns=OUTPUT_COLS)
    return out.sort_values("game_id", kind="mergesort").reset_index(drop=True)


def build_boxdetail_asof(
    espn_box: Optional[pd.DataFrame] = None,
    out_path: Optional[str] = None,
) -> Path:
    """Build leak-free walk-forward box-detail as-of features.

    Parameters
    ----------
    espn_box:
        ``espn_boxscores.parquet``-shaped DataFrame (event_id, date, home_abbr,
        away_abbr + home_/away_ fast_break_pts/paint_pts/tov_pts/largest_lead/
        tech/flagrant). If None, reads the default on-disk parquet.
    out_path:
        Output parquet path. If None, uses the default ``boxdetail_asof.parquet``.

    Returns
    -------
    Path
        Parquet path written (one row per game_id; see OUTPUT_COLS). NaN as-of
        values where a team has zero prior games with a non-null detail value.
    """
    dest = Path(out_path) if out_path is not None else _DEFAULT_OUT
    if espn_box is None:
        if not _DEFAULT_IN.exists():
            raise FileNotFoundError(f"espn_boxscores.parquet not found at {_DEFAULT_IN}.")
        espn_box = pd.read_parquet(_DEFAULT_IN)

    if len(espn_box) == 0:
        out = pd.DataFrame(columns=OUTPUT_COLS)
    else:
        tg = _melt_to_team_games(espn_box)
        tg = _walk_forward_team(tg)
        out = _pivot_to_games(tg)

    dest.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(str(dest), index=False)
    return dest


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description="espn_boxscores.parquet -> leak-free box-detail as-of "
                    "(fast_break/paint/tov_pts/largest_lead/foul_trouble)")
    ap.add_argument("--in", dest="inp", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    _eb = pd.read_parquet(args.inp) if args.inp else None
    path = build_boxdetail_asof(espn_box=_eb, out_path=args.out)
    df = pd.read_parquet(str(path))
    print("LEAK-FREE walk-forward box-detail as-of (prior-only; snapshot-before-update).")
    print("NOT a market edge. Gate decides honestly next.")
    print(f"Wrote {path}  ({len(df)} game rows)")
    if len(df):
        print(df.dropna(subset=["fast_break_pts_diff_asof"]).head(3).to_string())
