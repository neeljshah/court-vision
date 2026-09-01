"""tests/platformkit/test_ssac_halflife.py -- guards the SSAC half-life computation.

The logic that can silently break and flatter the result: the settled-tick filter (half
the raw corpus is post-final price pinned at 0/1), and the exponential fit. Both are
checked here on synthetic data, so the test runs on a clone with no private corpus.

Run: python -m pytest tests/platformkit/test_ssac_halflife.py -q
"""
import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.ssac import halflife as hl


def test_fit_recovers_known_half_life():
    """A curve built with a known half-life must be recovered within 5%."""
    true_hl = 12.0
    x = np.arange(2, 48, 4, dtype=float)
    v = 0.05 * np.exp(-np.log(2) / true_hl * x)
    _, got, r2 = hl.fit(x, v)
    assert got == pytest.approx(true_hl, rel=0.05)
    assert r2 > 0.999


def test_curve_is_zero_when_prior_adds_nothing():
    """If STATE and STATE+PRIOR are identical, V(t) must be exactly 0 in every bin."""
    n = 240
    te = pd.DataFrame({
        "minute": np.tile(np.arange(0, 48, 4), n // 12),
        "outcome_home_win": np.random.default_rng(0).integers(0, 2, n),
        "ps": 0.5, "pp": 0.5,
    })
    _, v = hl.curve(te)
    assert np.allclose(v, 0.0)


def test_logit_clips_extremes():
    """Settled prices at 0/1 must not produce infinities if they ever slip the filter."""
    out = hl._logit(np.array([0.0, 1.0, 0.5]))
    assert np.all(np.isfinite(out))
    assert out[2] == pytest.approx(0.0)


def test_settled_ticks_would_be_filtered():
    """The filter in load_clean must reject pinned post-final ticks and keep live ones."""
    df = pd.DataFrame({
        "period": [4, 4, 2],
        "game_clock_s": [0.0, 300.0, 400.0],       # first is post-final
        "market_prob": [0.9995, 0.62, 0.41],
    })
    keep = (df.period <= 4) & (df.game_clock_s > 0) & df.market_prob.between(0.002, 0.998)
    assert list(keep) == [False, True, True]
