"""Per-file test: frontend.exec_routes -- manual paper-trade placement.

A tiny FastAPI app mounts the exec router; predict_service.store.read_latest is
stubbed to return a controlled SnapshotEnvelope so a placement can be validated
against a known live line. The ledger is redirected to a tmp file via the
?ledger= query override.

Covers:
  * a valid placement records exactly ONE open row (executed False, channel
    paper_manual) and GET /api/paper/open returns it;
  * a line NOT in the store is rejected (no row written);
  * a same-day double-submit is idempotent (still ONE row).

Run: python -m pytest tests/frontend/test_exec_routes.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import frontend.exec_routes as exec_routes
from predict_service.contracts import (
    EdgeRow,
    MarketRow,
    PredictionRecord,
    SnapshotEnvelope,
)


# ---------------------------------------------------------------------------
# Stub store snapshot
# ---------------------------------------------------------------------------

_SPORT = "nba"
_GAME_ID = "nba|NYK@SAS|2026-06-18T22:00:00Z"
_BOOK = "espn:DK"
_DEC = 2.6


def _fresh_iso(age_sec: float = 0.0) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=age_sec)).isoformat()


_UNSET = object()


def _envelope(generated_at=_UNSET) -> SnapshotEnvelope:
    gen = _fresh_iso() if generated_at is _UNSET else generated_at
    market = MarketRow(
        sport=_SPORT, game_id=_GAME_ID, market_type="moneyline",
        side="away", line=None, odds=_DEC, book=_BOOK, devigged_prob=0.39,
    )
    edge = EdgeRow(
        game_id=_GAME_ID, market_type="moneyline", side="away",
        model_prob=0.4145, market_prob=0.39, ev=0.0777, tier="B", book=_BOOK,
    )
    pred = PredictionRecord(
        sport=_SPORT, game_id=_GAME_ID, home="SAS", away="NYK",
        pregame_probs={"home_ml": 0.61, "away_ml": 0.39},
    )
    return SnapshotEnvelope(
        sport=_SPORT, generated_at=gen, status="ok",
        predictions=[pred], markets=[market], edges=[edge],
    )


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(
        exec_routes.store, "read_latest",
        lambda sport, *a, **k: (_envelope() if str(sport).lower() == _SPORT
                                else SnapshotEnvelope.unavailable(sport)),
    )
    app = FastAPI()
    app.include_router(exec_routes.router)
    return TestClient(app)


def _valid_body() -> dict:
    return {
        "sport": _SPORT, "game_id": _GAME_ID, "market_type": "moneyline",
        "side": "away", "book": _BOOK, "taken_decimal": _DEC,
    }


def _count_rows(ledger: Path) -> int:
    if not ledger.exists():
        return 0
    n = 0
    with ledger.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                n += 1
    return n


# ---------------------------------------------------------------------------
# Valid placement
# ---------------------------------------------------------------------------

def test_valid_placement_records_one_open_row(client, tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    r = client.post("/api/paper/place",
                    params={"ledger": str(ledger)}, json=_valid_body())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["idempotent"] is False
    # PE-P0-05: a manual place writes EXACTLY ONE raw open row (no phantom dup).
    assert _count_rows(ledger) == 1, "manual place must write exactly one open row"
    bet = body["bet"]
    assert bet["executed"] is False
    assert bet["channel"] == "paper_manual"
    assert bet["status"] == "open"
    assert bet["sport"] == _SPORT
    assert bet["game_id"] == _GAME_ID
    # Stamped from the matching store edge.
    assert bet["tier"] == "B"
    assert bet["model_prob"] == pytest.approx(0.4145)
    # flat_unit 1.0 + quarter_kelly -> >= 1.0 units (positive-EV line here).
    assert bet["stake_units"] >= 1.0

    # GET open returns exactly the one open row.
    g = client.get("/api/paper/open", params={"ledger": str(ledger)})
    assert g.status_code == 200
    gb = g.json()
    assert gb["status"] == "ok"
    assert gb["count"] == 1
    assert gb["open"][0]["status"] == "open"
    assert gb["open"][0]["executed"] is False


def test_no_dollar_or_edge_fields(client, tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    r = client.post("/api/paper/place",
                    params={"ledger": str(ledger)}, json=_valid_body())
    body_str = json.dumps(r.json()).lower()
    for banned in ("$edge", "dollar", "roi", "profit"):
        assert banned not in body_str, "banned term in response: %s" % banned


# ---------------------------------------------------------------------------
# Rejection: line not in store
# ---------------------------------------------------------------------------

def test_line_not_in_store_rejected(client, tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    body = _valid_body()
    body["taken_decimal"] = 9.99  # price not present in the store line
    r = client.post("/api/paper/place",
                    params={"ledger": str(ledger)}, json=body)
    assert r.status_code == 400
    assert r.json()["status"] == "rejected"
    assert _count_rows(ledger) == 0  # nothing written


def test_fabricated_game_rejected(client, tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    body = _valid_body()
    body["game_id"] = "nba|FAKE@GAME|2026-01-01T00:00:00Z"
    r = client.post("/api/paper/place",
                    params={"ledger": str(ledger)}, json=body)
    assert r.status_code == 400
    assert _count_rows(ledger) == 0


def test_inactive_sport_rejected(client, tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    body = _valid_body()
    body["sport"] = "cricket"  # store returns unavailable
    r = client.post("/api/paper/place",
                    params={"ledger": str(ledger)}, json=body)
    assert r.status_code == 400
    assert _count_rows(ledger) == 0


def test_stale_snapshot_cannot_be_placed(monkeypatch, tmp_path):
    """PE / P0-6: a STALE snapshot (generated_at past the SLA) is rejected 409 and
    NO row is written -- 'a stale line cannot be placed' is actually enforced."""
    stale_env = _envelope(generated_at=_fresh_iso(age_sec=10_000))
    monkeypatch.setattr(
        exec_routes.store, "read_latest",
        lambda sport, *a, **k: (stale_env if str(sport).lower() == _SPORT
                                else SnapshotEnvelope.unavailable(sport)),
    )
    app = FastAPI()
    app.include_router(exec_routes.router)
    cl = TestClient(app)
    ledger = tmp_path / "ledger.jsonl"
    r = cl.post("/api/paper/place", params={"ledger": str(ledger)}, json=_valid_body())
    assert r.status_code == 409, r.text
    assert "stale" in r.json()["reason"].lower()
    assert _count_rows(ledger) == 0  # never recorded against a stale line


def test_missing_generated_at_is_treated_stale(monkeypatch, tmp_path):
    """Fail-closed: an unparseable/missing generated_at -> treated as stale (409)."""
    env = _envelope(generated_at="")
    monkeypatch.setattr(
        exec_routes.store, "read_latest", lambda sport, *a, **k: env)
    app = FastAPI()
    app.include_router(exec_routes.router)
    cl = TestClient(app)
    ledger = tmp_path / "ledger.jsonl"
    r = cl.post("/api/paper/place", params={"ledger": str(ledger)}, json=_valid_body())
    assert r.status_code == 409
    assert _count_rows(ledger) == 0


def test_bad_taken_decimal_rejected(client, tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    body = _valid_body()
    body["taken_decimal"] = 1.0  # not > 1.0
    r = client.post("/api/paper/place",
                    params={"ledger": str(ledger)}, json=body)
    assert r.status_code == 422
    assert _count_rows(ledger) == 0


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def test_double_submit_is_idempotent(client, tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    r1 = client.post("/api/paper/place",
                     params={"ledger": str(ledger)}, json=_valid_body())
    r2 = client.post("/api/paper/place",
                     params={"ledger": str(ledger)}, json=_valid_body())
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["idempotent"] is False
    assert r2.json()["idempotent"] is True
    # Same idem_key on both.
    assert r1.json()["bet"]["idem_key"] == r2.json()["bet"]["idem_key"]
    # GET open still shows exactly ONE open bet.
    g = client.get("/api/paper/open", params={"ledger": str(ledger)})
    assert g.json()["count"] == 1
