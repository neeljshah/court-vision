"""
Closed-form Empirical Bayes hierarchical pooled priors (C15 prototype).

Durable home: kernel/model_ops/bayes_hier.py (HUMAN-GATED) — this is the platformkit prototype.

A PRIOR IS NOT AN EDGE: shrinkage improves small-sample ESTIMATES (lower MSE / better
calibration on sparse groups), it does NOT imply beating the market.  Cross-sport transfer
= pooling sparse per-archetype/per-team rates toward a sport- or global-level prior.

Usage:
    python -m scripts.platformkit.hier_priors   # synthetic demo, prints MSE table
"""

from __future__ import annotations

import sys
import numpy as np


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def eb_beta_binomial(
    k: np.ndarray,
    n: np.ndarray,
    *,
    max_iter: int = 100,
) -> dict:
    """Beta-Binomial Empirical Bayes via marginal moment-matching.

    Parameters
    ----------
    k : array of int
        Successes per group.
    n : array of int
        Trials per group (may contain zeros).
    max_iter : int
        Reserved for future iterative refinement; unused in closed-form path.

    Returns
    -------
    dict with keys:
        a, b            – estimated Beta prior parameters (floats > 0)
        pooled_mean     – m = sum(k) / sum(n)  (scalar)
        kappa           – estimated concentration  (scalar >= 1)
        shrunk_rates    – posterior means (k+a)/(n+a+b), groups with n==0 get a/(a+b)
        raw_rates       – k/n  (n==0 groups get pooled_mean to avoid div-by-zero)
    """
    k = np.asarray(k, dtype=float)
    n = np.asarray(n, dtype=float)

    if k.shape != n.shape:
        raise ValueError("k and n must have the same shape")

    total_k = k.sum()
    total_n = n.sum()

    # Pooled mean — guard total_n == 0
    m = total_k / total_n if total_n > 0 else 0.5

    # Method-of-moments estimate of kappa (concentration).
    # For groups with n > 0 compute the observed rate variance and compare to
    # the binomial variance expected under the pooled mean.
    mask = n > 0
    if mask.sum() >= 2:
        p_g = k[mask] / n[mask]          # raw per-group rates
        obs_var = float(np.var(p_g))      # variance of group-level rates
        binom_var = m * (1.0 - m)         # expected within-group binomial variance
        # Under Beta-Binomial:  Var(p_g) ≈ m(1-m)/(1 + kappa)
        # => kappa ≈ m(1-m)/Var(p_g) - 1
        if obs_var > 1e-12 and binom_var > 1e-12:
            kappa = binom_var / obs_var - 1.0
        else:
            # Degenerate variance (all groups identical) → trust each group fully
            kappa = 1e6
        # Guard: concentration must be positive and finite
        kappa = float(np.clip(kappa, 1.0, 1e8))
    else:
        # Fewer than 2 non-zero groups — fall back to a uninformative-ish prior
        kappa = 2.0

    a = m * kappa
    b = (1.0 - m) * kappa

    # Posterior mean for each group
    shrunk = np.where(n > 0, (k + a) / (n + a + b), a / (a + b))

    # Raw rates — n==0 groups get pooled_mean (no information)
    # Guard: use max(n, 1) to avoid div-by-zero in the numpy broadcast before masking
    safe_n = np.where(n > 0, n, 1.0)
    raw = np.where(n > 0, k / safe_n, m)

    return {
        "a": a,
        "b": b,
        "pooled_mean": m,
        "kappa": kappa,
        "shrunk_rates": shrunk,
        "raw_rates": raw,
    }


def eb_normal(
    means: np.ndarray,
    variances: np.ndarray,
    *,
    pooled: float | None = None,
) -> dict:
    """Normal-Normal / James-Stein-style Empirical Bayes shrinkage.

    Shrinks per-group means toward the global mean by the ratio
        w_g = tau2 / (tau2 + var_g)
    where tau2 (between-group variance) is estimated as
        max(0, Var(means) - mean(variances)).

    Parameters
    ----------
    means     : per-group observed means  (1-D array)
    variances : per-group sampling variances  (1-D array, same shape)
    pooled    : optional override for the global mean; defaults to mean(means)

    Returns
    -------
    dict with keys:
        global_mean    – the pooled (or supplied) reference mean
        tau2           – estimated between-group variance (>= 0)
        shrunk_means   – posterior means
        raw_means      – original means (copy)
        shrink_weights – w_g in [0,1]; 0 = no shrinkage, 1 = full pooling
    """
    means = np.asarray(means, dtype=float)
    variances = np.asarray(variances, dtype=float)

    if means.shape != variances.shape:
        raise ValueError("means and variances must have the same shape")
    if means.ndim != 1:
        raise ValueError("means must be 1-D")

    g = len(means)
    global_mean = float(np.mean(means)) if pooled is None else float(pooled)

    if g < 2:
        # Single group — can't estimate between-group variance
        shrunk_means = means.copy()
        return {
            "global_mean": global_mean,
            "tau2": 0.0,
            "shrunk_means": shrunk_means,
            "raw_means": means.copy(),
            "shrink_weights": np.zeros(g),
        }

    # Moment-of-moments estimate: tau2 = Var(means) - mean(variances)
    between_var = float(np.var(means))          # empirical between-group variance
    within_mean = float(np.mean(variances))     # mean sampling variance
    tau2 = max(0.0, between_var - within_mean)

    # Shrinkage weight for each group
    denom = tau2 + variances
    # Guard div-by-zero (should not occur since variances >= 0, tau2 >= 0)
    safe_denom = np.where(denom > 0, denom, 1.0)
    weights = np.where(denom > 0, tau2 / safe_denom, 0.0)
    weights = np.clip(weights, 0.0, 1.0)

    shrunk = global_mean * weights + means * (1.0 - weights)

    return {
        "global_mean": global_mean,
        "tau2": tau2,
        "shrunk_means": shrunk,
        "raw_means": means.copy(),
        "shrink_weights": weights,
    }


