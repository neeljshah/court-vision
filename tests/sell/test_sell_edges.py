"""tests.sell.test_sell_edges -- per-file tests for sell edge + paper-place endpoints.

Tests
-----
Sell edge endpoints (/sell/v1/edges/{sport}, /sell/v1/edges/{sport}/{game_id}):
  * No key -> 401.
  * Invalid/forged key -> 401.
  * Free key -> 403 (live_edges not in free plan).
  * Pro key -> 200 deep edge view (store stubbed to return a real snapshot).
  * Enterprise key -> 200.
  * 200 response carries edge_claimed=false and honest_note.
  * 200 response has no $ / roi / profit / pnl field (recursive walk).
  * Per-game endpoint: pro key + known game_id -> 200 with game_id in body.
  * Per-game endpoint: unknown game_id -> 200 with status='unavailable'.
  * Usage recorded on authenticated call.

Paper-place endpoint (/sell/v1/paper/place):
  * No key -> 401.
  * Free key -> 403 (paper_place not in free plan).
  * Pro key + no live snapshot -> 400 rejected.

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/sell/test_sell_edges.py -q
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

_SECRET = "test-sell-edge-secret-not-for-production"

# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

def _no_dollar_keys(obj: Any, path: str = "") -> None:
    """Recursively assert that no key contains $, roi, profit, pnl, or bankroll."""
    BANNED = ("$", "roi", "profit", "pnl", "bankroll", "dollar")
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = k.lower()
            for tok in BANNED:
                assert tok not in kl, (
                    "Banned key %r found at %s.%s" % (tok, path, k))
            _no_dollar_keys(v, path + "." + k if path else k)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _no_dollar_keys(v, "%s[%d]" % (path, i))


def _key(plan: str) -> str:
    from sell.authz import issue_key
    return issue_key("edge-test-%s" % plan, plan, _secret=_SECRET)


def _auth(plan: str) -> Dict[str, str]:
    return {"Authorization": "Bearer %s" % _key(plan)}


# --------------------------------------------------------------------------- #
# Store stub                                                                   #
# --------------------------------------------------------------------------- #

def _make_stub_snapshot(sport: str = "nba") -> Any:
    """Build a minimal real SnapshotEnvelope so the edge view returns status='ok'."""
    from predict_service.contracts import (
        EdgeRow, MarketRow, PredictionRecord, SnapshotEnvelope,
    )
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    pred = PredictionRecord(
        sport=sport,
        game_id="G001",
        home="Home Team",
        away="Away Team",
        tipoff=now,
        pregame_probs={"home_ml": 0.60, "away_ml": 0.40},
        leak_guard={"in_sample": False},
    )
    market = MarketRow(
        sport=sport,
        game_id="G001",
        market_type="moneyline",
        side="home",
        line=None,
        odds=1.80,
        book="testbook",
        devigged_prob=0.57,
        captured_at=now,
        is_close=False,
        clv_is_proxy=True,
    )
    edge = EdgeRow(
        game_id="G001",
        market_type="moneyline",
        side="home",
        model_prob=0.60,
        market_prob=0.57,
        ev=0.08,
        tier="B",
        book="testbook",
        clv_is_proxy=True,
    )
    return SnapshotEnvelope(
        sport=sport,
        generated_at=now,
        status="ok",
        predictions=[pred],
        markets=[market],
        edges=[edge],
    )


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #

@pytest.fixture(autouse=True)
def _patch_secret(monkeypatch):
    monkeypatch.setenv("SELL_API_SECRET", _SECRET)


@pytest.fixture()
def stub_store(monkeypatch):
    """Stub predict_service.store.read_latest to return a valid snapshot."""
    import predict_service.store as _store
    import frontend.edge_api as _edge_api

    snap = _make_stub_snapshot("nba")

    def _fake_read(sport, out_dir=None):
        if sport == "nba":
            return snap
        from predict_service.contracts import SnapshotEnvelope
        return SnapshotEnvelope.unavailable(sport, reason="no stub for %s" % sport)

    monkeypatch.setattr(_store, "read_latest", _fake_read)
    monkeypatch.setattr(_edge_api, "read_latest", _fake_read)
    return snap


@pytest.fixture()
def client(stub_store):
    """TestClient with the store stubbed."""
    os.environ["SELL_API_SECRET"] = _SECRET
    from sell.serve_sell import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# --------------------------------------------------------------------------- #
# Authentication                                                                #
# --------------------------------------------------------------------------- #

class TestEdgeAuth:
    def test_no_key_401(self, client):
        r = client.get("/sell/v1/edges/nba")
        assert r.status_code == 401

    def test_invalid_key_401(self, client):
        r = client.get("/sell/v1/edges/nba",
                       headers={"Authorization": "Bearer not.a.real.key"})
        assert r.status_code == 401

    def test_forged_key_401(self, client):
        key = _key("pro")
        parts = key.rsplit(".", 1)
        mac = parts[1]
        bad = "0" if mac[-1] != "0" else "1"
        forged = parts[0] + "." + mac[:-1] + bad
        r = client.get("/sell/v1/edges/nba",
                       headers={"Authorization": "Bearer %s" % forged})
        assert r.status_code == 401

    def test_401_edge_claimed_false(self, client):
        r = client.get("/sell/v1/edges/nba")
        detail = r.json().get("detail", {})
        if isinstance(detail, dict):
            assert detail.get("edge_claimed") is False


# --------------------------------------------------------------------------- #
# Plan gating -- live_edges                                                    #
# --------------------------------------------------------------------------- #

class TestEdgePlanGating:
    def test_free_key_403(self, client):
        """Free plan cannot access live_edges."""
        r = client.get("/sell/v1/edges/nba", headers=_auth("free"))
        assert r.status_code == 403

    def test_pro_key_200(self, client):
        """Pro plan can access live_edges."""
        r = client.get("/sell/v1/edges/nba", headers=_auth("pro"))
        assert r.status_code == 200

    def test_enterprise_key_200(self, client):
        """Enterprise plan can access live_edges."""
        r = client.get("/sell/v1/edges/nba", headers=_auth("enterprise"))
        assert r.status_code == 200

    def test_403_edge_claimed_false(self, client):
        r = client.get("/sell/v1/edges/nba", headers=_auth("free"))
        detail = r.json().get("detail", {})
        if isinstance(detail, dict):
            assert detail.get("edge_claimed") is False


# --------------------------------------------------------------------------- #
# Response shape -- sport edge view                                             #
# --------------------------------------------------------------------------- #

class TestEdgeViewShape:
    def test_edge_claimed_false(self, client):
        body = client.get("/sell/v1/edges/nba", headers=_auth("pro")).json()
        assert body.get("edge_claimed") is False

    def test_has_honest_note(self, client):
        body = client.get("/sell/v1/edges/nba", headers=_auth("pro")).json()
        assert "honest_note" in body
        assert body["honest_note"]

    def test_no_dollar_keys(self, client):
        body = client.get("/sell/v1/edges/nba", headers=_auth("pro")).json()
        _no_dollar_keys(body)

    def test_status_ok(self, client):
        body = client.get("/sell/v1/edges/nba", headers=_auth("pro")).json()
        assert body.get("status") == "ok"

    def test_games_list(self, client):
        body = client.get("/sell/v1/edges/nba", headers=_auth("pro")).json()
        assert "games" in body
        assert isinstance(body["games"], list)

    def test_count_matches_games(self, client):
        body = client.get("/sell/v1/edges/nba", headers=_auth("pro")).json()
        assert body.get("count") == len(body.get("games", []))

    def test_game_has_comparison(self, client):
        body = client.get("/sell/v1/edges/nba", headers=_auth("pro")).json()
        games = body.get("games", [])
        if games:
            assert "comparison" in games[0]

    def test_x_edge_claimed_header(self, client):
        r = client.get("/sell/v1/edges/nba", headers=_auth("pro"))
        assert r.headers.get("x-edge-claimed", "").lower() == "false"

    def test_query_param_auth(self, client):
        r = client.get("/sell/v1/edges/nba", params={"api_key": _key("pro")})
        assert r.status_code == 200

    def test_unavailable_sport_no_crash(self, client):
        """Unknown sport returns status=unavailable not a crash."""
        r = client.get("/sell/v1/edges/tennis", headers=_auth("pro"))
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "unavailable"


# --------------------------------------------------------------------------- #
# Per-game endpoint                                                             #
# --------------------------------------------------------------------------- #

class TestGameEdge:
    def test_no_key_401(self, client):
        r = client.get("/sell/v1/edges/nba/G001")
        assert r.status_code == 401

    def test_free_key_403(self, client):
        r = client.get("/sell/v1/edges/nba/G001", headers=_auth("free"))
        assert r.status_code == 403

    def test_pro_key_200(self, client):
        r = client.get("/sell/v1/edges/nba/G001", headers=_auth("pro"))
        assert r.status_code == 200

    def test_known_game_id_in_body(self, client):
        body = client.get("/sell/v1/edges/nba/G001", headers=_auth("pro")).json()
        assert body.get("game_id") == "G001"

    def test_unknown_game_id_unavailable(self, client):
        body = client.get("/sell/v1/edges/nba/NO_SUCH_GAME",
                          headers=_auth("pro")).json()
        assert body.get("status") == "unavailable"

    def test_edge_claimed_false(self, client):
        body = client.get("/sell/v1/edges/nba/G001", headers=_auth("pro")).json()
        assert body.get("edge_claimed") is False

    def test_no_dollar_keys(self, client):
        body = client.get("/sell/v1/edges/nba/G001", headers=_auth("pro")).json()
        _no_dollar_keys(body)

    def test_has_model_block(self, client):
        body = client.get("/sell/v1/edges/nba/G001", headers=_auth("pro")).json()
        if body.get("status") == "ok":
            assert "model" in body


# --------------------------------------------------------------------------- #
# Paper-place endpoint                                                          #
# --------------------------------------------------------------------------- #

class TestSellPaperPlace:
    def test_no_key_401(self, client):
        r = client.post("/sell/v1/paper/place",
                        json={"sport": "nba", "game_id": "G001",
                              "market_type": "moneyline", "side": "home",
                              "book": "testbook", "taken_decimal": 1.80})
        assert r.status_code == 401

    def test_free_key_403(self, client):
        """Free plan cannot access paper_place."""
        r = client.post("/sell/v1/paper/place",
                        json={"sport": "nba", "game_id": "G001",
                              "market_type": "moneyline", "side": "home",
                              "book": "testbook", "taken_decimal": 1.80},
                        headers=_auth("free"))
        assert r.status_code == 403

    def test_pro_missing_fields_422(self, client):
        """Missing required fields -> 422."""
        r = client.post("/sell/v1/paper/place",
                        json={"sport": "nba"},
                        headers=_auth("pro"))
        assert r.status_code == 422

    def test_pro_bad_decimal_422(self, client):
        """taken_decimal <= 1.0 -> 422."""
        r = client.post("/sell/v1/paper/place",
                        json={"sport": "nba", "game_id": "G001",
                              "market_type": "moneyline", "side": "home",
                              "book": "testbook", "taken_decimal": 0.90},
                        headers=_auth("pro"))
        assert r.status_code == 422

    def test_pro_no_snapshot_400(self, client):
        """No live snapshot for sport -> 400 rejected."""
        r = client.post("/sell/v1/paper/place",
                        json={"sport": "tennis", "game_id": "G001",
                              "market_type": "moneyline", "side": "home",
                              "book": "testbook", "taken_decimal": 1.80},
                        headers=_auth("pro"))
        assert r.status_code == 400

    def test_pro_stale_line_400(self, client):
        """A line not in the live store is rejected 400."""
        r = client.post("/sell/v1/paper/place",
                        json={"sport": "nba", "game_id": "G001",
                              "market_type": "moneyline", "side": "home",
                              "book": "testbook", "taken_decimal": 9.99},
                        headers=_auth("pro"))
        assert r.status_code == 400

    def test_403_edge_claimed_false(self, client):
        r = client.post("/sell/v1/paper/place",
                        json={"sport": "nba", "game_id": "G001",
                              "market_type": "moneyline", "side": "home",
                              "book": "testbook", "taken_decimal": 1.80},
                        headers=_auth("free"))
        detail = r.json().get("detail", {})
        if isinstance(detail, dict):
            assert detail.get("edge_claimed") is False


# --------------------------------------------------------------------------- #
# Usage meter                                                                   #
# --------------------------------------------------------------------------- #

class TestUsageMeter:
    def test_edges_increments_meter(self, stub_store, monkeypatch, tmp_path):
        import sell.tenancy as _tenancy
        import sell.usage_meter as _meter

        monkeypatch.setattr(_tenancy, "TENANTS_ROOT", tmp_path)
        os.environ["SELL_API_SECRET"] = _SECRET

        from sell.serve_sell import app as _app
        with TestClient(_app) as c:
            tenant_id = "edge-meter-test-pro"
            from sell.authz import issue_key
            key = issue_key(tenant_id, "pro", _secret=_SECRET)
            c.get("/sell/v1/edges/nba",
                  headers={"Authorization": "Bearer %s" % key})

        ns = _tenancy.namespace_for(tenant_id, root=tmp_path)
        total = _meter.total_calls(tenant_id, _ns=ns)
        assert total >= 1, "usage meter did not increment for tenant %s" % tenant_id
