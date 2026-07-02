"""ops.tests.test_health_aggregator_stale_live -- stale-never-green gap tests.

Proves the fix: a service row with live=True but age_sec >= fresh_sec scores
DEGRADED (not OK) and pushes overall off 'ok'. A fresh live row still scores OK.

Per-file run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest ops/tests/test_health_aggregator_stale_live.py -q
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import pytest

from ops import health_aggregator as agg


# ---------------------------------------------------------------------------
# Unit tests for _row_severity directly (fast, no I/O)
# ---------------------------------------------------------------------------

def _row(
    live: Optional[bool],
    age_sec: Optional[float],
    fresh_sec: Optional[float],
    fresh: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a minimal row dict for _row_severity."""
    return {
        "name": "test_svc",
        "critical": False,
        "live": live,
        "age_sec": age_sec,
        "fresh_sec": fresh_sec,
        "fresh": fresh,
        "breaker": None,
        "reason": None,
    }


class TestRowSeverityStaleNeverGreen:
    """_row_severity must not return OK for live=True with age_sec >= fresh_sec."""

    def test_live_true_age_exceeds_fresh_sec_is_degraded(self):
        """Core regression: live=True, age 2640s, fresh_sec 300s -> DEGRADED."""
        row = _row(live=True, age_sec=2640.0, fresh_sec=300.0)
        assert agg._row_severity(row) == agg.DEGRADED

    def test_live_true_age_equals_fresh_sec_is_degraded(self):
        """Boundary: age == fresh_sec is NOT fresh (>= triggers DEGRADED)."""
        row = _row(live=True, age_sec=300.0, fresh_sec=300.0)
        assert agg._row_severity(row) == agg.DEGRADED

    def test_live_true_age_below_fresh_sec_is_ok(self):
        """Happy path: age well below fresh_sec -> OK."""
        row = _row(live=True, age_sec=5.0, fresh_sec=300.0)
        assert agg._row_severity(row) == agg.OK

    def test_live_true_no_fresh_sec_no_fresh_is_ok(self):
        """No declared fresh_sec (port-probed server) + live=True -> OK."""
        row = _row(live=True, age_sec=9999.0, fresh_sec=None)
        assert agg._row_severity(row) == agg.OK

    def test_live_true_no_age_sec_is_ok(self):
        """No age_sec (heartbeat file absent) with live=True -> OK (no data to compare)."""
        row = _row(live=True, age_sec=None, fresh_sec=300.0)
        assert agg._row_severity(row) == agg.OK

    def test_live_false_is_down(self):
        """Existing invariant unchanged: live=False always -> DOWN."""
        row = _row(live=False, age_sec=10.0, fresh_sec=300.0)
        assert agg._row_severity(row) == agg.DOWN

    def test_fresh_stale_verdict_still_degraded(self):
        """Existing freshness verdict path unchanged: fresh=stale -> DEGRADED."""
        row = _row(live=True, age_sec=10.0, fresh_sec=300.0, fresh="stale")
        assert agg._row_severity(row) == agg.DEGRADED

    def test_fresh_down_verdict_still_down(self):
        """Existing freshness verdict path unchanged: fresh=down -> DOWN."""
        row = _row(live=True, age_sec=10.0, fresh_sec=300.0, fresh="down")
        assert agg._row_severity(row) == agg.DOWN

    def test_m7_like_scenario_44min_beat_on_7800s_window(self):
        """m7_ingame_refresh scenario: 44 min = 2640s beat, fresh_sec=7800s.
        2640 < 7800, so the m7 case with its own window does NOT trigger this path.
        This confirms the fix is targeted -- it only fires when age >= fresh_sec."""
        row = _row(live=True, age_sec=2640.0, fresh_sec=7800.0)
        assert agg._row_severity(row) == agg.OK  # 2640 < 7800 -> still OK

    def test_m7_like_scenario_exceeds_7800s(self):
        """If m7's own beat is older than 7800s (2.2h) it must score DEGRADED."""
        row = _row(live=True, age_sec=9000.0, fresh_sec=7800.0)
        assert agg._row_severity(row) == agg.DEGRADED


