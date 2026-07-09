"""scripts.platformkit.benchmarks.crps_market.market_dist -- turn the raw
line_history 'total' rows for one game into a market-implied Gaussian(mu, sigma)
for the total-runs/points distribution.

Each devigged (line, P(over line)) pair is one point on the market's implied CDF
(probit space: Phi^-1(1 - P(over)) = (line - mu) / sigma is linear in the line).
  * >=2 DISTINCT lines (line movement open->close, or cross-book) -> least-squares
    fit of BOTH mu and sigma from market data alone (the honest, pure case).
  * exactly 1 distinct line -> mu solved from that single point ASSUMING a
    supplied fallback sigma (the fit-season climatology sd, itself never derived
    from the eval-window market or outcomes) -- labeled n_lines_used=1 so the
    readout can separate this fallback case from the pure multi-line fit.
"""
from __future__ import annotations

from typing import List, Tuple

import numpy as np
from scipy.stats import norm

_EPS = 1e-4


def devig_points(rows: List[dict]) -> List[Tuple[float, float]]:
    """rows: raw line_history dicts (side in {over,under}, one game). Returns
    deduped (line, p_over) points, averaging across books/snapshots at the same
    line. p_over is that row's own devigged_prob when side=='over', else 1-it."""
    by_line: dict = {}
    for r in rows:
        line = r.get("line")
        if line is None:
            continue
        p = float(r["devigged_prob"])
        p_over = p if r.get("side") == "over" else 1.0 - p
        by_line.setdefault(float(line), []).append(p_over)
    return sorted((line, float(np.mean(ps))) for line, ps in by_line.items())


def fit_market_gaussian(points: List[Tuple[float, float]],
                         sigma_fallback: float) -> Tuple[float, float, int]:
    """(mu, sigma, n_lines_used) for one game's devigged total-line points."""
    if not points:
        raise ValueError("no market points for this game")
    if len(points) == 1:
        line, p_over = points[0]
        p_over = min(max(p_over, _EPS), 1.0 - _EPS)
        z = norm.ppf(1.0 - p_over)
        mu = line - sigma_fallback * z
        return float(mu), float(sigma_fallback), 1
    lines = np.array([p[0] for p in points])
    p_over = np.clip(np.array([p[1] for p in points]), _EPS, 1.0 - _EPS)
    z = norm.ppf(1.0 - p_over)
    # lines = mu + sigma * z  ->  linear regression of lines on z
    A = np.vstack([np.ones_like(z), z]).T
    (mu, sigma), *_ = np.linalg.lstsq(A, lines, rcond=None)
    # near-collinear points (lines close together, similar p_over -> ~zero slope
    # in the regression's other axis) make sigma blow up or collapse; a total-
    # runs sigma outside a generous multiple of the fit-season climatology sd is
    # not a market-implied estimate, it is regression noise -- fall back to the
    # single most-informative point (closest to a 50/50 line) + climatology sd.
    if not np.isfinite(sigma) or not (0.5 * sigma_fallback <= sigma <= 3.0 * sigma_fallback):
        line, p_over = min(points, key=lambda t: abs(t[1] - 0.5))
        return fit_market_gaussian([(line, p_over)], sigma_fallback)
    return float(mu), float(sigma), len(points)


__all__ = ["devig_points", "fit_market_gaussian"]
