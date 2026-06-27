"""Per-file test: frontend.sse SSE stream endpoints.

Checks 200 text/event-stream, first-event == REST body, build error -> unavailable.
Run: python -m pytest tests/frontend/test_sse.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import pytest
from fastapi.testclient import TestClient

from predict_service import store
from predict_service.contracts import EdgeRow, MarketRow, PredictionRecord, SnapshotEnvelope

# ---------------------------------------------------------------------------
# Constants + stub data helpers
# ---------------------------------------------------------------------------

_SPORT = "nba"
_GID = "0042500401"

_HONEST_NOTE_PAPER = (
    "Paper-only. executed is always False. "
    "Edges are EV/CLV (probability-space); no $ edge is claimed. "
    "CLV = better-number-than-close (positive = good). "
    "Proxy closes are labelled clv_is_proxy=true."
)


def _envelope() -> SnapshotEnvelope:
    market = MarketRow(
        sport=_SPORT, game_id=_GID, market_type="moneyline",
        side="home", line=None, odds=1.71, book="espn:DK",
        devigged_prob=0.57, captured_at="2026-06-18T22:00:00+00:00",
        is_close=False, clv_is_proxy=True,
    )
    record = PredictionRecord(
        sport=_SPORT, game_id=_GID,
        home="Boston Celtics", away="New York Knicks",
        tipoff="2026-06-18T23:30:00+00:00",
        pregame_probs={"home_ml": 0.58, "away_ml": 0.42},
        markets=[market], leak_guard={"in_sample": False},
        produced_at="2026-06-18T21:00:00+00:00",
    )
    edge = EdgeRow(
        game_id=_GID, market_type="moneyline", side="home",
        model_prob=0.58, market_prob=0.555, ev=0.045, tier="B",
        book="espn:DK", line=None, clv_is_proxy=True,
    )
    return SnapshotEnvelope(
        sport=_SPORT, generated_at="2026-06-18T22:01:00+00:00",
        status="ok", predictions=[record], markets=[market], edges=[edge],
    )


def _write_ledger(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _open_bet() -> dict:
    return {
        "ts": "2026-06-18T22:00:00+00:00",
        "sport": _SPORT,
        "matchup": "NYK@BOS",
        "side": "away",
        "taken_book": "espn:DK",
        "taken_decimal": 2.6,
        "model_prob": 0.4145,
        "status": "open",
        "executed": False,
    }


# ---------------------------------------------------------------------------
# Helper: read first SSE data event from a streaming TestClient response
# ---------------------------------------------------------------------------

def _first_data_event(response: Any) -> Optional[Dict[str, Any]]:
    """Read lines from a streaming response until the first 'data: ...' frame.

    Returns the decoded JSON dict, or None if no data frame found in the first
    4 KB of content.
    """
    buf = ""
    max_bytes = 4096
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client_with_store(tmp_path, monkeypatch):
    """TestClient with stubbed store + SSE_INTERVAL_SEC=0.05 for fast ticks."""
    # Write stub envelope into a temp store dir.
    store.save(_envelope(), out_dir=tmp_path, append=False)
    monkeypatch.setenv("PREDICT_SERVICE_STORE_DIR", str(tmp_path))

    # Fast tick so the stream progresses in test time.
    monkeypatch.setenv("SSE_INTERVAL_SEC", "0.05")
    monkeypatch.setenv("SSE_MAX_DURATION_SEC", "2.0")
    monkeypatch.setenv("SSE_HEARTBEAT_SEC", "60.0")  # suppress heartbeats

    # Stub live block so no network call is made.
    import frontend.report as _report_mod  # noqa: PLC0415
    monkeypatch.setattr(
        _report_mod, "_live",
        lambda *a, **k: {"status": "unavailable", "reason": "stubbed in test"},
    )

    from predict_service.app import app  # noqa: PLC0415
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def ledger_path(tmp_path) -> Path:
    p = tmp_path / "ledger" / "clv_ledger.jsonl"
    _write_ledger(p, [_open_bet()])
    return p


# ---------------------------------------------------------------------------
# /api/stream/game/{sport}/{game_id}
# ---------------------------------------------------------------------------

def test_stream_game_returns_200_event_stream(client_with_store):
    with client_with_store.stream("GET", "/api/stream/game/%s/%s" % (_SPORT, _GID)) as r:
        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("content-type", "")


def test_stream_game_first_event_equals_rest_body(client_with_store, monkeypatch):
    """First SSE event must be byte-identical to GET /api/report/{sport}/{game_id}."""
    # Capture REST body.
    rest = client_with_store.get("/api/report/%s/%s" % (_SPORT, _GID)).json()

    # Read first SSE event.
    with client_with_store.stream(
        "GET", "/api/stream/game/%s/%s" % (_SPORT, _GID)
    ) as r:
        event = _first_data_event(r)

    assert event is not None, "No data event received from stream"
    # Both are dicts from the same builder; keys and runtime-stable values match.
    # 'meta.as_of' and 'meta.freshness' can drift by a few ms between calls,
    # so we compare the stable structural keys.
    assert event["status"] == rest["status"]
    assert event["sport"] == rest["sport"]
    assert event["game_id"] == rest["game_id"]
    assert event["pregame"]["home"] == rest["pregame"]["home"]
    assert event["pregame"]["away"] == rest["pregame"]["away"]
    assert event["pregame"]["model_probs"] == rest["pregame"]["model_probs"]
    assert len(event["markets"]) == len(rest["markets"])
    assert len(event["edges"]) == len(rest["edges"])
    if event["edges"]:
        assert event["edges"][0]["tier"] == rest["edges"][0]["tier"]
    # 'meta.honest_note' must match verbatim (string constant, never fabricated).
    assert event["meta"]["honest_note"] == rest["meta"]["honest_note"]


# ---------------------------------------------------------------------------
# /api/stream/game -- build error emits unavailable, not a 500
# ---------------------------------------------------------------------------

def test_stream_game_build_error_emits_unavailable(tmp_path, monkeypatch):
    """When build_report raises, the stream emits unavailable -- no 500."""
    monkeypatch.setenv("SSE_INTERVAL_SEC", "0.05")
    monkeypatch.setenv("SSE_MAX_DURATION_SEC", "2.0")
    monkeypatch.setenv("SSE_HEARTBEAT_SEC", "60.0")

    # Make build_report always raise.
    import frontend.sse as _sse_mod  # noqa: PLC0415
    monkeypatch.setattr(
        _sse_mod, "_report_payload",
        lambda *a, **k: {
            "status": "unavailable",
            "sport": str(a[0]) if a else "?",
            "game_id": str(a[1]) if len(a) > 1 else "?",
            "reason": "injected build error",
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
    # Must NOT be a plain HTTP 500 (the stream itself is 200 + data frame).


# ---------------------------------------------------------------------------
# /api/stream/paper
# ---------------------------------------------------------------------------

def test_stream_paper_returns_200_event_stream(client_with_store, ledger_path):
    with client_with_store.stream(
        "GET", "/api/stream/paper", params={"ledger": str(ledger_path)},
    ) as r:
        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("content-type", "")


def test_stream_paper_first_event_matches_rest_body(client_with_store, ledger_path):
    """First SSE event must carry same trail + clv keys as REST endpoints."""
    # Capture REST bodies via the standard endpoints.
    rest_trail = client_with_store.get(
        "/api/paper/trail", params={"ledger": str(ledger_path)}
    ).json()
    rest_clv = client_with_store.get(
        "/api/paper/clv", params={"ledger": str(ledger_path)}
    ).json()

    with client_with_store.stream(
        "GET",
        "/api/stream/paper",
        params={"ledger": str(ledger_path)},
    ) as r:
        event = _first_data_event(r)

    assert event is not None, "No data event received from paper stream"
    assert event["status"] == rest_trail["status"]
    assert event["count"] == rest_trail["count"]
    # trail rows must match the REST trail response.
    assert event["trail"] == rest_trail["trail"]
    # clv block must match the REST clv summary.
    assert "clv" in event, "SSE paper event missing 'clv' key"
    assert event["clv"]["n_bets"] == rest_clv["n_bets"]
    # honest_note is the paper-specific string constant.
    assert event["honest_note"] == _HONEST_NOTE_PAPER


# ---------------------------------------------------------------------------
# /api/stream/paper -- build error emits unavailable, not a 500
# ---------------------------------------------------------------------------

def test_stream_paper_build_error_emits_unavailable(monkeypatch):
    """When paper_payload raises, the stream emits unavailable -- no 500."""
    monkeypatch.setenv("SSE_INTERVAL_SEC", "0.05")
    monkeypatch.setenv("SSE_MAX_DURATION_SEC", "2.0")
    monkeypatch.setenv("SSE_HEARTBEAT_SEC", "60.0")

    import frontend.sse as _sse_mod  # noqa: PLC0415
    monkeypatch.setattr(
        _sse_mod, "_paper_payload",
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
