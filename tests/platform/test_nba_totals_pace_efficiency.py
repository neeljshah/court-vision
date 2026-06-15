"""Per-file test for scripts/platformkit/proof_nba/totals_pace_efficiency.py.

Records the honest negative: a pace x efficiency decomposition is NOT sharper than the raw
points model (NBA pregame totals are at the structural data ceiling). Structural asserts.

Run: python -m pytest tests/platform/test_nba_totals_pace_efficiency.py -q
"""
from __future__ import annotations

import pytest

from scripts.platformkit.proof_nba import totals_pace_efficiency as mod


def test_run_structure_and_ceiling():
    rep = mod.run()
    assert rep["n_games"] > 500
    for k in ("raw_points_model", "pace_efficiency_model"):
        m = rep[k]
        # both models sit at the ~17-18pt irreducible NBA total sigma (shooting variance)
        assert 15.0 < m["sigma"] < 21.0
        assert 0.0 <= m["ece"] <= 0.2
    # the decomposition does not buy a meaningful sharpness gain (structural ceiling)
    assert abs(rep["sigma_gain"]) < 1.0
    assert isinstance(rep["verdict"], str)
