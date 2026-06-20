"""predict_service.test_core_mounts_ops_status -- per-file test for iter-3 P0 fix.

Acceptance criteria:
  GET /api/ops/status must ALWAYS return:
    - _normalized=True
    - overall derived by normalize_rows (never a false 'ok' when services are stale)

The bug: ops.status_endpoint router's /api/ops/status route could shadow the direct
normalized handler in core_mounts._mount_ops, returning the raw aggregate's overall='ok'
with _normalized=None even though normalize_rows correctly derives 'degraded'.

The fix: strip /api/ops/status (and /api/ops/doctor) from the ops router before
include_router so only the direct handlers own those paths.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/test_core_mounts_ops_status.py -q

INVARIANTS: ASCII only; no $ field; stale-never-green; per-file test only; <=300 LOC.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import predict_service.core_mounts as core_mounts
from predict_service.status_freshness_normalizer import normalize_rows


# ---------------------------------------------------------------------------
# Helpers to build controlled stale-service aggregates.
# ---------------------------------------------------------------------------

def _stale_row(name: str, age_sec: float = 600.0) -> Dict[str, Any]:
    """A service row with fresh=null and age >= SLA (should normalize to stale)."""
    return {
        "name": name,
        "critical": True,
        "live": True,
        "fresh": None,       # null -- the raw aggregator emits this for many services
        "age_sec": age_sec,  # >= 300s SLA -> stale
        "port": None,
    }


def _stale_aggregate(n_stale: int = 9) -> Dict[str, Any]:
    """Return a raw aggregate dict that normalize_rows would degrade to 'degraded'."""
    return {
        "generated_at": "2026-06-20T00:00:00Z",
        "overall": "ok",           # raw aggregator says ok -- this is the bug vector
        "_normalized": None,       # not yet normalized
        "services": [_stale_row("svc_%d" % i, age_sec=600.0) for i in range(n_stale)],
        "notes": [],
    }


def _build_app_with_stale_aggregate(n_stale: int = 9) -> FastAPI:
    """Build a FastAPI test app via core_mounts.register, with a mocked aggregate."""
    agg_data = _stale_aggregate(n_stale)

    app = FastAPI()
    with patch("ops.health_aggregator.aggregate", return_value=agg_data):
        core_mounts.register(app)
    return app


# ---------------------------------------------------------------------------
# Test 1: normalized=True is always present.
# ---------------------------------------------------------------------------

class TestOpsStatusNormalized:
    """GET /api/ops/status must always carry _normalized=True."""

    def test_normalized_flag_true(self) -> None:
        app = _build_app_with_stale_aggregate(n_stale=9)
        client = TestClient(app)

        # We patch aggregate at request time too (the handler calls it lazily).
        with patch("ops.health_aggregator.aggregate", return_value=_stale_aggregate(9)):
            resp = client.get("/api/ops/status")

        assert resp.status_code == 200, "expected 200, got %d" % resp.status_code
        body = resp.json()
        assert body.get("_normalized") is True, (
            "_normalized must be True; got %r. "
            "This means the raw ops router handler is winning, not the normalized one." % body.get("_normalized")
        )

    def test_normalized_flag_not_none(self) -> None:
        """_normalized=None means the raw ops_status handler ran (the bug)."""
        app = _build_app_with_stale_aggregate(n_stale=3)
        client = TestClient(app)

        with patch("ops.health_aggregator.aggregate", return_value=_stale_aggregate(3)):
            resp = client.get("/api/ops/status")

        body = resp.json()
        assert body.get("_normalized") is not None, (
            "_normalized must not be None; the raw ops router handler is shadowing the "
            "normalized direct handler."
        )


# ---------------------------------------------------------------------------
# Test 2: overall must match normalize_rows (never a false 'ok' with stale rows).
# ---------------------------------------------------------------------------

class TestOpsStatusOverallMatchesNormalizer:
    """overall field must match what normalize_rows derives, never a false 'ok'."""

    def test_stale_rows_yield_degraded_overall(self) -> None:
        """9 stale services -> normalize_rows -> 'degraded'; endpoint must agree."""
        raw = _stale_aggregate(n_stale=9)
        expected_overall = normalize_rows(raw["services"], default_sla_sec=300.0)["overall"]
        assert expected_overall in ("degraded", "down"), (
            "test fixture: expected normalize_rows to degrade, got %r" % expected_overall
        )

        app = FastAPI()
        with patch("ops.health_aggregator.aggregate", return_value=raw):
            core_mounts.register(app)

        client = TestClient(app)
        with patch("ops.health_aggregator.aggregate", return_value=raw):
            resp = client.get("/api/ops/status")

        body = resp.json()
        got_overall = body.get("overall")
        assert got_overall == expected_overall, (
            "overall mismatch: endpoint returned %r but normalize_rows says %r. "
            "Raw aggregate had overall='ok' -- the normalized handler must override it."
            % (got_overall, expected_overall)
        )

    def test_no_false_ok_with_stale_services(self) -> None:
        """overall must never be 'ok' when services contain stale rows."""
        raw = _stale_aggregate(n_stale=5)
        # Sanity check: raw would be 'ok' if the bug were present.
        assert raw["overall"] == "ok", "test fixture invariant: raw overall should be 'ok'"

        app = FastAPI()
        with patch("ops.health_aggregator.aggregate", return_value=raw):
            core_mounts.register(app)

        client = TestClient(app)
        with patch("ops.health_aggregator.aggregate", return_value=raw):
            resp = client.get("/api/ops/status")

        body = resp.json()
        assert body.get("overall") != "ok", (
            "FALSE 'ok': endpoint returned overall='ok' with %d stale services. "
            "The normalized handler must be the resolved route, not the raw ops router."
            % len(raw["services"])
        )

    def test_overall_never_ok_when_any_row_stale(self) -> None:
        """Even a single stale critical service must not yield overall='ok'."""
        raw: Dict[str, Any] = {
            "generated_at": "2026-06-20T00:00:00Z",
            "overall": "ok",
            "_normalized": None,
            "services": [_stale_row("single_stale", age_sec=9999.0)],
            "notes": [],
        }

        app = FastAPI()
        with patch("ops.health_aggregator.aggregate", return_value=raw):
            core_mounts.register(app)

        client = TestClient(app)
        with patch("ops.health_aggregator.aggregate", return_value=raw):
            resp = client.get("/api/ops/status")

        body = resp.json()
        assert body.get("overall") != "ok", (
            "A single stale service must degrade overall away from 'ok'; got 'ok'."
        )
        assert body.get("_normalized") is True, (
            "_normalized must be True even for single-stale case."
        )


# ---------------------------------------------------------------------------
# Test 3: Confirm the ops router's /api/ops/status is stripped (no duplicate).
# ---------------------------------------------------------------------------

class TestOpsRouterStatusStripped:
    """The ops router's /api/ops/status route must not appear in app.routes."""

    def test_only_one_ops_status_route(self) -> None:
        app = FastAPI()
        with patch("ops.health_aggregator.aggregate", return_value=_stale_aggregate(1)):
            core_mounts.register(app)

        ops_status_routes = [
            r for r in app.routes
            if getattr(r, "path", None) == "/api/ops/status"
        ]
        assert len(ops_status_routes) == 1, (
            "Expected exactly 1 route for /api/ops/status, found %d: %s. "
            "The ops router's /api/ops/status must be stripped before include_router."
            % (len(ops_status_routes), [getattr(r, "name", "?") for r in ops_status_routes])
        )

    def test_normalized_handler_is_the_registered_route(self) -> None:
        app = FastAPI()
        with patch("ops.health_aggregator.aggregate", return_value=_stale_aggregate(1)):
            core_mounts.register(app)

        ops_status_routes = [
            r for r in app.routes
            if getattr(r, "path", None) == "/api/ops/status"
        ]
        assert ops_status_routes, "No /api/ops/status route found in app.routes"
        handler_name = getattr(ops_status_routes[0], "name", "")
        # The direct normalized handler is named _ops_status_normalized.
        assert "_normalized" in handler_name, (
            "The /api/ops/status route should be the normalized handler "
            "(_ops_status_normalized), found: %r" % handler_name
        )

    def test_metrics_route_still_present(self) -> None:
        """Stripping status/doctor must not remove /api/ops/metrics."""
        app = FastAPI()
        with patch("ops.health_aggregator.aggregate", return_value=_stale_aggregate(1)):
            core_mounts.register(app)

        metrics_routes = [
            r for r in app.routes
            if getattr(r, "path", None) == "/api/ops/metrics"
        ]
        assert metrics_routes, (
            "/api/ops/metrics must still be present after stripping /api/ops/status "
            "from the ops router."
        )


