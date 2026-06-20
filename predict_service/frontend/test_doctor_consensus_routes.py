"""predict_service.frontend.test_doctor_consensus_routes -- per-file test.

Acceptance criteria for QA-DOCTOR-CONSENSUS:

  DC1. A row with fresh=null + age_sec >= sla  ->  doctor severity 'degraded'/'down',
       never 'ok'. The service appears in problems[], NOT ok_services[].

  DC2. doctor overall == WORST of all normalized row severities.
       Two stale rows -> overall 'degraded', never 'ok'.

  DC3. doctor overall matches what normalize_rows would report for the SAME input
       (consensus guarantee: cannot disagree with autonomy for the same services[]).

  DC4. A fresh child cannot lift a stale parent: stale+fresh -> overall != 'ok'.

  DC5. No $/roi/pnl/profit key anywhere in the diagnosis output.

  DC6. stale-never-green: fresh=null with no age/ts -> problems[], never ok_services[].

  DC7. A 'down' row (live=False or breaker=OPEN) -> overall 'down', in problems[].

  DC8. A critical service that is stale -> problems[].severity == 'critical'.

  DC9. build_diagnosis() NEVER raises on garbage input (None, [], bad types).

  DC10. ok_services[] has only services whose normalized fresh=='fresh' (no heartbeat
        issues), problems[] has everything else.

  DC11. edge_claimed=False always present; honest_note always present (no $ key).

  DC12. build_diagnosis([]) -> overall 'degraded'/'down' (empty is never ok).

Run (per-file only -- never run the full suite, it freezes the box)::
    cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/frontend/test_doctor_consensus_routes.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure repo root is on sys.path.
# ---------------------------------------------------------------------------
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from predict_service.frontend.doctor_consensus_routes import build_diagnosis  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_bad_key(d: object) -> bool:
    """True if any key in *d* (recursively) contains $, roi, pnl, or profit."""
    if not isinstance(d, dict):
        return False
    for k, v in d.items():
        k_low = str(k).lower()
        if any(tok in k_low for tok in ("$", "roi", "pnl", "profit")):
            return True
        if isinstance(v, dict) and _has_bad_key(v):
            return True
        if isinstance(v, list):
            for item in v:
                if _has_bad_key(item):
                    return True
    return False


def _svc(name, fresh=None, age_sec=None, live=None, critical=False, breaker=None):
    """Minimal services[] row fixture."""
    row = {"name": name, "fresh": fresh, "critical": critical}
    if age_sec is not None:
        row["age_sec"] = age_sec
    if live is not None:
        row["live"] = live
    if breaker is not None:
        row["breaker"] = breaker
    return row


# ---------------------------------------------------------------------------
# DC1 -- fresh=null + age_sec >= sla -> problems[], never ok_services[]
# ---------------------------------------------------------------------------

def test_dc1_null_fresh_stale_age_is_problem():
    svc = _svc("m1_producer", fresh=None, age_sec=548.0)
    diag = build_diagnosis([svc], sla_sec=300.0)
    names_in_problems = [p["service"] for p in diag["problems"]]
    assert "m1_producer" in names_in_problems, (
        "DC1: m1_producer (fresh=null, age=548>sla=300) must be in problems"
    )
    assert "m1_producer" not in diag["ok_services"], (
        "DC1: m1_producer must NOT be in ok_services"
    )
    assert diag["overall"] in ("degraded", "down"), (
        "DC1: overall must be degraded/down, got %r" % diag["overall"]
    )


def test_dc1_null_fresh_no_age_is_problem():
    svc = _svc("m1_producer", fresh=None, age_sec=None)
    diag = build_diagnosis([svc], sla_sec=300.0)
    names = [p["service"] for p in diag["problems"]]
    assert "m1_producer" in names, "DC1b: null fresh + no age -> problems[]"
    assert diag["overall"] in ("degraded", "down")


# ---------------------------------------------------------------------------
# DC2 -- overall == WORST of normalized severities
# ---------------------------------------------------------------------------

def test_dc2_two_stale_rows_overall_degraded():
    rows = [
        _svc("svc_a", fresh=None, age_sec=9000.0),
        _svc("svc_b", fresh=None, age_sec=None),
    ]
    diag = build_diagnosis(rows, sla_sec=300.0)
    assert diag["overall"] in ("degraded", "down"), (
        "DC2: two stale rows -> degraded/down; got %r" % diag["overall"]
    )
    assert diag["overall"] != "ok"


def test_dc2_all_fresh_is_ok():
    rows = [
        _svc("svc_a", fresh="fresh", age_sec=10.0),
        _svc("svc_b", fresh="fresh", age_sec=20.0),
    ]
    diag = build_diagnosis(rows, sla_sec=300.0)
    assert diag["overall"] == "ok", (
        "DC2: all fresh -> overall ok; got %r" % diag["overall"]
    )


# ---------------------------------------------------------------------------
# DC3 -- consensus: doctor overall matches normalize_rows overall for same input
# ---------------------------------------------------------------------------

def test_dc3_consensus_with_normalize_rows():
    from predict_service.status_freshness_normalizer import normalize_rows
    rows = [
        _svc("svc_null", fresh=None, age_sec=548.0),
        _svc("svc_fresh", fresh="fresh", age_sec=10.0),
    ]
    diag = build_diagnosis(rows, sla_sec=300.0)
    norm = normalize_rows(rows, default_sla_sec=300.0)
    assert diag["overall"] == norm["overall"], (
        "DC3: doctor overall %r must match normalize_rows overall %r"
        % (diag["overall"], norm["overall"])
    )


def test_dc3_consensus_all_null_fresh():
    from predict_service.status_freshness_normalizer import normalize_rows
    rows = [
        _svc("a", fresh=None, age_sec=999.0),
        _svc("b", fresh=None, age_sec=None),
    ]
    diag = build_diagnosis(rows, sla_sec=300.0)
    norm = normalize_rows(rows, default_sla_sec=300.0)
    assert diag["overall"] == norm["overall"], (
        "DC3b: doctor %r vs normalize_rows %r"
        % (diag["overall"], norm["overall"])
    )


# ---------------------------------------------------------------------------
# DC4 -- fresh child cannot lift stale parent
# ---------------------------------------------------------------------------

def test_dc4_fresh_cannot_lift_stale():
    rows = [
        _svc("stale_svc", fresh=None, age_sec=9999.0),
        _svc("fresh_svc", fresh="fresh", age_sec=5.0),
    ]
    diag = build_diagnosis(rows, sla_sec=300.0)
    assert diag["overall"] != "ok", (
        "DC4: fresh child must not lift stale parent; got %r" % diag["overall"]
    )


# ---------------------------------------------------------------------------
# DC5 -- No $/roi/pnl/profit key anywhere
# ---------------------------------------------------------------------------

def test_dc5_no_dollar_key():
    rows = [_svc("svc", fresh=None, age_sec=548.0)]
    diag = build_diagnosis(rows, sla_sec=300.0)
    assert not _has_bad_key(diag), "DC5: no $/roi/pnl/profit key in diagnosis"


def test_dc5_no_dollar_key_fresh():
    rows = [_svc("svc", fresh="fresh", age_sec=10.0)]
    diag = build_diagnosis(rows, sla_sec=300.0)
    assert not _has_bad_key(diag), "DC5b: no $/roi/pnl/profit key in ok diagnosis"


# ---------------------------------------------------------------------------
# DC6 -- stale-never-green: fresh=null + no ts/age -> problems[], never ok
# ---------------------------------------------------------------------------

def test_dc6_stale_never_green_missing_source():
    svc = _svc("m1_producer", fresh=None, age_sec=None)
    # no source_ts, no generated_at, no age -> missing source -> stale
    diag = build_diagnosis([svc], sla_sec=300.0)
    assert "m1_producer" not in diag["ok_services"], (
        "DC6: missing source -> never in ok_services"
    )
    assert diag["overall"] in ("degraded", "down"), (
        "DC6: missing source -> degraded/down"
    )


# ---------------------------------------------------------------------------
# DC7 -- down row (live=False or breaker=OPEN) -> overall 'down'
# ---------------------------------------------------------------------------

def test_dc7_live_false_is_down():
    svc = _svc("m1_producer", fresh="fresh", live=False, critical=True)
    diag = build_diagnosis([svc], sla_sec=300.0)
    assert diag["overall"] == "down", (
        "DC7: live=False -> overall 'down'; got %r" % diag["overall"]
    )
    assert any(p["service"] == "m1_producer" for p in diag["problems"]), (
        "DC7: live=False must appear in problems"
    )


def test_dc7_breaker_open_is_down():
    svc = _svc("m1_producer", fresh="fresh", breaker="OPEN")
    diag = build_diagnosis([svc], sla_sec=300.0)
    assert diag["overall"] == "down", (
        "DC7b: breaker=OPEN -> overall 'down'; got %r" % diag["overall"]
    )


# ---------------------------------------------------------------------------
# DC8 -- critical + stale -> problems[].severity == 'critical'
# ---------------------------------------------------------------------------

def test_dc8_critical_stale_is_critical_severity():
    svc = _svc("m1_producer", fresh=None, age_sec=9000.0, critical=True)
    diag = build_diagnosis([svc], sla_sec=300.0)
    crit_problems = [p for p in diag["problems"] if p["service"] == "m1_producer"]
    assert crit_problems, "DC8: m1_producer must be in problems"
    assert crit_problems[0]["severity"] == "critical", (
        "DC8: critical service -> problems[].severity='critical'; got %r"
        % crit_problems[0]["severity"]
    )


# ---------------------------------------------------------------------------
# DC9 -- build_diagnosis() NEVER raises on garbage input
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_input", [
    None,
    [],
    [{}],
    [{"fresh": object()}],
    [{"fresh": None, "age_sec": "not-a-number"}],
    [{"name": None, "fresh": None, "critical": "yes"}],
    "not a list",
    42,
])
def test_dc9_never_raises_on_garbage(bad_input):
    try:
        diag = build_diagnosis(bad_input)  # type: ignore[arg-type]
        # Must always return a dict with 'overall'.
        assert isinstance(diag, dict), "DC9: must return a dict"
        assert "overall" in diag, "DC9: must have 'overall' key"
        assert diag["overall"] in ("ok", "degraded", "down"), (
            "DC9: overall must be ok/degraded/down; got %r" % diag["overall"]
        )
    except Exception as exc:
        pytest.fail("DC9: build_diagnosis raised on input %r: %s" % (bad_input, exc))


# ---------------------------------------------------------------------------
# DC10 -- ok_services has only fresh services; problems has the rest
# ---------------------------------------------------------------------------

def test_dc10_ok_services_only_fresh():
    rows = [
        _svc("fresh_one", fresh="fresh", age_sec=10.0),
        _svc("stale_one", fresh=None, age_sec=9999.0),
        _svc("down_one", fresh="down"),
    ]
    diag = build_diagnosis(rows, sla_sec=300.0)
    assert "fresh_one" in diag["ok_services"], "DC10: fresh service in ok_services"
    problem_names = {p["service"] for p in diag["problems"]}
    assert "stale_one" in problem_names, "DC10: stale service in problems"
    assert "down_one" in problem_names, "DC10: down service in problems"
    assert "stale_one" not in diag["ok_services"], "DC10: stale not in ok_services"
    assert "down_one" not in diag["ok_services"], "DC10: down not in ok_services"


# ---------------------------------------------------------------------------
# DC11 -- edge_claimed=False, honest_note present, no $ key
# ---------------------------------------------------------------------------

def test_dc11_edge_claimed_and_honest_note():
    diag = build_diagnosis([_svc("svc", fresh=None, age_sec=548.0)], sla_sec=300.0)
    assert diag.get("edge_claimed") is False, "DC11: edge_claimed must be False"
    assert "honest_note" in diag, "DC11: honest_note must be present"
    assert diag["honest_note"], "DC11: honest_note must be non-empty"
    assert not _has_bad_key(diag), "DC11: no $/roi/pnl/profit key"


# ---------------------------------------------------------------------------
# DC12 -- empty services list -> degraded/down (never ok)
# ---------------------------------------------------------------------------

def test_dc12_empty_services_not_ok():
    diag = build_diagnosis([], sla_sec=300.0)
    assert diag["overall"] in ("degraded", "down"), (
        "DC12: empty services -> degraded/down; got %r" % diag["overall"]
    )
    assert diag["overall"] != "ok", "DC12: empty services must never be ok"
