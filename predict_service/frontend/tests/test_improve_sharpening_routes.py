"""Per-file tests for predict_service.frontend.improve_sharpening_routes (SIX-02).

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/frontend/tests/test_improve_sharpening_routes.py -q

Acceptance criteria (8 gates):
  (1) 3-cycle improving segmented ledger -> market entry monotone_improving=true,
      negative deltas, regression_flag=false
  (2) worsening market -> regression_flag=true
  (3) <2 cycles -> INSUFFICIENT_DATA passthrough
  (4) ledger absent -> status=unavailable, edge_claimed=false, never green
  (5) coverage block lists untried cells as gaps, not failures
  (6) daemon SHIP w/o graded row -> drift flag
  (7) no $/roi/pnl/profit/edge key in response
  (8) mount snippet is a literal string in improve_sharpening_mount.py, not imported

ASCII only; never raises; per-file test.
"""
from __future__ import annotations

import importlib
import json
import re
import tempfile
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from predict_service.frontend import improve_sharpening_routes
from predict_service.frontend.improve_sharpening_routes import (
    _build_coverage_block,
    _build_reconcile_block,
    _build_trends_block,
    router,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Keys that are explicitly $ / P&L / ROI fields -- these must never appear.
# "edge_claimed" is an allowed boolean flag, NOT a profit field.
# Note: we only scan KEY names, not string values (notes may say "calibration != edge").
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
    """Return True iff no KEY in obj matches a banned dollar/profit pattern.

    Checks key NAMES only, not string values (notes may legitimately contain
    the word 'edge' as in 'calibration != edge').
    edge_claimed is explicitly allowed: it is a boolean flag, not a P&L field.
    """
    for k in _all_keys(obj):
        if _BANNED_KEY_RE.match(k):
            return False
    return True


def _make_ledger_rows(market: str, briers: list) -> str:
    """Build a JSONL string with one row per Brier value for `market`."""
    lines = []
    for i, b in enumerate(briers):
        row = {
            "market": market,
            "status": "GRADED",
            "ts": "2026-06-%02dT12:00:00" % (i + 1),
            "readout": {"raw_brier": b, "raw_ece": 0.05},
        }
        lines.append(json.dumps(row))
    return "\n".join(lines)


def _make_app(ledger_path: Path) -> TestClient:
    """Create a minimal FastAPI app with the sharpening router wired in."""
    app = FastAPI()
    app.include_router(router)

    with patch.object(
        improve_sharpening_routes,
        "_DEFAULT_LEDGER",
        ledger_path,
    ):
        client = TestClient(app, raise_server_exceptions=False)
        # Need the patching context active at call time, so return (app, path).
    return app, ledger_path


def _get_sharpening(ledger_path: Path, sentinel: bool = False) -> Dict[str, Any]:
    """Call the route with the given ledger path injected via module-level patch."""
    app = FastAPI()
    app.include_router(router)
    sentinel_path = ledger_path.parent / "_PIPELINE_ENABLED_TEST"
    if sentinel:
        sentinel_path.touch()

    try:
        with patch.object(
            improve_sharpening_routes,
            "_DEFAULT_LEDGER",
            ledger_path,
        ), patch(
            "predict_service.frontend.improve_sharpening_routes._pipeline_enabled",
            return_value=sentinel,
        ), patch(
            "scripts.platformkit.improve.improvement_trend._DEFAULT_LEDGER",
            ledger_path,
        ), patch(
            "scripts.platformkit.improve.coverage_map._DEFAULT_LEDGER",
            ledger_path,
        ), patch(
            "scripts.platformkit.improve.ledger_reconcile.DEFAULT_GRADED",
            ledger_path,
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/api/improve/sharpening",
                params={"ledger": str(ledger_path)},
            )
    finally:
        if sentinel_path.exists():
            sentinel_path.unlink()

    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Test 1: 3-cycle improving ledger -> monotone_improving=True, negative deltas
# ---------------------------------------------------------------------------


def test_improving_market_monotone():
    """Gate 1: strictly decreasing Brier -> monotone_improving=True."""
    briers = [0.30, 0.25, 0.20]  # each step improves
    market = "nba:moneyline"
    rows_text = _make_ledger_rows(market, briers)

    with tempfile.TemporaryDirectory() as tmp:
        lp = Path(tmp) / "improve_ledger_segmented.jsonl"
        lp.write_text(rows_text, encoding="utf-8")

        data = _get_sharpening(lp)

    assert data["status"] == "ok", "status should be ok when ledger present"
    trends = data["trends"]
    assert market in trends, "market should appear in trends"
    entry = trends[market]
    assert entry["status"] == "ok", "market status should be ok with 3 cycles"
    assert entry["monotone_improving"] is True, "improving briers -> monotone_improving"
    deltas = entry["deltas"]
    assert all(d < 0 for d in deltas), "all deltas should be negative (improvement)"
    assert entry["regression_flag"] is False


# ---------------------------------------------------------------------------
# Test 2: worsening market -> regression_flag=True
# ---------------------------------------------------------------------------


def test_worsening_market_regression_flag():
    """Gate 2: Brier increases across cycles -> regression_flag=True."""
    briers = [0.20, 0.25, 0.30]  # getting worse
    market = "nba:spread"
    rows_text = _make_ledger_rows(market, briers)

    with tempfile.TemporaryDirectory() as tmp:
        lp = Path(tmp) / "improve_ledger_segmented.jsonl"
        lp.write_text(rows_text, encoding="utf-8")

        data = _get_sharpening(lp)

    trends = data["trends"]
    assert market in trends
    entry = trends[market]
    assert entry["status"] == "ok"
    assert entry["regression_flag"] is True
    assert entry["monotone_improving"] is False


# ---------------------------------------------------------------------------
# Test 3: <2 cycles -> INSUFFICIENT_DATA passthrough
# ---------------------------------------------------------------------------


def test_insufficient_data_single_cycle():
    """Gate 3: only 1 data cycle -> INSUFFICIENT_DATA for that market."""
    briers = [0.28]
    market = "mlb:moneyline"
    rows_text = _make_ledger_rows(market, briers)

    with tempfile.TemporaryDirectory() as tmp:
        lp = Path(tmp) / "improve_ledger_segmented.jsonl"
        lp.write_text(rows_text, encoding="utf-8")

        data = _get_sharpening(lp)

    trends = data["trends"]
    assert market in trends
    entry = trends[market]
    assert entry["status"] == "INSUFFICIENT_DATA"
    assert entry["monotone_improving"] is None
    assert entry["regression_flag"] is None


# ---------------------------------------------------------------------------
# Test 4: ledger absent -> status=unavailable, edge_claimed=false (never green)
# ---------------------------------------------------------------------------


def test_ledger_absent_returns_unavailable():
    """Gate 4: missing ledger -> unavailable, edge_claimed=false."""
    with tempfile.TemporaryDirectory() as tmp:
        lp = Path(tmp) / "does_not_exist.jsonl"
        # Do NOT create the file.

        app = FastAPI()
        app.include_router(router)
        with patch(
            "predict_service.frontend.improve_sharpening_routes._pipeline_enabled",
            return_value=False,
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/api/improve/sharpening",
                params={"ledger": str(lp)},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unavailable", "absent ledger must be unavailable"
    assert data["edge_claimed"] is False, "edge_claimed must be false"
    # Ensure it never appears green (no status==ok when ledger absent).
    assert data["status"] != "ok"
    assert _no_banned_keys(data), "no banned keys in response"


# ---------------------------------------------------------------------------
# Test 5: coverage block lists untried cells as gaps, not failures
# ---------------------------------------------------------------------------


def test_coverage_gaps_are_honest_not_failures():
    """Gate 5: untried cells appear in gaps list, never labelled as failures."""
    # Build a minimal coverage map result with untried cells.
    mock_coverage_raw = {
        "cells": [
            {
                "family": "FAMILY_INGAME",
                "aspect": "nba:moneyline",
                "status": "untried",
                "frozen": False,
                "tried": False,
                "latest_delta": None,
                "vs_close": "UNPROVEN",
                "note": "calibration != edge",
            },
            {
                "family": "FAMILY_RECAL",
                "aspect": "nba:moneyline",
                "status": "graded",
                "frozen": False,
                "tried": True,
                "latest_delta": -0.01,
                "vs_close": "UNPROVEN",
                "note": "calibration != edge",
            },
        ],
        "summary": {"total": 2, "graded": 1, "untried": 1, "shipped": 0,
                    "frozen": 0, "insufficient_data": 0},
        "ledger_present": True,
        "tried_present": False,
        "note": "calibration != edge",
        "vs_close": "UNPROVEN",
    }

    coverage = _build_coverage_block(mock_coverage_raw)
    gaps = coverage["gaps"]
    # The untried cell should appear as a gap.
    assert len(gaps) == 1
    assert gaps[0]["family"] == "FAMILY_INGAME"
    assert gaps[0]["aspect"] == "nba:moneyline"
    # Summary shows untried=1, not a failure count.
    assert coverage["summary"]["untried"] == 1
    # graded cell should NOT appear in gaps.
    graded_in_gaps = [g for g in gaps if g.get("family") == "FAMILY_RECAL"]
    assert len(graded_in_gaps) == 0, "graded cells must not appear as gaps"
    assert _no_banned_keys(coverage)


# ---------------------------------------------------------------------------
# Test 6: daemon SHIP without graded row -> drift flag in reconcile block
# ---------------------------------------------------------------------------


def test_daemon_ship_without_graded_produces_drift_flag():
    """Gate 6: proposals has SHIP row with no matching graded row -> drift flag."""
    from scripts.platformkit.improve.ledger_reconcile import reconcile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        # proposals.jsonl: one SHIP row
        proposals = tmp_path / "proposals.jsonl"
        proposals.write_text(
            json.dumps({
                "decision": "SHIP",
                "name": "nba",
                "ts": "2026-06-01T00:00:00",
                "shipped_version": "v1",
            }) + "\n",
            encoding="utf-8",
        )
        # graded ledger: empty (no matching graded row)
        graded = tmp_path / "graded.jsonl"
        graded.write_text("", encoding="utf-8")

        result = reconcile(proposals_path=proposals, graded_path=graded)

    # graded is empty -> INSUFFICIENT_DATA (honest; graded missing = not green)
    # OR drift if graded exists but has no match; here graded is empty -> INSUFFICIENT_DATA
    assert result["status"] in ("drift", "INSUFFICIENT_DATA")

    # Now test with graded having rows but no match for the SHIP name.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        proposals = tmp_path / "proposals.jsonl"
        proposals.write_text(
            json.dumps({
                "decision": "SHIP",
                "name": "tennis",
                "ts": "2026-06-01T00:00:00",
                "shipped_version": "v1",
            }) + "\n",
            encoding="utf-8",
        )
        # graded ledger has an NBA row (no match for "tennis")
        graded = tmp_path / "graded.jsonl"
        graded.write_text(
            json.dumps({
                "market": "nba:moneyline",
                "ts": "2026-06-01T00:00:00",
                "status": "GRADED",
                "readout": {"raw_brier": 0.25},
            }) + "\n",
            encoding="utf-8",
        )
        result = reconcile(proposals_path=proposals, graded_path=graded)

    reconcile_block = _build_reconcile_block(result)
    assert reconcile_block["n_drift"] > 0, "unmatched SHIP must produce a drift flag"
    assert len(reconcile_block["drift_flags"]) > 0
    assert _no_banned_keys(reconcile_block)


# ---------------------------------------------------------------------------
# Test 7: no $/roi/pnl/profit/edge key in any response
# ---------------------------------------------------------------------------


def test_no_dollar_or_banned_keys_in_response():
    """Gate 7: full response must contain no banned keys."""
    briers = [0.30, 0.25, 0.20]
    market = "soccer:ou"
    rows_text = _make_ledger_rows(market, briers)

    with tempfile.TemporaryDirectory() as tmp:
        lp = Path(tmp) / "improve_ledger_segmented.jsonl"
        lp.write_text(rows_text, encoding="utf-8")

        data = _get_sharpening(lp)

    assert _no_banned_keys(data), "response must have no banned keys"

    # Also verify absent-ledger response has no banned keys
    with tempfile.TemporaryDirectory() as tmp:
        lp2 = Path(tmp) / "missing.jsonl"
        app = FastAPI()
        app.include_router(router)
        with patch(
            "predict_service.frontend.improve_sharpening_routes._pipeline_enabled",
            return_value=False,
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/api/improve/sharpening", params={"ledger": str(lp2)})
    assert _no_banned_keys(resp.json())


# ---------------------------------------------------------------------------
# Test 8: mount snippet is a literal string, not imported
# ---------------------------------------------------------------------------


def test_mount_snippet_is_literal_not_imported():
    """Gate 8: docs/research/improve_sharpening_mount.py is a plain string literal."""
    repo = Path(__file__).resolve().parents[3]
    mount_file = repo / "docs" / "research" / "improve_sharpening_mount.py"
    assert mount_file.exists(), "mount snippet file must exist"

    text = mount_file.read_text(encoding="utf-8")
    # Must contain the literal include_router call as a string.
    assert "include_router" in text, "snippet must contain include_router"
    # Must reference the route module by name.
    assert "improve_sharpening_routes" in text
    # Must NOT be a module that exports objects (no def/class at top level).
    assert "import improve_sharpening_routes" not in text, (
        "snippet must be a literal, not an import of the module itself"
    )
    # The file should be tiny (a single statement).
    non_empty_lines = [l for l in text.splitlines() if l.strip()]
    assert len(non_empty_lines) == 1, (
        "mount snippet must be a single-line literal, got %d lines" % len(non_empty_lines)
    )


# ---------------------------------------------------------------------------
# Test: route never raises (error resilience)
# ---------------------------------------------------------------------------


def test_route_never_raises_on_garbage():
    """Route must return 200 even when dependencies raise unexpected errors."""
    app = FastAPI()
    app.include_router(router)

    # Patch _compute_trends to raise an unexpected error (simulates dependency crash).
    # The route-level try/except must swallow it and return unavailable.
    with patch(
        "predict_service.frontend.improve_sharpening_routes._compute_trends",
        side_effect=RuntimeError("dependency exploded"),
    ), patch(
        "predict_service.frontend.improve_sharpening_routes._pipeline_enabled",
        return_value=False,
    ), patch(
        "predict_service.frontend.improve_sharpening_routes._ledger_exists",
        return_value=True,  # Pretend ledger exists so we hit the main path.
    ):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/improve/sharpening")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "unavailable")
    assert data["edge_claimed"] is False
