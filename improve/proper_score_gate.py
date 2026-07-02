"""Multi-score SHIP/REJECT gate for the self-improvement ratchet (Milestone-8).

`score_gate(base_preds, cand_preds, y, kind=...)` compares a recalibration
CANDIDATE against the current BASE on every proper score that APPLIES to the
prediction kind, and ships ONLY when the candidate is at least as good as base
on ALL of them (proper scores are lower-is-better).

Hard-learned honesty invariant this enforces:
    A win on one proper score and a loss on ANOTHER is a REJECT, not a ship.
    The dissenting (regressing) score is named in `reasons`. Shipping on a
    one-sided "improvement" silently ships a regression -- the most expensive
    self-improvement bug class. This gate makes that impossible.

REUSE: the proper-score math comes from the validated eval-gate scoring module
(`scripts.platformkit.eval_gate.scoring`) -- brier / log_loss for probabilities,
crps_gaussian / pinball_loss for served interval distributions. This module adds
NO new math; it only orchestrates the unanimous-agreement decision.

Applicable scores by kind:
    kind="prob"     -> Brier, log-loss        (y in {0,1}, preds = P(y=1))
    kind="interval" -> CRPS, pinball           (preds = (mu, sigma) Gaussians)

Purity: never raises. Degenerate / malformed input -> ship=False with a reason.
There is NO dollar edge anywhere; the bar is proper-score calibration only.
"""
from __future__ import annotations

from typing import Any, Dict, Sequence, Tuple

import numpy as np

from scripts.platformkit.eval_gate.scoring import (
    brier,
    log_loss,
    crps_gaussian,
    pinball_loss,
)

# Proper scores per kind. Each entry: (metric_key, human_name). All are
# lower-is-better, so "candidate <= base" means "no regression".
_PROB_SCORES = ("brier", "logloss")
_INTERVAL_SCORES = ("crps", "pinball")

# Quantile levels used to grade a served interval band via averaged pinball
# loss. A symmetric 80% band (P10..P90) plus the median -- enough levels that a
# candidate cannot win on coverage while quietly degrading the central forecast.
_PINBALL_QUANTILES = (0.1, 0.25, 0.5, 0.75, 0.9)

# Numerical slack: a candidate must not be WORSE than base by more than this
# (lower-is-better), i.e. it must satisfy cand <= base + EPS. Pure float noise
# of identical predictions stays inside this band; a real regression does not.
_EPS = 1e-9


def _arr(x: Any) -> np.ndarray:
    return np.asarray(x, dtype=float)


def _finite(*arrays: np.ndarray) -> bool:
    return all(a.size > 0 and np.all(np.isfinite(a)) for a in arrays)


def _prob_scores(p: np.ndarray, y: np.ndarray) -> Dict[str, float]:
    """Brier + log-loss for a binary-probability forecast (lower better)."""
    return {"brier": brier(p, y), "logloss": log_loss(p, y)}


def _interval_scores(mu: np.ndarray, sigma: np.ndarray, y: np.ndarray) -> Dict[str, float]:
    """CRPS + averaged-pinball for a Gaussian predictive distribution.

    Pinball is averaged across `_PINBALL_QUANTILES`, mapping each Gaussian
    forecast to its quantile via the (mu, sigma) inverse-CDF, so a single band
    score grades the whole served interval rather than one bound.
    """
    crps = crps_gaussian(mu, sigma, y)
    # Map each band level to its Gaussian quantile via the (mu, sigma)
    # inverse-CDF, then average pinball across the band (no scipy).
    z = _z_for(_PINBALL_QUANTILES)
    losses = []
    for q, zq in zip(_PINBALL_QUANTILES, z):
        q_pred = mu + zq * sigma
        losses.append(pinball_loss(y, q_pred, q))
    return {"crps": crps, "pinball": float(np.mean(losses))}


def _z_for(quantiles: Sequence[float]) -> np.ndarray:
    """Standard-normal quantiles (inverse CDF) for the fixed band levels.

    Uses the Beasley-Springer/Moro rational approximation -- stdlib+numpy only,
    accurate to ~1e-9 in the central region we use (P10..P90). Pure helper so
    `_interval_scores` stays scipy-free like the rest of the eval gate.
    """
    a = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
    b = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01)
    out = np.empty(len(quantiles), dtype=float)
    for i, p in enumerate(quantiles):
        # All band levels are in the central region (0.02 < p < 0.98).
        r = p - 0.5
        s = r * r
        num = (((((a[0] * s + a[1]) * s + a[2]) * s + a[3]) * s + a[4]) * s + a[5]) * r
        den = ((((b[0] * s + b[1]) * s + b[2]) * s + b[3]) * s + b[4]) * s + 1.0
        out[i] = num / den
    return out


