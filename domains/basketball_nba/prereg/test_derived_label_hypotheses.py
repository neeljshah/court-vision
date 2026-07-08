"""Per-file test for domains.basketball_nba.prereg.derived_label_hypotheses --
run with: python -m pytest domains/basketball_nba/prereg/test_derived_label_hypotheses.py -q
(never bare pytest -- see bash-cwd-prefix rule)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.basketball_nba.prereg.derived_label_hypotheses import METHOD, run
from domains.basketball_nba.prereg.stats_common import NULL, SURVIVES, alpha_fwer, fit_interaction, verdict


def test_planted_interaction_survives_the_k2_bar():
    """Sanity check on THIS module's bar (K=2, not K=3 like nba_hypotheses.py):
    a real, strong interaction must clear alpha_fwer(2)."""
    rng = np.random.default_rng(7)
    n = 4000
    a = rng.normal(size=n)
    b = rng.integers(0, 2, size=n).astype(float)
    logit_p = -0.2 + 0.15 * a + 0.1 * b + 2.5 * a * b
    p = 1.0 / (1.0 + np.exp(-logit_p))
    y = rng.binomial(1, p)
    df = pd.DataFrame({"y": y, "a": a, "b": b})
    fit = fit_interaction(df, "y ~ a * b", kind="logit")
    assert verdict(fit["p"], alpha_fwer(k=2)) == SURVIVES


def test_pure_noise_interaction_is_null_at_k2_bar():
    rng = np.random.default_rng(8)
    n = 4000
    a = rng.normal(size=n)
    b = rng.integers(0, 2, size=n).astype(float)
    y = rng.binomial(1, 0.5, size=n)
    df = pd.DataFrame({"y": y, "a": a, "b": b})
    fit = fit_interaction(df, "y ~ a * b", kind="logit")
    assert verdict(fit["p"], alpha_fwer(k=2)) == NULL


def test_run_produces_two_derived_label_rows_with_proxy_quality_caveats():
    rows, k = run()
    assert k == 2
    assert len(rows) == 2
    names = {r["hypothesis"] for r in rows}
    assert names == {"spacing x late-clock (<=7s) efficiency", "lineup spacing x transition frequency"}
    for r in rows:
        assert r["method"] == METHOD
        assert r["edge_claimed"] is False
        assert "agreement" in r["note"] or "precision" in r["note"]  # proxy-quality numbers present
        assert r["n"] > 1000  # ran on the real corpus, not a stub


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
