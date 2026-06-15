"""domains.basketball_nba.asof_runvar — calibration PROBE (NOT a wired feature):
does leak-free trailing per-team quarter-scoring variance recalibrate base Elo win-prob?

A measured calibration PROOF/probe (sibling of scripts/platformkit/proof_nba/*). NO live
path consumes its output (predictor/repricer/JointDistribution/cohesive_read/live_read do
NOT read combined_var/asof_runvar.parquet); only __main__ + tests/platform/test_nba_runvar.py
import it. For each game: strictly-prior trailing variance of per-quarter points over each
team's last N=10 games (snapshot-before-update; NaN when n_prior==0). --eval fits scalar alpha
on train (first 65%): logit_new = logit_base/(1+alpha*combined_var), evals Brier/LogLoss/ECE
vs base Elo on held-out 35%. W102 result = recalibration NULL (no held-out value), which is
why nothing downstream is wired. Probe artifact cols: game_id, home_var, away_var,
combined_var, n_prior. HONESTY: calibration != edge; NO edge claimed.
CLI: python -m domains.basketball_nba.asof_runvar [--eval] [--force]
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_QPTS  = _REPO_ROOT / "data" / "cache" / "nba_quarter_points.parquet"
_DEFAULT_GAMES = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "games.parquet"
_DEFAULT_OUT   = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "asof_runvar.parquet"

TRAILING_N: int = 10
TRAIN_FRAC: float = 0.65
OUTPUT_COLS: Tuple[str, ...] = ("game_id", "home_var", "away_var", "combined_var", "n_prior")
HONEST_NOTE = "DISCIPLINE: calibration != edge. NO edge claimed vs closing line."

# Step 1: per-(team, game) quarter-point lists

def _team_game_pts(qpts: pd.DataFrame) -> pd.DataFrame:
    """Aggregate quarter rows into (game_id, team_id, team_abbr, q_list) per team-game."""
    return (
        qpts.groupby(["game_id", "team_id", "team_abbr"])
        .agg(total_pts=("pts", "sum"), q_list=("pts", list))
        .reset_index()
    )

# Step 2: walk-forward per-team trailing variance (leak-free)

def _walk_forward_variance(
    team_game: pd.DataFrame,
    games_dates: pd.DataFrame,
    trailing_n: int = TRAILING_N,
) -> pd.DataFrame:
    """Snapshot-before-update trailing variance of per-quarter pts."""
    gd = games_dates[["game_id", "date"]].copy()
    gd["game_id"] = gd["game_id"].astype(str)
    gd["date"] = pd.to_datetime(gd["date"])

    tg = team_game.copy()
    tg["game_id"] = tg["game_id"].astype(str)
    tg = tg.merge(gd, on="game_id", how="left")
    tg = tg.sort_values(["date", "game_id"], kind="mergesort").reset_index(drop=True)

    history: dict = {}
    var_vals: List[float] = []
    n_prior_vals: List[int] = []

    for _, row in tg.iterrows():
        tid = int(row["team_id"])
        prior: List[List[float]] = history.get(tid, [])
        n_p = len(prior)
        n_prior_vals.append(n_p)

        if n_p == 0:
            var_vals.append(float("nan"))
        else:
            flat: List[float] = []
            for q_list in prior[-trailing_n:]:
                flat.extend(q_list)
            var_vals.append(float(np.var(flat, ddof=1)) if len(flat) >= 2 else float("nan"))

        q_raw = row.get("q_list", [])
        q_floats = [float(v) for v in q_raw] if isinstance(q_raw, list) else []
        if tid not in history:
            history[tid] = []
        history[tid].append(q_floats)

    tg["var_q_pts"] = var_vals
    tg["n_prior"] = n_prior_vals
    return tg[["game_id", "team_id", "var_q_pts", "n_prior"]]

# Step 3: pivot to home/away per game_id

def _pivot_home_away(team_var: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """Join variance to home/away sides using team_abbr == home_team/away_team."""
    g = games[["game_id", "home_team", "away_team"]].copy()
    g["game_id"] = g["game_id"].astype(str)
    tv = team_var.copy()
    merged = tv.merge(g, on="game_id", how="inner")

    if "team_abbr" in merged.columns:
        home_mask = merged["team_abbr"] == merged["home_team"]
        away_mask = merged["team_abbr"] == merged["away_team"]
    else:
        logger.warning("team_abbr missing; home/away pivot skipped.")
        home_mask = pd.Series(False, index=merged.index)
        away_mask = pd.Series(False, index=merged.index)

    home = merged[home_mask][["game_id", "var_q_pts", "n_prior"]].rename(
        columns={"var_q_pts": "home_var", "n_prior": "home_n_prior"})
    away = merged[away_mask][["game_id", "var_q_pts", "n_prior"]].rename(
        columns={"var_q_pts": "away_var", "n_prior": "away_n_prior"})

    out = home.merge(away, on="game_id", how="outer")
    out["combined_var"] = out["home_var"].fillna(0) + out["away_var"].fillna(0)
    out["n_prior"] = out[["home_n_prior", "away_n_prior"]].min(axis=1).fillna(0).astype("int64")
    return out[["game_id", "home_var", "away_var", "combined_var", "n_prior"]].sort_values(
        "game_id", kind="mergesort").reset_index(drop=True)

# Public build function

def build_asof_runvar(
    qpts_df: Optional[pd.DataFrame] = None,
    games_df: Optional[pd.DataFrame] = None,
    out_path: Optional[str] = None,
    force: bool = False,
) -> Path:
    """Build leak-free trailing quarter-variance parquet. Returns path written."""
    dest = Path(out_path) if out_path is not None else _DEFAULT_OUT
    if not force and dest.exists():
        logger.info("Output exists at %s; skipping rebuild.", dest)
        return dest

    if qpts_df is None:
        if not _DEFAULT_QPTS.exists():
            raise FileNotFoundError(f"nba_quarter_points.parquet not found at {_DEFAULT_QPTS}.")
        qpts_df = pd.read_parquet(_DEFAULT_QPTS)
    if games_df is None:
        if not _DEFAULT_GAMES.exists():
            raise FileNotFoundError(f"games.parquet not found at {_DEFAULT_GAMES}.")
        games_df = pd.read_parquet(_DEFAULT_GAMES)

    if len(qpts_df) == 0:
        out = pd.DataFrame(columns=list(OUTPUT_COLS))
        dest.parent.mkdir(parents=True, exist_ok=True)
        out.to_parquet(str(dest), index=False)
        return dest

    team_game = _team_game_pts(qpts_df)
    team_var = _walk_forward_variance(team_game, games_df)
    team_var = team_var.merge(
        team_game[["game_id", "team_id", "team_abbr"]].assign(game_id=lambda d: d["game_id"].astype(str)),
        on=["game_id", "team_id"], how="left",
    )
    games_s = games_df.copy()
    games_s["game_id"] = games_s["game_id"].astype(str)
    out = _pivot_home_away(team_var, games_s).reindex(columns=list(OUTPUT_COLS))
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(str(dest), index=False)
    logger.info("Wrote %d rows to %s", len(out), dest)
    return dest

# Metric helpers + eval

def _brier(p: np.ndarray, y: np.ndarray) -> float:
    m = np.isfinite(p) & np.isfinite(y)
    return float(np.mean((p[m] - y[m]) ** 2)) if m.sum() else float("nan")

def _log_loss(p: np.ndarray, y: np.ndarray, eps: float = 1e-7) -> float:
    m = np.isfinite(p) & np.isfinite(y)
    if not m.sum():
        return float("nan")
    pc = np.clip(p[m], eps, 1 - eps)
    return float(-np.mean(y[m] * np.log(pc) + (1 - y[m]) * np.log(1 - pc)))

def _ece(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> float:
    m = np.isfinite(p) & np.isfinite(y)
    if m.sum() < n_bins:
        return float("nan")
    p, y = p[m], y[m]
    total = sum(
        s * abs(p[b].mean() - y[b].mean())
        for lo, hi in zip(*(np.linspace(0, 1, n_bins + 1)[i:] for i in [0, 1]))
        for b in [(p >= lo) & (p < hi)]
        for s in [b.sum()] if s
    )
    return float(total / len(p))

def _logit(p: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    p = np.clip(p, eps, 1 - eps)
    return np.log(p / (1 - p))

def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))

def run_eval() -> None:
    """Fit alpha on train split; report Brier/LogLoss/ECE base vs recal."""
    from domains.basketball_nba.ingest_quarter_box import build_quarter_points
    qpts_df = pd.read_parquet(build_quarter_points(force=False))
    rv = pd.read_parquet(build_asof_runvar(qpts_df=qpts_df, force=True))

    import importlib
    adapter = importlib.import_module("domains.basketball_nba.adapter").NBAAdapter()
    bundle = adapter.feature_bundle(hypothesis=None, seasons=[])
    base_p = np.asarray(bundle.signal_col, dtype=float)
    target = np.asarray(bundle.target, dtype=float)

    # Reconstruct game_ids from games.parquet in adapter's sort order
    from domains.basketball_nba.ratings import walk_forward_elo
    gdf = pd.read_parquet(_DEFAULT_GAMES).copy()
    gdf["season"] = gdf["season"].apply(lambda s: int(str(s)[:4]) if isinstance(s, str) else int(s))
    wf = walk_forward_elo(gdf)
    wf["home_win"] = pd.to_numeric(wf.get("home_win"), errors="coerce")
    game_ids = list(wf[wf["home_win"].notna()]["game_id"].astype(str))

    if len(game_ids) != len(base_p):
        print("WARNING: game_id alignment failed; reporting base metrics only.")
        print(f"  Brier={_brier(base_p, target):.6f}  {HONEST_NOTE}")
        return

    joined = pd.DataFrame({"game_id": game_ids, "base_p": base_p, "target": target})
    rv_s = rv[["game_id", "combined_var", "n_prior"]].copy()
    rv_s["game_id"] = rv_s["game_id"].astype(str)
    joined = joined.merge(rv_s, on="game_id", how="left")
    mask = np.isfinite(joined["base_p"].values) & np.isfinite(joined["target"].values)
    joined = joined[mask].reset_index(drop=True)

    n = len(joined); n_train = int(n * TRAIN_FRAC)
    train, test = joined.iloc[:n_train], joined.iloc[n_train:]

    # Cold-start fill: combined_var is NaN/0 when a side has n_prior==0. Filling
    # with 0 would give the LEAST-informed games NO shrink (var=0 => full
    # confidence in logit/(1+alpha*var)) — i.e. cold-start rows masquerade as the
    # most confident. Instead, impute cold-start (n_prior_min==0) variance with
    # the TRAIN warm-row median variance (computed once, leak-free), so the
    # least-informed games get at least a typical amount of shrink rather than
    # the most confident treatment. n_prior is the carried min(home, away).
    def _fill_var(df: pd.DataFrame, warm_median: float) -> np.ndarray:
        v = df["combined_var"].astype(float).values.copy()
        n_p = pd.to_numeric(df.get("n_prior"), errors="coerce").fillna(0).values
        cold = (n_p <= 0) | ~np.isfinite(v)
        v[cold] = warm_median
        return np.clip(v, 0, None)

    t_n_prior = pd.to_numeric(train.get("n_prior"), errors="coerce").fillna(0).values
    warm_var = train["combined_var"].astype(float).values[
        (t_n_prior > 0) & np.isfinite(train["combined_var"].astype(float).values)]
    warm_median = float(np.median(warm_var)) if warm_var.size else 0.0

    t_base, t_y = train["base_p"].values, train["target"].values
    t_var = _fill_var(train, warm_median)
    t_logit = _logit(t_base)

    best_alpha, best_b = 0.0, float("inf")
    for alpha in np.linspace(0.0, 2.0, 41):
        recal_p = _sigmoid(t_logit / (1.0 + alpha * t_var))
        b = _brier(recal_p, t_y)
        if b < best_b:
            best_b, best_alpha = b, alpha

    test_base = test["base_p"].values; test_y = test["target"].values
    test_var = _fill_var(test, warm_median)
    recal_p = _sigmoid(_logit(test_base) / (1.0 + best_alpha * test_var))

    print(f"\n{'='*65}\n  asof_runvar EVAL — quarter-variance recalibration\n{'='*65}")
    print(f"  n={n} | train={n_train} | test={n-n_train} | alpha={best_alpha:.4f}")
    print(f"\n  {'Metric':<10}  {'Base':>10}  {'Recal':>10}  {'Delta':>10}")
    print(f"  {'-'*46}")
    metrics = [("Brier", _brier(test_base, test_y), _brier(recal_p, test_y)),
               ("LogLoss", _log_loss(test_base, test_y), _log_loss(recal_p, test_y)),
               ("ECE", _ece(test_base, test_y), _ece(recal_p, test_y))]
    for name, bv, rv2 in metrics:
        print(f"  {name:<10}  {bv:>10.6f}  {rv2:>10.6f}  {rv2-bv:>+10.6f}")
    print(f"{'='*65}")
    bv0, rv0 = metrics[0][1], metrics[0][2]
    if rv0 < bv0 - 1e-4:
        verdict = "IMPROVEMENT on Brier. Calibration only — no edge claimed."
    elif rv0 > bv0 + 1e-4:
        verdict = "NULL/WORSE on Brier. Variance adds no calibration value here."
    else:
        verdict = "MARGINAL — within noise. No meaningful improvement; no edge claimed."
    print(f"\n  VERDICT: {verdict}\n  {HONEST_NOTE}\n")

# CLI

if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Build leak-free quarter-variance features.")
    ap.add_argument("--eval", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    dest = build_asof_runvar(out_path=args.out, force=args.force)
    df = pd.read_parquet(str(dest))
    print(f"Wrote {dest}\nRows: {len(df)} | home_var non-null: {df['home_var'].notna().sum()}")
    if args.eval:
        run_eval()
