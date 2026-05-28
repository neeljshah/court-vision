"""Tests for the steam (sharp-money) badge feature.

Covers:
  - api._courtvision_odds.steam_lookup() — file parsing, freshness, dedup
  - api/lines_router.py /api/lines/scan — steam field attached per prop
  - api/templates/scan.html — 🔥 badge rendered for fresh events
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _iso_utc(unix_ts: float) -> str:
    """Render a unix timestamp as ISO-8601 with a trailing Z (matches producer)."""
    return datetime.fromtimestamp(unix_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_jsonl(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


def _reset_steam_cache():
    """Drop the module-level cache so each test sees a fresh read."""
    from api import _courtvision_odds as cvo
    cvo._STEAM_CACHE.clear()


# ── steam_lookup() unit tests ─────────────────────────────────────────────────

def test_steam_lookup_empty_returns_dict(tmp_path, monkeypatch):
    """Missing jsonl file → empty dict, no exception."""
    from api import _courtvision_odds as cvo
    monkeypatch.setattr(cvo, "_STEAM_PATH", tmp_path / "absent.jsonl")
    _reset_steam_cache()
    out = cvo.steam_lookup("2026-05-27")
    assert out == {}


def test_steam_lookup_parses_event(tmp_path, monkeypatch):
    """One fresh event should be indexed under both old_line and new_line."""
    from api import _courtvision_odds as cvo
    p = tmp_path / "steam.jsonl"
    now = time.time()
    _write_jsonl(p, [{
        "topic": "sharp.steam",
        "player": "Shai Gilgeous-Alexander",
        "stat": "pts",
        "old_line": 30.5,
        "new_line": 31.5,
        "direction": "up",
        "n_books_moving": 4,
        "pin_moved": True,
        "ts": _iso_utc(now - 60),  # 60s old
        "confidence": "high",
    }])
    monkeypatch.setattr(cvo, "_STEAM_PATH", p)
    _reset_steam_cache()
    out = cvo.steam_lookup("2026-05-27")

    # Both lines should be present
    assert ("shai gilgeous-alexander", "pts", 30.5) in out
    assert ("shai gilgeous-alexander", "pts", 31.5) in out

    ev = out[("shai gilgeous-alexander", "pts", 30.5)]
    assert ev["direction"] == "up"
    assert ev["age_sec"] >= 50 and ev["age_sec"] <= 120
    assert ev["confidence"] == "high"
    assert ev["pin_moved"] is True


def test_steam_lookup_filters_old(tmp_path, monkeypatch):
    """Events older than 1 hour should be dropped."""
    from api import _courtvision_odds as cvo
    p = tmp_path / "steam.jsonl"
    now = time.time()
    _write_jsonl(p, [{
        "player": "Jaylen Brown",
        "stat": "reb",
        "old_line": 5.5,
        "new_line": 5.0,
        "direction": "down",
        "ts": _iso_utc(now - 7200),  # 2h old
    }])
    monkeypatch.setattr(cvo, "_STEAM_PATH", p)
    _reset_steam_cache()
    out = cvo.steam_lookup("2026-05-27")
    assert out == {}


def test_steam_lookup_fresh_takes_priority(tmp_path, monkeypatch):
    """When two events share a key, the newer one wins."""
    from api import _courtvision_odds as cvo
    p = tmp_path / "steam.jsonl"
    now = time.time()
    _write_jsonl(p, [
        {
            "player": "Jaylen Brown", "stat": "reb",
            "old_line": 5.5, "new_line": 5.0,
            "direction": "down", "n_books_moving": 2,
            "ts": _iso_utc(now - 600),  # 10 min old
        },
        {
            "player": "Jaylen Brown", "stat": "reb",
            "old_line": 5.5, "new_line": 5.0,
            "direction": "down", "n_books_moving": 5,
            "ts": _iso_utc(now - 30),  # 30 sec old — fresher
        },
    ])
    monkeypatch.setattr(cvo, "_STEAM_PATH", p)
    _reset_steam_cache()
    out = cvo.steam_lookup("2026-05-27")
    ev = out[("jaylen brown", "reb", 5.5)]
    # Fresher event has n_books_moving=5 → magnitude=5; age should be ~30s
    assert ev["age_sec"] <= 90
    assert ev["magnitude"] == 5


def test_steam_lookup_handles_malformed_lines(tmp_path, monkeypatch):
    """A malformed JSON line should be skipped without aborting the parse."""
    from api import _courtvision_odds as cvo
    p = tmp_path / "steam.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    good = json.dumps({
        "player": "LeBron James", "stat": "pts",
        "old_line": 25.5, "new_line": 26.5,
        "direction": "up", "ts": _iso_utc(now - 30),
    })
    with p.open("w", encoding="utf-8") as f:
        f.write("{not valid json\n")
        f.write("\n")  # blank line
        f.write(good + "\n")
        f.write("garbage trailing\n")
    monkeypatch.setattr(cvo, "_STEAM_PATH", p)
    _reset_steam_cache()
    out = cvo.steam_lookup("2026-05-27")
    # Only the one well-formed event surfaces
    assert ("lebron james", "pts", 25.5) in out
    assert ("lebron james", "pts", 26.5) in out
    assert len([k for k in out if k[0] == "lebron james"]) == 2


# ── /api/lines/scan integration ───────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    from api.main import app
    return TestClient(app)


def test_scan_endpoint_no_steam_returns_none(client, tmp_path, monkeypatch):
    """With no steam events, every prop in /api/lines/scan should have steam==None."""
    from api import _courtvision_odds as cvo
    monkeypatch.setattr(cvo, "_STEAM_PATH", tmp_path / "absent.jsonl")
    _reset_steam_cache()
    r = client.get("/api/lines/scan?date=2026-05-29&min_books=1")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("n_steam") == 0
    if j["n_props"] == 0:
        pytest.skip("no props on 2026-05-29 — endpoint still responded OK")
    for p in j["props"]:
        assert p.get("steam") is None


def test_scan_endpoint_attaches_steam(client, tmp_path, monkeypatch):
    """Synthesize a steam event matching a real player in the day's CSVs."""
    from api import _courtvision_odds as cvo

    # Pull a real (player, stat, line) tuple straight out of consolidate so
    # we know the join is exercised end-to-end.
    sample_props = cvo.consolidate("2026-05-29")
    if not sample_props:
        pytest.skip("no consolidated props for 2026-05-29 fixture date")
    target = sample_props[0]
    player = target["player"]
    stat = target["stat"]
    line = float(target["line"])

    p = tmp_path / "steam.jsonl"
    now = time.time()
    _write_jsonl(p, [{
        "player": player, "stat": stat,
        "old_line": line, "new_line": line + 0.5,
        "direction": "up", "n_books_moving": 3,
        "ts": _iso_utc(now - 60),
        "confidence": "medium",
    }])
    monkeypatch.setattr(cvo, "_STEAM_PATH", p)
    _reset_steam_cache()
    # Also clear the consolidate cache so we hit a fresh path each call
    cvo._CACHE.clear()

    r = client.get("/api/lines/scan?date=2026-05-29&min_books=1")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("n_steam", 0) >= 1, f"expected at least one steam-tagged prop, got envelope={j.get('n_steam')}"
    matched = [
        pp for pp in j["props"]
        if pp.get("steam") and pp["player"].lower() == player.lower()
        and pp["stat"] == stat
        and abs(float(pp["line"]) - line) < 0.01
    ]
    assert matched, "expected the synthesized steam event to attach to its target prop"
    ev = matched[0]["steam"]
    assert ev["direction"] == "up"
    assert ev["age_sec"] < 600


def test_steam_field_present_in_response_envelope(client, tmp_path, monkeypatch):
    """n_steam key must be present on the envelope even with zero events."""
    from api import _courtvision_odds as cvo
    monkeypatch.setattr(cvo, "_STEAM_PATH", tmp_path / "absent.jsonl")
    _reset_steam_cache()
    r = client.get("/api/lines/scan?date=2026-05-29&min_books=1")
    assert r.status_code == 200
    j = r.json()
    assert "n_steam" in j
    assert isinstance(j["n_steam"], int)
