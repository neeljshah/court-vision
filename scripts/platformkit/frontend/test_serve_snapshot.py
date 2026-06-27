"""Per-file tests for serve.py's prefer-snapshot behavior on /api/slate + /api/live.

Network-free: monkeypatches snapshot_writer.read_snapshot to return canned
envelopes (no disk, no compute). Verifies that an ok-envelope is served straight
from the snapshot (served_from=='snapshot' with the canned slate + a freshness
stamp), and that a missing snapshot (read_snapshot -> None) falls back to the
synchronous live compute (served_from=='live_compute', 200, with a status) -- a
cold cache must never dark-screen the board.

Run (per-file ONLY -- full pytest freezes this box):
  cd /c/Users/neelj/nba-ai-system && \
    python -m pytest scripts/platformkit/frontend/test_serve_snapshot.py -q
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from scripts.platformkit.frontend import serve as serve_mod


def _fresh_ts() -> str:
    """A generated_at within the snapshot TTL (so it is served, not aged out)."""
    return datetime.now(tz=timezone.utc).isoformat()


def _ok_envelope(generated_at: str = ""):
    ts = generated_at or _fresh_ts()
    return {
        "sport": "nba",
        "generated_at": ts,
        "status": "ok",
        "slate": {"sport": "nba", "status": "ok",
                  "rows": [{"matchup": "BOS vs LAL", "status": "ok"}],
                  "honest_note": "NO $ edge."},
        "live": {"sport": "nba", "status": "ok",
                 "games": [{"matchup": "BOS vs LAL", "state": "live"}]},
        "props": {"sport": "soccer_intl", "status": "ok",
                  "edges": [{"player": "X", "stat": "shots", "reliable": True}],
                  "unresolved": [], "unresolved_count": 0},
        "freshness": {"as_of": ts, "source": "snapshot"},
        "honest_note": "NO $ edge.",
    }


def _client_with_snapshot(monkeypatch, envelope):
    """Build a TestClient with snapshot_writer.read_snapshot stubbed to *envelope*.

    The canonical predict_service-store slate path (_read_ps_store_slate, tried
    FIRST by /api/slate) is neutralized to None so these tests isolate the
    legacy-snapshot vs live-compute branch deterministically, independent of
    whatever real on-disk store happens to exist on the box.
    """
    assert serve_mod._snapshot_writer is not None, "snapshot_writer must be importable"
    monkeypatch.setattr(serve_mod._snapshot_writer, "read_snapshot",
                        lambda sport, *a, **k: envelope)
    monkeypatch.setattr(serve_mod, "_read_ps_store_slate", lambda sport: None)
    return TestClient(serve_mod.create_app())


def test_slate_served_from_snapshot(monkeypatch):
    env = _ok_envelope()
    client = _client_with_snapshot(monkeypatch, env)
    r = client.get("/api/slate?sport=nba")
    assert r.status_code == 200
    body = r.json()
    assert body["served_from"] == "snapshot"
    # the canned slate rows are returned verbatim
    assert body["rows"] == env["slate"]["rows"]
    assert body["status"] == "ok"
    # a freshness block is stamped from the envelope's generated_at
    assert body["freshness"]["source"] == "snapshot"
    assert body["freshness"]["as_of"] == env["generated_at"]


def test_slate_falls_back_to_live_compute(monkeypatch):
    # read_snapshot -> None (no snapshot): the endpoint must do the live compute.
    client = _client_with_snapshot(monkeypatch, None)
    r = client.get("/api/slate?sport=nba")
    assert r.status_code == 200
    body = r.json()
    assert body["served_from"] == "live_compute"
    # predictor may be unavailable on a fresh clone; either way it degrades, not 500
    assert body["status"] in {"ok", "unavailable", "unknown_sport"}
    assert "honest_note" in body


def test_slate_stale_envelope_falls_back(monkeypatch):
    # An envelope that is NOT ok must be ignored -> live compute fallback.
    env = _ok_envelope()
    env["status"] = "unavailable"
    client = _client_with_snapshot(monkeypatch, env)
    r = client.get("/api/slate?sport=nba")
    assert r.status_code == 200
    assert r.json()["served_from"] == "live_compute"


def test_slate_past_ttl_snapshot_not_served(monkeypatch):
    # STALE-NEVER-GREEN: an ok-envelope whose generated_at is older than the TTL
    # (e.g. yesterday's slate from the un-daemoned snapshot_writer) must NOT be
    # served -- it is a cache miss -> canonical store / live compute fallback.
    old = (datetime.now(tz=timezone.utc)
           - timedelta(seconds=serve_mod._SNAPSHOT_TTL_SECONDS + 3600)).isoformat()
    env = _ok_envelope(generated_at=old)
    client = _client_with_snapshot(monkeypatch, env)
    r = client.get("/api/slate?sport=nba")
    assert r.status_code == 200
    assert r.json()["served_from"] != "snapshot"


def test_snapshot_is_stale_unit():
    # Direct guard checks: fresh -> not stale; old -> stale; missing/bad -> stale.
    now = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
    fresh = (now - timedelta(minutes=10)).isoformat()
    old = (now - timedelta(hours=5)).isoformat()
    assert serve_mod._snapshot_is_stale(fresh, now=now) is False
    assert serve_mod._snapshot_is_stale(old, now=now) is True
    assert serve_mod._snapshot_is_stale("", now=now) is True
    assert serve_mod._snapshot_is_stale("not-a-date", now=now) is True


def test_live_served_from_snapshot(monkeypatch):
    env = _ok_envelope()
    client = _client_with_snapshot(monkeypatch, env)
    r = client.get("/api/live?sport=nba")
    assert r.status_code == 200
    body = r.json()
    assert body["served_from"] == "snapshot"
    assert body["games"] == env["live"]["games"]
    assert body["freshness"]["as_of"] == env["generated_at"]


def test_live_falls_back(monkeypatch):
    client = _client_with_snapshot(monkeypatch, None)
    r = client.get("/api/live?sport=nba")
    assert r.status_code == 200
    body = r.json()
    assert body["served_from"] == "live_compute"
    assert body["status"] in {"ok", "unavailable"}


def test_props_served_from_snapshot(monkeypatch):
    env = _ok_envelope()
    client = _client_with_snapshot(monkeypatch, env)
    r = client.get("/api/props?sport=soccer_intl")
    assert r.status_code == 200
    body = r.json()
    assert body["served_from"] == "snapshot"
    assert body["edges"] == env["props"]["edges"]
    assert body["status"] == "ok"
    assert body["freshness"]["as_of"] == env["generated_at"]


def test_props_falls_back_to_live_compute(monkeypatch):
    # No snapshot -> the endpoint live-computes (or degrades) but is ALWAYS 200 and
    # carries served_from=='live_compute' (never raises, never dark-screens).
    monkeypatch.setattr(
        serve_mod, "_build_prop_board",
        lambda sport, *a, **k: {"sport": sport, "status": "ok",
                                "edges": [{"player": "Y", "reliable": False}]})
    client = _client_with_snapshot(monkeypatch, None)
    r = client.get("/api/props?sport=soccer_intl")
    assert r.status_code == 200
    body = r.json()
    assert body["served_from"] == "live_compute"
    assert body["status"] == "ok"
    assert body["edges"][0]["player"] == "Y"


def test_props_degrades_when_builder_errors(monkeypatch):
    def boom(sport, *a, **k):
        raise RuntimeError("provider down")

    monkeypatch.setattr(serve_mod, "_build_prop_board", boom)
    client = _client_with_snapshot(monkeypatch, None)
    r = client.get("/api/props?sport=soccer_intl")
    assert r.status_code == 200  # never 500
    body = r.json()
    assert body["status"] == "unavailable"
    assert body["served_from"] == "live_compute"
    assert body["edges"] == []
