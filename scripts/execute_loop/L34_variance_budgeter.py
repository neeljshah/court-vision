"""
L34 Variance Budgeter — Mean-variance portfolio allocation across betting buckets.

Public API:
    compute_daily_allocation(total_bankroll, edges, stds, correlations, max_weight_per_bucket)
        -> list[Allocation]
    mean_variance_optimize(expected_returns, stds, correlations, max_weight)
        -> dict[str, float]
    coordinate_with_sell_to_close(current_positions, variance_budget)
        -> list[dict]  — positions suggested for closure, ranked by variance contribution

Environment Variables:
    None.  L34 is a pure in-memory computation layer; it writes no files.

Paper vs Live Mode:
    L34 produces allocation recommendations only — it does not submit orders.
    The caller (L33 sell-to-close or the execution router) is responsible for
    acting on the returned suggestions in either paper or live mode.

L33 Integration:
    coordinate_with_sell_to_close() is the bridge to L33 (sell-to-close engine).
    Pass the current open positions with their variance footprints; L34 returns
    a prioritised close list whenever the portfolio variance exceeds the budget.
"""
from __future__ import annotations

import argparse
import logging
import math
import sys
from dataclasses import dataclass
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DEFAULTS
# ---------------------------------------------------------------------------

BUCKETS = ["cash_dfs", "gpp_dfs", "exchange_props", "exchange_game_lines"]

DEFAULTS_EDGES: dict[str, float] = {
    "cash_dfs": 0.04,
    "gpp_dfs": 0.10,
    "exchange_props": 0.055,
    "exchange_game_lines": 0.03,
}

DEFAULTS_STDS: dict[str, float] = {
    "cash_dfs": 0.08,
    "gpp_dfs": 0.40,
    "exchange_props": 0.15,
    "exchange_game_lines": 0.10,
}

# ---------------------------------------------------------------------------
# DATACLASS
# ---------------------------------------------------------------------------


@dataclass
class Allocation:
    bucket: str
    target_dollars: float
    target_pct: float
    expected_roi: float
    expected_std: float
    sharpe_contribution: float


# ---------------------------------------------------------------------------
# OPTIMIZATION CORE
# ---------------------------------------------------------------------------


def _build_cov_matrix(
    keys: list[str],
    stds: dict[str, float],
    correlations: Optional[dict[str, dict[str, float]]],
) -> tuple[np.ndarray, bool]:
    """Build covariance matrix Σ_ij = ρ_ij * σ_i * σ_j.

    Returns (cov_matrix, used_identity) where used_identity=True means
    the caller should log a PSD-fallback warning.
    """
    n = len(keys)
    sigma = np.array([stds[k] for k in keys], dtype=float)

    if correlations is None:
        corr = np.eye(n)
    else:
        corr = np.eye(n)
        for i, ki in enumerate(keys):
            for j, kj in enumerate(keys):
                if i != j:
                    rho = correlations.get(ki, {}).get(kj, 0.0)
                    corr[i, j] = rho

    # PSD check
    eigvals = np.linalg.eigvalsh(corr)
    if eigvals.min() < -1e-8:
        logger.warning(
            "Correlation matrix is not PSD (min eigenvalue=%.6f); "
            "falling back to identity correlation.",
            float(eigvals.min()),
        )
        corr = np.eye(n)
        used_identity = True
    else:
        used_identity = False

    cov = corr * np.outer(sigma, sigma)
    return cov, used_identity


def _portfolio_sharpe(weights: np.ndarray, mu: np.ndarray, cov: np.ndarray) -> float:
    """Return negative Sharpe (for minimisation)."""
    port_return = float(weights @ mu)
    port_var = float(weights @ cov @ weights)
    if port_var <= 0:
        return 0.0
    return -port_return / math.sqrt(port_var)


def _heuristic_weights(
    keys: list[str],
    mu: np.ndarray,
    sigma: np.ndarray,
    max_weight: float,
) -> np.ndarray:
    """Markowitz approximation: w_i ∝ μ_i / σ_i^2, then clip + renormalise."""
    raw = np.where(sigma > 0, mu / (sigma ** 2), 0.0)
    raw = np.clip(raw, 0.0, None)
    total = raw.sum()
    if total <= 0:
        return np.zeros(len(keys))
    w = raw / total
    # Clip to max_weight and renormalise iteratively (max 20 passes)
    for _ in range(20):
        w = np.clip(w, 0.0, max_weight)
        s = w.sum()
        if s <= 0:
            break
        w = w / s
        if w.max() <= max_weight + 1e-9:
            break
    return w


