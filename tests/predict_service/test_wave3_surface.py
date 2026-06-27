"""Per-file tests: WAVE 3 surface projection + endpoints (offline, populated store).

Run: python -m pytest tests/predict_service/test_wave3_surface.py -q

Writes a tiny snapshot into a tmp store, then exercises build_surface and the
three new endpoints (/api/predict/contract, /api/predict/{sport}/surface,
/api/predict/{sport}/{game_id}/uncertainty) via the FastAPI TestClient. Confirms:
  * a merged number carries phase='merged', never a silent average;
  * an interval appears ONLY when held-out residuals are injected;
  * no $ key; vs_close not promoted; contract reports 1.1.0.
"""
from __future__ import annotations

import pytest

from predict_service import store, surface
from predict_service.contracts import (
    PHASE_MERGED,
    PredictionRecord,
    SnapshotEnvelope,
)


def _seed_store(out_dir: str) -> None:
    rec = PredictionRecord(
        sport="nba", game_id="g1", home="NYK", away="SAS",
        tipoff="2026-06-19T23:00:00+00:00",
        pregame_probs={"home_ml": 0.58, "away_ml": 0.42},
        leak_guard={"in_sample": False})
    env = SnapshotEnvelope(sport="nba", generated_at="2026-06-19T22:00:00+00:00",
                           status="ok", predictions=[rec])
    store.save(env, out_dir=out_dir)


def test_build_surface_pregame_only(tmp_path):
    out = str(tmp_path)
    _seed_store(out)
    body = surface.build_surface("nba", out_dir=out)
    assert body["status"] == "ok"
    assert body["schema_version"] == "1.1.0"
    assert body["games"]
    ests = body["games"][0]["estimates"]
    labels = {e["label"] for e in ests}
    assert {"home_ml", "away_ml"} <= labels
    for e in ests:
        # pregame-only -> phase 'pregame', interval None (no residuals injected).
        assert e["provenance"]["phase"] == "pregame"
        assert e["interval"] is None


def test_build_surface_merged_is_labelled(tmp_path):
    out = str(tmp_path)
    _seed_store(out)
    body = surface.build_surface(
        "nba", out_dir=out,
        ingame_by_game={"g1": {"home_ml": 0.81}})
    est = next(e for e in body["games"][0]["estimates"]
               if e["label"] == "home_ml")
    assert est["provenance"]["phase"] == PHASE_MERGED
    # merged number is the in-game number, NOT the average of 0.58 and 0.81.
    assert est["prob"] == 0.81
    assert est["prob"] != round((0.58 + 0.81) / 2.0, 6)


def test_build_surface_interval_from_heldout_residuals(tmp_path):
    out = str(tmp_path)
    _seed_store(out)
    resid = [-0.2, -0.1, -0.05, 0.0, 0.0, 0.05, 0.1, 0.2, 0.15, -0.15]
    body = surface.build_surface(
        "nba", out_dir=out,
        residuals_by_game={"g1": {"home_ml": resid}})
    est = next(e for e in body["games"][0]["estimates"]
               if e["label"] == "home_ml")
    assert est["interval"] is not None
    assert est["interval"]["method"] == "heldout_residual_quantile"
    # away_ml had NO residuals -> no fabricated band.
    away = next(e for e in body["games"][0]["estimates"]
                if e["label"] == "away_ml")
    assert away["interval"] is None


# --------------------------------------------------------------------------- #
# Endpoint tests via TestClient.
# --------------------------------------------------------------------------- #
def _client(out_dir, monkeypatch):
    monkeypatch.setenv("PREDICT_SERVICE_STORE_DIR", out_dir)
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from predict_service.app import app
    return TestClient(app)


def test_endpoint_contract(tmp_path, monkeypatch):
    c = _client(str(tmp_path), monkeypatch)
    r = c.get("/api/predict/contract")
    assert r.status_code == 200
    body = r.json()
    assert body["schema_version"] == "1.1.0"
    assert body["vs_close_default"] == "UNPROVEN"
    assert "ProbEstimate" in body["schemas"]
    assert body["edge_claimed"] is False


def test_endpoint_surface_matches_specific_path(tmp_path, monkeypatch):
    """'.../surface' must NOT be captured as game_id='surface'."""
    out = str(tmp_path)
    _seed_store(out)
    c = _client(out, monkeypatch)
    r = c.get("/api/predict/nba/surface")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "games" in body and body["games"]
    assert body["games"][0]["game_id"] == "g1"


def test_endpoint_uncertainty(tmp_path, monkeypatch):
    out = str(tmp_path)
    _seed_store(out)
    c = _client(out, monkeypatch)
    r = c.get("/api/predict/nba/g1/uncertainty")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["game_id"] == "g1"
    assert isinstance(body["estimates"], list) and body["estimates"]
    assert body["edge_claimed"] is False


def test_endpoint_uncertainty_missing_game(tmp_path, monkeypatch):
    out = str(tmp_path)
    _seed_store(out)
    c = _client(out, monkeypatch)
    r = c.get("/api/predict/nba/nope/uncertainty")
    assert r.status_code == 200
    assert r.json()["status"] == "unavailable"