# ---------------------------------------------------------------------------
# Test 4: Consistency -- status agrees with normalize_rows reference impl.
# ---------------------------------------------------------------------------

class TestOpsStatusConsistencyWithNormalizer:
    """The endpoint and the normalizer must agree on overall for any input."""

    def _roundtrip(self, raw: Dict[str, Any]) -> str:
        app = FastAPI()
        with patch("ops.health_aggregator.aggregate", return_value=raw):
            core_mounts.register(app)
        client = TestClient(app)
        with patch("ops.health_aggregator.aggregate", return_value=raw):
            resp = client.get("/api/ops/status")
        assert resp.status_code == 200
        return resp.json().get("overall")

    def test_all_stale_matches_normalizer(self) -> None:
        raw = _stale_aggregate(n_stale=17)
        expected = normalize_rows(raw["services"], default_sla_sec=300.0)["overall"]
        got = self._roundtrip(raw)
        assert got == expected, "all-stale: endpoint=%r normalizer=%r" % (got, expected)

    def test_empty_services_matches_normalizer(self) -> None:
        raw: Dict[str, Any] = {
            "generated_at": "2026-06-20T00:00:00Z",
            "overall": "ok",
            "_normalized": None,
            "services": [],
            "notes": [],
        }
        expected = normalize_rows([], default_sla_sec=300.0)["overall"]
        got = self._roundtrip(raw)
        # Both must agree (empty = degraded per stale-never-green invariant).
        assert got == expected, "empty: endpoint=%r normalizer=%r" % (got, expected)