def mean_variance_optimize(
    expected_returns: dict[str, float],
    stds: dict[str, float],
    correlations: Optional[dict[str, dict[str, float]]] = None,
    max_weight: float = 0.6,
) -> dict[str, float]:
    """Maximise Sharpe = w'μ / sqrt(w'Σw) subject to sum(w)=1, 0≤w_i≤max_weight.

    Falls back to Markowitz heuristic (w_i ∝ μ_i / σ_i^2) if scipy is
    unavailable.  Returns a dict {bucket: weight} for buckets with positive
    expected return.  Buckets with expected_return <= 0 receive weight 0.
    """
    # Filter to positive-edge buckets only
    keys = [k for k in expected_returns if expected_returns[k] > 0]

    if not keys:
        return {k: 0.0 for k in expected_returns}

    n = len(keys)
    if n > 1 and max_weight * n < 1.0:
        raise ValueError(
            f"max_weight={max_weight} is too restrictive for {n} buckets "
            f"({max_weight * n:.3f} < 1.0). Increase max_weight or reduce buckets."
        )

    mu = np.array([expected_returns[k] for k in keys], dtype=float)
    sigma = np.array([stds[k] for k in keys], dtype=float)
    cov, _ = _build_cov_matrix(keys, stds, correlations)

    # Try scipy SLSQP
    weights: Optional[np.ndarray] = None
    try:
        from scipy.optimize import minimize, LinearConstraint, Bounds  # type: ignore

        def neg_sharpe(w: np.ndarray) -> float:
            return _portfolio_sharpe(w, mu, cov)

        w0 = np.full(n, 1.0 / n)
        bounds = Bounds(lb=np.zeros(n), ub=np.full(n, max_weight))
        constraints = {"type": "eq", "fun": lambda w: w.sum() - 1.0}
        result = minimize(
            neg_sharpe,
            w0,
            method="SLSQP",
            bounds=[(0.0, max_weight)] * n,
            constraints=constraints,
            options={"ftol": 1e-10, "maxiter": 1000},
        )
        if result.success or result.fun < 0:
            weights = np.clip(result.x, 0.0, max_weight)
            s = weights.sum()
            weights = weights / s if s > 0 else weights
        else:
            logger.warning(
                "scipy SLSQP did not converge (%s); falling back to heuristic.",
                result.message,
            )
    except ImportError:
        logger.info("scipy not available; using Markowitz heuristic for allocation.")

    if weights is None:
        weights = _heuristic_weights(keys, mu, sigma, max_weight)

    # Build output dict (zero for all-negative buckets)
    result_dict: dict[str, float] = {k: 0.0 for k in expected_returns}
    for k, w in zip(keys, weights):
        result_dict[k] = float(w)
    return result_dict


# ---------------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------------


