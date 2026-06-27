"""Per-file test: predict_service.frontend.paper_series_routes.

Covers /api/paper/pnl/series and /api/paper/bankroll: verbatim passthrough on a
present file, honest unavailable sentinel on a missing file, and the no-$ rail.
Uses FastAPI TestClient against a tiny app + monkeypatched synthetic data files.
Does NOT depend on the live daemon.

Run: python -m pytest predict_service/frontend/test_paper_series_routes.py -q
"""
from __future__ import annotations

import json
import pathlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from predict_service.frontend import paper_series_routes as psr


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(psr.router)
    return TestClient(app)


_BANNED = ("pnl_dollars", "roi", "profit", "$", "dollar", "usd")


def _assert_no_dollar(text: str) -> None:
    low = text.lower()
    for key in ("pnl_dollars", "\"roi\"", "profit", "dollar", "usd"):
        assert key not in low, "banned key %r leaked: %s" % (key, low[:200])


def test_series_passthrough(tmp_path, monkeypatch):
    doc = {
        "start_units": 100.0,
        "points": [{"ts": "2026-06-20T01:00:00+00:00", "day": "2026-06-20",
                    "balance_units": 99.0, "daily_units": -1.0,
                    "cumulative_units": -1.0, "n_bets": 1, "n_win": 0, "n_loss": 1}],
        "daily": [{"day": "2026-06-20", "daily_units": -1.0}],
        "summary": {"total_units": -1.0, "n_bets": 1, "n_win": 0, "n_loss": 1,
                    "n_push": 0, "win_rate": 0.0,
                    "mean_clv_pct_or_INSUFFICIENT": "INSUFFICIENT",
                    "current_units": 99.0},
        "honest_note": "paper only",
        "edge_claimed": False, "executed": False,
    }
    p = tmp_path / "paper_pnl_series.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(psr, "_SERIES_PATH", p)

    r = _client().get("/api/paper/pnl/series")
    assert r.status_code == 200
    body = r.json()
    assert body["start_units"] == 100.0
    assert body["points"][0]["n_bets"] == 1
    assert body["summary"]["current_units"] == 99.0
    assert body["edge_claimed"] is False and body["executed"] is False
    _assert_no_dollar(r.text)


def test_series_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(psr, "_SERIES_PATH", tmp_path / "does_not_exist.json")
    r = _client().get("/api/paper/pnl/series")
    assert r.status_code == 200  # honest sentinel, never a 500
    body = r.json()
    assert body["status"] == "unavailable"
    assert body["points"] == [] and body["summary"] is None
    assert body["edge_claimed"] is False
    assert "honest_note" in body


def test_series_strips_banned_keys(tmp_path, monkeypatch):
    doc = {"start_units": 100.0, "roi": 0.5, "profit": 999, "points": []}
    p = tmp_path / "paper_pnl_series.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(psr, "_SERIES_PATH", p)
    body = _client().get("/api/paper/pnl/series").json()
    assert "roi" not in body and "profit" not in body
    assert body["start_units"] == 100.0


def test_bankroll_passthrough(tmp_path, monkeypatch):
    doc = {"start_units": 100.0, "current_units": 77.07,
           "updated_at": "2026-06-21T00:16:49+00:00",
           "honest_note": "paper units only", "net_units": -22.93}
    p = tmp_path / "paper_bankroll.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(psr, "_BANKROLL_PATH", p)

    r = _client().get("/api/paper/bankroll")
    assert r.status_code == 200
    body = r.json()
    assert body["start_units"] == 100.0 and body["current_units"] == 77.07
    assert body["edge_claimed"] is False and body["executed"] is False
    _assert_no_dollar(r.text)


def test_bankroll_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(psr, "_BANKROLL_PATH", tmp_path / "missing.json")
    body = _client().get("/api/paper/bankroll").json()
    assert body["status"] == "unavailable"
    assert body["current_units"] is None
    assert body["edge_claimed"] is False


def test_bankroll_corrupt_file_is_unavailable(tmp_path, monkeypatch):
    p = tmp_path / "paper_bankroll.json"
    p.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(psr, "_BANKROLL_PATH", p)
    body = _client().get("/api/paper/bankroll").json()
    assert body["status"] == "unavailable"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
