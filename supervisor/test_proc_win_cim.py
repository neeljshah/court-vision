"""Per-file test for supervisor.proc_win_cim TTL cache (tick-cost fix 2026-07-10).

The bug: each cmdline_for_pid / find_by_match re-spawned PowerShell to enumerate
the whole process table (~1.3s), and supervise() calls it ~90-130x per tick. The
TTL cache must make a burst of lookups spawn PowerShell ONCE.
"""
from __future__ import annotations

import supervisor.proc_win_cim as cim


class _FakeRun:
    """Counts subprocess.run invocations; returns two NDJSON process rows."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *_a, **_k):
        self.calls += 1

        class _R:
            stdout = '{"pid":111,"cmdline":"python -m foo.bar"}\n' \
                     '{"pid":222,"cmdline":"python -m baz.qux"}\n'
        return _R()


def _reset_cache() -> None:
    cim._table_cache["t"] = 0.0
    cim._table_cache["rows"] = []


def test_burst_enumerates_once(monkeypatch) -> None:
    """N back-to-back lookups within the TTL => ONE PowerShell spawn."""
    _reset_cache()
    fake = _FakeRun()
    monkeypatch.setattr(cim.subprocess, "run", fake)
    # Simulate a tick's worth of liveness lookups.
    for _ in range(50):
        assert cim.cmdline_for_pid(111) == "python -m foo.bar"
    assert cim.cmdline_for_pid(222) == "python -m baz.qux"
    assert fake.calls == 1, "burst must reuse the cached table, not re-enumerate"


def test_ttl_expiry_re_enumerates(monkeypatch) -> None:
    """Once the cache is stale, the next call spawns PowerShell again."""
    _reset_cache()
    fake = _FakeRun()
    monkeypatch.setattr(cim.subprocess, "run", fake)
    cim.ps_process_table()
    assert fake.calls == 1
    # Force staleness (simulate the inter-tick sleep elapsing).
    cim._table_cache["t"] -= (cim._TABLE_TTL_SEC + 1.0)
    cim.ps_process_table()
    assert fake.calls == 2


def test_failed_enumeration_not_cached(monkeypatch) -> None:
    """An empty/failed enumeration must not be served from cache."""
    _reset_cache()

    class _Empty:
        stdout = ""

    calls = {"n": 0}

    def _run(*_a, **_k):
        calls["n"] += 1
        return _Empty()

    monkeypatch.setattr(cim.subprocess, "run", _run)
    assert cim.ps_process_table() == []
    assert cim.ps_process_table() == []
    assert calls["n"] == 2, "empty result must retry, not serve stale-empty"
