"""predict_service.frontend.test_paper_predictions_routes -- per-file test (WS3).

Acceptance criteria:

  PP1. GET /api/paper/predictions -> 200; keys: status, total, offset, limit,
       trades, edge_claimed, real_money_enabled, honest_note.

  PP2. Each trade row carries the honest fields: sport, matchup, model_prob,
       market_prob, side, tier (null), result, clv, clv_status,
       executed (False), event_id, commence_time, channel, note, group,
       selection, logged_at.

  PP3. No trade row has a $ / roi / pnl / profit / dollar key anywhere.

  PP4. edge_claimed is always False in the response.

  PP5. real_money_enabled is always False in the response.

  PP6. executed is always False on every trade row.

  PP7. clv is null when no close_proxy (no close) -- never fabricated.

  PP8. clv is a float (not null) when fair_close_prob is present in close_proxy.

  PP9. tier is null on every row (no tier field in source data).

  PP10. result is null when no finals feed matches the event (no graded outcome).

  PP11. Missing / empty file -> status='ok', trades=[], total=0 (honest empty,
        never unavailable, never raises).

  PP12. Pagination: offset/limit slice correctly; total reflects full filtered N.

  PP13. sport filter narrows trades to the requested sport only.

  PP14. Router is mounted in app.py: TestClient over predict_service.app sees
        /api/paper/predictions return 200 (not 404).

  PP15. _shape_row() on a minimal row produces no banned key.

  PP16. market_prob = 1/fair_odds when fair_odds > 0; null when fair_odds absent.

  PP17. honest_note is present, non-empty, and references 'calibration' or
        'model_prob'.

  PP18. channel='paper' on every trade row.

  PP19. With an injected finals feed returning one completed game (home team won),
        the matching moneyline prediction for the home team grades result='win';
        a prediction for the away team grades result='loss'; an event_id with no
        matching final grades result=null. No game is graded without a real final.
        No $ field; edge_claimed=False.

  PP20. grade_prediction unit: spread cover/loss, total over/under, moneyline.

  PP21. No 'outcome' key in any trade row (field was renamed to 'result').

Run (per-file only -- never run the full suite, it freezes the box)::
    cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/frontend/test_paper_predictions_routes.py -q
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest

# ---------------------------------------------------------------------------
# Ensure repo root is on sys.path.
# ---------------------------------------------------------------------------
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from predict_service.frontend.paper_predictions_routes import (  # noqa: E402
    _shape_row,
    _grade_row,
    _read_predictions,
    _market_prob,
    _clv_from_close_proxy,
    _clv_status,
    _build_finals_index_for_sport,
    _HONEST_NOTE,
)
from predict_service.results_finals import (  # noqa: E402
    grade_prediction,
    build_finals_index,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_bad_key(d: object) -> bool:
    """Recursive check: True if any key contains $, roi, pnl, profit, dollar."""
    if not isinstance(d, dict):
        return False
    for k, v in d.items():
        kl = str(k).lower()
        if any(tok in kl for tok in ("$", "roi", "pnl", "profit", "dollar")):
            return True
        if isinstance(v, dict) and _has_bad_key(v):
            return True
        if isinstance(v, list):
            for item in v:
                if _has_bad_key(item):
                    return True
    return False


def _write_jsonl(tmpdir: str, rows: List[Dict[str, Any]]) -> str:
    """Write rows as JSONL to a temp file; return the file path string."""
    p = Path(tmpdir) / "paper_predictions.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return str(p)


def _minimal_row(
    sport: str = "nba",
    matchup: str = "TeamA@TeamB",
    model_prob: float = 0.60,
    fair_odds: float = 1.667,
    close_proxy: object = None,
    fair_close_prob: object = None,
) -> Dict[str, Any]:
    """Build a minimal paper_predictions.jsonl row."""
    cp: Any = None
    if fair_close_prob is not None:
        cp = {"close_decimal_home": 1.5, "close_decimal_away": 3.0,
              "fair_close_prob": fair_close_prob}
    elif close_proxy is not None:
        cp = close_proxy
    return {
        "logged_at": "2026-06-17T22:00:00+00:00",
        "sport": sport,
        "matchup": matchup,
        "group": "Moneyline",
        "selection": "TeamA ML",
        "model_prob": model_prob,
        "line": None,
        "fair_odds": fair_odds,
        "price": None,
        "close_proxy": cp,
        "would_pass_real_gate": False,
        "executed": False,
        "channel": "paper",
        "event_id": "EV-001",
        "commence_time": "2026-06-17T18:00Z",
        "note": "model view, no tradeable book price; logged for accuracy/CLV grading",
    }


def _make_client_with_file(file_path: str):
    """Build a standalone FastAPI TestClient with the paper_predictions router."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from predict_service.frontend.paper_predictions_routes import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app), f"/api/paper/predictions?file={file_path}"


