"""predict_service.tests.test_status_freshness_normalizer -- per-file test.

Acceptance criteria (from QA-STATUS-FRESH-NORM):
  A1. row fresh=null, age_sec=548, sla=300  -> normalized fresh='stale', ok=False.
  A2. row with recent source_ts (age < sla) -> normalized fresh='fresh', ok=True.
  A3. row with missing source_ts            -> normalized fresh='stale', ok=False
      (invariant: missing source = stale, never ok).
  A4. monotone-down rollup: any stale child degrades parent overall to >=degraded.
      A fresh child cannot lift a stale parent back to 'ok'.
  A5. fresh already 'stale'/'fresh'/'down' passes through unchanged (no over-write).
  A6. fresh='unknown' coerces to 'stale'.
  A7. normalize_row NEVER raises on garbage input.
  A8. normalize_rows NEVER raises on an empty list (yields degraded, not ok).
  A9. No $ field emitted anywhere in the output.
  A10. ok=True ONLY when fresh=='fresh'.
  A11. Two stale rows -> rollup overall='degraded', n_fresh=0, n_stale=2.
  A12. sla_map per-name override respected (tight SLA forces stale sooner).

Run (per-file only -- never run the full suite, it freezes the box)::
    cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/tests/test_status_freshness_normalizer.py -q
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure repo root is on sys.path so the module import resolves cleanly.
# ---------------------------------------------------------------------------
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from predict_service.status_freshness_normalizer import (  # noqa: E402
    DEFAULT_SLA_SEC,
    HONEST_NOTE,
    normalize_row,
    normalize_rows,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ts_ago(seconds: float) -> str:
    """Return an ISO-8601 UTC timestamp for *seconds* seconds ago."""
    dt = _utcnow() - timedelta(seconds=seconds)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# A1 -- Canonical stale path: fresh=null, age_sec=548, sla=300 -> stale, ok=False
# ---------------------------------------------------------------------------

def test_a1_null_fresh_age_548_sla_300_is_stale():
    row = {
        "name": "m1_producer",
        "fresh": None,
        "age_sec": 548.0,
        "ok": None,
    }
    out = normalize_row(row, sla_sec=300.0)
    assert out["fresh"] == "stale", "A1: expected stale, got %r" % out["fresh"]
    assert out["ok"] is False, "A1: ok must be False when fresh=stale"
    assert "$" not in str(out), "A9: no $ field"


# ---------------------------------------------------------------------------
# A2 -- Recent source_ts (age < sla) -> fresh, ok=True
# ---------------------------------------------------------------------------

def test_a2_recent_source_ts_is_fresh():
    row = {
        "name": "m1_producer",
        "fresh": None,
        "source_ts": _ts_ago(60),  # 1 minute ago; sla=300
        "ok": None,
    }
    out = normalize_row(row, sla_sec=300.0)
    assert out["fresh"] == "fresh", "A2: expected fresh, got %r" % out["fresh"]
    assert out["ok"] is True, "A2: ok must be True when fresh='fresh'"


# ---------------------------------------------------------------------------
# A3 -- Missing source_ts (no age either) -> stale, ok=False
# ---------------------------------------------------------------------------

def test_a3_missing_source_ts_is_stale():
    row = {
        "name": "m1_producer",
        "fresh": None,
        "source_ts": None,
        "age_sec": None,
        "ok": None,
    }
    out = normalize_row(row, sla_sec=300.0)
    assert out["fresh"] == "stale", "A3: missing source_ts must yield stale"
    assert out["ok"] is False, "A3: ok must be False when source_ts missing"


# ---------------------------------------------------------------------------
# A4 -- Monotone-down rollup: stale child degrades parent
# ---------------------------------------------------------------------------

def test_a4_monotone_down_stale_child_degrades_parent():
    rows = [
        {"name": "svc_a", "fresh": "fresh", "age_sec": 10.0},
        {"name": "svc_b", "fresh": None, "age_sec": 9999.0},  # stale
    ]
    result = normalize_rows(rows, default_sla_sec=300.0)
    assert result["overall"] in ("degraded", "down"), (
        "A4: stale child must degrade parent; got %r" % result["overall"]
    )
    assert result["ok"] is False, "A4: rollup ok must be False when any child is stale"


def test_a4b_fresh_child_cannot_lift_stale_parent():
    rows = [
        {"name": "svc_stale", "fresh": "stale", "age_sec": 9999.0},
        {"name": "svc_fresh", "fresh": "fresh", "age_sec": 5.0},
    ]
    result = normalize_rows(rows, default_sla_sec=300.0)
    assert result["overall"] != "ok", (
        "A4b: fresh child must not lift stale parent to ok; got %r" % result["overall"]
    )


# ---------------------------------------------------------------------------
# A5 -- Concrete verdicts pass through unchanged
# ---------------------------------------------------------------------------

def test_a5_concrete_fresh_passthrough():
    row = {"name": "svc", "fresh": "fresh", "ok": True, "age_sec": 10.0}
    out = normalize_row(row, sla_sec=300.0)
    assert out["fresh"] == "fresh"
    assert out["ok"] is True


def test_a5_concrete_stale_passthrough():
    row = {"name": "svc", "fresh": "stale", "ok": False, "age_sec": 9999.0}
    out = normalize_row(row, sla_sec=300.0)
    assert out["fresh"] == "stale"
    assert out["ok"] is False


def test_a5_concrete_down_passthrough():
    row = {"name": "svc", "fresh": "down", "ok": False}
    out = normalize_row(row, sla_sec=300.0)
    assert out["fresh"] == "down"
    assert out["ok"] is False


# ---------------------------------------------------------------------------
# A6 -- fresh='unknown' coerces to 'stale'
# ---------------------------------------------------------------------------

def test_a6_unknown_fresh_coerces_to_stale():
    row = {"name": "svc", "fresh": "unknown", "age_sec": None}
    out = normalize_row(row, sla_sec=300.0)
    assert out["fresh"] == "stale", "A6: 'unknown' must coerce to 'stale'"
    assert out["ok"] is False


# ---------------------------------------------------------------------------
# A7 -- NEVER raises on garbage input
# ---------------------------------------------------------------------------

def test_a7_does_not_raise_on_garbage():
    garbage_inputs = [
        None,
        {},
        {"fresh": object()},
        {"fresh": None, "age_sec": "not-a-number", "source_ts": 12345},
        {"fresh": None, "generated_at": "garbage-ts"},
        {"name": None, "fresh": None, "age_sec": float("nan")},
    ]
    for inp in garbage_inputs:
        try:
            out = normalize_row(inp or {}, sla_sec=300.0)
            # Must always have fresh set and ok derived.
            assert out.get("fresh") in ("fresh", "stale", "down", None), (
                "A7: unexpected fresh value %r for input %r" % (out.get("fresh"), inp)
            )
        except Exception as exc:
            pytest.fail("A7: normalize_row raised on input %r: %s" % (inp, exc))


# ---------------------------------------------------------------------------
# A8 -- normalize_rows empty list -> degraded, never ok
# ---------------------------------------------------------------------------

def test_a8_empty_rows_yields_degraded():
    result = normalize_rows([], default_sla_sec=300.0)
    assert result["overall"] in ("degraded", "down"), (
        "A8: empty rows must yield degraded or down, got %r" % result["overall"]
    )
    assert result["ok"] is False, "A8: empty rows must never be ok"


# ---------------------------------------------------------------------------
# A9 -- No $ field in output
# ---------------------------------------------------------------------------

def _has_dollar_key(d: dict) -> bool:
    """Return True if any key in *d* (or nested dicts/lists) contains '$'."""
    for k, v in d.items():
        if "$" in str(k):
            return True
        if isinstance(v, dict) and _has_dollar_key(v):
            return True
        if isinstance(v, list):
            for item in v:
                if isinstance(item, dict) and _has_dollar_key(item):
                    return True
    return False


def test_a9_no_dollar_field_single_row():
    row = {"name": "m1_producer", "fresh": None, "age_sec": 548.0}
    out = normalize_row(row, sla_sec=300.0)
    assert not _has_dollar_key(out), "A9: no $ key in single row output"


def test_a9_no_dollar_field_rollup():
    rows = [{"name": "svc", "fresh": None, "age_sec": 548.0}]
    result = normalize_rows(rows, default_sla_sec=300.0)
    assert not _has_dollar_key(result), "A9: no $ key in rollup output"
    assert result.get("edge_claimed") is False


# ---------------------------------------------------------------------------
# A10 -- ok=True ONLY when fresh=='fresh'
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fresh,expected_ok", [
    ("fresh", True),
    ("stale", False),
    ("down", False),
    (None, False),
    ("unknown", False),
])
def test_a10_ok_only_when_fresh(fresh, expected_ok):
    row = {"name": "svc", "fresh": fresh, "age_sec": None, "source_ts": None}
    out = normalize_row(row, sla_sec=300.0)
    assert out["ok"] is expected_ok, (
        "A10: fresh=%r should give ok=%r, got ok=%r" % (fresh, expected_ok, out["ok"])
    )


# ---------------------------------------------------------------------------
# A11 -- Two stale rows -> overall degraded, n_fresh=0, n_stale=2
# ---------------------------------------------------------------------------

def test_a11_two_stale_rows_rollup():
    rows = [
        {"name": "svc_a", "fresh": None, "age_sec": 9999.0},
        {"name": "svc_b", "fresh": None, "source_ts": None, "age_sec": None},
    ]
    result = normalize_rows(rows, default_sla_sec=300.0)
    assert result["overall"] in ("degraded", "down"), (
        "A11: expected degraded/down, got %r" % result["overall"]
    )
    assert result["n_fresh"] == 0, "A11: n_fresh must be 0"
    assert result["n_stale"] == 2, "A11: n_stale must be 2"
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# A12 -- sla_map per-name override respected
# ---------------------------------------------------------------------------

def test_a12_sla_map_override():
    rows = [
        # age=100s; default sla=300 would give fresh, but name-sla=60 gives stale.
        {"name": "tight_svc", "fresh": None, "age_sec": 100.0},
        # age=10s; default sla=300 -> fresh.
        {"name": "normal_svc", "fresh": None, "age_sec": 10.0},
    ]
    result = normalize_rows(
        rows,
        default_sla_sec=300.0,
        sla_map={"tight_svc": 60.0},
    )
    norm_tight = result["rows"][0]
    norm_normal = result["rows"][1]
    assert norm_tight["fresh"] == "stale", (
        "A12: tight_svc age=100 > sla=60 must be stale"
    )
    assert norm_normal["fresh"] == "fresh", (
        "A12: normal_svc age=10 < sla=300 must be fresh"
    )
    # One stale child degrades overall.
    assert result["overall"] != "ok", "A12: stale child must degrade rollup"


# ---------------------------------------------------------------------------
# Extra: age_seconds alias (some rows carry this key instead of age_sec)
# ---------------------------------------------------------------------------

def test_age_seconds_alias():
    row = {"name": "m1_producer", "fresh": None, "age_seconds": 548.0}
    out = normalize_row(row, sla_sec=300.0)
    assert out["fresh"] == "stale"
    assert out["ok"] is False


# ---------------------------------------------------------------------------
# Extra: generated_at timestamp fallback (no age_sec, no source_ts)
# ---------------------------------------------------------------------------

def test_generated_at_fallback_fresh():
    row = {
        "name": "m1_producer",
        "fresh": None,
        "generated_at": _ts_ago(30),  # 30s ago; sla=300
        "age_sec": None,
        "source_ts": None,
    }
    out = normalize_row(row, sla_sec=300.0)
    assert out["fresh"] == "fresh"
    assert out["ok"] is True


def test_generated_at_fallback_stale():
    row = {
        "name": "m1_producer",
        "fresh": None,
        "generated_at": _ts_ago(9999),  # way old
        "age_sec": None,
        "source_ts": None,
    }
    out = normalize_row(row, sla_sec=300.0)
    assert out["fresh"] == "stale"
    assert out["ok"] is False


# ---------------------------------------------------------------------------
# Extra: normalize_rows never raises on garbage
# ---------------------------------------------------------------------------

def test_normalize_rows_never_raises():
    try:
        result = normalize_rows(None, default_sla_sec=300.0)  # type: ignore[arg-type]
        assert result["ok"] is False
    except Exception as exc:
        pytest.fail("normalize_rows raised on None input: %s" % exc)


# ---------------------------------------------------------------------------
# Extra: honest_note is always present, edge_claimed=False
# ---------------------------------------------------------------------------

def test_honest_note_and_edge_claimed_rollup():
    result = normalize_rows([{"name": "svc", "fresh": "fresh", "age_sec": 5.0}],
                            default_sla_sec=300.0)
    assert "honest_note" in result, "honest_note must be present"
    assert result.get("edge_claimed") is False, "edge_claimed must be False"
