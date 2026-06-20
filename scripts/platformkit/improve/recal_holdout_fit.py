"""scripts.platformkit.improve.recal_holdout_fit -- leak-free recal fit-and-score helper.

PURPOSE
-------
recalibrator.build_candidate fits the Platt map and scores its Brier delta on the
SAME rows (in-sample). This breaks the do-no-harm invariant: oos_improves is fabricated
because a map that overfits in-sample will always look good on the training rows.

This module provides a standalone fit_and_score() function that:
  1. Validates inputs (outcomes {0,1}, n >= 2*MIN_OBS).
  2. Splits chronologically (time-ordered) or by k-fold when no timestamps present.
  3. Fits the Platt map on the TRAIN split only.
  4. Scores base-vs-candidate Brier AND ECE on the held-out TEST split ONLY.
  5. Returns a typed dict with oos_delta_brier / oos_delta_ece / oos_improves.
  6. Never raises -- any failure returns status=INSUFFICIENT_DATA.

INVARIANTS
----------
- No $/roi/pnl/edge key anywhere in any returned dict.
- oos_improves True only when delta_brier > IMPROVE_TOL on genuine held-out rows.
- n < 2*MIN_OBS -> status INSUFFICIENT_DATA, oos_improves False, no map shipped.
- outcomes outside {0,1} -> INSUFFICIENT_DATA.
- ASCII; <= 300 LOC; stdlib + numpy + eval_gate.scoring (read-only) only.
- NEVER raises on garbage input.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from scripts.platformkit.eval_gate.scoring import brier, ece

logger = logging.getLogger("recal_holdout_fit")

# Minimum observations TOTAL. We require at least 2*MIN_OBS so the train and test
# splits each have MIN_OBS rows (honest null on thin corpus).
MIN_OBS = 8

# A Brier improvement must exceed this threshold to count as a genuine gain.
# Prevents reporting noise-level improvements as true improvements.
IMPROVE_TOL = 1e-4

# Fraction of data used for the TEST (held-out) split.
_TEST_FRAC = 0.25

# Status constants returned in the result dict.
STATUS_OK = "ok"
STATUS_INSUFFICIENT = "INSUFFICIENT_DATA"


def _clip01(p: np.ndarray) -> np.ndarray:
    return np.clip(p, 1e-6, 1.0 - 1e-6)


def _fit_platt_train(base_train: np.ndarray,
                     y_train: np.ndarray) -> Optional[Tuple[float, float]]:
    """Fit logistic P = sigmoid(a * logit(base) + b) on train rows via GD.

    Pure numpy, no scipy. Returns (a, b) or None on failure.
    Identical to recalibrator._fit_platt but operates only on TRAIN data.
    """
    z = np.log(_clip01(base_train) / (1.0 - _clip01(base_train)))
    a, b = 1.0, 0.0
    lr = 0.1
    n = float(len(z))
    for _ in range(400):
        p = _clip01(1.0 / (1.0 + np.exp(-(a * z + b))))
        g = p - y_train
        ga = float(np.dot(g, z) / n)
        gb = float(np.mean(g))
        a -= lr * ga
        b -= lr * gb
        if not (np.isfinite(a) and np.isfinite(b)):
            return None
    return a, b


def _apply_platt(base: np.ndarray, ab: Tuple[float, float]) -> np.ndarray:
    a, b = ab
    z = np.log(_clip01(base) / (1.0 - _clip01(base)))
    return _clip01(1.0 / (1.0 + np.exp(-(a * z + b))))


def _validate_inputs(
    base: np.ndarray, y: np.ndarray
) -> Optional[str]:
    """Return an error string if inputs are invalid, else None (valid)."""
    if len(base) == 0 or len(y) == 0:
        return "empty input"
    if len(base) != len(y):
        return "length mismatch"
    if not (np.all(np.isfinite(base)) and np.all(np.isfinite(y))):
        return "non-finite values"
    unique_y = set(float(v) for v in np.unique(y).tolist())
    if unique_y - {0.0, 1.0}:
        return "outcomes outside {0,1}: %s" % sorted(unique_y)
    if len(base) < 2 * MIN_OBS:
        return "n=%d < 2*MIN_OBS=%d" % (len(base), 2 * MIN_OBS)
    return None


def _chronological_split(
    base: np.ndarray,
    y: np.ndarray,
    timestamps: Optional[Sequence],
    test_frac: float,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Split into (base_train, y_train, base_test, y_test).

    If timestamps are provided, order by time then take the LAST test_frac rows as
    TEST (chronological: train on past, evaluate on future). When timestamps are
    absent, use the natural order (caller is responsible for chronological ordering)
    and take the last test_frac fraction as TEST.
    """
    n = len(base)
    if timestamps is not None:
        order = np.argsort(timestamps, kind="stable")
    else:
        order = np.arange(n)

    base_ord = base[order]
    y_ord = y[order]

    split = max(MIN_OBS, n - max(MIN_OBS, int(round(n * test_frac))))
    # Ensure test split also has at least MIN_OBS rows.
    split = min(split, n - MIN_OBS)

    return (
        base_ord[:split],
        y_ord[:split],
        base_ord[split:],
        y_ord[split:],
    )


