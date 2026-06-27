"""Per-file test: contract validation for the browse-UI API shapes.

Validates the exact shapes that SportGrid / GameCard consume:

  * GET /api/sports  -- active list + capabilities; no forbidden $ keys.
  * GET /api/predict/{sport} -- SnapshotEnvelope; predictions[] parsed into
      GameCardData-compatible fields (home/away/tipoff/pregame_probs/markets).
  * Unavailable sport (no snapshot on disk) -> status='unavailable' sentinel,
      never crashes, never fabricates games.
  * No $ / dollar / roi / pnl / profit / stake / bankroll key appears anywhere
      in any response (honesty invariant).
  * Regression: /health + /api/paper/trail still respond (no import regressions).

Run: python -m pytest tests/frontend/test_browse_ui_contract.py -q
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from predict_service import store
from predict_service.contracts import (
    EdgeRow,
    MarketRow,
    PredictionRecord,
    SnapshotEnvelope,
)

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_SPORT = "nba"
_SPORT_UNAVAIL = "tennis"   # no snapshot written -> unavailable sentinel
_GID1 = "0042500401"
_GID2 = "0042500402"

_FORBIDDEN = ("$", "dollar", "roi", "pnl", "profit", "stake", "bankroll")


def _make_envelope(sport: str, game_ids: list[str]) -> SnapshotEnvelope:
    """Build a minimal but valid SnapshotEnvelope with *game_ids* predictions."""
    predictions = []
    markets = []
    edges = []
    for gid in game_ids:
        mkt = MarketRow(
            sport=sport, game_id=gid, market_type="moneyline",
            side="home", line=None, odds=1.71, book="espn:DK",
            devigged_prob=0.57, captured_at="2026-06-18T22:00:00+00:00",
            is_close=False, clv_is_proxy=False,
        )
        rec = PredictionRecord(
            sport=sport, game_id=gid,
            home="Boston Celtics", away="New York Knicks",
            tipoff="2026-06-18T23:30:00+00:00",
            pregame_probs={"home_ml": 0.58, "away_ml": 0.42},
            markets=[mkt], leak_guard={"in_sample": False},
            produced_at="2026-06-18T21:00:00+00:00",
        )
        edge = EdgeRow(
            game_id=gid, market_type="moneyline", side="home",
            model_prob=0.58, market_prob=0.555, ev=0.045, tier="B",
            book="espn:DK", line=None, clv_is_proxy=False,
        )
        predictions.append(rec)
        markets.append(mkt)
        edges.append(edge)
    return SnapshotEnvelope(
        sport=sport,
        generated_at="2026-06-18T22:01:00+00:00",
        status="ok",
        predictions=predictions,
        markets=markets,
        edges=edges,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path, monkeypatch):
    """TestClient with a stubbed store containing one NBA snapshot."""
    # Write the NBA snapshot; leave tennis absent (-> unavailable sentinel).
    store.save(_make_envelope(_SPORT, [_GID1, _GID2]), out_dir=tmp_path, append=False)
    monkeypatch.setenv("PREDICT_SERVICE_STORE_DIR", str(tmp_path))

    from predict_service.app import app  # noqa: PLC0415
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _no_forbidden(obj: Any, path: str = "") -> None:
    """Recursively assert no forbidden $ / roi / ... KEY appears."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            for bad in _FORBIDDEN:
                assert bad not in kl, (
                    "forbidden key %r (matches %r) found at path %r" % (k, bad, path)
                )
            _no_forbidden(v, path + "." + str(k))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _no_forbidden(item, path + "[%d]" % i)


# ---------------------------------------------------------------------------
# GET /api/sports -- active list contract
# ---------------------------------------------------------------------------

class TestSportsEndpoint:
    def test_status_200(self, client):
        r = client.get("/api/sports")
        assert r.status_code == 200

    def test_has_status_ok(self, client):
        body = client.get("/api/sports").json()
        assert body["status"] == "ok"

    def test_active_is_list(self, client):
        body = client.get("/api/sports").json()
        assert isinstance(body["active"], list)

    def test_capabilities_is_dict(self, client):
        body = client.get("/api/sports").json()
        assert isinstance(body["capabilities"], dict)

    def test_honest_note_present(self, client):
        body = client.get("/api/sports").json()
        assert "honest_note" in body
        assert body["honest_note"]  # non-empty

    def test_no_forbidden_keys(self, client):
        body = client.get("/api/sports").json()
        _no_forbidden(body)

    def test_capabilities_markets_are_lists(self, client):
        body = client.get("/api/sports").json()
        for sport, caps in body["capabilities"].items():
            assert isinstance(caps.get("markets", []), list), (
                "capabilities[%s].markets must be a list" % sport
            )

    def test_no_edge_field_in_capabilities(self, client):
        """Capabilities must not carry a 'edge' or 'roi' key."""
        body = client.get("/api/sports").json()
        for sport, caps in body["capabilities"].items():
            for key in caps:
                assert "edge" not in key.lower() or "honest" in key.lower(), (
                    "unexpected 'edge' key %r in capabilities for %s" % (key, sport)
                )


# ---------------------------------------------------------------------------
# GET /api/predict/{sport} -- SnapshotEnvelope / GameCard contract
# ---------------------------------------------------------------------------

