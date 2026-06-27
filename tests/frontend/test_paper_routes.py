"""Per-file test: frontend.paper_routes -- TestClient hitting /api/paper/trail and /api/paper/clv.

Run: python -m pytest tests/frontend/test_paper_routes.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from frontend.serve import app


# ---------------------------------------------------------------------------
# Stub ledger helpers
# ---------------------------------------------------------------------------

def _write_ledger(path: Path, rows: list) -> str:
    """Write rows to a temp JSONL and return the path as a str (for query param)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return str(path)


def _open_row(matchup: str = "NYK@SAS", sport: str = "nba",
              ts: str = "2026-06-18T22:00:00+00:00") -> dict:
    return {
        "ts": ts, "sport": sport, "matchup": matchup,
        "side": "away", "taken_book": "espn:DK",
        "taken_decimal": 2.6, "model_prob": 0.4145,
        "stake_units": 1.0, "market_type": "moneyline",
        "status": "open", "executed": False,
    }


def _settled_row(matchup: str = "NYK@SAS", sport: str = "nba",
                 ts: str = "2026-06-18T22:00:00+00:00") -> dict:
    """A NO-close settle: clv_pct=None, clv_is_proxy EXPLICITLY False (VOID)."""
    base = _open_row(matchup, sport, ts)
    base.update({
        "status": "settled", "settled_at": "2026-06-18T23:00:00+00:00",
        "clv_pct": None, "beat_close": None, "clv_is_proxy": False,
        "clv_status": "no_close",
        "clv_note": "no closing line captured; CLV unavailable (win/loss only)",
        "graded": True, "outcome": "win",
        "home_score": 90, "away_score": 94, "unit_result": 1.6,
        "settle_key": "nba|NYK@SAS|away|espn:DK|2.6|" + ts,
    })
    return base


def _proxy_settled_row(matchup: str = "BOS@MIA", sport: str = "nba",
                       ts: str = "2026-06-18T22:05:00+00:00") -> dict:
    """A genuine PROXY-close settle: clv_pct set, clv_is_proxy EXPLICITLY True."""
    base = _open_row(matchup, sport, ts)
    base.update({
        "status": "settled", "settled_at": "2026-06-18T23:05:00+00:00",
        "clv_pct": 1.5, "beat_close": True, "clv_is_proxy": True,
        "clv_status": "proxy", "graded": True, "outcome": "win",
        "home_score": 88, "away_score": 95, "unit_result": 1.6,
        "settle_key": "nba|BOS@MIA|away|espn:DK|2.6|" + ts,
    })
    return base


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# GET /api/paper/trail -- empty ledger
# ---------------------------------------------------------------------------

def test_trail_empty_ledger(client, tmp_path):
    ledger = str(tmp_path / "empty.jsonl")
    r = client.get("/api/paper/trail", params={"ledger": ledger})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["count"] == 0
    assert body["trail"] == []
    assert "honest_note" in body


def test_trail_missing_ledger(client, tmp_path):
    """Querying a non-existent ledger file -> status ok, empty trail."""
    r = client.get("/api/paper/trail",
                   params={"ledger": str(tmp_path / "nonexistent.jsonl")})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["trail"] == []


# ---------------------------------------------------------------------------
# GET /api/paper/trail -- with data
# ---------------------------------------------------------------------------

def test_trail_returns_rows(client, tmp_path):
    """One open bet -> one trail row returned."""
    ledger_path = _write_ledger(tmp_path / "ledger.jsonl", [_open_row()])
    r = client.get("/api/paper/trail", params={"ledger": ledger_path})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["count"] == 1
    row = body["trail"][0]
    assert row["sport"] == "nba"
    assert row["executed"] is False


def test_trail_collapse_open_settled(client, tmp_path):
    """Open + settled twin -> exactly one row, status='settled'."""
    rows = [_open_row(), _settled_row()]
    ledger_path = _write_ledger(tmp_path / "ledger.jsonl", rows)
    r = client.get("/api/paper/trail", params={"ledger": ledger_path})
    body = r.json()
    assert body["count"] == 1
    assert body["trail"][0]["status"] == "settled"
    assert body["trail"][0]["executed"] is False


