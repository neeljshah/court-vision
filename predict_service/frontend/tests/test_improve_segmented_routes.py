"""Per-file tests for predict_service.frontend.improve_segmented_routes (BE7-4).

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/frontend/tests/test_improve_segmented_routes.py -q

Acceptance (5 gates):
  (1) 3-market ledger fixture -> rows filterable by market (ml / total / prop)
  (2) missing ledger -> status=unavailable (never green), edge_claimed=false
  (3) thin market (under-N rows) -> INSUFFICIENT_DATA surfaced (never green)
  (4) no banned $/pnl/roi key in any response
  (5) edge_claimed=False always; n_promoted=0 -> '0 ships' in honest_note

ASCII only; never raises; per-file test.
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import predict_service.frontend.improve_segmented_routes as seg_mod
from predict_service.frontend.improve_segmented_routes import router

# ---------------------------------------------------------------------------
# Shared helpers
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
    """Return True iff no KEY name matches a banned dollar/profit pattern."""
    for k in _all_keys(obj):
        if _BANNED_KEY_RE.match(k):
            return False
    return True


def _jsonl_row(market: str, brier: float, ece: float,
               status: str = "GRADED",
               ts: str = "2026-06-01T12:00:00",
               note: str = "calibration != edge") -> str:
    row = {
        "market": market,
        "status": status,
        "ts": ts,
        "readout": {"raw_brier": brier, "raw_ece": ece},
        "note": note,
    }
    return json.dumps(row)


def _call(ledger_path: Path, market: str = None) -> Dict[str, Any]:
    """Call /api/improve/ledger/segmented with the ledger injected."""
    app = FastAPI()
    app.include_router(router)
    params: Dict[str, Any] = {"ledger_path": str(ledger_path)}
    if market is not None:
        params["market"] = market
    with patch.object(seg_mod, "_SEGMENTED_LEDGER_PATH", ledger_path):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/improve/ledger/segmented", params=params)
    assert resp.status_code == 200, (
        "route must return 200; got %d: %s" % (resp.status_code, resp.text)
    )
    return resp.json()


# ---------------------------------------------------------------------------
# Gate 1: 3-market fixture -- rows filterable by market
# ---------------------------------------------------------------------------


def test_three_market_fixture_filterable_by_market():
    """Gate 1: 3-market ledger -> filtering by each market returns only that market's rows."""
    rows = [
        # ml market -- 2 rows
        _jsonl_row("nba:moneyline", 0.30, 0.05, ts="2026-06-01T10:00:00"),
        _jsonl_row("nba:moneyline", 0.25, 0.04, ts="2026-06-02T10:00:00"),
        # total market -- 1 row
        _jsonl_row("nba:total", 0.28, 0.06, ts="2026-06-01T10:00:00"),
        # prop market -- 3 rows
        _jsonl_row("nba:prop:pts", 0.33, 0.08, ts="2026-06-01T10:00:00"),
        _jsonl_row("nba:prop:pts", 0.31, 0.07, ts="2026-06-02T10:00:00"),
        _jsonl_row("nba:prop:pts", 0.29, 0.06, ts="2026-06-03T10:00:00"),
    ]
    # Pad total market to avoid INSUFFICIENT_DATA threshold masking the test.
    for i in range(9):
        rows.append(_jsonl_row("nba:total", 0.27 + i * 0.001, 0.055,
                               ts="2026-06-%02dT10:00:00" % (i + 2)))
    ledger_text = "\n".join(rows)

    with tempfile.TemporaryDirectory() as tmp:
        seg = Path(tmp) / "improve_ledger_segmented.jsonl"
        seg.write_text(ledger_text, encoding="utf-8")

        # Filter by ml market.
        data_ml = _call(seg, market="nba:moneyline")
        # Filter by total market.
        data_total = _call(seg, market="nba:total")
        # Filter by prop market.
        data_prop = _call(seg, market="nba:prop:pts")
        # No filter -> all rows.
        data_all = _call(seg)

    # ml filter: only ml rows returned.
    for row in data_ml["rows"]:
        assert row["market"] == "nba:moneyline", (
            "ml filter returned wrong market: %r" % row["market"]
        )
    # total filter: only total rows.
    for row in data_total["rows"]:
        assert row["market"] == "nba:total", (
            "total filter returned wrong market: %r" % row["market"]
        )
    # prop filter: only prop rows.
    for row in data_prop["rows"]:
        assert row["market"] == "nba:prop:pts", (
            "prop filter returned wrong market: %r" % row["market"]
        )
    # No filter returns rows for all three markets.
    markets_in_all = {r["market"] for r in data_all["rows"]}
    assert "nba:moneyline" in markets_in_all
    assert "nba:total" in markets_in_all
    assert "nba:prop:pts" in markets_in_all

    # Summary covers all markets.
    assert "nba:moneyline" in data_all["summary"]
    assert "nba:total" in data_all["summary"]
    assert "nba:prop:pts" in data_all["summary"]

    # edge_claimed=false throughout.
    assert data_ml["edge_claimed"] is False
    assert data_total["edge_claimed"] is False
    assert data_prop["edge_claimed"] is False


