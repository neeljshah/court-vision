"""Offline contract tests for frontend.autonomy_routes.

Asserts the read-only observability contract the CourtVision P6 dashboard reads:
  * GET /api/improve/timeline -- shape + the INERT honesty rail (enabled=False on a
    box with no PIPELINE_ENABLED sentinel; n_promoted never fabricated; no $ key).
  * GET /api/ops/autonomy -- verbatim canonical doc when present+fresh; an honest
    'unavailable' / overall='down' sentinel (never green) on missing/stale.

Uses FastAPI TestClient against a throwaway app -- never binds a real port. The
self-improve outputs are pointed at a tmp dir via monkeypatch so the test is
hermetic and does not depend on real loop state.

Per-file run only:
    python -m pytest tests/frontend/test_autonomy_routes.py -q
"""
from __future__ import annotations

import json

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI               # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import frontend.autonomy_routes as ar     # noqa: E402

_BANNED = ('"$"', '"usd"', '"dollars"', '"dollar"', '"roi"', '"pnl"',
           '"profit"', '"p_n_l"')


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(ar.router)
    return TestClient(app)


def _assert_no_money(payload: dict) -> None:
    raw = json.dumps(payload).lower()
    for forbidden in _BANNED:
        assert forbidden not in raw, forbidden


# -- /api/improve/timeline ----------------------------------------------------

def test_timeline_shape_and_keys() -> None:
    r = _client().get("/api/improve/timeline")
    assert r.status_code == 200
    body = r.json()
    for key in ("status", "cycles", "n_promoted", "enabled", "edge_claimed",
                "honest_note"):
        assert key in body, key
    assert body["edge_claimed"] is False
    assert isinstance(body["cycles"], list)
    assert isinstance(body["n_promoted"], int)
    for c in body["cycles"]:
        for k in ("cycle", "decision", "reason", "at"):
            assert k in c, k
    _assert_no_money(body)


def test_timeline_inert_when_pipeline_disabled(monkeypatch) -> None:
    """The MEASUREMENT-ONLY rail: with the sentinel absent, enabled is False and
    n_promoted is 0 even if the loop logged cycles (it ships nothing)."""
    monkeypatch.setattr(ar, "_pipeline_enabled", lambda: False)
    r = _client().get("/api/improve/timeline")
    body = r.json()
    assert body["enabled"] is False
    # No proposals -> no real promotion can be claimed.
    monkeypatch.setattr(ar, "_n_promoted", lambda: 0)
    body2 = _client().get("/api/improve/timeline").json()
    assert body2["n_promoted"] == 0
    assert "measurement-only" in body2["honest_note"].lower()


def test_timeline_n_promoted_counts_only_real_ships(tmp_path, monkeypatch) -> None:
    """n_promoted counts ONLY proposals rows with SHIP/PROMOTE + a real
    shipped_version; no_candidate / reject / a faked label without a version is 0."""
    proposals = tmp_path / "proposals.jsonl"
    rows = [
        {"decision": "NO_CANDIDATE", "shipped_version": None},
        {"decision": "REJECT", "shipped_version": None},
        {"decision": "SHIP", "shipped_version": None},      # label only, no version
        {"decision": "SHIP", "shipped_version": 3},          # a real promotion
        {"decision": "PROMOTE", "shipped_version": 4},       # a real promotion
    ]
    proposals.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="ascii")
    monkeypatch.setattr(ar, "_IMPROVE_PROPOSALS", proposals)
    assert ar._n_promoted() == 2


# -- /api/ops/autonomy --------------------------------------------------------

def test_autonomy_unavailable_when_missing(tmp_path, monkeypatch) -> None:
    """Never green-on-missing: an absent canonical doc -> unavailable + down."""
    monkeypatch.setattr(ar, "_AUTONOMY_STATUS", tmp_path / "does_not_exist.json")
    r = _client().get("/api/ops/autonomy")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "unavailable"
    assert body["overall"] == "down"
    assert body["edge_claimed"] is False
    _assert_no_money(body)


def test_autonomy_unavailable_when_stale(tmp_path, monkeypatch) -> None:
    """A doc older than the SLA is a DEAD feed -> unavailable + down, never ok."""
    doc = tmp_path / "autonomy_status.json"
    doc.write_text(json.dumps(
        {"overall": "ok", "generated_at": 1.0, "services": []}), encoding="ascii")
    monkeypatch.setattr(ar, "_AUTONOMY_STATUS", doc)
    r = _client().get("/api/ops/autonomy")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "unavailable"
    assert body["overall"] == "down"
    _assert_no_money(body)


def test_autonomy_returns_fresh_doc_verbatim(tmp_path, monkeypatch) -> None:
    """A present + fresh canonical doc is returned verbatim with status ok."""
    import time
    doc = tmp_path / "autonomy_status.json"
    payload = {"overall": "degraded", "generated_at": time.time(),
               "idle_reason": "idle: no newly-settled games to fold",
               "services": []}
    doc.write_text(json.dumps(payload), encoding="ascii")
    monkeypatch.setattr(ar, "_AUTONOMY_STATUS", doc)
    r = _client().get("/api/ops/autonomy")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["overall"] == "degraded"
    assert body["idle_reason"].startswith("idle:")
    assert body["edge_claimed"] is False
    _assert_no_money(body)
