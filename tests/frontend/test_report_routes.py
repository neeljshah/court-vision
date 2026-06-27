"""Per-file test: frontend.report_routes mounted into predict_service.app.

Tests:
  * GET /api/report/nba/{game_id} returns the full ok-report shape when the
    store is stubbed with a canonical envelope;
  * GET /api/report/nba/{game_id} returns the unavailable sentinel for an
    unknown game_id;
  * GET /api/report/nba returns the browse list (game_ids[]);
  * Existing /api/paper/trail + /api/predict/nba still respond (no regression);
  * No forbidden $/roi/pnl/profit/stake key appears anywhere in any response.

Run: python -m pytest tests/frontend/test_report_routes.py -q
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from predict_service import store
from predict_service.contracts import (
    EdgeRow, MarketRow, PredictionRecord, SnapshotEnvelope,
)

# ---------------------------------------------------------------------------
# Stub envelope
# ---------------------------------------------------------------------------

_SPORT = "nba"
_GID = "0042500401"
_GID_UNKNOWN = "DOES_NOT_EXIST_99"
_FORBIDDEN = ("$", "dollar", "roi", "pnl", "profit", "stake", "bankroll")


def _envelope() -> SnapshotEnvelope:
    market = MarketRow(
        sport=_SPORT, game_id=_GID, market_type="moneyline",
        side="home", line=None, odds=1.71, book="espn:DK",
        devigged_prob=0.57, captured_at="2026-06-18T22:00:00+00:00",
        is_close=False, clv_is_proxy=True,
    )
    record = PredictionRecord(
        sport=_SPORT, game_id=_GID,
        home="Boston Celtics", away="New York Knicks",
        tipoff="2026-06-18T23:30:00+00:00",
        pregame_probs={"home_ml": 0.58, "away_ml": 0.42},
        markets=[market], leak_guard={"in_sample": False},
        produced_at="2026-06-18T21:00:00+00:00",
    )
    edge = EdgeRow(
        game_id=_GID, market_type="moneyline", side="home",
        model_prob=0.58, market_prob=0.555, ev=0.045, tier="B",
        book="espn:DK", line=None, clv_is_proxy=True,
    )
    return SnapshotEnvelope(
        sport=_SPORT, generated_at="2026-06-18T22:01:00+00:00",
        status="ok", predictions=[record], markets=[market], edges=[edge],
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path, monkeypatch):
    """TestClient on predict_service.app with a stubbed store + live board."""
    # Write stub envelope into a temp store dir.
    store.save(_envelope(), out_dir=tmp_path, append=False)

    # Point the app's _store_out_dir() at the temp dir.
    monkeypatch.setenv("PREDICT_SERVICE_STORE_DIR", str(tmp_path))

    # Stub out the live board so no network is needed and the live block
    # resolves to a clean unavailable (correct -- it is not in a live game).
    import frontend.report as _report_mod  # noqa: PLC0415
    monkeypatch.setattr(
        _report_mod, "_live",
        lambda *a, **k: {"status": "unavailable", "reason": "stubbed in test"},
    )

    from predict_service.app import app  # noqa: PLC0415
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assert_no_money(obj: Any) -> None:
    """Recursively assert no forbidden $/roi/pnl key appears anywhere."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            for bad in _FORBIDDEN:
                assert bad not in kl, "forbidden key %r found in report" % k
            _assert_no_money(v)
    elif isinstance(obj, list):
        for item in obj:
            _assert_no_money(item)


# ---------------------------------------------------------------------------
# /api/report/nba/{game_id} -- ok variant
# ---------------------------------------------------------------------------

def test_report_game_ok_status(client):
    r = client.get("/api/report/%s/%s" % (_SPORT, _GID))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["sport"] == _SPORT
    assert body["game_id"] == _GID


def test_report_game_pregame_block(client):
    body = client.get("/api/report/%s/%s" % (_SPORT, _GID)).json()
    pre = body["pregame"]
    assert pre is not None
    assert pre["home"] == "Boston Celtics"
    assert pre["away"] == "New York Knicks"
    assert pre["tipoff"] == "2026-06-18T23:30:00+00:00"
    assert pre["model_probs"] == {"home_ml": 0.58, "away_ml": 0.42}
    assert pre["leak_guard"] == {"in_sample": False}


def test_report_game_markets_present(client):
    body = client.get("/api/report/%s/%s" % (_SPORT, _GID)).json()
    assert len(body["markets"]) >= 1
    m = body["markets"][0]
    assert m["market_type"] == "moneyline"
    assert m["game_id"] == _GID


