"""domains.soccer.calibration — Leak-free walk-forward recalibration for soccer O/U 2.5.

RELIABILITY IMPROVEMENT — NOT AN EDGE CLAIM.
Calibration != edge. Better-calibrated probabilities do NOT imply beating the market.
The raw Poisson O/U model exhibits miscalibration at low lambda (ECE ~0.107 on real corpus).
This module corrects that purely as a reliability improvement.

ALGORITHM CHOICE — Isotonic regression vs Platt/logistic:
  We use IsotonicRegression (PAVA) because:
    1. It is monotone: higher raw prob → higher calibrated prob (sensible for a ranking model).
    2. It makes no parametric assumption about the shape of the miscalibration, which is
       important when the low-lambda regime is systematically biased (Poisson underestimates
       at small lambdas due to the zero-inflated true distribution).
    3. sklearn's out_of_bounds="clip" keeps calibrated probs in [0, 1] automatically.
  Platt (logistic) would only correct linear-log miscalibration, which is too restrictive
  for a model that is systematically wrong near the boundaries.

WALK-FORWARD CONTRACT (strictly leak-free):
  For event i, the calibration map is fitted using ONLY events 0 … i-1 (strictly before i).
  Events before the warmup window (MIN_HISTORY) pass through raw (no calibration applied).
  The calibrator for event i is completely independent of outcome i and all future outcomes.

IMPORTS: stdlib + numpy + sklearn.  No src.*, no domains.nba.*.
"""
from __future__ import annotations

import sys
from typing import Sequence, Tuple

import numpy as np
from sklearn.isotonic import IsotonicRegression

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_HISTORY: int = 50   # expanding-window warmup; pass-through below this count
CALIBRATION_NOTE: str = (
    "calibration != edge: better-calibrated probabilities do NOT imply beating the market"
)

# ---------------------------------------------------------------------------
# Core: walk-forward calibrated probabilities
# ---------------------------------------------------------------------------


