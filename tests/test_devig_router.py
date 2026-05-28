"""Tests for the /api/devig endpoint and the new devig methods.

Covers:
- multiplicative_devig basic behaviour
- power_devig (n=2 case)
- shin_devig vs proportional on heavy favourites
- the devig() dispatcher across all four methods
- the POST /api/devig endpoint (pair form + n-way form + method param)
- prob_to_american round-trip via american_to_prob
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from src.prediction.devig import (
    american_to_prob,
    devig,
    multiplicative_devig,
    power_devig,
    prob_to_american,
    proportional_devig,
    shin_devig,
)


client = TestClient(app)


# ---------------------------------------------------------------------------
# Unit tests for the new pure-Python devig functions
# ---------------------------------------------------------------------------


def test_multiplicative_basic():
    """A pair of true even odds (+100 / +100) devigs to ~0.5/0.5."""
    pi = [american_to_prob(+100), american_to_prob(+100)]  # 0.5 / 0.5 — no vig
    out = multiplicative_devig(pi)
    assert sum(out) == pytest.approx(1.0, abs=1e-9)
    assert out[0] == pytest.approx(0.5, abs=1e-9)
    assert out[1] == pytest.approx(0.5, abs=1e-9)

    # And a real -110/-110 vigged pair should also devig to 0.5/0.5
    pi2 = [american_to_prob(-110), american_to_prob(-110)]
    out2 = multiplicative_devig(pi2)
    assert sum(out2) == pytest.approx(1.0, abs=1e-9)
    assert out2[0] == pytest.approx(0.5, abs=1e-6)
    assert out2[1] == pytest.approx(0.5, abs=1e-6)


def test_power_n2():
    """Power method on -110/-110 returns ~0.5/0.5 and sums to 1 exactly."""
    pi = [american_to_prob(-110), american_to_prob(-110)]
    out = power_devig(pi, n=2)
    assert sum(out) == pytest.approx(1.0, abs=1e-9)
    assert out[0] == pytest.approx(0.5, abs=1e-9)
    assert out[1] == pytest.approx(0.5, abs=1e-9)


def test_shin_heavy_favorite():
    """On -500/+350, Shin gives the favourite a HIGHER prob than proportional."""
    pi = [american_to_prob(-500), american_to_prob(+350)]
    shin = shin_devig(pi)
    prop = proportional_devig(pi)
    assert sum(shin) == pytest.approx(1.0, abs=1e-9)
    assert sum(prop) == pytest.approx(1.0, abs=1e-9)
    assert shin[0] > prop[0], (
        f"Shin favourite={shin[0]:.4f} should be > proportional={prop[0]:.4f}"
    )
    assert shin[1] < prop[1]


def test_devig_dispatcher():
    """All four methods via devig() return distributions summing to 1.0."""
    pi = [american_to_prob(-150), american_to_prob(+130)]
    for method in ("additive", "multiplicative", "power", "shin"):
        out = devig(pi, method=method)
        assert len(out) == 2, f"{method} returned wrong arity"
        assert sum(out) == pytest.approx(1.0, abs=1e-9), (
            f"{method} did not sum to 1.0 (got {sum(out)})"
        )
        assert all(0.0 < p < 1.0 for p in out), f"{method} produced out-of-range prob"


def test_devig_dispatcher_rejects_unknown_method():
    with pytest.raises(ValueError):
        devig([0.55, 0.5], method="bogus")


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


def test_devig_endpoint_pair():
    """POST with over_odds/under_odds returns 200 with valid fair_probs."""
    resp = client.post(
        "/api/devig",
        json={"over_odds": -150, "under_odds": 130},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["method"] == "shin"
    assert len(body["fair_probs"]) == 2
    assert sum(body["fair_probs"]) == pytest.approx(1.0, abs=1e-6)
    assert len(body["vigged"]) == 2
    assert len(body["fair_odds"]) == 2
    assert body["overround"] > 0


def test_devig_endpoint_nway():
    """POST with a 3-way odds list returns 3 fair_probs summing to 1.0."""
    resp = client.post(
        "/api/devig",
        json={"odds": [+150, +200, +250], "method": "proportional"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["fair_probs"]) == 3
    assert sum(body["fair_probs"]) == pytest.approx(1.0, abs=1e-6)


def test_devig_endpoint_method_param():
    """method='power' is honoured and produces a different result than shin."""
    pair = {"over_odds": -200, "under_odds": +170}
    shin_resp = client.post("/api/devig", json={**pair, "method": "shin"})
    power_resp = client.post("/api/devig", json={**pair, "method": "power"})
    assert shin_resp.status_code == 200
    assert power_resp.status_code == 200
    assert power_resp.json()["method"] == "power"
    # The methods should differ on a vigged favourite line.
    assert (
        shin_resp.json()["fair_probs"][0] != power_resp.json()["fair_probs"][0]
    )


def test_devig_endpoint_rejects_bad_method():
    resp = client.post(
        "/api/devig",
        json={"over_odds": -110, "under_odds": -110, "method": "bogus"},
    )
    assert resp.status_code == 400


def test_devig_endpoint_rejects_missing_inputs():
    resp = client.post("/api/devig", json={"method": "shin"})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# american_to_prob <-> prob_to_american round-trip
# ---------------------------------------------------------------------------


def test_prob_to_american_roundtrip():
    """american_to_prob(prob_to_american(0.5)) is ≈ 0.5."""
    for p in (0.5, 0.25, 0.75, 0.1, 0.9):
        odds = prob_to_american(p)
        back = american_to_prob(odds)
        assert back == pytest.approx(p, abs=2e-3), (
            f"round-trip failed for p={p}: odds={odds}, back={back}"
        )
