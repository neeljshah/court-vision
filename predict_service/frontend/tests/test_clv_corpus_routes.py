"""Per-file tests for predict_service.frontend.clv_corpus_routes (BE7-5, SI-06).

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/frontend/tests/test_clv_corpus_routes.py -q

Acceptance criteria:
  (1) single-corpus candidate (n_rep=1) -> replication_label=REPLICATION_PENDING
  (2) all-proxy corpus (saw_proxy=True, all_positive=False) -> vs_close=UNPROVEN
  (3) missing proposals file -> status=unavailable, edge_claimed=false, never green
  (4) no $ / roi / pnl / profit key anywhere in any response
  (5) edge_claimed=false on every response shape
  (6) two-corpus candidate (n_rep=2) -> replication_label=REPLICATED
  (7) INSUFFICIENT_DATA when file exists but has no candidate rows

ASCII only; never raises; per-file test.
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import predict_service.frontend.clv_corpus_routes as routes_mod
from predict_service.frontend.clv_corpus_routes import router, _build_candidate_row

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BANNED_KEY_RE = re.compile(r"^(\$|roi|pnl|profit)$", re.IGNORECASE)


def _all_keys(obj: Any):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _all_keys(v)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            yield from _all_keys(item)


def _no_banned_keys(obj: Any) -> bool:
    """True iff no KEY name in obj matches a banned dollar/profit pattern.

    Key names are checked; string values are not (notes may say 'not edge').
    edge_claimed is an allowed boolean flag, not a P&L field.
    """
    for k in _all_keys(obj):
        if _BANNED_KEY_RE.match(str(k)):
            return False
    return True


def _proposal_row(
    name: str = "nba",
    decision: str = "REPLICATION_PENDING",
    n_rep: int = 1,
    saw_proxy: bool = False,
    all_positive: bool = True,
    vs_close: str = "UNPROVEN",
    ts: str = "2026-06-19T12:00:00",
    n_new: int = 10,
    dm_p: float = 0.04,
    delta: float = 0.005,
    significant: bool = True,
) -> str:
    row = {
        "ts": ts,
        "name": name,
        "decision": decision,
        "n_corpora_replicated": n_rep,
        "saw_proxy": saw_proxy,
        "all_positive": all_positive,
        "vs_close": vs_close,
        "n_new": n_new,
        "dm_p": dm_p,
        "delta": delta,
        "significant": significant,
        "reasons": ["calibration test row"],
        "note": "calibration, not edge; PROPOSAL only",
    }
    return json.dumps(row)


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def _call(proposals_path: Path, sentinel: bool = False) -> dict:
    """Call the route with the given proposals_path injected via module-level patch."""
    app = _make_app()
    with patch.object(routes_mod, "_PROPOSALS_PATH", proposals_path), \
         patch(
             "predict_service.frontend.clv_corpus_routes._pipeline_enabled",
             return_value=sentinel,
         ):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/improve/clv-corpus")
    assert resp.status_code == 200, "route must return 200, got %d" % resp.status_code
    return resp.json()


# ---------------------------------------------------------------------------
# Gate 1: single-corpus candidate (n_rep=1) -> REPLICATION_PENDING
# ---------------------------------------------------------------------------


def test_single_corpus_candidate_replication_pending():
    """Gate 1: n_rep=1 -> replication_label=REPLICATION_PENDING."""
    rows = [_proposal_row(name="nba", decision="REPLICATION_PENDING", n_rep=1)]

    with tempfile.TemporaryDirectory() as tmp:
        proposals = Path(tmp) / "proposals.jsonl"
        proposals.write_text("\n".join(rows), encoding="utf-8")

        data = _call(proposals)

    assert data["status"] == "ok", "status should be ok when file has rows"
    assert len(data["candidates"]) == 1

    cand = data["candidates"][0]
    assert cand["n_rep"] == 1
    assert cand["replication_label"] == "REPLICATION_PENDING", (
        "n_rep=1 must produce REPLICATION_PENDING, got %r" % cand["replication_label"]
    )
    assert cand["edge_claimed"] is False
    assert cand["units"] == "probability"
    assert _no_banned_keys(data)


# ---------------------------------------------------------------------------
# Gate 2: all-proxy corpus -> vs_close UNPROVEN (surfaced verbatim)
# ---------------------------------------------------------------------------


def test_all_proxy_corpus_vs_close_unproven():
    """Gate 2: saw_proxy=True AND all_positive=False -> vs_close label is UNPROVEN."""
    rows = [
        _proposal_row(
            name="nba",
            decision="REJECT",
            n_rep=0,
            saw_proxy=True,
            all_positive=False,
            vs_close="UNPROVEN",
        )
    ]

    with tempfile.TemporaryDirectory() as tmp:
        proposals = Path(tmp) / "proposals.jsonl"
        proposals.write_text("\n".join(rows), encoding="utf-8")

        data = _call(proposals)

    assert data["status"] == "ok"
    cand = data["candidates"][0]
    # vs_close must be UNPROVEN (never green) for an all-proxy corpus.
    assert "UNPROVEN" in cand["vs_close"].upper(), (
        "all-proxy corpus must produce UNPROVEN vs_close, got %r" % cand["vs_close"]
    )
    assert cand["edge_claimed"] is False
    assert _no_banned_keys(data)


# ---------------------------------------------------------------------------
# Gate 3: missing proposals file -> unavailable, never green
# ---------------------------------------------------------------------------


def test_missing_proposals_file_returns_unavailable():
    """Gate 3: absent proposals file -> status=unavailable, edge_claimed=false."""
    with tempfile.TemporaryDirectory() as tmp:
        proposals = Path(tmp) / "does_not_exist.jsonl"
        # Do NOT create the file.

        app = _make_app()
        with patch.object(routes_mod, "_PROPOSALS_PATH", proposals), \
             patch(
                 "predict_service.frontend.clv_corpus_routes._pipeline_enabled",
                 return_value=False,
             ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/api/improve/clv-corpus")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unavailable", (
        "absent file must return unavailable, got %r" % data["status"]
    )
    assert data["status"] != "ok", "absent file must never be green"
    assert data["edge_claimed"] is False
    assert data["candidates"] == []
    assert _no_banned_keys(data)


# ---------------------------------------------------------------------------
# Gate 4: no banned keys in any response shape
# ---------------------------------------------------------------------------


def test_no_banned_keys_in_all_response_shapes():
    """Gate 4: no $ / roi / pnl / profit KEY anywhere in any response."""
    # Shape 1: normal candidate row.
    with tempfile.TemporaryDirectory() as tmp:
        proposals = Path(tmp) / "proposals.jsonl"
        proposals.write_text(_proposal_row(n_rep=1), encoding="utf-8")
        data1 = _call(proposals)
    assert _no_banned_keys(data1), "normal response must have no banned keys"

    # Shape 2: absent file -> unavailable shape.
    with tempfile.TemporaryDirectory() as tmp:
        proposals = Path(tmp) / "missing.jsonl"
        data2 = _call(proposals)
    assert _no_banned_keys(data2), "unavailable response must have no banned keys"

    # Shape 3: empty file -> INSUFFICIENT_DATA shape.
    with tempfile.TemporaryDirectory() as tmp:
        proposals = Path(tmp) / "proposals.jsonl"
        proposals.write_text("", encoding="utf-8")
        data3 = _call(proposals)
    assert _no_banned_keys(data3), "INSUFFICIENT_DATA response must have no banned keys"


# ---------------------------------------------------------------------------
# Gate 5: edge_claimed=false on every response shape
# ---------------------------------------------------------------------------


def test_edge_claimed_false_all_shapes():
    """Gate 5: edge_claimed=False on every possible response shape."""
    # Normal.
    with tempfile.TemporaryDirectory() as tmp:
        proposals = Path(tmp) / "proposals.jsonl"
        proposals.write_text(_proposal_row(n_rep=2), encoding="utf-8")
        data = _call(proposals)
    assert data["edge_claimed"] is False

    # Unavailable.
    with tempfile.TemporaryDirectory() as tmp:
        proposals = Path(tmp) / "missing.jsonl"
        data = _call(proposals)
    assert data["edge_claimed"] is False

    # INSUFFICIENT_DATA.
    with tempfile.TemporaryDirectory() as tmp:
        proposals = Path(tmp) / "proposals.jsonl"
        proposals.write_text("", encoding="utf-8")
        data = _call(proposals)
    assert data["edge_claimed"] is False


# ---------------------------------------------------------------------------
# Gate 6: two-corpus candidate (n_rep=2) -> REPLICATED
# ---------------------------------------------------------------------------


def test_two_corpus_candidate_replicated():
    """Gate 6: n_rep=2 -> replication_label=REPLICATED."""
    rows = [_proposal_row(name="nba", decision="SHIP", n_rep=2)]

    with tempfile.TemporaryDirectory() as tmp:
        proposals = Path(tmp) / "proposals.jsonl"
        proposals.write_text("\n".join(rows), encoding="utf-8")

        data = _call(proposals)

    assert data["status"] == "ok"
    cand = data["candidates"][0]
    assert cand["n_rep"] == 2
    assert cand["replication_label"] == "REPLICATED", (
        "n_rep=2 must produce REPLICATED, got %r" % cand["replication_label"]
    )
    assert cand["edge_claimed"] is False


# ---------------------------------------------------------------------------
# Gate 7: file present but empty -> INSUFFICIENT_DATA
# ---------------------------------------------------------------------------


def test_empty_proposals_file_returns_insufficient_data():
    """Gate 7: proposals file exists but has no rows -> INSUFFICIENT_DATA."""
    with tempfile.TemporaryDirectory() as tmp:
        proposals = Path(tmp) / "proposals.jsonl"
        proposals.write_text("", encoding="utf-8")  # file exists, 0 rows

        data = _call(proposals)

    assert data["status"] == "INSUFFICIENT_DATA", (
        "empty file must return INSUFFICIENT_DATA, got %r" % data["status"]
    )
    assert data["candidates"] == []
    assert data["edge_claimed"] is False
    assert _no_banned_keys(data)


# ---------------------------------------------------------------------------
# Unit test: _build_candidate_row does not emit banned keys
# ---------------------------------------------------------------------------


def test_build_candidate_row_no_banned_keys():
    """Unit: _build_candidate_row strips banned keys from raw input."""
    raw = json.loads(_proposal_row(n_rep=1))
    # Inject a fake banned key to verify it's never passed through.
    raw["roi"] = 99.9
    raw["pnl"] = -5.0
    row = _build_candidate_row(raw)
    assert _no_banned_keys(row), "candidate row must have no banned keys"
    assert row["edge_claimed"] is False
    assert row["units"] == "probability"
    assert row["replication_label"] == "REPLICATION_PENDING"


# ---------------------------------------------------------------------------
# Route: never raises on garbage input
# ---------------------------------------------------------------------------


def test_route_never_raises_on_garbage():
    """Route must return 200 even when the proposals file contains garbage JSON."""
    garbage = "not json at all\n{broken\n"

    with tempfile.TemporaryDirectory() as tmp:
        proposals = Path(tmp) / "proposals.jsonl"
        proposals.write_text(garbage, encoding="utf-8")

        data = _call(proposals)

    # Garbage lines are skipped; 0 valid rows -> INSUFFICIENT_DATA.
    assert data["status"] in ("ok", "INSUFFICIENT_DATA", "unavailable")
    assert data["edge_claimed"] is False
    assert _no_banned_keys(data)
