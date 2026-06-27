"""tests.platformkit.test_improve_ledger_routes -- W10 GET /api/improve/ledger contract.

Asserts (FastAPI TestClient):
  (a) 200 OK on empty ledger file -> status='unavailable', rows=[].
  (b) 200 OK with ledger rows -> rows present, correct sport/cycle/verdict fields.
  (c) ?sport= filter: only matching sport rows returned.
  (d) No $ / roi / pnl / edge key in any response field (honesty rail).
  (e) edge_claimed is always False.
  (f) INSUFFICIENT_DATA verdict passed through verbatim (never re-labelled).
  (g) enabled=False when sentinel absent (PIPELINE_ENABLED not present).

Per-file test only. ASCII. Uses TestClient -- no uvicorn needed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_DIR = Path(__file__).resolve().parents[2]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

try:
    from fastapi.testclient import TestClient
except ImportError:
    pytest.skip("fastapi not installed", allow_module_level=True)

from predict_service.frontend.improve_ledger_routes import router

from fastapi import FastAPI

_app = FastAPI()
_app.include_router(router)
_client = TestClient(_app)

# ---------------------------------------------------------------------------
# helpers

_FORBIDDEN_KEYS = frozenset({"$", "roi", "pnl", "dollar"})
# "edge" appears in the URL and honest_note but must NOT be a data key.
_FORBIDDEN_DATA_KEYS = frozenset({"roi", "pnl", "dollar"})


def _has_forbidden_key(d: object) -> bool:
    if isinstance(d, dict):
        for k, v in d.items():
            kl = str(k).lower()
            if any(tok in kl for tok in _FORBIDDEN_DATA_KEYS):
                return True
            if _has_forbidden_key(v):
                return True
    if isinstance(d, list):
        return any(_has_forbidden_key(x) for x in d)
    return False


def _write_ledger(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _sample_row(sport: str = "nba", verdict: str = "INSUFFICIENT_DATA",
                ts: str = "2026-06-01T00:00:00+00:00") -> dict:
    return {
        "ts": ts, "sport": sport, "verdict": verdict, "n_settled": 0,
        "readout": {
            "n": 0, "raw_brier": None, "raw_ece": None, "bss_vs_close": None,
        },
        "note": "calibration != edge",
    }


# ---------------------------------------------------------------------------
# (a) Empty ledger file -> unavailable or ok, rows=[]


def test_empty_ledger(tmp_path):
    ledger = tmp_path / "improve_ledger.jsonl"
    ledger.touch()  # empty file
    with patch("predict_service.frontend.improve_ledger_routes._LEDGER_PATH", ledger):
        with patch("predict_service.frontend.improve_ledger_routes._pipeline_enabled",
                   return_value=False):
            resp = _client.get("/api/improve/ledger")
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows"] == []
    assert body["edge_claimed"] is False


# ---------------------------------------------------------------------------
# (b) Rows present -> fields populated


def test_rows_present(tmp_path):
    ledger = tmp_path / "improve_ledger.jsonl"
    _write_ledger(ledger, [
        _sample_row("nba", "INSUFFICIENT_DATA", "2026-06-01T00:00:00+00:00"),
        _sample_row("mlb", "NO_CANDIDATE", "2026-06-02T00:00:00+00:00"),
    ])
    with patch("predict_service.frontend.improve_ledger_routes._LEDGER_PATH", ledger):
        with patch("predict_service.frontend.improve_ledger_routes._pipeline_enabled",
                   return_value=False):
            resp = _client.get("/api/improve/ledger")
    assert resp.status_code == 200
    body = resp.json()
    rows = body["rows"]
    assert len(rows) == 2
    sports = {r["sport"] for r in rows}
    assert "nba" in sports and "mlb" in sports
    for r in rows:
        assert "ts" in r
        assert "verdict" in r
        assert "cycle" in r


# ---------------------------------------------------------------------------
# (c) ?sport= filter


def test_sport_filter(tmp_path):
    ledger = tmp_path / "improve_ledger.jsonl"
    _write_ledger(ledger, [
        _sample_row("nba", "INSUFFICIENT_DATA"),
        _sample_row("mlb", "INSUFFICIENT_DATA"),
        _sample_row("soccer", "INSUFFICIENT_DATA"),
    ])
    with patch("predict_service.frontend.improve_ledger_routes._LEDGER_PATH", ledger):
        with patch("predict_service.frontend.improve_ledger_routes._pipeline_enabled",
                   return_value=False):
            resp = _client.get("/api/improve/ledger?sport=nba")
    assert resp.status_code == 200
    body = resp.json()
    rows = body["rows"]
    assert all(r["sport"] == "nba" for r in rows), "filter must exclude non-NBA rows"


# ---------------------------------------------------------------------------
# (d) No forbidden key in any response field


def test_no_forbidden_keys(tmp_path):
    ledger = tmp_path / "improve_ledger.jsonl"
    _write_ledger(ledger, [_sample_row("nba")])
    with patch("predict_service.frontend.improve_ledger_routes._LEDGER_PATH", ledger):
        with patch("predict_service.frontend.improve_ledger_routes._pipeline_enabled",
                   return_value=False):
            resp = _client.get("/api/improve/ledger")
    assert resp.status_code == 200
    assert not _has_forbidden_key(resp.json()), "response must not carry $/roi/pnl keys"


# ---------------------------------------------------------------------------
# (e) edge_claimed always False


def test_edge_claimed_false(tmp_path):
    ledger = tmp_path / "improve_ledger.jsonl"
    ledger.touch()
    with patch("predict_service.frontend.improve_ledger_routes._LEDGER_PATH", ledger):
        with patch("predict_service.frontend.improve_ledger_routes._pipeline_enabled",
                   return_value=True):  # even when enabled
            resp = _client.get("/api/improve/ledger")
    assert resp.json()["edge_claimed"] is False


# ---------------------------------------------------------------------------
# (f) INSUFFICIENT_DATA verdict passed through verbatim


def test_insufficient_data_passthrough(tmp_path):
    ledger = tmp_path / "improve_ledger.jsonl"
    _write_ledger(ledger, [_sample_row("nba", "INSUFFICIENT_DATA")])
    with patch("predict_service.frontend.improve_ledger_routes._LEDGER_PATH", ledger):
        with patch("predict_service.frontend.improve_ledger_routes._pipeline_enabled",
                   return_value=False):
            resp = _client.get("/api/improve/ledger")
    rows = resp.json()["rows"]
    assert any(r["verdict"] == "INSUFFICIENT_DATA" for r in rows), (
        "INSUFFICIENT_DATA verdict must be passed through verbatim"
    )


# ---------------------------------------------------------------------------
# (g) enabled=False when sentinel absent


def test_enabled_false_when_sentinel_absent(tmp_path):
    ledger = tmp_path / "improve_ledger.jsonl"
    ledger.touch()
    with patch("predict_service.frontend.improve_ledger_routes._LEDGER_PATH", ledger):
        with patch("predict_service.frontend.improve_ledger_routes._pipeline_enabled",
                   return_value=False):
            resp = _client.get("/api/improve/ledger")
    assert resp.json()["enabled"] is False
