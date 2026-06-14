"""tests/platform/test_calibrator_zoo.py — Synthetic tests for calibrator_zoo.

All tests use pure numpy; NO pandas, NO real corpus files.
Covers:
  (1) Perfectly-calibrated series: identity competitive; recalibration does not hurt much.
  (2) Overconfident series: at least one calibrator beats identity; identity NOT chosen.
  (3) Truncation-invariance leak test: first k outputs on full series == outputs on [:k].
  (4) All methods return (N,) finite arrays in [0, 1].
  (5) select_calibrator(methods=["identity","temperature"]) honours subset (2-row table).

CALIBRATION != EDGE.  No edge claims.
"""
from __future__ import annotations

import numpy as np
import pytest

from scripts.platformkit.calibrator_zoo import (
    walk_forward_temperature,
    walk_forward_beta,
    select_calibrator,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

N_LARGE = 600
MIN_H = 50
SEED_PERFECT = 7
SEED_OVERCONF = 99


def _make_perfect(n: int = N_LARGE, seed: int = SEED_PERFECT):
    """Perfectly-calibrated: y ~ Bernoulli(p), p ~ Uniform(0.05, 0.95)."""
    rng = np.random.default_rng(seed)
    p = rng.uniform(0.05, 0.95, n)
    y = rng.binomial(1, p).astype(float)
    return p, y


def _make_overconfident(n: int = N_LARGE, seed: int = SEED_OVERCONF, stretch: float = 2.5):
    """Overconfident: true_p moderate, raw probs pushed toward 0/1."""
    rng = np.random.default_rng(seed)
    true_p = rng.uniform(0.3, 0.7, n)
    raw = np.where(true_p >= 0.5,
                   0.5 + (true_p - 0.5) * stretch,
                   0.5 - (0.5 - true_p) * stretch)
    raw = np.clip(raw, 0.01, 0.99)
    y = rng.binomial(1, true_p).astype(float)
    return raw, y


# ---------------------------------------------------------------------------
# (1) Perfectly-calibrated: identity competitive
# ---------------------------------------------------------------------------


def test_perfectly_calibrated_identity_competitive():
    """Identity's OOS log-loss close to chosen method's — recalibration should not hurt much."""
    raw, y = _make_perfect()
    result = select_calibrator(raw, y, min_history=MIN_H)

    # Find identity log-loss from the table
    table = {row["method"]: row["logloss"] for row in result["table"]}
    chosen_ll = table[result["chosen_method"]]
    identity_ll = table["identity"]

    # Chosen must not be worse than identity (it shouldn't be, by construction)
    assert chosen_ll <= identity_ll + 1e-8, (
        f"Chosen method worse than identity: {chosen_ll:.5f} > {identity_ll:.5f}"
    )
    # On a perfectly-calibrated series identity should be within 5% of chosen log-loss.
    # This is a soft bound — if the series happens to have slight miscalibration
    # due to finite sample noise, another method may improve slightly.
    eps = 0.05 * max(identity_ll, 1e-6)
    assert chosen_ll >= identity_ll - eps, (
        f"Calibrator improves over identity by suspiciously large margin "
        f"on a perfectly-calibrated series: identity={identity_ll:.5f} chosen={chosen_ll:.5f}"
    )


# ---------------------------------------------------------------------------
# (2) Overconfident series: a calibrator beats identity and is chosen
# ---------------------------------------------------------------------------


def test_overconfident_calibrator_beats_identity():
    """On overconfident probs, at least one calibrator lowers OOS log-loss; identity not chosen."""
    raw, y = _make_overconfident()
    result = select_calibrator(raw, y, min_history=MIN_H)

    table = {row["method"]: row["logloss"] for row in result["table"]}
    identity_ll = table["identity"]

    # At least one non-identity method must be strictly better
    non_identity = [m for m in table if m != "identity"]
    any_better = any(table[m] < identity_ll for m in non_identity)
    assert any_better, (
        f"No calibrator improved on identity ({identity_ll:.5f}) for overconfident series. "
        f"Table: {table}"
    )

    # Chosen method must NOT be identity
    assert result["chosen_method"] != "identity", (
        f"select_calibrator chose 'identity' on an overconfident series "
        f"(identity_ll={identity_ll:.5f}, chosen_ll={table[result['chosen_method']]:.5f})"
    )


# ---------------------------------------------------------------------------
# (3) Truncation-invariance (leak test) for temperature and beta
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fn_name,fn", [
    ("walk_forward_temperature", walk_forward_temperature),
    ("walk_forward_beta", walk_forward_beta),
])
def test_truncation_invariance(fn_name, fn):
    """First k outputs on full series == outputs on series[:k] — proves no look-ahead."""
    rng = np.random.default_rng(123)
    N = 250
    raw = rng.uniform(0.1, 0.9, N)
    y = rng.binomial(1, raw).astype(float)

    full = fn(raw, y, min_history=MIN_H, refit_every=1)

    for k in [MIN_H, MIN_H + 1, MIN_H + 20, N - 1]:
        truncated = fn(raw[:k], y[:k], min_history=MIN_H, refit_every=1)
        np.testing.assert_allclose(
            full[:k], truncated,
            rtol=1e-10, atol=1e-12,
            err_msg=(
                f"{fn_name}: outputs differ at truncation k={k}. "
                f"Difference implies look-ahead (LEAK). "
                f"Max abs diff: {np.max(np.abs(full[:k] - truncated)):.2e}"
            ),
        )


