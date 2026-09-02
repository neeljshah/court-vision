"""Tests for the freshness schema + vintage guard. stdlib only; standalone or pytest."""
from __future__ import annotations
import os as _os, sys as _sys  # noqa: E402
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # blueprint uses bare sibling imports; make them work under "python -m pytest" from the repo root too
from freshness_schema import (
    validate_delta, assert_vintage, partition_for_eval, label_metric, vacated_usage_share,
)


def _row(**kw):
    base = {"player_id": "p1", "team_id": "t1", "status": "OUT", "severity": "major",
            "game_date": "2024-01-15", "source": "beat-writer",
            "extracted_at": "2024-01-15T17:00:00", "confidence": 0.9}
    base.update(kw)
    return base


def test_valid_delta_passes():
    validate_delta(_row())


def test_bad_fields_raise():
    for bad in (_row(status="INJURED"), _row(severity="catastrophic"),
                _row(confidence=1.5), _row(player_id="")):
        try:
            validate_delta(bad); raise SystemExit("FAIL: bad row accepted")
        except AssertionError:
            pass


def test_vintage_guard():
    tip = "2024-01-15T19:30:00"
    assert_vintage(_row(extracted_at="2024-01-15T17:00:00"), tip)   # before tip -> ok
    try:
        assert_vintage(_row(extracted_at="2024-01-15T20:00:00"), tip)  # after tip -> leak
        raise SystemExit("FAIL: leak not caught")
    except AssertionError as e:
        assert "LEAK" in str(e)


def test_fallback_proxy_quarantined():
    tip = "2024-01-15T19:30:00"
    deltas = [
        _row(player_id="forward", extracted_at="2024-01-15T17:00:00"),       # leak-free
        _row(player_id="proxy", extracted_at="2024-01-15T18:00:00",
             is_fallback_proxy=True),                                        # quarantined
    ]
    leak_free, proxy = partition_for_eval(deltas, tip)
    assert [d["player_id"] for d in leak_free] == ["forward"]
    assert [d["player_id"] for d in proxy] == ["proxy"]
    # a metric on the proxy subset must be labeled an optimistic upper bound, never leak-free
    m = label_metric("fallback_proxy", 0.123)
    assert m["honesty"] == "OPTIMISTIC_UPPER_BOUND"
    assert label_metric("leak_free", 0.2)["honesty"] == "leak_free"


def test_partition_raises_on_forward_row_leak():
    tip = "2024-01-15T19:30:00"
    # a NON-proxy row dated after tip must fail the vintage guard inside partition
    try:
        partition_for_eval([_row(extracted_at="2024-01-15T21:00:00")], tip)
        raise SystemExit("FAIL: forward leak not caught")
    except AssertionError as e:
        assert "LEAK" in str(e)


def test_vacated_usage_mapping():
    assert vacated_usage_share(_row(status="OUT"), 0.28) == 0.28
    assert vacated_usage_share(_row(status="PROBABLE"), 0.28) == 0.0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} freshness schema tests passed.")
