"""Per-file tests for prop_circuit_breaker.

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/odds_provider/test_prop_circuit_breaker.py -q

Acceptance criteria:
  1. 3 consecutive failures -> circuit OPENS (is_open True).
  2. Fewer than threshold failures -> circuit stays CLOSED.
  3. A success resets the streak (CLOSES the circuit / clears opened_since).
  4. Persists across a fresh state load (same state_path, new call) -- simulates
     surviving a process restart.
  5. Cooldown elapses -> half-open (is_open False) so a real attempt can retry.
  6. filter_providers splits kept/skipped, NEVER silently drops (skipped carries
     reason=SKIPPED_CIRCUIT + since + last_reason).
  7. Corrupt/missing state file -> fail OPEN (never raises, treated as never-failed).
  8. Atomic write: state file exists and round-trips exact values.
"""
from __future__ import annotations

import json

import pytest

from scripts.platformkit.odds_provider import prop_circuit_breaker as pcb


class _FakeProvider:
    def __init__(self, name: str) -> None:
        self.name = name


@pytest.fixture
def state_path(tmp_path):
    return tmp_path / "circuit_state.json"


def test_three_consecutive_failures_opens_circuit(state_path):
    clock = [1000.0]
    for _ in range(3):
        pcb.record_result("prizepicks", False, reason="403", state_path=state_path,
                          now=lambda: clock[0])
    open_now, entry = pcb.is_open("prizepicks", state_path=state_path, now=lambda: clock[0])
    assert open_now is True
    assert entry["consecutive_failures"] == 3
    assert entry["opened_since"] == 1000.0


def test_below_threshold_stays_closed(state_path):
    pcb.record_result("betmgm", False, reason="400", state_path=state_path, now=lambda: 1.0)
    pcb.record_result("betmgm", False, reason="400", state_path=state_path, now=lambda: 2.0)
    open_now, entry = pcb.is_open("betmgm", state_path=state_path, now=lambda: 3.0)
    assert open_now is False
    assert entry is None


def test_success_resets_streak_and_closes(state_path):
    pcb.record_result("fanduel", False, reason="timeout", state_path=state_path, now=lambda: 1.0)
    pcb.record_result("fanduel", False, reason="timeout", state_path=state_path, now=lambda: 2.0)
    pcb.record_result("fanduel", False, reason="timeout", state_path=state_path, now=lambda: 3.0)
    open_now, _ = pcb.is_open("fanduel", state_path=state_path, now=lambda: 3.5)
    assert open_now is True
    # a recovery success closes it
    entry = pcb.record_result("fanduel", True, state_path=state_path, now=lambda: 4.0)
    assert entry["consecutive_failures"] == 0
    assert entry["opened_since"] is None
    open_now, _ = pcb.is_open("fanduel", state_path=state_path, now=lambda: 5.0)
    assert open_now is False


def test_state_persists_across_fresh_load(state_path):
    for i in range(3):
        pcb.record_result("prizepicks", False, reason="403", state_path=state_path,
                          now=lambda: 100.0 + i)
    # Simulate a restart: a brand-new call re-reads from disk, no shared in-memory state.
    open_now, entry = pcb.is_open("prizepicks", state_path=state_path, now=lambda: 200.0)
    assert open_now is True
    assert entry["consecutive_failures"] == 3
    raw = json.loads(state_path.read_text(encoding="utf-8"))
    assert raw["prizepicks"]["consecutive_failures"] == 3


def test_cooldown_elapses_to_half_open(state_path):
    for i in range(3):
        pcb.record_result("betmgm", False, reason="400", state_path=state_path,
                          now=lambda i=i: 0.0 + i)
    open_now, _ = pcb.is_open("betmgm", state_path=state_path, now=lambda: 100.0,
                              cooldown_sec=6 * 3600.0)
    assert open_now is True
    # past cooldown -> half-open
    open_now, entry = pcb.is_open("betmgm", state_path=state_path,
                                  now=lambda: 6 * 3600.0 + 101.0, cooldown_sec=6 * 3600.0)
    assert open_now is False
    assert entry is None


