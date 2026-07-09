"""Per-file test for failsafe_jobs (+ the m29 scheduler registration). Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ops_sentinel/test_failsafe_jobs.py -q
"""
from __future__ import annotations

from scripts.platformkit.ops_sentinel import failsafe_jobs


def test_run_all_isolates_a_raising_job():
    calls = []

    def ok(*, now):
        calls.append(now)

    def boom(*, now):
        raise RuntimeError("sentinel exploded")

    out = failsafe_jobs.run_all(now=42.0, jobs={"a": ok, "b": boom, "c": ok})
    assert out == {"a": True, "b": False, "c": True}
    assert calls == [42.0, 42.0]


def test_registry_names_the_four_failsafe_sentinels():
    assert set(failsafe_jobs._jobs()) == {
        "guard_integrity", "disk_space", "heartbeat_coverage",
        "exception_burst"}


def test_m29_tick_runs_failsafe_jobs(monkeypatch):
    """The m29 scheduler tick is the registration point: it must invoke
    failsafe_jobs.run_all every tick (pending supervisor restart to arm)."""
    from scripts.platformkit.ops_sentinel import output_freshness_runner as r

    seen = {}
    monkeypatch.setattr(failsafe_jobs, "run_all",
                        lambda *, now: seen.setdefault("now", now))
    rows = r.tick(now=77.0, check_fn=lambda **kw: [], write_fn=lambda *a, **kw: True)
    assert seen == {"now": 77.0}
    assert rows == []