def walk_forward_calibrate(
    raw_probs: Sequence[float],
    outcomes: Sequence[float],
    min_history: int = MIN_HISTORY,
) -> np.ndarray:
    """Return calibrated probabilities using a strictly leak-free walk-forward fit.

    For each event i:
      - If i < min_history: pass through raw_probs[i] unchanged (insufficient history).
      - Else: fit IsotonicRegression on (raw_probs[:i], outcomes[:i])  — ONLY events
        strictly before i — then transform raw_probs[i].

    Parameters
    ----------
    raw_probs:
        Sequence of raw model probabilities in [0, 1], length N, in date order.
    outcomes:
        Sequence of binary outcomes {0, 1}, length N, aligned to raw_probs.
    min_history:
        Minimum number of preceding events required before calibration is applied.
        Events with index < min_history pass through as raw. Default: 50.

    Returns
    -------
    np.ndarray of shape (N,)
        Calibrated probabilities, clipped to [0, 1].  Aligned index-for-index to inputs.

    Notes
    -----
    This is strictly leak-free: the IsotonicRegression for event i is fitted and
    transformed using only events 0 … i-1.  It never sees event i's outcome or any
    future outcome.  Calibration does NOT imply a betting edge.
    """
    p = np.asarray(raw_probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    n = len(p)
    if n != len(y):
        raise ValueError(f"raw_probs and outcomes must have equal length ({n} vs {len(y)})")

    calibrated = np.empty(n, dtype=float)
    ir = IsotonicRegression(out_of_bounds="clip")

    for i in range(n):
        if i < min_history:
            # Not enough history — pass through raw
            calibrated[i] = float(p[i])
        else:
            # Guard: drop pairs where raw_prob or outcome is NaN/inf so
            # IsotonicRegression never receives invalid data.  For all-finite
            # inputs the mask is all-True and behaviour is bit-identical.
            valid_window = np.isfinite(p[:i]) & np.isfinite(y[:i])
            if valid_window.any():
                ir.fit(p[:i][valid_window], y[:i][valid_window])
                # If the query point itself is invalid, pass it through as-is
                # (np.clip below keeps finite values in [0,1], leaves NaN alone).
                if np.isfinite(p[i]):
                    calibrated[i] = float(ir.transform([p[i]])[0])
                else:
                    calibrated[i] = float(p[i])
            else:
                # No valid history yet — pass through raw.
                calibrated[i] = float(p[i])

    return np.clip(calibrated, 0.0, 1.0)


# ---------------------------------------------------------------------------
# Convenience: raw vs calibrated from a SoccerAdapter feature_bundle
# ---------------------------------------------------------------------------


def calibrate_adapter(
    adapter,  # SoccerAdapter (typed loosely to avoid circular/F5 import)
    seasons: Sequence[int],
    min_history: int = MIN_HISTORY,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Pull (raw, outcome, dates) from SoccerAdapter.feature_bundle and calibrate.

    Parameters
    ----------
    adapter:
        A SoccerAdapter instance.  Imported lazily by the caller to respect F5.
    seasons:
        Season list forwarded to feature_bundle.
    min_history:
        Warmup count forwarded to walk_forward_calibrate.

    Returns
    -------
    raw_probs : np.ndarray shape (N,)
    calibrated_probs : np.ndarray shape (N,)
    outcomes : np.ndarray shape (N,)
        All three aligned index-for-index to the feature_bundle date order.

    Notes
    -----
    calibration != edge — see CALIBRATION_NOTE constant.
    """
    bundle = adapter.feature_bundle(hypothesis=None, seasons=seasons)
    raw_probs = bundle.signal_col.copy()
    outcomes = bundle.target.copy()
    calibrated_probs = walk_forward_calibrate(raw_probs, outcomes, min_history=min_history)
    return raw_probs, calibrated_probs, outcomes


# ---------------------------------------------------------------------------
# ECE wrapper (imports kernel function so we don't reimplement)
# ---------------------------------------------------------------------------


def compute_ece(probs: np.ndarray, outcomes: np.ndarray, bins: int = 10) -> float:
    """Compute Expected Calibration Error using kernel.validation.proof_metrics.ece.

    Falls back to an inline implementation if the kernel module is unavailable
    (e.g. isolated test environments).  The formula is identical in both cases.

    calibration != edge.
    """
    try:
        from kernel.validation.proof_metrics import ece as _kernel_ece
        return _kernel_ece(probs, outcomes, bins=bins)
    except ImportError:
        # Inline fallback — identical algorithm to kernel.validation.proof_metrics.ece
        p = np.asarray(probs, dtype=float)
        y = np.asarray(outcomes, dtype=float)
        edges = np.linspace(0.0, 1.0, bins + 1)
        total = len(p)
        if total == 0:
            return 0.0
        ece_val = 0.0
        for i in range(bins):
            lo, hi = edges[i], edges[i + 1]
            mask = (p >= lo) & (p < hi) if i < bins - 1 else (p >= lo) & (p <= hi)
            n_bin = int(mask.sum())
            if n_bin == 0:
                continue
            ece_val += (n_bin / total) * abs(float(y[mask].mean()) - float(p[mask].mean()))
        return float(ece_val)


# ---------------------------------------------------------------------------
# __main__ CLI: measure raw vs calibrated ECE on real soccer corpus
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    print(f"NOTE: {CALIBRATION_NOTE}")
    print()

    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[2]
    matches_path = repo_root / "data" / "domains" / "soccer" / "matches.parquet"

    if not matches_path.exists():
        print("Real soccer corpus not found at", matches_path)
        print("Skipping CLI measurement (no data).")
        sys.exit(0)

    try:
        from domains.soccer.adapter import SoccerAdapter
    except ImportError as exc:
        print(f"Could not import SoccerAdapter: {exc}")
        sys.exit(1)

    adapter = SoccerAdapter(repo_root=repo_root)
    try:
        bundle = adapter.feature_bundle(hypothesis=None, seasons=[])
    except Exception as exc:
        # feature_bundle raises if seasons filter leaves no rows; pass empty to get all
        try:
            import pandas as pd
            import pyarrow.parquet as pq
            df = pd.read_parquet(str(matches_path))
            all_seasons = sorted(df["season"].unique().tolist())
            bundle = adapter.feature_bundle(hypothesis=None, seasons=all_seasons)
        except Exception as exc2:
            print(f"Could not load feature bundle: {exc2}")
            sys.exit(1)

    raw = bundle.signal_col.copy()
    outcomes = bundle.target.copy()
    calibrated = walk_forward_calibrate(raw, outcomes, min_history=MIN_HISTORY)

    raw_ece = compute_ece(raw, outcomes)
    cal_ece = compute_ece(calibrated, outcomes)

    n = len(raw)
    n_calibrated = n - MIN_HISTORY
    print(f"Corpus size      : {n} events")
    print(f"Warmup events    : {MIN_HISTORY} (pass-through raw)")
    print(f"Calibrated events: {max(0, n_calibrated)}")
    print(f"Raw ECE          : {raw_ece:.4f}")
    print(f"Calibrated ECE   : {cal_ece:.4f}")

    if cal_ece < raw_ece:
        delta = raw_ece - cal_ece
        print(f"ECE reduction    : {delta:.4f} ({delta / raw_ece * 100:.1f}%)")
        print("Walk-forward recalibration IMPROVED calibration.")
    else:
        delta = cal_ece - raw_ece
        print(f"ECE change       : +{delta:.4f} (no improvement or negligible)")
        print("Walk-forward recalibration did NOT reduce ECE on this corpus.")

    print()
    print(f"REMINDER: {CALIBRATION_NOTE}")
