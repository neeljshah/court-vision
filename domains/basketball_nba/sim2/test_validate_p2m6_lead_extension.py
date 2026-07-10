"""Per-file: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/sim2/test_validate_p2m6_lead_extension.py -q

Covers the gate_verdict decision logic only (the fit/panel loop is exercised
via CLI -- network-free but heavy IO, same convention as test_validate_v3_gated.py)."""
from domains.basketball_nba.sim2.validate_p2m6_lead_extension import (
    gate_verdict, GATE_BUCKET, UNTOUCHED_BUCKETS, MIN_POWERED_N)


def _run(seed_offset, g_v2, g_g, pooled_v2, pooled_g, n=200,
         p3_v2=0.12, p3_g=None, p2_v2=0.14, p2_g=None, p4_v2=0.14, p4_g=None):
    p3_g = p3_v2 if p3_g is None else p3_g
    p2_g = p2_v2 if p2_g is None else p2_g
    p4_g = p4_v2 if p4_g is None else p4_g
    return {
        "seed_offset": seed_offset,
        "buckets": {
            GATE_BUCKET: {"n": n, "pit_dev_v2": g_v2, "pit_dev_gated": g_g},
            "P3|m3": {"n": 210, "pit_dev_v2": p3_v2, "pit_dev_gated": p3_g},
            "P2|m1": {"n": 132, "pit_dev_v2": p2_v2, "pit_dev_gated": p2_g},
            "P4|m2": {"n": 288, "pit_dev_v2": p4_v2, "pit_dev_gated": p4_g},
        },
        "pooled": {"n": 4624, "pit_dev_v2": pooled_v2, "pit_dev_gated": pooled_g},
    }


def test_ship_when_powered_and_improves_both_seeds_within_pooled_tol():
    runs = [_run(0, 0.20, 0.15, 0.0625, 0.0619, n=150),
            _run(1000, 0.21, 0.16, 0.0630, 0.0628, n=150)]
    v, _, checks = gate_verdict(runs)
    assert v == "SHIP_CANDIDATE_GATED"
    assert all(c["untouched_buckets_ok"] for c in checks)


def test_provisional_underpowered_when_n_below_floor_but_otherwise_ships():
    assert 65 < MIN_POWERED_N
    runs = [_run(0, 0.20, 0.15, 0.0625, 0.0619, n=65),
            _run(1000, 0.21, 0.16, 0.0630, 0.0628, n=65)]
    v, _, _ = gate_verdict(runs)
    assert v == "IMPROVES_PROVISIONAL_UNDERPOWERED"


def test_reject_when_pooled_exceeds_tolerance():
    runs = [_run(0, 0.20, 0.15, 0.0625, 0.0619, n=150),
            _run(1000, 0.21, 0.16, 0.0630, 0.0700, n=150)]  # blows the +0.0005 tol
    v, _, _ = gate_verdict(runs)
    assert v == "REJECT"


def test_reject_when_gate_bucket_does_not_improve():
    runs = [_run(0, 0.20, 0.22, 0.0625, 0.0619, n=150),   # got worse
            _run(1000, 0.21, 0.16, 0.0630, 0.0628, n=150)]
    v, _, _ = gate_verdict(runs)
    assert v == "REJECT"


def test_reject_when_untouched_bucket_is_not_byte_identical_to_v2():
    runs = [_run(0, 0.20, 0.15, 0.0625, 0.0619, n=150, p4_v2=0.14, p4_g=0.1403),
            _run(1000, 0.21, 0.16, 0.0630, 0.0628, n=150)]
    v, _, _ = gate_verdict(runs)
    assert v == "REJECT"


def test_underpowered_when_gate_bucket_has_zero_observations():
    r0 = _run(0, 0.20, 0.15, 0.0625, 0.0619, n=0)
    r1 = _run(1000, 0.21, 0.16, 0.0630, 0.0628, n=150)
    v, _, _ = gate_verdict([r0, r1])
    assert v == "UNDERPOWERED"


def test_gate_bucket_and_untouched_set_match_the_task_scope():
    assert GATE_BUCKET == "P2|m6"
    assert UNTOUCHED_BUCKETS == ["P3|m3", "P2|m1", "P4|m2"]
