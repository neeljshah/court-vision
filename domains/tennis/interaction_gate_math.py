"""domains.tennis.interaction_gate_math -- pure math for Family A1-T (LOC-split).

Corpus assembly, T1/T2 feature construction, and the generic 1-feature-base
fit/score helpers for the tennis_interactions_v1 gate. Split from
interaction_gate.py for the <=300 LOC/file rule; interaction_gate.py owns
orchestration (run/main/CLI) and imports every symbol below.

Formulas per PREREG_AMENDMENT_A1_2026-07-05.md Family A1-T:
  T1 tennis_surface_hold_regime: added = [blended_diff, surface_residual]
     blended_diff = p1_hold_pct_asof - p2_hold_pct_asof
     surface_residual = (p1_hold_pct_<surf>_asof - p2_hold_pct_<surf>_asof) - blended_diff
  T2 tennis_surface_serve_return_gap: added = [surface_diff, surface_diff * low_regime]
     surface_diff = p1_hold_pct_<surf>_asof - p2_hold_pct_<surf>_asof
     low_regime = 1 iff BOTH players' surface hold% < TRAIN-ONLY tour-surface median

`surf` is the ROW's OWN surface (lowercased); rows on Carpet/Unknown or below
MIN_PRIOR fall back to NaN (score_with_fallback then routes them to p_base).

No src.*/kernel.* imports. ASCII; <=300 LOC.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import numpy as np
import pandas as pd

from domains.tennis.adapter_helpers import _devig_prob
from domains.tennis.elo_walkforward import walk_forward_elo
from scripts.platformkit.combo import stack_fit as sf

_REPO = Path(__file__).resolve().parents[2]
_ODDS = _REPO / "data/domains/tennis/odds.parquet"

MIN_PRIOR = 5                    # both players need >= N strictly-prior matches
_SURFACES = ("hard", "clay", "grass")  # Carpet/Unknown -> no surface hold cols -> fallback


# --------------------------------------------------------------------------- #
# Corpus assembly (reuses asof_reclaim_gate's exact Elo + row-universe pattern)
# --------------------------------------------------------------------------- #

def build_corpus_frame(matches_path: Path, hold_path: Path) -> pd.DataFrame:
    """Elo + surface-hold ingredients merged on event_id, chronologically sorted.

    One walk_forward_elo replay so base and every candidate see the IDENTICAL
    p_elo per row. Surface-hold columns stay NaN when the parquet or the
    per-player prior-count coverage is insufficient (fallback contract below).
    """
    mm = pd.read_parquet(matches_path)
    mm = mm[mm["winner"].notna()].reset_index(drop=True)
    wf = walk_forward_elo(mm)

    odds = pd.read_parquet(_ODDS)
    _ocols = ["event_id", "ps_p1", "ps_p2", "b365_p1", "b365_p2"]
    odds_sel = odds[[c for c in _ocols if c in odds.columns]].drop_duplicates(
        "event_id", keep="first")
    wf = wf.merge(odds_sel, on="event_id", how="left")

    hold = pd.read_parquet(hold_path)
    _hcols = ["event_id", "surface", "p1_n_prior", "p2_n_prior",
             "p1_hold_pct_asof", "p2_hold_pct_asof"] + [
        f"{p}_hold_pct_{s}_asof" for p in ("p1", "p2") for s in _SURFACES]
    hold_sel = hold[[c for c in _hcols if c in hold.columns]].drop_duplicates(
        "event_id", keep="first")

    out = wf[["event_id", "date", "winner", "win_prob_p1"]].rename(
        columns={"win_prob_p1": "p_elo"})
    out["target_p1_win"] = (out["winner"].astype(float) == 1.0).astype(float)
    out["p_close"] = wf.apply(lambda r: _devig_prob(r, kind="close"), axis=1)
    out = out.merge(hold_sel, on="event_id", how="left")
    return out.sort_values("date").reset_index(drop=True)


def _surface_hold_diff(df: pd.DataFrame) -> np.ndarray:
    """Row-wise (p1 - p2) hold% at the ROW's OWN surface; NaN off-list surfaces."""
    surf = df["surface"].astype(str).str.lower()
    p1 = np.full(len(df), np.nan)
    p2 = np.full(len(df), np.nan)
    for s in _SURFACES:
        mask = (surf == s).to_numpy()
        p1_col, p2_col = f"p1_hold_pct_{s}_asof", f"p2_hold_pct_{s}_asof"
        if p1_col in df.columns and p2_col in df.columns:
            p1 = np.where(mask, df[p1_col].to_numpy(float), p1)
            p2 = np.where(mask, df[p2_col].to_numpy(float), p2)
    return p1 - p2


def _coverage_mask(df: pd.DataFrame, surf_diff: np.ndarray) -> np.ndarray:
    """Both players >= MIN_PRIOR AND the row's own-surface diff is finite."""
    n_ok = (df.get("p1_n_prior", pd.Series(0, index=df.index)).fillna(0) >= MIN_PRIOR) & (
        df.get("p2_n_prior", pd.Series(0, index=df.index)).fillna(0) >= MIN_PRIOR)
    return (n_ok.to_numpy(bool)) & np.isfinite(surf_diff)


# --------------------------------------------------------------------------- #
# T1: surface residual-over-blended interaction
# --------------------------------------------------------------------------- #

