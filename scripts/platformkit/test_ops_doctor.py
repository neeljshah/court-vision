"""Per-file test: scripts.platformkit.ops_doctor
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_ops_doctor.py -q
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import time

import pytest

from scripts.platformkit.ops_doctor import diagnose, render, _severity_of_row, OK, DEGRADED, DOWN


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_doc(
    services: List[Dict[str, Any]],
    overall: str = "ok",
) -> Dict[str, Any]:
    """Build a minimal autonomy_doc for injection into diagnose()."""
    return {
        "overall": overall,
        "services": services,
        "notes": [],
        "generated_at": "2026-06-20T00:00:00Z",
    }


def _svc(name: str, *, critical: bool = False,
         live: Optional[bool] = None,
         fresh: Optional[str] = None,
         breaker: Optional[str] = None,
         reason: Optional[str] = None,
         age_sec: Optional[float] = None,
         port: Optional[int] = None) -> Dict[str, Any]:
    return {
        "name": name, "critical": critical,
        "live": live, "fresh": fresh,
        "breaker": breaker, "reason": reason,
        "age_sec": age_sec, "port": port,
        "severity": "ok",  # status_composer also emits this; doctor re-derives
    }


# ---------------------------------------------------------------------------
# _severity_of_row: the fix for fresh=null green-on-stale
# ---------------------------------------------------------------------------

class TestSeverityOfRow:
    def test_live_false_is_down(self):
        assert _severity_of_row(_svc("x", live=False)) == DOWN

    def test_breaker_open_is_down(self):
        assert _severity_of_row(_svc("x", breaker="OPEN")) == DOWN

    def test_fresh_down_is_down(self):
        assert _severity_of_row(_svc("x", fresh="down")) == DOWN

    def test_fresh_stale_is_degraded(self):
        assert _severity_of_row(_svc("x", fresh="stale")) == DEGRADED

    def test_fresh_fresh_live_true_is_ok(self):
        assert _severity_of_row(_svc("x", live=True, fresh="fresh")) == OK

    # KEY: fresh=null with live not None -> UNKNOWN -> DEGRADED (not ok)
    def test_fresh_null_live_true_is_degraded(self):
        """QA iter 3/9 gap: a producer that is live but has fresh=null
        must NOT read green -- the doctor must surface it as DEGRADED."""
        row = _svc("m1_producer", critical=True, live=True, fresh=None)
        assert _severity_of_row(row) == DEGRADED

    def test_fresh_null_live_none_is_ok(self):
        """Port-probed server with live=None and fresh=None: no heartbeat
        measurement at all; doctor inherits the aggregator ok verdict
        (supervisor governs them at boot)."""
        row = _svc("m1_api_paper", live=None, fresh=None)
        assert _severity_of_row(row) == OK

    def test_fresh_null_live_false_is_down(self):
        """live=False always dominates, even when fresh=null."""
        row = _svc("x", live=False, fresh=None)
        assert _severity_of_row(row) == DOWN


# ---------------------------------------------------------------------------
# diagnose(): recovery_hint present on every non-ok row
# ---------------------------------------------------------------------------

class TestDiagnoseRecoveryHint:
    def test_non_ok_row_has_recovery_hint(self):
        doc = _make_doc([
            _svc("m6_ingame_loop", live=True, fresh="stale"),
        ])
        diag = diagnose(autonomy_doc=doc)
        assert diag["problems"], "expected a problem"
        p = diag["problems"][0]
        assert p.get("recovery_hint"), "recovery_hint must be non-empty"

    def test_unknown_service_gets_default_hint(self):
        doc = _make_doc([
            _svc("m99_unknown", live=True, fresh="stale"),
        ])
        diag = diagnose(autonomy_doc=doc)
        assert diag["problems"]
        assert diag["problems"][0]["recovery_hint"]

    def test_ok_rows_have_no_problems(self):
        doc = _make_doc([
            _svc("m6_ingame_loop", live=True, fresh="fresh"),
        ])
        diag = diagnose(autonomy_doc=doc)
        assert diag["problems"] == []
        assert "m6_ingame_loop" in diag["ok_services"]


# ---------------------------------------------------------------------------
# diagnose(): critical-first sorting
# ---------------------------------------------------------------------------

class TestCriticalFirstSort:
    def test_critical_before_warning(self):
        doc = _make_doc([
            _svc("m1_paper", critical=False, live=False),  # warning
            _svc("m1_producer", critical=True, live=False),  # critical
        ])
        diag = diagnose(autonomy_doc=doc)
        problems = diag["problems"]
        assert len(problems) == 2
        assert problems[0]["service"] == "m1_producer"
        assert problems[0]["severity"] == "critical"
        assert problems[1]["severity"] == "warning"

    def test_alpha_within_severity_bucket(self):
        doc = _make_doc([
            _svc("z_svc", critical=False, live=False),
            _svc("a_svc", critical=False, live=False),
        ])
        diag = diagnose(autonomy_doc=doc)
        names = [p["service"] for p in diag["problems"]]
        assert names == sorted(names), "expected alphabetical within warning bucket"


# ---------------------------------------------------------------------------
# diagnose(): stale-never-green / fresh=null not ok
# ---------------------------------------------------------------------------

class TestStaleNeverGreen:
    def test_fresh_null_producer_not_ok(self):
        """The QA 3/9 regression: critical producer with fresh=null must not
        be surfaced as ok overall."""
        doc = _make_doc([
            _svc("m1_producer", critical=True, live=True, fresh=None),
        ])
        diag = diagnose(autonomy_doc=doc)
        assert diag["overall"] != OK, (
            "fresh=null on a live producer must not yield overall=ok")
        assert diag["problems"], "must have at least one problem"

    def test_fresh_stale_is_not_ok(self):
        doc = _make_doc([
            _svc("m1_producer", critical=True, live=True, fresh="stale"),
        ], overall="degraded")
        diag = diagnose(autonomy_doc=doc)
        assert diag["overall"] != OK

    def test_all_fresh_and_ok(self):
        doc = _make_doc([
            _svc("m6_ingame_loop", live=True, fresh="fresh"),
            _svc("m1_api_paper", live=None, fresh=None),
        ], overall="ok")
        diag = diagnose(autonomy_doc=doc)
        assert diag["overall"] == OK
        assert diag["problems"] == []


# ---------------------------------------------------------------------------
# diagnose(): doctor==degraded whenever autonomy==degraded for same producer
# ---------------------------------------------------------------------------

class TestDoctorMatchesAutonomy:
    def test_autonomy_degraded_forces_doctor_degraded(self):
        """Even if the individual row looks ok to the doctor, an autonomy_doc
        overall of degraded must propagate (monotone-DOWN guarantee)."""
        doc = _make_doc([
            _svc("m1_api_paper", live=None, fresh=None),
        ], overall="degraded")
        diag = diagnose(autonomy_doc=doc)
        assert diag["overall"] != OK, (
            "doctor must be at least degraded when autonomy is degraded")

    def test_autonomy_ok_and_all_fresh_yields_ok(self):
        doc = _make_doc([
            _svc("m6_ingame_loop", live=True, fresh="fresh"),
        ], overall="ok")
        diag = diagnose(autonomy_doc=doc)
        assert diag["overall"] == OK

    def test_autonomy_down_forces_doctor_down_or_degraded(self):
        doc = _make_doc([], overall="down")
        diag = diagnose(autonomy_doc=doc)
        # No services -> ok from scan, but autonomy overall=down forces degraded/down.
        assert diag["overall"] != OK


# ---------------------------------------------------------------------------
# No $ / roi / pnl key
# ---------------------------------------------------------------------------

class TestNoPnlKeys:
    def _flatten_keys(self, obj: Any) -> List[str]:
        """Recursively collect all dict keys."""
        keys: List[str] = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                keys.append(k)
                keys.extend(self._flatten_keys(v))
        elif isinstance(obj, list):
            for item in obj:
                keys.extend(self._flatten_keys(item))
        return keys

    def test_no_dollar_pnl_roi_key(self):
        doc = _make_doc([
            _svc("m1_producer", critical=True, live=True, fresh="stale"),
        ])
        diag = diagnose(autonomy_doc=doc)
        banned = {"$", "pnl", "roi", "profit", "dollar"}
        all_keys = {k.lower() for k in self._flatten_keys(diag)}
        bad = banned & all_keys
        assert not bad, "banned key(s) found in output: %s" % bad


# ---------------------------------------------------------------------------
# render(): ASCII output, recovery_hint present
# ---------------------------------------------------------------------------

class TestRender:
    def test_render_ascii_only(self):
        doc = _make_doc([
            _svc("m6_ingame_loop", live=True, fresh="stale"),
        ])
        diag = diagnose(autonomy_doc=doc)
        text = render(diag)
        assert isinstance(text, str)
        for ch in text:
            assert ord(ch) < 128, "non-ASCII char found: %r" % ch

    def test_render_contains_recovery_hint_label(self):
        doc = _make_doc([
            _svc("m6_ingame_loop", live=True, fresh="stale"),
        ])
        diag = diagnose(autonomy_doc=doc)
        text = render(diag)
        assert "recovery_hint" in text.lower()

    def test_render_contains_honest_note(self):
        doc = _make_doc([], overall="ok")
        diag = diagnose(autonomy_doc=doc)
        text = render(diag)
        assert "calibration" in text.lower() or "honest" in text.lower()


# ---------------------------------------------------------------------------
# Read-only contract (behavioural: never tries to start a process)
# ---------------------------------------------------------------------------

class TestReadOnly:
    def test_diagnose_does_not_call_subprocess(self, monkeypatch):
        import subprocess
        called = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: called.append(a))
        doc = _make_doc([_svc("m1_producer", critical=True, live=False)])
        diagnose(autonomy_doc=doc)
        assert not called, "subprocess.run was invoked"


# ---------------------------------------------------------------------------
# Integration smoke: diagnose() with real compose() path
# ---------------------------------------------------------------------------

class TestIntegrationSmoke:
    def test_diagnose_live_no_raise(self):
        """diagnose() with no injection must never raise."""
        try:
            diag = diagnose()
        except Exception as exc:  # noqa: BLE001
            pytest.fail("diagnose() raised: %s" % exc)
        assert diag.get("overall") in (OK, DEGRADED, DOWN)
        assert isinstance(diag.get("generated_at"), str)
        assert isinstance(diag.get("problems"), list)
        assert isinstance(diag.get("ok_services"), list)
        # No pnl/$/roi in live output either
        banned = {"pnl", "roi", "profit"}
        all_keys = {k.lower() for k in diag}
        assert not (banned & all_keys)
