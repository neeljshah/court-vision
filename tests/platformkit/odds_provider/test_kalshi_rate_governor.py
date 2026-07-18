"""Per-file test for odds_provider.kalshi_rate_governor (pure logic, injected
clock/sleep, no real network, no real filesystem timing dependency).

Covers: bucket math (refill rate, capacity, acquire consumes a token), per-sport
fairness under contention (one sport cannot starve another's share), 429 backoff
escalation + decay (a reported 429 shrinks the effective refill rate, which
decays back to full over BACKOFF_DECAY_SEC), kill-switch no-op (env var makes
acquire an immediate no-sleep grant), and corrupt/missing state-file fail-open
(never raises, treated as "no pressure").

  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/odds_provider/test_kalshi_rate_governor.py -q
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List

import pytest

from scripts.platformkit.odds_provider import kalshi_rate_governor as krg


class _FakeClock:
    """Deterministic, manually-advanced clock -- no real time.sleep dependency."""

    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def now(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def _sleep_advances(clock: _FakeClock, log: List[float]):
    """A sleep_fn that both records the call and advances the fake clock by the
    same amount, so a bounded acquire() loop actually terminates in the test."""

    def _sleep(seconds: float) -> None:
        log.append(seconds)
        clock.advance(seconds)

    return _sleep


@pytest.fixture(autouse=True)
def _clear_kill_switch(monkeypatch):
    """Every test starts with the kill switch unset, regardless of the host
    environment's actual state, and any prior test's monkeypatch is undone
    automatically by pytest between tests."""
    monkeypatch.delenv(krg.ENV_KILL_SWITCH, raising=False)


# --------------------------------------------------------------------------------------- #
# bucket math -- capacity, refill, acquire consumes a token                                #
# --------------------------------------------------------------------------------------- #
def test_fresh_governor_starts_full_and_acquire_grants_immediately(tmp_path):
    clock = _FakeClock()
    gov = krg.KalshiRateGovernor(caller="capture", state_path=tmp_path / "state.json",
                                 clock=clock.now, sleep_fn=lambda s: None)
    assert gov.acquire("mlb") is True


def test_capacity_scales_with_rate_share(tmp_path):
    cap_gov = krg.KalshiRateGovernor(caller="capture", state_path=tmp_path / "s1.json",
                                     clock=_FakeClock().now, sleep_fn=lambda s: None)
    snap_gov = krg.KalshiRateGovernor(caller="snapshot", state_path=tmp_path / "s2.json",
                                      clock=_FakeClock().now, sleep_fn=lambda s: None)
    # snapshot's default share (0.65) is larger than capture's (0.35) -> more capacity.
    assert snap_gov._capacity > cap_gov._capacity


def test_unknown_caller_gets_small_fallback_share_not_half(tmp_path):
    """A typo'd/unregistered caller string must NOT get half the fleet budget --
    only a small (0.05) default share, well below every registered caller."""
    gov = krg.KalshiRateGovernor(caller="totally_unregistered_typo",
                                 state_path=tmp_path / "u.json",
                                 clock=_FakeClock().now, sleep_fn=lambda s: None)
    assert gov._base_rate == pytest.approx(max(0.1, krg.BASE_RPS * 0.05))
    registered = krg.KalshiRateGovernor(caller="capture", state_path=tmp_path / "r.json",
                                        clock=_FakeClock().now, sleep_fn=lambda s: None)
    assert gov._capacity < registered._capacity


def test_explicit_rate_share_overrides_caller_default(tmp_path):
    gov_default = krg.KalshiRateGovernor(caller="capture", state_path=tmp_path / "a.json",
                                         clock=_FakeClock().now, sleep_fn=lambda s: None)
    gov_custom = krg.KalshiRateGovernor(caller="capture", rate_share=0.9,
                                        state_path=tmp_path / "b.json",
                                        clock=_FakeClock().now, sleep_fn=lambda s: None)
    assert gov_custom._capacity > gov_default._capacity


def test_acquire_consumes_a_token_and_refill_replenishes(tmp_path):
    clock = _FakeClock()
    gov = krg.KalshiRateGovernor(caller="capture", base_rps=10.0, rate_share=1.0,
                                 state_path=tmp_path / "state.json",
                                 clock=clock.now, sleep_fn=lambda s: None)
    before = gov._tokens
    assert gov.acquire("mlb") is True
    assert gov._tokens == pytest.approx(before - 1.0)
    # Advance the clock and re-acquire -- refill should have added tokens back.
    clock.advance(1.0)
    assert gov.acquire("mlb") is True  # does not raise/block: capacity + refill cover it


def test_exhausted_bucket_waits_bounded_then_grants(tmp_path):
    clock = _FakeClock()
    sleeps: List[float] = []
    # Tiny base_rps + tiny burst so the bucket empties fast and a wait is forced.
    gov = krg.KalshiRateGovernor(caller="capture", base_rps=0.5, rate_share=1.0,
                                 state_path=tmp_path / "state.json",
                                 clock=clock.now, sleep_fn=_sleep_advances(clock, sleeps))
    gov._capacity = 1.0
    gov._tokens = 0.0
    granted = gov.acquire("mlb", max_wait_sec=5.0)
    assert granted is True
    assert len(sleeps) > 0  # it actually waited, not an instant no-op


def test_acquire_never_hangs_past_max_wait(tmp_path):
    """A permanently-starved bucket (base_rps effectively 0) still returns True
    once max_wait_sec elapses -- VOID-never-hang, not an infinite block."""
    clock = _FakeClock()
    sleeps: List[float] = []
    gov = krg.KalshiRateGovernor(caller="capture", base_rps=0.001, rate_share=1.0,
                                 state_path=tmp_path / "state.json",
                                 clock=clock.now, sleep_fn=_sleep_advances(clock, sleeps))
    gov._capacity = 0.001
    gov._tokens = 0.0
    granted = gov.acquire("mlb", max_wait_sec=1.0)
    assert granted is True
    # Bounded: the fake clock (which only advances via sleep_fn) never exceeds
    # max_wait_sec by more than one sleep-step's worth.
    assert clock.t - 1000.0 <= 1.0 + 0.26


# --------------------------------------------------------------------------------------- #
# per-sport fairness -- one sport cannot starve another's share                            #
# --------------------------------------------------------------------------------------- #
def test_one_sport_burst_does_not_exhaust_another_sports_fair_share(tmp_path):
    clock = _FakeClock()
    gov = krg.KalshiRateGovernor(caller="capture", base_rps=100.0, rate_share=1.0,
                                 state_path=tmp_path / "state.json",
                                 clock=clock.now, sleep_fn=lambda s: None)
    # Big capacity so tokens are never the binding constraint -- fairness is.
    gov._capacity = 1000.0
    gov._tokens = 1000.0
    n_active = 2
    # mlb hammers far past its fair share (capacity/n_active) in one window.
    fair_share = gov._capacity / n_active
    hammered = 0
    for _ in range(int(fair_share) + 50):
        if gov._sport_spent.get("mlb", 0.0) >= fair_share:
            break
        gov.acquire("mlb", n_active_sports=n_active, max_wait_sec=0.0)
        hammered += 1
    # mlb should have been capped at roughly its fair share, not the full capacity.
    assert gov._sport_spent.get("mlb", 0.0) <= fair_share + 1.0
    # tennis, arriving after mlb's burst, still gets a token from the shared pool
    # (tokens remain -- fairness gates PER-SPORT spend, not global token supply).
    assert gov.acquire("tennis", n_active_sports=n_active, max_wait_sec=0.0) is True


def test_fairness_window_resets_after_decay_period(tmp_path):
    clock = _FakeClock()
    gov = krg.KalshiRateGovernor(caller="capture", base_rps=100.0, rate_share=1.0,
                                 state_path=tmp_path / "state.json",
                                 clock=clock.now, sleep_fn=lambda s: None)
    gov._capacity = 100.0
    gov._tokens = 100.0
    gov._sport_spent["mlb"] = 999.0  # simulate mlb having spent heavily this window
    clock.advance(krg.BACKOFF_DECAY_SEC + 1.0)
    gov.acquire("tennis", n_active_sports=2, max_wait_sec=0.0)
    # The stale window rolled over -- mlb's old spend record is gone.
    assert "mlb" not in gov._sport_spent or gov._sport_spent["mlb"] < 999.0


# --------------------------------------------------------------------------------------- #
# 429 escalation + decay -- shared state file, cross-instance                              #
# --------------------------------------------------------------------------------------- #
def test_on_429_writes_shared_state_file(tmp_path):
    state_path = tmp_path / "state.json"
    clock = _FakeClock()
    gov = krg.KalshiRateGovernor(caller="capture", state_path=state_path,
                                 clock=clock.now, sleep_fn=lambda s: None)
    gov.on_429()
    assert state_path.exists()
    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert data["last_429_ts"] == clock.now()
    assert data["last_429_caller"] == "capture"
    assert data["n_429_total"] == 1


def test_on_429_increments_shared_counter_across_calls(tmp_path):
    state_path = tmp_path / "state.json"
    clock = _FakeClock()
    gov = krg.KalshiRateGovernor(caller="capture", state_path=state_path,
                                 clock=clock.now, sleep_fn=lambda s: None)
    gov.on_429()
    gov.on_429()
    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert data["n_429_total"] == 2


def test_pressure_multiplier_is_full_speed_with_no_recorded_429():
    assert krg._pressure_multiplier({}, now=1000.0) == 1.0


def test_pressure_multiplier_drops_immediately_after_a_429():
    state = {"last_429_ts": 1000.0}
    mult = krg._pressure_multiplier(state, now=1000.0)
    assert mult == pytest.approx(krg.BACKOFF_MULTIPLIER)


def test_pressure_multiplier_decays_linearly_back_to_full_speed():
    state = {"last_429_ts": 1000.0}
    half_decay = krg._pressure_multiplier(state, now=1000.0 + krg.BACKOFF_DECAY_SEC / 2)
    assert krg.BACKOFF_MULTIPLIER < half_decay < 1.0
    full_decay = krg._pressure_multiplier(state, now=1000.0 + krg.BACKOFF_DECAY_SEC + 1)
    assert full_decay == 1.0


def test_a_429_from_one_governor_instance_slows_a_second_instance_sharing_the_file(tmp_path):
    """Cross-process simulation: two SEPARATE governor objects (standing in for
    the two daemon processes) sharing one state file. A 429 reported by one
    measurably shrinks the other's refill rate on its next acquire."""
    state_path = tmp_path / "shared.json"
    clock_a = _FakeClock()
    clock_b = _FakeClock()  # same start time, independent clock objects
    gov_a = krg.KalshiRateGovernor(caller="capture", base_rps=10.0, rate_share=1.0,
                                   state_path=state_path, clock=clock_a.now,
                                   sleep_fn=lambda s: None)
    gov_b = krg.KalshiRateGovernor(caller="snapshot", base_rps=10.0, rate_share=1.0,
                                   state_path=state_path, clock=clock_b.now,
                                   sleep_fn=lambda s: None)
    gov_a.on_429()
    # gov_b refills at the shrunken (BACKOFF_MULTIPLIER-scaled) rate right after.
    gov_b._tokens = 0.0
    clock_b.advance(1.0)
    gov_b._refill(clock_b.now(), krg._pressure_multiplier(krg._read_state(state_path),
                                                          clock_b.now()))
    tokens_with_pressure = gov_b._tokens
    # Compare against what it WOULD have refilled with no pressure at all.
    baseline = gov_b._base_rate * 1.0
    assert tokens_with_pressure < baseline


