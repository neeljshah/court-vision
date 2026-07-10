"""Per-file: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/sim2/test_validate_clutch.py -q

Covers the verdict branch (single-bucket, multi-seed gate); the full walk-forward
pipeline is exercised via CLI, not unit tests (heavy IO)."""
from domains.basketball_nba.sim2.validate_clutch import _verdict_p4m2


def _run(p4_v2, p4_v3, pooled_v2, pooled_v3, crps_v2=5.0, crps_v3=5.0):
    return {"named": {"P4|m2": {"n": 288, "pit_dev_v2": p4_v2, "pit_dev_v3": p4_v3,
                                "crps_v2": crps_v2, "crps_v3": crps_v3}},
            "pooled": {"pit_dev_v2": pooled_v2, "pit_dev_v3": pooled_v3,
                      "crps_v2": crps_v2, "crps_v3": crps_v3}}


def test_matters_provisional_needs_p4m2_improved_on_every_seed():
    runs = [_run(0.14, 0.12, 0.06, 0.059), _run(0.14, 0.13, 0.06, 0.061, crps_v3=4.9)]
    v, _ = _verdict_p4m2(runs)
    assert v == "MATTERS_PROVISIONAL"


def test_null_when_one_seed_regresses_p4m2():
    runs = [_run(0.14, 0.12, 0.06, 0.059), _run(0.14, 0.15, 0.06, 0.059)]
    v, _ = _verdict_p4m2(runs)
    assert v == "NULL"


def test_null_when_pooled_never_improves_even_if_p4m2_does():
    runs = [_run(0.14, 0.12, 0.06, 0.061), _run(0.14, 0.13, 0.06, 0.061)]
    v, _ = _verdict_p4m2(runs)
    assert v == "NULL"


def test_not_testable_when_p4m2_missing():
    runs = [{"named": {"P4|m2": None}, "pooled": {"pit_dev_v2": 0.06, "pit_dev_v3": 0.06,
                                                   "crps_v2": 5.0, "crps_v3": 5.0}}]
    v, _ = _verdict_p4m2(runs)
    assert v == "NOT_TESTABLE"