def test_trail_sport_filter(client, tmp_path):
    """sport= filter returns only rows matching that sport."""
    rows = [
        _open_row("NYK@SAS", "nba", "2026-06-18T22:00:00+00:00"),
        _open_row("BOS@ATL", "mlb", "2026-06-18T22:01:00+00:00"),
    ]
    ledger_path = _write_ledger(tmp_path / "ledger.jsonl", rows)
    r = client.get("/api/paper/trail",
                   params={"ledger": ledger_path, "sport": "nba"})
    body = r.json()
    assert body["count"] == 1
    assert body["trail"][0]["sport"] == "nba"


def test_trail_limit(client, tmp_path):
    """limit= caps the number of rows returned."""
    rows = [
        _open_row("G%d@H%d" % (i, i), "nba", "2026-06-18T%02d:00:00+00:00" % i)
        for i in range(10)
    ]
    ledger_path = _write_ledger(tmp_path / "ledger.jsonl", rows)
    r = client.get("/api/paper/trail",
                   params={"ledger": ledger_path, "limit": 3})
    body = r.json()
    assert body["count"] == 3
    assert len(body["trail"]) == 3


def test_trail_row_shape(client, tmp_path):
    """Every trail row has the exact fields the React panel expects."""
    ledger_path = _write_ledger(tmp_path / "ledger.jsonl", [_open_row()])
    r = client.get("/api/paper/trail", params={"ledger": ledger_path})
    row = r.json()["trail"][0]
    expected_fields = {
        "game_id", "matchup", "sport", "side", "taken_book", "taken_decimal",
        "model_prob", "model_ev", "tier", "status", "graded", "outcome",
        "clv_pct", "beat_close", "clv_is_proxy", "clv_note", "executed",
        "ts", "settled_at",
    }
    missing = expected_fields - set(row.keys())
    assert not missing, "Missing trail row fields: %s" % missing


def test_trail_no_dollar_fields(client, tmp_path):
    """HONESTY: no $ / pnl / roi / bankroll / bare-stake key in any trail row.

    stake_units (a UNIT count) is allowed; a bare 'stake' / 'pnl' / 'roi' is not.
    """
    rows = [_open_row(), _settled_row()]
    ledger_path = _write_ledger(tmp_path / "ledger.jsonl", rows)
    r = client.get("/api/paper/trail", params={"ledger": ledger_path})
    banned = {"stake", "pnl", "total_pnl", "total_stake", "paper_roi", "roi",
              "bankroll", "profit", "dollars", "dollar"}
    for row in r.json()["trail"]:
        keys = {k.lower() for k in row}
        assert not (banned & keys), "banned $ keys on trail row: %s" % (banned & keys)
        assert "stake_units" in keys  # units record IS present


# ---------------------------------------------------------------------------
# GET /api/paper/clv -- empty / missing ledger
# ---------------------------------------------------------------------------

def test_clv_empty_ledger(client, tmp_path):
    """Empty ledger -> status ok, n_bets=0, nulls."""
    ledger_path = _write_ledger(tmp_path / "empty.jsonl", [])
    r = client.get("/api/paper/clv", params={"ledger": ledger_path})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["n_bets"] == 0
    assert body["pct_beat_close"] is None
    assert body["mean_clv_pct"] is None


def test_clv_missing_ledger(client, tmp_path):
    """Non-existent ledger -> status ok, n_bets=0."""
    r = client.get("/api/paper/clv",
                   params={"ledger": str(tmp_path / "nonexistent.jsonl")})
    body = r.json()
    assert body["status"] == "ok"
    assert body["n_bets"] == 0


# ---------------------------------------------------------------------------
# GET /api/paper/clv -- with settled data
# ---------------------------------------------------------------------------

