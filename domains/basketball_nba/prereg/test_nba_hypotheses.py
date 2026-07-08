"""Per-file test for domains.basketball_nba.prereg -- run with:
python -m pytest domains/basketball_nba/prereg/test_nba_hypotheses.py -q
(never bare pytest -- see bash-cwd-prefix rule)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.basketball_nba.prereg.nba_hypotheses import BLOCKED_REASONS
from domains.basketball_nba.prereg.stats_common import (
    NULL, SURVIVES, alpha_fwer, fit_interaction, fit_single, verdict,
)


def test_blocked_reasons_cover_seven_and_are_named():
    """The 7 hypotheses this census can't test each carry a concrete premise
    reason (never a placeholder), and never overlap the 3 tested ones."""
    assert len(BLOCKED_REASONS) == 7
    for name, reason in BLOCKED_REASONS.items():
        assert len(reason) > 20
    tested = {"lineup_vs_lineup net-rating x rest differential", "stint continuity",
              "spacing x clutch"}
    assert not any(any(t in name for t in tested) for name in BLOCKED_REASONS)


def test_planted_interaction_survives():
    """A REAL interaction (large n, strong true effect) must clear the FWER
    bar -- if this ever goes NULL, fit_interaction/alpha_fwer broke."""
    rng = np.random.default_rng(0)
    n = 4000
    a = rng.normal(size=n)
    b = rng.integers(0, 2, size=n).astype(float)
    logit_p = -0.2 + 0.15 * a + 0.1 * b + 2.5 * a * b  # strong planted interaction
    p = 1.0 / (1.0 + np.exp(-logit_p))
    y = rng.binomial(1, p)
    df = pd.DataFrame({"y": y, "a": a, "b": b})
    fit = fit_interaction(df, "y ~ a * b", kind="logit")
    alpha = alpha_fwer(k=3)
    assert verdict(fit["p"], alpha) == SURVIVES


def test_pure_noise_interaction_is_null():
    """A genuinely null interaction (y independent of a*b) must NOT survive
    the FWER-tightened bar -- guards against a p-hacked false SHIP."""
    rng = np.random.default_rng(1)
    n = 4000
    a = rng.normal(size=n)
    b = rng.integers(0, 2, size=n).astype(float)
    y = rng.binomial(1, 0.5, size=n)  # y has zero relationship to a, b, or a*b
    df = pd.DataFrame({"y": y, "a": a, "b": b})
    fit = fit_interaction(df, "y ~ a * b", kind="logit")
    alpha = alpha_fwer(k=3)
    assert verdict(fit["p"], alpha) == NULL


def test_single_factor_fit_runs():
    rng = np.random.default_rng(2)
    n = 2000
    x = rng.normal(size=n)
    y = rng.binomial(1, 1.0 / (1.0 + np.exp(-(0.3 * x))))
    df = pd.DataFrame({"y": y, "x": x})
    fit = fit_single(df, "y ~ x", kind="logit")
    assert fit["term"] == "x"
    assert fit["n"] == n


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
