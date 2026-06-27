"""tests.platformkit.selfheal.test_escalation_ladder

Unit tests for escalation_ladder -- streak accumulator + threshold policy.

Acceptance criteria:
  * 1 stale tick  -> level WATCH
  * 3 consecutive stale -> level RESTART_RECOMMENDED with name + streak
  * fresh tick after stale streak -> streak resets to 0, level OK
  * ladder NEVER returns an action/command field in any entry or feed
  * no $ key anywhere in returned dicts

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/selfheal/test_escalation_ladder.py -q
"""
from __future__ import annotations

import pytest

from scripts.platformkit.selfheal.escalation_ladder import (
    LEVEL_OK,
    LEVEL_RESTART_RECOMMENDED,
    LEVEL_WATCH,
    RESTART_THRESHOLD,
    build_feed,
    tick,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_NOW = "2026-06-20T06:00:00Z"

def _stale_row(name: str) -> dict:
    return {"name": name, "severity": "degraded"}

def _down_row(name: str) -> dict:
    return {"name": name, "severity": "down"}

def _fresh_row(name: str) -> dict:
    return {"name": name, "severity": "ok"}

def _no_forbidden_keys(d: dict, path: str = "") -> None:
    """Assert no 'action', 'command', or '$' key anywhere in *d* (recursive)."""
    forbidden = {"action", "command"}
    for k, v in d.items():
        key_str = str(k)
        assert key_str not in forbidden, (
            "Forbidden key '%s' found at %s%s" % (key_str, path, key_str)
        )
        assert "$" not in key_str, (
            "Dollar key '%s' found at %s%s" % (key_str, path, key_str)
        )
        if isinstance(v, dict):
            _no_forbidden_keys(v, path=path + key_str + ".")
        if isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    _no_forbidden_keys(item, path=path + key_str + "[%d]." % i)


# ---------------------------------------------------------------------------
# tick() -- streak accumulation
# ---------------------------------------------------------------------------

class TestTickStreakAccumulation:

    def test_first_stale_tick_gives_watch(self):
        """1 stale tick -> streak=1, level=WATCH."""
        rows = [_stale_row("m1_producer")]
        new_store = tick(rows, {}, now_iso=_NOW)
        assert new_store["m1_producer"]["streak"] == 1
        assert new_store["m1_producer"]["level"] == LEVEL_WATCH

    def test_two_stale_ticks_still_watch(self):
        """2 consecutive stale ticks -> still WATCH (threshold is 3)."""
        rows = [_stale_row("m1_producer")]
        store = tick(rows, {}, now_iso=_NOW)
        store = tick(rows, store, now_iso=_NOW)
        assert store["m1_producer"]["streak"] == 2
        assert store["m1_producer"]["level"] == LEVEL_WATCH

    def test_three_stale_ticks_gives_restart_recommended(self):
        """3 consecutive stale ticks -> RESTART_RECOMMENDED."""
        rows = [_stale_row("m1_producer")]
        store: dict = {}
        for _ in range(RESTART_THRESHOLD):
            store = tick(rows, store, now_iso=_NOW)
        assert store["m1_producer"]["streak"] == RESTART_THRESHOLD
        assert store["m1_producer"]["level"] == LEVEL_RESTART_RECOMMENDED

    def test_down_severity_treated_as_stale(self):
        """Severity 'down' also counts as stale."""
        rows = [_down_row("m6_ingame_loop")]
        store = tick(rows, {}, now_iso=_NOW)
        assert store["m6_ingame_loop"]["streak"] == 1
        assert store["m6_ingame_loop"]["level"] == LEVEL_WATCH

    def test_fresh_tick_resets_streak_to_zero(self):
        """After 3 stale ticks, a fresh tick resets streak to 0 and level to OK."""
        rows_stale = [_stale_row("m4_selfimprove")]
        rows_fresh = [_fresh_row("m4_selfimprove")]
        store: dict = {}
        for _ in range(RESTART_THRESHOLD):
            store = tick(rows_stale, store, now_iso=_NOW)
        assert store["m4_selfimprove"]["level"] == LEVEL_RESTART_RECOMMENDED
        # Now recover
        store = tick(rows_fresh, store, now_iso=_NOW)
        assert store["m4_selfimprove"]["streak"] == 0
        assert store["m4_selfimprove"]["level"] == LEVEL_OK

    def test_streak_not_negative_on_double_fresh(self):
        """Streak never goes negative."""
        rows = [_fresh_row("m5_autonomy_monitor")]
        store = tick(rows, {}, now_iso=_NOW)
        store = tick(rows, store, now_iso=_NOW)
        assert store["m5_autonomy_monitor"]["streak"] == 0

    def test_multiple_daemons_independent(self):
        """Streaks for different daemons are independent."""
        rows = [_stale_row("alpha"), _fresh_row("beta")]
        store = tick(rows, {}, now_iso=_NOW)
        assert store["alpha"]["streak"] == 1
        assert store["beta"]["streak"] == 0

    def test_idempotent_on_repeated_fresh(self):
        """Ticking fresh rows multiple times stays at streak=0."""
        rows = [_fresh_row("m1_paper")]
        store: dict = {}
        for _ in range(5):
            store = tick(rows, store, now_iso=_NOW)
        assert store["m1_paper"]["streak"] == 0
        assert store["m1_paper"]["level"] == LEVEL_OK

    def test_first_stale_at_set_on_first_stale(self):
        """first_stale_at is set on the first stale tick and preserved through streak."""
        rows = [_stale_row("m2_inplay")]
        store = tick(rows, {}, now_iso="2026-06-20T06:00:00Z")
        assert store["m2_inplay"]["first_stale_at"] == "2026-06-20T06:00:00Z"
        # Second stale tick should preserve the original timestamp
        store = tick(rows, store, now_iso="2026-06-20T06:01:00Z")
        assert store["m2_inplay"]["first_stale_at"] == "2026-06-20T06:00:00Z"

    def test_first_stale_at_cleared_on_recovery(self):
        """first_stale_at resets to None when the daemon recovers."""
        rows_stale = [_stale_row("m1_line_daemon")]
        rows_fresh = [_fresh_row("m1_line_daemon")]
        store = tick(rows_stale, {}, now_iso=_NOW)
        assert store["m1_line_daemon"]["first_stale_at"] is not None
        store = tick(rows_fresh, store, now_iso=_NOW)
        assert store["m1_line_daemon"]["first_stale_at"] is None

    def test_tick_does_not_mutate_input_store(self):
        """tick() is non-mutating -- original store is unchanged."""
        rows = [_stale_row("x")]
        orig = {"x": {"streak": 2, "level": LEVEL_WATCH, "first_stale_at": _NOW}}
        new = tick(rows, orig, now_iso=_NOW)
        # Original should still have streak 2
        assert orig["x"]["streak"] == 2
        assert new["x"]["streak"] == 3

    def test_empty_services_returns_empty_store(self):
        """Empty services list returns empty store."""
        store = tick([], {}, now_iso=_NOW)
        assert store == {}

    def test_row_missing_name_is_skipped(self):
        """Rows with empty or missing name are silently skipped."""
        rows = [{"severity": "degraded"}]  # no "name" key
        store = tick(rows, {}, now_iso=_NOW)
        assert store == {}


# ---------------------------------------------------------------------------
# build_feed() -- advisory document
# ---------------------------------------------------------------------------

class TestBuildFeed:

    def test_feed_has_no_action_or_command_key(self):
        """Feed must never contain an 'action' or 'command' key."""
        rows = [_stale_row("m1_producer"), _stale_row("m6_ingame_loop"), _stale_row("m4_selfimprove")]
        store: dict = {}
        for _ in range(3):
            store = tick(rows, store, now_iso=_NOW)
        feed = build_feed(store, generated_at=_NOW)
        _no_forbidden_keys(feed)

    def test_feed_has_no_dollar_key(self):
        """Feed must never contain a $ key."""
        rows = [_stale_row("daemon_x")]
        store = tick(rows, {}, now_iso=_NOW)
        feed = build_feed(store, generated_at=_NOW)
        _no_forbidden_keys(feed)

    def test_feed_restart_recommended_entry_names_daemon(self):
        """A RESTART_RECOMMENDED entry must name the daemon + streak in advice."""
        rows = [_stale_row("target_daemon")]
        store: dict = {}
        for _ in range(RESTART_THRESHOLD):
            store = tick(rows, store, now_iso=_NOW)
        feed = build_feed(store, generated_at=_NOW)
        entry = next(e for e in feed["entries"] if e["name"] == "target_daemon")
        assert entry["level"] == LEVEL_RESTART_RECOMMENDED
        assert "target_daemon" in entry["advice"]
        assert str(RESTART_THRESHOLD) in entry["advice"]

    def test_feed_watch_entry_present_after_one_stale(self):
        """1 stale tick -> WATCH entry in feed."""
        rows = [_stale_row("m7_ingame_refresh")]
        store = tick(rows, {}, now_iso=_NOW)
        feed = build_feed(store, generated_at=_NOW)
        entry = next(e for e in feed["entries"] if e["name"] == "m7_ingame_refresh")
        assert entry["level"] == LEVEL_WATCH
        assert entry["streak"] == 1

    def test_feed_ok_entry_after_recovery(self):
        """After recovery, entry has level=OK and streak=0."""
        store = tick([_stale_row("m8_ci_cadence")], {}, now_iso=_NOW)
        store = tick([_fresh_row("m8_ci_cadence")], store, now_iso=_NOW)
        feed = build_feed(store, generated_at=_NOW)
        entry = next(e for e in feed["entries"] if e["name"] == "m8_ci_cadence")
        assert entry["level"] == LEVEL_OK
        assert entry["streak"] == 0

    def test_feed_has_generated_at(self):
        """build_feed includes generated_at in the document."""
        feed = build_feed({}, generated_at=_NOW)
        assert feed["generated_at"] == _NOW

    def test_feed_has_honest_note(self):
        """build_feed includes an honest_note (calibration, not edge)."""
        feed = build_feed({}, generated_at=_NOW)
        assert "honest_note" in feed
        assert "ADVISORY" in feed["honest_note"]

    def test_feed_empty_store_gives_empty_entries(self):
        """Empty streak store gives empty entries list."""
        feed = build_feed({}, generated_at=_NOW)
        assert feed["entries"] == []

    def test_advice_is_str_not_empty(self):
        """All entries have a non-empty string advice field."""
        rows = [_stale_row("d1"), _fresh_row("d2")]
        store = tick(rows, {}, now_iso=_NOW)
        feed = build_feed(store, generated_at=_NOW)
        for entry in feed["entries"]:
            assert isinstance(entry["advice"], str)
            assert len(entry["advice"]) > 0
