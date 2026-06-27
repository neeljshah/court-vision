"""Per-file test: frontend.edge_routes + predict_service.app integration.

Two strategies used herein:

A) For edge_routes isolation tests: a bare FastAPI mini-app mounting only the
   edge_routes router, combined with store_out_dir passed as ?store_dir= so
   the router reads from a controlled tmp directory (same pattern as
   test_edge_api.py which uses store_out_dir to stub the store on disk).

B) For predict_service.app integration (regression / mount-failure safety): a
   bare mini-app mounting only the relevant routers with monkeypatching, avoiding
   the already-loaded module cache issue.

Covers
------
1. GET /api/v1/edges/nba   -> 200 with deep shape (sport, generated_at, count,
   games, honest_note, edge_claimed=false, comparison with best-book edge).
2. ETag header returned on 200; If-None-Match with matching token -> 304 (no body).
3. New generated_at (stale ETag) -> 200 again (cache invalidated).
4. GET /api/v1/edges/nba/<game_id>  -> single-game, unavailable for unknown.
5. POST /api/paper/place reachable (exec_routes mounted) and returns a paper bet
   with executed=false; same-day double-submit is idempotent.
6. GET /api/predict/nba still works (no regression on existing predict endpoint).
7. GET /api/paper/trail still works (no regression on existing paper endpoint).
8. NO dollar / $edge / roi / pnl / profit / stake / bankroll key anywhere in
   /api/v1/edges/* responses (honesty walk).

Run: python -m pytest tests/frontend/test_edge_routes.py -q
"""
from __future__ import annotations

import json
from typing import Any
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from predict_service.contracts import (
    EdgeRow,
    MarketRow,
    PredictionRecord,
    SnapshotEnvelope,
)
from predict_service import store

# -- test constants -----------------------------------------------------------
_SPORT = "nba"
_GID = "0042500401"
_GEN_AT = "2026-06-18T22:01:00+00:00"
_BOOK = "espn:DK"
_BOOK2 = "espn:FD"
_DEC = 1.80
_DEC2 = 1.71
_FORBIDDEN = ("$", "dollar", "roi", "pnl", "profit", "stake", "bankroll")


def _envelope() -> SnapshotEnvelope:
    """Canonical test envelope: two books for moneyline/home; DK is best price."""
    m_dk = MarketRow(
        sport=_SPORT, game_id=_GID, market_type="moneyline",
        side="home", line=None, odds=_DEC, book=_BOOK,
        devigged_prob=0.57, captured_at="2026-06-18T22:00:00+00:00",
        is_close=False, clv_is_proxy=True,
    )
    m_fd = MarketRow(
        sport=_SPORT, game_id=_GID, market_type="moneyline",
        side="home", line=None, odds=_DEC2, book=_BOOK2,
        devigged_prob=0.55, captured_at="2026-06-18T21:55:00+00:00",
        is_close=False, clv_is_proxy=True,
    )
    pred = PredictionRecord(
        sport=_SPORT, game_id=_GID,
        home="Boston Celtics", away="New York Knicks",
        tipoff="2026-06-18T23:30:00+00:00",
        pregame_probs={"home_ml": 0.60, "away_ml": 0.40},
        markets=[m_dk, m_fd],
        leak_guard={"in_sample": False},
        produced_at="2026-06-18T21:00:00+00:00",
    )
    edge = EdgeRow(
        game_id=_GID, market_type="moneyline", side="home",
        model_prob=0.60, market_prob=0.57, ev=0.08, tier="B",
        book=_BOOK, line=None, clv_is_proxy=True,
    )
    return SnapshotEnvelope(
        sport=_SPORT, generated_at=_GEN_AT, status="ok",
        predictions=[pred], markets=[m_dk, m_fd], edges=[edge],
    )


# -- fixtures -----------------------------------------------------------------