# ---------------------------------------------------------------------------
# Gate 2: missing ledger -> status=unavailable, never green
# ---------------------------------------------------------------------------


def test_missing_ledger_returns_unavailable():
    """Gate 2: missing ledger file -> status=unavailable, edge_claimed=false, never ok."""
    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp) / "does_not_exist.jsonl"
        # DO NOT create the file.

        app = FastAPI()
        app.include_router(router)
        with patch.object(seg_mod, "_SEGMENTED_LEDGER_PATH", missing):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/api/improve/ledger/segmented")

    assert resp.status_code == 200, "must return 200 even when unavailable"
    data = resp.json()
    assert data["status"] == "unavailable", (
        "missing ledger must yield status=unavailable, got: %r" % data["status"]
    )
    assert data["status"] != "ok", "status must never be ok for missing ledger"
    assert data["edge_claimed"] is False
    assert data["rows"] == [], "rows must be empty for missing ledger"
    assert data["n_promoted"] == 0
    assert _no_banned_keys(data)


# ---------------------------------------------------------------------------
# Gate 3: thin market -> INSUFFICIENT_DATA, never green
# ---------------------------------------------------------------------------


def test_thin_market_returns_insufficient_data():
    """Gate 3: market with fewer than _MIN_N_PER_MARKET rows -> INSUFFICIENT_DATA."""
    # Write 3 rows for a market (well below the 10-row threshold).
    rows = [
        _jsonl_row("tennis:moneyline", 0.28, 0.05, status="GRADED",
                   ts="2026-06-%02dT10:00:00" % i)
        for i in range(1, 4)
    ]
    ledger_text = "\n".join(rows)

    with tempfile.TemporaryDirectory() as tmp:
        seg = Path(tmp) / "improve_ledger_segmented.jsonl"
        seg.write_text(ledger_text, encoding="utf-8")

        data = _call(seg, market="tennis:moneyline")

    assert data["status"] == "ok", "route status is ok even when market is thin"
    # All non-SHIP rows must surface INSUFFICIENT_DATA (never green calibration).
    for row in data["rows"]:
        if row.get("status") != "SHIP":
            assert row["status"] == "INSUFFICIENT_DATA", (
                "thin market row must be INSUFFICIENT_DATA, got: %r" % row["status"]
            )
            assert row["brier"] is None, (
                "thin market row must not fabricate brier, got: %r" % row["brier"]
            )
            assert row["ece"] is None

    # Summary reflects INSUFFICIENT_DATA.
    summary = data.get("summary", {})
    if "tennis:moneyline" in summary:
        assert summary["tennis:moneyline"]["latest_status"] == "INSUFFICIENT_DATA"

    assert data["edge_claimed"] is False
    assert _no_banned_keys(data)


# ---------------------------------------------------------------------------
# Gate 4: no banned $/pnl/roi key in any response
# ---------------------------------------------------------------------------