def test_filter_providers_splits_and_records_reason(state_path):
    for i in range(3):
        pcb.record_result("prizepicks", False, reason="403 walled", state_path=state_path,
                          now=lambda i=i: 10.0 + i)
    providers = [_FakeProvider("betmgm"), _FakeProvider("prizepicks"), _FakeProvider("fanduel")]
    kept, skipped = pcb.filter_providers(providers, state_path=state_path, now=lambda: 20.0)
    kept_names = [p.name for p in kept]
    assert kept_names == ["betmgm", "fanduel"]
    assert len(skipped) == 1
    assert skipped[0]["provider"] == "prizepicks"
    assert skipped[0]["reason"] == "SKIPPED_CIRCUIT"
    assert skipped[0]["since"] == 12.0  # opened_since = ts of the 3rd (threshold-hit) failure
    assert skipped[0]["last_reason"] == "403 walled"
    assert skipped[0]["consecutive_failures"] == 3


def test_filter_providers_never_drops_silently_all_open(state_path):
    for name in ("betmgm", "prizepicks"):
        for i in range(3):
            pcb.record_result(name, False, reason="dead", state_path=state_path,
                              now=lambda i=i: 10.0 + i)
    providers = [_FakeProvider("betmgm"), _FakeProvider("prizepicks")]
    kept, skipped = pcb.filter_providers(providers, state_path=state_path, now=lambda: 20.0)
    assert kept == []
    assert len(skipped) == 2
    assert {s["provider"] for s in skipped} == {"betmgm", "prizepicks"}


def test_missing_state_file_fails_open(tmp_path):
    missing = tmp_path / "does_not_exist" / "state.json"
    open_now, entry = pcb.is_open("anything", state_path=missing, now=lambda: 1.0)
    assert open_now is False
    assert entry is None


def test_corrupt_state_file_fails_open(state_path):
    state_path.write_text("{ not valid json", encoding="utf-8")
    open_now, entry = pcb.is_open("betmgm", state_path=state_path, now=lambda: 1.0)
    assert open_now is False
    assert entry is None
    # record_result must also tolerate the corrupt file (treated as empty state)
    updated = pcb.record_result("betmgm", False, reason="x", state_path=state_path,
                                now=lambda: 2.0)
    assert updated["consecutive_failures"] == 1


def test_atomic_write_round_trips(state_path):
    pcb.record_result("fanduel", False, reason="500", state_path=state_path, now=lambda: 42.0)
    assert state_path.is_file()
    raw = json.loads(state_path.read_text(encoding="utf-8"))
    assert raw["fanduel"]["last_reason"] == "500"
    assert raw["fanduel"]["last_result_at"] == 42.0
    # no leftover tmp file
    assert not state_path.with_suffix(state_path.suffix + ".tmp").exists()


def test_filter_providers_empty_input_never_raises(state_path):
    kept, skipped = pcb.filter_providers([], state_path=state_path, now=lambda: 1.0)
    assert kept == []
    assert skipped == []


def test_half_open_retry_failure_reopens_with_fresh_cooldown(state_path):
    """Regression (Opus fix-round finding): a failed half-open retry must get a
    FRESH opened_since, not be retried every cycle forever. Sequence: 3 fails ->
    open at t=2.0; is_open past a 100s cooldown -> half-open (state cleared);
    one more failure -> re-opens with A NEW opened_since; is_open immediately
    after must be True (fresh cooldown), not False (the bug: stale timestamp
    already looked "expired")."""
    for i in range(3):
        pcb.record_result("betmgm", False, reason="400", state_path=state_path,
                          now=lambda i=i: 0.0 + i)
    open_now, entry = pcb.is_open("betmgm", state_path=state_path, now=lambda: 2.0,
                                  cooldown_sec=100.0)
    assert open_now is True
    assert entry["opened_since"] == 2.0

    # Cooldown elapses -> half-open (this call must persist the transition).
    open_now, entry = pcb.is_open("betmgm", state_path=state_path, now=lambda: 200.0,
                                  cooldown_sec=100.0)
    assert open_now is False
    assert entry is None
    raw = json.loads(state_path.read_text(encoding="utf-8"))
    assert raw["betmgm"]["opened_since"] is None
    assert raw["betmgm"]["consecutive_failures"] == 0

    # Half-open retry FAILS 3x (fresh streak) -> must re-open with a NEW timestamp.
    for i in range(3):
        pcb.record_result("betmgm", False, reason="400 again", state_path=state_path,
                          now=lambda i=i: 200.0 + i)
    open_now, entry = pcb.is_open("betmgm", state_path=state_path, now=lambda: 202.0,
                                  cooldown_sec=100.0)
    # THE BUG: without the fix this was False (stale opened_since=2.0 already
    # looked >= cooldown at t=202, so age >= cooldown_sec was already true).
    assert open_now is True
    assert entry["opened_since"] == 202.0  # fresh (3rd failure's ts), not the original 2.0
    assert entry["consecutive_failures"] == 3