def shrinkage_mse_gain(
    true_rates: np.ndarray,
    k: np.ndarray,
    n: np.ndarray,
) -> dict:
    """Compare MSE of raw vs EB-shrunk estimates against the true rates.

    Parameters
    ----------
    true_rates : ground-truth per-group rates
    k          : observed successes
    n          : observed trials

    Returns
    -------
    dict with keys:
        mse_raw     – MSE of k/n vs true_rates
        mse_shrunk  – MSE of EB shrunk_rates vs true_rates
        gain        – mse_raw - mse_shrunk  (positive = EB helped)

    Notes
    -----
    Honest: on data actually drawn from a shared prior, EB reduces MSE.
    If groups are truly heterogeneous with large n, gain ≈ 0 (also honest).
    A prior is not an edge.
    """
    true_rates = np.asarray(true_rates, dtype=float)
    k = np.asarray(k, dtype=float)
    n = np.asarray(n, dtype=float)

    result = eb_beta_binomial(k, n)
    raw = result["raw_rates"]
    shrunk = result["shrunk_rates"]

    mse_raw = float(np.mean((raw - true_rates) ** 2))
    mse_shrunk = float(np.mean((shrunk - true_rates) ** 2))
    gain = mse_raw - mse_shrunk

    return {
        "mse_raw": mse_raw,
        "mse_shrunk": mse_shrunk,
        "gain": gain,
    }


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------

def _run_demo(seed: int = 42) -> None:
    """Synthetic demo: draw G=40 groups' true rates from Beta(8,12), then
    draw k~Binomial(n_g, true_rate) with small n_g (5–30).  Compare raw
    vs EB-shrunk MSE across several sample-size regimes."""
    rng = np.random.default_rng(seed)

    G = 40
    alpha_true, beta_true = 8.0, 12.0
    true_rates = rng.beta(alpha_true, beta_true, size=G)

    # Three sample-size regimes
    regimes = {
        "tiny  (n=5-10)":  rng.integers(5,  11, size=G),
        "small (n=10-30)": rng.integers(10, 31, size=G),
        "large (n=50-200)": rng.integers(50, 201, size=G),
    }

    header = f"{'Regime':<22}  {'MSE raw':>12}  {'MSE shrunk':>12}  {'Gain':>12}  {'EB wins?':>8}"
    print()
    print("=" * len(header))
    print("  Empirical Bayes Beta-Binomial: raw vs shrunk MSE")
    print(f"  Prior: Beta({alpha_true:.0f},{beta_true:.0f}), G={G} groups, seed={seed}")
    print("  A PRIOR IS NOT AN EDGE — shrinkage improves estimates, not market beat")
    print("=" * len(header))
    print(header)
    print("-" * len(header))

    for label, n_g in regimes.items():
        k_g = rng.binomial(n_g, true_rates)
        res = shrinkage_mse_gain(true_rates, k_g, n_g)
        wins = "YES" if res["gain"] > 0 else "no"
        print(
            f"  {label:<22}  {res['mse_raw']:>12.6f}  {res['mse_shrunk']:>12.6f}"
            f"  {res['gain']:>+12.6f}  {wins:>8}"
        )

    print("-" * len(header))
    print()

    # Also show a small table of group-level detail for the tiny regime
    n_g = rng.integers(5, 11, size=10)
    k_g = rng.binomial(n_g, true_rates[:10])
    res = eb_beta_binomial(k_g, n_g)

    print(f"  Group-level detail — first 10 groups (tiny regime, seed={seed}):")
    print(f"  Prior: a={res['a']:.3f}  b={res['b']:.3f}  "
          f"pooled_mean={res['pooled_mean']:.3f}  kappa={res['kappa']:.1f}")
    print()
    print(f"  {'Group':>5}  {'n':>4}  {'k':>4}  {'true_rate':>10}  "
          f"{'raw_rate':>10}  {'shrunk':>10}  {'|raw-pool|':>11}  {'|shr-pool|':>11}")
    pm = res["pooled_mean"]
    for i in range(10):
        raw_r = res["raw_rates"][i]
        shr_r = res["shrunk_rates"][i]
        print(
            f"  {i+1:>5}  {int(n_g[i]):>4}  {int(k_g[i]):>4}  "
            f"{true_rates[i]:>10.4f}  {raw_r:>10.4f}  {shr_r:>10.4f}"
            f"  {abs(raw_r-pm):>11.4f}  {abs(shr_r-pm):>11.4f}"
        )
    print()


if __name__ == "__main__":
    _run_demo()
