"""
Tests for scripts.platformkit.hier_priors — Empirical Bayes hierarchical pooled priors.

All tests use pure numpy synthetic data; no pandas/scipy/sklearn.
Run:
    C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe \
        -m pytest tests/platform/test_hier_priors.py -q
"""

from __future__ import annotations

import numpy as np
import pytest

from scripts.platformkit.hier_priors import (
    eb_beta_binomial,
    eb_normal,
    shrinkage_mse_gain,
)


# ---------------------------------------------------------------------------
# Test 1: EB-WINS on small-n groups drawn from a shared Beta prior
# ---------------------------------------------------------------------------

def test_eb_wins_small_sample():
    """Groups' true rates ~ Beta(8,12); small n_g (5–30).
    EB shrinkage should beat raw per-group rates (gain > 0).
    A PRIOR IS NOT AN EDGE — this only improves MSE on sparse groups."""
    rng = np.random.default_rng(7)

    G = 60
    true_rates = rng.beta(8, 12, size=G)
    n_g = rng.integers(5, 31, size=G)
    k_g = rng.binomial(n_g, true_rates)

    result = shrinkage_mse_gain(true_rates, k_g, n_g)

    assert result["gain"] > 0, (
        f"Expected EB gain > 0 on small-n groups, got gain={result['gain']:.6f} "
        f"(mse_raw={result['mse_raw']:.6f}, mse_shrunk={result['mse_shrunk']:.6f})"
    )


# ---------------------------------------------------------------------------
# Test 2: n=0 group receives exactly the pooled prior mean
# ---------------------------------------------------------------------------

def test_n_zero_group_gets_prior_mean():
    """A group with n==0 must get the pooled prior mean — no div-by-zero."""
    rng = np.random.default_rng(13)

    k = np.array([3.0, 0.0, 5.0, 2.0, 7.0])
    n = np.array([10.0, 0.0, 15.0, 8.0, 20.0])   # second group has n=0

    res = eb_beta_binomial(k, n)

    prior_mean = res["a"] / (res["a"] + res["b"])
    shrunk_zero_group = res["shrunk_rates"][1]

    assert np.isfinite(shrunk_zero_group), "shrunk_rate for n=0 group is not finite"
    assert abs(shrunk_zero_group - prior_mean) < 1e-10, (
        f"n=0 group shrunk_rate {shrunk_zero_group:.6f} != prior_mean {prior_mean:.6f}"
    )


# ---------------------------------------------------------------------------
# Test 3: Shrinkage is monotone in n — small n is pulled closer to pooled mean
# ---------------------------------------------------------------------------

def test_shrinkage_monotone_in_n():
    """A group with small n is pulled CLOSER to the pooled mean than
    a group with large n that has the same raw rate.

    Strategy: use many background groups near p=0.5 to anchor pooled_mean,
    then place two focal groups both with raw_rate=0.80 (far from 0.5) but
    with n_small=5 vs n_large=200.  The small-n focal group should be pulled
    noticeably closer to the pooled mean than the large-n focal group.
    """
    # Background groups: 20 groups with ~50% rate, large n -> anchor pooled_mean near 0.5
    bg_k = np.array([50.0] * 20)
    bg_n = np.array([100.0] * 20)

    # Focal group A (small n): 4/5  = 0.80 raw
    # Focal group B (large n): 160/200 = 0.80 raw
    # Both have identical raw rates but very different n.
    focal_k = np.array([4.0, 160.0])
    focal_n = np.array([5.0, 200.0])

    k = np.concatenate([bg_k, focal_k])
    n = np.concatenate([bg_n, focal_n])

    res = eb_beta_binomial(k, n)
    pm = res["pooled_mean"]

    # focal indices are the last two
    shrunk_small = res["shrunk_rates"][-2]
    shrunk_large = res["shrunk_rates"][-1]
    raw_small = res["raw_rates"][-2]
    raw_large = res["raw_rates"][-1]

    dist_small = abs(shrunk_small - pm)
    dist_large = abs(shrunk_large - pm)

    assert abs(raw_small - raw_large) < 1e-9, "Focal groups must start with the same raw rate"
    assert dist_small < dist_large, (
        f"Expected small-n focal group pulled closer to pooled mean.\n"
        f"  pooled_mean={pm:.4f}\n"
        f"  small-n (n=5):   raw={raw_small:.4f}, shrunk={shrunk_small:.4f}, "
        f"|shrunk-pool|={dist_small:.4f}\n"
        f"  large-n (n=200): raw={raw_large:.4f}, shrunk={shrunk_large:.4f}, "
        f"|shrunk-pool|={dist_large:.4f}"
    )


