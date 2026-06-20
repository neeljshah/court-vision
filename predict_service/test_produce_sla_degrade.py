"""predict_service.test_produce_sla_degrade -- per-file test for BE-R5-6.

Acceptance criteria (per workstream spec):
  (a) A sport with snapshot age >= its SLA scores ok=False (stale-never-green).
  (b) A registered sport absent from the scheduler sports_run heartbeat degrades
      the rollup with a warning field.
  (c) A fresh in-SLA sport scores ok=True.
  (d) Uses normalize_service_severity from ops_staleness_normalizer (shared
      evaluator -- not a parallel stub).
  (e) No $ field, honest_note present.

Also covers:
  - /api/produce/status endpoint integration (FastAPI TestClient).
  - scheduler_gap appears in the status rollup when a sport is missing from
    heartbeat sports_run.
  - SLA-degrade applied at the endpoint level: stale snapshot file -> ok=False
    in the response JSON.

Run (per-file only):
    cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/test_produce_sla_degrade.py -q

INVARIANTS: ASCII only; no $ field; stale-never-green; <=300 LOC; per-file only.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except ImportError:
    pytest.skip("fastapi/httpx not installed", allow_module_level=True)

from predict_service.produce_sla_degrade import (
    HONEST_NOTE,
    SPORT_SLA_SEC,
    default_sla_for,
    evaluate_scheduler_gap,
    evaluate_sport_freshness,
)
from predict_service.ops_staleness_normalizer import (
    normalize_service_severity,
    OK,
    DEGRADED,
)


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------

def _iso_ago(seconds: float) -> str:
    """ISO-8601 UTC timestamp *seconds* in the past."""
    ts = datetime.now(timezone.utc).timestamp() - seconds
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _make_envelope(status: str = "ok", age_sec: float = 60.0) -> MagicMock:
    """Build a minimal SnapshotEnvelope-like mock."""
    env = MagicMock()
    env.status = status
    env.generated_at = _iso_ago(age_sec)
    env.predictions = []
    env.markets = []
    env.note = None
    return env


def _make_produce_status_client(
    sport_envs: Dict[str, MagicMock],
    heartbeat: Optional[Dict[str, Any]] = None,
    active: Optional[List[str]] = None,
) -> TestClient:
    """Build a minimal FastAPI app with produce_status router and inject mocks."""
    from predict_service.produce_status import router  # noqa: PLC0415

    app = FastAPI()
    app.include_router(router)

    client = TestClient(app, raise_server_exceptions=True)
    return client, sport_envs, heartbeat, active


def _get_status(
    sport_envs: Dict[str, MagicMock],
    heartbeat: Optional[Dict[str, Any]] = None,
    active: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Hit /api/produce/status with controlled mocks; return response JSON."""
    from predict_service.produce_status import router  # noqa: PLC0415

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=True)

    active_sports_list = active if active is not None else list(sport_envs.keys())

    def _fake_read_latest(sport: str, out_dir: Any = None) -> MagicMock:
        if sport in sport_envs:
            return sport_envs[sport]
        raise FileNotFoundError("no envelope for %s" % sport)

    hb = heartbeat if heartbeat is not None else {
        "sports_run": active_sports_list,
        "updated_at": time.time(),
    }

    with (
        patch("predict_service.produce_status.store.read_latest",
              side_effect=_fake_read_latest),
        patch("predict_service.produce_status._active_sports",
              return_value=active_sports_list),
        patch("predict_service.produce_status.read_heartbeat", return_value=hb),
    ):
        resp = client.get("/api/produce/status")

    assert resp.status_code == 200, "Expected 200, got %d" % resp.status_code
    return resp.json()


# ---------------------------------------------------------------------------
# (a) Sport with age >= SLA -> ok=False (stale-never-green).
# ---------------------------------------------------------------------------