def test_no_banned_keys_in_any_response():
    """Gate 4: response must never contain $ / pnl / roi / profit as a key."""
    rows = [
        _jsonl_row("nba:moneyline", 0.25, 0.04, status="SHIP"),
        _jsonl_row("nba:total", 0.27, 0.05, status="HOLD"),
        _jsonl_row("mlb:moneyline", 0.28, 0.05, status="GRADED"),
    ]
    # Pad each to avoid thin-market trigger.
    for mkt in ("nba:moneyline", "nba:total", "mlb:moneyline"):
        for i in range(9):
            rows.append(_jsonl_row(mkt, 0.26, 0.05,
                                   ts="2026-06-%02dT09:00:00" % (i + 2)))
    ledger_text = "\n".join(rows)

    with tempfile.TemporaryDirectory() as tmp:
        seg = Path(tmp) / "improve_ledger_segmented.jsonl"
        seg.write_text(ledger_text, encoding="utf-8")

        data_all = _call(seg)
        data_filtered = _call(seg, market="nba:moneyline")

    assert _no_banned_keys(data_all), (
        "full response must have no banned keys ($, roi, pnl, profit)"
    )
    assert _no_banned_keys(data_filtered), (
        "filtered response must have no banned keys ($, roi, pnl, profit)"
    )

    # Also verify missing-ledger response.
    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp) / "missing.jsonl"
        app = FastAPI()
        app.include_router(router)
        with patch.object(seg_mod, "_SEGMENTED_LEDGER_PATH", missing):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/api/improve/ledger/segmented")
    assert _no_banned_keys(resp.json()), "missing-ledger response must have no banned keys"


# ---------------------------------------------------------------------------
# Gate 5: edge_claimed=False; n_promoted=0 -> '0 ships' marker in honest_note
# ---------------------------------------------------------------------------


def test_edge_claimed_false_and_zero_ships_marker():
    """Gate 5: edge_claimed=False always; n_promoted=0 -> '0 ships' in honest_note."""
    # No SHIP rows.
    rows = [
        _jsonl_row("nba:moneyline", 0.28, 0.05, status="HOLD"),
        _jsonl_row("nba:total", 0.30, 0.06, status="INSUFFICIENT_DATA"),
    ]
    # Pad to avoid thin-market override on nba:moneyline (test only HOLD status).
    for i in range(9):
        rows.append(_jsonl_row("nba:moneyline", 0.27, 0.05, status="HOLD",
                               ts="2026-06-%02dT09:00:00" % (i + 2)))

    ledger_text = "\n".join(rows)

    with tempfile.TemporaryDirectory() as tmp:
        seg = Path(tmp) / "improve_ledger_segmented.jsonl"
        seg.write_text(ledger_text, encoding="utf-8")

        data = _call(seg, market="nba:moneyline")

    assert data["edge_claimed"] is False, "edge_claimed must be False"
    assert data["n_promoted"] == 0, "no SHIP rows -> n_promoted must be 0"
    assert "0 ships" in data["honest_note"].lower(), (
        "honest_note must contain '0 ships' when n_promoted==0; "
        "got: %r" % data["honest_note"]
    )

    # Now test with a SHIP row -- n_promoted>0, no '0 ships' marker needed.
    rows_with_ship = [
        _jsonl_row("nba:moneyline", 0.22, 0.03, status="SHIP"),
    ] + [
        _jsonl_row("nba:moneyline", 0.25, 0.04, status="HOLD",
                   ts="2026-06-%02dT09:00:00" % i)
        for i in range(1, 11)
    ]

    with tempfile.TemporaryDirectory() as tmp:
        seg2 = Path(tmp) / "improve_ledger_segmented.jsonl"
        seg2.write_text("\n".join(rows_with_ship), encoding="utf-8")

        data2 = _call(seg2, market="nba:moneyline")

    assert data2["edge_claimed"] is False, "edge_claimed must always be False"
    assert data2["n_promoted"] == 1, (
        "expected 1 SHIP row; got %d" % data2["n_promoted"]
    )
    assert _no_banned_keys(data2)
