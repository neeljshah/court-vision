"""Log-odds forecast pooling with a bounded market-deviation guard."""
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence, Tuple, Union

import numpy as np

_EPS = 1e-9
_MIN_EXTREMIZE = 0.5
_DEFAULT_CAP = 1.6
_GRID_POINTS = 241
_MIN_FIT_ROWS = 20
_MAX_DEVIATION = 0.15

Number = Union[float, np.ndarray]

__all__ = ["to_logit", "from_logit", "blend", "fit_extremize", "guard_vs_market"]


def to_logit(p: Number, eps: float = _EPS) -> Number:
    """Return clipped log odds for a probability or probability array."""
    arr = np.clip(np.asarray(p, dtype=float), eps, 1.0 - eps)
    out = np.log(arr / (1.0 - arr))
    return float(out) if np.ndim(p) == 0 else out


def from_logit(z: Number, eps: float = _EPS) -> Number:
    """Return the clipped inverse-logit of a scalar or array."""
    arr = np.asarray(z, dtype=float)
    out = np.clip(1.0 / (1.0 + np.exp(-np.clip(arr, -700.0, 700.0))), eps, 1.0 - eps)
    return float(out) if np.ndim(z) == 0 else out


def _as_matrix(components: Any) -> Tuple[np.ndarray, list[str]]:
    if isinstance(components, Mapping):
        names = list(components)
        if not names:
            raise ValueError("logit_blend: no components supplied")
        mat = np.column_stack([np.asarray(components[name], dtype=float).ravel() for name in names])
    else:
        rows = list(components)
        if not rows:
            raise ValueError("logit_blend: no components supplied")
        if isinstance(rows[0], Mapping):
            names = list(rows[0])
            mat = np.asarray([[float(row[name]) for name in names] for row in rows], dtype=float)
        else:
            mat = np.asarray(rows, dtype=float)
            if mat.ndim == 1:
                mat = mat.reshape(1, -1)
            names = ["c%d" % index for index in range(mat.shape[1])]
    if mat.ndim != 2 or mat.shape[1] == 0:
        raise ValueError("logit_blend: components must form an n x k matrix")
    if not np.isfinite(mat).all() or mat.min() < 0.0 or mat.max() > 1.0:
        raise ValueError("logit_blend: component probabilities must be finite and in [0, 1]")
    return mat, names


def _weights(weights: Optional[Any], names: Sequence[str]) -> np.ndarray:
    if weights is None:
        return np.full(len(names), 1.0 / len(names))
    values = ([float(weights[name]) for name in names] if isinstance(weights, Mapping)
              else list(weights))
    result = np.asarray(values, dtype=float)
    if result.shape != (len(names),) or not np.isfinite(result).all() or result.min() < 0.0:
        raise ValueError("logit_blend: weights must be finite, non-negative, and aligned")
    total = float(result.sum())
    if total <= 0.0:
        raise ValueError("logit_blend: weights must sum to > 0")
    return result / total


def blend(component_probs: Any, weights: Optional[Any] = None, extremize: float = 1.0) -> Number:
    """Pool component probabilities by weighted mean log odds."""
    exponent = float(extremize)
    if not np.isfinite(exponent) or exponent < 0.0:
        raise ValueError("logit_blend: extremize must be finite and >= 0")
    matrix, names = _as_matrix(component_probs)
    result = from_logit((to_logit(matrix) @ _weights(weights, names)) * exponent)
    return float(result[0]) if matrix.shape[0] == 1 else result


def fit_extremize(components: Any, outcomes: Sequence[float], cap: float = _DEFAULT_CAP,
                  weights: Optional[Any] = None) -> float:
    """Fit a capped log-odds exponent by Brier score on a supplied fit set."""
    ceiling = float(cap)
    if not np.isfinite(ceiling) or ceiling < 1.0:
        raise ValueError("logit_blend: cap must be finite and >= 1.0")
    matrix, names = _as_matrix(components)
    labels = np.asarray(outcomes, dtype=float).ravel()
    if labels.shape[0] != matrix.shape[0] or not np.isfinite(labels).all() or labels.min() < 0.0 or labels.max() > 1.0:
        raise ValueError("logit_blend: outcomes must be finite [0, 1] values aligned to components")
    if matrix.shape[0] < _MIN_FIT_ROWS:
        return 1.0
    base = to_logit(matrix) @ _weights(weights, names)
    grid = np.linspace(_MIN_EXTREMIZE, ceiling, _GRID_POINTS)
    briers = np.mean((from_logit(np.outer(base, grid)) - labels[:, None]) ** 2, axis=0)
    return float(grid[int(np.argmin(briers))])


def guard_vs_market(blended: Number, market_prob: Number,
                    max_abs_deviation: float = _MAX_DEVIATION) -> Number:
    """Clamp a probability to a fixed maximum absolute deviation from market."""
    deviation = float(max_abs_deviation)
    market = np.asarray(market_prob, dtype=float)
    if not np.isfinite(deviation) or deviation < 0.0:
        raise ValueError("logit_blend: max_abs_deviation must be finite and >= 0")
    if not np.isfinite(market).all() or market.min() < 0.0 or market.max() > 1.0:
        raise ValueError("logit_blend: market_prob must be finite and in [0, 1]")
    out = np.clip(np.asarray(blended, dtype=float), np.clip(market - deviation, _EPS, 1.0 - _EPS),
                  np.clip(market + deviation, _EPS, 1.0 - _EPS))
    return float(out) if np.ndim(blended) == 0 and np.ndim(market_prob) == 0 else out