def _decide(
    base: Dict[str, float],
    cand: Dict[str, float],
    keys: Sequence[str],
) -> Tuple[bool, Dict[str, float], list]:
    """Unanimous lower-is-better agreement across `keys`.

    Returns (ship, deltas, reasons). deltas[k] = cand - base (negative = the
    candidate improved that score). ship is True iff NO applicable score
    regressed beyond `_EPS`. Every regressing score is named in reasons.
    """
    deltas: Dict[str, float] = {}
    reasons: list = []
    for k in keys:
        d = cand[k] - base[k]
        deltas[k] = float(d)
        if d > _EPS:  # candidate WORSE on this proper score -> dissent
            reasons.append(f"regression on {k}: cand={cand[k]:.6g} > base={base[k]:.6g}")
    ship = len(reasons) == 0
    if ship:
        reasons.append("candidate >= base on all applicable proper scores")
    return ship, deltas, reasons


def _flat(scores: Dict[str, float], suffix: str) -> Dict[str, float]:
    return {f"{k}_{suffix}": float(v) for k, v in scores.items()}


def _reject(reason: str) -> Dict[str, Any]:
    return {"ship": False, "scores": {}, "deltas": {}, "reasons": [reason]}


def score_gate(base_preds, cand_preds, y, *, kind: str = "prob") -> Dict[str, Any]:
    """SHIP/REJECT a recalibration candidate by unanimous proper-score agreement.

    Parameters
    ----------
    base_preds, cand_preds
        For kind="prob": array-like of P(y=1), aligned with `y`.
        For kind="interval": (mu, sigma) -- two aligned array-likes (a Gaussian
        predictive distribution per observation). A dict with keys "mu"/"sigma"
        is also accepted.
    y
        Realized outcomes (binary {0,1} for prob; continuous for interval).
    kind
        "prob" -> grade Brier + log-loss. "interval" -> grade CRPS + pinball.

    Returns
    -------
    dict with keys:
        ship    : bool  -- True only if candidate did not regress ANY applicable
                  proper score (lower-is-better) vs base.
        scores  : {<metric>_base, <metric>_cand} for every applicable metric.
        deltas  : {<metric>: cand - base} (negative = candidate improved).
        reasons : list[str] -- on reject, names the dissenting score(s); on
                  degenerate input, the failure reason.

    Never raises: any malformed / degenerate input -> ship=False with a reason.
    """
    try:
        y_arr = _arr(y)
        if kind == "prob":
            pb, pc = _arr(base_preds), _arr(cand_preds)
            if pb.ndim != 1 or pc.ndim != 1 or y_arr.ndim != 1:
                return _reject("prob preds and y must be 1-D arrays")
            if not _finite(pb, pc, y_arr):
                return _reject("degenerate input: empty or non-finite values")
            if not (len(pb) == len(pc) == len(y_arr)):
                return _reject("length mismatch between base, cand, and y")
            base_s = _prob_scores(pb, y_arr)
            cand_s = _prob_scores(pc, y_arr)
            keys = _PROB_SCORES
        elif kind == "interval":
            mb, sb = _unpack_interval(base_preds)
            mc, sc = _unpack_interval(cand_preds)
            if mb is None or mc is None:
                return _reject("interval preds must be (mu, sigma) pairs")
            if not _finite(mb, sb, mc, sc, y_arr):
                return _reject("degenerate input: empty or non-finite values")
            if not (len(mb) == len(mc) == len(y_arr)):
                return _reject("length mismatch between base, cand, and y")
            if np.any(sb <= 0) or np.any(sc <= 0):
                return _reject("degenerate input: sigma must be strictly positive")
            base_s = _interval_scores(mb, sb, y_arr)
            cand_s = _interval_scores(mc, sc, y_arr)
            keys = _INTERVAL_SCORES
        else:
            return _reject(f"unknown kind: {kind!r} (expected 'prob' or 'interval')")

        # Guard: any non-finite score (e.g. a divergent log-loss) is degenerate.
        if not all(np.isfinite(v) for v in list(base_s.values()) + list(cand_s.values())):
            return _reject("degenerate input: a proper score was non-finite")

        ship, deltas, reasons = _decide(base_s, cand_s, keys)
        scores = {**_flat(base_s, "base"), **_flat(cand_s, "cand")}
        return {"ship": ship, "scores": scores, "deltas": deltas, "reasons": reasons}
    except Exception as exc:  # purity contract: never raise to the caller
        return _reject(f"degenerate input: {type(exc).__name__}: {exc}")


def _unpack_interval(preds) -> Tuple[Any, Any]:
    """Normalize interval preds to (mu_array, sigma_array) or (None, None)."""
    try:
        if isinstance(preds, dict):
            mu, sigma = preds["mu"], preds["sigma"]
        else:
            mu, sigma = preds  # (mu, sigma) tuple/list
        return _arr(mu), _arr(sigma)
    except Exception:
        return None, None