# ---------------------------------------------------------------------------
# Test 4: eb_normal shrink_weights in [0,1]; high-variance group shrunk more
# ---------------------------------------------------------------------------

def test_eb_normal_properties():
    """shrink_weights in [0,1]; a high-variance group is shrunk MORE toward
    the global mean than a low-variance group; tau2 >= 0."""
    rng = np.random.default_rng(21)

    G = 20
    # True group means from a distribution
    true_mu = rng.normal(50.0, 5.0, size=G)
    # Low-variance groups (tight measurements)
    var_low = 1.0 * np.ones(G // 2)
    # High-variance groups (noisy measurements)
    var_high = 25.0 * np.ones(G - G // 2)

    variances = np.concatenate([var_low, var_high])
    # observed means = true + noise
    noise = rng.normal(0, np.sqrt(variances))
    means = true_mu + noise

    res = eb_normal(means, variances)

    weights = res["shrink_weights"]
    tau2 = res["tau2"]
    gm = res["global_mean"]

    # All weights in [0, 1]
    assert np.all(weights >= 0.0) and np.all(weights <= 1.0), (
        f"shrink_weights out of [0,1]: min={weights.min():.4f} max={weights.max():.4f}"
    )

    # tau2 >= 0
    assert tau2 >= 0.0, f"tau2={tau2} is negative"

    # High-variance groups should have (strictly) larger shrinkage toward global_mean
    # compared to low-variance groups (w_g = tau2/(tau2+var_g), larger var_g => smaller w)
    # => high-var group weight < low-var group weight
    # => high-var group is pulled more: (1 - w_high) > (1 - w_low)  [more raw kept]
    # Actually the DISTANCE to global mean after shrinkage:
    #   |shrunk_g - gm| = (1-w_g)*|mean_g - gm|
    # A high-variance group gets a LOWER weight w_g, so keeps more of its raw mean.
    # What the task says: "high-variance group is shrunk MORE" — this means the
    # shrinkage WEIGHT w_g is higher for high-variance groups... WAIT:
    # w_g = tau2/(tau2+var_g).  Larger var_g => smaller w_g => LESS shrinkage toward global.
    # The standard James-Stein interpretation: shrink MORE when var_g is SMALLER.
    # Let's test the correct direction: low-variance groups have HIGHER weights (more shrinkage).
    mean_w_low = float(np.mean(weights[:G // 2]))
    mean_w_high = float(np.mean(weights[G // 2:]))
    assert mean_w_low > mean_w_high, (
        f"Expected low-variance groups to have higher shrinkage weights "
        f"(tau2/(tau2+var_g) decreases with var_g). "
        f"mean_w_low={mean_w_low:.4f}, mean_w_high={mean_w_high:.4f}, tau2={tau2:.4f}"
    )


# ---------------------------------------------------------------------------
# Test 5: Degenerate inputs — all groups identical / single group
# ---------------------------------------------------------------------------

def test_degenerate_all_identical():
    """All groups have the same raw rate — shrunk should be close to raw, no NaN."""
    k = np.array([3.0, 3.0, 3.0, 3.0, 3.0])
    n = np.array([10.0, 10.0, 10.0, 10.0, 10.0])

    res = eb_beta_binomial(k, n)

    assert np.all(np.isfinite(res["shrunk_rates"])), "NaN/Inf in shrunk_rates for identical groups"
    assert np.all(np.isfinite(res["raw_rates"])), "NaN/Inf in raw_rates for identical groups"

    # Shrunk rates should all be finite and within (0,1)
    assert np.all(res["shrunk_rates"] > 0) and np.all(res["shrunk_rates"] < 1)


def test_degenerate_single_group():
    """Single group — should not crash."""
    k = np.array([7.0])
    n = np.array([20.0])

    res = eb_beta_binomial(k, n)
    assert np.isfinite(res["shrunk_rates"][0])
    assert np.isfinite(res["a"]) and np.isfinite(res["b"])

    # eb_normal single group
    res_n = eb_normal(np.array([0.35]), np.array([0.01]))
    assert np.isfinite(res_n["shrunk_means"][0])
    assert res_n["tau2"] == 0.0


def test_degenerate_eb_normal_all_identical():
    """All group means identical — no NaN, tau2=0."""
    means = np.array([0.3, 0.3, 0.3, 0.3])
    variances = np.array([0.05, 0.05, 0.05, 0.05])

    res = eb_normal(means, variances)
    assert np.all(np.isfinite(res["shrunk_means"]))
    assert res["tau2"] == 0.0
    assert np.allclose(res["shrunk_means"], res["raw_means"])