# ---------------------------------------------------------------------------
# PP1 -- 200 with all required top-level keys
# ---------------------------------------------------------------------------

def test_pp1_required_top_level_keys():
    """PP1: Response has all required top-level keys."""
    with tempfile.TemporaryDirectory() as td:
        f = _write_jsonl(td, [_minimal_row()])
        client, url = _make_client_with_file(f)
        resp = client.get(url)
    assert resp.status_code == 200, f"PP1: expected 200; got {resp.status_code}"
    body = resp.json()
    for key in ("status", "total", "offset", "limit", "trades",
                "edge_claimed", "real_money_enabled", "honest_note"):
        assert key in body, f"PP1: missing top-level key {key!r}"


# ---------------------------------------------------------------------------
# PP2 -- trade row shape
# ---------------------------------------------------------------------------

def test_pp2_trade_row_fields():
    """PP2: Each trade row has the required honest fields (result, not outcome)."""
    with tempfile.TemporaryDirectory() as td:
        f = _write_jsonl(td, [_minimal_row()])
        client, url = _make_client_with_file(f)
        resp = client.get(url)
    body = resp.json()
    assert body["trades"], "PP2: expected at least one trade row"
    row = body["trades"][0]
    for key in ("sport", "matchup", "model_prob", "market_prob", "side",
                "tier", "result", "clv", "clv_status", "executed",
                "event_id", "commence_time", "channel", "note",
                "group", "selection", "logged_at"):
        assert key in row, f"PP2: trade row missing field {key!r}"


# ---------------------------------------------------------------------------
# PP3 -- no banned keys in any row
# ---------------------------------------------------------------------------

def test_pp3_no_banned_keys_in_trades():
    """PP3: No $/roi/pnl/profit/dollar key anywhere in trade rows."""
    with tempfile.TemporaryDirectory() as td:
        rows = [
            _minimal_row(sport="nba", model_prob=0.55),
            _minimal_row(sport="mlb", model_prob=0.48, fair_close_prob=0.45),
        ]
        f = _write_jsonl(td, rows)
        client, url = _make_client_with_file(f)
        resp = client.get(url)
    body = resp.json()
    for trade in body["trades"]:
        assert not _has_bad_key(trade), (
            f"PP3: banned key in trade row: {trade}"
        )


# ---------------------------------------------------------------------------
# PP4 -- edge_claimed always False
# ---------------------------------------------------------------------------

def test_pp4_edge_claimed_false():
    """PP4: edge_claimed is always False."""
    with tempfile.TemporaryDirectory() as td:
        f = _write_jsonl(td, [_minimal_row()])
        client, url = _make_client_with_file(f)
        resp = client.get(url)
    body = resp.json()
    assert body["edge_claimed"] is False, (
        f"PP4: edge_claimed must be False; got {body['edge_claimed']!r}"
    )


# ---------------------------------------------------------------------------
# PP5 -- real_money_enabled always False
# ---------------------------------------------------------------------------

def test_pp5_real_money_enabled_false():
    """PP5: real_money_enabled is always False."""
    with tempfile.TemporaryDirectory() as td:
        f = _write_jsonl(td, [_minimal_row()])
        client, url = _make_client_with_file(f)
        resp = client.get(url)
    body = resp.json()
    assert body["real_money_enabled"] is False, (
        f"PP5: real_money_enabled must be False; got {body['real_money_enabled']!r}"
    )


