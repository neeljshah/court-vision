"""domains.basketball_nba.asof_features — LEAK-FREE walk-forward as-of team features.

Build prior-only trailing team rates from the W59 sidecar ``player_boxscores.parquet``
(player-level realized box lines).  Players are aggregated up to TEAM-GAME totals,
then each team's history is replayed IN DATE ORDER with a strict snapshot-before-update
discipline (mirrors ``ratings.py``): the as-of features for game *i* use ONLY each
team's games with ``date < date_i`` — that game's own realized box NEVER feeds its own
features, and no future game can contaminate it.

This DEEPENS the substrate / calibration so the regular-season ASSIST-RATE signal can
be gate-tested HONESTLY downstream.  It is NOT a market edge.  No edge is claimed here.
The AST rate is a pure transform of leak-free prior box totals; the honest gate decides
ship/reject next (expect REJECT/DEFER) — it must never be claimed an edge.

LEAK-NOTE:
- Feature for game *i* uses ONLY each team's games with ``date < date_i``.
- Snapshot-BEFORE-update: record the team's trailing aggregates, THEN fold game *i* in.
- NaN when a team has zero strictly-prior games (``n_prior == 0``).
- Coverage is limited to seasons present in the box cache (2024-25 ~complete +
  2025-26 partial); games with no box rows simply do not appear.

Input ``player_box`` columns consumed (self-sufficient sidecar):
  game_id, date, team, opp, is_home, ast, fgm, fga, fg3m, reb, oreb, dreb, tov, pts, fta.

Output -> ``data/domains/basketball_nba/asof_features.parquet`` keyed game_id:
  game_id,
  home_ast_rate_asof, away_ast_rate_asof, ast_rate_diff_asof (home-minus-away),
  home_ast_pg_asof, away_ast_pg_asof, home_oreb_pg_asof, away_oreb_pg_asof,
  home_tov_pg_asof, away_tov_pg_asof, home_pace_asof, away_pace_asof,
  home_n_prior, away_n_prior.

PRIVATE: ``data/domains/basketball_nba/`` is never tracked.  No src.* / kernel.* /
other-domain imports (falsifier F5 compliance).
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_IN = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
_DEFAULT_OUT = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "asof_features.parquet"

_LAST_N = 10  # trailing window for the *_l10 view (last-10 expanding to expanding mean)

# Player-level counting stats SUMMED to team-game totals.
_TEAM_SUM = ("ast", "fgm", "fga", "fg3m", "reb", "oreb", "dreb", "tov", "pts", "fta")


def _aggregate_team_games(player_box: pd.DataFrame) -> pd.DataFrame:
    """Step 1: players -> one row per (game_id, team) with summed box totals.

    Carries the game context (date, opp, is_home) — all constant within a
    (game_id, team) group, so ``first`` is exact.
    """
    pb = player_box.copy()
    pb["game_id"] = pb["game_id"].astype(str)
    pb["team"] = pb["team"].astype(str)
    for c in _TEAM_SUM:
        pb[c] = pd.to_numeric(pb.get(c), errors="coerce").fillna(0.0)

    agg = {c: "sum" for c in _TEAM_SUM}
    agg.update({"date": "first", "opp": "first", "is_home": "first"})
    tg = pb.groupby(["game_id", "team"], as_index=False, sort=False).agg(agg)
    tg = tg.rename(columns={c: f"team_{c}" for c in _TEAM_SUM})
    return tg


def _walk_forward_team(tg: pd.DataFrame) -> pd.DataFrame:
    """Step 2: per-team prior-only trailing aggregates (snapshot-before-update).

    Sort team-games by (date, game_id) stable, then replay.  For each team-game,
    BEFORE folding it in, record the team's trailing aggregates over its STRICTLY
    prior games (expanding mean; pace/ast_pg/oreb_pg/tov_pg as per-game means;
    ast_rate as sum(team_ast)/sum(team_fgm) over prior games).  Then UPDATE history.
    NaN when no prior games (n_prior == 0).
    """
    tg = tg.copy()
    tg["date"] = pd.to_datetime(tg["date"])
    tg = tg.sort_values(["date", "game_id"], kind="mergesort").reset_index(drop=True)

    # Per-team running accumulators (sums over strictly-prior games).
    n: dict = {}
    s_ast: dict = {}
    s_fgm: dict = {}
    s_oreb: dict = {}
    s_tov: dict = {}
    s_pace: dict = {}  # fga + 0.44*fta per game, summed

    ast_rate: List[float] = []
    ast_pg: List[float] = []
    oreb_pg: List[float] = []
    tov_pg: List[float] = []
    pace: List[float] = []
    n_prior: List[int] = []

    for _, r in tg.iterrows():
        t = r["team"]
        cnt = n.get(t, 0)
        if cnt == 0:
            ast_rate.append(np.nan)
            ast_pg.append(np.nan)
            oreb_pg.append(np.nan)
            tov_pg.append(np.nan)
            pace.append(np.nan)
        else:
            fgm_sum = s_fgm.get(t, 0.0)
            ast_rate.append(s_ast[t] / fgm_sum if fgm_sum > 0 else np.nan)
            ast_pg.append(s_ast[t] / cnt)
            oreb_pg.append(s_oreb[t] / cnt)
            tov_pg.append(s_tov[t] / cnt)
            pace.append(s_pace[t] / cnt)
        n_prior.append(cnt)

        # ---- UPDATE (post-snapshot) ----
        n[t] = cnt + 1
        s_ast[t] = s_ast.get(t, 0.0) + float(r["team_ast"])
        s_fgm[t] = s_fgm.get(t, 0.0) + float(r["team_fgm"])
        s_oreb[t] = s_oreb.get(t, 0.0) + float(r["team_oreb"])
        s_tov[t] = s_tov.get(t, 0.0) + float(r["team_tov"])
        s_pace[t] = s_pace.get(t, 0.0) + float(r["team_fga"]) + 0.44 * float(r["team_fta"])

    tg["ast_rate_asof"] = ast_rate
    tg["ast_pg_asof"] = ast_pg
    tg["oreb_pg_asof"] = oreb_pg
    tg["tov_pg_asof"] = tov_pg
    tg["pace_asof"] = pace
    tg["n_prior"] = n_prior
    return tg


_ASOF_COLS = ("ast_rate_asof", "ast_pg_asof", "oreb_pg_asof", "tov_pg_asof", "pace_asof")

OUTPUT_COLS = (
    "game_id",
    "home_ast_rate_asof", "away_ast_rate_asof", "ast_rate_diff_asof",
    "home_ast_pg_asof", "away_ast_pg_asof",
    "home_oreb_pg_asof", "away_oreb_pg_asof",
    "home_tov_pg_asof", "away_tov_pg_asof",
    "home_pace_asof", "away_pace_asof",
    "home_n_prior", "away_n_prior",
)


def _pivot_to_games(tg: pd.DataFrame) -> pd.DataFrame:
    """Step 3: collapse two team-rows per game into one game_id row (home & away).

    ``is_home`` selects the home side; the other team-row is the away side.
    ast_rate_diff_asof = home - away.  One row per game_id.
    """
    is_home = tg["is_home"].apply(lambda v: bool(v) if pd.notna(v) else False)
    home = tg[is_home]
    away = tg[~is_home]

    cols = list(_ASOF_COLS) + ["n_prior"]
    home_r = home[["game_id"] + cols].rename(columns={c: f"home_{c}" for c in cols})
    away_r = away[["game_id"] + cols].rename(columns={c: f"away_{c}" for c in cols})

    out = home_r.merge(away_r, on="game_id", how="outer")
    out["ast_rate_diff_asof"] = out["home_ast_rate_asof"] - out["away_ast_rate_asof"]
    for side in ("home_n_prior", "away_n_prior"):
        out[side] = pd.to_numeric(out[side], errors="coerce").fillna(0).astype("int64")
    out = out.reindex(columns=list(OUTPUT_COLS))
    out = out.sort_values("game_id", kind="mergesort").reset_index(drop=True)
    return out


def build_asof_features(
    player_box: Optional[pd.DataFrame] = None,
    out_path: Optional[str] = None,
) -> Path:
    """Build the leak-free walk-forward as-of team feature table.

    Parameters
    ----------
    player_box:
        Player-level box DataFrame (the W59 sidecar).  If None, read the default
        ``player_boxscores.parquet``.  Self-sufficient: must carry game_id, date,
        team, opp, is_home + player box stats.
    out_path:
        Output parquet path.  If None, the default ``asof_features.parquet``.

    Returns
    -------
    Path
        The parquet path written (one row per game_id; see module docstring /
        OUTPUT_COLS).  NaN as-of values where ``n_prior == 0``.
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
        description="NBA player_boxscores.parquet -> leak-free as-of team features")
    ap.add_argument("--in", dest="inp", default=None, help="player_boxscores.parquet (optional)")
    ap.add_argument("--out", default=None, help="Output parquet path (optional)")
    args = ap.parse_args()

    _pb = pd.read_parquet(args.inp) if args.inp else None
    path = build_asof_features(player_box=_pb, out_path=args.out)
    df = pd.read_parquet(str(path))
    print("LEAK-FREE walk-forward as-of team features (prior-only; snapshot-before-update).")
    print("DEEPENS substrate/calibration; NOT a market edge; AST signal gate-tested HONESTLY next.")
    print(f"Wrote {path}")
    print(f"Game rows: {len(df)}")
    if len(df):
        cov = int((df["home_n_prior"] > 0).sum() + (df["away_n_prior"] > 0).sum())
        print(f"Team-sides with >=1 prior game: {cov} / {2 * len(df)}")
        print("Sample (3 rows):")
        print(df.head(3).to_string())