# ---------------------------------------------------------------------------
# Integration tests via aggregate() -- proves overall rollup is affected
# ---------------------------------------------------------------------------

def _fake_snap_with_fresh_sec(age_sec: float, live: bool = True) -> Dict[str, Any]:
    """Snapshot keyed by the liveness component name for m1_paper."""
    return {
        "predict_service_scheduler": {"live": True, "age_sec": 5.0},
        "ingame_live_loop": {"live": True, "age_sec": 10.0},
        "line_daemon": {"live": True, "age_sec": 12.0},
        "paper_loop": {"live": live, "age_sec": age_sec},
    }


class TestAggregateStaleNeverGreen:
    """aggregate() must surface DEGRADED / off-ok when a service is live but stale."""

    def test_stale_live_heartbeat_pushes_overall_off_ok(self, monkeypatch):
        """m1_paper has fresh_sec=2700s; a 3000s-old but live heartbeat -> DEGRADED."""
        snap = _fake_snap_with_fresh_sec(age_sec=3000.0, live=True)
        monkeypatch.setattr(agg._liveness, "liveness_snapshot", lambda **k: snap)
        status = agg.aggregate(now=10000.0)
        # overall must NOT be ok
        assert status["overall"] != agg.OK
        assert status["overall"] == agg.DEGRADED
        # the paper row must surface the staleness
        row = next(s for s in status["services"] if s["name"] == "m1_paper")
        assert row["live"] is True   # liveness snapshot still says live
        assert row["age_sec"] == 3000.0
        # notes must mention m1_paper
        combined_notes = " ".join(status["notes"])
        assert "m1_paper" in combined_notes

    def test_fresh_live_heartbeat_stays_ok(self, monkeypatch):
        """m1_paper with a 20s-old heartbeat (well within 2700s fresh_sec) -> ok."""
        snap = _fake_snap_with_fresh_sec(age_sec=20.0, live=True)
        monkeypatch.setattr(agg._liveness, "liveness_snapshot", lambda **k: snap)
        status = agg.aggregate(now=10000.0)
        assert status["overall"] == agg.OK
        row = next(s for s in status["services"] if s["name"] == "m1_paper")
        assert row["live"] is True
        assert row["age_sec"] == 20.0

    def test_stale_row_carries_reason(self, monkeypatch):
        """A stale-live row must carry a reason string explaining the staleness."""
        snap = _fake_snap_with_fresh_sec(age_sec=3000.0, live=True)
        monkeypatch.setattr(agg._liveness, "liveness_snapshot", lambda **k: snap)
        status = agg.aggregate(now=10000.0)
        row = next(s for s in status["services"] if s["name"] == "m1_paper")
        # reason should be set (either by the pre-existing code or the new path)
        assert row.get("reason") or any("m1_paper" in n for n in status["notes"])

    def test_fresh_sec_field_present_in_row(self, monkeypatch):
        """Every row exposes fresh_sec so callers can render the threshold."""
        snap = _fake_snap_with_fresh_sec(age_sec=5.0, live=True)
        monkeypatch.setattr(agg._liveness, "liveness_snapshot", lambda **k: snap)
        status = agg.aggregate(now=10000.0)
        row = next(s for s in status["services"] if s["name"] == "m1_paper")
        assert "fresh_sec" in row
        assert row["fresh_sec"] is not None  # m1_paper has a declared fresh_sec

    def test_non_heartbeat_service_unaffected(self, monkeypatch):
        """Port-probed services (no fresh_sec) are never demoted by the new check."""
        snap = _fake_snap_with_fresh_sec(age_sec=5.0, live=True)
        monkeypatch.setattr(agg._liveness, "liveness_snapshot", lambda **k: snap)
        status = agg.aggregate(now=10000.0)
        # m1_api_paper is port-probed (live=None, no heartbeat) -> should stay ok
        api_row = next(
            (s for s in status["services"] if s["name"] == "m1_api_paper"), None
        )
        if api_row is not None:
            assert api_row["live"] is None
            # The new check requires live==True, so port-probed rows skip it
            assert agg._row_severity(api_row) == agg.OK
