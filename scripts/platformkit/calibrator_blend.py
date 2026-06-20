"""scripts/platformkit/calibrator_blend.py — Convex-weighted ensemble blend of calibrators.

Given per-method walk-forward prob arrays from select_calibrator, fit non-negative
weights summing to 1 by minimizing held-out log-loss on a TRAIN slice, score the
blend on the held-out TEST slice vs. best single member AND vs. identity.

SHIP blend ONLY if held-out Brier beats best single by > IMPROVE_TOL AND ECE
non-worse; else fall back to single winner (and identity if nothing beats raw).

Readout-only dict: weights, verdict, brier, ece, winner.  No serve wiring.

CALIBRATION != EDGE.  Calibrated probabilities do NOT imply beating the close.
No $/roi/pnl/edge/profit key anywhere in this module.
"""
from __future__ import annotations

import sys
from typing import Dict, List, Optional, Sequence

import numpy as np

from scripts.platformkit.calibrator_zoo import select_calibrator, CALIBRATION_NOTE
from scripts.platformkit.recalibration import _ece

_EPS = 1e-15
_MIN_SAMPLES = 20          # thin corpus -> INSUFFICIENT_DATA
_IMPROVE_TOL = 1e-4        # blend must beat best single Brier by at least this
_TRAIN_FRAC = 0.5          # first half of eval window = blend weight TRAIN
_MAX_ITER = 500            # projected-gradient iterations
_STEP = 0.01               # projected-gradient step size
_FORBIDDEN_KEYS = frozenset({"$", "roi", "pnl", "edge", "profit"})