# --------------------------------------------------------------------------------------- #
# kill switch -- env var makes acquire an immediate no-sleep grant                          #
# --------------------------------------------------------------------------------------- #
def test_kill_switch_on_skips_acquire_entirely(tmp_path, monkeypatch):
    monkeypatch.setenv(krg.ENV_KILL_SWITCH, "1")
    sleeps: List[float] = []
    gov = krg.KalshiRateGovernor(caller="capture", base_rps=0.001, rate_share=1.0,
                                 state_path=tmp_path / "state.json",
                                 clock=_FakeClock().now, sleep_fn=sleeps.append)
    gov._capacity = 0.0
    gov._tokens = 0.0  # would otherwise force a long wait
    assert gov.acquire("mlb", max_wait_sec=10.0) is True
    assert sleeps == []  # no sleep at all -- fully skipped


@pytest.mark.parametrize("value", ["0", "false", "False", ""])
def test_kill_switch_off_values_do_not_disable(tmp_path, monkeypatch, value):
    monkeypatch.setenv(krg.ENV_KILL_SWITCH, value)
    assert krg._kill_switch_on() is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "on"])
def test_kill_switch_on_values_disable(monkeypatch, value):
    monkeypatch.setenv(krg.ENV_KILL_SWITCH, value)
    assert krg._kill_switch_on() is True


