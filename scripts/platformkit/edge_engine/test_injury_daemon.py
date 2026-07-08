"""Per-file tests for injury_daemon (M39). Offline; injected feed + heartbeat.

Covers snapshot-dating (as-of vintage rows keyed by snapshot_date), same-day
idempotence, a fresh row on a new day, per-sport isolation of a raising feed, and
the heartbeat write. No network.

Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/edge_engine/test_injury_daemon.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.platformkit.edge_engine import facts_store, injury_daemon  # noqa: E402

_FIXTURE = {
    "injuries": [
        {"id": "1", "displayName": "Atlanta Hawks", "injuries": [
            {"status": "Out", "date": "2026-07-06T18:00Z", "longComment": "knee.",
             "athlete": {"displayName": "Test Guy", "links": []}},
        ]},
    ]
}


def test_tick_snapshot_dates_and_beats(monkeypatch, tmp_path):
    monkeypatch.setattr(facts_store, "FACTS_DIR", tmp_path)
    beats = []
    monkeypatch.setattr(injury_daemon, "_beat", lambda now=None: beats.append(now))
    doc = injury_daemon.tick(now=123.0, sports=("nba",), snapshot_date="2026-07-08",
                             http_get=lambda url: _FIXTURE)
    assert doc["snapshot_date"] == "2026-07-08"
    assert doc["sports"]["nba"] == {"fetched": 1, "added": 1}
    assert beats == [123.0]
    rows = facts_store.read_rows(facts_store.path_for("injury", "nba"))
    assert rows and rows[0]["snapshot_date"] == "2026-07-08"


def test_same_day_rerun_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(facts_store, "FACTS_DIR", tmp_path)
    monkeypatch.setattr(injury_daemon, "_beat", lambda now=None: None)
    d1 = injury_daemon.tick(now=1.0, sports=("nba",), snapshot_date="2026-07-08",
                            http_get=lambda url: _FIXTURE)
    d2 = injury_daemon.tick(now=2.0, sports=("nba",), snapshot_date="2026-07-08",
                            http_get=lambda url: _FIXTURE)
    assert d1["sports"]["nba"]["added"] == 1
    assert d2["sports"]["nba"]["added"] == 0  # same snapshot day -> nothing new


def test_new_day_is_a_fresh_asof_row(monkeypatch, tmp_path):
    monkeypatch.setattr(facts_store, "FACTS_DIR", tmp_path)
    monkeypatch.setattr(injury_daemon, "_beat", lambda now=None: None)
    injury_daemon.tick(now=1.0, sports=("nba",), snapshot_date="2026-07-08",
                       http_get=lambda url: _FIXTURE)
    d2 = injury_daemon.tick(now=2.0, sports=("nba",), snapshot_date="2026-07-09",
                            http_get=lambda url: _FIXTURE)
    assert d2["sports"]["nba"]["added"] == 1  # new snapshot day -> fresh vintage row


def test_tick_isolates_a_raising_sport(monkeypatch):
    monkeypatch.setattr(injury_daemon, "_beat", lambda now=None: None)

    def boom(sport, http_get=None, snapshot_date=None):
        if sport == "wnba":
            raise RuntimeError("boom")
        return (2, 2)

    doc = injury_daemon.tick(now=1.0, sports=("nba", "wnba"), store_fn=boom)
    assert doc["sports"]["nba"] == {"fetched": 2, "added": 2}
    assert doc["sports"]["wnba"] == {"error": "RuntimeError"}


def test_store_fn_receives_snapshot_date(monkeypatch):
    monkeypatch.setattr(injury_daemon, "_beat", lambda now=None: None)
    seen = {}

    def fake_store(sport, http_get=None, snapshot_date=None):
        seen[sport] = snapshot_date
        return (0, 0)

    injury_daemon.tick(now=1.0, sports=("nba",), snapshot_date="2026-07-08",
                       store_fn=fake_store)
    assert seen == {"nba": "2026-07-08"}
