"""domains.mlb.totals_sigma_wf -- Leak-free walk-forward empirical sigma for MLB totals.

MOTIVATION
----------
The existing negbinom_engine.py fits dispersion (r) via Method-of-Moments on the raw
variance of historical totals (fit_r_mom).  That estimator conflates (a) true
over-dispersion in run scoring with (b) game-to-game variation in the *expected* run
rate lambda.  As a result, the fitted r is too small (~7), causing the 50% predictive
interval to over-cover (~55%) on held-out data.

This module corrects that by *targeting coverage*: we binary-search for the NB
dispersion r such that the NB(r, lam_total) predictive interval covers exactly 50% of
training games (first half of corpus, date-sorted), then validate the fitted r on the
held-out second half.

ACCEPTANCE CRITERIA (enforced by the per-file test)
-----------------------------------------------------
  * 50% band covers ~50% +/- 3 pp on held-out half2.
  * Pinball loss (sum of q=0.25 and q=0.75 quantile losses) on half2 is <= the
    Poisson(lam_total) baseline -- never worsens by fitting.
  * No future row used in the fit (all lam_total values are walk-forward; only the
    first-half *outcomes* inform the r search).
  * Deterministic: fixed binary-search bounds, no randomness in the analytic NB PPF.

DESIGN
------
  * lambda source: domains.mlb.inning_engine.RunRateState (same walk-forward EW
    exponential-smoothing used by the predictor and the negbinom_engine).  We replay
    the corpus in date order, snapshot lam_total = lam_home + lam_away *before*
    updating on each game's outcomes -- fully leak-free.
  * Interval: [NB.ppf(0.25, r, p), NB.ppf(0.75, r, p)] where p = r/(r+lam_total).
    These are the 25th and 75th percentile of NB(r, lam_total).  Coverage = fraction
    of actual totals inside the interval.
  * Baseline for pinball comparison: Poisson(lam_total) -- the model the system uses
    without fitted dispersion (r -> infinity in the NB limit).
  * fit() returns (r_fit, diagnostics_dict) so callers can integrate the sigma into
    the markets layer.

HONEST: calibration/accuracy only. Markets are efficient; NO dollar edge is claimed.
INVARIANTS: never edit src/ kernel/ api/; imports are read-only; <=300 LOC.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
from scipy.stats import nbinom, poisson

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_R_LO = 1.0        # binary search lower bound for r
_R_HI = 10_000.0   # binary search upper bound; large r -> near-Poisson
_SEARCH_ITERS = 80  # bisection iterations; 80 iters on log scale -> 1e-24 precision
_TARGET_COV = 0.50  # desired 50% predictive-interval coverage


# ---------------------------------------------------------------------------
# Walk-forward lambda builder (reads RunRateState; no outcome leak)
# ---------------------------------------------------------------------------

def _build_wf_lambdas(df) -> Tuple[np.ndarray, np.ndarray]:
    """Return (lam_total, actual_total) arrays in date order.

    lam_total[i] is computed from RunRateState BEFORE updating on row i's outcomes,
    so it is leak-free: only games 0..i-1 inform lam_total[i].
    """
    from domains.mlb.inning_engine import RunRateState

    rr = RunRateState()
    lam_tots: list[float] = []
    actual_tots: list[float] = []

    for _, row in df.iterrows():
        home = str(row["home_team"])
        away = str(row["away_team"])
        season = int(row["season"])
        hr = float(row["home_runs"])
        ar = float(row["away_runs"])

        lh, la = rr.snapshot(home, away, season)
        lam_tots.append(lh + la)
        actual_tots.append(hr + ar)
        rr.update(home, away, hr, ar)

    return np.array(lam_tots, dtype=float), np.array(actual_tots, dtype=float)


# ---------------------------------------------------------------------------
# Core scoring helpers
# ---------------------------------------------------------------------------

def _nb_quantiles(r: float, lam_arr: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Vectorized NB 25th and 75th percentiles for an array of lambdas.

    p_i = r / (r + lam_i).  Returns (q25_arr, q75_arr) as float arrays.
    Using scipy vectorised ppf avoids a Python loop over rows (10-20x faster).
    """
    p_arr = r / (r + lam_arr)
    q25 = nbinom.ppf(0.25, r, p_arr).astype(float)
    q75 = nbinom.ppf(0.75, r, p_arr).astype(float)
    return q25, q75


def _coverage_at_r(
    r: float, lam_arr: np.ndarray, actual_arr: np.ndarray
) -> float:
    """Fraction of games where actual_total in [NB.ppf(0.25), NB.ppf(0.75)]."""
    q25, q75 = _nb_quantiles(r, lam_arr)
    n = len(lam_arr)
    if n == 0:
        return 0.0
    return float(np.mean((q25 <= actual_arr) & (actual_arr <= q75)))