def _insufficient(reason: str) -> Dict[str, Any]:
    """Return a well-formed INSUFFICIENT_DATA result."""
    return {
        "status": STATUS_INSUFFICIENT,
        "reason": reason,
        "oos_improves": False,
        "oos_delta_brier": None,
        "oos_delta_ece": None,
        "n_train": None,
        "n_test": None,
        "platt_a": None,
        "platt_b": None,
        "note": "calibration, not edge",
    }


def fit_and_score(
    base_probs: Sequence[float],
    outcomes: Sequence[float],
    *,
    timestamps: Optional[Sequence] = None,
    test_frac: float = _TEST_FRAC,
) -> Dict[str, Any]:
    """Fit a Platt recalibration map on TRAIN and score base-vs-candidate on TEST only.

    Parameters
    ----------
    base_probs:
        Sequence of base model probabilities in [0, 1].
    outcomes:
        Sequence of binary outcomes, each must be 0 or 1.
    timestamps:
        Optional sequence of sortable timestamps (same length as base_probs).
        When provided, data is split chronologically (train=earlier, test=later).
        When absent, the natural order of base_probs is used as the time order.
    test_frac:
        Fraction of total rows to hold out for testing. Default 0.25.
        Each split will have at least MIN_OBS rows.

    Returns
    -------
    dict with keys:
        status:           "ok" | "INSUFFICIENT_DATA"
        oos_improves:     bool -- True ONLY on genuine held-out Brier improvement
        oos_delta_brier:  float (base_brier - cand_brier on TEST; positive = improved)
        oos_delta_ece:    float (base_ece - cand_ece on TEST; diagnostic only)
        n_train:          int
        n_test:           int
        platt_a:          float -- fitted Platt slope (a=1, b~0 = near-identity)
        platt_b:          float -- fitted Platt intercept
        note:             "calibration, not edge"

    Never raises. Returns INSUFFICIENT_DATA on any failure.
    No $/roi/pnl/edge key ever appears.
    """
    try:
        base = np.asarray(base_probs, dtype=float)
        y = np.asarray(outcomes, dtype=float)

        err = _validate_inputs(base, y)
        if err is not None:
            logger.debug("recal_holdout_fit: validation failed: %s", err)
            return _insufficient(err)

        ts: Optional[np.ndarray] = None
        if timestamps is not None:
            ts_arr = np.asarray(timestamps)
            if len(ts_arr) != len(base):
                return _insufficient("timestamps length mismatch")
            ts = ts_arr

        base_train, y_train, base_test, y_test = _chronological_split(
            base, y, ts, test_frac
        )

        if len(base_train) < MIN_OBS or len(base_test) < MIN_OBS:
            return _insufficient(
                "split too small: train=%d test=%d (MIN_OBS=%d)"
                % (len(base_train), len(base_test), MIN_OBS)
            )

        ab = _fit_platt_train(base_train, y_train)
        if ab is None:
            return _insufficient("Platt fit failed to converge")

        # Score on TEST rows ONLY -- never on train rows.
        cand_test = _apply_platt(base_test, ab)

        base_brier_test = brier(base_test.tolist(), y_test.tolist())
        cand_brier_test = brier(cand_test.tolist(), y_test.tolist())
        base_ece_test = ece(base_test.tolist(), y_test.tolist())
        cand_ece_test = ece(cand_test.tolist(), y_test.tolist())

        delta_brier = float(base_brier_test - cand_brier_test)
        delta_ece = float(base_ece_test - cand_ece_test)

        oos_improves = bool(delta_brier > IMPROVE_TOL)

        return {
            "status": STATUS_OK,
            "oos_improves": oos_improves,
            "oos_delta_brier": round(delta_brier, 8),
            "oos_delta_ece": round(delta_ece, 8),
            "n_train": int(len(base_train)),
            "n_test": int(len(base_test)),
            "platt_a": float(ab[0]),
            "platt_b": float(ab[1]),
            "note": "calibration, not edge",
        }

    except Exception as exc:  # noqa: BLE001 -- purity: never raises.
        logger.debug("recal_holdout_fit failed: %s", exc)
        return _insufficient("unexpected error: %s" % exc)


__all__ = ["fit_and_score", "MIN_OBS", "IMPROVE_TOL", "STATUS_OK", "STATUS_INSUFFICIENT"]
