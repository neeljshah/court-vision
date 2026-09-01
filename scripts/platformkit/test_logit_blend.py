"""scripts/platformkit/test_logit_blend.py -- per-file tests for logit_blend.py.

Acceptance tests:
  (1) identical components -> blend returns that probability unchanged
  (2) correlated (hedged) components -> fitted extremize > 1 AND lower Brier
      than the plain log-odds mean
  (3) the cap is HARD -- heavily hedged components want > cap, get exactly cap
  (4) guard_vs_market clamps a runaway blend back to the market band edge

Run:
  cd /c/Users/neelj/nba-ai-system && \
    python -m pytest scripts/platformkit/test_logit_blend.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from scripts.platformkit.logit_blend import (
    blend,
    fit_extremize,
    from_logit,
    guard_vs_market,
    to_logit,
)


def _hedged_corpus(shrink: float, n: int = 4000, seed: int = 7):
    """Three correlated components that each hedge toward 0.5 by `shrink`.

    True log-odds z_true drives the outcome; every component reports
    shrink * z_true plus small idiosyncratic noise, so the log-odds mean is
    under-confident by roughly 1 / shrink.
    """
    rng = np.random.default_rng(seed)
    z_true = rng.normal(0.0, 1.6, size=n)
    y = (rng.random(n) < from_logit(z_true)).astype(float)
    comps = {
        "a": from_logit(shrink * z_true + rng.normal(0.0, 0.15, size=n)),
        "b": from_logit(shrink * z_true + rng.normal(0.0, 0.15, size=n)),
        "c": from_logit(shrink * z_true + rng.normal(0.0, 0.15, size=n)),
    }
    return comps, y


def _brier(p, y) -> float:
    return float(np.mean((np.asarray(p) - np.asarray(y)) ** 2))


# ---------------------------------------------------------------------------
# (1) identical components are a no-op
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("p", [0.02, 0.2, 0.5, 0.73, 0.99])
def test_identical_components_return_input(p: float) -> None:
    assert blend({"a": p, "b": p, "c": p}) == pytest.approx(p, abs=1e-9)


def test_identical_components_ignore_weights() -> None:
    assert blend({"a": 0.3, "b": 0.3}, weights={"a": 0.9, "b": 0.1}) == pytest.approx(0.3, abs=1e-9)


def test_logit_roundtrip_and_clipping() -> None:
    assert from_logit(to_logit(0.42)) == pytest.approx(0.42, abs=1e-9)
    assert np.isfinite(to_logit(0.0)) and np.isfinite(to_logit(1.0))
    assert 0.0 < from_logit(-1e6) < from_logit(1e6) < 1.0


def test_blend_is_monotone_in_extremize() -> None:
    p = blend({"a": 0.7, "b": 0.8})
    assert blend({"a": 0.7, "b": 0.8}, extremize=1.4) > p
    assert blend({"a": 0.7, "b": 0.8}, extremize=0.6) < p


# ---------------------------------------------------------------------------
# (2) correlated components -> fitted exponent > 1 and better Brier
# ---------------------------------------------------------------------------

def test_fitted_extremize_beats_plain_mean() -> None:
    comps, y = _hedged_corpus(shrink=0.70)
    a = fit_extremize(comps, y, cap=1.6)
    assert 1.0 < a < 1.6, a
    plain = blend(comps, extremize=1.0)
    sharp = blend(comps, extremize=a)
    assert _brier(sharp, y) < _brier(plain, y)


def test_fitted_extremize_generalises_to_a_holdout() -> None:
    comps, y = _hedged_corpus(shrink=0.70, seed=11)
    fit = {k: v[:2000] for k, v in comps.items()}
    hold = {k: v[2000:] for k, v in comps.items()}
    a = fit_extremize(fit, y[:2000], cap=1.6)
    assert _brier(blend(hold, extremize=a), y[2000:]) < _brier(
        blend(hold, extremize=1.0), y[2000:]
    )


def test_wellcalibrated_components_stay_near_one() -> None:
    comps, y = _hedged_corpus(shrink=1.0, seed=3)
    assert fit_extremize(comps, y, cap=1.6) == pytest.approx(1.0, abs=0.12)


# ---------------------------------------------------------------------------
# (3) the cap is hard
# ---------------------------------------------------------------------------

def test_cap_is_respected_when_fit_wants_more() -> None:
    comps, y = _hedged_corpus(shrink=0.35)   # optimum ~2.9, far above any cap
    assert fit_extremize(comps, y, cap=1.6) == pytest.approx(1.6, abs=1e-9)
    assert fit_extremize(comps, y, cap=1.2) == pytest.approx(1.2, abs=1e-9)
    assert fit_extremize(comps, y, cap=1.0) == pytest.approx(1.0, abs=1e-9)


def test_thin_fit_set_refuses_to_fit() -> None:
    comps, y = _hedged_corpus(shrink=0.35, n=10)
    assert fit_extremize(comps, y) == 1.0


def test_bad_cap_rejected() -> None:
    comps, y = _hedged_corpus(shrink=0.7, n=50)
    with pytest.raises(ValueError):
        fit_extremize(comps, y, cap=0.9)


# ---------------------------------------------------------------------------
# (4) the market guard
# ---------------------------------------------------------------------------

def test_guard_clamps_runaway_blend() -> None:
    runaway = blend({"a": 0.93, "b": 0.95, "c": 0.94}, extremize=1.6)
    assert runaway > 0.70
    assert guard_vs_market(runaway, 0.55) == pytest.approx(0.70, abs=1e-9)
    assert guard_vs_market(0.05, 0.55) == pytest.approx(0.40, abs=1e-9)


def test_guard_passes_through_inside_the_band() -> None:
    assert guard_vs_market(0.61, 0.55) == pytest.approx(0.61, abs=1e-12)
    assert guard_vs_market(0.90, 0.55, max_abs_deviation=0.5) == pytest.approx(0.90, abs=1e-12)


def test_guard_never_leaves_the_unit_interval() -> None:
    out = guard_vs_market(np.array([0.99, 0.01]), np.array([0.98, 0.02]), 0.15)
    assert np.all((out > 0.0) & (out < 1.0))
    assert guard_vs_market(0.99, 1.0) == pytest.approx(0.99, abs=1e-9)


def test_guard_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError):
        guard_vs_market(0.6, 1.4)
    with pytest.raises(ValueError):
        guard_vs_market(0.6, 0.5, max_abs_deviation=-0.1)


# ---------------------------------------------------------------------------
# input shapes / validation
# ---------------------------------------------------------------------------

def test_series_and_row_shapes_agree() -> None:
    cols = {"a": [0.6, 0.7], "b": [0.4, 0.55]}
    rows = [{"a": 0.6, "b": 0.4}, {"a": 0.7, "b": 0.55}]
    assert np.allclose(blend(cols), blend(rows))
    assert np.allclose(blend(cols), [[blend({"a": 0.6, "b": 0.4}), blend({"a": 0.7, "b": 0.55})]])


def test_weights_shift_the_pool_and_bad_weights_raise() -> None:
    comp = {"a": 0.9, "b": 0.3}
    assert blend(comp, weights=[3.0, 1.0]) > blend(comp)
    with pytest.raises(ValueError):
        blend(comp, weights=[1.0, -1.0])
    with pytest.raises(ValueError):
        blend(comp, weights=[1.0])
    with pytest.raises(ValueError):
        blend({})
    with pytest.raises(ValueError):
        blend({"a": 1.4, "b": 0.3})
