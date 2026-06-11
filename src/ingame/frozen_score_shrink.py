"""src/ingame/frozen_score_shrink.py — P3.3: between-poll team-score re-price + its RMSE+bias serve gate.

RED-B Attack 1 (the deepest in-game finding): a 'frozen-distribution shrink' that re-prices the pre-rolled
final toward the LIVE score is shrink-toward-current BY CONSTRUCTION. For a SKEWED quantity it wins MAE
while worsening RMSE+bias — the keystone artifact (the MAE-vs-RMSE memory). A resim-parity gate would
certify it as 'correct' while it is biased. So this module:

  - DEFAULTS to NO-OP: serve the unshrunk pre-rolled sim mean (the calibrated mean, at the MAE ceiling).
  - Gates the shrink re-price behind its OWN RMSE+bias serve gate (``gate_shrink``), NOT a parity check.
    The shrink ships ONLY if it beats the unshrunk mean on RMSE AND does not worsen bias magnitude, on the
    elapsed-time-bucketed eval cache. Until that is shown, every serve is the unshrunk mean.

``demonstrate_artifact`` (and the test) make the trap concrete: on a right-skewed outcome distribution the
shrink-toward-current (≈ the median) predictor has LOWER MAE but HIGHER RMSE and a negative bias vs the
mean — which is exactly why the gate scores RMSE+bias, never MAE.

numpy lazy-imported. DEFAULT-OFF: reached only under CV_INGAME_SHRINK; default mode is 'noop'.
"""
from __future__ import annotations

from typing import Dict, Tuple


def reprice(prior_final: float, live_so_far: float, remaining_frac: float,
            mode: str = "noop") -> float:
    """Re-price one team's projected final.

    mode='noop' (DEFAULT): return ``prior_final`` unchanged (the unshrunk pre-rolled sim mean).
    mode='shrink': translate toward the live score — final = live_so_far + (prior_final - live_so_far)*rf.
                   As rf->0 this collapses onto the scoreboard (the shrink-toward-current operation). This
                   path is GATED and never the default; it ships only if gate_shrink approves it.
    """
    if mode == "noop":
        return float(prior_final)
    rf = min(1.0, max(0.0, float(remaining_frac)))
    return float(live_so_far) + (float(prior_final) - float(live_so_far)) * rf


def rmse_bias(preds, actuals) -> Tuple[float, float, float]:
    """Return (rmse, signed_bias, mae) for a vector of predictions vs realized outcomes."""
    import numpy as np
    p = np.asarray(preds, dtype=float)
    a = np.asarray(actuals, dtype=float)
    err = p - a
    rmse = float(np.sqrt(np.mean(err ** 2)))
    bias = float(np.mean(err))
    mae = float(np.mean(np.abs(err)))
    return rmse, bias, mae


def gate_shrink(shrink_preds, noop_preds, actuals, rmse_eps: float = 1e-9) -> Dict[str, object]:
    """Decide whether the shrink re-price may serve, vs the unshrunk no-op baseline.

    Ships the shrink ONLY if it BEATS the no-op on RMSE and does NOT worsen |bias| (RED-B Attack 1).
    MAE is reported but is NEVER the deciding criterion (the artifact wins MAE). Returns a verdict dict;
    ``serve`` is 'shrink' or 'noop'.
    """
    s_rmse, s_bias, s_mae = rmse_bias(shrink_preds, actuals)
    n_rmse, n_bias, n_mae = rmse_bias(noop_preds, actuals)
    beats_rmse = s_rmse < n_rmse - rmse_eps
    not_worse_bias = abs(s_bias) <= abs(n_bias) + rmse_eps
    serve = "shrink" if (beats_rmse and not_worse_bias) else "noop"
    return {
        "serve": serve,
        "shrink": {"rmse": s_rmse, "bias": s_bias, "mae": s_mae},
        "noop": {"rmse": n_rmse, "bias": n_bias, "mae": n_mae},
        "beats_rmse": beats_rmse, "not_worse_bias": not_worse_bias,
        "note": ("shrink approved" if serve == "shrink"
                 else "shrink REJECTED -> serve unshrunk mean (RMSE/bias guard; MAE is not a gate)"),
    }


def demonstrate_artifact(seed: int = 7, n: int = 20000) -> Dict[str, object]:
    """Make the MAE-vs-RMSE artifact concrete on a right-skewed outcome distribution.

    The mean minimizes RMSE; the median (≈ shrink-toward-current) minimizes MAE. On a right-skewed
    distribution median < mean, so the 'shrink' predictor wins MAE but LOSES RMSE and runs negatively
    biased. gate_shrink therefore (correctly) rejects it. This is the whole reason the gate uses RMSE.
    """
    import numpy as np
    rng = np.random.default_rng(seed)
    actuals = rng.lognormal(mean=3.0, sigma=0.6, size=n)   # right-skewed
    mean_pred = float(actuals.mean())
    median_pred = float(np.median(actuals))                 # the shrink-toward-current proxy
    noop_preds = np.full(n, mean_pred)
    shrink_preds = np.full(n, median_pred)
    verdict = gate_shrink(shrink_preds, noop_preds, actuals)
    verdict["mean_pred"] = mean_pred
    verdict["median_pred"] = median_pred
    return verdict
