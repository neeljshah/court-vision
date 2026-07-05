# -*- coding: utf-8 -*-
"""scripts.platformkit.geo.soccer_altitude_gate_math -- math companion for
soccer_altitude_gate_run.py (kept <=300 LOC per file; split by precedent).

Corpus construction (leak-free walk-forward Skellam win-prob + altitude_m
descriptor + planted null) and the per-direction logistic-regression /
clustered-DM scoring primitive. No CLI, no I/O beyond reading the source
parquet in build_corpus(). See soccer_altitude_gate_run.py module docstring
for the full gate rationale.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy.stats import skellam

from domains.soccer_intl.ratings import walk_forward_goals
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.scoring import brier, log_loss
from scripts.platformkit.geo.travel_scouting_common import altitude_m

_REPO = Path(__file__).resolve().parents[3]
_RESULTS = _REPO / "data" / "domains" / "soccer_intl" / "results.parquet"

_NULL_COL = "planted_null"
_EPS = 0.05
_MIN_BSS = 0.01
_MIN_GAMES_PER_FOLD = 100


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


def p_home_skellam(lam_home: np.ndarray, lam_away: np.ndarray) -> np.ndarray:
    """P(home goals > away goals) via the Skellam distribution (difference of
    two independent Poissons) -- a closed-form read-off, no new estimation."""
    lam_home = np.asarray(lam_home, dtype=float)
    lam_away = np.asarray(lam_away, dtype=float)
    # P(X - Y > 0) = 1 - CDF_skellam(0) ; sf(0) already excludes the draw mass
    return skellam.sf(0, lam_home, lam_away)


def build_corpus() -> pd.DataFrame:
    """Leak-free walk-forward Poisson lambdas + derived skellam win-prob +
    per-match host-venue altitude_m (matched, not a model artifact) + planted
    null. Draws are natively handled by Skellam (P(home win) excludes them);
    the outcome label is a strict home-win binary, matching the NBA gate's
    home_win convention."""
    df = pd.read_parquet(_RESULTS)
    df = df.dropna(subset=["home_score", "away_score", "date", "city"]).copy()
    feat = walk_forward_goals(df)
    feat["p_home_skellam"] = p_home_skellam(feat["lam_home"], feat["lam_away"])
    feat["home_win"] = (feat["fthg"] > feat["ftag"]).astype(float)
    feat["altitude_m"] = feat.apply(
        lambda r: altitude_m(r["city"], r["country"]), axis=1)
    feat["season"] = pd.to_datetime(feat["date"]).dt.year
    rng = np.random.default_rng(12345)
    feat[_NULL_COL] = rng.standard_normal(len(feat))
    return feat


def year_corpora(feat: pd.DataFrame, min_games: int = _MIN_GAMES_PER_FOLD) -> List[Tuple[str, pd.DataFrame]]:
    """Bucket by calendar year, merging any year under min_games into the
    next year forward (never backward, keeps walk-forward direction sane)."""
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


def direction(train: pd.DataFrame, test: pd.DataFrame, col: str,
             eps: float = _EPS) -> Dict[str, object]:
    """Fit BASE (skellam logit) and +FEATURE (skellam logit + col) on TRAIN,
    score on TEST. Leak-free walk-forward, clustered-DM by (date,home,away)."""
    tr = train.dropna(subset=[col, "p_home_skellam", "home_win"]).copy()
    te = test.dropna(subset=[col, "p_home_skellam", "home_win"]).copy()
    if len(tr) < _MIN_GAMES_PER_FOLD or len(te) < _MIN_GAMES_PER_FOLD:
        return {"ok": False, "reason": "thin corpus after dropna",
                "n_train": int(len(tr)), "n_test": int(len(te))}

    z_tr = _logit(tr["p_home_skellam"].to_numpy())
    z_te = _logit(te["p_home_skellam"].to_numpy())
    fmu, fsd = float(tr[col].mean()), float(tr[col].std())
    f_tr = _zstd(tr[col].to_numpy(), fmu, fsd)
    f_te = _zstd(te[col].to_numpy(), fmu, fsd)
    y_tr = tr["home_win"].to_numpy(dtype=float)
    y_te = te["home_win"].to_numpy(dtype=float)
    gid_te = (te["date"].astype(str) + "_" + te["home_team"].astype(str) +
             "_" + te["away_team"].astype(str)).to_numpy()

    w_base = _fit_logistic(z_tr.reshape(-1, 1), y_tr)
    w_feat = _fit_logistic(np.column_stack([z_tr, f_tr]), y_tr)
    p_base = _predict(w_base, z_te.reshape(-1, 1))
    p_feat = _predict(w_feat, np.column_stack([z_te, f_te]))

    bb, bf = float(brier(p_base, y_te)), float(brier(p_feat, y_te))
    lb, lf = float(log_loss(p_base, y_te)), float(log_loss(p_feat, y_te))
    const = np.full(len(y_te), float(y_tr.mean()))
    bss_base = 1.0 - bb / float(brier(const, y_te)) if brier(const, y_te) > 0 else 0.0
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


__all__ = ["build_corpus", "year_corpora", "direction", "p_home_skellam",
           "_NULL_COL", "_EPS", "_MIN_BSS", "_MIN_GAMES_PER_FOLD", "_RESULTS"]
