"""Per-file tests for output_freshness_runner (offline; injected check/write/clock/sleep)."""
from __future__ import annotations

from scripts.platformkit.ops_sentinel import output_freshness_runner as r


def test_tick_calls_check_then_write_then_returns_rows(monkeypatch):
    calls = []
    monkeypatch.setattr(r, "_beat", lambda *_a, **_k: calls.append("beat"))
    rows_out = [{"name": "m25_ingame_outcome_verdict", "status": "GREEN"}]

    def fake_check(now=None):
        calls.append(("check", now))
        return rows_out

    def fake_write(rows, now=None):
        calls.append(("write", rows, now))
        return True

    got = r.tick(now=123.0, check_fn=fake_check, write_fn=fake_write)
    assert got == rows_out
    assert calls == [("check", 123.0), ("write", rows_out, 123.0), "beat"]


def test_tick_never_raises_on_bad_check_or_write(monkeypatch):
    monkeypatch.setattr(r, "_beat", lambda *_a, **_k: None)
    got = r.tick(now=1.0,
                check_fn=lambda now=None: (_ for _ in ()).throw(ValueError("boom")),
                write_fn=lambda rows, now=None: (_ for _ in ()).throw(ValueError("boom2")))
    assert got == []  # a bad check -> empty rows, never a crash


def test_run_loops_max_ticks_and_beats_at_boot(monkeypatch):
    beats = []
    monkeypatch.setattr(r, "_beat", lambda *a, **k: beats.append((a, k)))
    clock_calls = {"n": 0}

    def clock():
        clock_calls["n"] += 1
        return float(clock_calls["n"])

    sleeps = []
    n = r.run(max_ticks=3, clock=clock, sleep=lambda s: sleeps.append(s),
              check_fn=lambda now=None: [], write_fn=lambda rows, now=None: True)
    assert n == 3
    assert len(sleeps) == 2          # sleeps between ticks; breaks at max_ticks before the last sleep
    assert len(beats) >= 1           # at least the boot beat fired


def test_run_stops_on_should_stop(monkeypatch):
    monkeypatch.setattr(r, "_beat", lambda *_a, **_k: None)
    calls = {"n": 0}

    def should_stop():
        calls["n"] += 1
        return calls["n"] > 2

    n = r.run(clock=lambda: 1.0, sleep=lambda s: None, should_stop=should_stop,
              check_fn=lambda now=None: [], write_fn=lambda rows, now=None: True)
    assert n == 2