class TestSlaDegrade:
    """Rule A: snapshot age >= SLA must score ok=False."""

    def test_age_at_sla_boundary_scores_false(self) -> None:
        """Snapshot exactly at the SLA must degrade (>=, not >)."""
        sla = default_sla_for("nba")
        result = evaluate_sport_freshness("nba", age_sec=sla, snapshot_status="ok")
        assert result["ok"] is False, (
            "(a) age==SLA must score ok=False; got ok=%r" % result["ok"]
        )
        assert result["severity"] != OK, (
            "(a) severity must be degraded at SLA boundary; got %r" % result["severity"]
        )

    def test_age_over_sla_scores_false(self) -> None:
        """Snapshot well beyond the SLA must also score ok=False."""
        sla = default_sla_for("mlb")
        result = evaluate_sport_freshness("mlb", age_sec=sla + 300.0,
                                          snapshot_status="ok")
        assert result["ok"] is False, (
            "(a) age > SLA must score ok=False; got ok=%r" % result["ok"]
        )

    def test_none_age_scores_false(self) -> None:
        """Never-written snapshot (age=None) must score ok=False."""
        result = evaluate_sport_freshness("tennis", age_sec=None,
                                          snapshot_status="ok")
        assert result["ok"] is False, (
            "(a) age=None (never written) must score ok=False; got %r" % result["ok"]
        )

    def test_unavailable_snapshot_scores_false(self) -> None:
        """snapshot_status != 'ok' must degrade regardless of age."""
        result = evaluate_sport_freshness("soccer", age_sec=10.0,
                                          snapshot_status="unavailable")
        assert result["ok"] is False, (
            "(a) unavailable snapshot must score ok=False; got %r" % result["ok"]
        )

    def test_endpoint_stale_snapshot_ok_false(self) -> None:
        """Integration: /api/produce/status must return ok=False for stale sport."""
        sla = default_sla_for("nba")
        stale_env = _make_envelope(status="ok", age_sec=sla + 600.0)
        body = _get_status({"nba": stale_env})
        sports = {s["sport"]: s for s in body.get("sports", [])}
        assert "nba" in sports, "nba entry must appear in sports list"
        assert sports["nba"]["ok"] is False, (
            "(a) endpoint must return ok=False for stale nba snapshot; "
            "got ok=%r" % sports["nba"].get("ok")
        )


# ---------------------------------------------------------------------------
# (b) Registered sport absent from scheduler sports_run -> warning in rollup.
# ---------------------------------------------------------------------------

class TestSchedulerGap:
    """Rule B: a registered sport absent from heartbeat sports_run degrades rollup."""

    def test_gap_detected_when_sport_missing(self) -> None:
        """evaluate_scheduler_gap returns gap_detected=True for absent sport."""
        result = evaluate_scheduler_gap(
            registered_sports=["nba", "mlb"],
            sports_run=["nba"],  # mlb silently absent
        )
        assert result["gap_detected"] is True, (
            "(b) gap_detected must be True when mlb absent from sports_run"
        )
        assert "mlb" in result["missing_sports"], (
            "(b) mlb must appear in missing_sports"
        )
        assert result["warning"] is not None, (
            "(b) warning field must be set when gap is detected"
        )

    def test_no_gap_when_all_present(self) -> None:
        """evaluate_scheduler_gap returns gap_detected=False when all match."""
        result = evaluate_scheduler_gap(
            registered_sports=["nba", "mlb"],
            sports_run=["nba", "mlb"],
        )
        assert result["gap_detected"] is False, (
            "(b) gap_detected must be False when all registered sports are present"
        )
        assert result["missing_sports"] == [], (
            "(b) missing_sports must be empty when no gap"
        )

    def test_endpoint_gap_in_rollup_when_sport_dropped(self) -> None:
        """Integration: /api/produce/status includes scheduler_gap warning."""
        fresh_env = _make_envelope(status="ok", age_sec=60.0)
        # heartbeat only ran nba; mlb was silently dropped
        hb = {"sports_run": ["nba"], "updated_at": time.time()}
        body = _get_status(
            sport_envs={"nba": fresh_env, "mlb": fresh_env},
            heartbeat=hb,
            active=["nba", "mlb"],
        )
        assert "scheduler_gap" in body, (
            "(b) scheduler_gap must appear in rollup when mlb dropped; "
            "keys=%r" % list(body.keys())
        )
        gap = body["scheduler_gap"]
        assert gap.get("gap_detected") is True, (
            "(b) gap_detected must be True in rollup; gap=%r" % gap
        )
        assert "mlb" in gap.get("missing_sports", []), (
            "(b) mlb must be listed in scheduler_gap.missing_sports"
        )
        assert body.get("warning") is not None, (
            "(b) top-level warning must be set when scheduler gap detected"
        )

    def test_no_gap_key_when_all_present_in_heartbeat(self) -> None:
        """Integration: scheduler_gap absent from rollup when all sports present."""
        fresh_env = _make_envelope(status="ok", age_sec=60.0)
        hb = {"sports_run": ["nba"], "updated_at": time.time()}
        body = _get_status(
            sport_envs={"nba": fresh_env},
            heartbeat=hb,
            active=["nba"],
        )
        assert "scheduler_gap" not in body, (
            "(b) scheduler_gap must not appear when all sports present; "
            "got keys=%r" % list(body.keys())
        )


