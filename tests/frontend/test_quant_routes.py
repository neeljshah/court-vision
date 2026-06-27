"""Offline tests for frontend.quant_routes -- the GET-only quant Execution API.

Mounts ONLY the quant router on a throwaway FastAPI app (never binds a real port,
never spawns the real stack) and asserts the transparency contract:
  * every endpoint returns 200,
  * NO $/roi/pnl/bankroll/profit/stake_dollars key anywhere in any response,
  * gate_proven defaults False on validation verdicts,
  * there is NO POST / placement path on this router,
  * arb is flagged descriptive (never promoted) and RoR is flagged descriptive
    (not a guarantee),
  * edge_claimed / real_money_enabled are stamped False.

Per-file run only:
    python -m pytest tests/frontend/test_quant_routes.py -q
"""
from __future__ import annotations

from typing import Any

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI                # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from frontend.quant_routes import router  # noqa: E402
from scripts.platformkit.quant_exec import build_validation, is_verified_gate_token  # noqa: E402

# Keys that must NEVER appear anywhere in a quant response (units only, no $).
_BANNED = {"roi", "pnl", "profit", "bankroll", "dollars", "stake_dollars",
           "usd", "cash", "money_won"}


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _walk(obj: Any):
    """Yield every (key, value) pair recursively through dicts/lists."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k), v
            yield from _walk(v)
    elif isinstance(obj, list):
        for it in obj:
            yield from _walk(it)


import re

# A $-AMOUNT is a '$' adjacent to a digit (e.g. $5, 10$). The retraction phrase
# "No $ edge is claimed" is ALLOWED (it is a disclaimer, not a money field), so we
# only flag $ when it quotes an actual amount.
_DOLLAR_AMOUNT = re.compile(r"\$\s*\d|\d\s*\$")


def _assert_no_dollar(body: Any) -> None:
    for k, v in _walk(body):
        kl = k.lower()
        assert "$" not in kl, "dollar key %r" % k
        assert kl not in _BANNED, "banned money key %r" % k
        # No $-AMOUNT in string values (the 'No $ edge' disclaimer is allowed).
        if isinstance(v, str):
            assert not _DOLLAR_AMOUNT.search(v), "dollar amount in value for %r" % k


def test_validate_endpoint_200_no_dollar_gate_false(client: TestClient) -> None:
    r = client.get("/api/quant/nba/validate")
    assert r.status_code == 200
    body = r.json()
    assert body["edge_claimed"] is False
    assert body["real_money_enabled"] is False
    _assert_no_dollar(body)
    # Every validation verdict defaults gate_proven False (no verified token wired).
    for g in body.get("games", []):
        for v in g.get("validations", []):
            assert v["gate_proven"] is False
            assert v["edge_claimed"] is False
            assert v["units"] == "probability"
            assert v["decision"] in ("bet", "no_bet")


def test_devig_endpoint_200_probability_only(client: TestClient) -> None:
    r = client.get("/api/quant/nba/devig")
    assert r.status_code == 200
    body = r.json()
    assert body["edge_claimed"] is False
    _assert_no_dollar(body)
    for g in body.get("games", []):
        for d in g.get("devig", []):
            p = d.get("consensus_fair_prob")
            assert p is None or 0.0 <= float(p) <= 1.0
            assert d.get("method") == "shin"


def test_arb_endpoint_flagged_descriptive_not_promoted(client: TestClient) -> None:
    r = client.get("/api/quant/nba/arb")
    assert r.status_code == 200
    body = r.json()
    assert body["arb_promoted"] is False
    assert body["arb_descriptive"] is True
    assert body["edge_claimed"] is False
    _assert_no_dollar(body)
    for g in body.get("games", []):
        for a in g.get("arb", []):
            assert a.get("promoted") is False
            assert a.get("descriptive") is True


def test_risk_endpoint_unit_space_ror_descriptive(client: TestClient) -> None:
    r = client.get("/api/quant/risk")
    assert r.status_code == 200
    body = r.json()
    assert body["ror_descriptive"] is True
    assert body["ror_is_guarantee"] is False
    assert body["edge_claimed"] is False
    assert body["real_money_enabled"] is False
    # exposure is a units field, never a $ field
    assert "total_exposure_units" in body
    _assert_no_dollar(body)


def test_clv_endpoint_vs_close_unproven(client: TestClient) -> None:
    r = client.get("/api/quant/clv")
    assert r.status_code == 200
    body = r.json()
    assert body["edge_claimed"] is False
    assert body["clv"]["vs_close_proven"] is False
    _assert_no_dollar(body)


def test_no_post_or_placement_path(client: TestClient) -> None:
    # The quant router exposes GET only -- a POST to any quant path must 405/404,
    # never place a bet. Placement stays on exec_routes (executed=False).
    for path in ("/api/quant/nba/validate", "/api/quant/risk", "/api/quant/clv",
                 "/api/quant/nba/place", "/api/quant/place"):
        resp = client.post(path, json={})
        assert resp.status_code in (404, 405), (path, resp.status_code)
    # Confirm no route on this router declares a POST method.
    for route in router.routes:
        methods = getattr(route, "methods", set()) or set()
        assert "POST" not in methods, getattr(route, "path", "?")


def test_build_validation_no_bet_is_success_default() -> None:
    # A model prob ON the devigged close clears no floor -> no_bet (the common,
    # honest outcome). gate_proven defaults False; no $ field in the record.
    v = build_validation(
        side="home", market="moneyline", model_prob=0.5,
        best_decimal=2.0, close_home=0.5, close_away=0.5)
    d = v.as_dict()
    assert d["decision"] == "no_bet"
    assert d["gate_proven"] is False
    assert d["units"] == "probability"
    assert "matches-the-close" in d["note"] or "no_bet" in d["note"]
    for k in d:
        assert "$" not in k and k.lower() not in _BANNED


def test_gate_proven_only_on_verified_token() -> None:
    assert is_verified_gate_token(None) is False
    assert is_verified_gate_token(True) is False
    assert is_verified_gate_token({"verified": True}) is False
    assert is_verified_gate_token({"passed": True}) is False
    assert is_verified_gate_token({"verified": True, "passed": True}) is True
    # A verified token flips gate_proven True on a verdict.
    v = build_validation(
        side="home", market="moneyline", model_prob=0.7,
        best_decimal=2.0, close_home=0.5, close_away=0.5,
        gate_token={"verified": True, "passed": True})
    assert v.gate_proven is True
