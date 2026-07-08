"""Per-file test for replicate_spacing_lateclock_2023_24 -- pure _verdict_row
logic only (no disk/network): REPLICATED requires BOTH same effect sign as the
2025-26 hit (+1) AND p < the declared K=1 alpha (0.05); n=0 -> NOT_TESTABLE.

Run: python -m pytest domains/basketball_nba/prereg/test_replicate_spacing_lateclock_2023_24.py -q
"""
from __future__ import annotations

from domains.basketball_nba.prereg.replicate_spacing_lateclock_2023_24 import ALPHA, _verdict_row


def _fit(effect: float, p: float, n: int = 50000) -> dict:
    return {"effect": effect, "p": p, "n": n, "term": "spacing_mean_dist:is_late_clock"}


def test_alpha_is_point_zero_five():
    assert ALPHA == 0.05


def test_same_sign_and_significant_replicates():
    row = _verdict_row(_fit(effect=0.005, p=1e-4))
    assert row["verdict"] == "REPLICATED"
    assert row["method"] == "replication_spacing_lateclock_2023_24"
    assert row["alpha_fwer"] == ALPHA
    assert row["edge_claimed"] is False


def test_wrong_sign_fails_even_if_significant():
    row = _verdict_row(_fit(effect=-0.005, p=1e-4))
    assert row["verdict"] == "FAILED_REPLICATION"


def test_not_significant_fails_even_same_sign():
    row = _verdict_row(_fit(effect=0.005, p=0.5))
    assert row["verdict"] == "FAILED_REPLICATION"


def test_n_zero_is_not_testable_not_failed():
    row = _verdict_row(_fit(effect=0.005, p=1e-4, n=0))
    assert row["verdict"] == "NOT_TESTABLE"


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