def _pinball_at_r(
    r: float, lam_arr: np.ndarray, actual_arr: np.ndarray
) -> float:
    """Mean pinball loss (sum of q25 + q75 terms) for NB(r, lam_total)."""
    if len(lam_arr) == 0:
        return 0.0
    q25, q75 = _nb_quantiles(r, lam_arr)
    e25 = actual_arr - q25
    e75 = actual_arr - q75
    pb25 = np.where(e25 >= 0, 0.25 * e25, -0.75 * e25)
    pb75 = np.where(e75 >= 0, 0.75 * e75, -0.25 * e75)
    return float(np.mean(pb25) + np.mean(pb75))


def _pinball_poisson(lam_arr: np.ndarray, actual_arr: np.ndarray) -> float:
    """Baseline pinball using Poisson(lam_total) quantiles (vectorized)."""
    if len(lam_arr) == 0:
        return 0.0
    q25 = poisson.ppf(0.25, lam_arr).astype(float)
    q75 = poisson.ppf(0.75, lam_arr).astype(float)
    e25 = actual_arr - q25
    e75 = actual_arr - q75
    pb25 = np.where(e25 >= 0, 0.25 * e25, -0.75 * e25)
    pb75 = np.where(e75 >= 0, 0.75 * e75, -0.25 * e75)
    return float(np.mean(pb25) + np.mean(pb75))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fit(
    games_df,
    *,
    target_coverage: float = _TARGET_COV,
) -> Tuple[float, Dict]:
    """Fit walk-forward NB dispersion r on the first half of games_df.

    Parameters
    ----------
    games_df : pd.DataFrame
        Must contain columns: date, home_team, away_team, season, home_runs, away_runs.
        Rows need NOT be pre-sorted; fit() sorts by date internally.
    target_coverage : float
        Desired 50% predictive-interval coverage on training half. Default: 0.50.

    Returns
    -------
    r_fit : float
        NB dispersion fitted on the first half (leak-free).
    diag : dict
        Diagnostics: n_train, n_val, r_fit, train_coverage, val_coverage,
        pinball_nb_val, pinball_poisson_val, pinball_delta (negative = NB wins),
        passes (True iff val criteria met).
    """
    import pandas as pd

    df = games_df.sort_values("date").reset_index(drop=True)
    lam_arr, actual_arr = _build_wf_lambdas(df)
    n = len(df)
    mid = n // 2

    # Fit r by targeting coverage on half1 (binary search on log scale)
    lo_r, hi_r = _R_LO, _R_HI
    lam_train = lam_arr[:mid]
    actual_train = actual_arr[:mid]

    for _ in range(_SEARCH_ITERS):
        mid_r = np.exp(0.5 * (np.log(lo_r) + np.log(hi_r)))
        cov = _coverage_at_r(mid_r, lam_train, actual_train)
        # r is INVERSELY related to coverage (larger r -> narrower interval -> lower coverage)
        if cov > target_coverage:
            lo_r = mid_r   # interval too wide; increase r to narrow it
        else:
            hi_r = mid_r   # interval too narrow; decrease r to widen it

    r_fit = float(np.exp(0.5 * (np.log(lo_r) + np.log(hi_r))))

    # Evaluate on held-out half2
    lam_val = lam_arr[mid:]
    actual_val = actual_arr[mid:]

    train_cov = _coverage_at_r(r_fit, lam_train, actual_train)
    val_cov = _coverage_at_r(r_fit, lam_val, actual_val)
    pb_nb = _pinball_at_r(r_fit, lam_val, actual_val)
    pb_pois = _pinball_poisson(lam_val, actual_val)

    passes = (
        abs(val_cov - 0.50) <= 0.03
        and pb_nb <= pb_pois
    )

    diag: Dict = {
        "n_train": mid,
        "n_val": n - mid,
        "r_fit": r_fit,
        "train_coverage": float(train_cov),
        "val_coverage": float(val_cov),
        "pinball_nb_val": float(pb_nb),
        "pinball_poisson_val": float(pb_pois),
        "pinball_delta": float(pb_nb - pb_pois),
        "passes": bool(passes),
        "note": (
            "r fitted on first 50% by coverage targeting (no future-row leak). "
            "Baseline = Poisson(lam_total). CALIBRATION only; NO edge claimed."
        ),
    }
    return r_fit, diag


def load_and_fit(
    *,
    repo_root: Optional[Path] = None,
) -> Tuple[float, Dict]:
    """Load the canonical MLB corpus and call fit().

    Convenience wrapper for scripts / tests that don't already hold the DataFrame.
    """
    import pandas as pd

    root = repo_root or Path(__file__).resolve().parents[2]
    path = root / "data" / "domains" / "mlb" / "games.parquet"
    if not path.exists():
        raise FileNotFoundError(f"MLB corpus not found at {path}")
    df = pd.read_parquet(path)
    return fit(df)


__all__ = ["fit", "load_and_fit"]