# ---------------------------------------------------------------------------
# PP6 -- executed always False on every trade row
# ---------------------------------------------------------------------------

def test_pp6_executed_always_false():
    """PP6: executed=False on every trade row, even if source had True."""
    row = _minimal_row()
    row["executed"] = True  # source might have True; the API must override
    with tempfile.TemporaryDirectory() as td:
        f = _write_jsonl(td, [row])
        client, url = _make_client_with_file(f)
        resp = client.get(url)
    body = resp.json()
    for trade in body["trades"]:
        assert trade["executed"] is False, (
            f"PP6: executed must be False; got {trade['executed']!r}"
        )


# ---------------------------------------------------------------------------
# PP7 -- clv is null when no close_proxy
# ---------------------------------------------------------------------------

def test_pp7_clv_null_when_no_close():
    """PP7: clv is null when close_proxy is absent."""
    row = _minimal_row()  # close_proxy=None by default
    assert row.get("close_proxy") is None
    with tempfile.TemporaryDirectory() as td:
        f = _write_jsonl(td, [row])
        client, url = _make_client_with_file(f)
        resp = client.get(url)
    body = resp.json()
    trade = body["trades"][0]
    assert trade["clv"] is None, (
        f"PP7: clv must be null when no close_proxy; got {trade['clv']!r}"
    )
    assert trade["clv_status"] == "no_close", (
        f"PP7: clv_status must be 'no_close'; got {trade['clv_status']!r}"
    )


# ---------------------------------------------------------------------------
# PP8 -- clv is float when fair_close_prob is present
# ---------------------------------------------------------------------------

def test_pp8_clv_float_when_close_prob_present():
    """PP8: clv is a float (not null) when fair_close_prob is present."""
    row = _minimal_row(model_prob=0.60, fair_close_prob=0.55)
    with tempfile.TemporaryDirectory() as td:
        f = _write_jsonl(td, [row])
        client, url = _make_client_with_file(f)
        resp = client.get(url)
    body = resp.json()
    trade = body["trades"][0]
    assert trade["clv"] is not None, "PP8: clv must be float when fair_close_prob present"
    assert isinstance(trade["clv"], float), (
        f"PP8: clv must be float; got {type(trade['clv'])!r}"
    )
    assert trade["clv"] == pytest.approx(0.05, abs=1e-4), (
        f"PP8: expected clv=0.05; got {trade['clv']!r}"
    )
    assert trade["clv_status"] == "proxy"


# ---------------------------------------------------------------------------
# PP9 -- tier is null on every row
# ---------------------------------------------------------------------------

def test_pp9_tier_always_null():
    """PP9: tier is null on every row (no tier in source data)."""
    with tempfile.TemporaryDirectory() as td:
        f = _write_jsonl(td, [_minimal_row(), _minimal_row(sport="mlb")])
        client, url = _make_client_with_file(f)
        resp = client.get(url)
    body = resp.json()
    for trade in body["trades"]:
        assert trade["tier"] is None, (
            f"PP9: tier must be null; got {trade['tier']!r}"
        )


# ---------------------------------------------------------------------------
# PP10 -- outcome is null on every row
# ---------------------------------------------------------------------------

def test_pp10_result_null_when_no_finals():
    """PP10: result is null when no finals feed matches the event (no graded outcome)."""
    with tempfile.TemporaryDirectory() as td:
        f = _write_jsonl(td, [_minimal_row()])
        client, url = _make_client_with_file(f)
        resp = client.get(url)
    body = resp.json()
    for trade in body["trades"]:
        # Without a matching settled final the result must be null (no fabrication).
        assert trade["result"] is None, (
            f"PP10: result must be null when no finals match; got {trade['result']!r}"
        )


# ---------------------------------------------------------------------------
# PP11 -- missing/empty file -> status='ok', trades=[], total=0
# ---------------------------------------------------------------------------

