"""Per-file test: SSE stream event JSON shape matches what useEventStream / components consume.

Validates that:
  1. /api/stream/game SSE event payload == /api/report REST shape (ReportData)
  2. /api/stream/paper SSE event payload has all keys useEventStream / PaperTrailPanel consumes
  3. No forbidden $ / roi / pnl key appears in either stream payload (HONESTY)
  4. 'clv' block in the paper payload matches the ClvData shape (ClvSummaryStrip)
  5. 'trail' rows in the paper payload match the TrailRow shape (PaperBetRow)
  6. Error-sentinel events carry only safe keys ('status', 'reason', ...)

These are the SAME shapes the TypeScript hook and components parse at runtime.
Any drift here breaks the live-update UI.

Run: python -m pytest tests/frontend/test_sse_ui_contract.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import pytest
from fastapi.testclient import TestClient

from predict_service import store
from predict_service.contracts import (
    EdgeRow,
    MarketRow,
    PredictionRecord,
    SnapshotEnvelope,
)
import frontend.report as _report_mod

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SPORT = "nba"
_GID = "0042500402"

# Keys the TypeScript ReportData interface reads (GameReport.tsx).
_REPORT_OK_KEYS = {
    "status", "sport", "game_id",
    "pregame", "markets", "edges", "live", "intel", "meta",
}

# Keys the TypeScript PaperStreamPayload reads (PaperTrailPanel.tsx).
# Merges /api/paper/trail body + 'clv' key from /api/paper/clv.
_PAPER_STREAM_KEYS = {
    "status", "count", "trail", "honest_note", "clv",
}

# Keys the TypeScript ClvData interface reads (ClvSummaryStrip.tsx).
_CLV_KEYS = {"n_bets", "note"}

# Required keys per TrailRow (PaperBetRow.tsx).
_TRAIL_ROW_KEYS = {
    "game_id", "matchup", "sport", "side",
    "taken_book", "taken_decimal",
    "model_prob", "model_ev",
    "tier", "status", "graded",
    "outcome", "clv_pct", "beat_close",
    "clv_is_proxy", "clv_note",
    "executed", "ts", "settled_at",
}

# Keys forbidden everywhere (HONESTY -- no $ / roi / profit claims).
_FORBIDDEN = ("$", "dollar", "roi", "pnl", "profit", "stake", "bankroll")

# The honest_note the SSE paper payload always carries (from frontend/sse.py).
_PAPER_HONEST_NOTE = (
    "Paper-only. executed is always False. "
    "Edges are EV/CLV (probability-space); no $ edge is claimed. "
    "CLV = better-number-than-close (positive = good). "
    "Proxy closes are labelled clv_is_proxy=true."
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _envelope() -> SnapshotEnvelope:
    market = MarketRow(
        sport=_SPORT, game_id=_GID, market_type="moneyline",
        side="home", line=None, odds=1.65, book="espn:DK",
        devigged_prob=0.60, captured_at="2026-06-18T21:00:00+00:00",
        is_close=False, clv_is_proxy=False,
    )
    record = PredictionRecord(
        sport=_SPORT, game_id=_GID,
        home="Indiana Pacers", away="Oklahoma City Thunder",
        tipoff="2026-06-18T23:30:00+00:00",
        pregame_probs={"home_ml": 0.42, "away_ml": 0.58},
        markets=[market], leak_guard={"in_sample": False},
        produced_at="2026-06-18T20:00:00+00:00",
    )
    edge = EdgeRow(
        game_id=_GID, market_type="moneyline", side="away",
        model_prob=0.58, market_prob=0.57, ev=0.012, tier="C",
        book="espn:DK", line=None, clv_is_proxy=False,
    )
    return SnapshotEnvelope(
        sport=_SPORT, generated_at="2026-06-18T21:05:00+00:00",
        status="ok", predictions=[record], markets=[market], edges=[edge],
    )


def _write_ledger(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _open_bet() -> dict:
    return {
        "ts": "2026-06-18T20:00:00+00:00",
        "sport": _SPORT,
        "matchup": "OKC@IND",
        "side": "away",
        "taken_book": "espn:DK",
        "taken_decimal": 2.2,
        "model_prob": 0.58,
        "status": "open",
        "executed": False,
    }


def _first_data_event(response: Any) -> Optional[Dict[str, Any]]:
    """Extract the first 'data: ...' SSE frame from a streaming TestClient response."""
    buf = ""
    max_bytes = 8192
    read = 0
    for chunk in response.iter_text():
        buf += chunk
        read += len(chunk)
        for line in buf.splitlines(keepends=True):
            stripped = line.strip()
            if stripped.startswith("data:"):
                json_str = stripped[len("data:"):].strip()
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    return None
        if read >= max_bytes:
            break
    return None


def _assert_no_money(obj: Any, path: str = "root") -> None:
    """Recursively assert no forbidden key name ($ / roi / pnl / ...) appears."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            for bad in _FORBIDDEN:
                assert bad not in kl, (
                    "Forbidden key %r at path %r -- no $ keys in stream payload"
                    % (k, path)
                )
            _assert_no_money(v, path="%s.%s" % (path, k))
    elif isinstance(obj, list):
        for i, it in enumerate(obj):
            _assert_no_money(it, path="%s[%d]" % (path, i))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Full app TestClient with stub store, no network, fast SSE ticks."""
    store.save(_envelope(), out_dir=tmp_path, append=False)
    monkeypatch.setenv("PREDICT_SERVICE_STORE_DIR", str(tmp_path))
    monkeypatch.setenv("SSE_INTERVAL_SEC", "0.05")
    monkeypatch.setenv("SSE_MAX_DURATION_SEC", "2.0")
    monkeypatch.setenv("SSE_HEARTBEAT_SEC", "60.0")
    monkeypatch.setattr(
        _report_mod, "_live",
        lambda *a, **k: {"status": "unavailable", "reason": "stubbed"},
    )
    from predict_service.app import app  # noqa: PLC0415
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def ledger_path(tmp_path) -> Path:
    p = tmp_path / "led" / "clv_ledger.jsonl"
    _write_ledger(p, [_open_bet()])
    return p


# ---------------------------------------------------------------------------
# 1. /api/stream/game SSE event shape == ReportData (GameReport.tsx)
# ---------------------------------------------------------------------------


def test_game_stream_event_has_report_ok_keys(client):
    """SSE game event must carry all keys GameReport.ReportData reads."""
    with client.stream("GET", "/api/stream/game/%s/%s" % (_SPORT, _GID)) as r:
        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("content-type", "")
        event = _first_data_event(r)

    assert event is not None, "No SSE data event received"
    missing = _REPORT_OK_KEYS - set(event.keys())
    assert not missing, "SSE game event missing keys: %s" % sorted(missing)
    assert event["status"] == "ok"
    assert event["sport"] == _SPORT
    assert event["game_id"] == _GID


def test_game_stream_event_matches_rest_shape(client):
    """SSE game event stable fields == REST /api/report response stable fields."""
    rest = client.get("/api/report/%s/%s" % (_SPORT, _GID)).json()
    with client.stream("GET", "/api/stream/game/%s/%s" % (_SPORT, _GID)) as r:
        event = _first_data_event(r)

    assert event is not None
    # Structural parity (as_of / freshness can drift by milliseconds).
    assert event["status"] == rest["status"]
    assert event["sport"] == rest["sport"]
    assert event["game_id"] == rest["game_id"]
    assert event["pregame"]["home"] == rest["pregame"]["home"]
    assert event["pregame"]["away"] == rest["pregame"]["away"]
    assert event["pregame"]["model_probs"] == rest["pregame"]["model_probs"]
    assert len(event["markets"]) == len(rest["markets"])
    assert len(event["edges"]) == len(rest["edges"])
    assert event["meta"]["honest_note"] == rest["meta"]["honest_note"]
    assert event["meta"]["schema_version"] == rest["meta"]["schema_version"]


def test_game_stream_event_no_forbidden_keys(client):
    """HONESTY: SSE game event must carry no $ / roi / pnl key anywhere."""
    with client.stream("GET", "/api/stream/game/%s/%s" % (_SPORT, _GID)) as r:
        event = _first_data_event(r)
    assert event is not None
    _assert_no_money(event)


def test_game_stream_pregame_shape(client):
    """pregame block must expose home, away, tipoff, model_probs, leak_guard."""
    with client.stream("GET", "/api/stream/game/%s/%s" % (_SPORT, _GID)) as r:
        event = _first_data_event(r)
    pre = event["pregame"]
    for key in ("home", "away", "tipoff", "model_probs", "leak_guard", "produced_at"):
        assert key in pre, "pregame missing key %r" % key
    assert isinstance(pre["model_probs"], dict)
    assert isinstance(pre["leak_guard"], dict)
    assert "in_sample" in pre["leak_guard"]


def test_game_stream_edges_shape(client):
    """Each edge row must expose all EdgeRow keys the component reads."""
    _EDGE_KEYS = {
        "game_id", "market_type", "side",
        "model_prob", "market_prob", "ev", "tier",
        "book", "line", "clv_is_proxy",
    }
    with client.stream("GET", "/api/stream/game/%s/%s" % (_SPORT, _GID)) as r:
        event = _first_data_event(r)
    for e in event.get("edges", []):
        missing = _EDGE_KEYS - set(e.keys())
        assert not missing, "EdgeRow missing keys: %s" % sorted(missing)
        assert isinstance(e["clv_is_proxy"], bool)


def test_game_stream_error_sentinel_is_safe(monkeypatch):
    """When build_report fails, SSE emits safe unavailable dict -- no 500."""
    monkeypatch.setenv("SSE_INTERVAL_SEC", "0.05")
    monkeypatch.setenv("SSE_MAX_DURATION_SEC", "2.0")
    monkeypatch.setenv("SSE_HEARTBEAT_SEC", "60.0")
    import frontend.sse as _sse  # noqa: PLC0415
    monkeypatch.setattr(
        _sse, "_report_payload",
        lambda s, g: {
            "status": "unavailable",
            "sport": str(s),
            "game_id": str(g),
            "reason": "injected error",
        },
    )
    from predict_service.app import app  # noqa: PLC0415
    c = TestClient(app, raise_server_exceptions=False)
    with c.stream("GET", "/api/stream/game/%s/%s" % (_SPORT, _GID)) as r:
        assert r.status_code == 200
        event = _first_data_event(r)
    assert event is not None
    assert event["status"] == "unavailable"
    assert "reason" in event
    # Error sentinel must also carry no forbidden keys.
    _assert_no_money(event)


# ---------------------------------------------------------------------------
# 2. /api/stream/paper SSE event shape (PaperTrailPanel.tsx / PaperStreamPayload)
# ---------------------------------------------------------------------------


def test_paper_stream_event_has_required_keys(client, ledger_path):
    """SSE paper event must carry all keys PaperStreamPayload reads."""
    with client.stream(
        "GET", "/api/stream/paper", params={"ledger": str(ledger_path)}
    ) as r:
        assert r.status_code == 200
        event = _first_data_event(r)

    assert event is not None, "No SSE data event received from paper stream"
    missing = _PAPER_STREAM_KEYS - set(event.keys())
    assert not missing, "SSE paper event missing keys: %s" % sorted(missing)
    assert event["status"] == "ok"
    assert isinstance(event["count"], int)
    assert isinstance(event["trail"], list)
    assert event["honest_note"] == _PAPER_HONEST_NOTE
    assert isinstance(event["clv"], dict)


def test_paper_stream_event_matches_rest_trail(client, ledger_path):
    """SSE paper event trail must match /api/paper/trail REST response."""
    rest_trail = client.get(
        "/api/paper/trail", params={"ledger": str(ledger_path)}
    ).json()
    with client.stream(
        "GET", "/api/stream/paper", params={"ledger": str(ledger_path)}
    ) as r:
        event = _first_data_event(r)

    assert event is not None
    assert event["count"] == rest_trail["count"]
    assert event["trail"] == rest_trail["trail"]


def test_paper_stream_clv_block_matches_rest_clv(client, ledger_path):
    """SSE paper event 'clv' block must match /api/paper/clv REST response."""
    rest_clv = client.get(
        "/api/paper/clv", params={"ledger": str(ledger_path)}
    ).json()
    with client.stream(
        "GET", "/api/stream/paper", params={"ledger": str(ledger_path)}
    ) as r:
        event = _first_data_event(r)

    assert event is not None
    clv = event["clv"]
    assert isinstance(clv, dict), "clv block must be a dict"
    missing = _CLV_KEYS - set(clv.keys())
    assert not missing, "clv block missing keys: %s" % sorted(missing)
    assert clv["n_bets"] == rest_clv["n_bets"]


def test_paper_stream_trail_row_shape(client, ledger_path):
    """Each trail row must expose all keys PaperBetRow.TrailRow reads."""
    with client.stream(
        "GET", "/api/stream/paper", params={"ledger": str(ledger_path)}
    ) as r:
        event = _first_data_event(r)

    assert event is not None
    for row in event.get("trail", []):
        missing = _TRAIL_ROW_KEYS - set(row.keys())
        assert not missing, "TrailRow missing keys: %s" % sorted(missing)
        # executed INVARIANT: paper-only, always False.
        assert row["executed"] is False, (
            "TrailRow.executed must always be False (paper-only invariant)"
        )


def test_paper_stream_no_forbidden_keys(client, ledger_path):
    """HONESTY: SSE paper event must carry no $ / roi / pnl key anywhere."""
    with client.stream(
        "GET", "/api/stream/paper", params={"ledger": str(ledger_path)}
    ) as r:
        event = _first_data_event(r)
    assert event is not None
    _assert_no_money(event)


def test_paper_stream_error_sentinel_is_safe(monkeypatch):
    """When paper_payload fails, SSE emits safe unavailable dict -- no 500."""
    monkeypatch.setenv("SSE_INTERVAL_SEC", "0.05")
    monkeypatch.setenv("SSE_MAX_DURATION_SEC", "2.0")
    monkeypatch.setenv("SSE_HEARTBEAT_SEC", "60.0")
    import frontend.sse as _sse  # noqa: PLC0415
    monkeypatch.setattr(
        _sse, "_paper_payload",
        lambda *a, **k: {
            "status": "unavailable",
            "reason": "injected paper error",
            "trail": [],
            "count": 0,
        },
    )
    from predict_service.app import app  # noqa: PLC0415
    c = TestClient(app, raise_server_exceptions=False)
    with c.stream("GET", "/api/stream/paper") as r:
        assert r.status_code == 200
        event = _first_data_event(r)
    assert event is not None
    assert event["status"] == "unavailable"
    assert "reason" in event
    _assert_no_money(event)


# ---------------------------------------------------------------------------
# 3. Parity: stream events == REST bodies (no extra / missing fields)
# ---------------------------------------------------------------------------


def test_game_stream_no_extra_top_level_keys(client):
    """SSE game event must not add any key that the REST endpoint does not have."""
    rest = client.get("/api/report/%s/%s" % (_SPORT, _GID)).json()
    with client.stream("GET", "/api/stream/game/%s/%s" % (_SPORT, _GID)) as r:
        event = _first_data_event(r)
    assert event is not None
    extra = set(event.keys()) - set(rest.keys())
    assert not extra, (
        "SSE game event has extra keys vs REST body: %s -- payloads must be identical"
        % sorted(extra)
    )


def test_paper_stream_clv_no_forbidden_keys(client, ledger_path):
    """HONESTY: clv block inside paper SSE event must not carry $ keys."""
    with client.stream(
        "GET", "/api/stream/paper", params={"ledger": str(ledger_path)}
    ) as r:
        event = _first_data_event(r)
    assert event is not None
    clv = event.get("clv", {})
    _assert_no_money(clv, path="clv")
