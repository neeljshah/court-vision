"""tests/test_live_v2_app.py — FastAPI WebSocket bridge regression set."""
from __future__ import annotations

import csv
import json
import os
import tempfile

import pytest


@pytest.fixture(autouse=True)
def _no_orchestrator(monkeypatch):
    # Force the app to start in passive mode (no real polling).
    monkeypatch.delenv("LIVE_V2_GAME_IDS", raising=False)
    # Reset module-level caches before each test.
    import api.live_v2_app as app_mod
    app_mod._latest_snapshot.clear()
    app_mod._latest_projections.clear()
    app_mod._recent_bets.clear()
    app_mod._recent_alerts.clear()
    from src.live.event_bus import reset_bus_for_tests
    reset_bus_for_tests()
    yield


def test_health_endpoint_open_no_token():
    from fastapi.testclient import TestClient
    from api.live_v2_app import app

    with TestClient(app) as client:
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert "ws_clients" in body


def test_state_endpoint_returns_empty_when_passive():
    from fastapi.testclient import TestClient
    from api.live_v2_app import app

    with TestClient(app) as client:
        r = client.get("/api/state")
        assert r.status_code == 200
        body = r.json()
        assert body["snapshots"] == {}
        assert body["recent_bets"] == []


def test_state_endpoint_requires_token_when_configured(monkeypatch):
    monkeypatch.setenv("LIVE_V2_AUTH_TOKEN", "secret123")
    from fastapi.testclient import TestClient
    from api.live_v2_app import app

    with TestClient(app) as client:
        r = client.get("/api/state")
        assert r.status_code == 401
        r2 = client.get("/api/state?token=secret123")
        assert r2.status_code == 200


def test_explain_endpoint_returns_sections(monkeypatch):
    from fastapi.testclient import TestClient
    import api.live_v2_app as app_mod

    app_mod._latest_snapshot["g"] = {
        "game_id": "g", "period": 4, "clock": "PT05M30S",
        "players": [{"player_id": 1, "name": "Jokic", "pf": 4, "min": 30}],
    }
    app_mod._latest_projections["g"] = [{
        "player_id": 1, "stat": "pts",
        "projection_source": "endQ2_head+residual_head_endq2",
        "foul_factor": 0.95,
    }]

    with TestClient(app_mod.app) as client:
        r = client.post("/api/explain", json={"bet": {
            "game_id": "g", "player_id": 1, "name": "Jokic",
            "stat": "pts", "side": "over", "line": 24.5,
            "book": "pin", "odds": -110, "ev": 0.07, "kelly": 0.12,
            "projected_final": 32.0,
        }})
        assert r.status_code == 200
        body = r.json()
        kinds = [s["kind"] for s in body["sections"]]
        assert "projection_path" in kinds
        assert "foul_pressure" in kinds


def test_websocket_hello_payload_on_connect():
    """Verify the WS handshake delivers the hello hydration payload."""
    from fastapi.testclient import TestClient
    from api.live_v2_app import app
    import api.live_v2_app as app_mod

    # Seed some state so the hello payload is non-empty.
    app_mod._latest_snapshot["g"] = {"game_id": "g", "period": 4}
    app_mod._recent_bets.insert(0, {"name": "Jokic", "ev": 0.07})

    with TestClient(app) as client:
        with client.websocket_connect("/ws/live") as ws:
            hello = ws.receive_json()
            assert hello["topic"] == "hello"
            assert "snapshots" in hello["event"]
            assert hello["event"]["snapshots"]["g"]["period"] == 4
            assert hello["event"]["recent_bets"][0]["name"] == "Jokic"


def test_websocket_rejects_invalid_token(monkeypatch):
    monkeypatch.setenv("LIVE_V2_AUTH_TOKEN", "right")
    from fastapi.testclient import TestClient
    from api.live_v2_app import app
    from starlette.websockets import WebSocketDisconnect

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/live?token=wrong") as ws:
                ws.receive_json()