def test_clv_response_shape(client, tmp_path):
    """CLV response has all required keys."""
    ledger_path = _write_ledger(tmp_path / "ledger.jsonl", [_settled_row()])
    r = client.get("/api/paper/clv", params={"ledger": ledger_path})
    assert r.status_code == 200
    body = r.json()
    required = {
        "status", "n_bets", "pct_beat_close", "mean_clv_pct",
        "clv_is_proxy", "by_sport", "note", "honest_note",
    }
    missing = required - set(body.keys())
    assert not missing, "Missing CLV response keys: %s" % missing


def test_clv_honest_note_present(client, tmp_path):
    """honest_note is always present and non-empty."""
    ledger_path = str(tmp_path / "empty.jsonl")
    r = client.get("/api/paper/clv", params={"ledger": ledger_path})
    body = r.json()
    assert "honest_note" in body
    assert body["honest_note"]


def test_clv_proxy_flagged_in_summary(client, tmp_path):
    """clv_is_proxy=True ONLY when a settled row is EXPLICITLY a proxy close."""
    ledger_path = _write_ledger(tmp_path / "ledger.jsonl", [_proxy_settled_row()])
    r = client.get("/api/paper/clv", params={"ledger": ledger_path})
    body = r.json()
    assert body["clv_is_proxy"] is True


def test_clv_no_close_not_proxy_in_summary(client, tmp_path):
    """PE-P0-03: a no-close settle is n_no_close, NOT proxy (no fabricated label)."""
    ledger_path = _write_ledger(tmp_path / "ledger.jsonl", [_settled_row()])
    r = client.get("/api/paper/clv", params={"ledger": ledger_path})
    body = r.json()
    assert body["clv_is_proxy"] is False
    assert body.get("n_no_close") == 1


def test_clv_no_dollar_fields(client, tmp_path):
    """HONESTY: no dollar / roi / profit anywhere in CLV response."""
    ledger_path = _write_ledger(tmp_path / "ledger.jsonl", [_settled_row()])
    r = client.get("/api/paper/clv", params={"ledger": ledger_path})
    body_str = json.dumps(r.json()).lower()
    for banned in ("dollar", "roi", "profit", "$edge"):
        assert banned not in body_str, "Banned term in CLV response: %s" % banned


# ---------------------------------------------------------------------------
# POST /api/paper/settle  (BE-P0-03)
# ---------------------------------------------------------------------------

def test_settle_endpoint_status(client, tmp_path):
    """Guarded settle pass returns a status with open/settled/pending counts."""
    ledger_path = _write_ledger(tmp_path / "ledger.jsonl", [])
    r = client.post("/api/paper/settle", params={"ledger": ledger_path})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    for k in ("n_open", "n_settled_now", "n_pending"):
        assert k in body
    assert "honest_note" in body


def test_settle_no_dollar_fields(client, tmp_path):
    ledger_path = _write_ledger(tmp_path / "ledger.jsonl", [_settled_row()])
    r = client.post("/api/paper/settle", params={"ledger": ledger_path})
    s = json.dumps(r.json()).lower()
    for banned in ("\"pnl\"", "paper_roi", "\"stake\"", "bankroll", "dollar"):
        assert banned not in s, "banned term in settle response: %s" % banned


# ---------------------------------------------------------------------------
# GET /api/paper/clv/series  (BE-P1-02/04)
# ---------------------------------------------------------------------------

def test_clv_series_excludes_no_close(client, tmp_path):
    """A no-close (VOID) settle is EXCLUDED from the series -- never plotted as 0."""
    rows = [_settled_row(), _proxy_settled_row()]  # 1 no-close + 1 real CLV
    ledger_path = _write_ledger(tmp_path / "ledger.jsonl", rows)
    r = client.get("/api/paper/clv/series", params={"ledger": ledger_path})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    # only the proxy row (with a real clv_pct) appears; the no-close VOID does not.
    assert body["count"] == 1
    pt = body["series"][0]
    assert pt["clv_pct"] == pytest.approx(1.5)
    assert "cumulative_mean_clv_pct" in pt


def test_clv_series_empty_ledger(client, tmp_path):
    r = client.get("/api/paper/clv/series",
                   params={"ledger": str(tmp_path / "none.jsonl")})
    assert r.status_code == 200
    assert r.json()["count"] == 0