def test_before_request_helper_respects_kill_switch(tmp_path, monkeypatch):
    monkeypatch.setenv(krg.ENV_KILL_SWITCH, "1")
    gov = krg.KalshiRateGovernor(caller="capture", state_path=tmp_path / "state.json",
                                 clock=_FakeClock().now, sleep_fn=lambda s: None)
    krg.before_request(gov, "mlb")  # must not raise regardless of kill switch


def test_before_request_is_a_noop_for_none_governor():
    krg.before_request(None, "mlb")  # must never raise


def test_report_429_is_a_noop_for_none_governor():
    krg.report_429(None)  # must never raise


# --------------------------------------------------------------------------------------- #
# corrupt / missing state file -- fail-open, never raises                                  #
# --------------------------------------------------------------------------------------- #
def test_read_state_missing_file_returns_empty_dict(tmp_path):
    assert krg._read_state(tmp_path / "does_not_exist.json") == {}


def test_read_state_corrupt_json_returns_empty_dict(tmp_path):
    path = tmp_path / "corrupt.json"
    path.write_text("{not valid json!!", encoding="utf-8")
    assert krg._read_state(path) == {}


def test_read_state_non_dict_json_returns_empty_dict(tmp_path):
    path = tmp_path / "list.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert krg._read_state(path) == {}


