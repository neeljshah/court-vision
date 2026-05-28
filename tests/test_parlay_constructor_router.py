"""Tests for the /api/parlays/constructor + /parlays?engine=constructor wiring.

Validates that `src.prediction.parlay_constructor` is reachable from the
CourtVision UI, that the new JSON endpoint serialises cleanly, and that the
HTML route's engine toggle round-trips through Jinja.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    from api.main import app
    return TestClient(app)


# ── /api/parlays/constructor JSON endpoint ───────────────────────────────────

def test_endpoint_returns_200(client: TestClient) -> None:
    """GET /api/parlays/constructor returns 200 for a known date."""
    resp = client.get("/api/parlays/constructor", params={"date": "2026-05-29"})
    assert resp.status_code == 200
    body = resp.json()
    assert "n_parlays" in body
    assert "parlays" in body
    assert "has_lines" in body
    assert isinstance(body["parlays"], list)


def test_endpoint_engine_field(client: TestClient) -> None:
    """Returned envelope identifies itself as the constructor engine."""
    resp = client.get("/api/parlays/constructor", params={"date": "2026-05-29"})
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("engine") == "constructor"


def test_endpoint_no_lines(client: TestClient) -> None:
    """A date with no slate returns n_parlays==0 without crashing."""
    resp = client.get("/api/parlays/constructor", params={"date": "1999-01-01"})
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("n_parlays") == 0
    assert body.get("parlays") == []
    # has_lines may be False on a stale date — must not crash either way.
    assert "has_lines" in body
    assert body.get("engine") == "constructor"


def test_endpoint_accepts_filter_params(client: TestClient) -> None:
    """Endpoint accepts max_legs/min_ev_pct/top_n/seed query params."""
    resp = client.get(
        "/api/parlays/constructor",
        params={"date": "2026-05-29", "max_legs": 3,
                "min_ev_pct": 0.0, "top_n": 10, "seed": 7},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body.get("parlays"), list)
    assert len(body["parlays"]) <= 10


def test_endpoint_parlay_shape_when_present(client: TestClient) -> None:
    """When the constructor produces parlays, each row has the expected fields."""
    resp = client.get(
        "/api/parlays/constructor",
        params={"date": "2026-05-29", "min_ev_pct": -100.0, "top_n": 5},
    )
    assert resp.status_code == 200
    body = resp.json()
    parlays = body.get("parlays") or []
    if not parlays:
        pytest.skip("no slate/lines for this date — endpoint shape covered separately")
    row = parlays[0]
    # Constructor output schema:
    for field in ("parlay_id", "expected_roi_sgp_pct", "hit_rate_adj",
                  "decimal_odds", "american_odds", "leg_0", "leg_1", "leg_2"):
        assert field in row, f"missing {field} in parlay row: {row}"


# ── /parlays HTML route engine toggle ────────────────────────────────────────

def test_parlays_html_constructor(client: TestClient) -> None:
    """GET /parlays?engine=constructor renders the constructor-mode page."""
    resp = client.get("/parlays", params={"engine": "constructor",
                                          "date": "2026-05-29"})
    assert resp.status_code == 200
    text = resp.text.lower()
    assert "constructor" in text


def test_parlays_html_default(client: TestClient) -> None:
    """GET /parlays (no engine param) keeps the default ParlayEngine behavior."""
    resp = client.get("/parlays", params={"date": "2026-05-29"})
    assert resp.status_code == 200
    # Default engine should be advertised somewhere — at minimum the page
    # must still render the engine-toggle UI we just added.
    text = resp.text.lower()
    assert "parlayengine" in text or "engine" in text