class TestPredictEnvelopeContract:
    def test_status_200(self, client):
        r = client.get("/api/predict/%s" % _SPORT)
        assert r.status_code == 200

    def test_envelope_has_required_top_level_keys(self, client):
        body = client.get("/api/predict/%s" % _SPORT).json()
        for key in ("status", "sport", "generated_at", "predictions",
                    "markets", "edges", "honest_note"):
            assert key in body, "missing top-level key %r" % key

    def test_predictions_is_list(self, client):
        body = client.get("/api/predict/%s" % _SPORT).json()
        assert isinstance(body["predictions"], list)

    def test_predictions_count_matches(self, client):
        body = client.get("/api/predict/%s" % _SPORT).json()
        assert len(body["predictions"]) == 2

    def test_prediction_record_has_game_card_fields(self, client):
        """Every prediction must carry the fields GameCard needs."""
        body = client.get("/api/predict/%s" % _SPORT).json()
        for rec in body["predictions"]:
            for field in ("sport", "game_id", "home", "away",
                          "tipoff", "pregame_probs", "markets"):
                assert field in rec, "missing field %r in prediction record" % field

    def test_pregame_probs_is_dict(self, client):
        body = client.get("/api/predict/%s" % _SPORT).json()
        for rec in body["predictions"]:
            assert isinstance(rec["pregame_probs"], dict)

    def test_pregame_probs_no_dollar_keys(self, client):
        """pregame_probs must not contain $ or edge keys (honesty invariant)."""
        body = client.get("/api/predict/%s" % _SPORT).json()
        for rec in body["predictions"]:
            _no_forbidden(rec["pregame_probs"])

    def test_markets_is_list(self, client):
        body = client.get("/api/predict/%s" % _SPORT).json()
        for rec in body["predictions"]:
            assert isinstance(rec["markets"], list)

    def test_game_ids_are_strings(self, client):
        body = client.get("/api/predict/%s" % _SPORT).json()
        for rec in body["predictions"]:
            assert isinstance(rec["game_id"], str)
            assert rec["game_id"]  # non-empty

    def test_home_away_are_strings(self, client):
        body = client.get("/api/predict/%s" % _SPORT).json()
        for rec in body["predictions"]:
            assert isinstance(rec["home"], str)
            assert isinstance(rec["away"], str)

    def test_no_forbidden_keys_full_envelope(self, client):
        body = client.get("/api/predict/%s" % _SPORT).json()
        _no_forbidden(body)

    def test_no_edge_field_in_predictions(self, client):
        """Predictions must not carry a raw 'edge' key (only ev / tier / model_prob)."""
        body = client.get("/api/predict/%s" % _SPORT).json()
        for rec in body["predictions"]:
            # 'edge' not allowed as a direct key; 'edges' at envelope level is fine
            assert "edge" not in rec, (
                "prediction record must not have a top-level 'edge' key"
            )

    def test_leak_guard_in_sample_false(self, client):
        body = client.get("/api/predict/%s" % _SPORT).json()
        for rec in body["predictions"]:
            assert "leak_guard" in rec
            assert rec["leak_guard"].get("in_sample") is False

    def test_envelope_sport_matches(self, client):
        body = client.get("/api/predict/%s" % _SPORT).json()
        assert body["sport"] == _SPORT


# ---------------------------------------------------------------------------
# Unavailable sport (no snapshot) -> sentinel, never fabricates
# ---------------------------------------------------------------------------

class TestUnavailableSport:
    def test_status_200(self, client):
        r = client.get("/api/predict/%s" % _SPORT_UNAVAIL)
        assert r.status_code == 200

    def test_returns_unavailable_status(self, client):
        body = client.get("/api/predict/%s" % _SPORT_UNAVAIL).json()
        assert body["status"] == "unavailable"

    def test_predictions_empty_for_unavailable(self, client):
        body = client.get("/api/predict/%s" % _SPORT_UNAVAIL).json()
        # unavailable sentinel -> no fabricated predictions
        assert body.get("predictions", []) == []

    def test_no_forbidden_keys_unavailable(self, client):
        body = client.get("/api/predict/%s" % _SPORT_UNAVAIL).json()
        _no_forbidden(body)

    def test_unknown_sport_also_unavailable(self, client):
        body = client.get("/api/predict/totally_unknown_sport").json()
        assert body["status"] == "unavailable"
        assert body.get("predictions", []) == []


# ---------------------------------------------------------------------------
# Regression: other endpoints still respond
# ---------------------------------------------------------------------------

class TestRegression:
    def test_health_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_paper_trail_responds(self, client, tmp_path):
        r = client.get("/api/paper/trail",
                       params={"ledger": str(tmp_path / "empty.jsonl")})
        assert r.status_code in (200, 503)
        assert "status" in r.json()

    def test_predict_game_id_responds(self, client):
        r = client.get("/api/predict/%s/%s" % (_SPORT, _GID1))
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "prediction" in body
        _no_forbidden(body)
    def test_predict_game_id_unknown(self, client):
        r = client.get("/api/predict/%s/DOES_NOT_EXIST" % _SPORT)
        assert r.status_code == 200
        assert r.json()["status"] == "unavailable"
