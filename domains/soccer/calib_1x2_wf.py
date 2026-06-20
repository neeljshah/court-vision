"""domains.soccer.calib_1x2_wf -- Draw-aware 3-way (1X2) calibration for soccer.

Fits a leak-free walk-forward 3-way (home/draw/away) isotonic calibrator so the
full 1X2 simplex is calibrated, not just P(home win). Each arm is fitted on
events 0..i-1 only; then the triple is renormalised to sum=1.

ALGORITHM: per-arm isotonic regression (PAVA) -> renormalise.
EVENT i: fit on events 0..i-1. Events < MIN_HISTORY pass through raw.
ACCEPTANCE: 3-way ECE half2 < raw; triples sum to 1.0 +/- 1e-6; no future leak.
HONEST: CALIBRATION only. NO edge claimed. Markets are efficient.
INVARIANTS: never edit src/ kernel/ api/ scripts/team_system/ intel/. <=300 LOC.

Run test:
    cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/tests/test_calib_1x2_wf.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_HISTORY: int = 50    # events before calibration kicks in; pass-through below

_OUTCOMES = ("home", "draw", "away")   # consistent slot order throughout

CALIBRATION_NOTE: str = (
    "calibration != edge: better-calibrated 3-way probabilities "
    "do NOT imply beating the market"
)


# ---------------------------------------------------------------------------
# ECE for 3-way simplex
# ---------------------------------------------------------------------------

def ece_3way(
    probs: np.ndarray,
    outcomes: np.ndarray,
    bins: int = 10,
) -> float:
    """Expected Calibration Error for a 3-way (1X2) probability distribution.

    probs:    shape (N, 3) -- rows are (p_home, p_draw, p_away), must sum to ~1.
    outcomes: shape (N,) -- integer class label in {0, 1, 2} (home=0, draw=1, away=2).
    Returns mean ECE across the three outcome arms (weighted by support per arm).
    """
    probs = np.asarray(probs, dtype=float)
    outcomes = np.asarray(outcomes, dtype=int)
    n = len(outcomes)
    if n == 0:
        return 0.0
    total_ece = 0.0
    edges = np.linspace(0.0, 1.0, bins + 1)
    for c in range(3):
        y_c = (outcomes == c).astype(float)
        p_c = probs[:, c]
        for b in range(bins):
            lo, hi = edges[b], edges[b + 1]
            mask = (p_c >= lo) & (p_c < hi) if b < bins - 1 else (p_c >= lo) & (p_c <= hi)
            n_bin = int(mask.sum())
            if n_bin == 0:
                continue
            total_ece += (n_bin / (n * 3)) * abs(float(y_c[mask].mean()) - float(p_c[mask].mean()))
    return float(total_ece)


# ---------------------------------------------------------------------------
# Core: walk-forward 3-way calibration
# ---------------------------------------------------------------------------

def walk_forward_calibrate_1x2(
    raw_probs: np.ndarray,
    outcomes: np.ndarray,
    min_history: int = MIN_HISTORY,
) -> np.ndarray:
    """Leak-free walk-forward 3-way isotonic calibration.

    raw_probs : shape (N, 3) -- (p_home, p_draw, p_away) per event, in date order.
                Each row must sum to 1.0 (accepted from scoreline_engine; renorm applied
                if not, but scoreline_engine already renormalises).
    outcomes  : shape (N,) -- integer class label in {0, 1, 2}.
    min_history : events required before calibration kicks in.

    Returns calibrated_probs: shape (N, 3), each row sums to 1.0 +/- 1e-6.

    Contract: for event i the isotonic maps are fitted on events 0..i-1 ONLY.
    Events i < min_history pass through the raw triple (renormalised if needed).
    """
    from sklearn.isotonic import IsotonicRegression

    raw_probs = np.asarray(raw_probs, dtype=float)
    outcomes = np.asarray(outcomes, dtype=int)
    n = len(outcomes)
    if raw_probs.shape != (n, 3):
        raise ValueError(
            f"raw_probs must be shape (N, 3); got {raw_probs.shape} for N={n}"
        )

    calibrated = np.empty_like(raw_probs)

    # One isotonic regressor per outcome arm, refit each step.
    ir = [IsotonicRegression(out_of_bounds="clip") for _ in range(3)]

    for i in range(n):
        row = raw_probs[i].copy()
        # Guard: ensure row is a valid probability triple.
        row = np.clip(row, 0.0, 1.0)
        row_sum = row.sum()
        if row_sum > 0:
            row /= row_sum

        if i < min_history:
            # Insufficient history -- pass through (already renormalised).
            calibrated[i] = row
            continue

        # Fit each arm on strictly-prior window.
        valid = (
            np.isfinite(raw_probs[:i, 0])
            & np.isfinite(raw_probs[:i, 1])
            & np.isfinite(raw_probs[:i, 2])
            & (outcomes[:i] >= 0)
            & (outcomes[:i] <= 2)
        )
        if not valid.any():
            calibrated[i] = row
            continue

        p_hist = np.clip(raw_probs[:i][valid], 0.0, 1.0)
        # Renormalise history rows as well (defensive).
        row_sums = p_hist.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1.0
        p_hist = p_hist / row_sums
        y_hist = outcomes[:i][valid]

        q = np.empty(3)
        for c in range(3):
            y_c = (y_hist == c).astype(float)
            try:
                ir[c].fit(p_hist[:, c], y_c)
                q[c] = float(ir[c].transform([row[c]])[0])
            except Exception:   # noqa: BLE001 -- identity fallback
                q[c] = row[c]

        q = np.clip(q, 0.0, 1.0)
        q_sum = q.sum()
        if q_sum > 0:
            q /= q_sum
        else:
            q = row     # degenerate -- fall back to raw
        calibrated[i] = q

    return calibrated


# ---------------------------------------------------------------------------
# Main API: fit / score walk-forward splits
# ---------------------------------------------------------------------------

def _build_1x2_arrays(df) -> Tuple[np.ndarray, np.ndarray]:
    """Build (raw_probs (N,3), outcomes (N,)) from a walk-forward DataFrame.

    Resolves columns: p_home/p_draw/p_away > lam_home/lam_away > p_poisson fallback.
    Encodes ftr: H=0, D=1, A=2; unknown rows get label -1 (filtered at scoring).
    """
    import pandas as pd

    df = df.copy()
    # Resolve probability columns.
    if "p_home" in df.columns and "p_draw" in df.columns and "p_away" in df.columns:
        p_h = df["p_home"].astype(float).values
        p_d = df["p_draw"].astype(float).values
        p_a = df["p_away"].astype(float).values
    else:
        # Fallback: derive from scoreline_engine lambdas if available.
        if "lam_home" in df.columns and "lam_away" in df.columns:
            from domains.soccer.scoreline_engine import scoreline_matrix, markets_from_matrix
            triples = []
            for _, row in df.iterrows():
                try:
                    P = scoreline_matrix(float(row["lam_home"]), float(row["lam_away"]))
                    mkt = markets_from_matrix(P)
                    triples.append((mkt["1X2_home"], mkt["1X2_draw"], mkt["1X2_away"]))
                except Exception:  # noqa: BLE001
                    triples.append((0.333, 0.333, 0.334))
            p_h = np.array([t[0] for t in triples])
            p_d = np.array([t[1] for t in triples])
            p_a = np.array([t[2] for t in triples])
        elif "p_poisson" in df.columns:
            # Binary P(home win) -> split residual equally into draw / away.
            p_h = df["p_poisson"].astype(float).values
            residual = (1.0 - p_h) / 2.0
            p_d = residual.copy()
            p_a = residual.copy()
        else:
            raise ValueError(
                "DataFrame must have (p_home, p_draw, p_away) OR (lam_home, lam_away) "
                "OR p_poisson to build 1X2 arrays."
            )

    raw_probs = np.stack([p_h, p_d, p_a], axis=1)
    # Renormalise rows to sum=1 (defensive).
    row_sums = raw_probs.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1.0
    raw_probs = raw_probs / row_sums

    # Encode outcomes: H=0, D=1, A=2.
    ftr = df["ftr"].astype(str).str.upper()
    outcome_map = {"H": 0, "D": 1, "A": 2}
    outcomes = ftr.map(outcome_map).fillna(-1).astype(int).values

    return raw_probs, outcomes


def fit_and_score(
    df,
    *,
    min_history: int = MIN_HISTORY,
) -> Dict:
    """Fit 3-way calibrator on first half; score held-out second half.

    Returns dict: n_total, n_train, n_val, ece_raw_half2, ece_cal_half2,
    ece_improves, sum_to_one_ok, passes, note.
    """
    import pandas as pd

    if "date" in df.columns:
        df = df.sort_values("date").reset_index(drop=True)
    else:
        df = df.reset_index(drop=True)

    raw_probs, outcomes = _build_1x2_arrays(df)

    # Only keep events with a valid outcome label.
    valid_mask = outcomes >= 0
    valid_idx = np.where(valid_mask)[0]
    n_valid = len(valid_idx)
    mid = n_valid // 2

    n = len(df)

    # Run full walk-forward calibration on ALL events (both halves),
    # using only strictly-prior events for each calibrator fit.
    calibrated_all = walk_forward_calibrate_1x2(
        raw_probs, outcomes, min_history=min_history
    )

    # Half2 validation uses the second half of VALID events.
    half2_idx = valid_idx[mid:]
    raw_h2 = raw_probs[half2_idx]
    cal_h2 = calibrated_all[half2_idx]
    y_h2 = outcomes[half2_idx]

    ece_raw = ece_3way(raw_h2, y_h2)
    ece_cal = ece_3way(cal_h2, y_h2)

    # Verify sum-to-one on ALL calibrated events.
    cal_sums = calibrated_all.sum(axis=1)
    sum_to_one_ok = bool(np.all(np.abs(cal_sums - 1.0) < 1e-6))

    ece_improves = bool(ece_cal < ece_raw)
    passes = ece_improves and sum_to_one_ok

    return {
        "n_total": n,
        "n_train": mid,
        "n_val": len(half2_idx),
        "ece_raw_half2": float(ece_raw),
        "ece_cal_half2": float(ece_cal),
        "ece_improves": ece_improves,
        "sum_to_one_ok": sum_to_one_ok,
        "passes": passes,
        "note": (
            f"3-way ECE half2: raw={ece_raw:.4f} cal={ece_cal:.4f}. "
            f"CALIBRATION only; NO edge claimed. {CALIBRATION_NOTE}"
        ),
    }


__all__ = [
    "ece_3way",
    "walk_forward_calibrate_1x2",
    "fit_and_score",
    "MIN_HISTORY",
    "CALIBRATION_NOTE",
]
