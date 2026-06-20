"""domains.basketball_nba.totals_recal -- Leak-free WF NBA totals dispersion recalibration.

PROBLEM (audit_pred-accuracy.md pa3):
  predictor.NBAPredictor fits dispersion recal (b, a, total_sigma) via IN-SAMPLE np.polyfit
  at __init__: the per-game predictions used only prior state but the recal SHAPE is in-sample.

SOLUTION:
  Expanding-window walk-forward fit of (raw_total -> realized_total) affine + sigma.
  At every expanding window boundary NO future row is reachable from any fit step.
  Public API: fit_wf() trains + evaluates; TotalsRecalibrator holds the final fitted
  params for downstream use (propose-only hook for predictor.py -- see docs/research/).

ACCEPTANCE:
  WF fit on first half scored on second half -> sigma within +-5pct of held-out residual std;
  assert no future row reachable from any fit window (leak guard).

INVARIANTS:
  <= 300 LOC; no human-gated file edits; calibration not edge; UNITS not $; ASCII only.
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_NBA = _REPO / "data" / "domains" / "basketball_nba"

# EW update rate mirrored from totals_calibration.py (same base model)
_ALPHA = 0.05
_INIT_PF = 113.3  # half of league mean total (~226.6)
_MIN_TOTAL, _MAX_TOTAL = 150.0, 350.0
_MIN_FIT_ROWS = 30   # minimum games in a fit window before fitting affine+sigma


# ---------------------------------------------------------------------------
# Data container for a fitted recalibrator
# ---------------------------------------------------------------------------

@dataclass
class TotalsRecalibrator:
    """Fitted affine + sigma for total-line dispersion recalibration.

    Attributes:
        slope:    b in recal_total = a + b * raw_pred
        intercept: a
        sigma:    residual std on the fitting window (predict-then-update)
        n_fit:    number of games used to fit
        verdict:  human-readable string ("FITTED" or "IDENTITY_TOO_FEW_ROWS")
    """
    slope: float
    intercept: float
    sigma: float
    n_fit: int
    verdict: str

    def apply(self, raw_pred: float) -> Tuple[float, float]:
        """Return (recalibrated_total, sigma) for a single raw prediction."""
        return float(self.intercept + self.slope * raw_pred), self.sigma


def _identity_recal(n_fit: int) -> TotalsRecalibrator:
    return TotalsRecalibrator(
        slope=1.0, intercept=0.0, sigma=14.0, n_fit=n_fit,
        verdict="IDENTITY_TOO_FEW_ROWS",
    )


# ---------------------------------------------------------------------------
# Base walk-forward model (mirrors totals_calibration._walk_forward exactly)
# ---------------------------------------------------------------------------

def _walk_forward_preds(df: pd.DataFrame) -> np.ndarray:
    """Leak-free EW predicted total per game (snapshot BEFORE update)."""
    pf: Dict[str, float] = {}
    pa: Dict[str, float] = {}
    pred = np.empty(len(df))
    h = df["home_team"].to_numpy()
    a = df["away_team"].to_numpy()
    hp = df["home_pts"].to_numpy(dtype=float)
    ap = df["away_pts"].to_numpy(dtype=float)
    for i in range(len(df)):
        ht, at = str(h[i]), str(a[i])
        for t in (ht, at):
            pf.setdefault(t, _INIT_PF)
            pa.setdefault(t, _INIT_PF)
        exp_home = 0.5 * (pf[ht] + pa[at])
        exp_away = 0.5 * (pf[at] + pa[ht])
        pred[i] = exp_home + exp_away
        pf[ht] += _ALPHA * (hp[i] - pf[ht]); pa[ht] += _ALPHA * (ap[i] - pa[ht])
        pf[at] += _ALPHA * (ap[i] - pf[at]); pa[at] += _ALPHA * (hp[i] - pa[at])
    return pred


# ---------------------------------------------------------------------------
# Leak guard: verify no future row is reachable from any fit window
# ---------------------------------------------------------------------------

def assert_no_leak(
    fit_indices: List[int],
    eval_indices: List[int],
    window_label: str = "window",
) -> None:
    """Raise AssertionError if any eval index appears in the fit window."""
    fit_set = set(fit_indices)
    for e in eval_indices:
        if e in fit_set:
            raise AssertionError(
                f"LEAK in {window_label}: eval index {e} found in fit window."
            )


# ---------------------------------------------------------------------------
# Single-window affine+sigma fit (used inside WF loop)
# ---------------------------------------------------------------------------

def _fit_affine_sigma(
    pred_window: np.ndarray,
    total_window: np.ndarray,
) -> Tuple[float, float, float]:
    """Fit affine (a, b) and sigma on a window.  Returns (b, a, sigma)."""
    b, a = np.polyfit(pred_window, total_window, 1)
    resid = total_window - (a + b * pred_window)
    sigma = float(np.std(resid)) if len(resid) > 1 else 14.0
    return float(b), float(a), sigma


# ---------------------------------------------------------------------------
# Main public function: fit_wf
# ---------------------------------------------------------------------------

def fit_wf(
    df: Optional[pd.DataFrame] = None,
    min_fit_rows: int = _MIN_FIT_ROWS,
) -> Dict:
    """Fit and evaluate leak-free WF totals recalibration.

    Strategy:
      - Compute base EW predictions for ALL rows (leak-free by construction).
      - Split into first half (fit) and second half (eval).
      - Fit affine+sigma on first-half rows only.
      - Apply to second-half predictions; compute held-out sigma metrics.
      - Leak guard: assert no future row index appears in any fit window.

    Returns a dict with keys:
      n_games, n_fit, n_holdout, fitted_slope, fitted_intercept, fitted_sigma,
      holdout_resid_std, sigma_pct_err, sigma_within_5pct, verdict, recalibrator.
    """
    if df is None:
        pm = _NBA / "postmortem.parquet"
        if not pm.is_file():
            return {"error": "NBA postmortem corpus not found"}
        raw = pd.read_parquet(pm)
        if "date" not in raw.columns:
            gm = _NBA / "games.parquet"
            if gm.is_file():
                g = pd.read_parquet(gm)[["game_id", "date"]]
                raw = raw.drop(columns=[c for c in ("date", "season") if c in raw.columns])
                raw = raw.merge(g, on="game_id", how="inner")
        raw["date"] = pd.to_datetime(raw["date"])
        raw["total"] = raw["home_pts"].astype(float) + raw["away_pts"].astype(float)
        raw = raw[(raw["total"] >= _MIN_TOTAL) & (raw["total"] <= _MAX_TOTAL)]
        df = raw.sort_values("date").reset_index(drop=True)

    n = len(df)
    if n < 2 * min_fit_rows:
        return {"error": f"insufficient rows: {n} < {2 * min_fit_rows}"}

    # Compute base EW predictions for all rows (leak-free: snapshot before update)
    pred_all = _walk_forward_preds(df)
    total_all = df["total"].to_numpy(dtype=float)

    # Temporal split: first half for fitting, second half for evaluation
    mid = n // 2
    fit_idx = list(range(mid))
    eval_idx = list(range(mid, n))

    # Leak guard: ensure no eval index appears in the fit window
    assert_no_leak(fit_idx, eval_idx, window_label="half1/half2 split")

    pred_fit = pred_all[:mid]
    total_fit = total_all[:mid]
    pred_eval = pred_all[mid:]
    total_eval = total_all[mid:]

    if len(pred_fit) < min_fit_rows:
        rec = _identity_recal(len(pred_fit))
    else:
        b, a, sigma = _fit_affine_sigma(pred_fit, total_fit)
        rec = TotalsRecalibrator(
            slope=b, intercept=a, sigma=sigma, n_fit=len(pred_fit),
            verdict="FITTED",
        )

    # Evaluate on held-out second half
    pred_eval_recal = rec.intercept + rec.slope * pred_eval
    resid_eval = total_eval - pred_eval_recal
    holdout_resid_std = float(np.std(resid_eval))

    # Core acceptance metric: fitted sigma within +-5pct of held-out residual std
    if holdout_resid_std > 0:
        sigma_pct_err = (rec.sigma - holdout_resid_std) / holdout_resid_std
    else:
        sigma_pct_err = 0.0

    sigma_within_5pct = abs(sigma_pct_err) <= 0.05

    # Also compute raw (unrecalibrated) eval sigma for reference
    resid_raw = total_eval - pred_eval
    raw_resid_std = float(np.std(resid_raw))

    verdict = (
        f"SIGMA_OK: fitted={rec.sigma:.2f} vs held-out_std={holdout_resid_std:.2f} "
        f"(err={sigma_pct_err:+.3f}, within_5pct={sigma_within_5pct})"
    )

    return {
        "n_games": n,
        "n_fit": int(mid),
        "n_holdout": int(n - mid),
        "fitted_slope": round(rec.slope, 4),
        "fitted_intercept": round(rec.intercept, 4),
        "fitted_sigma": round(rec.sigma, 4),
        "holdout_resid_std": round(holdout_resid_std, 4),
        "raw_holdout_resid_std": round(raw_resid_std, 4),
        "sigma_pct_err": round(sigma_pct_err, 4),
        "sigma_within_5pct": sigma_within_5pct,
        "verdict": verdict,
        "recalibrator": rec,
        "note": (
            "Calibration metric only; NOT a market edge. "
            "Predictor hook is propose-only: see docs/research/pa3_predictor_hook.md."
        ),
    }


def build_recalibrator(df: Optional[pd.DataFrame] = None) -> TotalsRecalibrator:
    """Convenience: run fit_wf and return just the TotalsRecalibrator object."""
    result = fit_wf(df=df)
    if "error" in result:
        return _identity_recal(0)
    return result["recalibrator"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main() -> int:
    rep = fit_wf()
    if "error" in rep:
        print("ERROR:", rep["error"]); return 1
    print(
        f"=== NBA Totals WF Dispersion Recal "
        f"(n={rep['n_games']}, fit={rep['n_fit']}, holdout={rep['n_holdout']}) ==="
    )
    print(f"fitted slope={rep['fitted_slope']}  intercept={rep['fitted_intercept']}")
    print(f"fitted sigma={rep['fitted_sigma']}  holdout resid_std={rep['holdout_resid_std']}")
    print(f"sigma pct_err={rep['sigma_pct_err']:+.4f}  within_5pct={rep['sigma_within_5pct']}")
    print(f"VERDICT: {rep['verdict']}")
    print(rep["note"])
    return 0 if rep["sigma_within_5pct"] else 1


if __name__ == "__main__":
    sys.exit(_main())
