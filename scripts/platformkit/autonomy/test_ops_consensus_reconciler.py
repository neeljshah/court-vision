"""Per-file tests for scripts.platformkit.autonomy.ops_consensus_reconciler.

Acceptance criteria (R6-4 ops-consensus-reconciler):
  (A) m1_producer fresh=null age_sec >= SLA_sec -> consensus 'stale' -> DEGRADED.
  (B) fresh child cannot lift a stale parent (monotone-down rollup).
  (C) Two views given identical input rows -> identical per-service verdict.
  (D) No $ field anywhere in the output.
  (E) Never raises (garbage inputs, None, empty list, non-dict rows).
  (F) fresh=null age_sec < SLA_sec -> consensus 'fresh' -> OK.
  (G) fresh=null + no age_sec + no timestamp -> consensus 'stale' -> DEGRADED.
  (H) fresh='stale' -> DEGRADED; fresh='down' -> DOWN; fresh='fresh' -> OK.
  (I) overall is WORST consensus severity across all rows (monotone-down).
  (J) evaluate_row and reconcile are consistent on the same row.
  (K) empty rows list -> overall DEGRADED (never green on absent data).
  (L) live=False forces DOWN regardless of fresh.
  (M) breaker='OPEN' forces DOWN regardless of fresh.

Run (per-file only -- never full pytest):
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autonomy/test_ops_consensus_reconciler.py -q
"""
from __future__ import annotations

import re
import time

import pytest

