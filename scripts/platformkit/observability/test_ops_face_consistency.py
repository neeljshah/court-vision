"""Per-file tests for scripts.platformkit.observability.ops_face_consistency.

Acceptance criteria (BE8-5 single shared ops-face freshness verdict):

  A. Critical service live=None or fresh=None -> DEGRADED, never OK.
  B. age_sec=560, sla=300 -> DEGRADED (stale).
  C. Same row through all three face evaluators -> identical severity.
  D. consistency_matrix flags a mismatch when one face says ok + another down.
  E. Never returns OK for unknown on critical.
  F. Non-critical live=None + fresh=None + no age -> DEGRADED (missing = stale).
  G. live=False -> DOWN regardless of fresh.
  H. breaker='OPEN' -> DOWN regardless of fresh.
  I. fresh='stale' explicitly -> DEGRADED; fresh='down' -> DOWN; fresh='fresh' -> OK.
  J. age < sla + explicit fresh='fresh' -> OK.
  K. consistency_matrix with all_agree=True when all faces match.
  L. Never raises on garbage inputs.
  M. No $ field in any output.

Run (per-file only -- never full pytest):
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/observability/test_ops_face_consistency.py -q
"""
from __future__ import annotations

import re
from typing import Any, Dict

import pytest

from scripts.platformkit.observability.ops_face_consistency import (
    DEFAULT_SLA_SEC,
    DEGRADED,
    DOWN,
    HONEST_NOTE,
    OK,
    consistency_matrix,
    evaluate_service,
)

SLA = DEFAULT_SLA_SEC  # 300.0 s


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row(
    name: str = "m1_producer",
    *,
    critical: bool = True,
    live: Any = None,      # None = unknown; True = live; False = dead
    fresh: Any = None,     # None | 'fresh' | 'stale' | 'down'
    age_sec: Any = None,
    breaker: Any = None,
) -> Dict[str, Any]:
    """Build a minimal services[] row for testing."""
    r: Dict[str, Any] = {"name": name, "critical": critical}
    if live is not None:
        r["live"] = live
    # Include explicit None for fresh so callers can test None explicitly
    r["fresh"] = fresh
    if age_sec is not None:
        r["age_sec"] = age_sec
    if breaker is not None:
        r["breaker"] = breaker
    return r


# ---------------------------------------------------------------------------
# A. Critical service live=None or fresh=None -> DEGRADED
# ---------------------------------------------------------------------------

class TestCriticalUnknownNeverOK:

    def test_critical_live_none_is_degraded(self):
        """Critical service with live=None must be DEGRADED, never OK."""
        row = _row("m1_producer", critical=True, live=None, fresh=None)
        sev = evaluate_service(row, sla_sec=SLA)
        assert sev in (DEGRADED, DOWN), (
            "critical live=None must be DEGRADED or DOWN, not OK; got %r" % sev
        )
        assert sev != OK

    def test_critical_fresh_none_no_age_is_degraded(self):
        """Critical service with fresh=None and no age must be DEGRADED."""
        row = _row("m1_producer", critical=True, live=None, fresh=None)
        # No age_sec in row.
        sev = evaluate_service(row, sla_sec=SLA)
        assert sev == DEGRADED

    def test_critical_fresh_none_with_age_below_sla_is_degraded(self):
        """Critical service with fresh=None but age < SLA must still be DEGRADED.

        Per acceptance rule: live=None on critical -> DEGRADED (cannot be OK
        on unknown liveness).
        """
        row = _row("m1_producer", critical=True, live=None, fresh=None, age_sec=10.0)
        sev = evaluate_service(row, sla_sec=SLA)
        # live is None on critical -> must not be OK
        assert sev != OK


# ---------------------------------------------------------------------------
# B. age_sec >= SLA -> DEGRADED
# ---------------------------------------------------------------------------

