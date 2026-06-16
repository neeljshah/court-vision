"""Per-file tests for the X1 freshness pipeline. stdlib only; standalone or pytest.

Run ONLY as:
    python -m pytest scripts/platformkit/freshness/test_freshness_pipeline.py -q

The load-bearing test is the PLANTED-LATE-ROW guard: a row with extracted_at >= asof_ts MUST be
filtered out by as_of_out_ids AND must trip assert_vintage. If that ever passes silently, the
freshness lever has become a leak.
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402
from schema import validate_delta, STATUSES, SEVERITIES  # noqa: E402
from as_of_reader import as_of_out_ids, assert_vintage, partition_for_eval  # noqa: E402
from proxy_quarantine import (  # noqa: E402
    make_fallback_proxy, label_metric, assert_not_proxy_leak_free,
    OPTIMISTIC, LEAK_FREE,
)
from extract_stub import extract_doc, InjuryExtraction, downstream_valid, SYSTEM_PROMPT  # noqa: E402


def _row(**kw):
    base = {"player_id": "p1", "team_id": "t1", "status": "OUT", "severity": "major",
            "game_date": "2024-01-15", "source": "nba_official",
            "extracted_at": "2024-01-15T17:00:00", "confidence": 0.9}
    base.update(kw)
    return base


# ---- schema.validate_delta ----

def test_valid_delta_passes():
    validate_delta(_row())


def test_malformed_and_bad_status_rejected():
    for bad in (_row(status="INJURED"), _row(severity="catastrophic"),
                _row(confidence=1.5), _row(player_id=""),
                _row(status="AVAILABLE", severity="season_ending")):
        with pytest.raises(AssertionError):
            validate_delta(bad)


# ---- the load-bearing vintage guard ----

def test_planted_late_row_filtered_by_reader():
    asof = "2024-01-15T19:30:00"
    deltas = [
        _row(player_id="early", extracted_at="2024-01-15T17:00:00"),   # known pre-tip
        _row(player_id="late", extracted_at="2024-01-15T20:00:00"),    # PLANTED LATE row
    ]
    out = as_of_out_ids("t1", asof, deltas)
    assert out == {"early"}
    assert "late" not in out


def test_planted_late_row_trips_assert_vintage():
    asof = "2024-01-15T19:30:00"
    assert_vintage(_row(extracted_at="2024-01-15T17:00:00"), asof)   # pre-tip ok
    with pytest.raises(AssertionError) as e:
        assert_vintage(_row(extracted_at="2024-01-15T20:00:00"), asof)
    assert "LEAK" in str(e.value)


def test_tz_aware_late_row_raises_assertion_not_type_error():
    """Bug #5: tz-aware extracted_at must raise AssertionError('LEAK'), not TypeError."""
    asof = "2024-01-15T19:30:00"
    # tz-aware string with Z suffix; this row is after asof
    late_tz = _row(extracted_at="2024-01-15T20:00:00Z")
    with pytest.raises(AssertionError) as e:
        assert_vintage(late_tz, asof)
    assert "LEAK" in str(e.value)
    # also confirm as_of_out_ids filters it out rather than crashing
    out = as_of_out_ids("t1", asof, [late_tz, _row(player_id="early",
                                                    extracted_at="2024-01-15T17:00:00")])
    assert out == {"early"}
    assert "p1" not in out


def test_tie_break_is_deterministic_and_conservative():
    """Bug #6: equal extracted_at with conflicting status -> OUT wins regardless of order."""
    asof = "2024-01-15T19:30:00"
    same_ts = "2024-01-15T18:00:00"
    row_out = _row(player_id="star", status="OUT", extracted_at=same_ts)
    row_avail = _row(player_id="star", status="AVAILABLE", extracted_at=same_ts)
    # order 1: OUT first
    out1 = as_of_out_ids("t1", asof, [row_out, row_avail])
    # order 2: AVAILABLE first
    out2 = as_of_out_ids("t1", asof, [row_avail, row_out])
    assert out1 == out2, "tie-break must be input-order-independent"
    assert "star" in out1, "OUT must win the tie (conservative/leak-safe choice)"


