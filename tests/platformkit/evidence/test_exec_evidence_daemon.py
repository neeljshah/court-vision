"""Per-file tests for exec_evidence_daemon (injected fns, no network, no real
ledger/series writes).

cd /c/Users/neelj/nba-ai-system && python -m pytest \
    tests/platformkit/evidence/test_exec_evidence_daemon.py -q
"""
from __future__ import annotations

from scripts.platformkit.evidence import exec_evidence_daemon as D


def test_tick_reports_appended_snapshot():
    def append_fn():
        return {"snapshot_hour": "2026-07-15T12"}

    doc = D.tick(now=1.0, append_fn=append_fn)
    assert doc == {"appended": True, "snapshot_hour": "2026-07-15T12"}


def test_tick_reports_noop_when_append_fn_returns_none():
    doc = D.tick(now=1.0, append_fn=lambda: None)
    assert doc == {"appended": False, "snapshot_hour": None}


def test_tick_isolates_append_failure():
    def _boom():
        raise RuntimeError("append exploded")

    doc = D.tick(now=1.0, append_fn=_boom)
    assert doc["appended"] is False
    assert "error" in doc


def test_run_calls_tick_max_ticks_times(monkeypatch):
    calls = []
    monkeypatch.setattr(D, "append_snapshot", lambda: calls.append(1) or None)
    clock = iter([1.0, 2.0, 3.0]).__next__
    sleeps = []

    ticks = D.run(clock=clock, sleep=sleeps.append, max_ticks=2,
                  interval_sec=999)
    assert ticks == 2
    assert calls == [1, 1]
    assert sleeps == [999.0]