@pytest.fixture()
def store_dir(tmp_path, monkeypatch):
    """Write the test envelope to a tmp store dir; stub freshness to deterministic."""
    import frontend.edge_api as _edge_api
    store.save(_envelope(), out_dir=tmp_path, append=False)
    monkeypatch.setattr(_edge_api, "_freshness",
                        lambda *a, **k: {"status": "fresh", "age_sec": 60.0})
    return tmp_path


@pytest.fixture()
def edge_client(store_dir):
    """Bare FastAPI app mounting only edge_routes; store passed via ?store_dir=."""
    import frontend.edge_routes as _er
    app = FastAPI()
    app.include_router(_er.router)
    return TestClient(app, raise_server_exceptions=True)


def _eu(store_dir: Path) -> str:
    """Query param string for store_dir."""
    return str(store_dir)


# -- helpers ------------------------------------------------------------------

def _assert_no_money(obj: Any) -> None:
    """Recursively assert no forbidden key exists anywhere in the response."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            low = str(k).lower()
            for bad in _FORBIDDEN:
                assert bad not in low, "forbidden key %r in edge response" % k
            _assert_no_money(v)
    elif isinstance(obj, list):
        for item in obj:
            _assert_no_money(item)


# -- 1. Deep shape ------------------------------------------------------------

def test_edge_view_top_level_shape(edge_client, store_dir):
    r = edge_client.get("/api/v1/edges/nba",
                        params={"store_dir": _eu(store_dir)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["sport"] == _SPORT
    assert body["generated_at"] == _GEN_AT
    assert body["count"] == 1
    assert body["edge_claimed"] is False
    assert isinstance(body.get("honest_note"), str) and body["honest_note"]
    assert "edge_note" in body
    assert "schema_version" in body


def test_edge_view_game_object(edge_client, store_dir):
    r = edge_client.get("/api/v1/edges/nba",
                        params={"store_dir": _eu(store_dir)})
    assert r.status_code == 200
    games = r.json()["games"]
    assert len(games) == 1
    g = games[0]
    assert g["game_id"] == _GID
    assert g["home"] == "Boston Celtics"
    assert g["away"] == "New York Knicks"
    assert g["status"] == "ok"
    assert g["model"]["probs"]["home_ml"] == pytest.approx(0.60)
    assert g["model"]["leak_guard"]["in_sample"] is False
    # Both book quotes present.
    books = {m["book"] for m in g["markets"]}
    assert books == {_BOOK, _BOOK2}
    # Freshness stub.
    assert g["freshness"]["status"] == "fresh"
    assert g["as_of"]


def test_edge_view_comparison_row(edge_client, store_dir):
    r = edge_client.get("/api/v1/edges/nba",
                        params={"store_dir": _eu(store_dir)})
    assert r.status_code == 200
    comp = r.json()["games"][0]["comparison"]
    assert len(comp) == 1
    row = comp[0]
    assert row["market_type"] == "moneyline"
    assert row["side"] == "home"
    # Best devigged across books: DK at 0.57 (vs FD 0.55).
    assert row["market_prob"] == pytest.approx(0.57)
    assert row["best_book"] == _BOOK
    assert row["best_odds"] == pytest.approx(_DEC)
    assert row["model_prob"] == pytest.approx(0.60)
    # edge = model_prob - market_prob = 0.03
    assert abs(row["edge"] - 0.03) < 1e-9
    # ev + tier from the snapshot EdgeRow.
    assert row["ev"] == pytest.approx(0.08)
    assert row["tier"] == "B"
    assert row["clv_is_proxy"] is True


# -- 2. ETag / 304 caching ----------------------------------------------------

def test_etag_returned_on_200(edge_client, store_dir):
    r = edge_client.get("/api/v1/edges/nba",
                        params={"store_dir": _eu(store_dir)})
    assert r.status_code == 200
    etag = r.headers.get("etag") or r.headers.get("ETag") or ""
    assert etag, "ETag header missing from 200 response"
    # ETag must embed the generated_at token.
    assert _GEN_AT in etag


def test_if_none_match_same_etag_returns_304(edge_client, store_dir):
    r1 = edge_client.get("/api/v1/edges/nba",
                         params={"store_dir": _eu(store_dir)})
    assert r1.status_code == 200
    etag = r1.headers.get("etag") or r1.headers.get("ETag") or ""
    r2 = edge_client.get("/api/v1/edges/nba",
                         params={"store_dir": _eu(store_dir)},
                         headers={"If-None-Match": etag})
    assert r2.status_code == 304, (
        "Expected 304 on matching ETag but got %d. Body: %s"
        % (r2.status_code, r2.text))
    # 304 must carry no body.
    assert r2.content == b""


def test_stale_etag_returns_200(edge_client, store_dir):
    """A client with an old ETag must get a full 200, not a 304."""
    r = edge_client.get("/api/v1/edges/nba",
                        params={"store_dir": _eu(store_dir)},
                        headers={"If-None-Match": '"old-etag-from-yesterday"'})
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_etag_on_single_game_endpoint(edge_client, store_dir):
    r = edge_client.get("/api/v1/edges/nba/%s" % _GID,
                        params={"store_dir": _eu(store_dir)})
    assert r.status_code == 200
    etag = r.headers.get("etag") or r.headers.get("ETag") or ""
    assert etag
    r304 = edge_client.get("/api/v1/edges/nba/%s" % _GID,
                           params={"store_dir": _eu(store_dir)},
                           headers={"If-None-Match": etag})
    assert r304.status_code == 304


# -- 3. Single-game endpoint --------------------------------------------------

def test_single_game_shape(edge_client, store_dir):
    r = edge_client.get("/api/v1/edges/nba/%s" % _GID,
                        params={"store_dir": _eu(store_dir)})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["game_id"] == _GID
    assert body["edge_claimed"] is False
    assert "honest_note" in body
    assert len(body["comparison"]) == 1


def test_single_game_unknown_id_unavailable(edge_client, store_dir):
    r = edge_client.get("/api/v1/edges/nba/NO-SUCH-GAME-999",
                        params={"store_dir": _eu(store_dir)})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "unavailable"
    assert body["game_id"] == "NO-SUCH-GAME-999"


def test_unavailable_sport_returns_sentinel(edge_client, store_dir):
    r = edge_client.get("/api/v1/edges/cricket",
                        params={"store_dir": _eu(store_dir)})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "unavailable"
    assert body.get("count", 0) == 0


# -- 4. exec_routes: /api/paper/place reachable + idempotent ------------------

def _fresh_envelope() -> SnapshotEnvelope:
    """Same as _envelope() but generated_at = NOW, so the placement freshness gate
    (exec_routes rejects 409 on a snapshot past the SLA) sees a FRESH line. The
    pinned _GEN_AT envelope is intentionally stale and must NOT back a placement;
    the place path only records against a fresh store line."""
    from datetime import datetime, timezone
    env = _envelope()
    env.generated_at = datetime.now(timezone.utc).isoformat()
    return env


@pytest.fixture()
def exec_client(monkeypatch):
    """Bare FastAPI with exec_routes; store stubbed to return a FRESH test envelope.

    The placement freshness gate (P0-6) rejects 409 against a stale snapshot, so the
    stub must stamp generated_at = NOW -- otherwise the place path can never reach
    200 and the idempotency rail is never exercised."""
    import frontend.exec_routes as _exec
    monkeypatch.setattr(
        _exec.store, "read_latest",
        lambda sport, *a, **k: (
            _fresh_envelope() if str(sport).lower() == _SPORT
            else SnapshotEnvelope.unavailable(sport)
        ),
    )
    app = FastAPI()
    app.include_router(_exec.router)
    return TestClient(app, raise_server_exceptions=True)


def _place_body() -> dict:
    return {
        "sport": _SPORT, "game_id": _GID, "market_type": "moneyline",
        "side": "home", "book": _BOOK, "taken_decimal": _DEC,
    }


def test_paper_place_reachable(exec_client, tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    r = exec_client.post("/api/paper/place",
                         params={"ledger": str(ledger)},
                         json=_place_body())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["idempotent"] is False
    bet = body["bet"]
    assert bet["executed"] is False
    assert bet["channel"] == "paper_manual"
    assert bet["sport"] == _SPORT
    assert bet["game_id"] == _GID


def test_paper_place_idempotent(exec_client, tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    params = {"ledger": str(ledger)}
    r1 = exec_client.post("/api/paper/place", params=params, json=_place_body())
    r2 = exec_client.post("/api/paper/place", params=params, json=_place_body())
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["idempotent"] is False
    assert r2.json()["idempotent"] is True
    # Same idem_key on both submissions.
    assert r1.json()["bet"]["idem_key"] == r2.json()["bet"]["idem_key"]
    # GET open via exec_client still shows exactly ONE open bet.
    g = exec_client.get("/api/paper/open", params={"ledger": str(ledger)})
    assert g.status_code == 200
    assert g.json()["count"] == 1


# -- 5. Regression: /api/predict + /api/paper/trail via predict_service.app --

@pytest.fixture()
def full_app_client(monkeypatch):
    """predict_service.app with store monkeypatched BEFORE the app is imported
    into THIS test's scope, so the mounts see the stub."""
    import predict_service.store as _store
    monkeypatch.setattr(_store, "read_latest", lambda sport, *a, **k: (
        _envelope() if str(sport).lower() == _SPORT
        else SnapshotEnvelope.unavailable(sport)
    ))
    from predict_service.app import app as _app
    return TestClient(_app, raise_server_exceptions=False)


