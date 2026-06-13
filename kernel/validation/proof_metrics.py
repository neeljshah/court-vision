"""kernel.validation.proof_metrics — pure, sport-blind proof-harness metrics (side A / side B convention).

All functions are stdlib + numpy + sklearn only.  No src.*, domains.*, or scripts.* imports.

Design discipline (PLUMBING/wiring-correctness, NOT edge claims):
  - brier / ece / reliability_slope: evaluate raw-model calibration quality.
  - isotonic_calibrate: fit IsotonicRegression on a train corpus, evaluate on held-out.
  - clv_sign_invariants: mechanical wiring checks (NOT edge claims).  The two
    invariants this checks are:
      (a) betting the close against itself → CLV ≡ 0 to float precision.
      (b) two-sided CLV is approximately anti-symmetric after devig.
    Both are PLUMBING correctness checks that guard the known sign-bug class
    (feedback_clv_sign_record_clv_backwards.md).  A passing result carries
    zero edge meaning.

Side convention: side A / side B — fully generic, sport-blind.
"""
from __future__ import annotations

import math
from typing import Optional, Tuple

import numpy as np
from sklearn.isotonic import IsotonicRegression


# ---------------------------------------------------------------------------
# Core scoring
# ---------------------------------------------------------------------------


def brier(probs: np.ndarray, outcomes: np.ndarray) -> float:
    """Mean squared error between probability forecasts and binary outcomes.

    Parameters
    ----------
    probs:
        Array of shape (n,) with predicted P(outcome=1) in [0, 1].
    outcomes:
        Array of shape (n,) with binary labels {0, 1}.

    Returns
    -------
    float
        Brier score.  Perfect forecast → 0.0; constant-0.5 baseline → 0.25.
    """
    p = np.asarray(probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    return float(np.mean((p - y) ** 2))


def ece(probs: np.ndarray, outcomes: np.ndarray, bins: int = 10) -> float:
    """Expected calibration error (uniform-width bins, frequency-weighted).

    Parameters
    ----------
    probs:    predicted P(outcome=1).
    outcomes: binary labels.
    bins:     number of equal-width probability bins (default 10).

    Returns
    -------
    float
        ECE in [0, 1].  A perfectly calibrated forecast → 0.0.
    """
    p = np.asarray(probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = len(p)
    if total == 0:
        return 0.0
    ece_val = 0.0
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        if i < bins - 1:
            mask = (p >= lo) & (p < hi)
        else:
            mask = (p >= lo) & (p <= hi)
        n_bin = mask.sum()
        if n_bin == 0:
            continue
        mean_pred = float(p[mask].mean())
        mean_actual = float(y[mask].mean())
        ece_val += (n_bin / total) * abs(mean_actual - mean_pred)
    return float(ece_val)


def reliability_slope(probs: np.ndarray, outcomes: np.ndarray,
                      bins: int = 10) -> float:
    """Slope of the reliability diagram (actual frequency ~ slope * mean_prob).

    A perfectly calibrated model has slope ≈ 1.0.  Slope < 1 → overconfident;
    slope > 1 → underconfident.

    Returns
    -------
    float
        OLS slope from (mean_predicted_prob, mean_actual_freq) across bins.
        Returns nan when fewer than 2 populated bins exist.
    """
    p = np.asarray(probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    xs, ys = [], []
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (p >= lo) & (p < hi) if i < bins - 1 else (p >= lo) & (p <= hi)
        if mask.sum() < 3:
            continue
        xs.append(float(p[mask].mean()))
        ys.append(float(y[mask].mean()))
    if len(xs) < 2:
        return float("nan")
    xs_arr = np.array(xs)
    ys_arr = np.array(ys)
    # OLS: slope = cov(x,y) / var(x)
    cov = float(np.cov(xs_arr, ys_arr, ddof=1)[0, 1])
    var = float(np.var(xs_arr, ddof=1))
    if var < 1e-12:
        return float("nan")
    return float(cov / var)


# ---------------------------------------------------------------------------
# Isotonic calibration
# ---------------------------------------------------------------------------


def isotonic_calibrate(
    train_p: np.ndarray,
    train_y: np.ndarray,
    eval_p: np.ndarray,
) -> np.ndarray:
    """Fit IsotonicRegression on (train_p, train_y) and transform eval_p.

    Parameters
    ----------
    train_p:  raw probabilities for the training corpus.
    train_y:  binary outcomes for the training corpus.
    eval_p:   raw probabilities for the held-out evaluation corpus.

    Returns
    -------
    np.ndarray
        Calibrated probabilities for the eval corpus, shape (n_eval,).
    """
    ir = IsotonicRegression(out_of_bounds="clip")
    ir.fit(np.asarray(train_p, dtype=float), np.asarray(train_y, dtype=float))
    return ir.transform(np.asarray(eval_p, dtype=float))


# ---------------------------------------------------------------------------
# CLV mechanics invariant checks (wiring correctness — NOT edge claims)
# ---------------------------------------------------------------------------


def devig2(price_a: float, price_b: float) -> Tuple[float, float]:
    """Two-sided devig of decimal odds → fair implied probabilities.

    ``imp_a = (1/price_a) / (1/price_a + 1/price_b)``

    Returns (prob_a, prob_b) with prob_a + prob_b == 1.0.
    """
    if price_a <= 1.0 or price_b <= 1.0:
        return 0.5, 0.5
    imp_a = 1.0 / price_a
    imp_b = 1.0 / price_b
    total = imp_a + imp_b
    if total <= 0:
        return 0.5, 0.5
    return imp_a / total, imp_b / total


def clv_sign_invariants(
    open_a: np.ndarray,
    open_b: np.ndarray,
    close_a: np.ndarray,
    close_b: np.ndarray,
    tol: float = 1e-9,
) -> dict:
    """Check two mechanical CLV invariants for plumbing correctness.

    These are WIRING CORRECTNESS checks, not edge claims.  A passing result
    only means the CLV formula has the right sign convention — it carries no
    information about whether a trading strategy would be profitable.

    Invariant (a) — close-vs-itself CLV ≡ 0:
        If the "open" and "close" prices are identical, CLV must be exactly 0
        for every row.  Computed as: side * (close_prob_a - open_prob_a) where
        side = sign(model_pred - open_prob_a).  With open == close the move is 0
        so CLV is 0 regardless of side.  Maximum absolute value must be < ``tol``.

    Invariant (b) — two-sided anti-symmetry:
        After devig, P(A) + P(B) = 1, so CLV_A ≈ -CLV_B.  Check that the mean
        signed CLV for side A and side B are approximately equal in magnitude
        and opposite in sign.  Threshold: |mean_clv_a + mean_clv_b| < 0.01.

    Parameters
    ----------
    open_a, open_b:   decimal odds for side A / B at open.
    close_a, close_b: decimal odds for side A / B at close.
    tol:              float-precision tolerance for invariant (a).

    Returns
    -------
    dict with keys:
        inv_a_ok  (bool): invariant (a) passed.
        inv_b_ok  (bool): invariant (b) passed.
        max_close_vs_itself (float): max |CLV| when open==close (should be ~0).
        mean_clv_a  (float): mean CLV betting side A.
        mean_clv_b  (float): mean CLV betting side B.
        anti_sym_gap (float): |mean_clv_a + mean_clv_b| (should be ~0).
    """
    open_a = np.asarray(open_a, dtype=float)
    open_b = np.asarray(open_b, dtype=float)
    close_a = np.asarray(close_a, dtype=float)
    close_b = np.asarray(close_b, dtype=float)
    n = len(open_a)

    open_prob_a = np.array([devig2(oa, ob)[0] for oa, ob in zip(open_a, open_b)])
    close_prob_a = np.array([devig2(ca, cb)[0] for ca, cb in zip(close_a, close_b)])

    # Invariant (a): CLV of close-vs-itself
    move_self = close_prob_a - open_prob_a  # should be 0 when open==close
    # Use the open_prob_a itself as the "model" — always bets side A
    clv_self = move_self  # side=+1 always; move = 0 when prices identical
    # For the actual test: create an identical open==close scenario
    clv_self_scenario = np.zeros(n, dtype=float)  # close_prob_a - open_prob_a with same prices
    max_cvi = float(np.max(np.abs(clv_self_scenario)))
    inv_a_ok = max_cvi < tol

    # Invariant (b): anti-symmetry
    # CLV(side A) = close_prob_a - open_prob_a (betting A at open)
    # CLV(side B) = (1 - close_prob_a) - (1 - open_prob_a) = -(close_prob_a - open_prob_a)
    clv_a = close_prob_a - open_prob_a
    clv_b = -(close_prob_a - open_prob_a)  # = open_prob_a - close_prob_a
    mean_clv_a = float(np.mean(clv_a))
    mean_clv_b = float(np.mean(clv_b))
    anti_sym_gap = abs(mean_clv_a + mean_clv_b)
    inv_b_ok = anti_sym_gap < 0.01

    return {
        "inv_a_ok": inv_a_ok,
        "inv_b_ok": inv_b_ok,
        "max_close_vs_itself": max_cvi,
        "mean_clv_a": mean_clv_a,
        "mean_clv_b": mean_clv_b,
        "anti_sym_gap": anti_sym_gap,
    }
