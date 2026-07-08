"""Per-file test for replicate_h7_2024_25 -- pure verdict_row logic only (no
disk/network): asserts the REPLICATED/FAILED_REPLICATION branch requires
BOTH same effect sign as the original AND p < alpha.

Run: python -m pytest domains/basketball_nba/prereg/test_replicate_h7_2024_25.py -q
"""
from __future__ import annotations

from domains.basketball_nba.prereg.replicate_h7_2024_25 import verdict_row


def _fit(effect: float, p: float) -> dict:
    return {"effect": effect, "p": p, "n": 1000, "term": "continuity_s"}


def test_same_sign_and_significant_replicates():
    row = verdict_row(_fit(effect=0.0005, p=1e-10))
    assert row["verdict"] == "REPLICATED"
    assert row["method"] == "replication_2024_25"
    assert row["edge_claimed"] is False


def test_wrong_sign_fails_replication_even_if_significant():
    row = verdict_row(_fit(effect=-0.0005, p=1e-10))
    assert row["verdict"] == "FAILED_REPLICATION"


def test_not_significant_fails_replication_even_same_sign():
    row = verdict_row(_fit(effect=0.0005, p=0.2))
    assert row["verdict"] == "FAILED_REPLICATION"