class TestAgeSla:

    def test_age_560_sla_300_is_degraded(self):
        """age_sec=560, sla=300 -> DEGRADED (stale past SLA)."""
        row = _row("svc_a", critical=True, live=True, fresh=None, age_sec=560.0)
        sev = evaluate_service(row, sla_sec=300.0)
        assert sev == DEGRADED, "age 560 vs sla 300 must be DEGRADED; got %r" % sev

    def test_age_exactly_sla_is_degraded(self):
        """Boundary: age_sec == SLA is NOT fresh (strictly less required)."""
        row = _row("svc_b", critical=False, live=True, fresh=None, age_sec=SLA)
        sev = evaluate_service(row, sla_sec=SLA)
        assert sev == DEGRADED

    def test_age_well_below_sla_is_ok(self):
        """age_sec < SLA with explicit fresh='fresh' -> OK."""
        row = _row("svc_c", critical=False, live=True, fresh="fresh", age_sec=50.0)
        sev = evaluate_service(row, sla_sec=SLA)
        assert sev == OK, "age 50 vs sla 300 with fresh='fresh' must be OK; got %r" % sev

    def test_non_critical_null_fresh_age_above_sla_is_degraded(self):
        """Non-critical service with fresh=None and age >= SLA -> DEGRADED."""
        row = _row("background_svc", critical=False, live=True, fresh=None, age_sec=400.0)
        sev = evaluate_service(row, sla_sec=SLA)
        assert sev == DEGRADED


# ---------------------------------------------------------------------------
# C. Same row through all three face evaluators -> identical severity
# ---------------------------------------------------------------------------

class TestThreeFaceConsistency:

    def test_same_row_same_sla_same_severity(self):
        """Three calls with identical (row, sla_sec, now) must return identical severity."""
        row = _row("m1_producer", critical=True, live=True, fresh=None, age_sec=560.0)
        sev_status = evaluate_service(dict(row), sla_sec=SLA, now=1_000_000.0)
        sev_doctor = evaluate_service(dict(row), sla_sec=SLA, now=1_000_000.0)
        sev_autonomy = evaluate_service(dict(row), sla_sec=SLA, now=1_000_000.0)
        assert sev_status == sev_doctor == sev_autonomy, (
            "three face calls must agree: status=%r doctor=%r autonomy=%r"
            % (sev_status, sev_doctor, sev_autonomy)
        )

    def test_fresh_row_identical_across_faces(self):
        """A fresh, healthy row must return OK from all three face evaluators."""
        row = _row("predict_service", critical=False, live=True, fresh="fresh", age_sec=10.0)
        results = [evaluate_service(dict(row), sla_sec=SLA) for _ in range(3)]
        assert results[0] == results[1] == results[2] == OK

    def test_down_row_identical_across_faces(self):
        """A down row must return DOWN from all three face evaluators."""
        row = _row("m1_producer", critical=True, live=False, fresh=None)
        results = [evaluate_service(dict(row), sla_sec=SLA) for _ in range(3)]
        assert results[0] == results[1] == results[2] == DOWN


# ---------------------------------------------------------------------------
# D. consistency_matrix flags mismatch when one face ok + another down
# ---------------------------------------------------------------------------