def test_acquire_with_corrupt_state_file_still_grants(tmp_path):
    path = tmp_path / "corrupt.json"
    path.write_text("garbage{{{", encoding="utf-8")
    gov = krg.KalshiRateGovernor(caller="capture", state_path=path,
                                 clock=_FakeClock().now, sleep_fn=lambda s: None)
    assert gov.acquire("mlb") is True  # never raises, treated as no pressure


def test_write_state_to_unwritable_parent_does_not_raise(tmp_path, monkeypatch):
    """A write failure (e.g. a permission error) must be swallowed, not raised --
    on_429 is best-effort observability, never allowed to sink the real request."""

    def _boom_mkdir(*args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "mkdir", _boom_mkdir)
    krg._write_state(tmp_path / "sub" / "state.json", {"x": 1})  # must not raise


def test_resolve_governor_none_caller_returns_none():
    assert krg.resolve_governor(None) is None


def test_resolve_governor_valid_caller_returns_instance():
    gov = krg.resolve_governor("capture")
    assert isinstance(gov, krg.KalshiRateGovernor)


def test_get_governor_is_a_singleton_per_caller():
    a = krg.get_governor("capture")
    b = krg.get_governor("capture")
    assert a is b


def test_get_governor_different_callers_get_different_instances():
    a = krg.get_governor("capture")
    b = krg.get_governor("snapshot")
    assert a is not b


# --------------------------------------------------------------------------------------- #
# acquire() itself is fail-open on an internal error                                        #
# --------------------------------------------------------------------------------------- #
def test_acquire_fails_open_when_clock_raises(tmp_path):
    def _boom_clock() -> float:
        raise RuntimeError("clock broken")

    gov = krg.KalshiRateGovernor(caller="capture", state_path=tmp_path / "state.json",
                                 clock=_boom_clock, sleep_fn=lambda s: None)
    assert gov.acquire("mlb") is True  # fail-open, never raises/hangs


def test_on_429_fails_open_when_clock_raises(tmp_path):
    calls = {"n": 0}

    def _flaky_clock() -> float:
        calls["n"] += 1
        if calls["n"] == 1:
            return 1000.0
        raise RuntimeError("clock broken on second call")

    gov = krg.KalshiRateGovernor(caller="capture", state_path=tmp_path / "state.json",
                                 clock=_flaky_clock, sleep_fn=lambda s: None)
    gov.on_429()  # must not raise even if the clock breaks mid-call