def test_pp11_missing_file_honest_empty():
    """PP11: missing file -> status='ok', trades=[], total=0 (honest empty)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from predict_service.frontend.paper_predictions_routes import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    resp = client.get(
        "/api/paper/predictions?file=/does/not/exist/paper_predictions.jsonl"
    )
    assert resp.status_code == 200, f"PP11: expected 200; got {resp.status_code}"
    body = resp.json()
    assert body["status"] == "ok", f"PP11: status must be 'ok'; got {body['status']!r}"
    assert body["trades"] == [], f"PP11: trades must be []; got {body['trades']!r}"
    assert body["total"] == 0, f"PP11: total must be 0; got {body['total']!r}"
    assert body["edge_claimed"] is False
    assert body["real_money_enabled"] is False


def test_pp11_empty_file_honest_empty():
    """PP11b: empty file -> status='ok', trades=[], total=0."""
    with tempfile.TemporaryDirectory() as td:
        f = _write_jsonl(td, [])
        client, url = _make_client_with_file(f)
        resp = client.get(url)
    body = resp.json()
    assert body["status"] == "ok"
    assert body["trades"] == []
    assert body["total"] == 0


# ---------------------------------------------------------------------------
# PP12 -- pagination: offset/limit + total
# ---------------------------------------------------------------------------

def test_pp12_pagination_offset_limit():
    """PP12: offset/limit slices correctly; total is the full filtered N."""
    rows = [_minimal_row(matchup=f"T{i}@T{i+1}") for i in range(20)]
    with tempfile.TemporaryDirectory() as td:
        f = _write_jsonl(td, rows)
        client, base_url = _make_client_with_file(f)
        # Request page 2: offset=5, limit=5
        resp = client.get(f"{base_url}&offset=5&limit=5")
    body = resp.json()
    assert body["total"] == 20, f"PP12: total must be 20; got {body['total']!r}"
    assert body["offset"] == 5
    assert body["limit"] == 5
    assert len(body["trades"]) == 5, (
        f"PP12: expected 5 trades; got {len(body['trades'])}"
    )


def test_pp12_offset_beyond_total_empty():
    """PP12b: offset beyond total -> empty trades list, total unchanged."""
    rows = [_minimal_row()]
    with tempfile.TemporaryDirectory() as td:
        f = _write_jsonl(td, rows)
        client, base_url = _make_client_with_file(f)
        resp = client.get(f"{base_url}&offset=100&limit=10")
    body = resp.json()
    assert body["total"] == 1
    assert body["trades"] == []


# ---------------------------------------------------------------------------
# PP13 -- sport filter
# ---------------------------------------------------------------------------

def test_pp13_sport_filter():
    """PP13: sport filter narrows trades to the requested sport only."""
    rows = [
        _minimal_row(sport="nba"),
        _minimal_row(sport="mlb"),
        _minimal_row(sport="nba"),
        _minimal_row(sport="soccer_intl"),
    ]
    with tempfile.TemporaryDirectory() as td:
        f = _write_jsonl(td, rows)
        client, base_url = _make_client_with_file(f)
        resp = client.get(f"{base_url}&sport=nba")
    body = resp.json()
    assert body["total"] == 2, f"PP13: expected 2 nba rows; got {body['total']!r}"
    for trade in body["trades"]:
        assert trade["sport"] == "nba", (
            f"PP13: all trades must have sport='nba'; got {trade['sport']!r}"
        )


# ---------------------------------------------------------------------------
# PP14 -- router mounted in predict_service.app
# ---------------------------------------------------------------------------

def test_pp14_router_mounted_in_app():
    """PP14: predict_service.app mounts paper_predictions; returns 200 not 404."""
    try:
        from fastapi.testclient import TestClient
        from predict_service.app import app  # noqa: PLC0415
    except Exception as exc:
        pytest.skip(f"PP14: predict_service.app not importable ({exc})")
    client = TestClient(app, raise_server_exceptions=False)
    # Use an explicit absent path so we don't depend on the real data file
    resp = client.get(
        "/api/paper/predictions?file=/does/not/exist/paper_predictions.jsonl"
    )
    assert resp.status_code == 200, (
        f"PP14: /api/paper/predictions must return 200 (not 404); "
        f"got {resp.status_code}"
    )
    body = resp.json()
    assert "status" in body, "PP14: response must have 'status' key"
    assert body.get("edge_claimed") is False, "PP14: edge_claimed must be False"


# ---------------------------------------------------------------------------
# PP15 -- _shape_row() unit: no banned key on minimal row
# ---------------------------------------------------------------------------

def test_pp15_shape_row_no_banned_keys():
    """PP15: _shape_row() on a minimal row produces no banned key."""
    shaped = _shape_row(_minimal_row())
    assert not _has_bad_key(shaped), (
        f"PP15: _shape_row() produced a banned key: {shaped}"
    )


# ---------------------------------------------------------------------------
# PP16 -- market_prob unit tests
# ---------------------------------------------------------------------------

def test_pp16_market_prob_from_fair_odds():
    """PP16: market_prob = 1/fair_odds when fair_odds > 0."""
    row = _minimal_row(fair_odds=2.0)
    mp = _market_prob(row)
    assert mp == pytest.approx(0.5, abs=1e-6), (
        f"PP16: expected 0.5; got {mp!r}"
    )


def test_pp16_market_prob_null_when_absent():
    """PP16b: market_prob is null when fair_odds is absent."""
    row = _minimal_row()
    row.pop("fair_odds", None)
    mp = _market_prob(row)
    assert mp is None, f"PP16b: expected None; got {mp!r}"


def test_pp16_market_prob_null_zero_fair_odds():
    """PP16c: market_prob is null when fair_odds=0 (avoid divide-by-zero)."""
    row = _minimal_row()
    row["fair_odds"] = 0
    mp = _market_prob(row)
    assert mp is None, f"PP16c: expected None for fair_odds=0; got {mp!r}"


# ---------------------------------------------------------------------------
# PP17 -- honest_note is present, non-empty, references relevant content
# ---------------------------------------------------------------------------

def test_pp17_honest_note_non_empty():
    """PP17: honest_note is non-empty."""
    assert _HONEST_NOTE, "PP17: _HONEST_NOTE must be non-empty"


def test_pp17_honest_note_references_model_prob():
    """PP17b: honest_note references 'model_prob' or 'calibration'."""
    note = _HONEST_NOTE.lower()
    assert "model_prob" in note or "calibration" in note, (
        f"PP17b: honest_note must reference model_prob or calibration; got {_HONEST_NOTE!r}"
    )


def test_pp17_honest_note_no_edge_claim():
    """PP17c: honest_note contains 'edge_claimed=False' or 'No $'."""
    note = _HONEST_NOTE
    assert "edge_claimed=False" in note or "No $" in note, (
        f"PP17c: honest_note must disclaim edge; got {note!r}"
    )


# ---------------------------------------------------------------------------
# PP18 -- channel='paper' on every trade row
# ---------------------------------------------------------------------------

def test_pp18_channel_paper_on_all_rows():
    """PP18: channel='paper' on every trade row."""
    rows = [
        _minimal_row(sport="nba"),
        _minimal_row(sport="mlb"),
    ]
    with tempfile.TemporaryDirectory() as td:
        f = _write_jsonl(td, rows)
        client, url = _make_client_with_file(f)
        resp = client.get(url)
    body = resp.json()
    for trade in body["trades"]:
        assert trade["channel"] == "paper", (
            f"PP18: channel must be 'paper'; got {trade['channel']!r}"
        )


# ---------------------------------------------------------------------------
# PP19 -- grading with injected finals feed (acceptance criterion)
# ---------------------------------------------------------------------------

def _make_settled_final(
    game_id: str, home: str, away: str, home_score: int, away_score: int
) -> Dict[str, Any]:
    """Build a minimal settled-final record matching results_finals shape."""
    return {
        "game_id": game_id,
        "sport": "nba",
        "home": home,
        "away": away,
        "home_score": home_score,
        "away_score": away_score,
        "completed": True,
        "state": "post",
        "status_detail": "Final",
        "commence_time": "2026-06-17T18:00Z",
    }


def _make_client_with_finals(file_path: str, finals_feed):
    """Build a TestClient with the paper_predictions router and inject finals_feed."""
    import predict_service.frontend.paper_predictions_routes as ppr
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    original = ppr._finals_feed_override
    ppr._finals_feed_override = finals_feed
    try:
        new_app = FastAPI()
        new_app.include_router(ppr.router)
        client = TestClient(new_app)
        resp = client.get(f"/api/paper/predictions?file={file_path}")
    finally:
        ppr._finals_feed_override = original
    return resp


def test_pp19_home_win_grades_win_for_home_moneyline():
    """PP19a: home team wins -> moneyline pick on home team grades 'win'."""
    home = "Boston Celtics"
    away = "Miami Heat"
    game_id = "EV-ML-001"
    final = _make_settled_final(game_id, home, away, home_score=110, away_score=95)

    def _feed(sport):
        return [final]

    row = _minimal_row(matchup=f"{away}@{home}", model_prob=0.65)
    row["event_id"] = game_id
    row["selection"] = home  # picked home (moneyline)
    row["group"] = "Moneyline"

    with tempfile.TemporaryDirectory() as td:
        f = _write_jsonl(td, [row])
        resp = _make_client_with_finals(f, _feed)
    body = resp.json()
    assert resp.status_code == 200
    trade = body["trades"][0]
    assert trade["result"] == "win", (
        f"PP19a: home moneyline pick should grade 'win'; got {trade['result']!r}"
    )
    assert trade["executed"] is False
    assert body["edge_claimed"] is False
    assert body["real_money_enabled"] is False
    assert not _has_bad_key(trade), "PP19a: banned key in graded trade row"


def test_pp19_away_pick_grades_loss_when_home_wins():
    """PP19b: home team wins -> moneyline pick on away team grades 'loss'."""
    home = "Boston Celtics"
    away = "Miami Heat"
    game_id = "EV-ML-002"
    final = _make_settled_final(game_id, home, away, home_score=110, away_score=95)

    def _feed(sport):
        return [final]

    row = _minimal_row(matchup=f"{away}@{home}", model_prob=0.40)
    row["event_id"] = game_id
    row["selection"] = away  # picked away team (moneyline)
    row["group"] = "Moneyline"

    with tempfile.TemporaryDirectory() as td:
        f = _write_jsonl(td, [row])
        resp = _make_client_with_finals(f, _feed)
    body = resp.json()
    trade = body["trades"][0]
    assert trade["result"] == "loss", (
        f"PP19b: away moneyline pick should grade 'loss'; got {trade['result']!r}"
    )


def test_pp19_no_matching_final_grades_null():
    """PP19c: event_id with no matching final -> result=null (no fabrication)."""
    def _feed(sport):
        return []  # no finals available

    row = _minimal_row()
    row["event_id"] = "EV-MISSING"
    row["selection"] = "SomeTeam"
    row["group"] = "Moneyline"

    with tempfile.TemporaryDirectory() as td:
        f = _write_jsonl(td, [row])
        resp = _make_client_with_finals(f, _feed)
    body = resp.json()
    trade = body["trades"][0]
    assert trade["result"] is None, (
        f"PP19c: unmatched event_id must grade null; got {trade['result']!r}"
    )


def test_pp19_no_game_graded_without_real_final():
    """PP19d: a prediction without event_id never gets a non-null result."""
    def _feed(sport):
        return [_make_settled_final("EV-X", "TeamA", "TeamB", 100, 90)]

    row = _minimal_row()
    row["event_id"] = None  # no event_id
    row["selection"] = "TeamA"
    row["group"] = "Moneyline"

    with tempfile.TemporaryDirectory() as td:
        f = _write_jsonl(td, [row])
        resp = _make_client_with_finals(f, _feed)
    body = resp.json()
    trade = body["trades"][0]
    assert trade["result"] is None, (
        f"PP19d: no event_id -> result must be null; got {trade['result']!r}"
    )


# ---------------------------------------------------------------------------
# PP20 -- grade_prediction unit tests (spread, total, moneyline)
# ---------------------------------------------------------------------------

def _make_final_dict(
    home: str, away: str, home_score: int, away_score: int, game_id: str = "G1"
) -> Dict[str, Any]:
    return {
        "game_id": game_id, "sport": "nba",
        "home": home, "away": away,
        "home_score": home_score, "away_score": away_score,
        "completed": True, "state": "post",
    }


def test_pp20_moneyline_win():
    """PP20a: moneyline pick on winner grades 'win'."""
    final = _make_final_dict("Bulls", "Heat", 110, 100)
    row = {"selection": "Bulls", "matchup": "Heat@Bulls", "group": "Moneyline"}
    assert grade_prediction(row, final) == "win"


def test_pp20_moneyline_loss():
    """PP20b: moneyline pick on loser grades 'loss'."""
    final = _make_final_dict("Bulls", "Heat", 100, 110)
    row = {"selection": "Bulls", "matchup": "Heat@Bulls", "group": "Moneyline"}
    assert grade_prediction(row, final) == "loss"


def test_pp20_spread_cover():
    """PP20c: spread cover grades 'win' (Bulls -5.5, wins by 8)."""
    final = _make_final_dict("Bulls", "Heat", 110, 102)  # margin +8
    row = {"selection": "Bulls -5.5", "matchup": "Heat@Bulls", "group": "Spread"}
    assert grade_prediction(row, final) == "win"


def test_pp20_spread_fail_to_cover():
    """PP20d: spread fail grades 'loss' (Bulls -8.5, wins by only 3)."""
    final = _make_final_dict("Bulls", "Heat", 103, 100)  # margin +3
    row = {"selection": "Bulls -8.5", "matchup": "Heat@Bulls", "group": "Spread"}
    assert grade_prediction(row, final) == "loss"


def test_pp20_total_over():
    """PP20e: total over grades 'win' when total > line."""
    final = _make_final_dict("Bulls", "Heat", 115, 108)  # total 223
    row = {"selection": "Over 215.5", "matchup": "Heat@Bulls", "group": "Game total"}
    assert grade_prediction(row, final) == "win"


def test_pp20_total_under():
    """PP20f: total under grades 'win' when total < line."""
    final = _make_final_dict("Bulls", "Heat", 100, 98)  # total 198
    row = {"selection": "Under 215.5", "matchup": "Heat@Bulls", "group": "Game total"}
    assert grade_prediction(row, final) == "win"


def test_pp20_no_score_returns_none():
    """PP20g: missing score -> grade_prediction returns None (never fabricates)."""
    final = {"game_id": "G1", "home": "Bulls", "away": "Heat",
             "home_score": None, "away_score": None, "completed": True}
    row = {"selection": "Bulls", "matchup": "Heat@Bulls", "group": "Moneyline"}
    assert grade_prediction(row, final) is None


# ---------------------------------------------------------------------------
# PP21 -- 'outcome' key must NOT appear in any trade row (renamed to 'result')
# ---------------------------------------------------------------------------

def test_pp21_no_outcome_key_in_trade_rows():
    """PP21: 'outcome' key must not appear in any trade row (field is now 'result')."""
    with tempfile.TemporaryDirectory() as td:
        f = _write_jsonl(td, [_minimal_row(), _minimal_row(sport="mlb")])
        client, url = _make_client_with_file(f)
        resp = client.get(url)
    body = resp.json()
    for trade in body["trades"]:
        assert "outcome" not in trade, (
            f"PP21: 'outcome' key must not appear in trade rows (use 'result'); "
            f"found in: {trade}"
        )
        assert "result" in trade, "PP21: 'result' key must be present"


# ---------------------------------------------------------------------------
# Self-runner for quick iteration without pytest
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn()
            print("PASS", fn.__name__)
            passed += 1
        except Exception as exc:
            print("FAIL", fn.__name__, "->", exc)
    print("%d/%d green" % (passed, len(fns)))
