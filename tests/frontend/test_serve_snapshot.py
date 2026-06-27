"""Per-file test: /api/slate read-precedence -- predict_service.store (preferred)
over snapshot_writer (legacy), with graceful fallback when either is absent.

Run: python -m pytest tests/frontend/test_serve_snapshot.py -q
"""
from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers to build a minimal SnapshotEnvelope-like object + store stub
# ---------------------------------------------------------------------------

def _make_env(status: str = "ok", predictions: list = None,
              edges: list = None, generated_at: str = "2026-06-18T00:00:00Z"
              ) -> Any:
    """Return a simple namespace that mirrors SnapshotEnvelope for testing."""
    ns = types.SimpleNamespace()
    ns.status = status
    ns.generated_at = generated_at
    ns.honest_note = "calibrated only"
    ns.predictions = predictions or []
    ns.edges = edges or []
    return ns


def _pred(game_id: str = "G1", home: str = "SAS", away: str = "NYK",
          tipoff: str = "2026-06-18T22:00:00Z",
          pregame_probs: Optional[Dict[str, float]] = None,
          markets: list = None, note: str = "") -> Any:
    p = types.SimpleNamespace()
    p.game_id = game_id
    p.home = home
    p.away = away
    p.tipoff = tipoff
    p.pregame_probs = pregame_probs or {"home_ml": 0.58, "away_ml": 0.42}
    p.markets = [types.SimpleNamespace(to_dict=lambda: {"market": "ml"})]
    p.note = note
    return p


def _edge(game_id: str = "G1", side: str = "home",
          model_prob: float = 0.58, market_prob: float = 0.52,
          ev: float = 0.05, book: str = "espn") -> Any:
    e = types.SimpleNamespace()
    e.game_id = game_id
    e.side = side
    e.model_prob = model_prob
    e.market_prob = market_prob
    e.ev = ev
    e.book = book
    e.to_dict = lambda: {"game_id": game_id, "side": side, "ev": ev}
    return e


# ---------------------------------------------------------------------------
# Import serve under test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_serve_module():
    """Reload serve fresh per-test so module-level guards reset cleanly."""
    # We patch at the module level rather than reloading to avoid FastAPI teardown
    # issues.  Each test patches _ps_store / _snapshot_writer independently.
    yield


# ---------------------------------------------------------------------------
# 1. Store-present + ok envelope -> store used, served_from=predict_service_store
# ---------------------------------------------------------------------------

def test_store_present_slate_returns_store(tmp_path):
    """When predict_service.store has an ok envelope, /api/slate uses it."""
    from scripts.platformkit.frontend import serve as serve_mod
    from fastapi.testclient import TestClient

    env = _make_env("ok", predictions=[_pred()], edges=[_edge()])

    store_stub = types.SimpleNamespace(read_latest=lambda sport: env)
    with patch.object(serve_mod, "_ps_store", store_stub):
        client = TestClient(serve_mod.create_app())
        r = client.get("/api/slate", params={"sport": "nba"})

    assert r.status_code == 200
    body = r.json()
    assert body["served_from"] == "predict_service_store"
    assert body["status"] == "ok"
    assert len(body["games"]) == 1
    g = body["games"][0]
    assert g["home"] == "SAS"
    assert g["away"] == "NYK"
    assert "pregame_probs" in g
    assert "edges" in g
    assert body["freshness"]["source"] == "predict_service_store"
    assert "honest_note" in body


# ---------------------------------------------------------------------------
# 2. Store absent (None) -> falls back to snapshot_writer, no crash
# ---------------------------------------------------------------------------

def test_store_absent_falls_back_to_snapshot(tmp_path):
    """When _ps_store is None, /api/slate falls back to snapshot_writer gracefully."""
    from scripts.platformkit.frontend import serve as serve_mod
    from fastapi.testclient import TestClient

    snap_payload = {"status": "ok", "generated_at": "2026-06-18T00:00:00Z",
                    "slate": {"sport": "nba", "games": [], "status": "ok"}}

    def _read_snap(sport):
        return snap_payload

    snap_stub = types.SimpleNamespace(read_snapshot=_read_snap)
    with patch.object(serve_mod, "_ps_store", None):
        with patch.object(serve_mod, "_snapshot_writer", snap_stub):
            client = TestClient(serve_mod.create_app())
            r = client.get("/api/slate", params={"sport": "nba"})

    assert r.status_code == 200
    body = r.json()
    # snapshot_writer path stamps served_from="snapshot"
    assert body.get("served_from") == "snapshot"


# ---------------------------------------------------------------------------
# 3. Store unavailable (status='unavailable') -> falls back without crash
# ---------------------------------------------------------------------------

def test_store_unavailable_status_falls_back(tmp_path):
    """When store returns status='unavailable', slate falls back to live compute."""
    from scripts.platformkit.frontend import serve as serve_mod
    from fastapi.testclient import TestClient

    env = _make_env("unavailable", predictions=[])
    store_stub = types.SimpleNamespace(read_latest=lambda sport: env)

    # Also stub snapshot_writer to None so we reach live compute
    with patch.object(serve_mod, "_ps_store", store_stub):
        with patch.object(serve_mod, "_snapshot_writer", None):
            client = TestClient(serve_mod.create_app())
            r = client.get("/api/slate", params={"sport": "nba"})

    # live compute path -> served_from="live_compute" (from slate_mod)
    assert r.status_code == 200
    body = r.json()
    assert body.get("served_from") == "live_compute"


# ---------------------------------------------------------------------------
# 4. Store raises -> no crash, fallback succeeds
# ---------------------------------------------------------------------------

def test_store_read_raises_no_crash(tmp_path):
    """If _ps_store.read_latest raises, /api/slate still returns 200."""
    from scripts.platformkit.frontend import serve as serve_mod
    from fastapi.testclient import TestClient

    def _raise(sport):
        raise RuntimeError("disk error")

    store_stub = types.SimpleNamespace(read_latest=_raise)
    with patch.object(serve_mod, "_ps_store", store_stub):
        with patch.object(serve_mod, "_snapshot_writer", None):
            client = TestClient(serve_mod.create_app())
            r = client.get("/api/slate", params={"sport": "nba"})

    assert r.status_code == 200
    # Must not have come from store (since read raised)
    assert r.json().get("served_from") != "predict_service_store"


# ---------------------------------------------------------------------------
# 5. Store empty predictions -> falls back (not served_from=predict_service_store)
# ---------------------------------------------------------------------------

def test_store_empty_predictions_falls_back(tmp_path):
    """ok envelope with no predictions -> falls back (treats as cache miss)."""
    from scripts.platformkit.frontend import serve as serve_mod
    from fastapi.testclient import TestClient

    env = _make_env("ok", predictions=[])
    store_stub = types.SimpleNamespace(read_latest=lambda sport: env)
    with patch.object(serve_mod, "_ps_store", store_stub):
        with patch.object(serve_mod, "_snapshot_writer", None):
            client = TestClient(serve_mod.create_app())
            r = client.get("/api/slate", params={"sport": "nba"})

    assert r.status_code == 200
    assert r.json().get("served_from") != "predict_service_store"
