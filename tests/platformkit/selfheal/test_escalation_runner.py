"""tests.platformkit.selfheal.test_escalation_runner -- unit tests for escalation_runner tick I/O + run loop.

Acceptance criteria:
  * tick() reads autonomy_status services[], updates streaks, writes feed + streaks atomically
  * runner heartbeat component is m16_escalation
  * feed written to data/frontend/ops/escalation_feed.json atomically (tmp + replace)
  * idempotent on repeat tick with same input
  * never restarts/mutates specs/raises
  * no $ key in any output

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/selfheal/test_escalation_runner.py -q
"""
from __future__ import annotations

import json
import pathlib
import time

import pytest

from scripts.platformkit.selfheal.escalation_runner import (
    HEARTBEAT_COMPONENT,
    tick,
    run,
)
from scripts.platformkit.selfheal.escalation_ladder import (
    LEVEL_OK,
    LEVEL_WATCH,
    LEVEL_RESTART_RECOMMENDED,
    RESTART_THRESHOLD,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mk_autonomy(tmp_path: pathlib.Path, services: list) -> pathlib.Path:
    """Write a minimal autonomy_status.json and return its path."""
    doc = {"services": services}
    p = tmp_path / "autonomy_status.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def _read_feed(feed_path: pathlib.Path) -> dict:
    return json.loads(feed_path.read_text(encoding="utf-8"))


def _read_streaks(streaks_path: pathlib.Path) -> dict:
    return json.loads(streaks_path.read_text(encoding="utf-8"))


def _no_dollar_key(d: object, path: str = "") -> None:
    if isinstance(d, dict):
        for k, v in d.items():
            assert "$" not in str(k), "Dollar key at %s%s" % (path, k)
            _no_dollar_key(v, path=path + str(k) + ".")
    elif isinstance(d, list):
        for i, item in enumerate(d):
            _no_dollar_key(item, path=path + "[%d]." % i)


_TS = 1_800_000_000.0  # fixed epoch for tests


def _stale_svc(name: str) -> dict:
    return {"name": name, "severity": "degraded"}


def _fresh_svc(name: str) -> dict:
    return {"name": name, "severity": "ok"}


# ---------------------------------------------------------------------------
# tick() I/O tests
# ---------------------------------------------------------------------------

class TestTickIO:

    def test_tick_creates_feed_file(self, tmp_path):
        """tick() must create escalation_feed.json."""
        ap = _mk_autonomy(tmp_path, [_stale_svc("m1_producer")])
        sp = tmp_path / "streaks.json"
        fp = tmp_path / "escalation_feed.json"
        tick(now=_TS, autonomy_path=ap, streaks_path=sp, feed_path=fp)
        assert fp.exists(), "feed file not created"

    def test_tick_creates_streaks_file(self, tmp_path):
        """tick() must persist streaks to the streaks path."""
        ap = _mk_autonomy(tmp_path, [_stale_svc("m4_selfimprove")])
        sp = tmp_path / "streaks.json"
        fp = tmp_path / "escalation_feed.json"
        tick(now=_TS, autonomy_path=ap, streaks_path=sp, feed_path=fp)
        assert sp.exists(), "streaks file not created"

    def test_one_stale_tick_gives_watch_in_feed(self, tmp_path):
        """1 stale tick -> WATCH level in feed entry."""
        ap = _mk_autonomy(tmp_path, [_stale_svc("m1_producer")])
        sp = tmp_path / "streaks.json"
        fp = tmp_path / "escalation_feed.json"
        tick(now=_TS, autonomy_path=ap, streaks_path=sp, feed_path=fp)
        feed = _read_feed(fp)
        entry = next(e for e in feed["entries"] if e["name"] == "m1_producer")
        assert entry["level"] == LEVEL_WATCH

    def test_three_stale_ticks_gives_restart_recommended(self, tmp_path):
        """3 consecutive stale ticks -> RESTART_RECOMMENDED in feed, names daemon."""
        ap = _mk_autonomy(tmp_path, [_stale_svc("m6_ingame_loop")])
        sp = tmp_path / "streaks.json"
        fp = tmp_path / "escalation_feed.json"
        for _ in range(RESTART_THRESHOLD):
            tick(now=_TS, autonomy_path=ap, streaks_path=sp, feed_path=fp)
        feed = _read_feed(fp)
        entry = next(e for e in feed["entries"] if e["name"] == "m6_ingame_loop")
        assert entry["level"] == LEVEL_RESTART_RECOMMENDED
        assert entry["streak"] >= RESTART_THRESHOLD
        assert "m6_ingame_loop" in entry["advice"]

    def test_fresh_tick_resets_streak_in_feed(self, tmp_path):
        """After 3 stale ticks, a fresh tick resets to streak=0 + level=OK."""
        daemon = "m4_selfimprove"
        ap_stale = _mk_autonomy(tmp_path, [_stale_svc(daemon)])
        sp = tmp_path / "streaks.json"
        fp = tmp_path / "escalation_feed.json"
        for _ in range(RESTART_THRESHOLD):
            tick(now=_TS, autonomy_path=ap_stale, streaks_path=sp, feed_path=fp)
        # Confirm RESTART_RECOMMENDED
        feed = _read_feed(fp)
        entry = next(e for e in feed["entries"] if e["name"] == daemon)
        assert entry["level"] == LEVEL_RESTART_RECOMMENDED
        # Now recover
        ap_fresh = _mk_autonomy(tmp_path, [_fresh_svc(daemon)])
        tick(now=_TS + 60, autonomy_path=ap_fresh, streaks_path=sp, feed_path=fp)
        feed = _read_feed(fp)
        entry = next(e for e in feed["entries"] if e["name"] == daemon)
        assert entry["streak"] == 0
        assert entry["level"] == LEVEL_OK

    def test_feed_has_no_action_or_command_key(self, tmp_path):
        """Feed must never have action/command keys."""
        ap = _mk_autonomy(tmp_path, [_stale_svc("d1"), _stale_svc("d2"), _stale_svc("d3")])
        sp = tmp_path / "streaks.json"
        fp = tmp_path / "escalation_feed.json"
        for _ in range(3):
            tick(now=_TS, autonomy_path=ap, streaks_path=sp, feed_path=fp)
        feed = _read_feed(fp)
        for entry in feed.get("entries", []):
            assert "action" not in entry, "forbidden 'action' key in entry"
            assert "command" not in entry, "forbidden 'command' key in entry"

    def test_feed_has_no_dollar_key(self, tmp_path):
        """No $ key anywhere in feed."""
        ap = _mk_autonomy(tmp_path, [_stale_svc("m1_paper")])
        sp = tmp_path / "streaks.json"
        fp = tmp_path / "escalation_feed.json"
        tick(now=_TS, autonomy_path=ap, streaks_path=sp, feed_path=fp)
        feed = _read_feed(fp)
        _no_dollar_key(feed)

    def test_idempotent_on_repeated_tick_same_input(self, tmp_path):
        """Repeated ticks with the same fresh input produce the same streak=0 output."""
        ap = _mk_autonomy(tmp_path, [_fresh_svc("m5_autonomy_monitor")])
        sp = tmp_path / "streaks.json"
        fp = tmp_path / "escalation_feed.json"
        tick(now=_TS, autonomy_path=ap, streaks_path=sp, feed_path=fp)
        tick(now=_TS + 60, autonomy_path=ap, streaks_path=sp, feed_path=fp)
        tick(now=_TS + 120, autonomy_path=ap, streaks_path=sp, feed_path=fp)
        feed = _read_feed(fp)
        entry = next(e for e in feed["entries"] if e["name"] == "m5_autonomy_monitor")
        assert entry["streak"] == 0
        assert entry["level"] == LEVEL_OK

    def test_missing_autonomy_file_does_not_raise(self, tmp_path):
        """Missing autonomy_status.json must not raise -- returns empty feed."""
        sp = tmp_path / "streaks.json"
        fp = tmp_path / "escalation_feed.json"
        ap = tmp_path / "nonexistent.json"
        result = tick(now=_TS, autonomy_path=ap, streaks_path=sp, feed_path=fp)
        assert isinstance(result, dict)

    def test_corrupt_autonomy_file_does_not_raise(self, tmp_path):
        """Corrupt autonomy_status.json must not raise."""
        ap = tmp_path / "autonomy_status.json"
        ap.write_text("this is not json", encoding="utf-8")
        sp = tmp_path / "streaks.json"
        fp = tmp_path / "escalation_feed.json"
        result = tick(now=_TS, autonomy_path=ap, streaks_path=sp, feed_path=fp)
        assert isinstance(result, dict)

    def test_feed_written_atomically_no_tmp_leftover(self, tmp_path):
        """After tick(), there should be no .tmp leftover for the feed file."""
        ap = _mk_autonomy(tmp_path, [_stale_svc("m1_producer")])
        sp = tmp_path / "streaks.json"
        fp = tmp_path / "escalation_feed.json"
        tick(now=_TS, autonomy_path=ap, streaks_path=sp, feed_path=fp)
        tmp_file = fp.with_suffix(fp.suffix + ".tmp")
        assert not tmp_file.exists(), ".tmp file left after atomic write"

    def test_streaks_persist_across_ticks(self, tmp_path):
        """Streak increments are durable across tick() calls (read from disk)."""
        daemon = "m2_inplay"
        ap = _mk_autonomy(tmp_path, [_stale_svc(daemon)])
        sp = tmp_path / "streaks.json"
        fp = tmp_path / "escalation_feed.json"
        tick(now=_TS, autonomy_path=ap, streaks_path=sp, feed_path=fp)
        tick(now=_TS + 60, autonomy_path=ap, streaks_path=sp, feed_path=fp)
        streaks = _read_streaks(sp)
        assert streaks[daemon]["streak"] == 2

    def test_heartbeat_component_name(self):
        """Heartbeat component must be m16_escalation."""
        assert HEARTBEAT_COMPONENT == "m16_escalation"


# ---------------------------------------------------------------------------
# run() loop tests
# ---------------------------------------------------------------------------

class TestRunLoop:

    def test_run_max_ticks_returns_count(self, tmp_path):
        """run() with max_ticks=3 executes exactly 3 ticks and returns 3."""
        ap = _mk_autonomy(tmp_path, [_fresh_svc("m1_paper")])
        sp = tmp_path / "streaks.json"
        fp = tmp_path / "escalation_feed.json"
        count = run(
            max_ticks=3,
            autonomy_path=ap,
            streaks_path=sp,
            feed_path=fp,
            clock=lambda: _TS,
            sleep=lambda _s: None,
        )
        assert count == 3

    def test_run_does_not_raise(self, tmp_path):
        """run() must not raise under any circumstance."""
        ap = tmp_path / "no_such_file.json"
        sp = tmp_path / "streaks.json"
        fp = tmp_path / "feed.json"
        # Should complete without exception even with missing source
        count = run(
            max_ticks=2,
            autonomy_path=ap,
            streaks_path=sp,
            feed_path=fp,
            clock=lambda: _TS,
            sleep=lambda _s: None,
        )
        assert isinstance(count, int)

    def test_run_should_stop_honored(self, tmp_path):
        """should_stop callback stops the loop early."""
        ap = _mk_autonomy(tmp_path, [_fresh_svc("m8_ci_cadence")])
        sp = tmp_path / "streaks.json"
        fp = tmp_path / "feed.json"
        calls = [0]

        def stop():
            calls[0] += 1
            return calls[0] >= 2

        count = run(
            autonomy_path=ap,
            streaks_path=sp,
            feed_path=fp,
            clock=lambda: _TS,
            sleep=lambda _s: None,
            should_stop=stop,
        )
        # Loop checks should_stop BEFORE tick, so should_stop()==True on call 2 -> 1 tick ran
        assert count == 1

    def test_run_builds_restart_recommended_after_threshold(self, tmp_path):
        """run() for RESTART_THRESHOLD ticks produces RESTART_RECOMMENDED feed."""
        daemon = "m7_ingame_refresh"
        ap = _mk_autonomy(tmp_path, [_stale_svc(daemon)])
        sp = tmp_path / "streaks.json"
        fp = tmp_path / "feed.json"
        tick_counter = [0]

        def fake_clock():
            return _TS + tick_counter[0] * 60

        def fake_sleep(_s):
            tick_counter[0] += 1

        run(
            max_ticks=RESTART_THRESHOLD,
            autonomy_path=ap,
            streaks_path=sp,
            feed_path=fp,
            clock=fake_clock,
            sleep=fake_sleep,
        )
        feed = _read_feed(fp)
        entry = next(e for e in feed["entries"] if e["name"] == daemon)
        assert entry["level"] == LEVEL_RESTART_RECOMMENDED
