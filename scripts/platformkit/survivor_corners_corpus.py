"""scripts.platformkit.survivor_corners_corpus -- corpus build + leak-free fit/split
helpers for the corners survivor-scrutiny run (sibling-split from
survivor_corners_combo_gate.py for the <=300 LOC rule). NO new scoring trick: a plain
TRAIN-only logistic + the gate's pregame->state bridge.

Calibration only; NO $/ROI/edge anywhere. numpy/pandas + stdlib. ASCII.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.scoring import brier

_REPO = Path(__file__).resolve().parents[2]
MATCHES = _REPO / "data" / "domains" / "soccer" / "matches.parquet"
MATCH_STATS = _REPO / "data" / "domains" / "soccer" / "match_stats.parquet"

CORPUS_A = ("E0", "E1")
CORPUS_B = ("SP1", "I1")
FAMILY = ("diff_corners_asof", "diff_fouls_asof", "diff_yellow_asof",
          "diff_red_asof", "diff_sot_ratio_asof")
TARGET = "diff_corners_asof"


def logit(p) -> np.ndarray:
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return np.log(p / (1.0 - p))


def sigmoid(z) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0)))


def build_corpus(divs: Sequence[str], matches: pd.DataFrame,
                 match_stats: pd.DataFrame, layer: pd.DataFrame) -> pd.DataFrame:
    """Real EW-Poisson base + the 5 as-of diffs, mapped to the gate's state contract.

    One row per match (event_id). state_diff = logit(p_poisson); frac_elapsed = 1.0;
    outcome = y_home. NaN feature rows are kept here and DROPPED per-candidate later
    (we never 0-fill a debut).
    """
    from domains.soccer.pregame_winprob import walk_forward
    g = matches[matches["div"].isin(divs)].copy()
    ms = (match_stats[match_stats["div"].isin(divs)]
          if "div" in match_stats.columns else match_stats)
    wf = walk_forward(g, ms)
    wf["event_id"] = wf["event_id"].astype(str)
    keep = ["event_id", *[c for c in FAMILY if c in layer.columns]]
    merged = wf.merge(layer[keep], on="event_id", how="left")
    merged = merged.sort_values(["date", "div", "home_team", "away_team"],
                                kind="mergesort").reset_index(drop=True)
    out = pd.DataFrame({
        "game_id": merged["event_id"].astype(str),
        "asof_idx": 0,
        "state_diff": logit(merged["p_poisson"].to_numpy(float)),
        "frac_elapsed": 1.0,
        "outcome": merged["y_home"].astype(int),
    })
    for c in FAMILY:
        out[c] = merged[c].to_numpy(float) if c in merged.columns else np.nan
    return out


def aligned(base: pd.DataFrame, col: str) -> pd.DataFrame:
    """Base rows that have a non-NaN value for `col` (one candidate's merge universe)."""
    return base.dropna(subset=[col]).reset_index(drop=True)


def detail_frame(base: pd.DataFrame, col: str) -> pd.DataFrame:
    """A gate-ready DETAIL frame for ONE candidate column, NaN rows dropped."""
    keep = aligned(base, col)
    keep = keep[["game_id", "asof_idx", col]].rename(columns={col: "detail"})
    return keep[["game_id", "asof_idx", "detail"]]


def _fit(X: np.ndarray, y: np.ndarray, iters: int = 300, lr: float = 0.1) -> np.ndarray:
    Xb = np.hstack([np.ones((X.shape[0], 1)), X])
    w = np.zeros(Xb.shape[1])
    for _ in range(iters):
        p = sigmoid(Xb @ w)
        w -= lr * (Xb.T @ (p - y) / len(y))
    return w


def _pred(w: np.ndarray, X: np.ndarray) -> np.ndarray:
    return sigmoid(np.hstack([np.ones((X.shape[0], 1)), X]) @ w)


def split_brier_delta(sub: pd.DataFrame, col: str, frac: float = 0.5,
                      boot_seed: Optional[int] = None) -> float:
    """One chronological-split held-out Brier-delta (base - base+feat); +ve => feat wins.

    Leak-free like-for-like: BASE = sigmoid(w0+w1*state_diff), BASE+feat adds the
    standardized feature, both fit on TRAIN, scored on the held-out tail. boot_seed
    bootstrap-resamples the TRAIN block (the FIXED later tail is never touched -> no
    leak) so the seed-ensemble can expose an unstable single-seed lift.
    """
    n = len(sub)
    if n < 200:
        return float("nan")
    cut = int(n * frac)
    tr, te = sub.iloc[:cut], sub.iloc[cut:]
    if len(tr) < 50 or len(te) < 50:
        return float("nan")
    if boot_seed is not None:
        rng = np.random.default_rng(boot_seed)
        tr = tr.iloc[rng.integers(0, len(tr), size=len(tr))]
    y_tr, y_te = tr["outcome"].to_numpy(float), te["outcome"].to_numpy(float)
    sd_tr, sd_te = tr["state_diff"].to_numpy(float), te["state_diff"].to_numpy(float)
    f_tr, f_te = tr[col].to_numpy(float), te[col].to_numpy(float)
    mu, s = float(f_tr.mean()), float(f_tr.std() or 1.0)
    fz_tr, fz_te = (f_tr - mu) / s, (f_te - mu) / s
    wb = _fit(np.column_stack([sd_tr]), y_tr)
    wf = _fit(np.column_stack([sd_tr, fz_tr]), y_tr)
    pb = _pred(wb, np.column_stack([sd_te]))
    pf = _pred(wf, np.column_stack([sd_te, fz_te]))
    return float(brier(pb, y_te) - brier(pf, y_te))


def seed_split_deltas(base: pd.DataFrame, col: str, seeds: Sequence[int],
                      splits: Sequence[float]) -> Dict[str, List[float]]:
    """Seed-ensemble (TRAIN bootstrap) x multi-split held-out Brier-deltas for `col`.

    A single-seed lift collapses here when the train estimate is unstable; the caller
    reports mean AND p10. Splits are >=3 chronological cut points.
    """
    sub0 = aligned(base, col)
    seed_d = [split_brier_delta(sub0, col, frac=0.5, boot_seed=sd) for sd in seeds]
    split_d = [split_brier_delta(sub0, col, frac=fr) for fr in splits]
    return {"seed": [d for d in seed_d if np.isfinite(d)],
            "split": [d for d in split_d if np.isfinite(d)]}


__all__ = ["MATCHES", "MATCH_STATS", "CORPUS_A", "CORPUS_B", "FAMILY", "TARGET",
           "logit", "sigmoid", "build_corpus", "aligned", "detail_frame",
           "split_brier_delta", "seed_split_deltas"]
