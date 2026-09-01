"""scripts/platformkit/logit_blend.py -- log-odds pooling with a fitted extremizer.

Averaging forecasts in log-odds space and then scaling the pooled log-odds by an
exponent > 1 is the Satopaa / Good Judgment Project "extremized logit pool".
Independent forecasters each hedge toward 0.5, so their average is systematically
under-confident; the exponent undoes part of that shrinkage.  The exponent is
FITTED on a held-out set with a hard cap -- never assumed, never unbounded.

Honesty rail: `guard_vs_market` clamps the pooled probability so it can never sit
further than `max_abs_deviation` from a market price we have already verified as
efficient.  We are willing to sharpen INSIDE that band.  We are not willing to
extremize past a market we have measured as efficient -- an unbounded exponent
would manufacture confidence we have no evidence for.

CALIBRATION ONLY.  Nothing in this module is an edge, an ROI, or a profit claim.

Accepted component shapes (all handled by `_as_matrix`):
  {"a": 0.6, "b": 0.4}                  one forecast per component  -> scalar out
  {"a": [0.6, 0.7], "b": [0.4, 0.5]}    aligned series per component -> array out
  [{"a": 0.6, "b": 0.4}, {...}]         one dict per row
  [[0.6, 0.4], [0.7, 0.5]]              raw n x k matrix
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence, Tuple, Union

import numpy as np

_EPS = 1e-9              # probability clip; keeps logit finite at p == 0 or 1
_MIN_EXTREMIZE = 0.5     # allow shrinkage too: over-confident components exist
_DEFAULT_CAP = 1.6       # hard cap on the fitted exponent (Satopaa-range)
_GRID_POINTS = 241       # 1-D sweep resolution over [_MIN_EXTREMIZE, cap]
_MIN_FIT_ROWS = 20       # thinner than this -> refuse to fit, stay at 1.0
_MAX_DEVIATION = 0.15    # default honesty rail half-width vs. the market

Number = Union[float, np.ndarray]

__all__ = [
    "to_logit",
    "from_logit",
    "blend",
    "fit_extremize",
    "guard_vs_market",
]


# ---------------------------------------------------------------------------
# log-odds transforms
# ---------------------------------------------------------------------------

def to_logit(p: Number, eps: float = _EPS) -> Number:
    """log(p / (1 - p)) with clipping, so p == 0 / 1 stay finite."""
    arr = np.clip(np.asarray(p, dtype=float), eps, 1.0 - eps)
    out = np.log(arr / (1.0 - arr))
    return float(out) if np.ndim(p) == 0 else out


def from_logit(z: Number, eps: float = _EPS) -> Number:
    """Inverse of `to_logit`; overflow-safe and clipped back into (0, 1)."""
    arr = np.asarray(z, dtype=float)
    out = np.clip(1.0 / (1.0 + np.exp(-np.clip(arr, -700.0, 700.0))), eps, 1.0 - eps)
    return float(out) if np.ndim(z) == 0 else out


# ---------------------------------------------------------------------------
# input normalisation
# ---------------------------------------------------------------------------

def _as_matrix(components: Any) -> Tuple[np.ndarray, list]:
    """Normalise any accepted component shape to (n_rows x k_components, names)."""
    if isinstance(components, Mapping):
        names = list(components)
        if not names:
            raise ValueError("logit_blend: no components supplied")
        cols = [np.asarray(components[n], dtype=float).ravel() for n in names]
        mat = np.column_stack(cols)
    else:
        rows = list(components)
        if not rows:
            raise ValueError("logit_blend: no components supplied")
        if isinstance(rows[0], Mapping):
            names = list(rows[0])
            mat = np.asarray([[float(r[n]) for n in names] for r in rows], dtype=float)
        else:
            mat = np.asarray(rows, dtype=float)
            if mat.ndim == 1:
                mat = mat.reshape(1, -1)
            names = ["c%d" % i for i in range(mat.shape[1])]
    if mat.ndim != 2 or mat.shape[1] == 0:
        raise ValueError("logit_blend: components must form an n x k matrix")
    if not np.isfinite(mat).all():
        raise ValueError("logit_blend: component probabilities must be finite")
    if mat.min() < 0.0 or mat.max() > 1.0:
        raise ValueError("logit_blend: component probabilities must lie in [0, 1]")
    return mat, names


def _weights(weights: Optional[Any], names: Sequence[str]) -> np.ndarray:
    """Non-negative weights aligned to `names`, normalised to sum 1."""
    k = len(names)
    if weights is None:
        return np.full(k, 1.0 / k)
    if isinstance(weights, Mapping):
        missing = [n for n in names if n not in weights]
        if missing:
            raise ValueError("logit_blend: missing weight for %s" % missing)
        w = np.asarray([float(weights[n]) for n in names], dtype=float)
    else:
        w = np.asarray(list(weights), dtype=float)
    if w.shape != (k,):
        raise ValueError("logit_blend: expected %d weights, got %s" % (k, w.shape))
    if not np.isfinite(w).all() or w.min() < 0.0:
        raise ValueError("logit_blend: weights must be finite and non-negative")
    total = float(w.sum())
    if total <= 0.0:
        raise ValueError("logit_blend: weights must sum to > 0")
    return w / total


def _pool(mat: np.ndarray, w: np.ndarray, extremize: float) -> np.ndarray:
    """Weighted mean log-odds, scaled by the extremizing exponent."""
    return from_logit((to_logit(mat) @ w) * float(extremize))


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def blend(
    component_probs: Any,
    weights: Optional[Any] = None,
    extremize: float = 1.0,
) -> Number:
    """Pool component probabilities in log-odds space.

    extremize == 1.0 is the plain (weighted) log-odds mean; > 1.0 sharpens,
    < 1.0 shrinks toward 0.5.  Identical components with extremize == 1.0
    return that component's probability unchanged.

    Returns a float for one-forecast-per-component input, else an ndarray.
    """
    ex = float(extremize)
    if not np.isfinite(ex) or ex < 0.0:
        raise ValueError("logit_blend: extremize must be finite and >= 0")
    mat, names = _as_matrix(component_probs)
    out = _pool(mat, _weights(weights, names), ex)
    return float(out[0]) if mat.shape[0] == 1 else out


def fit_extremize(
    components: Any,
    outcomes: Sequence[float],
    cap: float = _DEFAULT_CAP,
    weights: Optional[Any] = None,
) -> float:
    """Exponent in [_MIN_EXTREMIZE, cap] minimising Brier on the fit set.

    The cap is HARD: a fit set that "wants" a larger exponent gets `cap`, never
    more.  Extremizing corrects for hedging; it is not a licence to invent
    confidence, and an uncapped fit will happily overfit a lucky fit window.

    A fit set thinner than _MIN_FIT_ROWS returns 1.0 (the plain mean) rather
    than a number nobody should trust.
    """
    cap = float(cap)
    if not np.isfinite(cap) or cap < 1.0:
        raise ValueError("logit_blend: cap must be finite and >= 1.0")
    mat, names = _as_matrix(components)
    y = np.asarray(outcomes, dtype=float).ravel()
    if y.shape[0] != mat.shape[0]:
        raise ValueError(
            "logit_blend: %d outcomes for %d component rows" % (y.shape[0], mat.shape[0])
        )
    if not np.isfinite(y).all() or y.min() < 0.0 or y.max() > 1.0:
        raise ValueError("logit_blend: outcomes must be finite and in [0, 1]")
    if mat.shape[0] < _MIN_FIT_ROWS:
        return 1.0
    z = to_logit(mat) @ _weights(weights, names)
    # ponytail: dense monotone sweep over the capped interval, not golden-section --
    # Brier(a) is smooth but not guaranteed unimodal, and 241 evals is microseconds.
    grid = np.linspace(_MIN_EXTREMIZE, cap, _GRID_POINTS)
    briers = np.mean((from_logit(np.outer(z, grid)) - y[:, None]) ** 2, axis=0)
    best = float(grid[int(np.argmin(briers))])
    return float(min(max(best, _MIN_EXTREMIZE), cap))


def guard_vs_market(
    blended: Number,
    market_prob: Number,
    max_abs_deviation: float = _MAX_DEVIATION,
) -> Number:
    """Honesty rail: clamp `blended` to within `max_abs_deviation` of the market.

    We have measured these markets as efficient on team strength.  A blend that
    lands 0.40 away from the close is a modelling artifact, not a discovery, so
    the guard clamps it back to the band edge.  This is a calibration rail, not
    a trading rule: it asserts nothing about the market being wrong.
    """
    d = float(max_abs_deviation)
    if not np.isfinite(d) or d < 0.0:
        raise ValueError("logit_blend: max_abs_deviation must be finite and >= 0")
    m = np.asarray(market_prob, dtype=float)
    if not np.isfinite(m).all() or m.min() < 0.0 or m.max() > 1.0:
        raise ValueError("logit_blend: market_prob must be finite and in [0, 1]")
    lo = np.clip(m - d, _EPS, 1.0 - _EPS)
    hi = np.clip(m + d, _EPS, 1.0 - _EPS)
    out = np.clip(np.asarray(blended, dtype=float), lo, hi)
    return float(out) if np.ndim(blended) == 0 and np.ndim(market_prob) == 0 else out
