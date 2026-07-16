"""Per-file test for news_daemon (M45). Offline; injected feed + heartbeat.

Covers: writes rows + heartbeat, dedupes a same-payload re-run, per-sport
isolation of a raising feed. No network.

Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/edge_engine/test_news_daemon.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.platformkit.edge_engine import facts_store, news_daemon  # noqa: E402

_FIXTURE = {
    "articles": [
        {"headline": "Test Guy questionable for tonight", "published": "2026-07-15T12:00Z",
         "categories": [{"type": "athlete", "description": "Test Guy"},
                        {"type": "team", "description": "Atlanta Hawks"}],
         "links": {"web": {"href": "https://example.com/1"}}},
    ]
}


def test_tick_writes_rows_and_beats(monkeypatch, tmp_path):
    monkeypatch.setattr(facts_store, "FACTS_DIR", tmp_path)
    beats = []
    monkeypatch.setattr(news_daemon, "_beat", lambda now=None: beats.append(now))
    doc = news_daemon.tick(now=123.0, sports=("nba",), http_get=lambda url: _FIXTURE)
    assert doc["sports"]["nba"] == {"fetched": 1, "added": 1}
    assert beats == [123.0]
    rows = facts_store.read_rows(facts_store.path_for("news", "nba"))
    assert rows and rows[0]["players"] == ["Test Guy"]


def test_rerun_same_payload_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(facts_store, "FACTS_DIR", tmp_path)
    monkeypatch.setattr(news_daemon, "_beat", lambda now=None: None)
    d1 = news_daemon.tick(now=1.0, sports=("nba",), http_get=lambda url: _FIXTURE)
    d2 = news_daemon.tick(now=2.0, sports=("nba",), http_get=lambda url: _FIXTURE)
    assert d1["sports"]["nba"]["added"] == 1
    assert d2["sports"]["nba"]["added"] == 0  # same headline|published -> nothing new


def test_tick_isolates_a_raising_sport(monkeypatch):
    monkeypatch.setattr(news_daemon, "_beat", lambda now=None: None)

    def boom(sport, http_get=None):
        if sport == "mlb":
            raise RuntimeError("boom")
        return (2, 2)

    doc = news_daemon.tick(now=1.0, sports=("nba", "mlb"), store_fn=boom)
    assert doc["sports"]["nba"] == {"fetched": 2, "added": 2}
    assert doc["sports"]["mlb"] == {"error": "RuntimeError"}