# ---------------------------------------------------------------------------
# (c) Fresh in-SLA sport scores ok=True.
# ---------------------------------------------------------------------------

class TestFreshSport:
    """A snapshot younger than its SLA must score ok=True."""

    def test_fresh_sport_scores_ok_true(self) -> None:
        """age < SLA with status='ok' must score ok=True."""
        sla = default_sla_for("nba")
        result = evaluate_sport_freshness("nba", age_sec=sla - 60.0,
                                          snapshot_status="ok")
        assert result["ok"] is True, (
            "(c) fresh sport must score ok=True; got ok=%r" % result["ok"]
        )
        assert result["severity"] == OK, (
            "(c) severity must be ok for fresh sport; got %r" % result["severity"]
        )

    def test_endpoint_fresh_snapshot_ok_true(self) -> None:
        """Integration: /api/produce/status returns ok=True for fresh snapshot."""
        sla = default_sla_for("nba")
        fresh_env = _make_envelope(status="ok", age_sec=sla - 60.0)
        hb = {"sports_run": ["nba"], "updated_at": time.time()}
        body = _get_status({"nba": fresh_env}, heartbeat=hb, active=["nba"])
        sports = {s["sport"]: s for s in body.get("sports", [])}
        assert sports.get("nba", {}).get("ok") is True, (
            "(c) endpoint must return ok=True for fresh nba snapshot; "
            "got sports=%r" % sports
        )


# ---------------------------------------------------------------------------
# (d) Uses normalize_service_severity from ops_staleness_normalizer.
# ---------------------------------------------------------------------------