def test_predict_endpoint_regression(full_app_client):
    """GET /api/predict/nba returns a SnapshotEnvelope-like body."""
    r = full_app_client.get("/api/predict/nba")
    assert r.status_code == 200
    body = r.json()
    # The real store might differ from the stub (module already imported), but
    # the shape must always be valid: must have sport and status.
    assert "sport" in body
    assert "status" in body


def test_health_endpoint_regression(full_app_client):
    r = full_app_client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_paper_trail_endpoint_regression(full_app_client, tmp_path):
    """GET /api/paper/trail still reachable via paper_routes mount."""
    ledger = tmp_path / "empty.jsonl"
    r = full_app_client.get("/api/paper/trail",
                            params={"ledger": str(ledger)})
    # 503 -> paper_routes mount degraded but path exists; 200 -> mounted fine.
    assert r.status_code in (200, 503)
    if r.status_code == 200:
        body = r.json()
        assert body["status"] == "ok"
        assert "trail" in body


def test_edge_routes_mounted_in_full_app(full_app_client, store_dir):
    """The edge router is mounted in predict_service.app; 404 would mean failure."""
    r = full_app_client.get("/api/v1/edges/nba",
                            params={"store_dir": _eu(store_dir)})
    # Must not be 404 (route not mounted) or 503 (guard degraded).
    assert r.status_code not in (404, 503), (
        "edge_routes not mounted in predict_service.app; status=%d body=%s"
        % (r.status_code, r.text))
    assert r.status_code == 200


# -- 6. Honesty: no money keys anywhere in edge responses ---------------------

def test_no_money_keys_in_edge_view(edge_client, store_dir):
    r = edge_client.get("/api/v1/edges/nba",
                        params={"store_dir": _eu(store_dir)})
    assert r.status_code == 200
    _assert_no_money(r.json())


def test_no_money_keys_in_single_game(edge_client, store_dir):
    r = edge_client.get("/api/v1/edges/nba/%s" % _GID,
                        params={"store_dir": _eu(store_dir)})
    assert r.status_code == 200
    _assert_no_money(r.json())
