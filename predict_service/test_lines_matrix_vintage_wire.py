"""predict_service.test_lines_matrix_vintage_wire -- vintage-wire acceptance tests.

BE7-2 (captured_at_vintage) wired into lines_matrix_routes.lines_matrix().
Acceptance criteria (per workstream spec):
  W1. Unchanged price keeps original captured_at (not now()).
  W2. Changed price advances captured_at.
  W3. Final/post game_state -> is_close=True on every served row.
  W4. pre/live game_state -> is_close untouched (stays False).
  W5. Absent history (first serve) -> passthrough, no crash.
  W6. No $ field on any response key.
  W7. No regression: existing route shape (status/sport/game_id/markets/best) intact.

Run (per-file only -- never run the full suite, it freezes the box)::
    cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/test_lines_matrix_vintage_wire.py -q
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# ---------------------------------------------------------------------------
# FastAPI TestClient import guard
# ---------------------------------------------------------------------------
try:
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
except ImportError:
    pytest.skip("fastapi not installed", allow_module_level=True)

# ---------------------------------------------------------------------------
# Build a minimal test app around the router
# ---------------------------------------------------------------------------
import predict_service.frontend.lines_matrix_routes as _lmr

app = FastAPI()
app.include_router(_lmr.router)
client = TestClient(app)

# ---------------------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------------------
_ORIG_TS = "2026-06-19T18:00:00Z"
_NEW_TS  = "2026-06-19T20:30:00Z"

# A past commence_time that puts the game >2.5h ago -> game_state='post'.
_POST_COMMENCE  = (
    datetime.now(timezone.utc) - timedelta(hours=4)
).strftime("%Y-%m-%dT%H:%M:%SZ")

# A future commence_time -> game_state='pre'.
_PRE_COMMENCE = (
    datetime.now(timezone.utc) + timedelta(hours=2)
).strftime("%Y-%m-%dT%H:%M:%SZ")

# ---------------------------------------------------------------------------
# Helpers: build minimal aggregate() payloads
# ---------------------------------------------------------------------------

def _mk_payload(
    game_id: str = "g1",
    commence_time: str = _PRE_COMMENCE,
    dk_home: float = 1.91,
    as_of: str = _NEW_TS,
) -> Dict[str, Any]:
    """Minimal aggregate() return value with one moneyline event."""
    return {
        "status": "ok",
        "as_of": as_of,
        "sources": {"espn": "ok"},
        "events": [{
            "event_id": game_id,
            "sport": "nba",
            "home": "Knicks",
            "away": "Spurs",
            "commence_time": commence_time,
            "prices": {
                "draftkings": {"home": dk_home, "away": 2.10},
            },
            "source": "test",
            "as_of": as_of,
        }],
    }


def _get_rows(data: Dict[str, Any], market: str = "moneyline") -> List[Dict[str, Any]]:
    """Flatten markets[market] into a list of row dicts."""
    rows = []
    for side_rows in data.get("markets", {}).get(market, {}).values():
        rows.extend(side_rows)
    return rows


def _has_dollar_key(obj: Any) -> bool:
    if isinstance(obj, dict):
        return any("$" in str(k) or _has_dollar_key(v) for k, v in obj.items())
    if isinstance(obj, list):
        return any(_has_dollar_key(i) for i in obj)
    return False


# ---------------------------------------------------------------------------
# W5: first serve (absent history) -> passthrough, no crash
# ---------------------------------------------------------------------------

def test_w5_absent_history_first_serve_no_crash():
    """First call ever for a game_id: no history, must passthrough gracefully."""
    _lmr._history_cache.clear()
    with patch.object(_lmr, "aggregate", return_value=_mk_payload("g_w5")):
        resp = client.get("/api/lines/nba/g_w5")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "ok"
    rows = _get_rows(data)
    assert rows, "Expected at least one moneyline row"
    # captured_at must equal as_of (the payload's as_of)
    for r in rows:
        assert r["captured_at"] == _NEW_TS, (
            "W5: first-serve row must keep as_of as captured_at; got %r" % r
        )


# ---------------------------------------------------------------------------
# W1: second serve with same price -> original captured_at preserved
# ---------------------------------------------------------------------------

def test_w1_unchanged_price_keeps_original_captured_at():
    """Second serve with identical price: captured_at must stay at first-serve ts."""
    _lmr._history_cache.clear()
    game_id = "g_w1"
    payload_first = _mk_payload(game_id, as_of=_ORIG_TS, dk_home=1.91)
    payload_second = _mk_payload(game_id, as_of=_NEW_TS,  dk_home=1.91)

    with patch.object(_lmr, "aggregate", return_value=payload_first):
        resp1 = client.get(f"/api/lines/nba/{game_id}")
    assert resp1.status_code == 200

    with patch.object(_lmr, "aggregate", return_value=payload_second):
        resp2 = client.get(f"/api/lines/nba/{game_id}")
    assert resp2.status_code == 200
    rows = _get_rows(resp2.json())
    home_rows = [r for r in rows if r.get("book") == "draftkings"]
    assert home_rows, "Expected dk rows"
    for r in home_rows:
        assert r["captured_at"] == _ORIG_TS, (
            "W1: unchanged price must keep ORIGINAL ts %r; got %r" % (_ORIG_TS, r)
        )


# ---------------------------------------------------------------------------
# W2: second serve with changed price -> captured_at advances
# ---------------------------------------------------------------------------

def test_w2_changed_price_advances_captured_at():
    """Second serve with a different dk_home odds: changed-price rows advance."""
    _lmr._history_cache.clear()
    game_id = "g_w2"
    payload_first  = _mk_payload(game_id, as_of=_ORIG_TS, dk_home=1.91)
    payload_second = _mk_payload(game_id, as_of=_NEW_TS,  dk_home=1.85)  # changed

    with patch.object(_lmr, "aggregate", return_value=payload_first):
        client.get(f"/api/lines/nba/{game_id}")

    with patch.object(_lmr, "aggregate", return_value=payload_second):
        resp2 = client.get(f"/api/lines/nba/{game_id}")
    assert resp2.status_code == 200
    data = resp2.json()
    # The home side for draftkings changed (1.91->1.85); check its captured_at advanced.
    # markets["moneyline"]["home"] = [{book, odds, captured_at, ...}, ...]
    home_rows = data.get("markets", {}).get("moneyline", {}).get("home", [])
    dk_home = [r for r in home_rows if r.get("book") == "draftkings"]
    assert dk_home, "Expected dk home moneyline row"
    for r in dk_home:
        assert r["captured_at"] == _NEW_TS, (
            "W2: changed home price must advance to new ts; got %r" % r
        )
    # Sanity: away side is unchanged (2.10 in both); its captured_at stays at ORIG.
    away_rows = data.get("markets", {}).get("moneyline", {}).get("away", [])
    dk_away = [r for r in away_rows if r.get("book") == "draftkings"]
    assert dk_away, "Expected dk away moneyline row"
    for r in dk_away:
        assert r["captured_at"] == _ORIG_TS, (
            "W2: unchanged away price must keep original ts; got %r" % r
        )


# ---------------------------------------------------------------------------
# W3: post/Final game_state -> is_close=True on every row
# ---------------------------------------------------------------------------

def test_w3_post_game_sets_is_close_true():
    """Game that ended >2.5h ago: is_close must be True on all rows."""
    _lmr._history_cache.clear()
    game_id = "g_w3"
    payload = _mk_payload(game_id, commence_time=_POST_COMMENCE)
    with patch.object(_lmr, "aggregate", return_value=payload):
        resp = client.get(f"/api/lines/nba/{game_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("game_state") == "post", (
        "W3: post-game must have game_state=post in response; got %r" % data.get("game_state")
    )
    rows = _get_rows(data)
    assert rows
    for r in rows:
        assert r.get("is_close") is True, (
            "W3: every row of a post-game must have is_close=True; got %r" % r
        )


# ---------------------------------------------------------------------------
# W4: pre/live game_state -> is_close stays False
# ---------------------------------------------------------------------------

def test_w4_pre_game_is_close_stays_false():
    """Future game: is_close must stay False on all rows."""
    _lmr._history_cache.clear()
    game_id = "g_w4"
    payload = _mk_payload(game_id, commence_time=_PRE_COMMENCE)
    with patch.object(_lmr, "aggregate", return_value=payload):
        resp = client.get(f"/api/lines/nba/{game_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("game_state") in ("pre", "live"), data.get("game_state")
    rows = _get_rows(data)
    assert rows
    for r in rows:
        assert r.get("is_close") is False, (
            "W4: pre-game row must have is_close=False; got %r" % r
        )


# ---------------------------------------------------------------------------
# W6: no $ field anywhere in the response
# ---------------------------------------------------------------------------

def test_w6_no_dollar_key_in_response():
    _lmr._history_cache.clear()
    with patch.object(_lmr, "aggregate", return_value=_mk_payload("g_w6")):
        resp = client.get("/api/lines/nba/g_w6")
    assert resp.status_code == 200
    assert not _has_dollar_key(resp.json()), "W6: no $ key allowed in response"


# ---------------------------------------------------------------------------
# W7: route shape regression -- status/sport/game_id/markets/best present
# ---------------------------------------------------------------------------

def test_w7_response_shape_no_regression():
    _lmr._history_cache.clear()
    with patch.object(_lmr, "aggregate", return_value=_mk_payload("g_w7")):
        resp = client.get("/api/lines/nba/g_w7")
    assert resp.status_code == 200
    data = resp.json()
    for key in ("status", "sport", "game_id", "markets", "best",
                "honest_note", "edge_claimed", "game_state", "captured_at"):
        assert key in data, f"W7: missing key {key!r} in response; got {list(data)}"
    assert data["status"] == "ok"
    assert data["sport"] == "nba"
    assert data["game_id"] == "g_w7"
    assert data["edge_claimed"] is False
    assert "moneyline" in data["markets"], "W7: moneyline must be present"
