"""WS2 acceptance test: GET /api/improve/clv-corpus wired into app.py.

Verifies the route is reachable via the FULL app (not just the standalone
router), enforcing the workstream acceptance criteria:

  (A) route returns status in {ok, unavailable, INSUFFICIENT_DATA}
  (B) no '$' / 'pnl' / 'roi' / 'profit' KEY anywhere in the payload
  (C) edge_claimed is false (never True) in every response shape
  (D) /openapi.json lists /api/improve/clv-corpus
  (E) missing proposals file -> status='unavailable' (never green)

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/frontend/test_clv_corpus_routes.py -q

ASCII only; per-file test; never raises; <=300 LOC.
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Import the full app so the guarded include_router block is exercised.
import predict_service.app as app_mod
import predict_service.frontend.clv_corpus_routes as routes_mod

_BANNED_KEY_RE = re.compile(r"^(\$|roi|pnl|profit)$", re.IGNORECASE)
_VALID_STATUSES = {"ok", "unavailable", "INSUFFICIENT_DATA"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_keys(obj: Any):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _all_keys(v)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            yield from _all_keys(item)


def _no_banned_keys(obj: Any) -> bool:
    for k in _all_keys(obj):
        if _BANNED_KEY_RE.match(str(k)):
            return False
    return True


def _proposal_line(
    name: str = "nba",
    decision: str = "REPLICATION_PENDING",
    n_rep: int = 1,
    saw_proxy: bool = False,
    all_positive: bool = True,
    vs_close: str = "UNPROVEN",
    delta: float = 0.003,
    dm_p: float = 0.04,
    significant: bool = True,
    n_new: int = 8,
) -> str:
    return json.dumps({
        "ts": "2026-06-19T12:00:00",
        "name": name,
        "decision": decision,
        "n_corpora_replicated": n_rep,
        "saw_proxy": saw_proxy,
        "all_positive": all_positive,
        "vs_close": vs_close,
        "delta": delta,
        "dm_p": dm_p,
        "significant": significant,
        "n_new": n_new,
        "reasons": ["calibration-only test"],
        "note": "calibration; no edge; proposal only",
    })


# ---------------------------------------------------------------------------
# (A) + (B) + (C): normal candidate row via full app
# ---------------------------------------------------------------------------

def test_clv_corpus_route_ok_shape():
    """(A)+(B)+(C): full-app client: route returns ok, no banned keys, edge_claimed=False."""
    with tempfile.TemporaryDirectory() as tmp:
        proposals = Path(tmp) / "proposals.jsonl"
        proposals.write_text(_proposal_line(n_rep=1), encoding="utf-8")

        with patch.object(routes_mod, "_PROPOSALS_PATH", proposals), \
             patch("predict_service.frontend.clv_corpus_routes._pipeline_enabled",
                   return_value=False):
            client = TestClient(app_mod.app, raise_server_exceptions=False)
            resp = client.get("/api/improve/clv-corpus")

    assert resp.status_code == 200, "route must return HTTP 200, got %d" % resp.status_code
    data = resp.json()
    assert data["status"] in _VALID_STATUSES, (
        "status must be in %r, got %r" % (_VALID_STATUSES, data["status"])
    )
    assert _no_banned_keys(data), "response contains a banned key ($, roi, pnl, profit)"
    assert data.get("edge_claimed") is not True, (
        "edge_claimed must be False, got %r" % data.get("edge_claimed")
    )
    # When we have a row the route should surface it.
    assert data["status"] == "ok"
    assert len(data["candidates"]) >= 1
    cand = data["candidates"][0]
    assert cand["edge_claimed"] is False
    assert cand["units"] == "probability"


# ---------------------------------------------------------------------------
# (E): missing proposals file -> unavailable, never green
# ---------------------------------------------------------------------------

def test_clv_corpus_missing_file_unavailable():
    """(E): absent proposals file -> status='unavailable', edge_claimed=False."""
    with tempfile.TemporaryDirectory() as tmp:
        proposals = Path(tmp) / "does_not_exist.jsonl"
        # Do NOT create the file.

        with patch.object(routes_mod, "_PROPOSALS_PATH", proposals), \
             patch("predict_service.frontend.clv_corpus_routes._pipeline_enabled",
                   return_value=False):
            client = TestClient(app_mod.app, raise_server_exceptions=False)
            resp = client.get("/api/improve/clv-corpus")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unavailable", (
        "missing file must return 'unavailable', got %r" % data["status"]
    )
    assert data["status"] != "ok", "missing proposals file must never be green"
    assert data.get("edge_claimed") is not True
    assert data["candidates"] == []
    assert _no_banned_keys(data)


# ---------------------------------------------------------------------------
# (D): /openapi.json lists /api/improve/clv-corpus
# ---------------------------------------------------------------------------

def test_openapi_lists_clv_corpus_route():
    """(D): openapi.json includes /api/improve/clv-corpus after mount."""
    client = TestClient(app_mod.app, raise_server_exceptions=False)
    resp = client.get("/openapi.json")
    assert resp.status_code == 200, "openapi.json must be reachable, got %d" % resp.status_code
    spec = resp.json()
    paths = spec.get("paths", {})
    assert "/api/improve/clv-corpus" in paths, (
        "/api/improve/clv-corpus not found in openapi paths: %r" % list(paths.keys())
    )


# ---------------------------------------------------------------------------
# (B)+(C): empty proposals file -> INSUFFICIENT_DATA, no banned keys
# ---------------------------------------------------------------------------

def test_clv_corpus_empty_file_insufficient_data():
    """(B)+(C): empty proposals file -> INSUFFICIENT_DATA, no banned keys, edge_claimed=False."""
    with tempfile.TemporaryDirectory() as tmp:
        proposals = Path(tmp) / "proposals.jsonl"
        proposals.write_text("", encoding="utf-8")  # present but empty

        with patch.object(routes_mod, "_PROPOSALS_PATH", proposals), \
             patch("predict_service.frontend.clv_corpus_routes._pipeline_enabled",
                   return_value=False):
            client = TestClient(app_mod.app, raise_server_exceptions=False)
            resp = client.get("/api/improve/clv-corpus")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in _VALID_STATUSES
    assert _no_banned_keys(data)
    assert data.get("edge_claimed") is not True


# ---------------------------------------------------------------------------
# (B)+(C): multi-row payload, all rows clean
# ---------------------------------------------------------------------------

def test_clv_corpus_multi_row_no_banned_keys():
    """Multi-row file: all candidate rows must be clean (no banned keys, edge_claimed=False)."""
    lines = [
        _proposal_line(name="nba", n_rep=1),
        _proposal_line(name="mlb", n_rep=2, decision="SHIP"),
        _proposal_line(name="soccer", n_rep=0, saw_proxy=True, all_positive=False),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        proposals = Path(tmp) / "proposals.jsonl"
        proposals.write_text("\n".join(lines), encoding="utf-8")

        with patch.object(routes_mod, "_PROPOSALS_PATH", proposals), \
             patch("predict_service.frontend.clv_corpus_routes._pipeline_enabled",
                   return_value=False):
            client = TestClient(app_mod.app, raise_server_exceptions=False)
            resp = client.get("/api/improve/clv-corpus")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert _no_banned_keys(data)
    assert data.get("edge_claimed") is not True
    for cand in data["candidates"]:
        assert cand["edge_claimed"] is False
        assert cand["units"] == "probability"
