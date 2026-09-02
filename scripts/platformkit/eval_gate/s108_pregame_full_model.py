"""S108 -- a FULL-FEATURE regularised pregame model per sport, screened against the incumbent.

Every prior screen added ONE feature to logit(incumbent). This fits the whole as-of feature
set at once, with logit(incumbent) as an OFFSET (coefficient fixed at 1), so the model can
only learn the RESIDUAL the incumbent misses:

  (a) elastic-net logistic  -- own FISTA proximal solver, true offset, penalty grid;
  (b) HistGradientBoosting  -- sklearn HistGradientBoostingRegressor on the Newton working
      response z = (y - p0) / (p0 (1 - p0)) with weights p0 (1 - p0), so eta = logit(p0) + f(x):
      the offset is exact, the boosting is one Newton step from it (glmboost-style).

NESTED walk-forward on the SCREEN side of the frozen partition only: expanding outer folds by
event_date (>= 5), inner expanding folds inside each train window pick the penalty, and a blanket
date GAP before every test window that is a superset of the harness's 48 h same-team purge and
the row's 1-day embargo. Standardisation and median imputation are computed inside the train fold.

No charge, no seal, no ledger read or write; the verdict side is never built. A REJECT is a
success. Calibration language only.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.pbo import cscv_pbo
from scripts.platformkit.eval_gate.s108_features import ROOT, build

IMPROVEMENT_BAR = 0.004          # Q3: the register row's bar, never moved
OUTER_FOLDS, INNER_FOLDS, GAP_DAYS = 6, 3, 2
LAMBDAS = (0.001, 0.003, 0.01, 0.03, 0.1, 0.3)
L1_RATIO = 0.5
HGB_GRID = ({"max_depth": 2, "l2_regularization": 10.0}, {"max_depth": 3, "l2_regularization": 10.0},
            {"max_depth": 2, "l2_regularization": 100.0})
HGB_FIXED = {"max_iter": 150, "learning_rate": 0.05, "min_samples_leaf": 50,
             "early_stopping": False, "random_state": 20260903}
MIN_TRAIN = 120
CLIP = 1e-3


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), CLIP, 1.0 - CLIP)
    return np.log(p / (1.0 - p))


def _sigmoid(eta: np.ndarray) -> np.ndarray:
    return np.clip(1.0 / (1.0 + np.exp(-np.clip(eta, -30.0, 30.0))), CLIP, 1.0 - CLIP)


def _spectral(X: np.ndarray, iters: int = 30) -> float:
    v = np.ones(X.shape[1]) / math.sqrt(max(1, X.shape[1]))
    for _ in range(iters):
        v = X.T @ (X @ v)
        norm = float(np.linalg.norm(v)) or 1.0
        v /= norm
    return float(np.linalg.norm(X @ v))


def enet_logistic(X: np.ndarray, y: np.ndarray, offset: np.ndarray, lam: float,
                  l1_ratio: float = L1_RATIO, iters: int = 400, sigma=None) -> tuple:
    """FISTA elastic-net logistic with a TRUE offset (its coefficient is fixed at 1)."""
    n, p = X.shape
    lip = 0.25 * (sigma if sigma is not None else _spectral(X)) ** 2 / n + lam * (1.0 - l1_ratio)
    lip = max(lip, 1e-8)
    beta, zb, alpha, za, t = np.zeros(p), np.zeros(p), 0.0, 0.0, 1.0
    for _ in range(iters):
        resid = _sigmoid(offset + za + X @ zb) - y
        grad = X.T @ resid / n + lam * (1.0 - l1_ratio) * zb
        step = zb - grad / lip
        new_beta = np.sign(step) * np.maximum(np.abs(step) - lam * l1_ratio / lip, 0.0)
        new_alpha = za - 4.0 * float(resid.mean())
        new_t = 0.5 * (1.0 + math.sqrt(1.0 + 4.0 * t * t))
        zb = new_beta + (t - 1.0) / new_t * (new_beta - beta)
        za = new_alpha + (t - 1.0) / new_t * (new_alpha - alpha)
        done = float(np.max(np.abs(new_beta - beta))) < 1e-7 and abs(new_alpha - alpha) < 1e-7
        beta, alpha, t = new_beta, new_alpha, new_t
        if done:
            break
    return beta, alpha


def enet_predict(X: np.ndarray, offset: np.ndarray, fit: tuple) -> np.ndarray:
    return _sigmoid(offset + fit[1] + X @ fit[0])


def hgb_offset(Xtr, ytr, offtr, Xte, offte, cfg: dict) -> np.ndarray:
    """One Newton step of HistGradientBoosting from the offset; the offset stays exact."""
    p0 = _sigmoid(offtr)
    w = np.clip(p0 * (1.0 - p0), 1e-3, None)
    model = HistGradientBoostingRegressor(**{**HGB_FIXED, **cfg}).fit(
        Xtr, (ytr - p0) / w, sample_weight=w)
    return _sigmoid(offte + model.predict(Xte))


def folds(dates: np.ndarray, k: int, gap_days: int = GAP_DAYS) -> list:
    """Expanding folds in date order; every train row sits >= gap_days before the test window."""
    n = len(dates)
    edges = [round(i * n / (k + 1)) for i in range(k + 2)]
    out = []
    for i in range(1, k + 1):
        test = np.arange(edges[i], edges[i + 1])
        if not len(test):
            continue
        cutoff = dates[test[0]] - np.timedelta64(gap_days, "D")
        train = np.flatnonzero(dates <= cutoff)
        train = train[train < test[0]]
        if len(train) >= MIN_TRAIN:
            out.append((train, test))
    return out


def _prep(X: pd.DataFrame, train: np.ndarray, test: np.ndarray) -> tuple:
    """Train-fold median imputation then train-fold standardisation, applied to both sides."""
    raw = X.to_numpy(dtype=float)
    med = np.nanmedian(raw[train], axis=0)
    med = np.where(np.isfinite(med), med, 0.0)
    filled = np.where(np.isfinite(raw), raw, med)
    mu, sd = filled[train].mean(axis=0), filled[train].std(axis=0)
    sd = np.where(sd > 1e-12, sd, 1.0)
    z = (filled - mu) / sd
    return z[train], z[test]


def _grid_oof(bundle: dict, k: int = OUTER_FOLDS) -> dict:
    """Per outer fold: every grid config's test predictions, plus the inner-CV pick."""
    X, y, offset = bundle["X"], bundle["y"], _logit(bundle["p_inc"])
    split = folds(bundle["dates"], k)
    if len(split) < 5:
        raise ValueError("%s produced only %d outer folds (>= 5 required)"
                         % (bundle["sport"], len(split)))
    rows, enet_cols, hgb_cols, picks = [], [], [], []
    for fold, (train, test) in enumerate(split):
        Ztr, Zte = _prep(X, train, test)
        sigma = _spectral(Ztr)
        inner = folds(bundle["dates"][train], INNER_FOLDS)
        fits = [enet_logistic(Ztr, y[train], offset[train], lam, sigma=sigma) for lam in LAMBDAS]
        enet_p = np.column_stack([enet_predict(Zte, offset[test], f) for f in fits])
        hgb_p = np.column_stack([hgb_offset(Ztr, y[train], offset[train], Zte, offset[test], c)
                                 for c in HGB_GRID])
        e_score, h_score = np.zeros(len(LAMBDAS)), np.zeros(len(HGB_GRID))
        ay, ao = y[train], offset[train]
        for itr, ite in inner:
            Wtr, Wte = _prep(X.iloc[train], itr, ite)
            isig = _spectral(Wtr)
            for j, lam in enumerate(LAMBDAS):
                p = enet_predict(Wte, ao[ite], enet_logistic(Wtr, ay[itr], ao[itr], lam, sigma=isig))
                e_score[j] += float(np.mean((p - ay[ite]) ** 2))
            for j, cfg in enumerate(HGB_GRID):
                p = hgb_offset(Wtr, ay[itr], ao[itr], Wte, ao[ite], cfg)
                h_score[j] += float(np.mean((p - ay[ite]) ** 2))
        e_pick, h_pick = int(np.argmin(e_score)), int(np.argmin(h_score))
        picks.append({"fold": fold, "n_train": int(len(train)), "n_test": int(len(test)),
                      "train_end": str(bundle["dates"][train[-1]]),
                      "test_start": str(bundle["dates"][test[0]]),
                      "lambda": LAMBDAS[e_pick], "hgb": HGB_GRID[h_pick],
                      "inner_folds": len(inner),
                      "nonzero_coefs": int(np.count_nonzero(fits[e_pick][0]))})
        enet_cols.append(enet_p)
        hgb_cols.append(hgb_p)
        for r, idx in enumerate(test):
            rows.append({"fold": fold, "row": int(idx), "p_enet": float(enet_p[r, e_pick]),
                         "p_hgb": float(hgb_p[r, h_pick])})
    return {"rows": rows, "picks": picks,
            "enet_grid": np.vstack(enet_cols), "hgb_grid": np.vstack(hgb_cols)}