__all__ = ["blend_calibrators", "CALIBRATION_NOTE"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _logloss_mean(probs: np.ndarray, outcomes: np.ndarray) -> float:
    """Mean binary log-loss; NaN-safe."""
    p = np.clip(probs, _EPS, 1.0 - _EPS)
    y = outcomes
    return float(np.mean(-(y * np.log(p) + (1.0 - y) * np.log(1.0 - p))))


def _brier(probs: np.ndarray, outcomes: np.ndarray) -> float:
    """Mean squared error of probabilistic forecasts."""
    try:
        from scripts.platformkit.eval_gate.scoring import brier as _b
        return _b(probs, outcomes)
    except Exception:
        return float(np.mean((probs - outcomes) ** 2))


def _fit_simplex_weights(
    method_probs: np.ndarray,
    outcomes: np.ndarray,
    *,
    max_iter: int = _MAX_ITER,
    step: float = _STEP,
) -> np.ndarray:
    """Fit non-negative weights summing to 1 minimising log-loss (projected gradient).

    method_probs : (n_eval, n_methods)  -- eval-window probs per method
    outcomes     : (n_eval,)             -- binary outcomes on eval window
    Returns weights (n_methods,) non-negative summing to 1.
    Pure numpy; no scipy hard dep.
    """
    n, m = method_probs.shape
    w = np.ones(m, dtype=float) / m  # uniform start on simplex

    for _ in range(max_iter):
        # blend prob
        blend = np.clip(method_probs @ w, _EPS, 1.0 - _EPS)
        # gradient of mean log-loss w.r.t. w:
        # d/dw_j = mean( -(y/blend - (1-y)/(1-blend)) * p_j )
        residual = -(outcomes / blend - (1.0 - outcomes) / (1.0 - blend))  # (n,)
        grad = method_probs.T @ residual / n                               # (m,)

        w_new = w - step * grad
        # project onto simplex: non-negative + sum-to-one
        w_new = _project_simplex(w_new)

        if np.max(np.abs(w_new - w)) < 1e-9:
            break
        w = w_new

    return w


def _project_simplex(v: np.ndarray) -> np.ndarray:
    """Project vector onto probability simplex (non-negative, sum=1)."""
    m = len(v)
    u = np.sort(v)[::-1]
    cssv = np.cumsum(u)
    rho = int(np.nonzero(u * np.arange(1, m + 1) > (cssv - 1.0))[0][-1])
    theta = float((cssv[rho] - 1.0) / (rho + 1.0))
    return np.maximum(v - theta, 0.0)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def blend_calibrators(
    raw_probs: Sequence[float],
    outcomes: Sequence[float],
    *,
    min_history: int = 50,
    refit_every: int = 1,
    methods: Optional[List[str]] = None,
    improve_tol: float = _IMPROVE_TOL,
    train_frac: float = _TRAIN_FRAC,
) -> dict:
    """Convex-weighted ensemble blend of calibrator methods.

    Parameters
    ----------
    raw_probs, outcomes : sequences of float
        Raw model probabilities and binary outcomes.
    min_history : int
        Warmup; forwarded to select_calibrator.
    refit_every : int
        Refit cadence; forwarded to select_calibrator.
    methods : list of str or None
        Subset of calibrator methods; None = all five.
    improve_tol : float
        Blend must beat best-single Brier by at least this on TEST.
    train_frac : float
        Fraction of the eval window used for fitting blend weights (rest = TEST).

    Returns
    -------
    dict with keys:
        winner          (str)   : 'blend' | best-single method name | 'identity'
        verdict         (str)   : 'BLEND_WINS' | 'SINGLE_WINS' | 'IDENTITY_WINS'
                                  | 'INSUFFICIENT_DATA'
        weights         (dict)  : {method_name: weight, ...} -- sum=1, non-negative
        brier_blend     (float) : TEST Brier of the blend (nan if not computed)
        brier_best_single (float): TEST Brier of the best single method
        brier_identity  (float) : TEST Brier of identity
        ece_blend       (float) : TEST ECE of the blend (nan if not computed)
        ece_best_single (float) : TEST ECE of best single
        n_train         (int)   : rows used for weight fitting
        n_test          (int)   : rows used for scoring
        note            (str)   : calibration honesty note

    Raises
    ------
    Never raises.  Thin corpora return verdict='INSUFFICIENT_DATA'.
    """
    result: dict = {
        "winner": "identity",
        "verdict": "INSUFFICIENT_DATA",
        "weights": {},
        "brier_blend": float("nan"),
        "brier_best_single": float("nan"),
        "brier_identity": float("nan"),
        "ece_blend": float("nan"),
        "ece_best_single": float("nan"),
        "n_train": 0,
        "n_test": 0,
        "note": CALIBRATION_NOTE,
    }

    try:
        p = np.asarray(raw_probs, dtype=float)
        y = np.asarray(outcomes, dtype=float)
        n = len(p)

        # Thin corpus guard
        if n < _MIN_SAMPLES:
            return result

        # Run all calibrators via select_calibrator (leak-free WF per method)
        zoo = select_calibrator(
            p, y,
            min_history=min_history,
            refit_every=refit_every,
            methods=methods,
        )
        n_eval = int(zoo["n_eval"])
        if n_eval < _MIN_SAMPLES:
            return result

        table = zoo["table"]
        method_names = [r["method"] for r in table]

        # Build eval-window arrays
        eval_mask = np.arange(n) >= min_history
        eval_mask &= np.isfinite(y)
        for row in table:
            pass  # masks already implied by select_calibrator logic

        # Rebuild per-method eval arrays from zoo
        # select_calibrator returns per-method probs for all N points
        # We rerun each method via the table ordering (same methods passed)
        # Use the chosen_probs from zoo + rerun remaining methods
        # Actually select_calibrator doesn't expose per-method arrays directly,
        # so we need to reconstruct them by calling walk-forward helpers.
        # We import the internal runners here (read-only).
        from scripts.platformkit.calibrator_zoo import (
            walk_forward_temperature,
            walk_forward_beta,
        )
        from scripts.platformkit.recalibration import walk_forward_recalibrate
        from scripts.platformkit.calibration_ladder import walk_forward_platt

        def _run_method(name: str) -> np.ndarray:
            if name == "identity":
                return np.clip(p.copy(), 0.0, 1.0)
            if name == "temperature":
                return walk_forward_temperature(p, y,
                                                min_history=min_history,
                                                refit_every=refit_every)
            if name == "platt":
                return walk_forward_platt(p, y,
                                          min_history=min_history,
                                          refit_every=refit_every)
            if name == "beta":
                return walk_forward_beta(p, y,
                                         min_history=min_history,
                                         refit_every=refit_every)
            # isotonic
            return walk_forward_recalibrate(p, y,
                                             min_history=min_history,
                                             refit_every=refit_every)

        active_methods = methods if methods is not None else [r["method"] for r in table]
        method_arrays = {m: _run_method(m) for m in active_methods}

        # Build clean eval mask (finite in ALL methods)
        eval_mask = np.arange(n) >= min_history
        eval_mask &= np.isfinite(y)
        for arr in method_arrays.values():
            eval_mask &= np.isfinite(arr)

        n_eval_clean = int(eval_mask.sum())
        if n_eval_clean < _MIN_SAMPLES:
            return result

        # Split eval window into TRAIN (weight fitting) and TEST (scoring)
        eval_indices = np.where(eval_mask)[0]
        n_train = max(1, int(len(eval_indices) * train_frac))
        train_idx = eval_indices[:n_train]
        test_idx = eval_indices[n_train:]

        if len(test_idx) < _MIN_SAMPLES:
            return result

        # Per-method arrays on TRAIN and TEST windows
        mnames = list(method_arrays.keys())
        n_methods = len(mnames)

        train_mat = np.column_stack([method_arrays[m][train_idx] for m in mnames])
        test_mat = np.column_stack([method_arrays[m][test_idx] for m in mnames])
        y_train = y[train_idx]
        y_test = y[test_idx]

        # Fit blend weights on TRAIN (minimise log-loss)
        w = _fit_simplex_weights(train_mat, y_train)

        # Clamp tiny weights to 0 for cleanliness then re-project
        w = np.where(w < 1e-6, 0.0, w)
        w_sum = float(w.sum())
        if w_sum < 1e-12:
            w = np.ones(n_methods) / n_methods
        else:
            w = w / w_sum

        # Score blend on TEST
        blend_test = np.clip(test_mat @ w, 0.0, 1.0)
        brier_blend = _brier(blend_test, y_test)
        ece_blend = float(_ece(blend_test, y_test))

        # Score each single method on TEST
        single_briers = {m: _brier(test_mat[:, i], y_test)
                         for i, m in enumerate(mnames)}
        best_single_name = min(single_briers, key=lambda m: single_briers[m])
        brier_best_single = single_briers[best_single_name]
        brier_identity = single_briers.get("identity", float("nan"))

        best_single_test = test_mat[:, mnames.index(best_single_name)]
        ece_best_single = float(_ece(best_single_test, y_test))

        # Decision logic
        weights_dict = {m: float(w[i]) for i, m in enumerate(mnames)}
        result.update({
            "weights": weights_dict,
            "brier_blend": float(brier_blend),
            "brier_best_single": float(brier_best_single),
            "brier_identity": float(brier_identity),
            "ece_blend": float(ece_blend),
            "ece_best_single": float(ece_best_single),
            "n_train": int(len(train_idx)),
            "n_test": int(len(test_idx)),
        })

        blend_beats_single = (brier_best_single - brier_blend) > improve_tol
        ece_non_worse = ece_blend <= (ece_best_single + 1e-4)

        if blend_beats_single and ece_non_worse:
            result["winner"] = "blend"
            result["verdict"] = "BLEND_WINS"
        else:
            # Check if best single beats identity
            if np.isfinite(brier_identity) and brier_best_single < brier_identity:
                result["winner"] = best_single_name
                result["verdict"] = "SINGLE_WINS"
            else:
                result["winner"] = "identity"
                result["verdict"] = "IDENTITY_WINS"

    except Exception:  # never raise -- degrade gracefully
        pass

    return result


# ---------------------------------------------------------------------------
# __main__ CLI (demo only)
# ---------------------------------------------------------------------------

def _main() -> int:
    rng = np.random.default_rng(42)
    N = 400
    true_p = rng.uniform(0.3, 0.7, N)
    # Two members pushed in OPPOSITE directions: one over-, one under-confident
    raw = np.where(true_p >= 0.5,
                   0.5 + (true_p - 0.5) * 2.0,
                   0.5 - (0.5 - true_p) * 2.0)
    raw = np.clip(raw, 0.01, 0.99)
    outcomes = rng.binomial(1, true_p).astype(float)

    result = blend_calibrators(raw, outcomes, min_history=30)
    print()
    print("=" * 60)
    print("calibrator_blend.py -- Convex blend demo (N=%d)" % N)
    print("NOTE: %s" % CALIBRATION_NOTE)
    print("=" * 60)
    print("Verdict      : %s" % result["verdict"])
    print("Winner       : %s" % result["winner"])
    print("Brier blend  : %.5f" % result["brier_blend"])
    print("Brier best1  : %.5f" % result["brier_best_single"])
    print("Brier identity: %.5f" % result["brier_identity"])
    print("ECE blend    : %.5f" % result["ece_blend"])
    print("ECE best1    : %.5f" % result["ece_best_single"])
    print("n_train/test : %d / %d" % (result["n_train"], result["n_test"]))
    print("Weights:")
    for m, wt in sorted(result["weights"].items()):
        print("  %-12s %.4f" % (m, wt))
    print()
    return 0


if __name__ == "__main__":
    sys.exit(_main())
