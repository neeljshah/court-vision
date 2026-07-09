"""Per-file: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/sim2/test_replicate_v3.py -q

Tests the pure decision logic (seed/temporal pass rules + verdict combination)
without the heavy fit/simulate pipeline, matching test_validate_v3.py's pattern."""
from domains.basketball_nba.sim2.replicate_v3 import (
    _seed_sign_ok, _temporal_sign_ok, replication_verdict)


def _named(pit2, pit3):
    return {"pit_dev_v2": pit2, "pit_dev_v3": pit3}


def test_seed_sign_ok_passes_when_4_of_5_seeds_improve_and_pooled_within_tol():
    runs = []
    for i in range(5):
        improved = i < 4
        runs.append({
            "pooled": {"pit_dev_v2": 0.06, "pit_dev_v3": 0.0601},
            "named": {"P3|m3": _named(0.14, 0.12 if improved else 0.16),
                     "P2|m1": _named(0.13, 0.11)},
        })
    v = _seed_sign_ok(runs)
    assert v["pass"] is True
    assert v["per_bucket"]["P3|m3"]["seeds_improved"] == 4


def test_seed_sign_ok_fails_when_only_2_of_5_seeds_improve():
    runs = []
    for i in range(5):
        improved = i < 2
        runs.append({
            "pooled": {"pit_dev_v2": 0.06, "pit_dev_v3": 0.0601},
            "named": {"P3|m3": _named(0.14, 0.12 if improved else 0.16),
                     "P2|m1": _named(0.13, 0.11)},
        })
    v = _seed_sign_ok(runs)
    assert v["pass"] is False


def test_seed_sign_ok_fails_when_pooled_degrades_beyond_tolerance():
    runs = [{
        "pooled": {"pit_dev_v2": 0.06, "pit_dev_v3": 0.07},  # +0.01 >> tol 0.0005
        "named": {"P3|m3": _named(0.14, 0.12), "P2|m1": _named(0.13, 0.11)},
    } for _ in range(5)]
    v = _seed_sign_ok(runs)
    assert v["pass"] is False
    assert v["pooled_within_tol"] is False


def test_temporal_sign_ok_passes_when_at_least_one_half_improves():
    halves = {
        "first_half": {"pooled": _named(0.06, 0.059),
                       "named": {"P3|m3": _named(0.14, 0.12), "P2|m1": _named(0.13, 0.14)}},
        "second_half": {"pooled": _named(0.06, 0.059),
                       "named": {"P3|m3": _named(0.14, 0.15), "P2|m1": _named(0.13, 0.11)}},
    }
    v = _temporal_sign_ok(halves)
    assert v["pass"] is True


def test_temporal_sign_ok_fails_on_full_reversal_in_both_halves():
    halves = {
        "first_half": {"pooled": _named(0.06, 0.059),
                       "named": {"P3|m3": _named(0.14, 0.16), "P2|m1": _named(0.13, 0.11)}},
        "second_half": {"pooled": _named(0.06, 0.059),
                       "named": {"P3|m3": _named(0.14, 0.16), "P2|m1": _named(0.13, 0.11)}},
    }
    v = _temporal_sign_ok(halves)
    assert v["per_bucket"]["P3|m3"]["pass"] is False


def test_replication_verdict_replicated_only_when_both_pass():
    pass_v = {"pass": True}
    fail_v = {"pass": False}
    verdict, _ = replication_verdict(pass_v, pass_v, {})
    assert verdict == "REPLICATED"
    verdict, lesson = replication_verdict(fail_v, pass_v, {})
    assert verdict == "NULL"
    assert "seed-unstable" in lesson
    verdict, lesson = replication_verdict(pass_v, fail_v, {})
    assert verdict == "NULL"
    assert "temporal-unstable" in lesson
