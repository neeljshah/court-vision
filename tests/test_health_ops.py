"""Tests for /health/ops endpoint."""
import time

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from api.main import app  # noqa: E402

client = TestClient(app)

REQUIRED_KEYS = {
    "scraper_lag_min",
    "model_inference_ms_p95",
    "daily_bet_count",
    "clv_hit_rate",
    "drift_flags",
    "last_slate_duration_min",
    "uptime_hours",
}


def test_health_ops_returns_200():
    resp = client.get("/health/ops")
    assert resp.status_code == 200


def test_health_ops_schema():
    resp = client.get("/health/ops")
    body = resp.json()
    missing = REQUIRED_KEYS - set(body.keys())
    assert not missing, f"Missing keys: {missing}"


def test_health_ops_drift_flags_list():
    resp = client.get("/health/ops")
    body = resp.json()
    assert isinstance(body["drift_flags"], list)


def test_health_ops_under_100ms():
    t0 = time.perf_counter()
    client.get("/health/ops")
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 100, f"Response took {elapsed_ms:.1f}ms (limit 100ms)"
