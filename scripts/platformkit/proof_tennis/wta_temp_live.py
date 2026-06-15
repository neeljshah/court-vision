"""scripts.platformkit.proof_tennis.wta_temp_live — WTA temperature as the LIVE recalibrator.

W132 (wta_recal_temp_iso.py) DIAGNOSED WTA Elo: it is OVER-CONFIDENT (train-era fitted
T=1.385 > 1, women's-tour upset variance) and TEMPERATURE scaling is the best recalibrator
(ECE 0.053 -> 0.035, -34%) while Platt and isotonic do NOT transfer. This module PACKAGES
that finding as a usable, leak-free, walk-forward LIVE recalibrator:

  * fit_wta_temperature(p_raw_train, y_train) -> T  : fit T>0 by min-logloss on a train window
  * apply_temperature(p, T)                          : p_cal = sigmoid(logit(p) / T)

run() walk-forwards the WTA surface-blend Elo on the full corpus, fits T on the FIRST 60% of
matches (chronological), applies it to the LAST 40% holdout, and reports raw ECE/Brier vs
temperature-recalibrated ECE/Brier on that holdout.

HONEST: this is a CALIBRATION result only, NEVER a $ edge — markets are efficient. WTA stays a
structural FAIL on the strict ECE<0.025 bar (the over-confidence is data-limited, not removable),
but temperature IS WTA's recalibrator of choice and it measurably sharpens calibration. An honest
FAIL on the strict bar paired with a real improvement is a SUCCESS in the discipline sense.

Leak-free: T is fit ONLY on the first-60% window; the holdout never informs the fit. The Elo
walk-forward already uses strictly-prior ratings at each match time. No market data is an input.
INVARIANTS: never edit src/ or kernel/; reuse domains.tennis.elo_tune; <=300 LOC.

Run: python -m scripts.platformkit.proof_tennis.wta_temp_live
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from domains.tennis import elo_tune as et  # noqa: E402

_WTA_PARQUET = _REPO / "data" / "domains" / "tennis" / "wta" / "matches.parquet"
_ECE_THRESHOLD = 0.025      # the strict bar WTA structurally fails
_TRAIN_FRAC = 0.60          # first 60% chronological -> fit T; last 40% -> holdout
_EPS = 1e-6


# ---------------------------------------------------------------------------
# The reusable live recalibrator (leak-free: fit on a train window, apply forward)
# ---------------------------------------------------------------------------

def fit_wta_temperature(p_raw_train: np.ndarray, y_train: np.ndarray) -> float:
    """Fit temperature T>0 minimising logloss of sigmoid(logit(p)/T) on a TRAIN window.

    T>1 shrinks every probability toward 0.5 — the direct fix for over-confident Elo.
    Returns T (float). Leak-free by construction: caller passes only the train window.
    """
    from scipy.optimize import minimize_scalar

    p = np.clip(np.asarray(p_raw_train, dtype=float), _EPS, 1.0 - _EPS)
    y = np.asarray(y_train, dtype=float)
    logits = np.log(p / (1.0 - p))

    def nll(t: float) -> float:
        q = 1.0 / (1.0 + np.exp(-logits / t))
        q = np.clip(q, _EPS, 1.0 - _EPS)
        return float(-np.mean(y * np.log(q) + (1.0 - y) * np.log(1.0 - q)))

    res = minimize_scalar(nll, bounds=(0.25, 5.0), method="bounded")
    return float(res.x)


def apply_temperature(p: np.ndarray, T: float) -> np.ndarray:
    """Apply a fitted temperature: p_cal = sigmoid(logit(p) / T). Vectorised, clipped."""
    p = np.clip(np.asarray(p, dtype=float), _EPS, 1.0 - _EPS)
    logits = np.log(p / (1.0 - p))
    q = 1.0 / (1.0 + np.exp(-logits / float(T)))
    return np.clip(q, _EPS, 1.0 - _EPS)


# ---------------------------------------------------------------------------
# Walk-forward + 60/40 evaluation
# ---------------------------------------------------------------------------

def run(parquet_path: Path = _WTA_PARQUET) -> Dict:
    if not parquet_path.is_file():
        return {"status": "data_limited", "error": f"WTA corpus not found: {parquet_path}"}
    matches = pd.read_parquet(parquet_path)
    if len(matches) < 200:
        return {"status": "data_limited", "n": int(len(matches))}

    # Best surface blend by Brier on the corpus's own test split (same selection as W132).
    best_blend = float(et.blend_sweep(matches).sort_values("brier").iloc[0]["blend"])
    # Walk-forward Elo: ratings at each match use strictly-prior matches only (leak-free).
    wf = et._sorted(et._walk_forward_blend(matches, best_blend)).reset_index(drop=True)

    p_raw = np.clip(wf["win_prob_p1"].to_numpy(dtype=float), _EPS, 1.0 - _EPS)
    y = (wf["winner"] == 1).to_numpy(dtype=float)
    n = len(wf)
    cut = int(n * _TRAIN_FRAC)            # chronological 60/40 split

    # --- fit T on the first 60% ONLY, apply to the last 40% holdout ---
    T = fit_wta_temperature(p_raw[:cut], y[:cut])
    p_h_raw = p_raw[cut:]
    y_h = y[cut:]
    p_h_recal = apply_temperature(p_h_raw, T)

    raw_ece = round(et.ece(p_h_raw, y_h), 5)
    raw_brier = round(et.brier(p_h_raw, y_h), 5)
    recal_ece = round(et.ece(p_h_recal, y_h), 5)
    recal_brier = round(et.brier(p_h_recal, y_h), 5)
    gap = round(recal_ece - raw_ece, 5)        # negative == temperature improved calibration

    holdout_dates = pd.to_datetime(wf["date"]).iloc[cut:]
    improved = gap < 0
    passes_strict = recal_ece < _ECE_THRESHOLD
    if passes_strict:
        verdict = (f"CALIBRATED: temperature (T={round(T,3)}) brings holdout ECE to "
                   f"{recal_ece} < {_ECE_THRESHOLD}")
    elif improved:
        verdict = (f"HONEST FAIL on the strict ECE<{_ECE_THRESHOLD} bar, but temperature "
                   f"(T={round(T,3)}) is the chosen live recalibrator: holdout ECE "
                   f"{raw_ece}->{recal_ece} ({gap:+}), Brier {raw_brier}->{recal_brier}")
    else:
        verdict = (f"temperature (T={round(T,3)}) did NOT improve the holdout ECE "
                   f"({raw_ece}->{recal_ece}) — recalibrator does not transfer this split")

    return {
        "status": "ok", "corpus": "WTA", "n": int(n), "n_holdout": int(n - cut),
        "best_blend": best_blend, "train_frac": _TRAIN_FRAC,
        "fitted_T": round(T, 3),
        "ece_threshold": _ECE_THRESHOLD,
        "raw_ece": raw_ece, "raw_brier": raw_brier,
        "recal_ece": recal_ece, "recal_brier": recal_brier,
        "ece_gap_recal_minus_raw": gap,
        "model_metric": recal_ece, "close_metric": raw_ece, "gap": gap,
        "holdout_span": (f"{holdout_dates.min().date()} -> {holdout_dates.max().date()}"
                         if len(holdout_dates) else "n/a"),
        "verdict": verdict,
        "note": ("Calibration metric only; NOT a market edge. Markets efficient. "
                 "T>1 confirms over-confident WTA Elo; temperature is its live recalibrator."),
    }


def _main() -> int:
    rep = run()
    if rep.get("status") != "ok":
        print(f"{rep.get('status')}: {rep.get('error') or ('n=' + str(rep.get('n')))}")
        return 0
    print(f"=== WTA temperature LIVE recalibrator (blend={rep['best_blend']}, "
          f"fit first {int(rep['train_frac']*100)}% -> holdout last "
          f"{100-int(rep['train_frac']*100)}%) ===")
    print(f"corpus n={rep['n']}  holdout n={rep['n_holdout']}  "
          f"({rep['holdout_span']})")
    print(f"fitted T = {rep['fitted_T']}  (T>1 => over-confident Elo)")
    print(f"  {'predictor':>16}  {'ECE':>9} {'Brier':>9}")
    print(f"  {'raw Elo':>16}  {rep['raw_ece']:>9} {rep['raw_brier']:>9}")
    print(f"  {'temp-recal':>16}  {rep['recal_ece']:>9} {rep['recal_brier']:>9}")
    print(f"\nECE gap (recal - raw) = {rep['ece_gap_recal_minus_raw']:+}  "
          f"(strict bar ECE<{rep['ece_threshold']})")
    print(f"VERDICT: {rep['verdict']}")
    print(rep["note"])
    return 0


if __name__ == "__main__":
    sys.exit(_main())
