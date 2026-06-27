"""Offline tests for ops.status_endpoint (the /api/ops/* router).

Uses FastAPI's TestClient against a throwaway app with only the ops router
mounted -- never binds a real port, never spawns the real stack. Liveness is
faked via a monkeypatched snapshot so the routes return deterministic data.

Per-file run only:
    python -m pytest tests/ops/test_status_endpoint.py -q
"""
from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI               # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from ops import health_aggregator as agg  # noqa: E402
from ops import status_endpoint as se      # noqa: E402


def _fake_snapshot(live_map):
    return {
        comp: {"live": live, "age_sec": age, "path": "/fake/%s" % comp}
        for comp, (live, age) in live_map.items()
    }


@pytest.fixture
def client_all_live(monkeypatch):
    snap = _fake_snapshot({
        "predict_service_scheduler": (True, 5.0),
        "ingame_live_loop": (True, 10.0),
        "line_daemon": (True, 12.0),
        "paper_loop": (True, 20.0),
    })
    monkeypatch.setattr(agg._liveness, "liveness_snapshot", lambda **k: snap)
    app = FastAPI()
    assert se.mount(app) is True
    return TestClient(app)


@pytest.fixture
def client_critical_down(monkeypatch):
    snap = _fake_snapshot({
        "predict_service_scheduler": (False, None),  # critical down
        "ingame_live_loop": (True, 10.0),
        "line_daemon": (True, 12.0),
        "paper_loop": (True, 20.0),
    })
    monkeypatch.setattr(agg._liveness, "liveness_snapshot", lambda **k: snap)
    app = FastAPI()
    se.mount(app)
    return TestClient(app)


class TestStatusRoute:
    def test_status_ok(self, client_all_live):
        r = client_all_live.get("/api/ops/status")
        assert r.status_code == 200
        body = r.json()
        assert body["overall"] == "ok"
        names = {s["name"] for s in body["services"]}
        assert "m1_producer" in names

    def test_status_down_when_critical_down(self, client_critical_down):
        r = client_critical_down.get("/api/ops/status")
        assert r.status_code == 200
        assert r.json()["overall"] == "down"


class TestMetricsRoute:
    def test_metrics_shape(self, client_all_live):
        r = client_all_live.get("/api/ops/metrics")
        assert r.status_code == 200
        body = r.json()
        assert "clv" in body and "liveness" in body
        # no $ / ROI leak
        blob = r.text.lower()
        assert "roi" not in blob and "profit" not in blob


class TestDoctorRoute:
    def test_doctor_names_failing_service(self, client_critical_down):
        r = client_critical_down.get("/api/ops/doctor")
        assert r.status_code == 200
        body = r.json()
        assert body["overall"] == "down"
        names = {p["service"] for p in body["problems"]}
        assert "m1_producer" in names

    def test_doctor_all_ok(self, client_all_live):
        r = client_all_live.get("/api/ops/doctor")
        assert r.status_code == 200
        assert r.json()["overall"] == "ok"


class TestMountGuard:
    def test_mount_returns_bool(self):
        app = FastAPI()
        assert se.mount(app) is True
