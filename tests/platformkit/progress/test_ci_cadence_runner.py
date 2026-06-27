"""Per-file test for ci_cadence_runner -- supervised M8 loop-wrapper (W4). NO full pytest.

  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/progress/test_ci_cadence_runner.py -q
"""
from __future__ import annotations

from scripts.platformkit.progress import ci_cadence_runner as r


def test_bounded_run_ticks_and_stops():
    """A bounded run executes exactly max_ticks of run_tick and ALWAYS stops."""
    ticks = {"n": 0}

    def _run_fn(now):
        ticks["n"] += 1
        return type("Res", (), {"overall": "ok", "degraded": []})

    slept = []
    n = r.run(interval_sec=10.0, run_fn=_run_fn,
              clock=lambda: 100.0, sleep=lambda s: slept.append(s), max_ticks=3)
    assert n == 3
    assert ticks["n"] == 3
    # slept between ticks but NOT after the final one (loop breaks at max_ticks).
    assert slept == [10.0, 10.0]


def test_heartbeat_beat_at_boot_and_each_tick(monkeypatch):
    """The runner beats the m8 liveness heartbeat at boot + every tick (stale-never-green)."""
    beats = []
    monkeypatch.setattr(r, "_beat", lambda now=None: beats.append(now))
    r.run(interval_sec=1.0, run_fn=lambda now: None,
          clock=lambda: 7.0, sleep=lambda s: None, max_ticks=2)
    # 1 boot beat + 1 per tick = 3 total; the per-tick beats carry the tick's now.
    assert len(beats) == 3
    assert beats.count(7.0) >= 2


def test_run_fn_raise_does_not_crash():
    """A raising tick is degrade-isolated (run_tick swallows it); the loop continues."""
    def _boom(now):
        raise RuntimeError("cadence dead")
    n = r.run(interval_sec=1.0, run_fn=_boom,
              clock=lambda: 0.0, sleep=lambda s: None, max_ticks=2)
    assert n == 2  # loop did NOT crash; it kept ticking


def test_should_stop_halts_loop():
    calls = {"n": 0}

    def _stop():
        calls["n"] += 1
        return calls["n"] >= 2

    n = r.run(interval_sec=1.0, run_fn=lambda now: None,
              clock=lambda: 0.0, sleep=lambda s: None, should_stop=_stop, max_ticks=99)
    assert n == 1  # stopped before max_ticks


if __name__ == "__main__":
    import sys
    test_bounded_run_ticks_and_stops()
    print("ok: test_bounded_run_ticks_and_stops")
    test_run_fn_raise_does_not_crash()
    print("ok: test_run_fn_raise_does_not_crash")
    test_should_stop_halts_loop()
    print("ok: test_should_stop_halts_loop")
    sys.exit(0)