class TestSharedEvaluator:
    """evaluate_sport_freshness must delegate to normalize_service_severity."""

    def test_delegates_to_normalize_service_severity(self) -> None:
        """Intercept normalize_service_severity to confirm delegation."""
        from predict_service import produce_sla_degrade as mod  # noqa: PLC0415

        calls: List[Dict] = []
        real_fn = mod.normalize_service_severity

        def _tracking_fn(row: Any, sla_sec: float = 300.0,
                         readiness_kind: str = "HEARTBEAT") -> str:
            calls.append({"row": row, "sla_sec": sla_sec,
                          "readiness_kind": readiness_kind})
            return real_fn(row, sla_sec=sla_sec, readiness_kind=readiness_kind)

        with patch.object(mod, "normalize_service_severity", _tracking_fn):
            evaluate_sport_freshness("nba", age_sec=60.0, snapshot_status="ok")

        assert len(calls) >= 1, (
            "(d) evaluate_sport_freshness must call normalize_service_severity; "
            "got 0 calls -- it is using a parallel stub instead of the shared evaluator"
        )
        assert calls[0].get("readiness_kind") == "HEARTBEAT", (
            "(d) readiness_kind must be HEARTBEAT; got %r" % calls[0].get("readiness_kind")
        )

    def test_sla_values_match_sport_sla_sec(self) -> None:
        """SLA passed to normalize_service_severity matches SPORT_SLA_SEC."""
        from predict_service import produce_sla_degrade as mod  # noqa: PLC0415

        calls: List[Dict] = []
        real_fn = mod.normalize_service_severity

        def _tracking_fn(row: Any, sla_sec: float = 300.0,
                         readiness_kind: str = "HEARTBEAT") -> str:
            calls.append({"sla_sec": sla_sec})
            return real_fn(row, sla_sec=sla_sec, readiness_kind=readiness_kind)

        with patch.object(mod, "normalize_service_severity", _tracking_fn):
            evaluate_sport_freshness("nba", age_sec=60.0, snapshot_status="ok")

        assert calls, "(d) no calls recorded to normalize_service_severity"
        used_sla = calls[0]["sla_sec"]
        expected_sla = SPORT_SLA_SEC["nba"]
        assert used_sla == expected_sla, (
            "(d) SLA mismatch: expected %r, got %r" % (expected_sla, used_sla)
        )


# ---------------------------------------------------------------------------
# (e) No $ field; honest_note present.
# ---------------------------------------------------------------------------

def _has_dollar(obj: Any) -> bool:
    if isinstance(obj, dict):
        return any("$" in str(k) or _has_dollar(v) for k, v in obj.items())
    if isinstance(obj, list):
        return any(_has_dollar(i) for i in obj)
    return False


class TestHonestyInvariants:
    """(e) No $ field; honest_note present; no edge_claimed."""

    def test_no_dollar_field_in_freshness_result(self) -> None:
        result = evaluate_sport_freshness("nba", age_sec=60.0, snapshot_status="ok")
        assert not _has_dollar(result), (
            "(e) no $ field allowed; result=%r" % result
        )

    def test_honest_note_in_freshness_result(self) -> None:
        result = evaluate_sport_freshness("nba", age_sec=60.0, snapshot_status="ok")
        assert result.get("honest_note"), "(e) honest_note must be non-empty"

    def test_edge_claimed_false_in_freshness_result(self) -> None:
        result = evaluate_sport_freshness("nba", age_sec=60.0, snapshot_status="ok")
        assert result.get("edge_claimed") is False, (
            "(e) edge_claimed must be False"
        )

    def test_no_dollar_in_scheduler_gap(self) -> None:
        result = evaluate_scheduler_gap(["nba"], [])
        assert not _has_dollar(result), (
            "(e) no $ in scheduler_gap result; got %r" % result
        )

    def test_honest_note_in_scheduler_gap(self) -> None:
        result = evaluate_scheduler_gap(["nba"], ["nba"])
        assert result.get("honest_note"), "(e) honest_note must be non-empty in gap result"

    def test_no_dollar_in_endpoint_response(self) -> None:
        """Integration: no $ field in /api/produce/status response."""
        fresh_env = _make_envelope(status="ok", age_sec=60.0)
        hb = {"sports_run": ["nba"], "updated_at": time.time()}
        body = _get_status({"nba": fresh_env}, heartbeat=hb, active=["nba"])
        assert not _has_dollar(body), (
            "(e) no $ field in endpoint response; keys=%r" % list(body.keys())
        )

    def test_honest_note_in_endpoint_response(self) -> None:
        """Integration: honest_note present in endpoint response."""
        fresh_env = _make_envelope(status="ok", age_sec=60.0)
        hb = {"sports_run": ["nba"], "updated_at": time.time()}
        body = _get_status({"nba": fresh_env}, heartbeat=hb, active=["nba"])
        assert body.get("honest_note"), (
            "(e) honest_note must be present in endpoint response"
        )