def test_report_game_edges_present(client):
    body = client.get("/api/report/%s/%s" % (_SPORT, _GID)).json()
    assert len(body["edges"]) >= 1
    e = body["edges"][0]
    assert e["tier"] == "B"
    assert e["model_prob"] == 0.58
    assert "ev" in e
    assert e["clv_is_proxy"] is True


def test_report_game_live_block(client):
    body = client.get("/api/report/%s/%s" % (_SPORT, _GID)).json()
    live = body["live"]
    # Live board is stubbed -> unavailable (correct; game is not live right now)
    assert "status" in live


def test_report_game_intel_block(client):
    body = client.get("/api/report/%s/%s" % (_SPORT, _GID)).json()
    intel = body["intel"]
    # intel is always a dict (either ok or unavailable); never null in the ok report
    assert isinstance(intel, dict)
    assert "status" in intel


def test_report_game_meta_block(client):
    body = client.get("/api/report/%s/%s" % (_SPORT, _GID)).json()
    meta = body["meta"]
    assert "as_of" in meta
    assert "honest_note" in meta
    assert meta["honest_note"]
    assert "schema_version" in meta
    assert "snapshot_generated_at" in meta
    assert meta["snapshot_generated_at"] == "2026-06-18T22:01:00+00:00"
    assert "freshness" in meta
    assert meta["freshness"]["status"] in ("fresh", "stale", "unknown")
    assert meta["clv_is_proxy"] is True


def test_report_game_no_money_keys(client):
    body = client.get("/api/report/%s/%s" % (_SPORT, _GID)).json()
    _assert_no_money(body)


# ---------------------------------------------------------------------------
# /api/report/nba/{game_id} -- unavailable (unknown game_id)
# ---------------------------------------------------------------------------

def test_report_unknown_game_returns_unavailable(client):
    r = client.get("/api/report/%s/%s" % (_SPORT, _GID_UNKNOWN))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "unavailable"
    assert body["sport"] == _SPORT
    assert body["game_id"] == _GID_UNKNOWN
    assert body["pregame"] is None
    assert body["markets"] == []
    assert body["edges"] == []
    assert "reason" in body and body["reason"]
    assert body["live"]["status"] == "unavailable"
    assert body["intel"] is None


def test_report_unknown_game_no_money_keys(client):
    body = client.get("/api/report/%s/%s" % (_SPORT, _GID_UNKNOWN)).json()
    _assert_no_money(body)


def test_report_unknown_sport_returns_unavailable(client):
    r = client.get("/api/report/unknown_sport/any_game_id")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "unavailable"
    assert body["pregame"] is None


# ---------------------------------------------------------------------------
# /api/report/{sport} -- browse list
# ---------------------------------------------------------------------------

def test_report_sport_list_ok(client):
    r = client.get("/api/report/%s" % _SPORT)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["sport"] == _SPORT
    assert isinstance(body["game_ids"], list)
    assert _GID in body["game_ids"]
    assert body["count"] == len(body["game_ids"])
    assert "honest_note" in body and body["honest_note"]
    assert "generated_at" in body


def test_report_sport_list_unavailable_unknown_sport(client):
    r = client.get("/api/report/unknown_sport_xyz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "unavailable"
    assert body["game_ids"] == []
    assert body["count"] == 0


# ---------------------------------------------------------------------------
# Regression: existing endpoints still respond
# ---------------------------------------------------------------------------

def test_health_still_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_predict_sport_still_responds(client):
    r = client.get("/api/predict/%s" % _SPORT)
    assert r.status_code == 200
    body = r.json()
    # status is ok (we have a stub) or unavailable (if store_out_dir not picked up)
    assert body["status"] in ("ok", "unavailable")


def test_paper_trail_still_responds(client, tmp_path):
    # Empty ledger is fine -- just assert it does not 404 or 500.
    r = client.get("/api/paper/trail",
                   params={"ledger": str(tmp_path / "empty.jsonl")})
    assert r.status_code in (200, 503)
    assert "status" in r.json()


def test_full_response_shape_no_money(client):
    """Comprehensive: no forbidden money keys appear anywhere in the report."""
    body = client.get("/api/report/%s/%s" % (_SPORT, _GID)).json()
    # _assert_no_money checks KEYS recursively (values may contain "$ edge" in notes)
    _assert_no_money(body)