from scripts.platformkit.autonomy.ops_consensus_reconciler import (
    DEFAULT_SLA_SEC,
    DEGRADED,
    DOWN,
    HONEST_NOTE,
    OK,
    evaluate_row,
    reconcile,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row(
    name: str = "m1_producer",
    fresh=None,
    age_sec=None,
    live=None,
    breaker=None,
    critical: bool = True,
) -> dict:
    """Build a minimal services[] row for testing."""
    r: dict = {"name": name, "critical": critical}
    if fresh is not None:
        r["fresh"] = fresh
    if age_sec is not None:
        r["age_sec"] = age_sec
    if live is not None:
        r["live"] = live
    if breaker is not None:
        r["breaker"] = breaker
    return r


SLA = DEFAULT_SLA_SEC  # 300.0 s

# ---------------------------------------------------------------------------
# (A) Core QA issue: m1_producer fresh=null age_sec >= SLA -> DEGRADED
# ---------------------------------------------------------------------------

class TestNullFreshStaleness:
    def test_null_fresh_age_ge_sla_is_degraded(self):
        """The QA root cause: fresh=null age_sec>=SLA must be DEGRADED, not OK."""
        row = _row("m1_producer", fresh=None, age_sec=SLA + 1.0)
        sev = evaluate_row(row, sla_sec=SLA)
        assert sev == DEGRADED, (
            "m1_producer fresh=null age_sec>=SLA must be DEGRADED (not OK); got %r" % sev
        )

    def test_null_fresh_age_ge_sla_in_reconcile(self):
        """reconcile() must also return DEGRADED for fresh=null age_sec>=SLA."""
        rows = [_row("m1_producer", fresh=None, age_sec=SLA + 60.0)]
        doc = reconcile(rows, default_sla_sec=SLA)
        svc = doc["consensus_services"][0]
        assert svc["consensus_severity"] == DEGRADED
        assert svc["coerced_fresh"] == "stale"
        assert doc["overall"] == DEGRADED

    def test_null_fresh_well_below_sla_is_ok(self):
        """fresh=null age_sec < SLA must resolve to OK (fresh in time)."""
        row = _row("m1_producer", fresh=None, age_sec=10.0)
        sev = evaluate_row(row, sla_sec=SLA)
        assert sev == OK, "fresh=null age<SLA must be OK; got %r" % sev

    def test_null_fresh_exactly_at_sla_is_degraded(self):
        """Boundary: age_sec == SLA is NOT strictly < SLA, so -> stale -> DEGRADED."""
        row = _row("m1_producer", fresh=None, age_sec=SLA)
        sev = evaluate_row(row, sla_sec=SLA)
        assert sev == DEGRADED, "age==SLA is NOT fresh; got %r" % sev

    def test_null_fresh_no_age_no_ts_is_degraded(self):
        """fresh=null + no age_sec + no timestamp -> stale -> DEGRADED (missing=stale)."""
        row = {"name": "m1_producer", "fresh": None, "critical": True}
        sev = evaluate_row(row, sla_sec=SLA)
        assert sev == DEGRADED, "no-age null fresh must be DEGRADED; got %r" % sev

    def test_unknown_fresh_is_degraded(self):
        """fresh='unknown' is not a concrete verdict, must coerce to stale -> DEGRADED."""
        row = _row("m1_producer", age_sec=10.0)
        row["fresh"] = "unknown"
        sev = evaluate_row(row, sla_sec=SLA)
        assert sev == DEGRADED, "fresh='unknown' must be DEGRADED; got %r" % sev


# ---------------------------------------------------------------------------
# (B) Monotone-down: fresh child cannot lift a stale parent
# ---------------------------------------------------------------------------

class TestMonotoneDown:
    def test_fresh_child_cannot_lift_stale_parent(self):
        """A fresh service does NOT upgrade the overall if another is stale."""
        rows = [
            _row("m1_producer", fresh=None, age_sec=SLA + 100.0),  # stale -> DEGRADED
            _row("m2_healthy", fresh="fresh", age_sec=10.0),         # fresh -> OK
        ]
        doc = reconcile(rows, default_sla_sec=SLA)
        assert doc["overall"] == DEGRADED, (
            "fresh child must not lift stale parent; got %r" % doc["overall"]
        )

    def test_one_down_overrides_fresh(self):
        """A DOWN row dominates even when others are fresh."""
        rows = [
            _row("svc_a", fresh="fresh", age_sec=5.0),
            _row("svc_b", fresh="down", age_sec=999.0),
        ]
        doc = reconcile(rows, default_sla_sec=SLA)
        assert doc["overall"] == DOWN

    def test_two_fresh_rows_overall_ok(self):
        """When all rows are fresh, overall must be OK."""
        rows = [
            _row("svc_a", fresh="fresh", age_sec=5.0),
            _row("svc_b", fresh="fresh", age_sec=20.0),
        ]
        doc = reconcile(rows, default_sla_sec=SLA)
        assert doc["overall"] == OK

    def test_degrade_direction_only(self):
        """Severity rank can only stay same or increase across a batch."""
        rows = [
            _row("svc_a", fresh="fresh", age_sec=5.0),    # ok
            _row("svc_b", fresh=None, age_sec=SLA + 1.0), # degraded
            _row("svc_c", fresh="fresh", age_sec=2.0),    # ok
        ]
        doc = reconcile(rows, default_sla_sec=SLA)
        # At least one DEGRADED row -> overall must be DEGRADED or worse.
        from scripts.platformkit.autonomy.ops_consensus_reconciler import _RANK
        assert _RANK[doc["overall"]] >= _RANK[DEGRADED], (
            "overall must be >= DEGRADED when one row is stale; got %r" % doc["overall"]
        )


# ---------------------------------------------------------------------------
# (C) Two views, same input rows -> identical per-service verdict
# ---------------------------------------------------------------------------

class TestViewConsistency:
    def test_identical_rows_produce_identical_verdicts(self):
        """Doctor view and autonomy view fed the same rows must agree per-service."""
        rows_a = [
            _row("m1_producer", fresh=None, age_sec=SLA + 60.0),
            _row("predict_service", fresh="fresh", age_sec=10.0),
        ]
        rows_b = [
            _row("m1_producer", fresh=None, age_sec=SLA + 60.0),
            _row("predict_service", fresh="fresh", age_sec=10.0),
        ]
        doc_a = reconcile(rows_a, default_sla_sec=SLA)
        doc_b = reconcile(rows_b, default_sla_sec=SLA)

        sev_a = {r["name"]: r["consensus_severity"] for r in doc_a["consensus_services"]}
        sev_b = {r["name"]: r["consensus_severity"] for r in doc_b["consensus_services"]}
        assert sev_a == sev_b, "identical inputs must produce identical verdicts"
        assert doc_a["overall"] == doc_b["overall"]

    def test_evaluate_row_and_reconcile_agree(self):
        """evaluate_row and reconcile must return the same severity for the same row."""
        row = _row("m1_producer", fresh=None, age_sec=SLA + 1.0)
        direct_sev = evaluate_row(row, sla_sec=SLA)
        doc = reconcile([row], default_sla_sec=SLA)
        batch_sev = doc["consensus_services"][0]["consensus_severity"]
        assert direct_sev == batch_sev, (
            "evaluate_row and reconcile disagree: %r vs %r" % (direct_sev, batch_sev)
        )


# ---------------------------------------------------------------------------
# (D) No $ field
# ---------------------------------------------------------------------------

class TestNoDollarField:
    def test_no_dollar_in_evaluate_row(self):
        """evaluate_row return value (a string) must not contain $ adjacent to digit."""
        sev = evaluate_row(_row("m1_producer", fresh=None, age_sec=SLA + 1.0))
        assert not re.search(r"\$\s*\d", sev)

    def test_no_dollar_field_in_reconcile_output(self):
        """reconcile() output must not carry any $ key or $ adjacent to digit value."""
        rows = [_row("m1_producer", fresh=None, age_sec=SLA + 1.0)]
        doc = reconcile(rows)
        doc_str = str(doc)
        # No $ adjacent to a digit (honest_note text may say 'no $ field' which is ok).
        assert not re.search(r"\$\s*\d", doc_str), (
            "doc must not contain $ adjacent to digit; got fragment in: %s" % doc_str[:200]
        )
        # No top-level $ keys.
        for key in doc:
            assert "$" not in str(key), "no $ in top-level key: %r" % key

    def test_honest_note_present_and_references_no_dollar(self):
        """Output must carry honest_note referencing 'no $ field'."""
        doc = reconcile([_row("svc_a", fresh="fresh", age_sec=5.0)])
        assert "honest_note" in doc
        assert "no $ field" in doc["honest_note"], (
            "honest_note must mention 'no $ field'; got: %s" % doc["honest_note"]
        )

    def test_edge_claimed_is_false(self):
        """edge_claimed must be False (we measure calibration, not profit)."""
        doc = reconcile([_row("svc_a", fresh="fresh")])
        assert doc["edge_claimed"] is False


# ---------------------------------------------------------------------------
# (E) Never raises
# ---------------------------------------------------------------------------

class TestNeverRaises:
    @pytest.mark.parametrize("bad_input", [None, 42, "string", [], object()])
    def test_evaluate_row_never_raises(self, bad_input):
        """evaluate_row must return DEGRADED for garbage inputs, never raise."""
        try:
            result = evaluate_row(bad_input)  # type: ignore[arg-type]
            assert result in (OK, DEGRADED, DOWN)
        except Exception as exc:
            pytest.fail("evaluate_row raised on %r: %s" % (bad_input, exc))

    @pytest.mark.parametrize("bad_input", [None, 42, "string", object()])
    def test_reconcile_never_raises_on_bad_rows(self, bad_input):
        """reconcile must never raise even on malformed row list."""
        try:
            doc = reconcile(bad_input)  # type: ignore[arg-type]
            assert isinstance(doc, dict)
            assert "overall" in doc
        except Exception as exc:
            pytest.fail("reconcile raised on rows=%r: %s" % (bad_input, exc))

    def test_reconcile_non_dict_rows_handled(self):
        """Non-dict items inside the rows list are treated as stale, never crash."""
        try:
            doc = reconcile(["garbage", None, 99, _row("ok_svc", fresh="fresh")])
            assert isinstance(doc, dict)
            # overall degraded because non-dict items -> stale.
            assert doc["overall"] in (DEGRADED, DOWN)
        except Exception as exc:
            pytest.fail("reconcile raised on mixed-type rows: %s" % exc)

    def test_reconcile_empty_list_is_degraded(self):
        """Empty rows -> overall DEGRADED (never green on absent data)."""
        doc = reconcile([])
        assert doc["overall"] == DEGRADED
        assert doc["ok"] is False

    def test_reconcile_empty_sla_map_uses_default(self):
        """sla_map={} must fall back to default_sla_sec without error."""
        rows = [_row("svc_a", fresh=None, age_sec=SLA + 1.0)]
        doc = reconcile(rows, sla_map={}, default_sla_sec=SLA)
        assert doc["consensus_services"][0]["consensus_severity"] == DEGRADED


# ---------------------------------------------------------------------------
# (H) Concrete fresh values pass through correctly
# ---------------------------------------------------------------------------

class TestConcreteFreshValues:
    def test_fresh_stale_is_degraded(self):
        sev = evaluate_row(_row("svc", age_sec=SLA + 1.0), sla_sec=SLA)
        # NOTE: no explicit fresh -> null; age >= SLA -> stale -> DEGRADED
        assert sev == DEGRADED

    def test_explicit_stale_is_degraded(self):
        row = _row("svc", age_sec=10.0)
        row["fresh"] = "stale"
        sev = evaluate_row(row, sla_sec=SLA)
        assert sev == DEGRADED

    def test_explicit_down_is_down(self):
        row = _row("svc", age_sec=10.0)
        row["fresh"] = "down"
        sev = evaluate_row(row, sla_sec=SLA)
        assert sev == DOWN

    def test_explicit_fresh_is_ok(self):
        row = _row("svc", age_sec=10.0)
        row["fresh"] = "fresh"
        sev = evaluate_row(row, sla_sec=SLA)
        assert sev == OK


# ---------------------------------------------------------------------------
# (L) Liveness gates
# ---------------------------------------------------------------------------

class TestLivenessGates:
    def test_live_false_forces_down(self):
        """live=False must force DOWN regardless of fresh."""
        row = _row("svc_a", fresh="fresh", age_sec=5.0, live=False)
        sev = evaluate_row(row, sla_sec=SLA)
        assert sev == DOWN, "live=False must force DOWN; got %r" % sev

    def test_live_false_on_null_fresh_is_down(self):
        """live=False + fresh=null -> DOWN (liveness gates above freshness)."""
        row = _row("svc_a", fresh=None, age_sec=10.0, live=False)
        sev = evaluate_row(row, sla_sec=SLA)
        assert sev == DOWN

    def test_breaker_open_forces_down(self):
        """breaker='OPEN' must force DOWN regardless of fresh."""
        row = _row("svc_a", fresh="fresh", age_sec=5.0, breaker="OPEN")
        sev = evaluate_row(row, sla_sec=SLA)
        assert sev == DOWN, "breaker=OPEN must force DOWN; got %r" % sev

    def test_live_true_no_fresh_null_below_sla_is_ok(self):
        """live=True + fresh=null + age_sec < SLA -> OK."""
        row = _row("svc_a", fresh=None, age_sec=10.0, live=True)
        sev = evaluate_row(row, sla_sec=SLA)
        assert sev == OK


# ---------------------------------------------------------------------------
# (I) Overall is WORST severity across rows
# ---------------------------------------------------------------------------

class TestOverall:
    def test_overall_is_worst_severity(self):
        """overall must equal the worst single-row severity."""
        rows = [
            _row("svc_a", fresh="fresh", age_sec=5.0),           # OK
            _row("svc_b", fresh=None, age_sec=SLA + 1.0),        # DEGRADED
            _row("svc_c", fresh="fresh", age_sec=2.0),           # OK
        ]
        doc = reconcile(rows, default_sla_sec=SLA)
        assert doc["overall"] == DEGRADED

    def test_overall_down_beats_degraded(self):
        """A single DOWN row must make overall DOWN even if others are degraded/ok."""
        rows = [
            _row("svc_a", fresh=None, age_sec=SLA + 1.0),   # DEGRADED
            _row("svc_b", fresh="down"),                      # DOWN
        ]
        doc = reconcile(rows, default_sla_sec=SLA)
        assert doc["overall"] == DOWN

    def test_counts_match_severities(self):
        """n_ok + n_degraded + n_down must equal n_rows."""
        rows = [
            _row("a", fresh="fresh", age_sec=5.0),
            _row("b", fresh=None, age_sec=SLA + 1.0),
            _row("c", fresh="down"),
        ]
        doc = reconcile(rows, default_sla_sec=SLA)
        assert doc["n_ok"] + doc["n_degraded"] + doc["n_down"] == doc["n_rows"] == 3


# ---------------------------------------------------------------------------
# Per-name SLA overrides
# ---------------------------------------------------------------------------

class TestSlaOverrides:
    def test_per_name_sla_override_short(self):
        """A very short SLA means a 10s age is already stale -> DEGRADED."""
        row = _row("fast_svc", fresh=None, age_sec=10.0)
        doc = reconcile([row], sla_map={"fast_svc": 5.0}, default_sla_sec=SLA)
        assert doc["consensus_services"][0]["consensus_severity"] == DEGRADED
        assert doc["consensus_services"][0]["sla_sec"] == 5.0

    def test_per_name_sla_override_long(self):
        """A long SLA means a 400s age is fresh -> OK (age < sla)."""
        row = _row("slow_svc", fresh=None, age_sec=400.0)
        doc = reconcile([row], sla_map={"slow_svc": 600.0}, default_sla_sec=SLA)
        assert doc["consensus_services"][0]["consensus_severity"] == OK

    def test_unmatched_name_uses_default(self):
        """A name not in sla_map uses default_sla_sec."""
        row = _row("other_svc", fresh=None, age_sec=SLA + 1.0)
        doc = reconcile([row], sla_map={"different_svc": 9999.0}, default_sla_sec=SLA)
        assert doc["consensus_services"][0]["consensus_severity"] == DEGRADED
