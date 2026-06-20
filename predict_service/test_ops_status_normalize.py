"""predict_service.test_ops_status_normalize -- per-file test for W-OPS-STATUS-NORM.

Acceptance (QA iter6 2026-06-20):
  N1. Critical producer: live=True, fresh=null, age_sec>=SLA served by
      /api/ops/status reads DEGRADED/stale (NEVER ok), matching
      doctor_consensus_routes for the same input.
  N2. Genuinely fresh row (age_sec < SLA, fresh=null) still reads ok from
      /api/ops/status.
  N3. /api/ops/status response includes _normalized=True.
  N4. No $ field in /api/ops/status response.
  N5. normalize_rows and doctor build_diagnosis agree on overall for the same
      raw services[] rows (cross-face consistency check).

Run (per-file only)::
    cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/test_ops_status_normalize.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Repo root on path.
# ---------------------------------------------------------------------------
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except ImportError:
    pytest.skip("fastapi/httpx not installed", allow_module_level=True)

from predict_service.status_freshness_normalizer import normalize_rows


# ---------------------------------------------------------------------------
# Helpers -- build a minimal app with only the ops status route mounted.
# ---------------------------------------------------------------------------

def _make_app(raw_agg_return: Dict[str, Any]) -> FastAPI:
    """Build a bare FastAPI app with _mount_ops wired to a mocked aggregator."""
    app = FastAPI()

    # Patch health_aggregator.aggregate so the route never touches the filesystem.
    with patch(
        "ops.health_aggregator.aggregate",
        return_value=raw_agg_return,
    ):
        from predict_service.core_mounts import _mount_ops  # noqa: PLC0415
        _mount_ops(app)

    return app


def _client(raw_agg_return: Dict[str, Any]) -> TestClient:
    return TestClient(_make_app(raw_agg_return), raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Shared fixtures.
# ---------------------------------------------------------------------------

_SLA = 300.0  # same default used by normalize_rows in _mount_ops


def _stale_critical_row() -> Dict[str, Any]:
    """Row that mimics m1_producer: live=True, fresh=null, age_sec >= SLA."""
    return {
        "name": "m1_producer",
        "critical": True,
        "live": True,
        "fresh": None,
        "age_sec": 548.0,   # > 300 SLA
        "breaker": None,
        "last_seen": None,
        "port": None,
        "reason": None,
    }


def _fresh_row() -> Dict[str, Any]:
    """Row that is genuinely fresh: age_sec well under SLA."""
    return {
        "name": "m1_api_paper",
        "critical": True,
        "live": True,
        "fresh": None,
        "age_sec": 45.0,    # < 300 SLA
        "breaker": None,
        "last_seen": None,
        "port": None,
        "reason": None,
    }


# ---------------------------------------------------------------------------
# N1 -- Critical stale producer reads DEGRADED/stale on /api/ops/status.
# ---------------------------------------------------------------------------

def test_n1_stale_critical_row_reads_degraded_on_status_endpoint():
    """N1: live=True fresh=null age>=SLA -> NEVER ok on /api/ops/status."""
    raw = {
        "generated_at": "2026-06-20T00:00:00Z",
        "overall": "ok",           # raw says ok -- normalization must override
        "services": [_stale_critical_row()],
        "notes": [],
    }
    with patch("ops.health_aggregator.aggregate", return_value=raw):
        from predict_service.core_mounts import _mount_ops  # noqa: PLC0415
        app = FastAPI()
        _mount_ops(app)
        client = TestClient(app)
        resp = client.get("/api/ops/status")

    assert resp.status_code == 200, "N1: endpoint must return 200"
    body = resp.json()

    # The overall must NOT be ok.
    assert body.get("overall") != "ok", (
        "N1: overall must be DEGRADED/down when critical service is stale; "
        "got overall=%r" % body.get("overall")
    )

    # The individual row must be stale.
    services: List[Dict[str, Any]] = body.get("services") or []
    assert services, "N1: services list must be non-empty"
    m1_row = next((s for s in services if s.get("name") == "m1_producer"), None)
    assert m1_row is not None, "N1: m1_producer row must be present"
    assert m1_row.get("fresh") == "stale", (
        "N1: m1_producer fresh must be 'stale' after normalization; "
        "got fresh=%r" % m1_row.get("fresh")
    )
    assert m1_row.get("ok") is False, "N1: m1_producer ok must be False"


# ---------------------------------------------------------------------------
# N2 -- Fresh row still reads ok after normalization.
# ---------------------------------------------------------------------------

def test_n2_fresh_row_still_reads_ok():
    """N2: age_sec < SLA with fresh=null -> fresh after normalization; ok=True."""
    raw = {
        "generated_at": "2026-06-20T00:00:00Z",
        "overall": "ok",
        "services": [_fresh_row()],
        "notes": [],
    }
    with patch("ops.health_aggregator.aggregate", return_value=raw):
        from predict_service.core_mounts import _mount_ops  # noqa: PLC0415
        app = FastAPI()
        _mount_ops(app)
        client = TestClient(app)
        resp = client.get("/api/ops/status")

    assert resp.status_code == 200
    body = resp.json()
    services = body.get("services") or []
    row = next((s for s in services if s.get("name") == "m1_api_paper"), None)
    assert row is not None, "N2: m1_api_paper row must be present"
    assert row.get("fresh") == "fresh", (
        "N2: age=45 < SLA=300 must yield fresh; got %r" % row.get("fresh")
    )
    assert row.get("ok") is True, "N2: ok must be True for fresh row"
    assert body.get("overall") == "ok", "N2: overall must be ok when all rows fresh"


# ---------------------------------------------------------------------------
# N3 -- _normalized flag present.
# ---------------------------------------------------------------------------

def test_n3_normalized_flag_present():
    """N3: /api/ops/status response includes _normalized=True."""
    raw = {
        "generated_at": "2026-06-20T00:00:00Z",
        "overall": "ok",
        "services": [_fresh_row()],
        "notes": [],
    }
    with patch("ops.health_aggregator.aggregate", return_value=raw):
        from predict_service.core_mounts import _mount_ops  # noqa: PLC0415
        app = FastAPI()
        _mount_ops(app)
        client = TestClient(app)
        resp = client.get("/api/ops/status")

    body = resp.json()
    assert body.get("_normalized") is True, "N3: _normalized must be True"


# ---------------------------------------------------------------------------
# N4 -- No $ field in response.
# ---------------------------------------------------------------------------

def _contains_dollar(obj: Any) -> bool:
    if isinstance(obj, dict):
        return any("$" in str(k) or _contains_dollar(v) for k, v in obj.items())
    if isinstance(obj, list):
        return any(_contains_dollar(i) for i in obj)
    return False


def test_n4_no_dollar_field():
    """N4: no $ field in /api/ops/status response."""
    raw = {
        "generated_at": "2026-06-20T00:00:00Z",
        "overall": "ok",
        "services": [_stale_critical_row()],
        "notes": [],
    }
    with patch("ops.health_aggregator.aggregate", return_value=raw):
        from predict_service.core_mounts import _mount_ops  # noqa: PLC0415
        app = FastAPI()
        _mount_ops(app)
        client = TestClient(app)
        resp = client.get("/api/ops/status")

    body = resp.json()
    assert not _contains_dollar(body), "N4: no $ key anywhere in response"


# ---------------------------------------------------------------------------
# N5 -- normalize_rows and doctor build_diagnosis agree on overall for same
#        raw services[] input (cross-face consistency).
# ---------------------------------------------------------------------------

def test_n5_status_and_doctor_agree_on_stale_critical():
    """N5: normalize_rows (status face) and build_diagnosis (doctor face) agree."""
    from predict_service.frontend.doctor_consensus_routes import build_diagnosis  # noqa: PLC0415

    raw_rows = [_stale_critical_row()]

    # status face: normalize_rows.
    norm = normalize_rows(raw_rows, default_sla_sec=_SLA)
    status_overall = norm.get("overall")

    # doctor face: build_diagnosis.
    diag = build_diagnosis(services=raw_rows, sla_sec=_SLA)
    doctor_overall = diag.get("overall")

    # Both must be non-ok (they need not be identical strings, but both must
    # agree that a stale critical service is not healthy).
    assert status_overall != "ok", (
        "N5: status normalize_rows overall must not be ok for stale critical; "
        "got %r" % status_overall
    )
    assert doctor_overall != "ok", (
        "N5: doctor build_diagnosis overall must not be ok for stale critical; "
        "got %r" % doctor_overall
    )


def test_n5_status_and_doctor_agree_on_fresh():
    """N5b: both faces agree fresh service is ok."""
    from predict_service.frontend.doctor_consensus_routes import build_diagnosis  # noqa: PLC0415

    raw_rows = [_fresh_row()]

    norm = normalize_rows(raw_rows, default_sla_sec=_SLA)
    status_overall = norm.get("overall")

    diag = build_diagnosis(services=raw_rows, sla_sec=_SLA)
    doctor_overall = diag.get("overall")

    assert status_overall == "ok", (
        "N5b: status face should be ok for fresh row; got %r" % status_overall
    )
    assert doctor_overall == "ok", (
        "N5b: doctor face should be ok for fresh row; got %r" % doctor_overall
    )
