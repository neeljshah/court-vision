"""tests.platformkit.test_ops_staleness_normalizer -- per-file acceptance test.

Acceptance criteria (BE-G-ops-face-consistency):

  AC1. Critical service with fresh=null and age_sec > SLA -> normalized to
       'degraded' / DEGRADED (never ok).
  AC2. HEARTBEAT service with live=True and age_sec > SLA -> DEGRADED
       (heartbeat age IS the freshness signal; past-SLA heartbeat = stale).
  AC3. HEARTBEAT service with live=True and age_sec=None (never written) -> DEGRADED
       (null age on heartbeat-only service is treated as stale, never ok).
  AC4. A genuinely fresh service (fresh='fresh', age<SLA, live=True) -> ok.
  AC5. live=False -> DOWN regardless of fresh/age.
  AC6. breaker='OPEN' -> DOWN regardless of fresh.
  AC7. PORT-probed service with live=True and age_sec>SLA -> ok
       (age alone does NOT demote a PORT service; fresh=live-probe).
  AC8. PORT-probed service with live=False -> DOWN (liveness gate still fires).
  AC9. faces_agree(ok, ok)      -> True.
       faces_agree(ok, degraded) -> False.
       faces_agree(degraded, down) -> False.
  AC10. check_face_pair returns all_agree=False when two faces disagree on any
        service; mismatches list contains the offending service name.
  AC11. check_face_pair returns all_agree=True when both faces agree on all
        common services.
  AC12. No $ field / edge_claimed in any output; ASCII only.
  AC13. normalize_service_severity never raises on garbage inputs.
  AC14. Non-critical service with fresh=None, no age -> DEGRADED (missing=stale).

Run (per-file only -- never the full suite, it freezes the box):
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_ops_staleness_normalizer.py -q
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

# ---------------------------------------------------------------------------
# Ensure repo root on sys.path.
# ---------------------------------------------------------------------------
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from predict_service.ops_staleness_normalizer import (  # noqa: E402
    DEGRADED,
    DOWN,
    HONEST_NOTE,
    OK,
    check_face_pair,
    faces_agree,
    normalize_service_severity,
)

SLA = 300.0


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------

def _row(
    name: str = "m1_producer",
    *,
    critical: bool = True,
    live: Any = True,
    fresh: Any = None,
    age_sec: Any = None,
    breaker: Any = None,
) -> Dict[str, Any]:
    r: Dict[str, Any] = {"name": name, "critical": critical, "live": live, "fresh": fresh}
    if age_sec is not None:
        r["age_sec"] = age_sec
    if breaker is not None:
        r["breaker"] = breaker
    return r


# ---------------------------------------------------------------------------
# AC1: Critical service, fresh=null, age_sec > SLA -> DEGRADED (never ok).
# ---------------------------------------------------------------------------

class TestCriticalFreshNullPastSla:

    def test_critical_fresh_null_age_past_sla_is_degraded(self):
        """AC1: Critical, fresh=null, age_sec=560, SLA=300 -> DEGRADED (not ok)."""
        row = _row("m1_producer", critical=True, live=True, fresh=None, age_sec=560.0)
        sev = normalize_service_severity(row, sla_sec=SLA)
        assert sev == DEGRADED, (
            "AC1: critical fresh=null age>SLA must be DEGRADED; got %r" % sev
        )
        assert sev != OK

    def test_critical_fresh_null_no_age_is_degraded(self):
        """AC1 variant: no age_sec either -> DEGRADED (missing=stale for critical)."""
        row = _row("m1_producer", critical=True, live=True, fresh=None)
        sev = normalize_service_severity(row, sla_sec=SLA)
        assert sev in (DEGRADED, DOWN), (
            "AC1: critical fresh=null no-age must be DEGRADED/DOWN; got %r" % sev
        )
        assert sev != OK


# ---------------------------------------------------------------------------
# AC2: HEARTBEAT service, live=True, age_sec > SLA -> DEGRADED.
# ---------------------------------------------------------------------------

class TestHeartbeatPastSla:

    def test_heartbeat_live_true_age_past_sla_is_degraded(self):
        """AC2: HEARTBEAT live=True age_sec=560 SLA=300 -> DEGRADED."""
        row = _row("m1_producer", critical=False, live=True, fresh=None, age_sec=560.0)
        sev = normalize_service_severity(row, sla_sec=SLA, readiness_kind="HEARTBEAT")
        assert sev == DEGRADED, (
            "AC2: HEARTBEAT live=True age>SLA must be DEGRADED; got %r" % sev
        )

    def test_heartbeat_live_true_age_exactly_sla_is_degraded(self):
        """Boundary: age_sec == SLA -> DEGRADED (strictly-less required for fresh)."""
        row = _row("svc", critical=False, live=True, fresh=None, age_sec=SLA)
        sev = normalize_service_severity(row, sla_sec=SLA, readiness_kind="HEARTBEAT")
        assert sev == DEGRADED, (
            "AC2 boundary: HEARTBEAT age==SLA must be DEGRADED; got %r" % sev
        )


# ---------------------------------------------------------------------------
# AC3: HEARTBEAT service, live=True, age_sec=None -> DEGRADED.
# ---------------------------------------------------------------------------

class TestHeartbeatNullAge:

    def test_heartbeat_live_true_null_age_is_degraded(self):
        """AC3: HEARTBEAT live=True age_sec=None (never written) -> DEGRADED."""
        row = _row("m1_producer", critical=False, live=True, fresh=None)
        # No age_sec key at all.
        sev = normalize_service_severity(row, sla_sec=SLA, readiness_kind="HEARTBEAT")
        assert sev in (DEGRADED, DOWN), (
            "AC3: HEARTBEAT live=True null-age must be DEGRADED/DOWN; got %r" % sev
        )
        assert sev != OK


# ---------------------------------------------------------------------------
# AC4: Genuinely fresh service -> ok.
# ---------------------------------------------------------------------------

class TestGenuinelyFresh:

    def test_fresh_service_is_ok(self):
        """AC4: fresh='fresh', age<SLA, live=True -> ok."""
        row = _row("predict_service", critical=False, live=True, fresh="fresh", age_sec=30.0)
        sev = normalize_service_severity(row, sla_sec=SLA, readiness_kind="HEARTBEAT")
        assert sev == OK, "AC4: genuinely fresh service must be ok; got %r" % sev

    def test_fresh_service_critical_is_ok(self):
        """AC4: critical=True fresh='fresh', age<SLA, live=True -> ok."""
        row = _row("m1_producer", critical=True, live=True, fresh="fresh", age_sec=50.0)
        sev = normalize_service_severity(row, sla_sec=SLA, readiness_kind="HEARTBEAT")
        assert sev == OK, "AC4: critical genuinely fresh must be ok; got %r" % sev

    def test_fresh_service_port_is_ok(self):
        """AC4: PORT fresh='fresh', live=True -> ok (no age check)."""
        row = _row("api_port", critical=False, live=True, fresh="fresh")
        sev = normalize_service_severity(row, sla_sec=SLA, readiness_kind="PORT")
        assert sev == OK, "AC4: PORT fresh service must be ok; got %r" % sev


# ---------------------------------------------------------------------------
# AC5: live=False -> DOWN.
# ---------------------------------------------------------------------------

class TestLiveFalseIsDown:

    def test_live_false_heartbeat_is_down(self):
        """AC5: HEARTBEAT live=False -> DOWN."""
        row = _row("m1_producer", critical=True, live=False, fresh="fresh", age_sec=5.0)
        sev = normalize_service_severity(row, sla_sec=SLA)
        assert sev == DOWN, "AC5: live=False must be DOWN; got %r" % sev

    def test_live_false_port_is_down(self):
        """AC5: PORT live=False -> DOWN."""
        row = _row("api_port", critical=False, live=False, fresh="fresh", age_sec=5.0)
        sev = normalize_service_severity(row, sla_sec=SLA, readiness_kind="PORT")
        assert sev == DOWN, "AC5: PORT live=False must be DOWN; got %r" % sev


# ---------------------------------------------------------------------------
# AC6: breaker='OPEN' -> DOWN.
# ---------------------------------------------------------------------------

class TestBreakerOpen:

    def test_breaker_open_is_down(self):
        """AC6: breaker='OPEN' -> DOWN regardless of fresh."""
        row = _row("m1_producer", critical=False, live=True, fresh="fresh", age_sec=5.0,
                   breaker="OPEN")
        sev = normalize_service_severity(row, sla_sec=SLA)
        assert sev == DOWN, "AC6: breaker=OPEN must be DOWN; got %r" % sev


# ---------------------------------------------------------------------------
# AC7: PORT service with live=True and old age -> ok (age not punitive).
# ---------------------------------------------------------------------------

class TestPortServiceAgeNotPunitive:

    def test_port_live_true_age_past_sla_is_ok(self):
        """AC7: PORT live=True age_sec>SLA -> ok (age alone does not demote PORT)."""
        row = {
            "name": "api_port",
            "critical": False,
            "live": True,
            "fresh": "fresh",  # probe said fresh
            "age_sec": 9999.0,
        }
        sev = normalize_service_severity(row, sla_sec=SLA, readiness_kind="PORT")
        assert sev == OK, (
            "AC7: PORT service with fresh='fresh' must be ok even with old age; got %r" % sev
        )


# ---------------------------------------------------------------------------
# AC8: PORT service with live=False -> DOWN.
# ---------------------------------------------------------------------------

class TestPortServiceDown:

    def test_port_live_false_is_down(self):
        """AC8: PORT live=False -> DOWN (liveness gate fires for all kinds)."""
        row = {"name": "api_port", "critical": False, "live": False, "fresh": "fresh"}
        sev = normalize_service_severity(row, sla_sec=SLA, readiness_kind="PORT")
        assert sev == DOWN, "AC8: PORT live=False must be DOWN; got %r" % sev


# ---------------------------------------------------------------------------
# AC9: faces_agree correctness.
# ---------------------------------------------------------------------------

class TestFacesAgree:

    def test_same_verdicts_agree(self):
        assert faces_agree(OK, OK) is True
        assert faces_agree(DEGRADED, DEGRADED) is True
        assert faces_agree(DOWN, DOWN) is True

    def test_ok_vs_degraded_disagree(self):
        assert faces_agree(OK, DEGRADED) is False

    def test_ok_vs_down_disagree(self):
        assert faces_agree(OK, DOWN) is False

    def test_degraded_vs_down_disagree(self):
        assert faces_agree(DEGRADED, DOWN) is False

    def test_none_vs_ok_disagree(self):
        """None verdict treated as DEGRADED for comparison -> disagrees with ok."""
        assert faces_agree(None, OK) is False

    def test_none_vs_degraded_agree(self):
        """None treated as DEGRADED -> agrees with explicit DEGRADED."""
        assert faces_agree(None, DEGRADED) is True


# ---------------------------------------------------------------------------
# AC10: check_face_pair flags mismatch when faces disagree.
# ---------------------------------------------------------------------------

class TestCheckFacePairDisagrees:

    def test_ok_vs_down_flagged(self):
        """AC10: one face ok, other down -> all_agree=False, service in mismatches."""
        face_a = {"m1_producer": OK, "sidecar": OK}
        face_b = {"m1_producer": DOWN, "sidecar": OK}
        report = check_face_pair(face_a, face_b)
        assert report["all_agree"] is False
        assert report["n_mismatches"] == 1
        mismatch_services = [m["service"] for m in report["mismatches"]]
        assert "m1_producer" in mismatch_services

    def test_ok_vs_degraded_flagged(self):
        """AC10: gap=1 (ok vs degraded) is still flagged."""
        face_a = {"svc": OK}
        face_b = {"svc": DEGRADED}
        report = check_face_pair(face_a, face_b)
        assert report["all_agree"] is False
        assert report["n_mismatches"] == 1
        assert report["mismatches"][0]["gap"] == 1

    def test_mismatch_sorted_worst_first(self):
        """Worst-gap mismatch appears first in the list."""
        face_a = {"svc_big": OK,   "svc_small": OK}
        face_b = {"svc_big": DOWN, "svc_small": DEGRADED}
        report = check_face_pair(face_a, face_b)
        assert len(report["mismatches"]) == 2
        assert report["mismatches"][0]["service"] == "svc_big"  # gap=2
        assert report["mismatches"][1]["service"] == "svc_small"  # gap=1


# ---------------------------------------------------------------------------
# AC11: check_face_pair returns all_agree=True when both faces match.
# ---------------------------------------------------------------------------

class TestCheckFacePairAgrees:

    def test_identical_faces_agree(self):
        """AC11: all services match -> all_agree=True, mismatches=[]."""
        face_a = {"svc_a": OK, "svc_b": DEGRADED, "svc_c": DOWN}
        face_b = {"svc_a": OK, "svc_b": DEGRADED, "svc_c": DOWN}
        report = check_face_pair(face_a, face_b)
        assert report["all_agree"] is True
        assert report["mismatches"] == []
        assert report["n_mismatches"] == 0

    def test_no_common_services_agree(self):
        """Services in only one face cannot be compared -> all_agree=True."""
        face_a = {"svc_only_a": OK}
        face_b = {"svc_only_b": DOWN}
        report = check_face_pair(face_a, face_b)
        assert report["all_agree"] is True
        assert report["n_services"] == 0  # no common services


# ---------------------------------------------------------------------------
# AC12: No $ field / edge_claimed in any output.
# ---------------------------------------------------------------------------

class TestNoDollarField:

    def test_normalize_no_dollar(self):
        row = _row("m1_producer", critical=True, live=True, fresh=None, age_sec=SLA + 1.0)
        sev = normalize_service_severity(row, sla_sec=SLA)
        assert "$" not in sev, "AC12: no $ in severity string"

    def test_check_face_pair_edge_claimed_false(self):
        report = check_face_pair({"svc": OK}, {"svc": DOWN})
        assert report.get("edge_claimed") is False

    def test_check_face_pair_no_dollar_key(self):
        report = check_face_pair({"svc": OK}, {"svc": DOWN})
        report_str = str(report)
        assert not re.search(r"\$\s*\d", report_str), (
            "AC12: no $ adjacent to digit in report"
        )

    def test_honest_note_present(self):
        report = check_face_pair({"svc": OK}, {"svc": DOWN})
        assert "honest_note" in report
        assert report["honest_note"]


# ---------------------------------------------------------------------------
# AC13: normalize_service_severity never raises on garbage inputs.
# ---------------------------------------------------------------------------

class TestNeverRaises:

    @pytest.mark.parametrize("bad_input", [
        None, 42, "string", [], object(), {}, {"fresh": object()},
    ])
    def test_never_raises_on_garbage(self, bad_input):
        try:
            result = normalize_service_severity(bad_input)  # type: ignore[arg-type]
            assert result in (OK, DEGRADED, DOWN), (
                "must return a valid severity; got %r" % result
            )
        except Exception as exc:
            pytest.fail("normalize_service_severity raised on %r: %s" % (bad_input, exc))

    @pytest.mark.parametrize("bad_input", [None, 42, "string", object()])
    def test_check_face_pair_never_raises_on_garbage(self, bad_input):
        try:
            result = check_face_pair(bad_input, bad_input)  # type: ignore[arg-type]
            assert isinstance(result, dict)
        except Exception as exc:
            pytest.fail("check_face_pair raised on %r: %s" % (bad_input, exc))

    def test_faces_agree_never_raises_on_garbage(self):
        for a, b in [(None, None), (42, "ok"), (object(), DOWN)]:
            try:
                faces_agree(a, b)  # type: ignore[arg-type]
            except Exception as exc:
                pytest.fail("faces_agree raised on (%r, %r): %s" % (a, b, exc))


# ---------------------------------------------------------------------------
# AC14: Non-critical, fresh=None, no age -> DEGRADED (missing=stale).
# ---------------------------------------------------------------------------

class TestNonCriticalMissingIsStale:

    def test_non_critical_null_fresh_null_age_is_degraded(self):
        """AC14: non-critical, fresh=None, no age -> DEGRADED (missing=stale)."""
        row = {"name": "background_svc", "critical": False, "live": True, "fresh": None}
        sev = normalize_service_severity(row, sla_sec=SLA)
        assert sev == DEGRADED, (
            "AC14: non-critical null-fresh no-age must be DEGRADED; got %r" % sev
        )
