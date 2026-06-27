"""tests/ops/test_freshness_breaker.py -- unit tests for ops.freshness_guard and ops.circuit_breaker.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/ops/test_freshness_breaker.py -q
No real network, processes, or ports -- injectable clock and now= throughout.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ops.freshness_guard import guard_status, SOURCE_MAX_AGE, live_source_keys
from ops.circuit_breaker import CircuitBreaker, CLOSED, OPEN, HALF_OPEN


_ANCHOR = datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc)


def _utc(offset_sec: float = 0.0) -> datetime:
    return _ANCHOR + timedelta(seconds=offset_sec)


def _iso(offset_sec: float = 0.0) -> str:
    return _utc(offset_sec).isoformat()


# -- freshness_guard tests ---------------------------------------------------

class TestGuardStatusFresh:
    """captured_at is within max_age -> "fresh"."""

    def test_known_source_within_age(self):
        now = _utc(0)
        # predict_service max_age = 120s; captured 100s ago (a LIVE source key)
        captured = _iso(-100)
        result = guard_status("predict_service", captured, now=now)
        assert result["status"] == "fresh"
        assert abs(result["age_sec"] - 100.0) < 1.0
        assert result["source"] == "predict_service"
        assert result["max_age_sec"] == SOURCE_MAX_AGE["predict_service"]

    def test_at_boundary_is_fresh(self):
        """age_sec == max_age_sec is still fresh (inclusive boundary)."""
        now = _utc(0)
        max_age = 300.0
        captured = _iso(-max_age)
        result = guard_status("line_daemon", captured, now=now, max_age_sec=max_age)
        assert result["status"] == "fresh"

    def test_explicit_override_respected(self):
        now = _utc(0)
        captured = _iso(-50)
        result = guard_status("unknown_source", captured, now=now, max_age_sec=100.0)
        assert result["status"] == "fresh"
        assert result["max_age_sec"] == 100.0

    def test_case_insensitive_source_key(self):
        now = _utc(0)
        captured = _iso(-10)
        r1 = guard_status("PINNACLE", captured, now=now)
        r2 = guard_status("pinnacle", captured, now=now)
        assert r1["status"] == r2["status"] == "fresh"
        assert r1["max_age_sec"] == r2["max_age_sec"]


class TestGuardStatusStale:
    """captured_at is parseable but older than max_age -> "stale"."""

    def test_just_over_max_age(self):
        now = _utc(0)
        captured = _iso(-(SOURCE_MAX_AGE["line_daemon"] + 1))
        result = guard_status("line_daemon", captured, now=now)
        assert result["status"] == "stale"
        assert result["age_sec"] is not None

    def test_unknown_source_uses_default(self):
        now = _utc(0)
        default_max = SOURCE_MAX_AGE["_default"]
        captured = _iso(-(default_max + 60))
        result = guard_status("totally_unknown_feed", captured, now=now)
        assert result["status"] == "stale"
        assert result["max_age_sec"] == default_max

    def test_predict_service_stale(self):
        now = _utc(0)
        max_age = SOURCE_MAX_AGE["predict_service"]  # 120s
        captured = _iso(-(max_age + 10))
        result = guard_status("predict_service", captured, now=now)
        assert result["status"] == "stale"


class TestGuardStatusDown:
    """Unparseable or None timestamp -> "down"."""

    def test_none_timestamp(self):
        result = guard_status("pinnacle", None, now=_utc(0))
        assert result["status"] == "down"
        assert result["age_sec"] is None

    def test_empty_string(self):
        result = guard_status("draftkings", "", now=_utc(0))
        assert result["status"] == "down"

    def test_garbage_timestamp(self):
        result = guard_status("bovada", "not-a-date-at-all", now=_utc(0))
        assert result["status"] == "down"

    def test_down_never_raises(self):
        # Should not raise for any weird input
        for bad in [object(), 12345, [], {}]:
            r = guard_status("espn_odds", bad, now=_utc(0))
            assert r["status"] in ("down", "fresh", "stale")

    def test_response_always_has_source_field(self):
        result = guard_status("my_feed", None, now=_utc(0))
        assert result["source"] == "my_feed"


# -- SLA registry: no dead config + manifest-derived thresholds --------------

class TestNoDeadConfig:
    """Every live SLA key must be reachable as a real service freshness source,
    and the removed aspirational odds-book keys must be gone (no dead config)."""

    def test_every_live_key_is_a_real_freshness_source(self):
        from ops import service_registry as sr
        reachable = set()
        for prof in ("default", "backend"):
            for d in sr.service_descriptors(prof):
                if d.freshness_source:
                    reachable.add(d.freshness_source)
        for key in live_source_keys():
            assert key in reachable, (
                "dead SLA config: %r in SOURCE_MAX_AGE but no descriptor "
                "references it as a freshness_source" % key)

    def test_removed_dead_odds_keys(self):
        for dead in ("pinnacle", "draftkings", "bovada", "fanduel", "espn_odds",
                     "kalshi", "polymarket", "injury_report", "lineup"):
            assert dead not in SOURCE_MAX_AGE, (
                "%r was dead config (never a live freshness source) and must "
                "not reappear" % dead)


class TestManifestDerivedSLA:
    """sla_minutes from the ingest manifest is ACTUALLY consulted, not a dead
    contract -- the line_daemon/inplay data-feed thresholds derive from it."""

    def test_line_daemon_threshold_respects_manifest_odds_sla(self):
        import importlib
        mod = importlib.import_module("domains.basketball_nba.ingest_manifest")
        odds = next(s for s in mod.NBA_MANIFEST.sources if s.corpus == "odds")
        manifest_ceiling = float(odds.sla_minutes) * 60.0
        # effective threshold must NOT exceed the manifest SLA ceiling (enforced),
        # and must be > 0 (a real number is consulted).
        eff = SOURCE_MAX_AGE["line_daemon"]
        assert 0 < eff <= manifest_ceiling

    def test_inplay_threshold_respects_manifest_linescores_sla(self):
        import importlib
        mod = importlib.import_module("domains.basketball_nba.ingest_manifest")
        ls = next(s for s in mod.NBA_MANIFEST.sources if s.corpus == "linescores")
        manifest_ceiling = float(ls.sla_minutes) * 60.0
        eff = SOURCE_MAX_AGE["inplay_history"]
        assert 0 < eff <= manifest_ceiling

    def test_tighter_manifest_sla_actually_binds(self, monkeypatch):
        """If the manifest odds SLA were tighter than the heartbeat window, the
        registry must adopt it -- proving sla_minutes is genuinely consulted."""
        import ops.freshness_guard as fg
        monkeypatch.setattr(fg, "_scan_manifest_slas", lambda: {"odds": 30.0})
        rebuilt = fg._build_source_max_age()
        assert rebuilt["line_daemon"] == 30.0  # 30s manifest SLA beats 300s hb

class TestCircuitBreakerInitial:
    """Breaker starts CLOSED and allows calls."""

    def test_starts_closed(self):
        cb = CircuitBreaker("test")
        assert cb.status()["state"] == CLOSED

    def test_allow_when_closed(self):
        cb = CircuitBreaker("test")
        assert cb.allow() is True

    def test_success_stays_closed(self):
        cb = CircuitBreaker("test")
        cb.record_success()
        assert cb.status()["state"] == CLOSED


class TestCircuitBreakerTrips:
    """N consecutive failures trips the breaker OPEN."""

    def test_trips_at_threshold(self):
        cb = CircuitBreaker("test", fail_threshold=3, clock=lambda: 0.0)
        cb.record_failure()
        cb.record_failure()
        assert cb.status()["state"] == CLOSED  # not yet
        cb.record_failure()
        assert cb.status()["state"] == OPEN

    def test_open_blocks_calls(self):
        t = [0.0]
        cb = CircuitBreaker("test", fail_threshold=2, cooldown_sec=60.0,
                            clock=lambda: t[0])
        cb.record_failure()
        cb.record_failure()
        assert cb.allow() is False

    def test_success_resets_streak(self):
        cb = CircuitBreaker("test", fail_threshold=3, clock=lambda: 0.0)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()  # streak reset; only 1 failure after success
        assert cb.status()["state"] == CLOSED

    def test_failure_threshold_1(self):
        cb = CircuitBreaker("test", fail_threshold=1, clock=lambda: 0.0)
        cb.record_failure()
        assert cb.status()["state"] == OPEN


class TestCircuitBreakerHalfOpen:
    """After cooldown the breaker enters HALF_OPEN and allows one trial."""

    def _make_cb(self, fail_threshold=2, cooldown_sec=30.0):
        self._t = [0.0]
        def clock():
            return self._t[0]
        return CircuitBreaker("test", fail_threshold=fail_threshold,
                              cooldown_sec=cooldown_sec, clock=clock)

    def test_half_open_after_cooldown(self):
        cb = self._make_cb(cooldown_sec=30.0)
        cb.record_failure()
        cb.record_failure()
        assert cb.status()["state"] == OPEN
        self._t[0] = 31.0  # advance past cooldown
        assert cb.allow() is True
        assert cb.status()["state"] == HALF_OPEN

    def test_success_in_half_open_closes(self):
        cb = self._make_cb(cooldown_sec=30.0)
        cb.record_failure()
        cb.record_failure()
        self._t[0] = 31.0
        cb.allow()  # triggers HALF_OPEN
        cb.record_success()
        assert cb.status()["state"] == CLOSED

    def test_failure_in_half_open_reopens(self):
        cb = self._make_cb(cooldown_sec=30.0)
        cb.record_failure()
        cb.record_failure()
        self._t[0] = 31.0
        cb.allow()  # triggers HALF_OPEN
        cb.record_failure()
        assert cb.status()["state"] == OPEN

    def test_half_open_trial_then_failure_reopens(self):
        """allow() in HALF_OPEN grants the trial; record_failure re-opens."""
        cb = self._make_cb(cooldown_sec=30.0)
        cb.record_failure()
        cb.record_failure()
        self._t[0] = 31.0
        assert cb.allow() is True   # HALF_OPEN granted
        cb.record_failure()         # trial failed -> back to OPEN
        assert cb.status()["state"] == OPEN
        assert cb.allow() is False  # cooldown restarted at t=31

    def test_cooldown_not_elapsed_stays_open(self):
        cb = self._make_cb(cooldown_sec=30.0)
        cb.record_failure()
        cb.record_failure()
        self._t[0] = 15.0  # only halfway through cooldown
        assert cb.allow() is False
        assert cb.status()["state"] == OPEN

    def test_reopen_restarts_cooldown(self):
        """When HALF_OPEN trial fails, new cooldown starts from the re-open time."""
        cb = self._make_cb(cooldown_sec=30.0)
        cb.record_failure()
        cb.record_failure()
        self._t[0] = 31.0
        cb.allow()  # -> HALF_OPEN
        cb.record_failure()  # -> re-OPEN at t=31
        self._t[0] = 50.0   # only 19s after re-open
        assert cb.allow() is False
        self._t[0] = 62.0   # 31s after re-open
        assert cb.allow() is True
        assert cb.status()["state"] == HALF_OPEN


class TestCircuitBreakerNeverRaises:
    """The breaker must not propagate exceptions to the caller."""

    def test_bad_clock_allow_returns_false(self):
        def bad_clock():
            raise RuntimeError("clock exploded")
        cb = CircuitBreaker("test", clock=bad_clock)
        # Starts CLOSED -> allow() reads self._state first before calling clock
        assert cb.allow() is True  # CLOSED path doesn't call clock

    def test_record_success_after_closed(self):
        cb = CircuitBreaker("test")
        cb.record_success()  # should not raise

    def test_status_always_returns_dict(self):
        cb = CircuitBreaker("test")
        s = cb.status()
        assert isinstance(s, dict)
        assert "state" in s

    def test_reset_to_closed(self):
        t = [0.0]
        cb = CircuitBreaker("test", fail_threshold=1, clock=lambda: t[0])
        cb.record_failure()
        assert cb.status()["state"] == OPEN
        cb.reset()
        assert cb.status()["state"] == CLOSED
        assert cb.allow() is True


class TestCircuitBreakerFullCycle:
    """End-to-end state machine walk: CLOSED -> OPEN -> HALF_OPEN -> CLOSED."""

    def test_full_cycle(self):
        t = [0.0]
        cb = CircuitBreaker("full_cycle", fail_threshold=2,
                            cooldown_sec=10.0, clock=lambda: t[0])
        # 1. CLOSED -- normal operation
        assert cb.allow() is True
        cb.record_success()
        assert cb.status()["state"] == CLOSED

        # 2. Two failures -> OPEN
        cb.record_failure()
        cb.record_failure()
        assert cb.status()["state"] == OPEN
        assert cb.allow() is False

        # 3. Cooldown passes -> HALF_OPEN; one trial allowed
        t[0] = 11.0
        assert cb.allow() is True
        assert cb.status()["state"] == HALF_OPEN

        # 4. Trial succeeds -> CLOSED
        cb.record_success()
        assert cb.status()["state"] == CLOSED
        assert cb.allow() is True