def _score(d: np.ndarray, clusters: np.ndarray) -> dict:
    if len(set(map(str, clusters))) < 2:
        return {"clusters": 1, "mean": float(np.mean(d)), "ci95": None, "p": None}
    dm = diebold_mariano(d, list(map(str, clusters)))
    return {"clusters": dm.n_clusters, "mean": float(dm.mean_diff),
            "ci95": [float(dm.ci95[0]), float(dm.ci95[1])], "p": float(dm.p_value)}


def run_sport(sport: str, out_dir: Path, k: int = OUTER_FOLDS) -> dict:
    bundle = build(sport)
    grid = _grid_oof(bundle, k)
    order = np.array([r["row"] for r in grid["rows"]])
    y, p_inc = bundle["y"][order], bundle["p_inc"][order]
    loss_inc = (p_inc - y) ** 2
    frame = pd.DataFrame({
        "event_id": bundle["X"].index.to_numpy()[order], "event_date": bundle["dates"][order],
        "corpus_unit": bundle["units"][order], "cluster_id": bundle["cluster_ids"][order],
        "fold": [r["fold"] for r in grid["rows"]], "y": y, "p_incumbent": p_inc,
        "p_enet": [r["p_enet"] for r in grid["rows"]], "p_hgb": [r["p_hgb"] for r in grid["rows"]]})
    frame["loss_incumbent"] = loss_inc
    result = {"sport": sport, "incumbent": bundle["incumbent"], "n_scored": int(len(order)),
              "n_screen": bundle["n_screen"], "n_states": bundle["n_states"],
              "n_features": int(bundle["X"].shape[1]), "n_missing_cols": bundle["n_missing_cols"],
              "screen_sha256": bundle["screen_sha256"], "partition_basis": bundle["partition_basis"],
              "cluster_key": bundle["cluster_key"], "improvement_bar": IMPROVEMENT_BAR,
              "brier_incumbent": float(loss_inc.mean()), "folds": grid["picks"],
              "sources": bundle["sources"], "n_refused": len(bundle["refusals"]),
              "refusals": bundle["refusals"], "dropped": bundle["dropped"], "arms": {}}
    for arm, column, matrix in (("elastic_net", "p_enet", grid["enet_grid"]),
                                ("hgb_offset", "p_hgb", grid["hgb_grid"])):
        p = frame[column].to_numpy(dtype=float)
        loss = (p - y) ** 2
        frame["loss_" + arm] = loss
        frame["d_" + arm] = loss_inc - loss
        pbo = cscv_pbo(np.clip(matrix, 0.0, 1.0), y)
        stats = {"brier_model": float(loss.mean()), "improvement": float((loss_inc - loss).mean()),
                 "unit_dm": _score(loss_inc - loss, frame["corpus_unit"].to_numpy()),
                 "declared_dm": _score(loss_inc - loss, frame["cluster_id"].to_numpy()),
                 "pbo": float(pbo.pbo), "n_configs": int(matrix.shape[1])}
        unit = stats["unit_dm"]
        stats["clears_bar"] = bool(stats["improvement"] >= IMPROVEMENT_BAR
                                   and unit["ci95"] is not None and unit["ci95"][0] > 0.0)
        result["arms"][arm] = stats
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / ("s108_%s_2026-09-03.csv" % sport)
    frame.to_csv(path, index=False)
    result["artifact"] = path.as_posix()
    return result


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="S108 full-feature pregame model screen")
    ap.add_argument("--sports", default="nba,mlb,soccer,tennis")
    ap.add_argument("--outer-folds", type=int, default=OUTER_FOLDS)
    ap.add_argument("--out-dir", type=Path, default=ROOT / "data" / "cache" / "eval_gate")
    args = ap.parse_args(argv)
    results = []
    for sport in [s for s in args.sports.split(",") if s]:
        result = run_sport(sport, args.out_dir, k=args.outer_folds)
        results.append(result)
        for arm, stats in result["arms"].items():
            print("%-7s %-12s n=%-6d p=%-4d brier_inc=%.6f brier=%.6f improvement=%+.6f "
                  "unit_ci=%s pbo=%.3f clears=%s"
                  % (sport, arm, result["n_scored"], result["n_features"],
                     result["brier_incumbent"], stats["brier_model"], stats["improvement"],
                     stats["unit_dm"]["ci95"], stats["pbo"], stats["clears_bar"]), flush=True)
    path = args.out_dir / "s108_pregame_full_model_2026-09-03.json"
    path.write_text(json.dumps(results, indent=1, sort_keys=True, default=str), encoding="ascii")
    print("summary %s" % path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
