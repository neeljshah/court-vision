"""predict_service.test_app_predict_postgame_gate -- per-file test.

BE workstream be-predict-postgame-gate (iter-3 P0).

Verifies that apply_games_gate / apply_game_gate are wired into the
/api/predict/{sport} and /api/predict/{sport}/{game_id} routes in app.py:

  P1. /api/predict/{sport} with a completed game (live.state='post') in the
      snapshot: prediction carries decision='no_bet', suppressed=True; edges
      for that game carry tier=None and a completed_note; no decision='bet' row
      anywhere in the predictions list.

  P2. /api/predict/{sport}/{game_id} for a completed game: same guarantees on
      the single-game projection.

  P3. A pregame game (game_state='pre') is UNCHANGED by the gate -- its
      prediction is returned as-is (decision not forced to no_bet).

  P4. No $/pnl/profit key anywhere in either response (honesty rail).

  P5. The completed game envelope carries a 'completed_note' on its edge entries
      and tier=None on each edge (positive-EV tier must not leak out).

Run (per-file only)::
    cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/test_app_predict_postgame_gate.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Repo root on sys.path.
# ---------------------------------------------------------------------------
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

try:
    from fastapi.testclient import TestClient
except ImportError:
    pytest.skip("fastapi/httpx not installed", allow_module_level=True)

from predict_service.contracts import (
    EdgeRow,
    MarketRow,
    PredictionRecord,
    SnapshotEnvelope,
    GAME_STATE_POST,
    GAME_STATE_PRE,
)


# ---------------------------------------------------------------------------
# Shared fixtures.
# ---------------------------------------------------------------------------

_SPORT = "nba"
_POST_GAME_ID = "SAS_NYK_20260612"   # completed Finals game (6 days old)
_PRE_GAME_ID = "NYK_BOS_20261001"    # future pregame

_GENERATED_AT = "2026-06-18T04:00:00+00:00"


def _post_game_prediction() -> PredictionRecord:
    """A prediction for a COMPLETED game (game_state='post')."""
    return PredictionRecord(
        sport=_SPORT,
        game_id=_POST_GAME_ID,
        home="NYK",
        away="SAS",
        tipoff="2026-06-12T23:30:00+00:00",
        pregame_probs={"home_ml": 0.55},
        game_state=GAME_STATE_POST,   # <-- the key signal arm 0 uses
        note="SAS @ NYK Finals G6",
    )


def _pre_game_prediction() -> PredictionRecord:
    """A prediction for a FUTURE pregame."""
    return PredictionRecord(
        sport=_SPORT,
        game_id=_PRE_GAME_ID,
        home="NYK",
        away="BOS",
        tipoff="2026-10-01T23:30:00+00:00",
        pregame_probs={"home_ml": 0.62},
        game_state=GAME_STATE_PRE,
        note="",
    )


def _post_game_edge() -> EdgeRow:
    """An edge associated with the completed game."""
    return EdgeRow(
        game_id=_POST_GAME_ID,
        market_type="moneyline",
        side="home",
        model_prob=0.58,
        market_prob=0.53,
        ev=0.094,
        tier="A",
        book="DraftKings",
    )


def _pre_game_edge() -> EdgeRow:
    """An edge associated with the pregame."""
    return EdgeRow(
        game_id=_PRE_GAME_ID,
        market_type="total",
        side="over",
        model_prob=0.61,
        market_prob=0.50,
        ev=0.22,
        tier="B",
        book="FanDuel",
    )


def _make_envelope() -> SnapshotEnvelope:
    """Build a two-game snapshot: one post-game, one pregame."""
    return SnapshotEnvelope(
        sport=_SPORT,
        generated_at=_GENERATED_AT,
        status="ok",
        predictions=[_post_game_prediction(), _pre_game_prediction()],
        markets=[
            MarketRow(
                sport=_SPORT, game_id=_POST_GAME_ID,
                market_type="moneyline", side="home",
                odds=1.89, book="DraftKings",
            ),
        ],
        edges=[_post_game_edge(), _pre_game_edge()],
    )


def _make_client() -> TestClient:
    """Build a TestClient whose store.read_latest is stubbed to our envelope."""
    # Import the app AFTER patching so the module-level store calls see the stub.
    with patch("predict_service.store.read_latest", return_value=_make_envelope()):
        from predict_service.app import app as _app  # noqa: PLC0415
    return TestClient(_app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------

def _has_money_key(obj: Any) -> bool:
    """True when any nested key/value looks like a $ / pnl / profit field."""
    _BANNED = {"$", "pnl", "profit", "roi", "bankroll", "dollar", "dollars"}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if any(b in str(k).lower() for b in _BANNED):
                return True
            if _has_money_key(v):
                return True
    if isinstance(obj, list):
        return any(_has_money_key(i) for i in obj)
    return False


# ---------------------------------------------------------------------------
# P1 -- /api/predict/{sport}: completed game is gated in the full snapshot.
# ---------------------------------------------------------------------------

def test_p1_sport_snapshot_completed_game_no_bet():
    """P1: /api/predict/nba -- post-game prediction carries no decision=bet."""
    client = _make_client()
    with patch("predict_service.store.read_latest", return_value=_make_envelope()):
        resp = client.get(f"/api/predict/{_SPORT}")

    assert resp.status_code == 200, "P1: endpoint must return 200"
    body = resp.json()
    assert body.get("status") == "ok", "P1: body status must be ok"

    predictions: List[Dict[str, Any]] = body.get("predictions") or []
    post_pred = next((p for p in predictions if p.get("game_id") == _POST_GAME_ID), None)
    assert post_pred is not None, "P1: completed game prediction must be present"

    # Gate must have fired: no decision='bet', suppressed=True.
    assert post_pred.get("decision") != "bet", (
        "P1: completed game must not carry decision='bet'; got %r"
        % post_pred.get("decision")
    )
    assert post_pred.get("suppressed") is True, (
        "P1: completed game must carry suppressed=True"
    )
    # tier must be stripped from prediction.
    assert post_pred.get("tier") is None, (
        "P1: tier must be None on completed prediction; got %r" % post_pred.get("tier")
    )

    # No decision=bet anywhere in predictions list.
    bet_preds = [p for p in predictions if p.get("decision") == "bet"]
    assert not bet_preds, (
        "P1: no prediction should carry decision='bet'; found %r" % bet_preds
    )


# ---------------------------------------------------------------------------
# P2 -- /api/predict/{sport}/{game_id}: single completed game is gated.
# ---------------------------------------------------------------------------

def test_p2_game_endpoint_completed_game_no_bet():
    """P2: /api/predict/nba/{post_game_id} -- prediction gated + edges stale."""
    client = _make_client()
    with patch("predict_service.store.read_latest", return_value=_make_envelope()):
        resp = client.get(f"/api/predict/{_SPORT}/{_POST_GAME_ID}")

    assert resp.status_code == 200, "P2: endpoint must return 200"
    body = resp.json()
    assert body.get("status") == "ok", "P2: body status must be ok"

    pred = body.get("prediction") or {}
    assert pred.get("decision") != "bet", (
        "P2: completed game prediction must not carry decision='bet'; got %r"
        % pred.get("decision")
    )
    assert pred.get("suppressed") is True, "P2: suppressed must be True"

    edges: List[Dict[str, Any]] = body.get("edges") or []
    for edge in edges:
        assert edge.get("tier") is None, (
            "P2: edge tier must be None for completed game; got %r" % edge.get("tier")
        )
        assert "completed_note" in edge, (
            "P2: edge must carry completed_note for completed game"
        )


# ---------------------------------------------------------------------------
# P3 -- Pregame game is UNCHANGED by the gate.
# ---------------------------------------------------------------------------

def test_p3_pregame_unchanged():
    """P3: /api/predict/nba/{pre_game_id} -- pregame prediction unchanged."""
    client = _make_client()
    with patch("predict_service.store.read_latest", return_value=_make_envelope()):
        resp = client.get(f"/api/predict/{_SPORT}/{_PRE_GAME_ID}")

    assert resp.status_code == 200, "P3: endpoint must return 200"
    body = resp.json()
    assert body.get("status") == "ok", "P3: body status must be ok"

    pred = body.get("prediction") or {}
    # Gate must NOT have fired on a pregame: suppressed must be absent/False.
    assert not pred.get("suppressed"), (
        "P3: pregame prediction must NOT be suppressed; got suppressed=%r"
        % pred.get("suppressed")
    )
    # tier is not set on the stub prediction, but the gate must not have set it to None
    # by force. Check that decision was not coerced to no_bet.
    assert pred.get("decision") != "no_bet", (
        "P3: pregame prediction must not carry decision='no_bet' from the gate; "
        "got %r" % pred.get("decision")
    )

    # Pregame edge: tier must still be 'B' (unchanged).
    edges: List[Dict[str, Any]] = body.get("edges") or []
    for edge in edges:
        assert edge.get("game_id") == _PRE_GAME_ID, (
            "P3: only pregame edges should be returned here"
        )
        assert edge.get("tier") == "B", (
            "P3: pregame edge tier must be unchanged ('B'); got %r" % edge.get("tier")
        )


# ---------------------------------------------------------------------------
# P4 -- No $ / pnl / profit key in responses.
# ---------------------------------------------------------------------------

def test_p4_no_money_key_sport_endpoint():
    """P4a: no $/pnl/profit key in /api/predict/{sport} response."""
    client = _make_client()
    with patch("predict_service.store.read_latest", return_value=_make_envelope()):
        resp = client.get(f"/api/predict/{_SPORT}")

    body = resp.json()
    assert not _has_money_key(body), (
        "P4a: money key found in /api/predict/{sport} response"
    )


def test_p4_no_money_key_game_endpoint():
    """P4b: no $/pnl/profit key in /api/predict/{sport}/{game_id} response."""
    client = _make_client()
    with patch("predict_service.store.read_latest", return_value=_make_envelope()):
        resp = client.get(f"/api/predict/{_SPORT}/{_POST_GAME_ID}")

    body = resp.json()
    assert not _has_money_key(body), (
        "P4b: money key found in /api/predict/{sport}/{game_id} response"
    )


# ---------------------------------------------------------------------------
# P5 -- Edge tier=None + completed_note stamped on completed game edges.
# ---------------------------------------------------------------------------

def test_p5_completed_game_edges_stale_in_sport_snapshot():
    """P5: completed-game edge carries tier=None and completed_note in /api/predict/{sport}."""
    client = _make_client()
    with patch("predict_service.store.read_latest", return_value=_make_envelope()):
        resp = client.get(f"/api/predict/{_SPORT}")

    body = resp.json()
    edges: List[Dict[str, Any]] = body.get("edges") or []
    post_edges = [e for e in edges if e.get("game_id") == _POST_GAME_ID]
    assert post_edges, "P5: completed game must have edges in the sport snapshot"
    for edge in post_edges:
        assert edge.get("tier") is None, (
            "P5: tier must be None for completed-game edge; got %r" % edge.get("tier")
        )
        assert "completed_note" in edge, (
            "P5: completed_note must be present on completed-game edge"
        )

    # Pregame edges must be untouched.
    pre_edges = [e for e in edges if e.get("game_id") == _PRE_GAME_ID]
    for edge in pre_edges:
        assert edge.get("tier") == "B", (
            "P5: pregame edge tier must be unchanged; got %r" % edge.get("tier")
        )
        assert "completed_note" not in edge, (
            "P5: pregame edge must NOT carry completed_note"
        )
