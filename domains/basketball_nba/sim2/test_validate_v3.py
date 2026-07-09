"""Per-file: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/sim2/test_validate_v3.py -q

Covers the verdict branch (the actual decision logic in validate_v3.run); the full
walk-forward pipeline is exercised via CLI, not unit tests (network-free but heavy IO)."""
from domains.basketball_nba.sim2.validate_v3 import _verdict


def test_matters_provisional_needs_2_of_3_named_plus_pooled_gain():
    pooled = {"pit_dev_v2": 0.10, "pit_dev_v3": 0.09, "crps_v2": 5.0, "crps_v3": 5.0}
    v, _ = _verdict(named_improved=2, pooled=pooled)
    assert v == "MATTERS_PROVISIONAL"


def test_null_when_pooled_does_not_improve_even_if_named_do():
    pooled = {"pit_dev_v2": 0.10, "pit_dev_v3": 0.11, "crps_v2": 5.0, "crps_v3": 5.1}
    v, _ = _verdict(named_improved=3, pooled=pooled)
    assert v == "NULL"


def test_null_when_only_1_of_3_named_improved():
    pooled = {"pit_dev_v2": 0.10, "pit_dev_v3": 0.09, "crps_v2": 5.0, "crps_v3": 4.9}
    v, _ = _verdict(named_improved=1, pooled=pooled)
    assert v == "NULL"
