"""Per-file tests for scripts.platformkit.autonomy.critical_severity_normalizer.

Acceptance criteria (BE-R3-6 status-severity normalizer):
  (A) A CRITICAL service row with live=None/fresh=null normalizes to DEGRADED (never OK).
  (B) A healthy fresh CRITICAL row (fresh='fresh') stays OK.
  (C) A non-critical row with live=None/fresh=null is unchanged (stays OK).
  (D) Severity is monotone degrade-only: DEGRADED->DOWN stays DOWN; never upgrades.
  (E) A row already at DEGRADED stays DEGRADED (not upgraded).
  (F) live=False forces DOWN regardless of critical flag.
  (G) fresh='stale' forces DEGRADED on both critical and non-critical rows.
  (H) fresh='down' forces DOWN on both critical and non-critical rows.
  (I) normalize_services returns a new list (does not mutate input).
  (J) worst_severity returns the worst normalised severity across rows.
  (K) worst_severity on an empty list returns DEGRADED (absent != green).
  (L) No $ field; calibration not edge.
  (M) Never raises on garbage inputs.
  (N) normalize_services and normalize_row agree on the same row.
  (O) breaker='OPEN' forces DOWN regardless of critical flag.
  (P) Rule 2 -- stale-age coercion (iter4 P1):
      live=True with age_sec > fresh_sec  -> live coerced + severity >= DEGRADED.
      live=True with age_sec <= fresh_sec -> unchanged OK.
      Missing fresh_sec falls back to _DEFAULT_MAX_STALE_SEC (300s); still degrades.
      Degrade-only: never lifts a stale row to OK.
      Existing live=None/fresh=null rule preserved (Rule 1 unchanged).
      No $ field.

Run (per-file only -- never full pytest):
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autonomy/test_critical_severity_normalizer.py -q
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

import pytest

from scripts.platformkit.autonomy.critical_severity_normalizer import (
    DEGRADED,
    DOWN,
    HONEST_NOTE,
    OK,
    _DEFAULT_MAX_STALE_SEC,
    normalize_row,
    normalize_services,
    worst_severity,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row(
    name: str = "m1_producer",
    *,
    critical: bool = True,
    live: Optional[bool] = None,
    fresh: Optional[str] = None,
    breaker: Optional[str] = None,
    severity: Optional[str] = None,
    age_sec: Optional[float] = None,
    fresh_sec: Optional[float] = None,
) -> Dict[str, Any]:
    """Build a minimal services[] row for testing."""
    r: Dict[str, Any] = {"name": name, "critical": critical}
    if live is not None:
        r["live"] = live
    if fresh is not None:
        r["fresh"] = fresh
    if breaker is not None:
        r["breaker"] = breaker
    if severity is not None:
        r["severity"] = severity
    if age_sec is not None:
        r["age_sec"] = age_sec
    if fresh_sec is not None:
        r["fresh_sec"] = fresh_sec
    return r


# ---------------------------------------------------------------------------
# (A) QA regression: CRITICAL + live=None + fresh=null -> DEGRADED (never OK)
# ---------------------------------------------------------------------------

class TestCriticalNullFreshDegraded:
    def test_critical_live_none_fresh_null_is_degraded(self):
        """The core QA gap: CRITICAL service with live=None, fresh=null -> DEGRADED."""
        row = _row("m1_producer", critical=True, live=None, fresh=None)
        sev = normalize_row(row)
        assert sev == DEGRADED, (
            "CRITICAL live=None fresh=null must be DEGRADED (not OK); got %r" % sev
        )

    def test_critical_live_none_fresh_null_never_ok(self):
        """A second critical service (m1_api_paper) with fresh=null -> DEGRADED."""
        row = _row("m1_api_paper", critical=True, live=None, fresh=None)
        sev = normalize_row(row)
        assert sev != OK, (
            "CRITICAL service m1_api_paper with fresh=null must not be OK; got %r" % sev
        )
        assert sev == DEGRADED

    def test_critical_live_true_fresh_null_is_degraded(self):
        """CRITICAL + live=True + fresh=None -> DEGRADED (freshness unverified)."""
        row = _row("m1_producer", critical=True, live=True, fresh=None)
        sev = normalize_row(row)
        assert sev == DEGRADED, (
            "CRITICAL live=True fresh=null must be DEGRADED; got %r" % sev
        )

    def test_critical_null_fresh_in_normalize_services(self):
        """normalize_services must also produce DEGRADED for CRITICAL fresh=null rows."""
        rows = [_row("m1_producer", critical=True, live=None, fresh=None)]
        result = normalize_services(rows)
        assert len(result) == 1
        assert result[0]["severity"] == DEGRADED, (
            "normalize_services: CRITICAL fresh=null must be DEGRADED; "
            "got %r" % result[0]["severity"]
        )


# ---------------------------------------------------------------------------
# (B) A healthy fresh CRITICAL row stays OK
# ---------------------------------------------------------------------------

class TestCriticalFreshStaysOk:
    def test_critical_fresh_fresh_is_ok(self):
        """A CRITICAL row with fresh='fresh' must remain OK."""
        row = _row("m1_producer", critical=True, live=True, fresh="fresh")
        sev = normalize_row(row)
        assert sev == OK, "CRITICAL fresh='fresh' must be OK; got %r" % sev

    def test_critical_live_true_fresh_fresh_is_ok(self):
        """CRITICAL + live=True + fresh='fresh' -> OK (healthy baseline)."""
        row = _row("m1_api_paper", critical=True, live=True, fresh="fresh")
        sev = normalize_row(row)
        assert sev == OK, "must be OK; got %r" % sev


# ---------------------------------------------------------------------------
# (C) Non-critical row with live=None/fresh=null is unchanged (stays OK)
# ---------------------------------------------------------------------------

class TestNonCriticalUnchanged:
    def test_non_critical_live_none_fresh_null_stays_ok(self):
        """A non-critical port-probed server with fresh=null must NOT be degraded
        by the normalizer.  The supervisor governs it at boot; the existing
        health_aggregator behaviour (OK) is preserved."""
        row = _row("m5_autonomy_monitor", critical=False, live=None, fresh=None)
        sev = normalize_row(row)
        assert sev == OK, (
            "non-critical live=None fresh=null must stay OK; got %r" % sev
        )

    def test_non_critical_live_true_fresh_null_stays_ok(self):
        """Non-critical + live=True + fresh=None -> OK (not degraded by normalizer)."""
        row = _row("m5_autonomy_monitor", critical=False, live=True, fresh=None)
        sev = normalize_row(row)
        assert sev == OK, (
            "non-critical live=True fresh=null must stay OK; got %r" % sev
        )


# ---------------------------------------------------------------------------
# (D) Monotone degrade-only: severity can only worsen, never improve
# ---------------------------------------------------------------------------

class TestMonotoneDegrade:
    def test_existing_degraded_never_upgraded_to_ok(self):
        """A row carrying severity='degraded' must not be upgraded to 'ok'."""
        row = _row("svc", critical=False, live=True, fresh="fresh", severity="degraded")
        sev = normalize_row(row)
        assert sev != OK, (
            "existing severity=degraded must never be upgraded to ok; got %r" % sev
        )
        assert sev in (DEGRADED, DOWN)

    def test_existing_down_never_upgraded_to_degraded(self):
        """A row carrying severity='down' must not be upgraded to 'degraded'."""
        row = _row("svc", critical=True, live=True, fresh="fresh", severity="down")
        sev = normalize_row(row)
        assert sev == DOWN, (
            "existing severity=down must never be upgraded; got %r" % sev
        )

    def test_critical_null_on_already_degraded_stays_degraded(self):
        """CRITICAL fresh=null + existing severity='degraded' -> DEGRADED (no change)."""
        row = _row("m1_producer", critical=True, live=None, fresh=None, severity="degraded")
        sev = normalize_row(row)
        assert sev == DEGRADED

    def test_rank_monotone_across_batch(self):
        """After normalize_services the per-row severity rank can only stay same or
        increase compared to what health_aggregator would have returned (base severity)."""
        rows = [
            _row("a", critical=True, live=None, fresh=None),     # base=OK -> normalised=DEGRADED
            _row("b", critical=False, live=None, fresh=None),    # base=OK -> normalised=OK
            _row("c", critical=True, live=True, fresh="fresh"),  # base=OK -> normalised=OK
            _row("d", critical=True, live=True, fresh="stale"),  # base=DEGRADED -> DEGRADED
            _row("e", critical=True, live=False, fresh=None),    # base=DOWN -> DOWN
        ]
        result = normalize_services(rows)
        rank = {"ok": 0, "degraded": 1, "down": 2}
        for orig, norm in zip(rows, result):
            orig_sev = orig.get("severity", "ok")
            if orig_sev not in rank:
                orig_sev = "ok"
            norm_sev = norm["severity"]
            assert rank.get(norm_sev, 1) >= rank.get(orig_sev, 0), (
                "severity must only worsen: %r -> %r for row %s" % (
                    orig_sev, norm_sev, orig.get("name"))
            )


# ---------------------------------------------------------------------------
# (E) Already DEGRADED stays DEGRADED
# ---------------------------------------------------------------------------

class TestAlreadyDegraded:
    def test_already_degraded_stays_degraded(self):
        row = _row("m1_producer", critical=True, live=None, fresh=None, severity="degraded")
        sev = normalize_row(row)
        assert sev == DEGRADED

    def test_already_degraded_non_critical_stays_degraded(self):
        row = _row("svc_x", critical=False, live=None, fresh=None, severity="degraded")
        sev = normalize_row(row)
        assert sev == DEGRADED


# ---------------------------------------------------------------------------
# (F) live=False forces DOWN
# ---------------------------------------------------------------------------

class TestLiveFalseDown:
    def test_live_false_forces_down_critical(self):
        row = _row("m1_producer", critical=True, live=False, fresh=None)
        sev = normalize_row(row)
        assert sev == DOWN, "live=False must be DOWN; got %r" % sev

    def test_live_false_forces_down_non_critical(self):
        row = _row("m5_svc", critical=False, live=False, fresh=None)
        sev = normalize_row(row)
        assert sev == DOWN, "live=False must be DOWN; got %r" % sev

    def test_live_false_with_fresh_fresh_is_still_down(self):
        """live=False overrides even a fresh freshness verdict."""
        row = _row("m1_producer", critical=True, live=False, fresh="fresh")
        sev = normalize_row(row)
        assert sev == DOWN


# ---------------------------------------------------------------------------
# (G) fresh='stale' -> DEGRADED
# ---------------------------------------------------------------------------

class TestStaleDegraded:
    def test_critical_fresh_stale_is_degraded(self):
        row = _row("m1_producer", critical=True, live=True, fresh="stale")
        sev = normalize_row(row)
        assert sev == DEGRADED

    def test_non_critical_fresh_stale_is_degraded(self):
        row = _row("svc_x", critical=False, live=True, fresh="stale")
        sev = normalize_row(row)
        assert sev == DEGRADED


# ---------------------------------------------------------------------------
# (H) fresh='down' -> DOWN
# ---------------------------------------------------------------------------

class TestFreshDownForces:
    def test_critical_fresh_down_is_down(self):
        row = _row("m1_producer", critical=True, live=True, fresh="down")
        sev = normalize_row(row)
        assert sev == DOWN

    def test_non_critical_fresh_down_is_down(self):
        row = _row("svc_x", critical=False, live=True, fresh="down")
        sev = normalize_row(row)
        assert sev == DOWN


# ---------------------------------------------------------------------------
# (I) normalize_services does not mutate input
# ---------------------------------------------------------------------------

class TestNoMutation:
    def test_normalize_services_does_not_mutate_original(self):
        """normalize_services must return a new list of new dicts; input unchanged."""
        row = _row("m1_producer", critical=True, live=None, fresh=None)
        original_row = dict(row)
        rows = [row]

        result = normalize_services(rows)

        # Input list must be untouched.
        assert rows is not result, "must return a new list"
        assert rows[0] is row, "original list element must be unchanged"
        assert row == original_row, "original row dict must not be mutated"

    def test_normalize_services_result_carries_severity(self):
        """Each result dict must carry a 'severity' key."""
        rows = [
            _row("m1_producer", critical=True, live=None, fresh=None),
            _row("svc_b", critical=False, live=True, fresh="fresh"),
        ]
        result = normalize_services(rows)
        for item in result:
            assert "severity" in item, "result row must have 'severity' key"
            assert item["severity"] in (OK, DEGRADED, DOWN)


# ---------------------------------------------------------------------------
# (J/K) worst_severity
# ---------------------------------------------------------------------------

class TestWorstSeverity:
    def test_worst_severity_all_ok(self):
        rows = [
            _row("a", critical=False, live=True, fresh="fresh"),
            _row("b", critical=False, live=True, fresh="fresh"),
        ]
        assert worst_severity(rows) == OK

    def test_worst_severity_one_degraded(self):
        rows = [
            _row("a", critical=False, live=True, fresh="fresh"),
            _row("b", critical=True, live=None, fresh=None),   # -> DEGRADED via normalizer
        ]
        assert worst_severity(rows) == DEGRADED

    def test_worst_severity_one_down(self):
        rows = [
            _row("a", critical=True, live=None, fresh=None),   # DEGRADED
            _row("b", critical=False, live=False, fresh=None), # DOWN
        ]
        assert worst_severity(rows) == DOWN

    def test_worst_severity_empty_is_degraded(self):
        """(K) Empty list -> DEGRADED (absent != green)."""
        assert worst_severity([]) == DEGRADED

    def test_worst_severity_none_input_is_degraded(self):
        assert worst_severity(None) == DEGRADED  # type: ignore[arg-type]

    def test_worst_severity_dominance(self):
        """DOWN dominates DEGRADED which dominates OK."""
        rows = [
            _row("a", critical=False, live=True, fresh="fresh"),  # OK
            _row("b", critical=True, live=None, fresh=None),      # DEGRADED
            _row("c", critical=True, live=False, fresh=None),     # DOWN
        ]
        assert worst_severity(rows) == DOWN


# ---------------------------------------------------------------------------
# (L) No $ field; calibration not edge
# ---------------------------------------------------------------------------

class TestNoDollarField:
    def test_no_dollar_in_normalize_row_result(self):
        sev = normalize_row(_row("m1_producer", critical=True, live=None, fresh=None))
        assert "$" not in sev

    def test_no_dollar_adjacent_digit_in_normalize_services(self):
        rows = [_row("m1_producer", critical=True, live=None, fresh=None)]
        result = normalize_services(rows)
        result_str = str(result)
        assert not re.search(r"\$\s*\d", result_str), (
            "no $ adjacent to digit in output: %s" % result_str[:200]
        )

    def test_honest_note_references_no_dollar(self):
        """HONEST_NOTE constant must reference 'no $ field' invariant."""
        assert "no $" in HONEST_NOTE.lower() or "no dollar" in HONEST_NOTE.lower(), (
            "HONEST_NOTE must mention 'no $ field'; got: %s" % HONEST_NOTE
        )

    def test_honest_note_references_calibration(self):
        assert "calibration" in HONEST_NOTE.lower(), (
            "HONEST_NOTE must mention calibration; got: %s" % HONEST_NOTE
        )


# ---------------------------------------------------------------------------
# (M) Never raises on garbage inputs
# ---------------------------------------------------------------------------

class TestNeverRaises:
    @pytest.mark.parametrize("bad_input", [None, 42, "string", [], object()])
    def test_normalize_row_never_raises(self, bad_input):
        try:
            sev = normalize_row(bad_input)  # type: ignore[arg-type]
            assert sev in (OK, DEGRADED, DOWN)
        except Exception as exc:
            pytest.fail("normalize_row raised on %r: %s" % (bad_input, exc))

    @pytest.mark.parametrize("bad_input", [None, 42, "string", object()])
    def test_normalize_services_never_raises(self, bad_input):
        try:
            result = normalize_services(bad_input)  # type: ignore[arg-type]
            assert isinstance(result, list)
        except Exception as exc:
            pytest.fail("normalize_services raised on %r: %s" % (bad_input, exc))

    @pytest.mark.parametrize("bad_input", [None, 42, "string", object()])
    def test_worst_severity_never_raises(self, bad_input):
        try:
            sev = worst_severity(bad_input)  # type: ignore[arg-type]
            assert sev in (OK, DEGRADED, DOWN)
        except Exception as exc:
            pytest.fail("worst_severity raised on %r: %s" % (bad_input, exc))

    def test_normalize_services_with_mixed_non_dict_rows(self):
        """Non-dict items in rows list are dropped, not crashed on."""
        rows = ["garbage", None, 42, _row("m1_producer", critical=True)]  # type: ignore
        try:
            result = normalize_services(rows)  # type: ignore[arg-type]
            assert isinstance(result, list)
            # Only the real dict row should appear.
            assert len(result) == 1
        except Exception as exc:
            pytest.fail("normalize_services raised on mixed list: %s" % exc)


# ---------------------------------------------------------------------------
# (N) normalize_services and normalize_row agree on the same row
# ---------------------------------------------------------------------------

class TestConsistency:
    def test_normalize_services_agrees_with_normalize_row(self):
        """Per-row severity from normalize_services must match normalize_row."""
        test_rows = [
            _row("m1_producer", critical=True, live=None, fresh=None),
            _row("m1_api_paper", critical=True, live=None, fresh=None),
            _row("svc_nc", critical=False, live=None, fresh=None),
            _row("svc_fresh", critical=True, live=True, fresh="fresh"),
            _row("svc_stale", critical=True, live=True, fresh="stale"),
            _row("svc_down", critical=False, live=False, fresh=None),
        ]
        batch = normalize_services(test_rows)
        for orig, result in zip(test_rows, batch):
            direct = normalize_row(orig)
            batch_sev = result["severity"]
            assert direct == batch_sev, (
                "normalize_row and normalize_services disagree for %r: "
                "%r vs %r" % (orig.get("name"), direct, batch_sev)
            )


# ---------------------------------------------------------------------------
# (O) breaker='OPEN' forces DOWN
# ---------------------------------------------------------------------------

class TestBreakerOpen:
    def test_breaker_open_forces_down_critical(self):
        row = _row("m1_producer", critical=True, live=True, fresh="fresh", breaker="OPEN")
        sev = normalize_row(row)
        assert sev == DOWN, "breaker=OPEN must force DOWN; got %r" % sev

    def test_breaker_open_forces_down_non_critical(self):
        row = _row("svc_x", critical=False, live=True, fresh="fresh", breaker="OPEN")
        sev = normalize_row(row)
        assert sev == DOWN

    def test_breaker_closed_does_not_force_down(self):
        """breaker='CLOSED' must not affect severity."""
        row = _row("m1_producer", critical=True, live=True, fresh="fresh", breaker="CLOSED")
        sev = normalize_row(row)
        assert sev == OK, "CLOSED breaker must not force DOWN; got %r" % sev


# ---------------------------------------------------------------------------
# (P) Rule 2 -- stale-age coercion (iter4 P1)
# ---------------------------------------------------------------------------

class TestStaleAgeCoercion:
    """Rule 2: live=True with age_sec > fresh_sec must coerce live off and
    demote severity to >= DEGRADED.  Closes the heartbeat-presence-vs-recency
    gap where m7_ingame_refresh reads live=True at 44min stale.
    """

    def test_live_true_age_over_fresh_sec_demoted(self):
        """Core iter4 P1 case: live=True but age_sec > fresh_sec -> severity >= DEGRADED."""
        row = _row("m7_ingame_refresh", critical=True, live=True,
                   age_sec=2640.0, fresh_sec=120.0)  # 44 min stale, 2 min window
        sev = normalize_row(row)
        assert sev in (DEGRADED, DOWN), (
            "live=True with age_sec(2640) > fresh_sec(120) must be DEGRADED or DOWN; "
            "got %r" % sev
        )
        assert sev != OK, "stale live must never be OK; got %r" % sev

    def test_live_true_age_over_fresh_sec_not_ok(self):
        """Non-critical service: live=True, age_sec > fresh_sec -> NOT OK."""
        row = _row("m7_ingame_refresh", critical=False, live=True,
                   age_sec=500.0, fresh_sec=60.0)
        sev = normalize_row(row)
        assert sev != OK, (
            "live=True with stale age must never be OK (non-critical too); got %r" % sev
        )
        assert sev in (DEGRADED, DOWN)

    def test_live_true_age_at_or_under_fresh_sec_stays_ok(self):
        """live=True with age_sec <= fresh_sec must remain OK (genuinely fresh)."""
        row = _row("m7_ingame_refresh", critical=False, live=True,
                   age_sec=59.9, fresh_sec=60.0)
        sev = normalize_row(row)
        assert sev == OK, (
            "live=True with age_sec(59.9) <= fresh_sec(60) must stay OK; got %r" % sev
        )

    def test_live_true_age_exactly_at_fresh_sec_stays_ok(self):
        """age_sec == fresh_sec is still fresh (boundary: > not >=)."""
        row = _row("m7_ingame_refresh", critical=False, live=True,
                   age_sec=60.0, fresh_sec=60.0)
        sev = normalize_row(row)
        assert sev == OK, (
            "live=True with age_sec(60) == fresh_sec(60) must stay OK; got %r" % sev
        )

    def test_missing_fresh_sec_falls_back_to_default_degrades_on_gross_staleness(self):
        """When fresh_sec is absent, _DEFAULT_MAX_STALE_SEC (300s) is the floor.
        A heartbeat that is 44 min (2640s) old must still degrade."""
        row = _row("m7_ingame_refresh", critical=False, live=True,
                   age_sec=2640.0)  # no fresh_sec -> default 300s
        sev = normalize_row(row)
        assert sev in (DEGRADED, DOWN), (
            "age_sec(2640) > default_max_stale(300) with no fresh_sec "
            "must be DEGRADED or DOWN; got %r" % sev
        )
        assert sev != OK

    def test_missing_fresh_sec_fresh_age_stays_ok(self):
        """When fresh_sec is absent and age_sec < 300 (default), row is fresh -> OK."""
        row = _row("svc_x", critical=False, live=True, age_sec=120.0)
        sev = normalize_row(row)
        assert sev == OK, (
            "age_sec(120) < default_max_stale(300) with no fresh_sec must stay OK; "
            "got %r" % sev
        )

    def test_default_max_stale_sec_is_300(self):
        """_DEFAULT_MAX_STALE_SEC must equal 300.0 (matches ops_consensus DEFAULT_SLA_SEC)."""
        assert _DEFAULT_MAX_STALE_SEC == 300.0, (
            "_DEFAULT_MAX_STALE_SEC must be 300.0; got %r" % _DEFAULT_MAX_STALE_SEC
        )

    def test_stale_age_degrade_only_never_lifts(self):
        """A row already at DOWN must not be lifted by stale-age logic."""
        row = _row("m7", critical=False, live=True, fresh="down",
                   age_sec=2640.0, fresh_sec=120.0)
        sev = normalize_row(row)
        assert sev == DOWN, (
            "a row at DOWN with stale age must stay DOWN (never lifted); got %r" % sev
        )

    def test_stale_age_in_normalize_services(self):
        """normalize_services must also demote stale-age rows."""
        rows = [
            _row("m7", critical=True, live=True, age_sec=2640.0, fresh_sec=120.0),
            _row("m8", critical=False, live=True, age_sec=30.0, fresh_sec=120.0),
        ]
        result = normalize_services(rows)
        assert result[0]["severity"] in (DEGRADED, DOWN), (
            "m7 (stale) must be DEGRADED or DOWN; got %r" % result[0]["severity"]
        )
        assert result[1]["severity"] == OK, (
            "m8 (fresh) must stay OK; got %r" % result[1]["severity"]
        )

    def test_stale_age_does_not_mutate_original_row(self):
        """Rule 2 must NEVER mutate the original row dict (uses a local shadow)."""
        row = _row("m7", critical=True, live=True, age_sec=2640.0, fresh_sec=120.0)
        original_live = row.get("live")
        _ = normalize_row(row)
        assert row.get("live") == original_live, (
            "normalize_row must not mutate original row; live changed from %r to %r"
            % (original_live, row.get("live"))
        )

    def test_rule1_still_applies_alongside_rule2(self):
        """Rule 1 (critical-null-fresh) still fires even when age_sec is present
        and below fresh_sec (i.e. the age is fresh but freshness verdict is None)."""
        row = _row("m1_producer", critical=True, live=True,
                   fresh=None, age_sec=30.0, fresh_sec=120.0)
        # age_sec(30) <= fresh_sec(120): Rule 2 does NOT fire.
        # fresh=None + critical=True: Rule 1 fires -> DEGRADED.
        sev = normalize_row(row)
        assert sev == DEGRADED, (
            "critical + fresh=None + fresh age -> Rule 1 must give DEGRADED; got %r" % sev
        )

    def test_negative_age_treated_as_stale(self):
        """Negative age (clock skew / future-stamped heartbeat) must be treated as stale."""
        row = _row("m7", critical=False, live=True, age_sec=-1.0, fresh_sec=120.0)
        sev = normalize_row(row)
        assert sev in (DEGRADED, DOWN), (
            "negative age_sec must be treated as stale -> DEGRADED or DOWN; got %r" % sev
        )
        assert sev != OK

    def test_worst_severity_stale_age_row_propagates(self):
        """worst_severity must pick up the stale-age row's demoted severity."""
        rows = [
            _row("ok_svc", critical=False, live=True, age_sec=10.0, fresh_sec=120.0),
            _row("m7", critical=False, live=True, age_sec=2640.0, fresh_sec=120.0),
        ]
        wsev = worst_severity(rows)
        assert wsev in (DEGRADED, DOWN), (
            "worst_severity with a stale-age row must be >= DEGRADED; got %r" % wsev
        )