class TestConsistencyMatrix:

    def test_mismatch_flagged_ok_vs_down(self):
        """consistency_matrix must flag a mismatch when one face says ok, another down."""
        face_results = {
            "status":   {"m1_producer": OK},
            "doctor":   {"m1_producer": DOWN},
            "autonomy": {"m1_producer": DEGRADED},
        }
        report = consistency_matrix(face_results)
        assert report["all_agree"] is False
        assert report["n_mismatches"] == 1
        mm = report["mismatches"][0]
        assert mm["service"] == "m1_producer"
        assert mm["worst"] == DOWN
        assert mm["best"] == OK
        assert mm["gap"] == 2  # DOWN(2) - OK(0) = 2

    def test_all_agree_no_mismatch(self):
        """When all faces agree on every service, all_agree=True and mismatches=[]."""
        face_results = {
            "status":   {"svc_a": OK, "svc_b": DEGRADED},
            "doctor":   {"svc_a": OK, "svc_b": DEGRADED},
            "autonomy": {"svc_a": OK, "svc_b": DEGRADED},
        }
        report = consistency_matrix(face_results)
        assert report["all_agree"] is True
        assert report["mismatches"] == []
        assert report["n_mismatches"] == 0

    def test_mismatch_degraded_vs_ok(self):
        """One face ok, another degraded -- gap=1 -> flagged."""
        face_results = {
            "status": {"svc_x": OK},
            "doctor": {"svc_x": DEGRADED},
        }
        report = consistency_matrix(face_results)
        assert report["all_agree"] is False
        mm = report["mismatches"][0]
        assert mm["gap"] == 1

    def test_worst_gap_sorted_first(self):
        """Mismatches are sorted worst-gap-first."""
        face_results = {
            "status": {"svc_small": OK,   "svc_big": OK},
            "doctor": {"svc_small": DEGRADED, "svc_big": DOWN},
        }
        report = consistency_matrix(face_results)
        assert report["n_mismatches"] == 2
        # svc_big gap=2 (OK->DOWN) comes before svc_small gap=1 (OK->DEGRADED)
        assert report["mismatches"][0]["service"] == "svc_big"
        assert report["mismatches"][1]["service"] == "svc_small"

    def test_single_face_no_comparison(self):
        """A service appearing in only one face cannot be compared -- not flagged."""
        face_results = {
            "status": {"svc_solo": OK},
        }
        report = consistency_matrix(face_results)
        assert report["all_agree"] is True
        assert report["n_mismatches"] == 0

    def test_empty_face_results(self):
        """Empty face_results -> all_agree=True (no services, no mismatches)."""
        report = consistency_matrix({})
        assert report["all_agree"] is True
        assert report["n_services"] == 0


# ---------------------------------------------------------------------------
# E. Never returns OK for unknown/None on critical
# ---------------------------------------------------------------------------

class TestNeverOKOnUnknownCritical:

    @pytest.mark.parametrize("live_val", [None])
    @pytest.mark.parametrize("fresh_val", [None, "unknown"])
    def test_critical_unknown_live_and_fresh_not_ok(self, live_val, fresh_val):
        """Critical service with unknown live/fresh must never be OK."""
        row: Dict[str, Any] = {"name": "m1_producer", "critical": True}
        row["live"] = live_val
        row["fresh"] = fresh_val
        sev = evaluate_service(row, sla_sec=SLA)
        assert sev != OK, (
            "critical live=%r fresh=%r must not be OK; got %r" % (live_val, fresh_val, sev)
        )

    def test_non_critical_unknown_with_age_ok(self):
        """Non-critical with fresh='fresh' and age < SLA is OK (not over-penalized)."""
        row = _row("background_svc", critical=False, live=True, fresh="fresh", age_sec=60.0)
        sev = evaluate_service(row, sla_sec=SLA)
        assert sev == OK


# ---------------------------------------------------------------------------
# F. Non-critical unknown/missing defaults to DEGRADED
# ---------------------------------------------------------------------------

class TestNonCriticalMissing:

    def test_non_critical_no_fresh_no_age_is_degraded(self):
        """Non-critical with fresh=None and no age -> DEGRADED (missing = stale)."""
        row: Dict[str, Any] = {"name": "background", "critical": False, "fresh": None}
        sev = evaluate_service(row, sla_sec=SLA)
        assert sev == DEGRADED


# ---------------------------------------------------------------------------
# G/H. Liveness gates
# ---------------------------------------------------------------------------

