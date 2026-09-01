"""Golden-number tests for scripts.platformkit.eval_gate.deflated_metrics."""
from __future__ import annotations

import math

import pytest

from scripts.platformkit.eval_gate.deflated_metrics import (
    deflated_p,
    expected_max_z,
    min_detectable_brier_edge,
)


def test_expected_max_z_k1_is_zero():
    # E[max of 1 draw] = E[Z] = 0 by symmetry of the standard normal.
    assert expected_max_z(1) == 0.0


def test_expected_max_z_k2_matches_closed_form():
    # Textbook closed form for the max of 2 iid standard normals: 1/sqrt(pi).
    assert expected_max_z(2) == pytest.approx(1.0 / math.sqrt(math.pi), abs=1e-8)


def test_expected_max_z_k10_matches_independent_reference():
    # Reference value from the same E[max]=integral(x*f(x)) integral, computed
    # independently at authoring time (scipy.integrate.quad, err ~1.9e-10).
    assert expected_max_z(10) == pytest.approx(1.538752730835173, abs=1e-6)


def test_expected_max_z_increasing_in_k():
    assert expected_max_z(2) < expected_max_z(5) < expected_max_z(50)


def test_expected_max_z_rejects_k_below_one():
    with pytest.raises(ValueError):
        expected_max_z(0)


def test_deflated_p_golden_values():
    assert deflated_p(0.01, 5) == pytest.approx(0.05)
    assert deflated_p(0.5, 10) == 1.0  # capped, not 5.0
    assert deflated_p(0.3, 1) == pytest.approx(0.3)  # k=1 is a no-op


def test_deflated_p_never_exceeds_one():
    assert deflated_p(1.0, 1000) == 1.0


def test_deflated_p_rejects_out_of_range_p():
    with pytest.raises(ValueError):
        deflated_p(1.5, 1)


def test_min_detectable_brier_edge_golden_n100_k1():
    # z = NormalDist().inv_cdf(0.975) = 1.9599639845400536
    assert min_detectable_brier_edge(100, 1, alpha=0.05) == pytest.approx(
        0.19599639845400535, abs=1e-12
    )


def test_min_detectable_brier_edge_golden_n400_k5():
    # z = NormalDist().inv_cdf(1 - 0.05/10) = 2.5758293035489
    assert min_detectable_brier_edge(400, 5, alpha=0.05) == pytest.approx(
        0.128791465177445, abs=1e-9
    )


def test_min_detectable_brier_edge_shrinks_with_more_games():
    assert min_detectable_brier_edge(400, 1, alpha=0.05) < min_detectable_brier_edge(
        100, 1, alpha=0.05
    )


def test_min_detectable_brier_edge_grows_with_more_trials():
    assert min_detectable_brier_edge(100, 10, alpha=0.05) > min_detectable_brier_edge(
        100, 1, alpha=0.05
    )


def test_min_detectable_brier_edge_rejects_bad_n():
    with pytest.raises(ValueError):
        min_detectable_brier_edge(0, 1)


# --- adversarial review 2026-09-01: k=1 identity, fail-open k, power term ---


def test_k_equals_one_is_the_raw_undeflated_case_everywhere():
    # The k=1 contract for all three: deflation must be an exact no-op.
    assert expected_max_z(1) == 0.0
    assert deflated_p(0.037, 1) == 0.037
    raw_z = 1.9599639845400536  # inv_cdf(1 - 0.05/2), the undeflated two-sided bar
    assert min_detectable_brier_edge(100, 1, alpha=0.05) == pytest.approx(
        raw_z / 10.0, abs=1e-12
    )


@pytest.mark.parametrize("bad_k", [0, -1])
def test_k_below_one_raises_instead_of_silently_undeflating(bad_k):
    # Was: k = max(1, int(k)) -- an empty trial ledger silently returned an
    # UNDEFLATED p-value / MDE, failing open toward false discoveries.
    with pytest.raises(ValueError):
        deflated_p(0.01, bad_k)
    with pytest.raises(ValueError):
        min_detectable_brier_edge(100, bad_k)
    with pytest.raises(ValueError):
        expected_max_z(bad_k)


def test_power_term_default_is_the_bare_critical_value():
    # power=0.5 -> z_power = 0 -> the formula reduces to the critical value, so
    # the pre-existing golden numbers are unchanged by adding the power term.
    assert min_detectable_brier_edge(100, 1, alpha=0.05, power=0.5) == pytest.approx(
        min_detectable_brier_edge(100, 1, alpha=0.05), abs=1e-12
    )


def test_power_80_requires_a_larger_effect_than_the_critical_value():
    # The anti-conservative direction the docstring used to omit: at 80% power
    # the detectable effect is LARGER, not smaller. (1.9599639845400536 +
    # 0.8416212335729143) / 10 = 0.2801585218112968.
    assert min_detectable_brier_edge(100, 1, alpha=0.05, power=0.8) == pytest.approx(
        0.2801585218112968, abs=1e-12
    )
    assert min_detectable_brier_edge(100, 1, alpha=0.05, power=0.8) > (
        min_detectable_brier_edge(100, 1, alpha=0.05)
    )


def test_power_out_of_range_rejected():
    for bad in (0.0, 1.0, -0.1, 1.5):
        with pytest.raises(ValueError):
            min_detectable_brier_edge(100, 1, power=bad)


def test_expected_max_z_quad_matches_independent_quantile_space_integral():
    # The quad(-inf, inf) integrand is sharply peaked for large k, the classic
    # way adaptive quadrature silently returns garbage. Cross-check against a
    # different formulation on a FINITE interval: E[max] = int_0^1 Phi^-1(u^(1/k)) du.
    from scipy import integrate
    from statistics import NormalDist

    nd = NormalDist()
    for k in (2, 50, 1000, 100000):
        ref, _err = integrate.quad(lambda u: nd.inv_cdf(u ** (1.0 / k)), 0.0, 1.0, limit=400)
        assert expected_max_z(k) == pytest.approx(ref, abs=1e-6)
