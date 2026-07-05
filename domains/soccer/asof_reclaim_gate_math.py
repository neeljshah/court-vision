"""domains.soccer.asof_reclaim_gate_math -- year-bucketed CROSS-CORPUS math
companion for the ON-DISK RECLAIM gate (asof_features.parquet /
asof_xg_proxy.parquet candidates vs the Poisson O/U 2.5 base).

MIRRORS scripts/platformkit/geo/soccer_altitude_gate_math.py's year_corpora /
direction pattern (same clustered-DM both-directions cross-corpus gate) but
adapted to THIS adapter's actual market: O/U 2.5 goals via Poisson
p_over25/target_over25 (domains.soccer.ratings.walk_forward_goals), not
Skellam home-win. Splitting the 11-season, single-source corpus into
year-buckets gives INDEPENDENT-ENOUGH train/test pairs for a real cross-
corpus check -- honest upgrade over a single 70/30 split, though still one
underlying data source (football-data.co.uk); never claimed as a second
independent corpus.

No CLI, no I/O beyond reading matches.parquet / an as-of parquet path.
Kept <=300 LOC per file (precedent: soccer_altitude_gate_math.py / _run.py split).

PURE pandas/numpy + domains.soccer.ratings + the shared clustered DM.
No src.*/kernel.* imports; no domains.nba/mlb/tennis imports (F5). ASCII only.
CALIBRATION only; NO $/edge; REJECT is the honest, successful default verdict.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from domains.soccer.ratings import walk_forward_goals
from scripts.platformkit.eval_gate.dm_test import diebold_mariano

_REPO = Path(__file__).resolve().parents[2]
_MATCHES = _REPO / "data" / "domains" / "soccer" / "matches.parquet"
_ASOF_FEATURES = _REPO / "data" / "domains" / "soccer" / "asof_features.parquet"
_ASOF_XG_PROXY = _REPO / "data" / "domains" / "soccer" / "asof_xg_proxy.parquet"

_NULL_COL = "planted_null"
_EPS = 0.05
_MIN_BSS = 0.0          # base must carry non-degenerate skill vs the base rate
_MIN_GAMES_PER_FOLD = 100
MIN_PRIOR = 5           # both teams need >= N strictly-prior matches for "covered"


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1.0 - 1e-6)
    return np.log(p / (1.0 - p))


def _zstd(x: np.ndarray, mu: float, sd: float) -> np.ndarray:
    return (np.asarray(x, dtype=float) - mu) / (sd if sd > 0 else 1.0)


def _fit_logistic(X: np.ndarray, y: np.ndarray, iters: int = 200,
                  lr: float = 0.2, l2: float = 1e-4) -> np.ndarray:
    n, d = X.shape
    Xb = np.hstack([np.ones((n, 1)), X])
    w = np.zeros(d + 1)
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-np.clip(Xb @ w, -30, 30)))
        grad = Xb.T @ (p - y) / n + l2 * np.concatenate([[0.0], w[1:]])
        w -= lr * grad
    return w


def _predict(w: np.ndarray, X: np.ndarray) -> np.ndarray:
    Xb = np.hstack([np.ones((len(X), 1)), X])
    return 1.0 / (1.0 + np.exp(-np.clip(Xb @ w, -30, 30)))


def _brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((np.asarray(p) - np.asarray(y)) ** 2))


def _log_loss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(np.asarray(p, dtype=float), 1e-7, 1 - 1e-7)
    y = np.asarray(y, dtype=float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def build_corpus(asof_path: Path = _ASOF_FEATURES) -> pd.DataFrame:
    """Leak-free walk-forward Poisson p_over25 + LEFT-MERGED as-of candidate
    columns (from *asof_path*) + planted null. Devigged close is NOT used here
    (see asof_features_gate.build_candidate_frame for the base-vs-close path);
    this module's job is the calibration-only cross-corpus feature check."""
    mdf = pd.read_parquet(_MATCHES)
    mdf["event_id"] = mdf["event_id"].astype(str)
    total_goals = (pd.to_numeric(mdf["fthg"], errors="coerce")
                   + pd.to_numeric(mdf["ftag"], errors="coerce"))
    mdf["target_over25"] = (total_goals >= 3).astype(float)
    mdf = mdf[total_goals.notna()].copy()

    wf = walk_forward_goals(mdf)
    wf["event_id"] = wf["event_id"].astype(str)
    wf["p_over25"] = np.clip(wf["p_over25"].astype(float), 1e-6, 1 - 1e-6)

    adf = pd.read_parquet(asof_path)
    adf["event_id"] = adf["event_id"].astype(str)
    adf = adf.drop_duplicates("event_id", keep="first")

    feat = wf.merge(
        adf.drop(columns=[c for c in ("date",) if c in adf.columns]),
        on="event_id", how="left")
    feat["season"] = pd.to_datetime(feat["date"]).dt.year
    rng = np.random.default_rng(12345)
    feat[_NULL_COL] = rng.standard_normal(len(feat))
    return feat


