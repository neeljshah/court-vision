"""Per-file tests for scripts.platformkit.frontend.refresh_daemon.

Network-free: the writer seam is fully injected (stub functions), so no snapshot
is built and no disk/network is touched. Verifies the degrade-never-die contract:
run_once returns the writer's dict; a writer that RAISES makes run_once return an
empty dict (last-good snapshots untouched) without raising; run_forever honors
max_ticks and a counting stub sleep, calling the writer exactly that many times.

Run (per-file ONLY -- full pytest freezes this box):
  cd /c/Users/neelj/nba-ai-system && \
    python -m pytest scripts/platformkit/frontend/test_refresh_daemon.py -q
"""
from __future__ import annotations

from scripts.platformkit.frontend import refresh_daemon as rd


def test_run_once_returns_writer_dict():
    calls = []

    def writer(sports=None):
        calls.append(sports)
        return {"nba": "/tmp/nba.json", "mlb": "/tmp/mlb.json"}

    out = rd.run_once(sports=["nba", "mlb"], writer=writer)
    assert out == {"nba": "/tmp/nba.json", "mlb": "/tmp/mlb.json"}
    assert calls == [["nba", "mlb"]]  # sports forwarded to the writer


def test_run_once_swallows_writer_error():
    def boom(sports=None):
        raise RuntimeError("odds feed down")

    # Must NOT raise; returns empty (last-good snapshots stay on disk).
    out = rd.run_once(writer=boom)
    assert out == {}


def test_run_once_non_dict_writer_result_is_empty():
    out = rd.run_once(writer=lambda sports=None: None)
    assert out == {}


def test_run_forever_calls_writer_max_ticks_times():
    calls = {"n": 0}
    sleeps = []

    def writer(sports=None):
        calls["n"] += 1
        return {"nba": "/tmp/nba.json"}

    def counting_sleep(secs):
        sleeps.append(secs)

    ticks = rd.run_forever(interval_s=5, sports=["nba"], writer=writer,
                           sleep=counting_sleep, max_ticks=2)
    assert ticks == 2
    assert calls["n"] == 2                 # writer called once per tick
    # sleeps only BETWEEN ticks, never after the final tick
    assert sleeps == [5]


def test_run_forever_survives_writer_errors():
    calls = {"n": 0}

    def flaky(sports=None):
        calls["n"] += 1
        raise ValueError("transient")

    # The loop must complete all ticks despite every writer call raising.
    ticks = rd.run_forever(interval_s=0, writer=flaky,
                           sleep=lambda s: None, max_ticks=3)
    assert ticks == 3
    assert calls["n"] == 3


def test_run_forever_single_tick_does_not_sleep():
    sleeps = []
    ticks = rd.run_forever(interval_s=1, writer=lambda sports=None: {},
                           sleep=lambda s: sleeps.append(s), max_ticks=1)
    assert ticks == 1
    assert sleeps == []  # no sleep after the only tick
