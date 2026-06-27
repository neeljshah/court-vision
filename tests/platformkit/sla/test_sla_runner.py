"""tests/platformkit/sla/test_sla_runner.py -- per-file tests for IOX-1 runner.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/sla/test_sla_runner.py -q

Acceptance tests:
  - runner beats heartbeat m14_sla each tick (injectable clock/sleep/max_ticks)
  - empty artifact list -> [] not error
  - tick writes data/frontend/ops/sla_scoreboard.json atomically
  - run() returns the tick count
  - max_ticks bounds the loop
  - never raises
"""
from __future__ import annotations

import json
import pathlib
import time
from typing import List
from unittest.mock import patch

import pytest

from scripts.platformkit.sla.sla_runner import (
    HEARTBEAT_COMPONENT,
    run,
    tick,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_clock(epoch: float = 1_000_000.0):
    """Return a factory that produces a steady clock value."""
    def _c():
        return epoch
    return _c


def _fake_sleep():
    """A no-op sleep that records calls."""
    calls: List[float] = []

    def _s(sec: float):
        calls.append(sec)

    _s.calls = calls  # type: ignore[attr-defined]
    return _s


# ---------------------------------------------------------------------------
# tick() tests
# ---------------------------------------------------------------------------

class TestTick:
    def test_tick_returns_list(self, tmp_path):
        out = tmp_path / "sla_scoreboard.json"
        result = tick(now=1_000_000.0, artifacts=[], out_path=out)
        assert isinstance(result, list)

    def test_tick_empty_artifacts_writes_empty_rows(self, tmp_path):
        out = tmp_path / "sla_scoreboard.json"
        tick(now=1_000_000.0, artifacts=[], out_path=out)
        doc = json.loads(out.read_text(encoding="ascii"))
        assert doc["rows"] == []

    def test_tick_with_fresh_artifact(self, tmp_path):
        f = tmp_path / "snap.json"
        f.write_text("{}", encoding="ascii")
        out = tmp_path / "sla_scoreboard.json"

        mtime = f.stat().st_mtime
        now = mtime + 10.0
        rows = tick(now=now, artifacts=[(f, 300.0)], out_path=out)
        assert len(rows) == 1
        assert rows[0]["breached"] is False
        assert rows[0]["status"] == "ok"

    def test_tick_with_absent_artifact(self, tmp_path):
        absent = tmp_path / "ghost.json"
        out = tmp_path / "sla_scoreboard.json"
        rows = tick(now=1_000_000.0, artifacts=[(absent, 300.0)], out_path=out)
        assert len(rows) == 1
        assert rows[0]["breached"] is True
        assert rows[0]["status"] == "STALE"

    def test_tick_writes_atomic_json(self, tmp_path):
        out = tmp_path / "sla_scoreboard.json"
        tick(now=1_000_000.0, artifacts=[], out_path=out)
        # Should be valid JSON (atomic write completed)
        doc = json.loads(out.read_text(encoding="ascii"))
        assert "rows" in doc
        assert "any_breached" in doc

    def test_tick_beats_heartbeat(self, tmp_path):
        """tick() should attempt to beat the m14_sla heartbeat."""
        out = tmp_path / "sla_scoreboard.json"
        beat_calls: List[float] = []

        def fake_beat(component, *, _now=None):
            beat_calls.append(_now or 0.0)

        with patch("scripts.platformkit.sla.sla_runner._beat") as mock_beat:
            tick(now=1_000_000.0, artifacts=[], out_path=out)
            assert mock_beat.called

    def test_tick_never_raises_on_bad_artifacts(self, tmp_path):
        out = tmp_path / "sla.json"
        # Should not raise even with pathological input
        result = tick(now=1_000_000.0, artifacts=None, out_path=out)  # type: ignore[arg-type]
        assert isinstance(result, list)

    def test_tick_no_dollar_key_in_output(self, tmp_path):
        out = tmp_path / "sla.json"
        tick(now=1_000_000.0, artifacts=[], out_path=out)
        doc = json.loads(out.read_text(encoding="ascii"))
        # No dollar-sign JSON keys at the top level
        all_keys = set(doc.keys())
        assert not any("$" in k for k in all_keys)
        assert "roi" not in all_keys
        assert "profit" not in all_keys


# ---------------------------------------------------------------------------
# run() tests
# ---------------------------------------------------------------------------

class TestRun:
    def test_run_max_ticks_returns_count(self, tmp_path):
        out = tmp_path / "sla.json"
        sleep = _fake_sleep()
        count = run(
            artifacts=[],
            out_path=out,
            max_ticks=3,
            clock=_fake_clock(1_000_000.0),
            sleep=sleep,
        )
        assert count == 3

    def test_run_zero_ticks_on_stop(self, tmp_path):
        out = tmp_path / "sla.json"
        count = run(
            artifacts=[],
            out_path=out,
            max_ticks=0,
            clock=_fake_clock(1_000_000.0),
            sleep=_fake_sleep(),
        )
        assert count == 0

    def test_run_sleeps_between_ticks(self, tmp_path):
        out = tmp_path / "sla.json"
        sleep = _fake_sleep()
        run(
            artifacts=[],
            out_path=out,
            max_ticks=3,
            clock=_fake_clock(),
            sleep=sleep,
            interval_sec=60.0,
        )
        # sleep called between ticks (not after last tick)
        assert len(sleep.calls) == 2  # type: ignore[attr-defined]

    def test_run_writes_scoreboard_each_tick(self, tmp_path):
        out = tmp_path / "sla.json"
        f = tmp_path / "art.json"
        f.write_text("{}", encoding="ascii")
        mtime = f.stat().st_mtime

        tick_num = [0]
        clock_times = [mtime + 10, mtime + 70, mtime + 130]

        def advancing_clock():
            idx = min(tick_num[0], len(clock_times) - 1)
            t = clock_times[idx]
            tick_num[0] += 1
            return t

        run(
            artifacts=[(f, 300.0)],
            out_path=out,
            max_ticks=3,
            clock=advancing_clock,
            sleep=_fake_sleep(),
        )
        # File should exist with the last scoreboard
        doc = json.loads(out.read_text(encoding="ascii"))
        assert len(doc["rows"]) == 1

    def test_run_beats_heartbeat_per_tick(self, tmp_path):
        out = tmp_path / "sla.json"
        beat_count = [0]

        def counting_beat(now_epoch=None):
            beat_count[0] += 1

        with patch("scripts.platformkit.sla.sla_runner._beat", side_effect=counting_beat):
            run(
                artifacts=[],
                out_path=out,
                max_ticks=4,
                clock=_fake_clock(),
                sleep=_fake_sleep(),
            )
        # One beat per tick
        assert beat_count[0] == 4

    def test_run_stops_on_should_stop(self, tmp_path):
        out = tmp_path / "sla.json"
        calls = [0]

        def stop_after_two():
            calls[0] += 1
            return calls[0] > 2

        count = run(
            artifacts=[],
            out_path=out,
            clock=_fake_clock(),
            sleep=_fake_sleep(),
            should_stop=stop_after_two,
        )
        assert count == 2

    def test_run_never_raises_on_bad_input(self, tmp_path):
        out = tmp_path / "sla.json"

        def bad_clock():
            raise RuntimeError("clock broken")

        count = run(
            artifacts=[],
            out_path=out,
            max_ticks=1,
            clock=bad_clock,
            sleep=_fake_sleep(),
        )
        # Should complete one tick (falling back to wall time) without raising
        assert count == 1

    def test_run_returns_int(self, tmp_path):
        out = tmp_path / "sla.json"
        result = run(
            artifacts=[],
            out_path=out,
            max_ticks=2,
            clock=_fake_clock(),
            sleep=_fake_sleep(),
        )
        assert isinstance(result, int)


# ---------------------------------------------------------------------------
# Heartbeat component constant
# ---------------------------------------------------------------------------

class TestHeartbeatComponent:
    def test_component_name(self):
        assert HEARTBEAT_COMPONENT == "m14_sla"


# ---------------------------------------------------------------------------
# End-to-end: full artifact cycle
# ---------------------------------------------------------------------------

class TestEndToEnd:
    def test_e2e_stale_artifact_survives_full_run(self, tmp_path):
        """run() for 2 ticks with one stale artifact -> scoreboard shows STALE."""
        absent = tmp_path / "missing.json"
        out = tmp_path / "ops" / "sla_scoreboard.json"

        run(
            artifacts=[(absent, 300.0)],
            out_path=out,
            max_ticks=2,
            clock=_fake_clock(1_000_000.0),
            sleep=_fake_sleep(),
        )
        doc = json.loads(out.read_text(encoding="ascii"))
        assert doc["any_breached"] is True
        assert doc["rows"][0]["status"] == "STALE"

    def test_e2e_fresh_artifact_shows_ok(self, tmp_path):
        """run() with a fresh artifact -> ok in the scoreboard."""
        f = tmp_path / "live.json"
        f.write_text("{}", encoding="ascii")
        out = tmp_path / "sla.json"

        mtime = f.stat().st_mtime
        now = mtime + 5.0  # very fresh

        run(
            artifacts=[(f, 300.0)],
            out_path=out,
            max_ticks=1,
            clock=lambda: now,
            sleep=_fake_sleep(),
        )
        doc = json.loads(out.read_text(encoding="ascii"))
        assert doc["any_breached"] is False
        assert doc["rows"][0]["status"] == "ok"