def test_supersede_picks_latest_pre_asof():
    asof = "2024-01-15T19:30:00"
    deltas = [
        _row(player_id="star", status="QUESTIONABLE",
             extracted_at="2024-01-15T12:00:00"),                     # noon: questionable
        _row(player_id="star", status="OUT",
             extracted_at="2024-01-15T18:00:00"),                     # 90min pre-tip: OUT
        _row(player_id="star", status="AVAILABLE",
             extracted_at="2024-01-15T21:00:00"),                     # post-tip: ignored
    ]
    assert as_of_out_ids("t1", asof, deltas) == {"star"}


def test_reader_ignores_other_team_and_other_date():
    asof = "2024-01-15T19:30:00"
    deltas = [
        _row(player_id="a", team_id="t2"),                           # wrong team
        _row(player_id="b", game_date="2024-01-16",
             extracted_at="2024-01-16T17:00:00"),                    # wrong date
        _row(player_id="c"),                                         # the only valid one
    ]
    assert as_of_out_ids("t1", asof, deltas) == {"c"}


def test_partition_quarantines_proxy_and_catches_forward_leak():
    tip = "2024-01-15T19:30:00"
    deltas = [
        _row(player_id="forward", extracted_at="2024-01-15T17:00:00"),
        _row(player_id="proxy", is_fallback_proxy=True,
             extracted_at="2024-01-15T18:00:00"),
    ]
    leak_free, proxy = partition_for_eval(deltas, tip)
    assert [d["player_id"] for d in leak_free] == ["forward"]
    assert [d["player_id"] for d in proxy] == ["proxy"]
    # a NON-proxy row dated after tip must fail the vintage guard inside partition
    with pytest.raises(AssertionError):
        partition_for_eval([_row(extracted_at="2024-01-15T21:00:00")], tip)


# ---- proxy quarantine firewall ----

def test_proxy_tagged_optimistic_never_leak_free():
    m = label_metric("fallback_proxy", 0.123)
    assert m["honesty"] == OPTIMISTIC
    assert label_metric("leak_free", 0.2)["honesty"] == LEAK_FREE
    assert_not_proxy_leak_free(m)                                    # correctly tagged -> ok
    # a proxy metric mislabeled leak_free MUST trip the firewall
    bad = {"kind": "fallback_proxy", "honesty": LEAK_FREE, "value": 0.1}
    with pytest.raises(AssertionError):
        assert_not_proxy_leak_free(bad)


def test_make_fallback_proxy_stamps_and_flags():
    tip = "2024-01-15T19:30:00"
    proxy = make_fallback_proxy(_row(extracted_at="ignored"), tip, minutes_before=90)
    assert proxy["is_fallback_proxy"] is True
    assert proxy["extracted_at"] == "2024-01-15T18:00:00"


# ---- extraction stub ----

def test_extract_doc_is_a_stub_no_live_call():
    with pytest.raises(NotImplementedError):
        extract_doc("Player X is OUT (knee).")


def test_system_prompt_forbids_numbers_and_no_prob_field():
    assert "do NOT predict games" in SYSTEM_PROMPT
    assert "win probability" in SYSTEM_PROMPT
    # the extraction shape has no probability/win field -- invariant enforced by structure
    fields = InjuryExtraction("X", "OUT").__dict__
    assert "win_prob" not in fields and "probability" not in fields
    assert "confidence" in fields


def test_downstream_valid_catches_semantic_miss():
    ok = InjuryExtraction(player_name="X", status="OUT", severity="major",
                          confidence=0.9, game_date="2024-01-15")
    assert downstream_valid(ok, doc_date="2024-01-15")
    bad_consistency = InjuryExtraction(player_name="X", status="AVAILABLE",
                                       severity="season_ending", confidence=0.9)
    assert not downstream_valid(bad_consistency)
    bad_date = InjuryExtraction(player_name="X", status="OUT", confidence=0.5,
                                game_date="2024-06-01")
    assert not downstream_valid(bad_date, doc_date="2024-01-15")
    bad_conf = InjuryExtraction(player_name="X", status="OUT", confidence=1.7)
    assert not downstream_valid(bad_conf)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} freshness pipeline tests passed.")