def year_corpora(feat: pd.DataFrame,
                  min_games: int = _MIN_GAMES_PER_FOLD) -> List[Tuple[str, pd.DataFrame]]:
    """Bucket by calendar year, merging any year under min_games into the next
    year forward (never backward -- keeps walk-forward direction sane)."""
    years = sorted(feat["season"].dropna().unique())
    buckets: List[Tuple[str, pd.DataFrame]] = []
    pending = pd.DataFrame()
    pending_label = None
    for y in years:
        chunk = feat[feat["season"] == y]
        pending = pd.concat([pending, chunk]) if len(pending) else chunk
        pending_label = "%s-%d" % (pending_label.split("-")[0], y) if pending_label else str(y)
        if len(pending) >= min_games:
            buckets.append((pending_label, pending.copy()))
            pending = pd.DataFrame()
            pending_label = None
    if len(pending) and buckets:
        label, prev_df = buckets[-1]
        buckets[-1] = (label + "+" + pending_label, pd.concat([prev_df, pending]))
    return buckets


def _covered(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Rows where both teams clear MIN_PRIOR strictly-prior matches AND col is finite."""
    home_n = df.get("home_n_prior", pd.Series(0, index=df.index)).fillna(0)
    away_n = df.get("away_n_prior", pd.Series(0, index=df.index)).fillna(0)
    ok = (home_n >= MIN_PRIOR) & (away_n >= MIN_PRIOR) & df[col].notna()
    return df[ok]


def direction(train: pd.DataFrame, test: pd.DataFrame, col: str,
             eps: float = _EPS) -> Dict[str, object]:
    """Fit BASE (Poisson p_over25 logit) and +FEATURE (logit + col z-score) on
    TRAIN, score on TEST. Leak-free walk-forward, clustered-DM by event_id."""
    tr = _covered(train, col).dropna(subset=["p_over25", "target_over25"]).copy()
    te = _covered(test, col).dropna(subset=["p_over25", "target_over25"]).copy()
    if len(tr) < _MIN_GAMES_PER_FOLD or len(te) < _MIN_GAMES_PER_FOLD:
        return {"ok": False, "reason": "thin covered corpus",
                "n_train": int(len(tr)), "n_test": int(len(te))}

    z_tr = _logit(tr["p_over25"].to_numpy())
    z_te = _logit(te["p_over25"].to_numpy())
    fmu, fsd = float(tr[col].mean()), float(tr[col].std())
    f_tr = _zstd(tr[col].to_numpy(), fmu, fsd)
    f_te = _zstd(te[col].to_numpy(), fmu, fsd)
    y_tr = tr["target_over25"].to_numpy(dtype=float)
    y_te = te["target_over25"].to_numpy(dtype=float)
    gid_te = te["event_id"].astype(str).to_numpy()

    w_base = _fit_logistic(z_tr.reshape(-1, 1), y_tr)
    w_feat = _fit_logistic(np.column_stack([z_tr, f_tr]), y_tr)
    p_base = _predict(w_base, z_te.reshape(-1, 1))
    p_feat = _predict(w_feat, np.column_stack([z_te, f_te]))

    bb, bf = _brier(p_base, y_te), _brier(p_feat, y_te)
    lb, lf = _log_loss(p_base, y_te), _log_loss(p_feat, y_te)
    const = np.full(len(y_te), float(y_tr.mean()))
    br_const = _brier(const, y_te)
    bss_base = 1.0 - bb / br_const if br_const > 0 else 0.0
    base_degenerate = bool(bss_base < _MIN_BSS)
    d = (p_base - y_te) ** 2 - (p_feat - y_te) ** 2
    dm = diebold_mariano(d, gid_te)
    feat_wins = bool(bf < bb and lf < lb and dm.p_value < eps and not base_degenerate)
    return {"ok": True, "brier_base": round(bb, 6), "brier_feat": round(bf, 6),
            "brier_delta": round(bb - bf, 7), "logloss_base": round(lb, 6),
            "logloss_feat": round(lf, 6), "dm_stat": round(dm.dm_stat, 4),
            "dm_p": round(dm.p_value, 6), "n_clusters": dm.n_clusters,
            "base_bss_vs_const": round(bss_base, 5), "base_degenerate": base_degenerate,
            "feat_wins": feat_wins, "n_train": int(len(tr)), "n_test": int(len(te))}


__all__ = ["build_corpus", "year_corpora", "direction", "_covered",
           "_NULL_COL", "_EPS", "_MIN_BSS", "_MIN_GAMES_PER_FOLD", "MIN_PRIOR",
           "_MATCHES", "_ASOF_FEATURES", "_ASOF_XG_PROXY"]
