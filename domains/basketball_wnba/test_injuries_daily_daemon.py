"""Per-file tests for injuries_daily_daemon (offline; injected ingest/clock/sleep). NO full pytest.

  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_injuries_daily_daemon.py -q
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from domains.basketball_wnba import injuries_daily_daemon as d


def test_seconds_until_next_run_same_day():
    now = dt.datetime(2026, 7, 5, 3, 0, 0, tzinfo=dt.timezone.utc)
    secs = d._seconds_until_next_run(now, hour_utc=11)
    assert secs == 8 * 3600.0


def test_seconds_until_next_run_rolls_to_tomorrow_when_past_hour():
    now = dt.datetime(2026, 7, 5, 12, 0, 0, tzinfo=dt.timezone.utc)
    secs = d._seconds_until_next_run(now, hour_utc=11)
    assert secs == 23 * 3600.0


def test_seconds_until_next_run_at_exact_boundary_rolls_to_tomorrow():
    now = dt.datetime(2026, 7, 5, 11, 0, 0, tzinfo=dt.timezone.utc)
    secs = d._seconds_until_next_run(now, hour_utc=11)
    assert secs == 24 * 3600.0


def test_tick_returns_row_count_from_injected_ingest_fn():
    df = pd.DataFrame({"team": ["A", "B"], "athlete_name": ["x", "y"]})
    n = d.tick(ingest_fn=lambda: df)
    assert n == 2


def test_tick_never_raises_on_bad_ingest_fn():
    def _boom():
        raise RuntimeError("feed dead")

    n = d.tick(ingest_fn=_boom)
    assert n == 0


def test_run_bounded_stops_at_max_ticks_no_real_sleep():
    slept = []
    clock_calls = {"n": 0}

    def clock():
        clock_calls["n"] += 1
        # advance a fake clock each call so _seconds_until_next_run always has
        # a fresh, valid "now" without ever touching the real wall clock.
        return dt.datetime(2026, 7, 5, 3, 0, 0, tzinfo=dt.timezone.utc) + dt.timedelta(
            hours=clock_calls["n"])

    n = d.run(ingest_fn=lambda: pd.DataFrame(), clock=clock,
              sleep=lambda s: slept.append(s), max_ticks=3)
    assert n == 3
    assert len(slept) == 2  # sleeps between ticks; breaks at max_ticks before the last sleep


def test_run_beats_at_boot_and_each_tick(monkeypatch):
    beats = []
    monkeypatch.setattr(d, "_beat", lambda *a, **k: beats.append((a, k)))
    clock = lambda: dt.datetime(2026, 7, 5, 3, 0, 0, tzinfo=dt.timezone.utc)
    d.run(ingest_fn=lambda: pd.DataFrame(), clock=clock,
          sleep=lambda s: None, max_ticks=2)
    # 1 boot beat + 1 per tick (2 ticks) = 3 total.
    assert len(beats) == 3


if __name__ == "__main__":
    for fn in (
        test_seconds_until_next_run_same_day,
        test_seconds_until_next_run_rolls_to_tomorrow_when_past_hour,
        test_seconds_until_next_run_at_exact_boundary_rolls_to_tomorrow,
        test_tick_returns_row_count_from_injected_ingest_fn,
        test_tick_never_raises_on_bad_ingest_fn,
        test_run_bounded_stops_at_max_ticks_no_real_sleep,
    ):
        fn()
        print("ok:", fn.__name__)
