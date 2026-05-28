"""Tests for the /clv standalone HTML dashboard.

Verifies the page renders, the days query-param flows through, and the page
remains resilient when the daily_clv.csv sparkline source is missing.
"""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    from api.main import app
    return TestClient(app)


def test_clv_router_imports() -> None:
    """Plain import smoke — no FastAPI app required."""
    mod = importlib.import_module("api.clv_router")
    assert hasattr(mod, "router")
    assert hasattr(mod, "_read_daily_clv_csv")


def test_clv_page_returns_200(client: TestClient) -> None:
    res = client.get("/clv")
    assert res.status_code == 200
    assert res.headers.get("content-type", "").startswith("text/html")


def test_clv_page_renders_summary(client: TestClient) -> None:
    res = client.get("/clv")
    assert res.status_code == 200
    assert "Closing Line Value" in res.text


def test_clv_page_days_param(client: TestClient) -> None:
    res = client.get("/clv?days=7")
    assert res.status_code == 200
    assert "7" in res.text
    # The window-bar button and the headline both interpolate the days value.
    assert "last 7 days" in res.text


def test_clv_page_resilient_to_missing_data(monkeypatch, client: TestClient) -> None:
    """If daily_clv.csv is missing/unreadable, the page must still render."""
    import api.clv_router as clv_router_mod
    monkeypatch.setattr(clv_router_mod, "_read_daily_clv_csv", lambda days: [])
    res = client.get("/clv?days=30")
    assert res.status_code == 200
    assert "Closing Line Value" in res.text