def test_refresh_pregame_bets_evicts_stale_pregame_picks():
    """When a previously-published pregame bet falls off the new scan (line
    moved below EV floor), it must disappear from _recent_bets. In-play
    bets (source != "pregame_ev") must survive the eviction."""
    import asyncio
    import api.live_v2_app as app_mod

    # Seed: one stale pregame bet that the new scan WON'T return, plus one
    # in-play bet from the decision engine that must be preserved.
    app_mod._recent_bets[:] = [
        {"player_id": "ghost", "stat": "pts", "side": "over", "line": 10.5,
         "book": "fd", "ev": 0.20, "source": "pregame_ev", "name": "Ghost"},
        {"player_id": "live1", "stat": "ast", "side": "over", "line": 7.5,
         "book": "bov", "ev": 0.15, "source": "in_play_decision",
         "name": "Live Player"},
    ]

    # Stub rank_pregame_bets to return ONE fresh pregame bet (different prop).
    fresh_pick = {"player_id": "fresh", "stat": "reb", "side": "over",
                  "line": 8.5, "book": "fd", "ev": 0.08,
                  "source": "pregame_ev", "name": "Fresh"}
    import src.live.pregame_ev_engine as pe_mod
    orig = pe_mod.rank_pregame_bets
    pe_mod.rank_pregame_bets = lambda: [fresh_pick]
    app_mod._rank_pregame_bets = pe_mod.rank_pregame_bets
    try:
        from src.live.event_bus import get_bus
        bus = get_bus()
        bus.subscribe("*", app_mod._on_any_event)
        asyncio.run(app_mod._refresh_pregame_bets("test", {}))
    finally:
        pe_mod.rank_pregame_bets = orig
        app_mod._rank_pregame_bets = orig

    keys = {b.get("player_id") for b in app_mod._recent_bets}
    assert "ghost" not in keys, \
        "stale pregame bet should have been evicted"
    assert "live1" in keys, \
        "in-play decision-engine bet must survive eviction"
    assert "fresh" in keys, \
        "newly-ranked pregame bet must be present after refresh"


def test_shadow_endpoint_empty_when_no_data(monkeypatch, tmp_path):
    """/api/shadow returns 200 with empty list when no shadow CSVs exist."""
    from fastapi.testclient import TestClient
    import api.live_v2_app as app_mod

    # Point shadow reader at an empty temp dir.
    monkeypatch.setattr(app_mod, "_shadow_cache", {})
    monkeypatch.setenv("LIVE_V2_AUTH_TOKEN", "tok")

    orig_fn = app_mod._read_shadow_bets_today

    def _empty():
        return []

    monkeypatch.setattr(app_mod, "_read_shadow_bets_today", _empty)

    with TestClient(app_mod.app) as client:
        r = client.get("/api/shadow?token=tok")
        assert r.status_code == 200
        body = r.json()
        assert "shadow_bets" in body
        assert body["shadow_bets"] == []

    monkeypatch.setattr(app_mod, "_read_shadow_bets_today", orig_fn)


