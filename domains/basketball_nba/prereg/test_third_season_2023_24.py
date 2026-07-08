"""Per-file test for third_season_2023_24 -- pure _verdict_row logic only (no
disk/network): REPLICATED requires BOTH same effect sign as the prior hit AND
p < the declared K=4 Bonferroni alpha (0.0125).

Run: python -m pytest domains/basketball_nba/prereg/test_third_season_2023_24.py -q
"""
from __future__ import annotations

from domains.basketball_nba.prereg.third_season_2023_24 import ALPHA, _verdict_row

_NAME = "endQ1 x floor_quality_now"  # _ORIGINAL_SIGN[_NAME] == +1


def _fit(effect: float, p: float) -> dict:
    return {"effect": effect, "p": p, "n": 500, "term": "floor_quality_now"}


def test_alpha_is_bonferroni_k4():
    assert abs(ALPHA - 0.0125) < 1e-12


def test_same_sign_and_significant_replicates():
    row = _verdict_row(_NAME, "nba", "team_asof_ingame", _fit(effect=0.001, p=1e-6))
    assert row["verdict"] == "REPLICATED"
    assert row["method"] == "third_season_2023_24"
    assert row["alpha_fwer"] == ALPHA
    assert row["edge_claimed"] is False


def test_wrong_sign_fails_even_if_significant():
    row = _verdict_row(_NAME, "nba", "team_asof_ingame", _fit(effect=-0.001, p=1e-6))
    assert row["verdict"] == "FAILED_REPLICATION"


def test_significant_but_above_bonferroni_bar_fails():
    """p=0.02 would clear a plain 0.05 bar but not the K=4 Bonferroni 0.0125 one."""
    row = _verdict_row(_NAME, "nba", "team_asof_ingame", _fit(effect=0.001, p=0.02))
    assert row["verdict"] == "FAILED_REPLICATION"


def test_not_significant_fails_even_same_sign():
    row = _verdict_row(_NAME, "nba", "team_asof_ingame", _fit(effect=0.001, p=0.5))
    assert row["verdict"] == "FAILED_REPLICATION"


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
