"""Tests for the multi-book line scanner endpoint + UI page.

Routes under test:
  GET /api/lines/scan?date=...&stat=...&min_books=...&sort=...
  GET /scan
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app

_TEST_DATE = "2026-05-27"


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def scan_json(client):
    r = client.get(f"/api/lines/scan?date={_TEST_DATE}&min_books=1")
    assert r.status_code == 200, r.text
    return r.json()


def test_scan_endpoint_returns_200(client):
    r = client.get(f"/api/lines/scan?date={_TEST_DATE}")
    assert r.status_code == 200
    body = r.json()
    assert "date" in body
    assert "props" in body
    assert "n_props" in body


def test_scan_props_have_required_fields(scan_json):
    if scan_json["n_props"] == 0:
        pytest.skip("no props for test date — skipping field check")
    required = {"player", "stat", "line", "best_over", "best_under", "n_books"}
    for p in scan_json["props"]:
        missing = required - set(p.keys())
        assert not missing, f"prop missing fields: {missing} in {p}"


def test_scan_min_books_filter(client):
    a = client.get(f"/api/lines/scan?date={_TEST_DATE}&min_books=1").json()
    b = client.get(f"/api/lines/scan?date={_TEST_DATE}&min_books=10").json()
    if a["n_props"] == 0:
        pytest.skip("no props for test date — skipping filter check")
    # higher min_books → fewer or equal results
    assert b["n_props"] <= a["n_props"]


def test_scan_stat_filter(client):
    r = client.get(f"/api/lines/scan?date={_TEST_DATE}&stat=pts&min_books=1").json()
    if r["n_props"] == 0:
        pytest.skip("no pts props for test date — skipping stat filter check")
    for p in r["props"]:
        assert p["stat"] == "pts"


def test_scan_sort_by_edge_desc(client):
    r = client.get(f"/api/lines/scan?date={_TEST_DATE}&min_books=2&sort=edge").json()
    if r["n_props"] < 2:
        pytest.skip("need at least 2 props to check sort order")
    edges = [float(p.get("best_combined_edge") or 0) for p in r["props"]]
    assert edges[0] >= edges[-1], f"first edge {edges[0]} should be >= last {edges[-1]}"


def test_scan_html_page_loads(client):
    r = client.get(f"/scan?date={_TEST_DATE}")
    assert r.status_code == 200
    ctype = r.headers.get("content-type", "")
    assert "text/html" in ctype, f"unexpected content-type: {ctype}"