def t1_added_raw(df: pd.DataFrame) -> np.ndarray:
    """RAW (pre-standardize) added columns for T1: [blended_diff, surface_residual]."""
    blended = (df["p1_hold_pct_asof"] - df["p2_hold_pct_asof"]).to_numpy(float)
    surf_diff = _surface_hold_diff(df)
    residual = surf_diff - blended
    cov = _coverage_mask(df, surf_diff) & np.isfinite(blended)
    blended = np.where(cov, blended, np.nan)
    residual = np.where(cov, residual, np.nan)
    return np.column_stack([blended, residual])


# --------------------------------------------------------------------------- #
# T2: surface diff x low-hold-regime interaction (regime median TRAIN-ONLY)
# --------------------------------------------------------------------------- #

def t2_added_raw(df: pd.DataFrame, train_median: float) -> np.ndarray:
    """RAW added columns for T2: [surface_diff, surface_diff * low_regime].

    `train_median` is the tour-surface median hold% computed on TRAIN rows
    ONLY (per fold, by the caller) -- never pooled across train+test.
    """
    surf = df["surface"].astype(str).str.lower()
    p1_hold = np.full(len(df), np.nan)
    p2_hold = np.full(len(df), np.nan)
    for s in _SURFACES:
        mask = (surf == s).to_numpy()
        p1_col, p2_col = f"p1_hold_pct_{s}_asof", f"p2_hold_pct_{s}_asof"
        if p1_col in df.columns and p2_col in df.columns:
            p1_hold = np.where(mask, df[p1_col].to_numpy(float), p1_hold)
            p2_hold = np.where(mask, df[p2_col].to_numpy(float), p2_hold)
    surf_diff = p1_hold - p2_hold
    low_regime = ((p1_hold < train_median) & (p2_hold < train_median)).astype(float)
    low_regime = np.where(np.isfinite(p1_hold) & np.isfinite(p2_hold), low_regime, np.nan)
    cov = _coverage_mask(df, surf_diff)
    surf_diff = np.where(cov, surf_diff, np.nan)
    interact = np.where(cov, surf_diff * low_regime, np.nan)
    return np.column_stack([surf_diff, interact])


def train_surface_median(train: pd.DataFrame) -> float:
    """TRAIN-ONLY tour-surface median hold% (pooled p1+p2 hold values, all 3 surfaces)."""
    surf = train["surface"].astype(str).str.lower()
    vals: List[float] = []
    for s in _SURFACES:
        mask = (surf == s).to_numpy()
        for p in ("p1", "p2"):
            col = f"{p}_hold_pct_{s}_asof"
            if col in train.columns:
                vals.extend(train.loc[mask, col].dropna().tolist())
    return float(np.median(vals)) if vals else 0.5


def added_raw_for(candidate: str, train: pd.DataFrame, test: pd.DataFrame
                  ) -> Tuple[np.ndarray, np.ndarray]:
    """Dispatch T1/T2 feature construction; T2's median is TRAIN-ONLY, computed here."""
    if candidate == "tennis_surface_hold_regime":
        return t1_added_raw(train), t1_added_raw(test)
    med = train_surface_median(train)
    return t2_added_raw(train, med), t2_added_raw(test, med)


# --------------------------------------------------------------------------- #
# Generic 1-feature-base + N-added fit/score (mirrors mlb.pregame_stack_gate)
# --------------------------------------------------------------------------- #

def fit_base(train: pd.DataFrame) -> sf.LogisticFit:
    """1-feature BASE logistic [1, logit(p_elo)] on TRAIN only."""
    X = sf.build_design([sf.logit(train["p_elo"].to_numpy(float))])
    return sf.fit_logistic(X, train["target_p1_win"].to_numpy(float))


def fit_candidate(train: pd.DataFrame, added_raw_train: np.ndarray
                  ) -> Tuple[sf.LogisticFit, sf.StandardizerParams]:
    added_std = sf.fit_standardizer(added_raw_train)
    added_z = sf.standardize(added_raw_train, added_std)
    X = sf.build_design([sf.logit(train["p_elo"].to_numpy(float))]
                       + [added_z[:, i] for i in range(added_z.shape[1])])
    fit = sf.fit_logistic(X, train["target_p1_win"].to_numpy(float))
    return fit, added_std


def score_base(df: pd.DataFrame, fit: sf.LogisticFit) -> np.ndarray:
    X = sf.build_design([sf.logit(df["p_elo"].to_numpy(float))])
    return sf.predict_proba(X, fit.weights)


def score_candidate(df: pd.DataFrame, fit: sf.LogisticFit, added_std: sf.StandardizerParams,
                    added_raw: np.ndarray, p_base: np.ndarray) -> np.ndarray:
    added_z = sf.standardize(added_raw, added_std)
    X = sf.build_design([sf.logit(df["p_elo"].to_numpy(float))]
                       + [added_z[:, i] for i in range(added_z.shape[1])])
    p_cand = sf.predict_proba(X, fit.weights)
    raw_cols = [added_raw[:, i] for i in range(added_raw.shape[1])]
    return sf.score_with_fallback(raw_cols, p_base, p_cand)


def close_brier_for_frame(df: pd.DataFrame) -> Tuple[float, int]:
    """vs-CLOSE: devigged close via adapter_helpers._devig_prob, covered subset only."""
    cov = df["p_close"].notna()
    if int(cov.sum()) == 0:
        return float("nan"), 0
    p = df.loc[cov, "p_close"].to_numpy(float)
    y = df.loc[cov, "target_p1_win"].to_numpy(float)
    return sf.brier(p, y), int(cov.sum())


__all__ = [
    "MIN_PRIOR", "build_corpus_frame", "t1_added_raw", "t2_added_raw",
    "train_surface_median", "added_raw_for", "fit_base", "fit_candidate",
    "score_base", "score_candidate", "close_brier_for_frame",
]