def compute_daily_allocation(
    total_bankroll: float,
    edges: Optional[dict[str, float]] = None,
    stds: Optional[dict[str, float]] = None,
    correlations: Optional[dict[str, dict[str, float]]] = None,
    max_weight_per_bucket: float = 0.6,
) -> list[Allocation]:
    """Compute optimal daily dollar allocation across betting buckets.

    Parameters
    ----------
    total_bankroll:
        Total available capital in dollars. Must be > 0.
    edges:
        Expected ROI per bucket. Defaults to DEFAULTS_EDGES.
    stds:
        Expected return std per bucket. Defaults to DEFAULTS_STDS.
    correlations:
        Nested dict {bucket_i: {bucket_j: rho}}. Default: identity (independent).
    max_weight_per_bucket:
        Upper bound on any single bucket's weight. Default 0.6.

    Returns
    -------
    list[Allocation] sorted by target_dollars DESC.
    Returns [] if all edges are <= 0.
    """
    if total_bankroll <= 0:
        raise ValueError(f"total_bankroll must be > 0, got {total_bankroll}")

    edges = edges or DEFAULTS_EDGES
    stds = stds or DEFAULTS_STDS

    # Merge: start from defaults, override with supplied values
    all_keys = list({**DEFAULTS_EDGES, **edges}.keys())
    merged_edges: dict[str, float] = {**DEFAULTS_EDGES, **edges}
    merged_stds: dict[str, float] = {**DEFAULTS_STDS, **stds}
    # Keep only keys present in both
    common_keys = [k for k in all_keys if k in merged_edges and k in merged_stds]
    merged_edges = {k: merged_edges[k] for k in common_keys}
    merged_stds = {k: merged_stds[k] for k in common_keys}

    if all(v <= 0 for v in merged_edges.values()):
        logger.warning("All edges <= 0; returning empty allocation.")
        return []

    # Validate max_weight feasibility across positive-edge buckets.
    # Single positive-edge bucket is always OK (receives 100% weight).
    positive_buckets = [k for k, v in merged_edges.items() if v > 0]
    n_pos = len(positive_buckets)
    if n_pos > 1 and max_weight_per_bucket * n_pos < 1.0:
        raise ValueError(
            f"max_weight_per_bucket={max_weight_per_bucket} too restrictive: "
            f"{n_pos} positive-edge buckets require sum >= 1.0 "
            f"but max total = {max_weight_per_bucket * n_pos:.3f}."
        )

    weights = mean_variance_optimize(
        expected_returns=merged_edges,
        stds=merged_stds,
        correlations=correlations,
        max_weight=max_weight_per_bucket,
    )

    # Compute portfolio Sharpe denominator for sharpe_contribution
    active_keys = [k for k in common_keys if weights.get(k, 0.0) > 0]
    if active_keys:
        w_arr = np.array([weights[k] for k in active_keys])
        cov, _ = _build_cov_matrix(active_keys, merged_stds, correlations)
        port_var = float(w_arr @ cov @ w_arr)
        port_std = math.sqrt(max(port_var, 1e-12))
    else:
        port_std = 1.0

    allocations: list[Allocation] = []
    for k in common_keys:
        w = weights.get(k, 0.0)
        if w <= 0:
            continue
        target_dollars = w * total_bankroll
        allocations.append(
            Allocation(
                bucket=k,
                target_dollars=target_dollars,
                target_pct=w,
                expected_roi=merged_edges[k],
                expected_std=merged_stds[k],
                sharpe_contribution=w * merged_edges[k] / port_std,
            )
        )

    # Sort by target_dollars DESC
    allocations.sort(key=lambda a: a.target_dollars, reverse=True)

    # Rounding: ensure sum(target_dollars) == total_bankroll within $1
    total_allocated = sum(a.target_dollars for a in allocations)
    if allocations and abs(total_allocated - total_bankroll) > 1.0:
        # Apply residual to the largest bucket
        diff = total_bankroll - total_allocated
        allocations[0].target_dollars += diff
        allocations[0].target_pct = allocations[0].target_dollars / total_bankroll

    return allocations


# ---------------------------------------------------------------------------
# L33 integration — sell-to-close coordinator
# ---------------------------------------------------------------------------


