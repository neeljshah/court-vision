"""Per-file: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/sim2/test_validate_v3_gated.py -q

Covers the gate_verdict decision logic only (the routing/panel loop is exercised
via CLI -- network-free but heavy IO, same convention as test_validate_v3.py)."""
from domains.basketball_nba.sim2.validate_v3_gated import gate_verdict, GATE_BUCKETS


def _run(seed_offset, p3_v2, p3_g, p2_v2, p2_g, pooled_v2, pooled_g, p4_v2=0.14, p4_g=None):
    if p4_g is None:
        p4_g = p4_v2  # untouched by default
    return {
        "seed_offset": seed_offset,
        "buckets": {
            "P3|m3": {"n": 210, "pit_dev_v2": p3_v2, "pit_dev_gated": p3_g},
            "P2|m1": {"n": 132, "pit_dev_v2": p2_v2, "pit_dev_gated": p2_g},
            "P4|m2": {"n": 288, "pit_dev_v2": p4_v2, "pit_dev_gated": p4_g},
        },
        "pooled": {"n": 4624, "pit_dev_v2": pooled_v2, "pit_dev_gated": pooled_g},
    }


def test_ship_when_both_gate_buckets_improve_both_seeds_within_pooled_tol():
    runs = [_run(0, 0.12, 0.10, 0.14, 0.12, 0.0625, 0.0619),
            _run(1000, 0.13, 0.11, 0.15, 0.13, 0.0630, 0.0628)]
    v, _, checks = gate_verdict(runs)
    assert v == "SHIP_CANDIDATE_GATED"
    assert all(c["p4m2_untouched"] for c in checks)


def test_reject_when_pooled_exceeds_tolerance():
    runs = [_run(0, 0.12, 0.10, 0.14, 0.12, 0.0625, 0.0619),
            _run(1000, 0.13, 0.11, 0.15, 0.13, 0.0630, 0.0700)]  # blows the +0.0005 tol
    v, _, _ = gate_verdict(runs)
    assert v == "REJECT"


def test_reject_when_a_gate_bucket_does_not_improve():
    runs = [_run(0, 0.12, 0.13, 0.14, 0.12, 0.0625, 0.0619),  # P3|m3 got worse
            _run(1000, 0.13, 0.11, 0.15, 0.13, 0.0630, 0.0628)]
    v, _, _ = gate_verdict(runs)
    assert v == "REJECT"


def test_reject_when_p4m2_is_not_byte_identical_to_v2():
    runs = [_run(0, 0.12, 0.10, 0.14, 0.12, 0.0625, 0.0619, p4_v2=0.14, p4_g=0.1403),
            _run(1000, 0.13, 0.11, 0.15, 0.13, 0.0630, 0.0628)]
    v, _, _ = gate_verdict(runs)
    assert v == "REJECT"


def test_underpowered_when_gate_bucket_has_zero_observations():
    r0 = _run(0, 0.12, 0.10, 0.14, 0.12, 0.0625, 0.0619)
    r0["buckets"]["P3|m3"]["n"] = 0
    runs = [r0, _run(1000, 0.13, 0.11, 0.15, 0.13, 0.0630, 0.0628)]
    v, _, _ = gate_verdict(runs)
    assert v == "UNDERPOWERED"


def test_gate_buckets_constant_matches_the_2_replicated_named_buckets():
    assert GATE_BUCKETS == ["P3|m3", "P2|m1"]
