"""Per-file tests for predict_service.frontend.improve_ledger_routes.

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/frontend/tests/test_improve_ledger_routes.py -q

Acceptance criteria (7 gates):
  (1) per_market breakdown present for ml/total/prop markets with brier/ece/delta
  (2) improvement_trend series present per market
  (3) n_promoted==0 -> honest_note contains 'ratchet has not promoted a version yet'
  (4) n_promoted>0 -> counts SHIP rows only
  (5) no $ / roi / pnl / profit key in any response
  (6) absent segmented ledger -> per_market=[], improvement_trend=[], n_promoted=0
  (7) CALIBRATION-only language: edge_claimed=False; no fabricated convergence

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

import predict_service.frontend.improve_ledger_routes as ledger_mod
from predict_service.frontend.improve_ledger_routes import router

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
    """Return True iff no KEY name matches a banned dollar/profit pattern."""
    for k in _all_keys(obj):
        if _BANNED_KEY_RE.match(k):
            return False
    return True


def _seg_row(market: str, brier: float, ece: float, status: str = "GRADED",
             ts: str = "2026-06-01T12:00:00") -> str:
    row = {
        "market": market,
        "status": status,
        "ts": ts,
        "readout": {"raw_brier": brier, "raw_ece": ece},
        "note": "calibration != edge",
    }
    return json.dumps(row)


def _make_client(seg_ledger_path: Path, main_ledger_path: Path) -> TestClient:
    """Build a TestClient with both ledger paths patched at the module level."""
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    return client


def _call(seg_path: Path, main_path: Path) -> dict:
    """Call /api/improve/ledger with both ledger paths injected."""
    app = FastAPI()
    app.include_router(router)
    with patch.object(ledger_mod, "_SEGMENTED_LEDGER_PATH", seg_path), \
         patch.object(ledger_mod, "_LEDGER_PATH", main_path), \
         patch.object(ledger_mod, "_pipeline_enabled", return_value=False), \
         patch(
             "scripts.platformkit.improve.improvement_trend._DEFAULT_LEDGER",
             seg_path,
         ):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/improve/ledger")
    assert resp.status_code == 200, "route must return 200"
    return resp.json()


# ---------------------------------------------------------------------------
# Gate 1: per_market breakdown for ml/total/prop with brier/ece/delta
# ---------------------------------------------------------------------------


def test_per_market_breakdown_has_brier_ece_delta():
    """Gate 1: per_market has ml/total/prop entries with brier, ece, delta."""
    rows = [
        # nba:moneyline (ml) -- two rows so delta is computable
        _seg_row("nba:moneyline", 0.30, 0.05, ts="2026-06-01T10:00:00"),
        _seg_row("nba:moneyline", 0.25, 0.04, ts="2026-06-02T10:00:00"),
        # nba:total -- single row, delta should be null
        _seg_row("nba:total", 0.28, 0.06, ts="2026-06-01T10:00:00"),
        # nba:prop -- single row
        _seg_row("nba:prop", 0.32, 0.07, ts="2026-06-01T10:00:00"),
    ]
    seg_text = "\n".join(rows)

    with tempfile.TemporaryDirectory() as tmp:
        seg = Path(tmp) / "improve_ledger_segmented.jsonl"
        seg.write_text(seg_text, encoding="utf-8")
        main = Path(tmp) / "improve_ledger.jsonl"
        main.write_text("", encoding="utf-8")

        data = _call(seg, main)

    pm = {e["market"]: e for e in data["per_market"]}

    # ml market
    assert "nba:moneyline" in pm, "nba:moneyline must appear in per_market"
    ml = pm["nba:moneyline"]
    assert ml["brier"] is not None, "brier must be present"
    assert ml["ece"] is not None, "ece must be present"
    # delta: brier went from 0.30 to 0.25, delta = 0.25 - 0.30 = -0.05
    assert ml["delta"] is not None, "delta must be computable from 2 rows"
    assert abs(ml["delta"] - (-0.05)) < 1e-5, "delta must reflect brier decrease"

    # total market (single row -> delta null)
    assert "nba:total" in pm
    assert pm["nba:total"]["brier"] is not None
    assert pm["nba:total"]["delta"] is None, "single row -> delta must be null"

    # prop market
    assert "nba:prop" in pm
    assert pm["nba:prop"]["brier"] is not None


# ---------------------------------------------------------------------------
# Gate 2: improvement_trend series present per market
# ---------------------------------------------------------------------------


def test_improvement_trend_series_present():
    """Gate 2: improvement_trend list contains per-market trend entries."""
    rows = [
        _seg_row("nba:moneyline", 0.30, 0.05, ts="2026-06-01T10:00:00"),
        _seg_row("nba:moneyline", 0.25, 0.04, ts="2026-06-02T10:00:00"),
        _seg_row("nba:moneyline", 0.20, 0.03, ts="2026-06-03T10:00:00"),
    ]

    with tempfile.TemporaryDirectory() as tmp:
        seg = Path(tmp) / "improve_ledger_segmented.jsonl"
        seg.write_text("\n".join(rows), encoding="utf-8")
        main = Path(tmp) / "improve_ledger.jsonl"
        main.write_text("", encoding="utf-8")

        data = _call(seg, main)

    trend_by_mkt = {e["market"]: e for e in data["improvement_trend"]}
    assert "nba:moneyline" in trend_by_mkt, "nba:moneyline must appear in improvement_trend"
    entry = trend_by_mkt["nba:moneyline"]
    assert "n_data_cycles" in entry
    assert "monotone_improving" in entry
    assert "regression_flag" in entry
    assert "status" in entry


# ---------------------------------------------------------------------------
# Gate 3: n_promoted==0 -> honest_note contains the ratchet message
# ---------------------------------------------------------------------------


def test_n_promoted_zero_honest_note():
    """Gate 3: when no SHIP rows exist, honest_note says ratchet has not promoted."""
    rows = [
        _seg_row("nba:moneyline", 0.28, 0.05, status="HOLD"),
        _seg_row("nba:total", 0.30, 0.06, status="INSUFFICIENT_DATA"),
    ]

    with tempfile.TemporaryDirectory() as tmp:
        seg = Path(tmp) / "improve_ledger_segmented.jsonl"
        seg.write_text("\n".join(rows), encoding="utf-8")
        main = Path(tmp) / "improve_ledger.jsonl"
        main.write_text("", encoding="utf-8")

        data = _call(seg, main)

    assert data["n_promoted"] == 0, "n_promoted must be 0 when no SHIP rows"
    assert "ratchet has not promoted a version yet" in data["honest_note"], (
        "honest_note must contain the ratchet message when n_promoted==0; "
        "got: %r" % data["honest_note"]
    )
    assert data["edge_claimed"] is False


# ---------------------------------------------------------------------------
# Gate 4: n_promoted counts SHIP rows only
# ---------------------------------------------------------------------------


def test_n_promoted_counts_only_ship_rows():
    """Gate 4: n_promoted == number of SHIP status rows in segmented ledger."""
    rows = [
        _seg_row("nba:moneyline", 0.25, 0.04, status="SHIP"),
        _seg_row("nba:total", 0.27, 0.05, status="HOLD"),
        _seg_row("mlb:moneyline", 0.26, 0.05, status="SHIP"),
        _seg_row("tennis:moneyline", 0.29, 0.06, status="REJECT"),
        _seg_row("soccer:ou", 0.31, 0.07, status="INSUFFICIENT_DATA"),
    ]

    with tempfile.TemporaryDirectory() as tmp:
        seg = Path(tmp) / "improve_ledger_segmented.jsonl"
        seg.write_text("\n".join(rows), encoding="utf-8")
        main = Path(tmp) / "improve_ledger.jsonl"
        main.write_text("", encoding="utf-8")

        data = _call(seg, main)

    assert data["n_promoted"] == 2, (
        "n_promoted must equal SHIP row count; expected 2, got %d" % data["n_promoted"]
    )
    # When n_promoted > 0, honest_note should NOT say 'ratchet has not promoted'
    assert "ratchet has not promoted a version yet" not in data["honest_note"], (
        "ratchet message must not appear when n_promoted > 0"
    )


# ---------------------------------------------------------------------------
# Gate 5: no banned keys in any response
# ---------------------------------------------------------------------------


def test_no_banned_keys_in_response():
    """Gate 5: response must contain no $ / roi / pnl / profit keys."""
    rows = [
        _seg_row("nba:moneyline", 0.28, 0.05, status="SHIP"),
        _seg_row("nba:total", 0.30, 0.06, status="HOLD"),
    ]

    with tempfile.TemporaryDirectory() as tmp:
        seg = Path(tmp) / "improve_ledger_segmented.jsonl"
        seg.write_text("\n".join(rows), encoding="utf-8")
        main = Path(tmp) / "improve_ledger.jsonl"
        main.write_text("", encoding="utf-8")

        data = _call(seg, main)

    assert _no_banned_keys(data), (
        "response must have no banned keys ($, roi, pnl, profit)"
    )
    assert data["edge_claimed"] is False


# ---------------------------------------------------------------------------
# Gate 6: absent segmented ledger -> per_market=[], improvement_trend=[], n_promoted=0
# ---------------------------------------------------------------------------


def test_absent_segmented_ledger_returns_empty_blocks():
    """Gate 6: missing segmented ledger -> empty per_market and improvement_trend."""
    with tempfile.TemporaryDirectory() as tmp:
        seg = Path(tmp) / "does_not_exist.jsonl"
        main = Path(tmp) / "improve_ledger.jsonl"
        main.write_text("", encoding="utf-8")

        data = _call(seg, main)

    assert data["per_market"] == [], "absent segmented ledger -> per_market empty"
    assert data["improvement_trend"] == [], "absent segmented ledger -> trend empty"
    assert data["n_promoted"] == 0, "absent segmented ledger -> n_promoted=0"
    assert data["edge_claimed"] is False
    assert _no_banned_keys(data)


# ---------------------------------------------------------------------------
# Gate 7: CALIBRATION-only language; no fabricated convergence
# ---------------------------------------------------------------------------


def test_calibration_only_no_fabricated_convergence():
    """Gate 7: edge_claimed=False; INSUFFICIENT_DATA surfaces verbatim."""
    # One market with INSUFFICIENT_DATA (no readout).
    insuf_row = json.dumps({
        "market": "nba:moneyline",
        "status": "INSUFFICIENT_DATA",
        "ts": "2026-06-01T10:00:00",
        "n": 5,
        "min_n": 30,
        "reason": "only 5 settled rows",
        "note": "calibration != edge",
    })

    with tempfile.TemporaryDirectory() as tmp:
        seg = Path(tmp) / "improve_ledger_segmented.jsonl"
        seg.write_text(insuf_row, encoding="utf-8")
        main = Path(tmp) / "improve_ledger.jsonl"
        main.write_text("", encoding="utf-8")

        data = _call(seg, main)

    assert data["edge_claimed"] is False, "edge_claimed must be False"
    # The INSUFFICIENT_DATA market must appear in per_market with null brier
    # (no readout -> brier=null, not fabricated).
    pm = {e["market"]: e for e in data["per_market"]}
    if "nba:moneyline" in pm:
        ml = pm["nba:moneyline"]
        assert ml["status"] == "INSUFFICIENT_DATA"
        assert ml["brier"] is None, "INSUFFICIENT_DATA row must not fabricate a brier"
    # n_promoted must be 0 (no SHIP rows)
    assert data["n_promoted"] == 0
    assert _no_banned_keys(data)