def coordinate_with_sell_to_close(
    current_positions: list,
    variance_budget: float,
) -> list[dict]:
    """Return positions suggested for closure, ranked by variance contribution.

    Compares the portfolio's current variance utilisation against
    *variance_budget*.  If the portfolio is within budget, returns an empty
    list (no action required).  If the budget is exceeded, returns positions
    sorted highest variance-contribution first — the caller (L33) should close
    them in order until the remaining portfolio falls within budget.

    Parameters
    ----------
    current_positions:
        List of position dicts.  Each dict must contain at minimum:

            ``bucket``   (str)   — one of the BUCKETS values
            ``dollars``  (float) — dollars at risk in this position
            ``variance`` (float) — position-level variance estimate (σ² for
                                   the position's return distribution).
                                   Pass ``std**2`` if you have σ only.

        Optional key:
            ``position_id`` (str | int) — for caller tracking; echoed back.

    variance_budget:
        Maximum acceptable portfolio variance (sum of position variances,
        assuming independence).  Must be > 0.

    Returns
    -------
    list[dict]
        Subset of *current_positions* whose closure is recommended, each
        enriched with::

            ``variance_contribution_pct``  — this position's share of total variance
            ``close_priority``             — 1 = close first

        Sorted by variance contribution DESC (highest first).
        Empty list if portfolio variance is within budget or positions is empty.

    Raises
    ------
    ValueError
        If variance_budget <= 0 or a position dict is missing required keys.
    """
    if variance_budget <= 0:
        raise ValueError(f"variance_budget must be > 0, got {variance_budget}")

    if not current_positions:
        return []

    # Validate required keys
    required_keys = {"bucket", "dollars", "variance"}
    for i, pos in enumerate(current_positions):
        missing = required_keys - set(pos.keys())
        if missing:
            raise ValueError(
                f"Position[{i}] is missing required keys: {missing}. "
                f"Got keys: {set(pos.keys())}"
            )

    total_variance = sum(float(p["variance"]) for p in current_positions)

    if total_variance <= variance_budget:
        logger.debug(
            "coordinate_with_sell_to_close: portfolio variance %.6f <= budget %.6f — no action",
            total_variance,
            variance_budget,
        )
        return []

    logger.info(
        "coordinate_with_sell_to_close: portfolio variance %.6f > budget %.6f — "
        "selecting positions for closure",
        total_variance,
        variance_budget,
    )

    # Rank by variance contribution DESC
    enriched = []
    for pos in current_positions:
        pvar = float(pos["variance"])
        contrib_pct = pvar / total_variance if total_variance > 0 else 0.0
        enriched.append({**pos, "variance_contribution_pct": round(contrib_pct, 6)})

    enriched.sort(key=lambda p: p["variance_contribution_pct"], reverse=True)

    # Assign close priority and select only what's needed to get back within budget
    to_close: list[dict] = []
    remaining_variance = total_variance
    for rank, pos in enumerate(enriched, start=1):
        if remaining_variance <= variance_budget:
            break
        pos_out = {**pos, "close_priority": rank}
        to_close.append(pos_out)
        remaining_variance -= float(pos["variance"])

    logger.info(
        "coordinate_with_sell_to_close: recommending %d position(s) for closure "
        "(variance reduction: %.6f → %.6f, budget: %.6f)",
        len(to_close),
        total_variance,
        remaining_variance,
        variance_budget,
    )
    return to_close


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _fmt_allocation(allocs: list[Allocation], bankroll: float) -> str:
    if not allocs:
        return "  (no allocations — all edges <= 0)"
    lines = [
        f"  {'Bucket':<24} {'$Target':>10} {'Weight%':>8} {'E[ROI]':>8} "
        f"{'Std':>7} {'Sharpe Contrib':>15}"
    ]
    lines.append("  " + "-" * 78)
    for a in allocs:
        lines.append(
            f"  {a.bucket:<24} ${a.target_dollars:>9,.0f} {a.target_pct*100:>7.1f}% "
            f"{a.expected_roi*100:>7.1f}% {a.expected_std*100:>6.1f}% "
            f"{a.sharpe_contribution:>15.4f}"
        )
    lines.append("  " + "-" * 78)
    total_d = sum(a.target_dollars for a in allocs)
    total_p = sum(a.target_pct for a in allocs)
    lines.append(f"  {'TOTAL':<24} ${total_d:>9,.0f} {total_p*100:>7.1f}%")
    return "\n".join(lines)


def _cmd_allocate(args: argparse.Namespace) -> None:
    allocs = compute_daily_allocation(
        total_bankroll=args.bankroll,
        max_weight_per_bucket=args.max_weight,
    )
    print(f"=== Daily Allocation  (bankroll=${args.bankroll:,.0f}) ===")
    print(_fmt_allocation(allocs, args.bankroll))


def _cmd_status(_args: argparse.Namespace) -> None:
    allocs = compute_daily_allocation(total_bankroll=100_000.0)
    print("=== Variance Budget Status  (defaults, $100k) ===")
    print(_fmt_allocation(allocs, 100_000.0))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="L34_variance_budgeter.py",
        description="Mean-variance allocation across betting buckets.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    alloc_p = sub.add_parser("allocate", help="Compute allocation for a given bankroll")
    alloc_p.add_argument("--bankroll", type=float, required=True, help="Total bankroll in $")
    alloc_p.add_argument(
        "--max-weight",
        type=float,
        default=0.6,
        dest="max_weight",
        help="Max weight per bucket (default 0.6)",
    )

    sub.add_parser("status", help="Show default allocation for $100k bankroll")
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = _build_parser()
    args = parser.parse_args()
    dispatch = {"allocate": _cmd_allocate, "status": _cmd_status}
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
