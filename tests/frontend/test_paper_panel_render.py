"""Per-file test: paper panel API contract validation.

Validates the API response shapes that PaperTrailPanel, PaperBetRow, and
ClvSummaryStrip consume from GET /api/paper/trail and GET /api/paper/clv.

Because the project has no JS test runner configured (no jest/vitest), this
Python test verifies the backend contract matches the TypeScript prop types
defined in the React components.  Any shape drift here breaks the panel.

Run: python -m pytest tests/frontend/test_paper_panel_render.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from frontend.serve import app

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _write_ledger(path: Path, rows: list) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return str(path)


def _open_row(
    matchup: str = "NYK@SAS",
    sport: str = "nba",
    ts: str = "2026-06-18T22:00:00+00:00",
) -> dict:
    return {
        "ts": ts,
        "sport": sport,
        "matchup": matchup,
        "side": "away",
        "taken_book": "espn:DraftKings",
        "taken_decimal": 2.6,
        "model_prob": 0.4145,
        "stake_units": 1.0,
        "market_type": "moneyline",
        "status": "open",
        "executed": False,
    }


def _settled_row(
    matchup: str = "NYK@SAS",
    sport: str = "nba",
    ts: str = "2026-06-18T22:00:00+00:00",
) -> dict:
    """A genuine PROXY-close settle: clv_pct set, clv_is_proxy EXPLICITLY True."""
    base = _open_row(matchup, sport, ts)
    base.update(
        {
            "status": "settled",
            "settled_at": "2026-06-18T23:00:00+00:00",
            "clv_pct": 0.85,
            "beat_close": True,
            "clv_is_proxy": True,
            "clv_status": "proxy",
            "graded": True,
            "outcome": "win",
            "home_score": 90,
            "away_score": 94,
            "unit_result": 1.6,
            "settle_key": "nba|NYK@SAS|away|espn:DraftKings|2.6|" + ts,
        }
    )
    return base


@pytest.fixture()
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# TrailRow shape -- must match PaperBetRow.TrailRow interface in TypeScript
# ---------------------------------------------------------------------------

# Exact set of fields the React PaperBetRow component destructures.
_TRAIL_ROW_FIELDS = {
    "game_id",           # string  -- synthetic "<sport>|<matchup>|<ts>"
    "matchup",           # string
    "sport",             # string
    "side",              # "home" | "away"
    "taken_book",        # string
    "taken_decimal",     # float | null
    "model_prob",        # float | null
    "model_ev",          # float | null  (EV per unit, not dollars)
    "tier",              # "A" | "B" | "C" | null
    "status",            # "open" | "settled"
    "graded",            # bool
    "outcome",           # "win" | "loss" | null
    "clv_pct",           # float | null
    "beat_close",        # bool | null
    "clv_is_proxy",      # bool
    "clv_note",          # string | null
    "executed",          # ALWAYS false
    "ts",                # ISO-8601 string
    "settled_at",        # ISO-8601 string | null
}

# Fields the React ClvSummaryStrip component destructures from /api/paper/clv.
_CLV_RESPONSE_FIELDS = {
    "status",           # "ok" | "unavailable"
    "n_bets",           # int
    "pct_beat_close",   # float | null
    "mean_clv_pct",     # float | null
    "clv_is_proxy",     # bool
    "by_sport",         # dict[sport -> {n, mean_clv_pct, pct_beat_close}]
    "note",             # string
    "honest_note",      # string
}

# Fields inside each by_sport entry.
_BY_SPORT_FIELDS = {"n", "mean_clv_pct", "pct_beat_close"}


def test_trail_row_matches_react_interface(client, tmp_path):
    """Every key in TrailRow interface exists on the API response row."""
    p = _write_ledger(tmp_path / "l.jsonl", [_open_row()])
    r = client.get("/api/paper/trail", params={"ledger": p})
    assert r.status_code == 200
    rows = r.json()["trail"]
    assert len(rows) == 1
    missing = _TRAIL_ROW_FIELDS - set(rows[0].keys())
    assert not missing, "TrailRow fields missing from API: %s" % sorted(missing)


def test_trail_row_executed_always_false(client, tmp_path):
    """PaperTrailPanel relies on executed=false invariant; never a real bet."""
    p = _write_ledger(tmp_path / "l.jsonl", [_open_row(), _settled_row()])
    r = client.get("/api/paper/trail", params={"ledger": p})
    for row in r.json()["trail"]:
        assert row["executed"] is False, (
            "executed must be False on every row (paper-only invariant)"
        )


def test_trail_row_no_dollar_fields(client, tmp_path):
    """React panel must never receive $ROI or profit fields."""
    p = _write_ledger(tmp_path / "l.jsonl", [_open_row(), _settled_row()])
    r = client.get("/api/paper/trail", params={"ledger": p})
    for row in r.json()["trail"]:
        keys_lower = {k.lower() for k in row}
        for banned in ("dollar", "roi", "profit", "stake"):
            assert banned not in keys_lower, (
                "Banned field '%s' must not reach the React panel" % banned
            )


def test_trail_row_model_ev_is_ev_not_dollars(client, tmp_path):
    """model_ev is (model_prob * taken_decimal) - 1, NOT a dollar amount."""
    p = _write_ledger(tmp_path / "l.jsonl", [_open_row()])
    r = client.get("/api/paper/trail", params={"ledger": p})
    row = r.json()["trail"][0]
    # 0.4145 * 2.6 - 1.0 = 0.0777
    assert row["model_prob"] == pytest.approx(0.4145)
    assert row["taken_decimal"] == pytest.approx(2.6)
    expected = 0.4145 * 2.6 - 1.0
    assert row["model_ev"] == pytest.approx(expected, rel=1e-4), (
        "model_ev must be EV per unit (probability-space), not a dollar amount"
    )


def test_clv_response_matches_react_interface(client, tmp_path):
    """Every key in ClvData interface exists on the /api/paper/clv response."""
    p = _write_ledger(tmp_path / "l.jsonl", [_settled_row()])
    r = client.get("/api/paper/clv", params={"ledger": p})
    assert r.status_code == 200
    body = r.json()
    missing = _CLV_RESPONSE_FIELDS - set(body.keys())
    assert not missing, "ClvData fields missing from API: %s" % sorted(missing)


def test_clv_by_sport_shape(client, tmp_path):
    """by_sport entries carry the three fields ClvSummaryStrip renders."""
    # Two settled bets in different sports; MLB has a real CLV value.
    mlb_row = _open_row("BOS@ATL", "mlb", "2026-06-18T19:00:00+00:00")
    mlb_settled = dict(mlb_row)
    mlb_settled.update(
        {
            "status": "settled",
            "settled_at": "2026-06-18T21:00:00+00:00",
            "clv_pct": 0.025,      # positive real CLV
            "beat_close": True,
            "clv_is_proxy": False,
            "clv_note": None,
            "graded": True,
            "outcome": "win",
            "home_score": 3,
            "away_score": 5,
            "unit_result": 1.6,
            "settle_key": "mlb|BOS@ATL|away|espn:DraftKings|2.6|"
                          + mlb_row["ts"],
        }
    )
    p = _write_ledger(tmp_path / "l.jsonl", [mlb_settled])
    r = client.get("/api/paper/clv", params={"ledger": p})
    body = r.json()
    by_sport = body.get("by_sport", {})
    # There should be an 'mlb' entry.
    assert "mlb" in by_sport, "by_sport must include 'mlb'"
    entry = by_sport["mlb"]
    missing = _BY_SPORT_FIELDS - set(entry.keys())
    assert not missing, "by_sport entry missing fields: %s" % sorted(missing)


def test_clv_honest_note_always_present(client, tmp_path):
    """honest_note is always present; ClvSummaryStrip shows the paper label."""
    p = str(tmp_path / "empty.jsonl")
    r = client.get("/api/paper/clv", params={"ledger": p})
    body = r.json()
    assert "honest_note" in body
    assert body["honest_note"], "honest_note must be non-empty"


def test_clv_proxy_badge_condition(client, tmp_path):
    """ClvSummaryStrip shows the proxy badge when clv_is_proxy=True (explicit)."""
    # Settled row with an EXPLICIT proxy close (clv_is_proxy=True from the grader).
    p = _write_ledger(tmp_path / "l.jsonl", [_settled_row()])
    r = client.get("/api/paper/clv", params={"ledger": p})
    body = r.json()
    assert body["clv_is_proxy"] is True, (
        "Panel must receive clv_is_proxy=True so it shows the proxy CLV badge"
    )


def test_trail_response_envelope(client, tmp_path):
    """
    PaperTrailPanel checks status=='ok' before rendering rows.
    The envelope must carry status, count, trail, honest_note.
    """
    p = _write_ledger(tmp_path / "l.jsonl", [_open_row()])
    r = client.get("/api/paper/trail", params={"ledger": p})
    body = r.json()
    for key in ("status", "count", "trail", "honest_note"):
        assert key in body, "Envelope key '%s' missing" % key
    assert body["status"] == "ok"
    assert isinstance(body["trail"], list)
    assert isinstance(body["count"], int)


def test_unavailable_state_graceful(client, tmp_path):
    """
    When the ledger is missing, API returns status=ok with empty trail --
    PaperTrailPanel must show the empty state, not crash.
    """
    missing = str(tmp_path / "nonexistent.jsonl")
    r = client.get("/api/paper/trail", params={"ledger": missing})
    body = r.json()
    assert body["status"] == "ok"
    assert body["trail"] == []
    assert body["count"] == 0


def test_settled_first_ordering(client, tmp_path):
    """
    PaperTrailPanel renders settled rows first.
    The API must return settled before open.
    """
    rows = [
        _open_row("BOS@MIA", "nba", "2026-06-18T22:01:00+00:00"),
        _settled_row("NYK@SAS", "nba", "2026-06-18T22:00:00+00:00"),
    ]
    p = _write_ledger(tmp_path / "l.jsonl", rows)
    r = client.get("/api/paper/trail", params={"ledger": p})
    trail = r.json()["trail"]
    assert len(trail) == 2
    assert trail[0]["status"] == "settled", "Settled rows must come first"
    assert trail[1]["status"] == "open"


def test_clv_no_dollar_fields_in_response(client, tmp_path):
    """HONESTY: the word 'dollar', 'roi', 'profit' must not appear in the CLV response."""
    p = _write_ledger(tmp_path / "l.jsonl", [_settled_row()])
    r = client.get("/api/paper/clv", params={"ledger": p})
    body_str = json.dumps(r.json()).lower()
    for banned in ("dollar", "roi", "profit", "$edge"):
        assert banned not in body_str, (
            "Banned term '%s' found in CLV response" % banned
        )