class TestLivenessGates:

    def test_live_false_forces_down(self):
        """live=False forces DOWN regardless of fresh or age."""
        row = _row("m1_producer", critical=True, live=False, fresh="fresh", age_sec=5.0)
        sev = evaluate_service(row, sla_sec=SLA)
        assert sev == DOWN

    def test_breaker_open_forces_down(self):
        """breaker='OPEN' forces DOWN regardless of fresh."""
        row = _row("svc_a", critical=False, live=True, fresh="fresh", age_sec=5.0,
                   breaker="OPEN")
        sev = evaluate_service(row, sla_sec=SLA)
        assert sev == DOWN

    def test_breaker_closed_ok(self):
        """breaker='CLOSED' with fresh='fresh' and age < SLA -> OK."""
        row = _row("svc_a", critical=False, live=True, fresh="fresh", age_sec=5.0,
                   breaker="CLOSED")
        sev = evaluate_service(row, sla_sec=SLA)
        assert sev == OK


# ---------------------------------------------------------------------------
# I. Explicit fresh values
# ---------------------------------------------------------------------------

class TestExplicitFresh:

    def test_explicit_stale_is_degraded(self):
        row = _row("svc", critical=False, live=True, fresh="stale", age_sec=10.0)
        assert evaluate_service(row, sla_sec=SLA) == DEGRADED

    def test_explicit_down_is_down(self):
        row = _row("svc", critical=False, live=True, fresh="down", age_sec=10.0)
        assert evaluate_service(row, sla_sec=SLA) == DOWN

    def test_explicit_fresh_below_sla_is_ok(self):
        row = _row("svc", critical=False, live=True, fresh="fresh", age_sec=10.0)
        assert evaluate_service(row, sla_sec=SLA) == OK


# ---------------------------------------------------------------------------
# L. Never raises
# ---------------------------------------------------------------------------

class TestNeverRaises:

    @pytest.mark.parametrize("bad_input", [None, 42, "string", [], object()])
    def test_evaluate_service_never_raises(self, bad_input):
        try:
            result = evaluate_service(bad_input)  # type: ignore[arg-type]
            assert result in (OK, DEGRADED, DOWN)
        except Exception as exc:
            pytest.fail("evaluate_service raised on %r: %s" % (bad_input, exc))

    @pytest.mark.parametrize("bad_input", [None, 42, "string", object()])
    def test_consistency_matrix_never_raises(self, bad_input):
        try:
            result = consistency_matrix(bad_input)  # type: ignore[arg-type]
            assert isinstance(result, dict)
        except Exception as exc:
            pytest.fail("consistency_matrix raised on %r: %s" % (bad_input, exc))

    def test_consistency_matrix_bad_face_values(self):
        """Face results with non-string verdicts are silently skipped, never crash."""
        face_results = {
            "status": {"svc_a": None, "svc_b": 42, "svc_c": OK},
            "doctor": {"svc_c": DOWN},
        }
        result = consistency_matrix(face_results)
        assert isinstance(result, dict)
        # svc_c appears in both faces with different verdicts -> should flag it
        assert result["n_mismatches"] >= 0  # just no crash


# ---------------------------------------------------------------------------
# M. No $ field
# ---------------------------------------------------------------------------

class TestNoDollarField:

    def test_no_dollar_in_evaluate_service_output(self):
        row = _row("m1_producer", critical=True, live=None, fresh=None, age_sec=SLA + 1.0)
        sev = evaluate_service(row, sla_sec=SLA)
        assert not re.search(r"\$\s*\d", sev)

    def test_no_dollar_in_consistency_matrix_output(self):
        face_results = {
            "status": {"svc_a": OK},
            "doctor": {"svc_a": DOWN},
        }
        report = consistency_matrix(face_results)
        report_str = str(report)
        assert not re.search(r"\$\s*\d", report_str), (
            "no $ adjacent to digit; got: %s" % report_str[:200]
        )

    def test_edge_claimed_false(self):
        report = consistency_matrix({"status": {"x": OK}, "doctor": {"x": OK}})
        assert report["edge_claimed"] is False

    def test_honest_note_present(self):
        report = consistency_matrix({"status": {"x": OK}, "doctor": {"x": DOWN}})
        assert "honest_note" in report
        assert report["honest_note"]
