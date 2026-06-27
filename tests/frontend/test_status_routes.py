"""Offline tests for frontend.status_routes (the /api/improve/status +
/api/parity routers the P6 dashboard reads).

Uses FastAPI's TestClient against a throwaway app with only the status router
mounted -- never binds a real port, never spawns the real stack. These assert
the read-only observability contract the CourtVision P6 UI depends on, plus the
no-$ / edge_claimed=False invariant.

Per-file run only:
    python -m pytest tests/frontend/test_status_routes.py -q
"""
from __future__ import annotations

import json

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI               # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from frontend.status_routes import router  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_improve_status_shape(client: TestClient) -> None:
    r = client.get("/api/improve/status")
    assert r.status_code == 200
    body = r.json()
    # Contract keys the RatchetPanel renders.
    for key in ("status", "ratchet", "kinds", "honest_note", "edge_claimed"):
        assert key in body, key
    assert body["edge_claimed"] is False
    assert isinstance(body["kinds"], list)
    assert "state" in body["ratchet"]
    # A fresh box (no calib artifacts) must degrade honestly, never fabricate.
    for k in body["kinds"]:
        assert "kind" in k and "current_version" in k


def test_parity_shape(client: TestClient) -> None:
    r = client.get("/api/parity")
    assert r.status_code in (200, 503)
    body = r.json()
    assert "status" in body
    assert body.get("edge_claimed") is False
    # When ok, every row carries a cells map the ParityGrid renders.
    if body["status"] == "ok":
        assert isinstance(body["dimensions"], list) and body["dimensions"]
        assert isinstance(body["sports"], list)
        for row in body["sports"]:
            assert "sport" in row and "cells" in row
            for cell in row["cells"].values():
                assert "status" in cell


def test_no_dollar_field_anywhere(client: TestClient) -> None:
    """Neither endpoint may emit a $ / dollar / usd / roi money field."""
    for path in ("/api/improve/status", "/api/parity"):
        raw = json.dumps(client.get(path).json()).lower()
        for forbidden in ('"$"', '"usd"', '"dollars"', '"roi"', '"profit"'):
            assert forbidden not in raw, (path, forbidden)