# ---------------------------------------------------------------------------
# (4) All methods return (N,) finite arrays in [0, 1]
# ---------------------------------------------------------------------------


def test_all_methods_shape_finite_bounded():
    """Every method: len=N, finite, all in [0, 1]."""
    raw, y = _make_overconfident(n=N_LARGE)
    result = select_calibrator(raw, y, min_history=MIN_H)

    for row in result["table"]:
        method = row["method"]

    # Run each method individually
    for fn, name in [
        (walk_forward_temperature, "temperature"),
        (walk_forward_beta, "beta"),
    ]:
        out = fn(raw, y, min_history=MIN_H)
        assert out.shape == (N_LARGE,), f"{name}: shape mismatch {out.shape}"
        assert np.all(np.isfinite(out)), f"{name}: contains non-finite values"
        assert np.all(out >= 0.0) and np.all(out <= 1.0), \
            f"{name}: values outside [0, 1]"

    # Also check chosen_probs from selector
    cp = result["chosen_probs"]
    assert cp.shape == (N_LARGE,), f"chosen_probs: shape mismatch {cp.shape}"
    assert np.all(np.isfinite(cp)), "chosen_probs: contains non-finite values"
    assert np.all(cp >= 0.0) and np.all(cp <= 1.0), "chosen_probs outside [0, 1]"


# ---------------------------------------------------------------------------
# (5) methods subset respected: 2-row table
# ---------------------------------------------------------------------------


def test_methods_subset_honoured():
    """select_calibrator(methods=['identity','temperature']) returns exactly 2 rows."""
    raw, y = _make_overconfident(n=300)
    result = select_calibrator(raw, y, min_history=MIN_H,
                               methods=["identity", "temperature"])

    assert len(result["table"]) == 2, (
        f"Expected 2-row table; got {len(result['table'])} rows"
    )
    methods_in_table = {row["method"] for row in result["table"]}
    assert methods_in_table == {"identity", "temperature"}, (
        f"Unexpected methods in table: {methods_in_table}"
    )
    assert result["chosen_method"] in {"identity", "temperature"}, (
        f"chosen_method not in subset: {result['chosen_method']}"
    )


# ---------------------------------------------------------------------------
# (6) Edge-case: min_history > series length
# ---------------------------------------------------------------------------


def test_short_series_passthrough():
    """When series shorter than min_history, all outputs are raw passthrough."""
    rng = np.random.default_rng(0)
    raw = rng.uniform(0.2, 0.8, 30)
    y = rng.binomial(1, 0.5, 30).astype(float)

    out_t = walk_forward_temperature(raw, y, min_history=100)
    out_b = walk_forward_beta(raw, y, min_history=100)

    np.testing.assert_allclose(out_t, np.clip(raw, 0, 1), atol=1e-12,
                                err_msg="temperature: short series not passed through raw")
    np.testing.assert_allclose(out_b, np.clip(raw, 0, 1), atol=1e-12,
                                err_msg="beta: short series not passed through raw")


# ---------------------------------------------------------------------------
# (7) Note key present in select_calibrator output
# ---------------------------------------------------------------------------


def test_calibration_note_present():
    """Result must contain the honesty note (CALIBRATION != EDGE)."""
    raw, y = _make_overconfident(n=200)
    result = select_calibrator(raw, y, min_history=MIN_H)
    assert "note" in result
    assert "CALIBRATION != EDGE" in result["note"]


# ---------------------------------------------------------------------------
# (8) market_probs optional arg does not break anything
# ---------------------------------------------------------------------------


def test_market_probs_optional():
    """Passing market_probs adds market_logloss column; table still selects correctly."""
    raw, y = _make_overconfident(n=300)
    market = np.clip(raw + np.random.default_rng(5).normal(0, 0.05, 300), 0.01, 0.99)
    result = select_calibrator(raw, y, min_history=MIN_H, market_probs=market)

    assert "chosen_method" in result
    for row in result["table"]:
        assert "market_logloss" in row