def test_shadow_endpoint_filters_blocked_and_sorts_by_ev(monkeypatch, tmp_path):
    """/api/shadow returns only blocked rows, sorted by raw_ev DESC."""
    from fastapi.testclient import TestClient
    import api.live_v2_app as app_mod

    # Build fake shadow rows with mixed gate_status values.
    rows = [
        {"ts": "t1", "game_id": "g1", "player_id": "1", "name": "Alpha",
         "team": "LAL", "stat": "pts", "side": "over", "line": 25.5,
         "book": "fd", "odds": -110, "model_proj": 28.0, "current_stat": 0.0,
         "raw_ev": 0.05, "kelly": 0.02, "tier": "B",
         "gate_blocked_by": "three_book_consensus", "source": "in_play_decision",
         "gate_status": "blocked"},
        {"ts": "t2", "game_id": "g1", "player_id": "2", "name": "Beta",
         "team": "BOS", "stat": "reb", "side": "under", "line": 8.5,
         "book": "pin", "odds": -120, "model_proj": 7.0, "current_stat": 0.0,
         "raw_ev": 0.09, "kelly": 0.04, "tier": "A",
         "gate_blocked_by": "projection_sane", "source": "in_play_decision",
         "gate_status": "blocked"},
        {"ts": "t3", "game_id": "g1", "player_id": "3", "name": "Gamma",
         "team": "GSW", "stat": "ast", "side": "over", "line": 6.5,
         "book": "bov", "odds": -105, "model_proj": 7.5, "current_stat": 0.0,
         "raw_ev": 0.03, "kelly": 0.01, "tier": "C",
         "gate_blocked_by": "", "source": "in_play_decision",
         "gate_status": "passed"},  # must NOT appear in shadow results
    ]

    monkeypatch.setattr(app_mod, "_shadow_cache", {})

    def _fake_read():
        return [r for r in rows if r.get("gate_status") == "blocked"]

    monkeypatch.setattr(app_mod, "_read_shadow_bets_today", _fake_read)

    with TestClient(app_mod.app) as client:
        r = client.get("/api/shadow")
        assert r.status_code == 200
        body = r.json()
        bets = body["shadow_bets"]
        # Only blocked rows returned.
        assert len(bets) == 2
        names = [b["name"] for b in bets]
        assert "Gamma" not in names, "passed row must be excluded"
        # Sorted by raw_ev desc: Beta (0.09) before Alpha (0.05).
        assert bets[0]["name"] == "Beta"
        assert bets[1]["name"] == "Alpha"


def test_shadow_endpoint_requires_token(monkeypatch):
    """/api/shadow enforces the same auth as /api/bets."""
    monkeypatch.setenv("LIVE_V2_AUTH_TOKEN", "mytoken")
    from fastapi.testclient import TestClient
    import api.live_v2_app as app_mod

    with TestClient(app_mod.app) as client:
        r_unauth = client.get("/api/shadow")
        assert r_unauth.status_code == 401

        r_wrong = client.get("/api/shadow?token=wrong")
        assert r_wrong.status_code == 401

        r_ok = client.get("/api/shadow?token=mytoken")
        assert r_ok.status_code == 200
        assert "shadow_bets" in r_ok.json()


def test_recent_bets_dedup_and_sort_by_ev_desc():
    """Re-publishing the same prop must not accumulate duplicates, and the
    list must stay sorted by EV descending so /api/bets surfaces the best
    pick first."""
    import asyncio
    import api.live_v2_app as app_mod
    from src.live.event_bus import TOPIC_BET_RECOMMENDED, get_bus

    async def _run():
        bus = get_bus()
        bus.subscribe("*", app_mod._on_any_event)
        # Same prop, three different EVs over time (simulating repeated scans).
        for ev in (0.03, 0.05, 0.04):
            await bus.publish(TOPIC_BET_RECOMMENDED, {
                "player_id": "1", "stat": "pts", "side": "over",
                "line": 24.5, "book": "fd", "ev": ev, "name": "X",
            })
        # A different prop with the highest EV — should land at index 0.
        await bus.publish(TOPIC_BET_RECOMMENDED, {
            "player_id": "2", "stat": "reb", "side": "over",
            "line": 8.5, "book": "bov", "ev": 0.10, "name": "Y",
        })
        # A different prop with the lowest EV — should land at the bottom.
        await bus.publish(TOPIC_BET_RECOMMENDED, {
            "player_id": "3", "stat": "ast", "side": "under",
            "line": 4.5, "book": "fd", "ev": 0.01, "name": "Z",
        })

    asyncio.run(_run())

    bets = app_mod._recent_bets
    assert len(bets) == 3, f"expected 3 distinct props, got {len(bets)}: {bets}"
    # Sorted by EV desc.
    assert bets[0]["name"] == "Y" and bets[0]["ev"] == 0.10
    assert bets[1]["name"] == "X" and bets[1]["ev"] == 0.04, \
        "latest publish of prop X (ev=0.04) should win the dedup"
    assert bets[2]["name"] == "Z" and bets[2]["ev"] == 0.01
