"""Per-file test for scripts.platformkit.autonomy.supervisor_readiness (RB-D-1).

Proves the readiness surface NEVER reads a hung/dead/unobserved service as READY:
fresh heartbeat => ok; stale => degraded; absent + expects_heartbeat => degraded;
breaker OPEN => down; dead => down; unobserved => not green. A green-on-missing row
would fail the monotone-DOWN rollup -- the negative-control test here proves the
rollup catches it.
"""
from __future__ import annotations

from scripts.platformkit.autonomy import supervisor_readiness as sr


class _RD:
    def __init__(self, kind, fresh_sec=300.0, hb="x"):
        self.kind = kind
        self.fresh_sec = fresh_sec
        self.heartbeat_path = hb


class _Spec:
    def __init__(self, name, kind, fresh_sec=300.0, hb="x"):
        self.name = name
        self.readiness = _RD(kind, fresh_sec, hb)


_HB = "heartbeat-file-fresh"
_NONE = "none"


def test_fresh_heartbeat_is_ok():
    doc = sr.compose_readiness(
        [_Spec("a", _HB)], {"a": {"alive": True, "hb_age": 5.0,
                                  "breaker": {"state": "CLOSED"}}})
    row = doc["services"][0]
    assert row["status"] == sr.OK
    assert doc["overall"] == sr.OK


def test_stale_heartbeat_is_degraded_not_ready():
    doc = sr.compose_readiness(
        [_Spec("a", _HB, fresh_sec=300.0)],
        {"a": {"alive": True, "hb_age": 99999.0, "breaker": {"state": "CLOSED"}}})
    assert doc["services"][0]["status"] == sr.DEGRADED
    assert doc["overall"] == sr.DEGRADED


def test_absent_heartbeat_with_expectation_is_degraded():
    doc = sr.compose_readiness(
        [_Spec("a", _HB)],
        {"a": {"alive": True, "hb_age": None, "breaker": {"state": "CLOSED"}}})
    assert doc["services"][0]["status"] == sr.DEGRADED


def test_open_breaker_is_down():
    doc = sr.compose_readiness(
        [_Spec("a", _HB)],
        {"a": {"alive": True, "hb_age": 5.0, "breaker": {"state": "OPEN"}}})
    assert doc["services"][0]["status"] == sr.DOWN
    assert doc["overall"] == sr.DOWN


def test_dead_service_is_down():
    doc = sr.compose_readiness(
        [_Spec("a", _HB)],
        {"a": {"alive": False, "hb_age": None, "breaker": {"state": "CLOSED"}}})
    assert doc["services"][0]["status"] == sr.DOWN


def test_unobserved_service_is_not_green():
    # A service in the manifest but with NO observation must NOT read OK.
    doc = sr.compose_readiness([_Spec("a", _HB)], {})
    assert doc["services"][0]["status"] != sr.OK
    assert doc["services"][0]["observed"] is False
    assert doc["overall"] != sr.OK


def test_none_readiness_service_ok_when_alive_but_flagged_exempt():
    doc = sr.compose_readiness(
        [_Spec("a", _NONE, hb=None)],
        {"a": {"alive": True, "hb_age": None, "breaker": {"state": "CLOSED"}}})
    row = doc["services"][0]
    assert row["status"] == sr.OK
    assert row["expects_heartbeat"] is False  # explicit exemption, not silent green


def test_future_stamped_heartbeat_not_green():
    # Negative age (clock skew / constant-future stamp) must not read fresh.
    doc = sr.compose_readiness(
        [_Spec("a", _HB)],
        {"a": {"alive": True, "hb_age": -50.0, "breaker": {"state": "CLOSED"}}})
    assert doc["services"][0]["status"] == sr.DEGRADED


def test_monotone_down_rollup_one_bad_degrades_whole():
    doc = sr.compose_readiness(
        [_Spec("a", _HB), _Spec("b", _HB)],
        {"a": {"alive": True, "hb_age": 5.0, "breaker": {"state": "CLOSED"}},
         "b": {"alive": True, "hb_age": 99999.0, "breaker": {"state": "OPEN"}}})
    # one ok + one down -> overall DOWN.
    assert doc["overall"] == sr.DOWN


def test_empty_specs_is_degraded_never_empty_green():
    doc = sr.compose_readiness([], {})
    assert doc["overall"] == sr.DEGRADED


def test_garbage_age_is_degraded():
    doc = sr.compose_readiness(
        [_Spec("a", _HB)],
        {"a": {"alive": True, "hb_age": "garbage", "breaker": {"state": "CLOSED"}}})
    assert doc["services"][0]["status"] == sr.DEGRADED


def test_no_dollar_field_in_surface():
    import re
    doc = sr.compose_readiness(
        [_Spec("a", _HB)],
        {"a": {"alive": True, "hb_age": 5.0, "breaker": {"state": "CLOSED"}}})
    # No fabricated money VALUE ($ adjacent to a digit). The honest_note may say
    # the phrase "no $ field" -- that is the disclaimer, not a money value.
    assert not re.search(r"\$\s*\d", str(doc))
    assert "no $ field" in doc["honest_note"]
