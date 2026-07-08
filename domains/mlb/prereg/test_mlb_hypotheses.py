"""Per-file test for domains.mlb.prereg -- run with:
python -m pytest domains/mlb/prereg/test_mlb_hypotheses.py -q
(never bare pytest -- see bash-cwd-prefix rule)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.mlb.prereg.mlb_hypotheses import BLOCKED_REASONS
from domains.mlb.prereg.stats_common import NULL, SURVIVES, alpha_fwer, fit_interaction, verdict


def test_blocked_reasons_cover_five_and_are_named():
    assert len(BLOCKED_REASONS) == 5
    for name, reason in BLOCKED_REASONS.items():
        assert len(reason) > 20


def test_planted_interaction_survives():
    """A REAL interaction (large n, strong true effect) must clear the FWER
    bar -- if this ever goes NULL, fit_interaction/alpha_fwer broke."""
    rng = np.random.default_rng(10)
    n = 4000
    a = rng.integers(0, 2, size=n).astype(float)
    b = rng.integers(0, 2, size=n).astype(float)
    logit_p = -0.1 + 0.1 * a + 0.1 * b + 2.0 * a * b
    p = 1.0 / (1.0 + np.exp(-logit_p))
    y = rng.binomial(1, p)
    df = pd.DataFrame({"y": y, "a": a, "b": b})
    fit = fit_interaction(df, "y ~ a * b", kind="logit")
    alpha = alpha_fwer(k=5)
    assert verdict(fit["p"], alpha) == SURVIVES


def test_pure_noise_interaction_is_null():
    """A genuinely null interaction must NOT survive the FWER-tightened bar."""
    rng = np.random.default_rng(11)
    n = 4000
    a = rng.integers(0, 2, size=n).astype(float)
    b = rng.integers(0, 2, size=n).astype(float)
    y = rng.binomial(1, 0.5, size=n)
    df = pd.DataFrame({"y": y, "a": a, "b": b})
    fit = fit_interaction(df, "y ~ a * b", kind="logit")
    alpha = alpha_fwer(k=5)
    assert verdict(fit["p"], alpha) == NULL


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
